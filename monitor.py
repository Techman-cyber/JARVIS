"""
Background topic monitoring for Jarvis - the "Mark L"-style feature where
you tell it to watch a topic, and it checks once a day for new headlines
and mentions it proactively (see proactive.py) instead of you having to ask.

Fully opt-in: nothing is monitored until you explicitly add a topic. State
(topics + last-seen headline per topic) is stored in monitor_state.json next
to this file, so it survives restarts.
"""

import os
import json
import time

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE_DIR, "monitor_state.json")

# Crypto/financial/trading topics are blocked at the code level regardless of
# what's requested - this assistant isn't the right tool for anything that
# could be read as financial advice or trading signals.
_BLOCKED_KEYWORDS = [
    "crypto", "bitcoin", "btc", "eth", "ethereum", "nft", "trading", "stock",
    "stocks", "forex", "investment", "invest", "shares", "dividend",
]

CHECK_INTERVAL_SECONDS = 24 * 60 * 60  # once a day per topic


def _is_blocked(topic: str) -> bool:
    lowered = topic.lower()
    return any(kw in lowered for kw in _BLOCKED_KEYWORDS)


def _load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def add_monitor(topic: str) -> str:
    topic = topic.strip()
    if not topic:
        return "Give me a topic to monitor."
    if _is_blocked(topic):
        return "I don't monitor crypto, trading, or financial topics - that's a hard line, not a preference."

    state = _load_state()
    if topic.lower() in state:
        return f"Already keeping an eye on '{topic}'."
    state[topic.lower()] = {"topic": topic, "last_headline": "", "last_checked": 0}
    _save_state(state)
    return f"Got it - I'll keep an eye on '{topic}' and let you know if anything new comes up."


def remove_monitor(topic: str) -> str:
    topic = topic.strip().lower()
    state = _load_state()
    if topic not in state:
        return f"I wasn't monitoring '{topic}' to begin with."
    del state[topic]
    _save_state(state)
    return f"Stopped monitoring '{topic}'."


def list_monitors() -> list:
    state = _load_state()
    return [entry["topic"] for entry in state.values()]


def check_all_due() -> list:
    """Checks every monitored topic that's due (hasn't been checked in the
    last CHECK_INTERVAL_SECONDS), and returns a list of natural-language
    strings for any topic that has a genuinely new headline since last time.
    Best-effort: a failed lookup for one topic doesn't block the others, and
    if duckduckgo_search isn't installed this just returns an empty list
    rather than erroring."""
    if DDGS is None:
        return []

    state = _load_state()
    if not state:
        return []

    updates = []
    now = time.time()
    changed = False

    for key, entry in state.items():
        if now - entry.get("last_checked", 0) < CHECK_INTERVAL_SECONDS:
            continue

        topic = entry["topic"]
        try:
            with DDGS() as ddgs:
                results = list(ddgs.news(topic, max_results=3))
        except Exception:
            continue  # skip this topic this round, try again next check

        entry["last_checked"] = now
        changed = True

        if not results:
            continue

        top_title = results[0].get("title", "")
        if top_title and top_title != entry.get("last_headline"):
            entry["last_headline"] = top_title
            updates.append(f"an update on '{topic}': {top_title}")

    if changed:
        _save_state(state)

    return updates


if __name__ == "__main__":
    print("Monitored topics:", list_monitors() or "(none)")
    print("Checking now...")
    print(check_all_due() or "Nothing new.")
