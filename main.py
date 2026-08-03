"""
Jarvis - personal assistant
Run with: python main.py

Meta commands (type these directly, no need to route through Claude):
  /voice     switch to voice input
  /text      switch to text input
  /serious   switch personality to serious mode
  /casual    switch personality to casual mode
  /mute      stop speaking replies out loud
  /unmute    resume speaking replies
  /forget    wipe Jarvis's persistent memory (everything it remembers about you)
  /exit      quit
"""

import sys
import webbrowser
import config
import nlu
import executor
import memory
import tts
import stt
import wake_listener
from personality import build_greeting

state = {"input_mode": "text", "speak": True}


def say(text: str):
    print(f"Jarvis: {text}")
    if state["speak"]:
        try:
            tts.speak(text)
        except Exception:
            pass  # don't let a broken audio driver kill the assistant


def get_input() -> str:
    if state["input_mode"] == "voice":
        wake_listener.pause()
        text = stt.listen()
        wake_listener.resume()
        if text:
            print(f"You said: {text}")
        return text
    return input("You: ").strip()


def handle_meta(cmd: str) -> bool:
    cmd = cmd.lower()
    if cmd == "/voice":
        state["input_mode"] = "voice"
        say("Switched to voice input.")
    elif cmd == "/text":
        state["input_mode"] = "text"
        say("Switched to text input.")
    elif cmd == "/serious":
        config.MODE = "serious"
        say("Serious mode engaged.")
    elif cmd == "/casual":
        config.MODE = "casual"
        say("Back to casual mode.")
    elif cmd == "/mute":
        state["speak"] = False
        print("Jarvis: Muted.")
    elif cmd == "/unmute":
        state["speak"] = True
        say("Unmuted.")
    elif cmd == "/forget":
        memory.forget_everything()
        say("Done. I've wiped everything I remembered about you.")
    elif cmd == "/exit":
        say("Goodbye.")
        sys.exit(0)
    else:
        return False
    return True


def main():
    print("=== Jarvis ===")
    print(__doc__)
    wake_listener.start()
    say(build_greeting(config.MODE))

    while True:
        user_text = get_input()
        if not user_text:
            continue
        if user_text.startswith("/"):
            handle_meta(user_text)
            continue

        # Instant shortcut - bypasses the AI model entirely so it's immediate.
        if "turn on hand" in user_text.lower():
            say("Activating hand tracking interface.")
            webbrowser.open("http://localhost:8000/gesture_control.html")
            print("[jarvis] Note: server.py must be running for the gesture page to work.")
            continue

        try:
            result = nlu.parse_command(user_text, config.MODE)
        except RuntimeError as e:
            say(str(e))
            continue
        except Exception as e:
            say(f"I hit an error talking to Gemini: {e}")
            continue

        intent = result.get("intent", "chat")
        params = result.get("params", {}) or {}
        reply = result.get("speak_response", "")

        print(f"[jarvis] parsed intent={intent} params={params}")  # visibility while debugging

        if intent == "chat":
            say(reply)
            memory.remember_turn(user_text, reply)
            continue

        if intent == "set_mode":
            lowered = user_text.lower()
            if "serious" not in lowered and "casual" not in lowered:
                print(f"[jarvis] ignoring set_mode - user text didn't actually say serious/casual")
                say(reply)
                memory.remember_turn(user_text, reply)
                continue
            new_mode = params.get("mode", "casual")
            config.MODE = "serious" if "serious" in new_mode.lower() else "casual"
            final_reply = reply or f"Switched to {config.MODE} mode."
            say(final_reply)
            memory.remember_turn(user_text, final_reply)
            continue

        # Announce what we're about to do
        if reply:
            say(reply)

        action_result, needs_confirmation = executor.execute(intent, params)

        if needs_confirmation:
            say(action_result)
            confirm_text = get_input().strip().lower()
            if confirm_text in ("yes", "y", "confirm", "do it"):
                action_result, _ = executor.execute(intent, params, confirmed=True)
                say(action_result)
            else:
                action_result = "Cancelled."
                say(action_result)
        else:
            say(action_result)

        # Log the whole exchange (the announced intent + the actual outcome)
        # as one turn, so memory reads naturally rather than as two fragments.
        full_reply = f"{reply} {action_result}".strip() if reply else action_result
        memory.remember_turn(user_text, full_reply)


if __name__ == "__main__":
    main()