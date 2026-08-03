"""
Jarvis - real-time voice mode
Run with: python voice_live.py

This replaces the old STT -> Gemini(text) -> TTS round-trip (main.py) with a
single streaming audio session via the Gemini Live API: you talk, Jarvis
hears and replies in real time, no separate transcribe/synthesize steps.
This is the actual fix for the "why does it take so long" latency problem -
not a tuning tweak, a different architecture.

Every existing ability (open_app, file ops, web search, close_app vs
shutdown, etc.) is reused as-is through executor.py/config.py - nothing
about how actions execute has changed, only how you talk to Jarvis.

New in this file: screen/webcam vision, background topic monitoring, and
proactive check-ins (Jarvis can speak up unprompted after a period of quiet,
same idea as Mark L's "Proactive 2.0", tuned down to a 20-minute cooldown).

Requires: pip install google-genai sounddevice numpy mss pillow opencv-python duckduckgo-search
"""

import asyncio
import os
import sys
import time
import traceback

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

import config
import executor
import memory
import monitor
import proactive
import vision
from personality import get_personality_prompt

SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

# Every intent executor.py already knows how to run, exposed as individual
# Live API tools instead of one forced "route_command" call - with the Live
# API, plain conversation just happens naturally and doesn't need a tool at
# all, so only real actions are declared here.
TOOL_DECLARATIONS = [
    {"name": "open_app", "description": "Opens a desktop application by name (e.g. notepad, chrome, word).",
     "parameters": {"type": "OBJECT", "properties": {"app_name": {"type": "STRING"}}, "required": ["app_name"]}},
    {"name": "open_file", "description": "Opens a file with its default application.",
     "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING"}}, "required": ["path"]}},
    {"name": "search_files", "description": "Searches for files by name inside the user's allowed folders.",
     "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}, "root": {"type": "STRING"}}, "required": ["query"]}},
    {"name": "read_file", "description": "Reads and returns the text content of a file.",
     "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Saves text content to a file (Desktop/Documents/Downloads only).",
     "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING"}, "content": {"type": "STRING"}}, "required": ["path", "content"]}},
    {"name": "delete_file", "description": "Deletes a file (sends to Recycle Bin). Destructive - will ask for confirmation first.",
     "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING"}}, "required": ["path"]}},
    {"name": "move_file", "description": "Moves a file from one path to another. Destructive - will ask for confirmation first.",
     "parameters": {"type": "OBJECT", "properties": {"src": {"type": "STRING"}, "dst": {"type": "STRING"}}, "required": ["src", "dst"]}},
    {"name": "type_in_app", "description": "Opens (if needed) and types text directly into an application window.",
     "parameters": {"type": "OBJECT", "properties": {"app_name": {"type": "STRING"}, "content": {"type": "STRING"}}, "required": ["content"]}},
    {"name": "screenshot", "description": "Takes a screenshot and saves it to disk.", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "lock_screen", "description": "Locks the computer.", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "shutdown", "description": "Shuts down the COMPUTER (not Jarvis). Destructive - will ask for confirmation first.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "close_app", "description": "Closes Jarvis ITSELF, not the computer. Only use when the user explicitly "
                                          "addresses Jarvis/itself (e.g. 'shut yourself down', 'close yourself', "
                                          "'exit jarvis'). A bare 'shut down' with no self-reference means 'shutdown' instead.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "set_volume", "description": "Sets system volume, 0-100.",
     "parameters": {"type": "OBJECT", "properties": {"level": {"type": "INTEGER"}}, "required": ["level"]}},
    {"name": "open_url", "description": "Opens a website, or a specific site's search results URL (build the full URL yourself).",
     "parameters": {"type": "OBJECT", "properties": {"url": {"type": "STRING"}}, "required": ["url"]}},
    {"name": "web_search", "description": "Searches the web for a query and opens the results.",
     "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING"}}, "required": ["query"]}},
    {"name": "vision_capture", "description": "Looks at the user's screen or webcam right now. Immediately say a short "
                                               "natural filler ('Looking at your screen now...') - the actual image "
                                               "arrives in the next message, don't describe or guess content yet.",
     "parameters": {"type": "OBJECT", "properties": {"angle": {"type": "STRING", "enum": ["screen", "camera"]}}, "required": ["angle"]}},
    {"name": "manage_monitor", "description": "Adds, removes, or lists background-monitored topics (daily headline checks).",
     "parameters": {"type": "OBJECT", "properties": {
         "action": {"type": "STRING", "enum": ["add", "remove", "list"]},
         "topic": {"type": "STRING"},
     }, "required": ["action"]}},
    {"name": "confirm_pending_action", "description": "Call this ONLY when the user just verbally confirmed "
                                                       "(yes/confirm/go ahead) a destructive action Jarvis just asked "
                                                       "them to confirm.", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "cancel_pending_action", "description": "Call this when the user declines a confirmation Jarvis just asked for.",
     "parameters": {"type": "OBJECT", "properties": {}}},
]

