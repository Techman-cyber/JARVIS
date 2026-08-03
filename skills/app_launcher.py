"""
Opens apps the same way a person would by hand: press the Windows key,
type the name into Windows Search, and press Enter to launch whatever
comes up as the top suggestion.

This replaces trying to guess an exact executable name/path (which is why
things like Word were failing - 'winword.exe' isn't reliably on PATH even
though typing 'word' into Windows Search finds it instantly). Using the
same search Windows already provides means it works for anything Windows
can already find - installed apps, Store apps, settings pages, etc.

Requires: pyautogui (already a project dependency).
"""

import time
import pyautogui

import config

pyautogui.FAILSAFE = True  # moving mouse to a screen corner aborts, as a safety valve

SEARCH_OPEN_DELAY = 0.6      # time for the Start/Search menu to animate open
TYPE_INTERVAL = 0.02         # seconds between simulated keystrokes
RESULTS_SETTLE_DELAY = 0.9   # time for search results to populate before hitting Enter


def open_app(app_name: str) -> str:
    """
    Opens an app by simulating: Win key -> type app_name -> Enter.
    Launches whichever result Windows Search shows as the top suggestion -
    exactly like doing it manually.
    """
    if not app_name:
        return "I need a name of something to open."

    # config.APP_ALIASES can still map a spoken name to a cleaner search
    # term (e.g. 'vscode' -> 'vs code'). If there's no mapping, or the
    # mapping is a raw executable name from the old direct-launch approach,
    # just search for the name as typed.
    query = config.APP_ALIASES.get(app_name.lower(), app_name)
    if query.lower().endswith(".exe"):
        query = query[:-4]
    if query.endswith(":"):  # things like 'ms-settings:' don't work as search text
        query = app_name

    try:
        pyautogui.press("win")
        time.sleep(SEARCH_OPEN_DELAY)
        pyautogui.write(query, interval=TYPE_INTERVAL)
        time.sleep(RESULTS_SETTLE_DELAY)
        pyautogui.press("enter")
        return f"Opening {app_name}."
    except Exception as e:
        return f"Couldn't open '{app_name}': {e}"


if __name__ == "__main__":
    # Quick manual test: python app_launcher.py "word"
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "notepad"
    print(f"Opening Start menu in 2 seconds, then searching for {name!r}...")
    time.sleep(2)
    print(open_app(name))