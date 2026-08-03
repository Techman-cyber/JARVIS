"""
Turns free-text/voice input into a structured intent using Google Gemini
(free tier - no billing required). Uses function calling, forced to always
call route_command, so we get reliable structured output back instead of
hoping the model formats JSON correctly on its own.
"""

import time
import config
import memory
from personality import get_personality_prompt

_configured = False
_genai = None  # lazy-loaded - google.generativeai is one of the heaviest
                # imports in this project (pulls in grpc/protobuf), so we
                # defer it until the first actual command instead of paying
                # that cost during app startup.


def _get_genai():
    global _genai
    if _genai is None:
        import google.generativeai as genai
        _genai = genai
    return _genai

ROUTE_FUNCTION = {
    "name": "route_command",
    "description": "Classify the user's command into a structured action for the assistant to execute.",
    "parameters": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "open_app",
                    "open_file",
                    "search_files",
                    "read_file",
                    "write_file",
                    "type_in_app",
                    "screenshot",
                    "delete_file",
                    "move_file",
                    "lock_screen",
                    "shutdown",
                    "close_app",
                    "set_volume",
                    "open_url",
                    "web_search",
                    "set_mode",
                    "chat",
                ],
                "description": "The category of action requested.",
            },
            "app_name": {"type": "string", "description": "For open_app or type_in_app, e.g. 'notepad', 'word', 'chrome'."},
            "path": {"type": "string", "description": "For open_file/read_file/write_file/delete_file, a file path."},
            "query": {"type": "string", "description": "For search_files or web_search, the search term."},
            "root": {"type": "string", "description": "For search_files, an optional folder to search within."},
            "content": {"type": "string", "description": "For write_file, the text to save to a file. For type_in_app, the full text to type directly into the app (write the whole thing out - don't summarize)."},
            "src": {"type": "string", "description": "For move_file, the source path."},
            "dst": {"type": "string", "description": "For move_file, the destination path."},
            "level": {"type": "integer", "description": "For set_volume, a number 0-100."},
            "url": {"type": "string", "description": "For open_url, the website address."},
            "mode": {"type": "string", "description": "For set_mode, either 'serious' or 'casual'."},
            "speak_response": {
                "type": "string",
                "description": "A short, in-character reply to say back to the user confirming what you're doing.",
            },
        },
        "required": ["intent", "speak_response"],
    },
}

# Which of the flat fields above actually belong to each intent's params dict.
INTENT_FIELDS = {
    "open_app": ["app_name"],
    "open_file": ["path"],
    "search_files": ["query", "root"],
    "read_file": ["path"],
    "write_file": ["path", "content"],
    "type_in_app": ["app_name", "content"],
    "screenshot": [],
    "delete_file": ["path"],
    "move_file": ["src", "dst"],
    "lock_screen": [],
    "shutdown": [],
    "close_app": [],
    "set_volume": ["level"],
    "open_url": ["url"],
    "web_search": ["query"],
    "set_mode": ["mode"],
    "chat": [],
}


