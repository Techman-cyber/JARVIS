"""
Jarvis Desktop App
Run with: python app.py

This wraps server.py in an actual native application window (using
pywebview) instead of making you open a browser tab yourself. It starts
the Flask backend in a background thread, waits until it's actually
responding, then opens a real window pointing at it.

Install the one extra dependency first:
    pip install pywebview

If you see a blank white window, the most common cause on Windows is a
missing/broken Microsoft Edge WebView2 Runtime (what pywebview uses to
render the page). Get it here (it's free, from Microsoft):
    https://developer.microsoft.com/microsoft-edge/webview2/
Look for "Evergreen Bootstrapper" and install it, then try again.

To turn this into a single double-clickable .exe (no Python window, no
console), install PyInstaller and run this from the project folder:
    pip install pyinstaller
    pyinstaller --noconsole --onefile --icon="jarvis.ico" --name Jarvis --add-data "interface;interface" app.py

The finished Jarvis.exe will be in the new 'dist' folder. You can pin that
to your taskbar or Start menu like any other app.

--- Why this version opens faster ---
Previously the native window wasn't created at all until Flask had fully
booted AND responded to a health check - so on a cold start (Python
interpreter startup + imports + Flask init + WebView2 spinning up) you'd
stare at nothing for the whole ~30s before anything appeared.

Now the window is created immediately with a small local "booting up"
splash (loaded from an in-memory data URL, no server needed), and a
background thread swaps it over to the real dashboard the moment Flask
answers. The total backend warm-up time doesn't change, but you get
instant visual feedback instead of a long silent pause, and the two
phases (window/WebView2 init and Flask startup) now happen in parallel
instead of one after another.
"""

import sys
import threading
import time
import urllib.request
import webview

import server  # this is your existing server.py - reused as-is, not duplicated

URL = "http://127.0.0.1:8000"

# Tiny inline splash screen - no network/file access required, so it shows
# the instant the native window is created, before Flask exists at all.
LOADING_HTML = """
<html>
<head><style>
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
         background:#0b0d10; color:#7fd7ff; font-family:Segoe UI, Arial, sans-serif; }
  .wrap { text-align:center; }
  .ring { width:48px; height:48px; margin:0 auto 18px; border-radius:50%;
          border:3px solid rgba(127,215,255,0.2); border-top-color:#7fd7ff;
          animation:spin 0.9s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .label { letter-spacing:2px; font-size:13px; opacity:0.8; text-transform:uppercase; }
</style></head>
<body>
  <div class="wrap">
    <div class="ring"></div>
    <div class="label">Jarvis systems booting...</div>
  </div>
</body>
</html>
"""

FAILURE_HTML = """
<html><body style="background:#0b0d10;color:#ff8080;font-family:Segoe UI,Arial,sans-serif;
padding:40px;">
<h2>Jarvis didn't start</h2>
<p>The backend server never responded. Check <code>silent_log.txt</code> /
<code>jarvis_log.txt</code> in the Jarvis folder for the real error, then close
this window and try again.</p>
</body></html>
"""


class JsApi:
    """Exposed to the page as window.pywebview.api.* (pywebview's built-in
    bridge). The front-end's F11 handler calls toggle_fullscreen() here in
    preference to the browser's own requestFullscreen() when running inside
    this desktop app, because requestFullscreen() alone just fills the
    existing embedded WebView2 window bounds rather than actually taking
    over the monitor like real OS-level fullscreen does."""

    def __init__(self, window):
        self._window = window

    def toggle_fullscreen(self):
        self._window.toggle_fullscreen()
        return True


def _log(msg: str):
    # flush=True so timestamps land in silent_log.txt / jarvis_log.txt in
    # real time instead of being buffered until process exit - important
    # since this runs fully hidden via the VBS launcher.
    print(f"[{time.time():.2f}] [app] {msg}", flush=True)


def _run_flask():
    # use_reloader=False is required - the reloader tries to spawn a second
    # process, which breaks when running inside a packaged/threaded app.
    server.app.run(port=8000, debug=False, use_reloader=False)


def _wait_for_server(timeout=25):
    """Polls the server instead of guessing with a fixed sleep - opening the
    window before Flask is actually ready is a common cause of a blank/stuck
    white screen."""
    _log("Waiting for the Jarvis server to come up...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(URL, timeout=1)
            _log(f"Server is up after {time.time() - start:.2f}s.")
            return True
        except Exception:
            time.sleep(0.2)
    _log(f"Server never responded within {timeout}s - something's wrong with server.py itself.")
    return False


def _after_gui_start(window):
    """Runs on a background thread once the WebView2/GUI loop is already
    live and the splash screen is already visible on screen. Flask was
    started in parallel before webview.start() was even called, so most of
    the warm-up has already happened concurrently with window/WebView2 init
    by the time we get here."""
    if _wait_for_server():
        window.load_url(URL)
    else:
        window.load_html(FAILURE_HTML)


def main():
    t0 = time.time()
    server._preflight_checks()

    # Start Flask warming up immediately, in parallel with window/WebView2 setup below.
    flask_thread = threading.Thread(target=_run_flask, daemon=True)
    flask_thread.start()

    # Create the window right away with the local splash - this does not
    # depend on Flask at all, so it shows as soon as WebView2 finishes its
    # own (unavoidable) init, instead of after Flask too.
    window = webview.create_window(
        "Jarvis",
        html=LOADING_HTML,
        width=1280,
        height=800,
        min_size=(900, 600),
    )
    window.expose(JsApi(window).toggle_fullscreen)
    _log(f"Window created at +{time.time() - t0:.2f}s, starting GUI loop...")

    try:
        # gui='edgechromium' forces the modern WebView2 engine explicitly on
        # Windows instead of letting pywebview guess. Passing a function as
        # the first arg makes pywebview run it on a separate thread once the
        # GUI loop (and therefore the splash screen) is already up.
        webview.start(_after_gui_start, window, gui="edgechromium", debug=False)
    except Exception as e:
        _log(f"pywebview failed to start with edgechromium: {e}")
        _log("This usually means the Microsoft Edge WebView2 Runtime isn't installed.")
        _log("Get it free from: https://developer.microsoft.com/microsoft-edge/webview2/")
        _log(f"In the meantime, you can still use Jarvis by opening {URL} in Chrome or Edge yourself.")
        sys.exit(1)


if __name__ == "__main__":
    main()