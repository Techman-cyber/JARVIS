# Jarvis - Personal Assistant (Windows)

A text/voice assistant that uses Claude to understand what you want and
executes it: opening apps, finding/reading/writing files, locking your PC,
shutting down, opening websites, or just chatting.

## Setup

1. **Install Python 3.10+** if you don't have it: https://www.python.org/downloads/
   (check "Add Python to PATH" during install)

2. **Get a free Google Gemini API key** at https://aistudio.google.com/apikey
   No credit card required. The free tier has daily/per-minute limits but is
   genuinely free with no expiration.

3. **Set the key as an environment variable** (Command Prompt):
   ```
   setx GOOGLE_API_KEY "your-key-here"
   ```
   Close and reopen your terminal after this so it takes effect.

4. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```
   Note: `PyAudio` sometimes fails to install via pip on Windows. If it does:
   ```
   pip install pipwin
   pipwin install pyaudio
   ```

5. **Run it**:
   ```
   python main.py
   ```

## Using it

Type or say things like:
- "open notepad"
- "search my documents for budget"
- "read C:/Users/you/Desktop/notes.txt"
- "lock my screen"
- "delete C:/Users/you/Downloads/old_file.txt"  → will ask you to confirm
- "switch to serious mode"
- "what's a good name for a dog"  → just chats

Meta commands (type directly):
- `/voice` and `/text` — switch input mode
- `/serious` and `/casual` — switch personality
- `/mute` / `/unmute` — toggle spoken replies
- `/exit` — quit

## Safety design (please read before loosening these)

- **File access is restricted** to the folders listed in `ALLOWED_ROOTS`
  inside `config.py` (Desktop, Documents, Downloads by default). Add more
  folders there as you trust the assistant with more of your system.
- **Deletes go to the Recycle Bin**, not permanent deletion, via `send2trash`.
- **Destructive actions require a "yes" confirmation**: delete, move,
  overwrite, shutdown, restart. You can turn this off in `config.py` by
  setting `CONFIRM_DESTRUCTIVE_ACTIONS = False`, but I'd leave it on.
- Voice recognition (`stt.py`) uses Google's free web speech API through the
  `SpeechRecognition` library, which sends audio to Google's servers over the
  internet. If that's a problem for you, swap it for an offline engine like
  `vosk`.
- **Gemini free-tier limits**: `gemini-2.5-flash-lite` (the default model)
  allows roughly 15 requests/minute and 1,000/day at the time of writing -
  plenty for personal use, but if you hit a rate-limit error, wait a minute
  and try again, or switch `MODEL` in `config.py` to `gemini-2.5-flash` for
  a different quota. Limits change over time - check
  https://ai.google.dev/gemini-api/docs/rate-limits for current numbers.

## Using the visual interface (optional)

Instead of the plain terminal (`main.py`), you can run Jarvis with the HUD-style
web interface:

1. Install the extra dependencies (already in `requirements.txt`): `flask`, `flask-cors`
2. Start the bridge server:
   ```
   python server.py
   ```
   Leave this terminal window running - it's what actually talks to Claude and
   executes commands.
3. Open `interface/index.html` in Chrome or Edge (double-click it, or right-click
   → Open with → Chrome).
4. Type in the command bar at the bottom, or click the ● mic button to speak
   (uses your browser's built-in speech recognition).

Destructive actions (delete/move/overwrite/shutdown) will pop up a browser
confirm dialog before the server actually executes them - same safety model
as the terminal version, just visual.

The interface is a static HTML file with no build step, so you can host it
anywhere or open it directly from disk - it just needs `server.py` running
on `localhost:8000`.

## Extending it

- **Add apps**: edit `APP_ALIASES` in `config.py`.
- **Add new abilities**: write a function in `skills/`, register it in the
  `intent` enum inside `nlu.py`'s `ROUTER_TOOL`, and wire it up in
  `executor.py`'s `handlers` dict. Examples of things you could add next:
  calendar/email integration, Spotify control, smart home devices, running
  scripts, git operations, browser automation.
- **Wake word ("Hey Jarvis")**: the current voice mode is push-to-talk style
  (it listens once per turn). For always-listening wake-word detection, add
  a library like `pvporcupine` and have it trigger `stt.listen()` when heard.
