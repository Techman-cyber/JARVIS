"""
Bridge server - lets interface/index.html talk to the Python Jarvis backend
(nlu.py + executor.py) over HTTP, and also serves the interface itself.

Run this INSTEAD of main.py when you want to use the visual interface:
    python server.py

Then go to http://localhost:8000 in your browser. Keep this terminal window
running. (Serving the page from http://localhost instead of a raw file is
required for the camera/microphone features to work - browsers block those
on file:// pages.)
"""

import os
import re
import sys
import tempfile
import asyncio
import xml.etree.ElementTree as ET
import requests
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

import config
import nlu
import executor
import memory
from skills import app_launcher
from personality import build_greeting

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import psutil
except ImportError:
    psutil = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INTERFACE_DIR = os.path.join(BASE_DIR, "interface")

app = Flask(__name__)
CORS(app)

# Holds the last action that's waiting on a yes/no confirmation.
# Simple single-user, single-pending-action state - fine for a personal assistant.
pending_action = None


@app.route("/")
def index():
    return send_from_directory(INTERFACE_DIR, "index.html")


# Gesture -> action mapping. Bypasses the LLM entirely (nlu.py) so gestures
# feel instant instead of waiting on a Gemini round-trip. Edit this to remap
# gestures to whatever you want.
gesture_state = {"volume": 50}


def _handle_gesture(gesture: str):
    if gesture == "pinch":
        return executor.execute("open_app", {"app_name": "notepad"})

    if gesture == "swipe_right":
        gesture_state["volume"] = min(100, gesture_state["volume"] + 10)
        return executor.execute("set_volume", {"level": gesture_state["volume"]})

    if gesture == "swipe_left":
        gesture_state["volume"] = max(0, gesture_state["volume"] - 10)
        return executor.execute("set_volume", {"level": gesture_state["volume"]})

    if gesture == "zoom_in":
        import typer_tool
        typer_tool.press_hotkey("ctrl", "+")
        return "Zoomed in.", False

    if gesture == "zoom_out":
        import typer_tool
        typer_tool.press_hotkey("ctrl", "-")
        return "Zoomed out.", False

    if gesture == "turn_around":
        import typer_tool
        typer_tool.press_hotkey("alt", "tab")
        return "Switched windows.", False

    return f"Unknown gesture '{gesture}'.", False


