"""
Persistent memory for Jarvis - so it remembers what you talked about, even
days later, without you having to explicitly say "remember this".

How it works:
- Every real exchange (what you said + what Jarvis replied) is logged to a
  local SQLite database (memory.db), with a timestamp, and kept forever.
- Raw history would eventually get too big to stuff into every Gemini call,
  so a compact "memory summary" is kept alongside it - a short running
  paragraph of durable facts/preferences/ongoing topics (e.g. "user's name
  is X", "working on project Y", "prefers casual mode", "asked to be
  reminded about Z"). This gets updated automatically every
  SUMMARIZE_EVERY_N_TURNS turns, using Gemini itself to merge new turns into
  the existing summary.
- Every command Jarvis processes gets BOTH injected into the system prompt:
  the long-term summary (covers anything from a previous session/day/week)
  and the last few raw turns (for immediate back-and-forth continuity).

Nothing here requires an extra dependency - just the standard library plus
whatever's already used elsewhere (google-generativeai, only imported lazily
when a summarization actually runs).
"""

import os
import sqlite3
import time
import datetime

import config

import sys

# Detect if running as a PyInstaller compiled executable
if getattr(sys, 'frozen', False):
    # Saves memory files right next to Jarvis.exe in its actual folder
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Saves memory files in the project root directory when running via python memory.py
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, "memory.db")
SUMMARY_PATH = os.path.join(BASE_DIR, "memory_summary.txt")

# How many raw turns (user+jarvis pairs) to always include verbatim in every
# prompt, regardless of age - keeps immediate continuity even right after a
# fresh summarization run.
RECENT_TURNS_LIMIT = 12

# Re-summarize once this many new turns have piled up since the last run -
# keeps the summary from ever going stale, without re-summarizing on every
# single message (that would be a wasted extra Gemini call each time).
SUMMARIZE_EVERY_N_TURNS = 20


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            user_text TEXT NOT NULL,
            jarvis_reply TEXT NOT NULL,
            summarized INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    return conn


def remember_turn(user_text: str, jarvis_reply: str):
    """Call this once per real exchange. Skip meta commands (/mute, /voice,
    etc.) - those aren't conversation content worth remembering."""
    if not getattr(config, "MEMORY_ENABLED", True):
        return
    if not user_text or not jarvis_reply:
        return
    conn = _get_conn()
    conn.execute(
        "INSERT INTO turns (ts, user_text, jarvis_reply) VALUES (?, ?, ?)",
        (time.time(), user_text, jarvis_reply),
    )
    conn.commit()
    conn.close()
    _maybe_summarize()


