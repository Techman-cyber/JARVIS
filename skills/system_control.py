import ctypes
import subprocess
import webbrowser


def lock_screen() -> str:
    ctypes.windll.user32.LockWorkStation()
    return "Locking the screen."


def shutdown(confirmed: bool = False) -> str:
    if not confirmed:
        return "CONFIRM_REQUIRED"
    subprocess.run(["shutdown", "/s", "/t", "5"])
    return "Shutting down in 5 seconds."


def restart(confirmed: bool = False) -> str:
    if not confirmed:
        return "CONFIRM_REQUIRED"
    subprocess.run(["shutdown", "/r", "/t", "5"])
    return "Restarting in 5 seconds."


def set_volume(level: int) -> str:
    """Requires: pip install pycaw comtypes"""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(max(0, min(level, 100)) / 100, None)
        return f"Volume set to {level}%."
    except ImportError:
        return "Volume control needs: pip install pycaw comtypes"


def open_url(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opening {url}."


def web_search(query: str) -> str:
    webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
    return f"Searching the web for '{query}'."
