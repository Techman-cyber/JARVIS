"""
Text-to-speech for Jarvis.

Primary voice: ElevenLabs (set ELEVENLABS_API_KEY in config.py / env).
Falls back to the offline pyttsx3 engine if no key is set, or if the
ElevenLabs call fails for any reason (network down, rate limit, bad key,
etc.) so a bad connection never kills the assistant's ability to talk.

Uses pygame's mixer (not `playsound`) to play the ElevenLabs MP3, because
mixer.music can be stopped mid-playback - required for the "say Jarvis to
interrupt" feature in wake_listener.py.
"""

import os
import tempfile
import time
import asyncio

import requests
import pyttsx3
import pygame
import config

try:
    import edge_tts
    _HAS_EDGE_TTS = True
except ImportError:
    _HAS_EDGE_TTS = False

pygame.mixer.init()

_pyttsx_engine = None
_elevenlabs_available = None  # None = not checked yet, True/False after first check
_edge_available = None        # same, for the edge-tts fallback tier
_speaking = False             # True while audio is actively playing - checked by wake_listener


def is_speaking() -> bool:
    return _speaking


def stop():
    """Immediately cuts off whatever Jarvis is currently saying."""
    global _speaking
    _speaking = False
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
    try:
        _get_pyttsx_engine().stop()
    except Exception:
        pass


def _get_pyttsx_engine():
    global _pyttsx_engine
    if _pyttsx_engine is None:
        _pyttsx_engine = pyttsx3.init()
        _pyttsx_engine.setProperty("rate", 185)
    return _pyttsx_engine


def _speak_offline(text: str):
    global _speaking
    _speaking = True
    engine = _get_pyttsx_engine()
    engine.say(text)
    engine.runAndWait()
    _speaking = False


def _play_mp3_file(path: str):
    """Shared interruptible playback for any mp3 on disk (ElevenLabs or edge-tts)."""
    global _speaking
    pygame.mixer.music.load(path)
    _speaking = True
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if not _speaking:  # stop() was called from another thread
            pygame.mixer.music.stop()
            break
        time.sleep(0.05)
    _speaking = False
    pygame.mixer.music.unload()


def _speak_edge(text: str):
    """Free, no-key-required neural voice via Microsoft Edge's TTS service.
    Sounds far more natural than pyttsx3 - good middle fallback tier."""
    if not _HAS_EDGE_TTS:
        raise RuntimeError("edge-tts not installed - run: pip install edge-tts")

    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        async def _generate():
            communicate = edge_tts.Communicate(text, config.EDGE_TTS_VOICE)
            await communicate.save(path)

        asyncio.run(_generate())
        _play_mp3_file(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _speak_elevenlabs(text: str):
    global _speaking

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": config.ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error {response.status_code}: {response.text[:300]}")

    fd, path = tempfile.mkstemp(suffix=".mp3")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(response.content)
        _play_mp3_file(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def speak(text: str):
    global _elevenlabs_available, _edge_available

    if not text:
        return

    if config.ELEVENLABS_API_KEY and _elevenlabs_available is not False:
        try:
            _speak_elevenlabs(text)
            _elevenlabs_available = True
            return
        except Exception as e:
            print(f"[tts] ElevenLabs failed, trying edge-tts. Reason: {e}")
            _elevenlabs_available = False

    if _HAS_EDGE_TTS and _edge_available is not False:
        try:
            _speak_edge(text)
            _edge_available = True
            return
        except Exception as e:
            print(f"[tts] edge-tts failed, falling back to offline voice. Reason: {e}")
            _edge_available = False

    _speak_offline(text)


if __name__ == "__main__":
    if not config.ELEVENLABS_API_KEY:
        print("ELEVENLABS_API_KEY is not set - would fall back to offline voice.")
    else:
        print(f"Using ElevenLabs voice {config.ELEVENLABS_VOICE_ID}...")
    speak("This is a test of the Jarvis voice system.")