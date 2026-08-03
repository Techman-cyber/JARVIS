import sys
import speech_recognition as sr
import config

try:
    import winsound
    _HAS_BEEP = True
except ImportError:
    _HAS_BEEP = False  # not on Windows

_recognizer = sr.Recognizer()
_recognizer.pause_threshold = 1.3        # allow a longer natural pause mid-sentence before cutting off
_recognizer.non_speaking_duration = 0.5


def list_microphones():
    """Prints every mic Python can see, with its index, so you can set
    config.MIC_DEVICE_INDEX to the right one."""
    names = sr.Microphone.list_microphone_names()
    for i, name in enumerate(names):
        print(f"[{i}] {name}")
    return names


def listen(timeout: int = 8, phrase_time_limit: int = 15) -> str:
    """Listens on the configured microphone and returns recognized text.

    Calibration is short and followed by an audible beep as the exact
    'start talking now' cue - waiting for the beep (instead of the printed
    text, which can lag behind due to console buffering) fixes the common
    issue where the first couple words get clipped.
    """
    try:
        mic = sr.Microphone(device_index=config.MIC_DEVICE_INDEX)
    except OSError as e:
        print(f"[stt] Couldn't open a microphone ({e}). "
              f"Run stt.list_microphones() to see available devices and set "
              f"MIC_DEVICE_INDEX in config.py.")
        return ""

    with mic as source:
        print("[stt] Calibrating...", flush=True)
        # 0.3s was too short to get a reliable noise floor on a lot of setups -
        # a bad threshold from this step is the single most common cause of
        # "heard something but couldn't make out words" (garbled/clipped audio
        # going to Google) or a timeout that never picks up your voice at all.
        _recognizer.adjust_for_ambient_noise(source, duration=1.0)
        print(f"[stt] Energy threshold set to {_recognizer.energy_threshold:.0f}", flush=True)

        if _HAS_BEEP:
            winsound.Beep(880, 120)
        print("[stt] Listening now - go ahead.", flush=True)

        try:
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            print("[stt] Timed out waiting for speech - didn't hear anything.")
            return ""

    if _HAS_BEEP:
        winsound.Beep(440, 100)
    print("[stt] Got audio, sending to Google for recognition...", flush=True)
    try:
        text = _recognizer.recognize_google(audio)
        print(f"[stt] Recognized: {text}")
        return text
    except sr.UnknownValueError:
        print("[stt] Heard something but couldn't make out words.")
        return ""
    except sr.RequestError as e:
        print(f"[stt] Speech recognition request failed (likely no internet or "
              f"Google API issue): {e}")
        return f"[speech recognition error: {e}]"


if __name__ == "__main__":
    # Run this file directly to debug your mic setup:  python stt.py
    print("Available microphones:")
    list_microphones()
    print(f"\nUsing MIC_DEVICE_INDEX = {config.MIC_DEVICE_INDEX} (None = system default)")
    print("Wait for the beep, then say something...")
    result = listen()
    print(f"\nFinal result: {result!r}")