@app.route("/speak", methods=["POST"])
def speak_route():
    """
    Generates speech audio for the web interface using edge-tts - free,
    no API key, deliberately NOT ElevenLabs so the browser voice doesn't
    burn ElevenLabs credits on every reply. Returns raw MP3 bytes.
    """
    if edge_tts is None:
        return jsonify({"error": "edge-tts not installed - run: pip install edge-tts"}), 500

    data = request.get_json(force=True)
    text = (data or {}).get("text", "").strip()
    if not text:
        return "", 204

    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        async def _generate():
            communicate = edge_tts.Communicate(text, config.EDGE_TTS_VOICE)
            await communicate.save(path)

        asyncio.run(_generate())

        with open(path, "rb") as f:
            audio_bytes = f.read()
        return Response(audio_bytes, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@app.route("/gesture", methods=["POST"])
def gesture():
    data = request.get_json(force=True)
    name = (data or {}).get("gesture", "").strip()
    if not name:
        return jsonify({"reply": "No gesture provided."})

    try:
        action_result, needs_confirmation = _handle_gesture(name)
    except Exception as e:
        return jsonify({"reply": f"Gesture handler error: {e}"})

    # Destructive intents aren't mapped to gestures above, but if you add one,
    # this refuses to auto-confirm it rather than silently executing.
    if needs_confirmation:
        return jsonify({"reply": f"'{name}' maps to a destructive action - "
                                  f"confirm it through voice/text instead of a gesture."})

    return jsonify({"reply": action_result})


@app.route("/command", methods=["POST"])
def command():
    global pending_action

    data = request.get_json(force=True)
    text = (data or {}).get("text", "").strip()
    if not text:
        return jsonify({"reply": "I didn't catch a command.", "needs_confirmation": False})

    # Fast path: "open <app>" is by far the most common command, and going
    # through the Gemini model for it adds a full network round-trip for no
    # real benefit when it's a plain, unambiguous match against a known app
    # name. Skip the model entirely in that case - only falls through to the
    # normal AI path if it's not a clean match.
    fast_match = re.match(r"^(?:open|launch|start)\s+(.+)$", text.strip(), re.IGNORECASE)
    if fast_match:
        app_name = fast_match.group(1).strip().lower()
        if app_name in config.APP_ALIASES:
            action_result = app_launcher.open_app(app_name)
            pending_action = None
            return jsonify({"reply": action_result, "needs_confirmation": False})

    try:
        result = nlu.parse_command(text, config.MODE)
    except RuntimeError as e:
        return jsonify({"reply": str(e), "needs_confirmation": False})
    except Exception as e:
        return jsonify({"reply": f"Error talking to Gemini: {e}", "needs_confirmation": False})

    intent = result.get("intent", "chat")
    params = result.get("params", {}) or {}
    speak_response = result.get("speak_response", "")

    print(f"[jarvis] parsed intent={intent} params={params}")  # visibility while debugging

    if intent == "chat":
        memory.remember_turn(text, speak_response)
        return jsonify({"reply": speak_response, "needs_confirmation": False})

    if intent == "set_mode":
        lowered = text.lower()
        if "serious" not in lowered and "casual" not in lowered:
            print("[jarvis] ignoring set_mode - user text didn't actually say serious/casual")
            memory.remember_turn(text, speak_response)
            return jsonify({"reply": speak_response, "needs_confirmation": False})
        new_mode = params.get("mode", "casual")
        config.MODE = "serious" if "serious" in new_mode.lower() else "casual"
        final_reply = speak_response or f"Switched to {config.MODE} mode."
        memory.remember_turn(text, final_reply)
        return jsonify({
            "reply": final_reply,
            "needs_confirmation": False,
            "mode": config.MODE,
        })

    try:
        action_result, needs_confirmation = executor.execute(intent, params)
    except Exception as e:
        # Without this, a bug inside executor.py/skills/*.py (e.g. system_control.py's
        # web_search/open_url) throws all the way up, Flask returns a raw 500, and the
        # browser just shows a generic error with no clue what actually broke.
        import traceback
        traceback.print_exc()  # full traceback still goes to the console / jarvis_log.txt
        return jsonify({"reply": f"Error running that action: {e}", "needs_confirmation": False})

    if needs_confirmation:
        # Stash the original text too, so if the user confirms, /confirm can
        # log the whole exchange (ask + outcome) as a single memory turn.
        pending_action = {"intent": intent, "params": params, "text": text}
        return jsonify({"reply": action_result, "needs_confirmation": True})

    pending_action = None
    reply = speak_response or action_result
    full_reply = f"{speak_response} {action_result}".strip() if speak_response else action_result
    memory.remember_turn(text, full_reply)
    return jsonify({"reply": f"{reply}\n{action_result}" if speak_response else action_result,
                     "needs_confirmation": False})


@app.route("/confirm", methods=["POST"])
def confirm():
    global pending_action

    data = request.get_json(force=True)
    approved = bool((data or {}).get("approved"))

    if not pending_action:
        return jsonify({"reply": "There's nothing waiting on confirmation."})

    original_text = pending_action.get("text", "")

    if not approved:
        pending_action = None
        memory.remember_turn(original_text, "Cancelled.")
        return jsonify({"reply": "Cancelled."})

    intent, params = pending_action["intent"], pending_action["params"]
    pending_action = None
    try:
        action_result, _ = executor.execute(intent, params, confirmed=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"reply": f"Error running that action: {e}"})
    memory.remember_turn(original_text, action_result)
    return jsonify({"reply": action_result})