def _to_python(value):
    """Recursively converts Gemini's protobuf Struct/MapComposite objects into
    plain Python dicts/lists so the rest of the app can use normal .get() calls."""
    if hasattr(value, "items"):
        return {k: _to_python(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_python(v) for v in value]
    return value


def get_model(mode: str):
    global _configured
    genai = _get_genai()

    if not config.GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey, "
            'then run: setx GOOGLE_API_KEY "your-key" and restart your terminal.'
        )
    if not _configured:
        genai.configure(api_key=config.GOOGLE_API_KEY)
        _configured = True

    system = get_personality_prompt(mode) + (
        "\n\nYou MUST call the route_command function exactly once for every user message, "
        "including plain conversation (use intent='chat' for that, with your reply in "
        "speak_response and params as an empty object)."
        "\n\nIf the user asks you to write/type something INTO an app that's visibly open or "
        "about to be opened (e.g. 'write a paragraph about X in notepad', 'type this in word'), "
        "use intent='type_in_app' with app_name set and the FULL requested text in content - "
        "do not summarize or shorten it. Only use intent='write_file' when the user explicitly "
        "asks to save/create a file, and only ever use paths inside the user's Desktop, "
        "Documents, or Downloads folders."
        "\n\nOnly use intent='set_mode' when the user explicitly asks to switch modes/tone "
        "(mentions the words 'serious' or 'casual' themselves) - never infer a mode switch "
        "from the general tone of their message."
        "\n\nIf the user says something like 'open youtube and search for X' or 'open "
        "[site] and look up X', treat that as ONE action: use intent='open_url' with the "
        "site's actual search URL (e.g. https://www.youtube.com/results?search_query=X), "
        "not two separate steps."
        "\n\nIf the user asks for a screenshot ('take a screenshot', 'capture my screen', "
        "'grab a screenshot'), use intent='screenshot' - this IS supported, don't claim you "
        "can't do it."
        "\n\nIMPORTANT distinction: use intent='close_app' ONLY when the message explicitly "
        "references YOU/Jarvis/the app itself alongside a shutdown/close/quit/exit word - e.g. "
        "'shut yourself down', 'close yourself', 'exit jarvis', 'quit the app', 'jarvis shutdown', "
        "'turn yourself off'. This only closes the Jarvis program itself, nothing else.\n"
        "Use intent='shutdown' for everything else that means powering off - including a BARE "
        "'shut down'/'turn it off'/'power off' with no self-reference at all. Plain 'shut down' "
        "on its own ALWAYS means the computer, never Jarvis itself - do not guess otherwise. "
        "This is also the safer default if ever unsure, since 'shutdown' is gated behind a "
        "confirmation prompt before anything happens, while 'close_app' is not."
    )

    memory_context = memory.build_context_block()
    if memory_context:
        # Appended last, after all the behavioral rules above, so it reads as
        # background context rather than instructions to follow.
        system += "\n\n" + memory_context

    return genai.GenerativeModel(
        model_name=config.MODEL,
        system_instruction=system,
        tools=[{"function_declarations": [ROUTE_FUNCTION]}],
        tool_config={"function_calling_config": {"mode": "ANY", "allowed_function_names": ["route_command"]}},
    )


def parse_command(user_text: str, mode: str) -> dict:
    """Returns a dict like {'intent': 'open_app', 'params': {...}, 'speak_response': '...'}"""
    model = get_model(mode)

    # 10s was too tight - forced function-calling adds latency on top of the
    # normal round-trip, and Gemini occasionally responds slowly under load.
    # That combination is what was surfacing as "504 Deadline expired before
    # operation could complete" on basically every other command.
    TIMEOUT_SECONDS = 30
    MAX_ATTEMPTS = 3

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.time()
        try:
            response = model.generate_content(user_text, request_options={"timeout": TIMEOUT_SECONDS})
            elapsed = time.time() - start
            print(f"[nlu] Gemini call took {elapsed:.2f}s (attempt {attempt})")
            break
        except Exception as e:
            elapsed = time.time() - start
            last_error = e
            err_name = type(e).__name__
            # DeadlineExceeded / ResourceExhausted / ServiceUnavailable are
            # transient - Google's own infra timing out or throttling, not a
            # problem with the request itself - so a short retry is worth it.
            # Anything else (bad API key, invalid request) won't fix itself
            # on retry, so fail fast instead of stalling 3x as long.
            transient = err_name in ("DeadlineExceeded", "ResourceExhausted", "ServiceUnavailable", "InternalServerError")
            print(f"[nlu] Gemini call FAILED after {elapsed:.2f}s (attempt {attempt}/{MAX_ATTEMPTS}, {err_name}): {e}")
            if not transient or attempt == MAX_ATTEMPTS:
                raise
            time.sleep(1.5 * attempt)  # brief backoff before retrying
    else:
        raise last_error

    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "route_command":
            args = _to_python(part.function_call.args)
            intent = args.get("intent", "chat")
            speak_response = args.get("speak_response", "")
            relevant_keys = INTENT_FIELDS.get(intent, [])
            params = {k: args[k] for k in relevant_keys if args.get(k) not in (None, "")}
            return {"intent": intent, "params": params, "speak_response": speak_response}

    # Fallback if the model somehow doesn't call the function
    return {"intent": "chat", "params": {}, "speak_response": "Sorry, I didn't catch that."}