"""
Proactive check-ins: decides if/when Jarvis should say something unprompted
during a live voice session, and what focus area to bring up. Rotates
between three angles so it never opens with the same kind of line twice in
a row, and respects a cooldown so it's not intrusive.

This module only decides WHETHER to speak and WHAT TOPIC/ANGLE to speak
about - it doesn't generate the actual sentence. voice_live.py takes the
returned angle/context and asks Gemini to phrase something natural from it,
the same way the rest of Jarvis already works.
"""

import time
import datetime

import memory
import monitor

COOLDOWN_SECONDS = 20 * 60  # 20 minutes between proactive check-ins

_last_checkin_time = 0.0
_last_angle = None  # avoid repeating the same angle twice in a row


def _time_of_day_tone() -> str:
    hour = datetime.datetime.now().hour
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def maybe_check_in() -> dict | None:
    """Returns a dict like {'angle': 'monitor', 'context': '...'} if Jarvis
    should proactively say something right now, or None if it's too soon /
    there's nothing worth bringing up. Call this periodically (e.g. every
    minute) from the idle loop of the live session."""
    global _last_checkin_time, _last_angle

    now = time.time()
    if now - _last_checkin_time < COOLDOWN_SECONDS:
        return None

    tone = _time_of_day_tone()

    # Rotate through angles, skipping whichever one we used last time so two
    # check-ins in a row don't feel identical.
    candidates = []

    monitor_updates = monitor.check_all_due()
    if monitor_updates and _last_angle != "monitor":
        candidates.append(("monitor", monitor_updates[0]))

    summary = memory._load_summary() if hasattr(memory, "_load_summary") else ""
    if summary and _last_angle != "project":
        candidates.append(("project", f"({tone}) Based on what you know about the user's "
                                       f"ongoing projects/preferences, ask a brief, natural "
                                       f"follow-up question about one of them:\n{summary}"))

    recent = memory.get_recent_turns(limit=8)
    if recent and _last_angle != "recent":
        last_user_line = recent[-1][1]
        candidates.append(("recent", f"({tone}) Bring up a brief, natural follow-up related to "
                                      f"what the user was just discussing: \"{last_user_line}\""))

    if not candidates:
        return None

    angle, context = candidates[0]
    _last_checkin_time = now
    _last_angle = angle
    return {"angle": angle, "context": context}
