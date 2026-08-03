import os
import threading
import time

import config
from skills import file_ops, app_launcher, system_control
import typer_tool

DESTRUCTIVE_INTENTS = {"delete_file", "move_file", "shutdown", "restart", "write_file"}


def describe_action(intent: str, params: dict) -> str:
    if intent == "delete_file":
        return f"delete '{params.get('path')}' (sends to Recycle Bin)"
    if intent == "move_file":
        return f"move '{params.get('src')}' to '{params.get('dst')}'"
    if intent == "shutdown":
        return "shut down this computer"
    if intent == "restart":
        return "restart this computer"
    if intent == "write_file":
        return f"overwrite/create '{params.get('path')}'"
    return intent


def _type_in_app(app_name: str, content: str) -> str:
    opened = ""
    if app_name:
        opened = app_launcher.open_app(app_name)
    typer_tool.type_into_active_window(content)
    return f"{opened} Typed it in." if opened else "Typed it in."


def _take_screenshot() -> str:
    path = typer_tool.take_screenshot()
    return f"Screenshot saved to {path}"


def _close_app() -> str:
    """Closes Jarvis itself - NOT the computer. Works the same whether this
    process is main.py, server.py, or app.py (the desktop window), since
    os._exit() just ends whatever Python process called it. The exit is
    fired from a background thread after a short delay so the reply below
    actually makes it back to the terminal/browser before the process dies -
    calling os._exit() immediately would kill the process mid-response."""
    def _exit_soon():
        time.sleep(0.6)
        os._exit(0)
    threading.Thread(target=_exit_soon, daemon=True).start()
    return "Shutting myself down. See you next time."


def execute(intent: str, params: dict, confirmed: bool = False):
    """
    Returns (result_text, needs_confirmation).
    If needs_confirmation is True, the caller should ask the user to confirm,
    then call execute() again with confirmed=True and the same params.
    """
    if intent in DESTRUCTIVE_INTENTS and config.CONFIRM_DESTRUCTIVE_ACTIONS and not confirmed:
        return f"Confirm: {describe_action(intent, params)}?", True

    handlers = {
        "open_app": lambda: app_launcher.open_app(params.get("app_name", "")),
        "open_file": lambda: file_ops.open_file(params.get("path", "")),
        "search_files": lambda: file_ops.search_files(params.get("query", ""), params.get("root")),
        "read_file": lambda: file_ops.read_file(params.get("path", "")),
        "write_file": lambda: file_ops.write_file(params.get("path", ""), params.get("content", "")),
        "delete_file": lambda: file_ops.delete_file(params.get("path", "")),
        "move_file": lambda: file_ops.move_file(params.get("src", ""), params.get("dst", "")),
        "type_in_app": lambda: _type_in_app(params.get("app_name", ""), params.get("content", "")),
        "screenshot": lambda: _take_screenshot(),
        "lock_screen": lambda: system_control.lock_screen(),
        "shutdown": lambda: system_control.shutdown(confirmed=True),
        "close_app": lambda: _close_app(),
        "restart": lambda: system_control.restart(confirmed=True),
        "set_volume": lambda: system_control.set_volume(int(params.get("level", 50))),
        "open_url": lambda: system_control.open_url(params.get("url", "")),
        "web_search": lambda: system_control.web_search(params.get("query", "")),
    }

    handler = handlers.get(intent)
    if handler is None:
        return f"I don't have a handler for '{intent}' yet.", False

    return handler(), False