def _load_summary() -> str:
    if os.path.exists(SUMMARY_PATH):
        with open(SUMMARY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _save_summary(text: str):
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write(text.strip())


def get_recent_turns(limit: int = RECENT_TURNS_LIMIT):
    conn = _get_conn()
    rows = conn.execute(
        "SELECT ts, user_text, jarvis_reply FROM turns ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return list(reversed(rows))  # oldest -> newest


def build_context_block() -> str:
    """Returns a block of text to fold into the Gemini system prompt so
    Jarvis has both long-term and short-term memory of the user. Returns ""
    if there's nothing yet (brand new install) or memory is disabled."""
    if not getattr(config, "MEMORY_ENABLED", True):
        return ""

    summary = _load_summary()
    recent = get_recent_turns()

    parts = []
    if summary:
        parts.append(
            "Long-term memory about the user (learned across past "
            "conversations, possibly days or weeks ago):\n" + summary
        )

    if recent:
        lines = []
        for ts, user_text, jarvis_reply in recent:
            when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{when}] User: {user_text}\n[{when}] Jarvis: {jarvis_reply}")
        parts.append(
            "Recent conversation history (may span multiple sessions/days):\n"
            + "\n".join(lines)
        )

    if not parts:
        return ""

    return (
        "=== MEMORY CONTEXT ===\n"
        + "\n\n".join(parts)
        + "\n=== END MEMORY CONTEXT ===\n"
        "Use the above naturally if it's relevant to the current message (e.g. "
        "the user references something from before, asks what you talked about "
        "earlier, or a past preference/fact applies now). Don't recite it "
        "verbatim or mention 'memory context'/'summary' out loud - just respond "
        "like you genuinely remember, the way a person would."
    )


def _maybe_summarize():
    conn = _get_conn()
    unsummarized_count = conn.execute(
        "SELECT COUNT(*) FROM turns WHERE summarized = 0"
    ).fetchone()[0]
    conn.close()

    if unsummarized_count >= SUMMARIZE_EVERY_N_TURNS:
        _run_summarization()


def _run_summarization():
    """Merges all not-yet-summarized turns into the running summary using
    Gemini, then marks those turns as summarized. Best-effort: if it fails
    (offline, bad key, rate limit) it just quietly tries again next time -
    raw turns stay in the DB either way, nothing is lost."""
    try:
        import google.generativeai as genai
    except ImportError:
        return

    if not config.GOOGLE_API_KEY:
        return

    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, ts, user_text, jarvis_reply FROM turns WHERE summarized = 0 ORDER BY id ASC"
    ).fetchall()
    conn.close()

    if not rows:
        return

    old_summary = _load_summary()
    transcript_lines = []
    for _id, ts, user_text, jarvis_reply in rows:
        when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        transcript_lines.append(f"[{when}] User: {user_text}\n[{when}] Jarvis: {jarvis_reply}")
    transcript = "\n".join(transcript_lines)

    prompt = (
        "You maintain a compact long-term memory profile for a personal voice/text "
        "assistant named Jarvis, about its one user. Below is the EXISTING memory "
        "summary, followed by a NEW batch of conversation turns. Merge them into a "
        "single updated summary.\n\n"
        "Rules:\n"
        "- Keep only durable, useful facts: the user's name, preferences, ongoing "
        "projects, recurring topics, things they asked you to remember, important "
        "dates/decisions, running jokes - anything that would help you pick up a "
        "conversation naturally days or weeks later.\n"
        "- Drop one-off small talk, one-time file paths/commands, and anything with "
        "no lasting relevance.\n"
        "- Keep it under ~300 words, written as plain notes, not a transcript.\n"
        "- If new turns update or contradict something old (the user changed their "
        "mind, a project finished, etc.), update it - don't keep both versions.\n\n"
        f"EXISTING SUMMARY:\n{old_summary or '(none yet)'}\n\n"
        f"NEW TURNS:\n{transcript}\n\n"
        "Return ONLY the updated summary text, nothing else - no preamble, no headers."
    )

    try:
        genai.configure(api_key=config.GOOGLE_API_KEY)
        model = genai.GenerativeModel(model_name=config.MODEL)
        response = model.generate_content(prompt, request_options={"timeout": 30})
        new_summary = (response.text or "").strip()
        if not new_summary:
            return
    except Exception as e:
        print(f"[memory] Summarization failed, will retry once more turns pile up: {e}")
        return

    _save_summary(new_summary)

    conn = _get_conn()
    ids = [str(r[0]) for r in rows]
    conn.execute(f"UPDATE turns SET summarized = 1 WHERE id IN ({','.join(ids)})")
    conn.commit()
    conn.close()
    print(f"[memory] Summarized {len(rows)} turn(s) into an updated memory profile.")


def forget_everything():
    """Wipes all memory - raw turns AND the running summary. This is personal
    data sitting in a local file, so there's a manual escape hatch (wired up
    as the '/forget' command in main.py, and available over the API too)."""
    conn = _get_conn()
    conn.execute("DELETE FROM turns")
    conn.commit()
    conn.close()
    if os.path.exists(SUMMARY_PATH):
        os.remove(SUMMARY_PATH)


if __name__ == "__main__":
    # Quick manual check: python memory.py
    print(f"DB: {DB_PATH}")
    print(f"Summary file: {SUMMARY_PATH}\n")
    print("--- Current summary ---")
    print(_load_summary() or "(none yet)")
    print("\n--- Recent turns ---")
    for ts, u, j in get_recent_turns():
        when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        print(f"[{when}] You: {u}\n[{when}] Jarvis: {j}\n")
