"""
Background 'wake word' listener - runs continuously in its own thread so
saying "Jarvis" while Jarvis is mid-reply interrupts it immediately.

Terminal (main.py) only - the browser HUD's voice output isn't handled here.

Note: this keeps a mic stream open and sends short audio chunks to Google's
free speech API continuously while active, so it uses more bandwidth/quota
than push-to-talk mode. If you're on limited data or hitting rate limits,
you can skip starting this and the rest of Jarvis works the same.
"""

import speech_recognition as sr
import config
import tts

_recognizer = sr.Recognizer()
_recognizer.pause_threshold = 0.5
_recognizer.non_speaking_duration = 0.3

_stop_listening = None
_mic = None


def _callback(recognizer, audio):
    if not tts.is_speaking():
        return  # only worth checking while Jarvis is actually talking
    try:
        text = recognizer.recognize_google(audio).lower()
    except (sr.UnknownValueError, sr.RequestError):
        return

    if "jarvis" in text:
        print("[wake] Heard 'Jarvis' - interrupting.")
        tts.stop()


def start():
    """Starts listening in the background. Call once at Jarvis startup."""
    global _stop_listening, _mic
    try:
        _mic = sr.Microphone(device_index=config.MIC_DEVICE_INDEX)
        with _mic as source:
            _recognizer.adjust_for_ambient_noise(source, duration=0.4)
    except OSError as e:
        print(f"[wake] Couldn't open a mic for the interrupt listener ({e}) - "
              f"'say Jarvis to interrupt' is disabled, everything else still works.")
        return

    _stop_listening = _recognizer.listen_in_background(_mic, _callback, phrase_time_limit=3)
    print("[wake] Say 'Jarvis' any time to interrupt while it's talking.")


def pause():
    """Temporarily stops background listening - call before /voice mode
    captures a command on the same mic, to avoid two streams fighting over
    one device."""
    global _stop_listening
    if _stop_listening:
        _stop_listening(wait_for_stop=False)
        _stop_listening = None


def resume():
    """Resumes background listening after pause()."""
    global _stop_listening
    if _mic and not _stop_listening:
        _stop_listening = _recognizer.listen_in_background(_mic, _callback, phrase_time_limit=3)
