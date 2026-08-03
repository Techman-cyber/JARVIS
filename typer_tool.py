"""
Types text into whatever window currently has focus - used so Jarvis can
open an app (Notepad, Word, etc.) and actually type content into it, rather
than only saving content to a file on disk.

Requires: pip install pyautogui
"""

import time
import os
import datetime
import pyautogui

pyautogui.FAILSAFE = True  # moving mouse to a screen corner aborts, as a safety valve


def type_into_active_window(content: str, delay_before: float = 1.8, interval: float = 0.012):
    """
    delay_before: seconds to wait before typing, so the target app has time
    to actually open and grab window focus first. Bump this up if Jarvis
    starts typing before the app is ready (slow machine, slow-launching app).
    """
    if not content:
        return
    time.sleep(delay_before)
    pyautogui.typewrite(content, interval=interval)


def press_hotkey(*keys):
    """Sends a key combo to whatever window has focus, e.g. press_hotkey('ctrl', '+')."""
    pyautogui.hotkey(*keys)


def take_screenshot(save_dir: str = None) -> str:
    """Captures the full screen and saves it as a PNG. Returns the saved path."""
    save_dir = save_dir or os.path.expanduser("~/Desktop/Jarvis Screenshots")
    os.makedirs(save_dir, exist_ok=True)
    filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = os.path.join(save_dir, filename)
    pyautogui.screenshot().save(path)
    return path