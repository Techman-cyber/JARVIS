SERIOUS_PROMPT = """You are Jarvis, a terse, highly competent personal assistant.
You do not joke, editorialize, or pad your responses. You confirm actions taken
in as few words as possible. Think: military ops assistant, not a chatbot."""

CASUAL_PROMPT = """You are Jarvis, a witty and warm personal assistant, in the
style of Tony Stark's AI. You're helpful first, playful second. Keep replies
short - one or two sentences unless the user asks for detail."""


def get_personality_prompt(mode: str) -> str:
    return SERIOUS_PROMPT if mode == "serious" else CASUAL_PROMPT


import random
from weather import get_current_weather

_CASUAL_OPENERS = [
    "Hey, good to see you.",
    "Well, look who's back.",
    "Hey there.",
]

_SERIOUS_OPENERS = [
    "Systems online.",
    "Standing by.",
    "All systems nominal.",
]


def build_greeting(mode: str) -> str:
    """Builds the conversational startup line: an opener, current weather
    (if it could be fetched), and - in casual mode only - a couple of
    genuinely conversational questions, so Jarvis feels like it's actually
    checking in rather than just announcing it's running."""
    casual = mode != "serious"
    opener = random.choice(_CASUAL_OPENERS if casual else _SERIOUS_OPENERS)
    parts = [opener]

    weather = get_current_weather()
    if weather:
        parts.append(f"By the way, {weather}." if casual else f"Current conditions: {weather}.")

    if casual:
        parts.append("How are you doing, and what are you up to today?")
    else:
        parts.append("Ready for instructions.")

    return " ".join(parts)