@app.route("/api/news", methods=["GET"])
def api_news():
    """
    Key-free headline feed via Google News RSS, fetched server-side so the
    browser dashboard doesn't hit CORS issues and nobody needs to sign up
    for a news API key.

    Query params (both optional):
      gl - country code, e.g. 'US', 'GB', 'IN' (default 'US')
      hl - language, e.g. 'en-US' (default 'en-US')
    """
    country = request.args.get("gl", "US")
    lang = request.args.get("hl", "en-US")
    ceid = f"{country}:{lang.split('-')[0]}"
    url = f"https://news.google.com/rss?hl={lang}&gl={country}&ceid={ceid}"

    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        items = []
        for item in root.findall(".//item")[:10]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            items.append({"title": title, "link": link, "source": source, "pubDate": pub_date})

        return jsonify({"items": items})
    except Exception as e:
        # Don't take the whole dashboard down if the news feed hiccups.
        return jsonify({"items": [], "error": str(e)}), 200


@app.route("/api/system", methods=["GET"])
def api_system():
    """CPU / RAM / battery for the dashboard gauges. Requires psutil."""
    if psutil is None:
        return jsonify({"error": "psutil not installed - run: pip install psutil"}), 200

    data = {
        "cpu": psutil.cpu_percent(interval=0.2),
        "ram": psutil.virtual_memory().percent,
    }
    try:
        batt = psutil.sensors_battery()
        data["battery"] = batt.percent if batt else None
    except Exception:
        data["battery"] = None
    return jsonify(data)


@app.route("/greeting", methods=["GET"])
def greeting():
    """Called once by the frontend right after the page loads, so Jarvis
    opens with an actual conversational check-in (weather + how-are-you)
    instead of a static 'systems online' line every single time."""
    return jsonify({"reply": build_greeting(config.MODE)})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({"mode": config.MODE, "pending": pending_action is not None})


@app.route("/forget", methods=["POST"])
def forget():
    """Wipes everything Jarvis remembers (raw history + the long-term
    summary). Wire a button to this in interface/index.html if you want a
    one-click 'forget me' control on the dashboard."""
    memory.forget_everything()
    return jsonify({"reply": "Done. I've wiped everything I remembered about you."})


# Registered LAST on purpose. This matches any leftover path (e.g.
# /gesture_control.html) and serves it from interface/ - if it were defined
# earlier, Flask/Werkzeug can end up matching it before more specific routes
# like POST /speak, causing a 405 Method Not Allowed on those instead of
# ever reaching their real handler.
@app.route("/<path:filename>")
def serve_interface_file(filename):
    """Serves any other file sitting in interface/, e.g. gesture_control.html,
    so you can open http://localhost:8000/gesture_control.html directly."""
    return send_from_directory(INTERFACE_DIR, filename)


def _preflight_checks():
    """Catches the most common reasons this crashes before the port ever
    opens, and prints a clear message instead of a silent exit / stack trace
    that scrolls past."""
    problems = []

    if not config.GOOGLE_API_KEY:
        problems.append(
            "GOOGLE_API_KEY is not set. Run: setx GOOGLE_API_KEY \"your-key\" "
            "then open a NEW terminal and try again."
        )

    if not os.path.isdir(INTERFACE_DIR):
        problems.append(
            f"Interface folder not found at {INTERFACE_DIR}. "
            f"Make sure there's an 'interface' folder with index.html next to server.py."
        )

    if edge_tts is None:
        print("[server] Note: edge-tts not installed - the web voice (/speak) won't work "
              "until you run: pip install edge-tts")

    if problems:
        print("=" * 60)
        print("Jarvis can't start:")
        for p in problems:
            print(f"  - {p}")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    _preflight_checks()
    print("Jarvis running at http://localhost:8000 — open that address in your browser.")
    try:
        app.run(port=8000, debug=False)
    except OSError as e:
        print(f"Couldn't start on port 8000 ({e}). Something else may already be using "
              f"it - close other Jarvis windows, or change the port number in server.py "
              f"(both in app.run(port=...) here and in interface/index.html where it "
              f"calls localhost:8000).")
        sys.exit(1)