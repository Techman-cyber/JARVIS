"""
Central configuration for Jarvis.
Set your Google Gemini API key as an environment variable before running:

    setx GOOGLE_API_KEY "your-key-here"

(then open a NEW terminal so it picks up the variable)

Get a free key (no credit card) at https://aistudio.google.com/apikey
"""

import os

GOOGLE_API_KEY = "AQ.Ab8RN6L2eOsTZbWImQKzfdnG91QQ6yWZwU18tFYAT_tQHlwG6g"

# --- ElevenLabs (voice) ---
# Set your ElevenLabs API key as an environment variable before running:
#
#     setx ELEVENLABS_API_KEY "your-key-here"
#
# (then open a NEW terminal so it picks up the variable)
# Get a key at https://elevenlabs.io/app/settings/api-keys
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# Voice to speak replies in.
ELEVENLABS_VOICE_ID = "a4CnuaYbALRvW39mDitg"

# ElevenLabs TTS model. "eleven_turbo_v2_5" is fast/low-latency and cheap on
# credits - good for an assistant that talks back a lot. Swap to
# "eleven_multilingual_v2" for higher quality if latency isn't a concern.
ELEVENLABS_MODEL = "eleven_turbo_v2_5"

# --- Edge TTS (free fallback voice, no API key needed) ---
# Used automatically if ElevenLabs isn't set up or fails. Sounds much more
# natural than the offline pyttsx3 voice. Some good Jarvis-ish options:
#   "en-GB-RyanNeural"      - British male, calm (closest to movie-Jarvis)
#   "en-US-GuyNeural"       - American male
#   "en-US-ChristopherNeural" - American male, deeper
# Full list: run `edge-tts --list-voices` after installing the package.
EDGE_TTS_VOICE = "en-GB-RyanNeural"

# gemini-3.5-flash-lite: current-generation, fast, and free-tier eligible.
# Swap to "gemini-3.6-flash" for noticeably smarter (but pricier/rate-limited) responses.
MODEL = "gemini-3.5-flash-lite"

# Used by voice_live.py for real-time streaming voice conversations.
VOICE_MODEL = "gemini-3.1-flash-live-preview"

# Microphone device index for stt.py. Leave as None to use the system default
# mic. If /voice mode isn't picking up your voice, run this to see your
# devices and their indices, then set the right one here:
#
#     python -c "import speech_recognition as sr; print(list(enumerate(sr.Microphone.list_microphone_names())))"
MIC_DEVICE_INDEX = None

# "serious" = terse, mission-focused, minimal chatter (classic Jarvis)
# "casual"  = friendlier, more conversational
MODE = "casual"

# If True, Jarvis asks "Are you sure?" before delete/move/shutdown/overwrite.
CONFIRM_DESTRUCTIVE_ACTIONS = True

# If True, Jarvis remembers conversations persistently (memory.py) - across
# restarts and across days, not just within one session. Stored locally in
# memory.db + memory_summary.txt next to this file. Say "/forget" (terminal)
# or POST /forget (server) to wipe it. Set to False to disable entirely.
MEMORY_ENABLED = True

# Root folders Jarvis is allowed to search/open/modify by default.
# Add more paths here as you trust it with more of your filesystem.
ALLOWED_ROOTS = [
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
]

# Friendly name -> actual executable / protocol Windows understands.
# Add your own apps here.
APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "vscode": "code.exe",
    "vs code": "code.exe",
    "spotify": "spotify.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
}