# Intents handled entirely by the existing executor.py - no special-casing needed.
_PASSTHROUGH_INTENTS = {
    "open_app", "open_file", "search_files", "read_file", "write_file",
    "delete_file", "move_file", "type_in_app", "screenshot", "lock_screen",
    "shutdown", "close_app", "set_volume", "open_url", "web_search",
}


class JarvisVoice:
    def __init__(self):
        if not config.GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey, "
                'then run: setx GOOGLE_API_KEY "your-key" and restart your terminal.'
            )
        self.client = genai.Client(api_key=config.GOOGLE_API_KEY)
        self.session = None
        self.out_queue = asyncio.Queue()
        self._pending_action = None       # {"intent": ..., "params": ...} awaiting yes/no
        self._pending_image = None        # (bytes, mime_type) waiting to be sent as the next turn
        self._last_user_transcript = ""
        self._last_jarvis_transcript = ""

    def _build_config(self) -> "types.LiveConnectConfig":
        sys_prompt = get_personality_prompt(config.MODE)
        mem_context = memory.build_context_block()
        parts = [sys_prompt]
        if mem_context:
            parts.append(mem_context)
        parts.append(
            "You are speaking in real time over voice. Keep replies conversational and "
            "not too long unless the user asks for detail. Use the tools available to you "
            "for anything actionable - don't just describe what you'd do, actually call the tool."
        )

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
        )

    # ---------------- tool execution ----------------

    async def _run_tool(self, name: str, args: dict) -> str:
        loop = asyncio.get_event_loop()

        if name == "confirm_pending_action":
            if not self._pending_action:
                return "There's nothing waiting on confirmation."
            intent, params, user_text = (self._pending_action["intent"],
                                          self._pending_action["params"],
                                          self._pending_action["text"])
            self._pending_action = None
            result, _ = await loop.run_in_executor(None, lambda: executor.execute(intent, params, confirmed=True))
            memory.remember_turn(user_text, result)
            return result

        if name == "cancel_pending_action":
            if not self._pending_action:
                return "There's nothing waiting on confirmation."
            memory.remember_turn(self._pending_action["text"], "Cancelled.")
            self._pending_action = None
            return "Cancelled."

        if name == "vision_capture":
            angle = args.get("angle", "screen")
            try:
                if angle == "camera":
                    img_bytes = await loop.run_in_executor(None, vision.capture_camera)
                else:
                    img_bytes = await loop.run_in_executor(None, vision.capture_screen)
                self._pending_image = (img_bytes, "image/jpeg")
                return f"[{angle} captured, arriving next message]"
            except Exception as e:
                return f"Couldn't access the {angle}: {e}"

        if name == "manage_monitor":
            action = args.get("action", "")
            topic = args.get("topic", "")
            if action == "add":
                return monitor.add_monitor(topic)
            if action == "remove":
                return monitor.remove_monitor(topic)
            if action == "list":
                topics = monitor.list_monitors()
                return ("Monitoring: " + ", ".join(topics)) if topics else "Nothing being monitored right now."
            return "Specify add, remove, or list."

        if name in _PASSTHROUGH_INTENTS:
            try:
                result, needs_confirmation = await loop.run_in_executor(
                    None, lambda: executor.execute(name, args)
                )
            except Exception as e:
                traceback.print_exc()
                return f"That action failed: {e}"

            if needs_confirmation:
                self._pending_action = {"intent": name, "params": args, "text": self._last_user_transcript}
                return result  # the "Confirm: ...?" question itself

            memory.remember_turn(self._last_user_transcript, result)
            return result

        return f"Unknown tool: {name}"

    # ---------------- audio I/O ----------------

    async def _listen_audio(self):
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            asyncio.run_coroutine_threadsafe(
                self.out_queue.put({"data": indata.copy().tobytes(), "mime_type": "audio/pcm"}),
                loop,
            )

        with sd.InputStream(
            samplerate=SEND_SAMPLE_RATE, channels=1, dtype="int16",
            blocksize=CHUNK_SIZE, callback=callback,
        ):
            while True:
                await asyncio.sleep(1)

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _receive_and_play(self):
        stream = sd.OutputStream(samplerate=RECEIVE_SAMPLE_RATE, channels=1, dtype="int16")
        stream.start()
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    if data := response.data:
                        audio = np.frombuffer(data, dtype=np.int16)
                        stream.write(audio)

                    if response.server_content:
                        sc = response.server_content
                        if sc.input_transcription and sc.input_transcription.text:
                            self._last_user_transcript = sc.input_transcription.text
                            print(f"[you] {self._last_user_transcript}")
                        if sc.output_transcription and sc.output_transcription.text:
                            self._last_jarvis_transcript += sc.output_transcription.text

                        if sc.turn_complete:
                            if self._last_jarvis_transcript:
                                print(f"[jarvis] {self._last_jarvis_transcript}")
                            self._last_jarvis_transcript = ""

                            # If a tool queued an image, send it now as the next turn.
                            if self._pending_image:
                                img_bytes, mime_type = self._pending_image
                                self._pending_image = None
                                await self.session.send_client_content(
                                    turns={"parts": [
                                        {"inline_data": {"mime_type": mime_type, "data": img_bytes}},
                                        {"text": "Here's what you just captured - describe/answer naturally."},
                                    ]},
                                    turn_complete=True,
                                )

                    if response.tool_call:
                        for fc in response.tool_call.function_calls:
                            result = await self._run_tool(fc.name, dict(fc.args or {}))
                            await self.session.send_tool_response(
                                function_responses=[
                                    types.FunctionResponse(id=fc.id, name=fc.name, response={"result": result})
                                ]
                            )
        finally:
            stream.stop()
            stream.close()

    async def _proactive_loop(self):
        """Checks every minute whether Jarvis has something worth saying
        unprompted (monitored-topic update, project follow-up, etc.)."""
        while True:
            await asyncio.sleep(60)
            checkin = proactive.maybe_check_in()
            if not checkin or not self.session:
                continue
            prompt = (
                f"[PROACTIVE CHECK-IN - {checkin['angle']}] Without waiting to be asked, say "
                f"something brief and natural based on this: {checkin['context']}"
            )
            try:
                await self.session.send_client_content(
                    turns={"parts": [{"text": prompt}]}, turn_complete=True,
                )
            except Exception:
                pass  # session might be mid-turn or closing - just skip this cycle

    async def run(self):
        model = getattr(config, "VOICE_MODEL", "gemini-3.1-flash-live-preview")
        live_config = self._build_config()

        async with self.client.aio.live.connect(model=model, config=live_config) as session:
            self.session = session
            print("=== Jarvis (real-time voice) ===")
            print("Speak naturally. Press Ctrl+C to quit.")

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._listen_audio())
                tg.create_task(self._send_realtime())
                tg.create_task(self._receive_and_play())
                tg.create_task(self._proactive_loop())


def main():
    try:
        asyncio.run(JarvisVoice().run())
    except KeyboardInterrupt:
        print("\nJarvis: Goodbye.")
        sys.exit(0)
    except RuntimeError as e:
        print(f"Jarvis: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
