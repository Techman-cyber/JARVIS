"""
Screen + webcam capture for Jarvis's vision tool. Returns raw JPEG bytes
ready to hand straight to the Gemini Live session as an image part.
"""

import io

import mss
from PIL import Image

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False


def capture_screen(max_width: int = 1280) -> bytes:
    """Grabs the primary monitor, downscales it (full-res screenshots are
    unnecessarily large for the model and slower to upload), returns JPEG bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # [0] is "all monitors combined"; [1] is the primary
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def capture_camera(cam_index: int = 0) -> bytes:
    """Grabs a single frame from the webcam, returns JPEG bytes. Raises
    RuntimeError with a clear message if no camera is available - callers
    should catch this and report it back through Jarvis's normal error path
    rather than crashing the whole session."""
    if not _HAS_CV2:
        raise RuntimeError("opencv-python isn't installed - run: pip install opencv-python")

    cap = cv2.VideoCapture(cam_index)
    try:
        if not cap.isOpened():
            raise RuntimeError("Couldn't open the webcam - check it's not in use by another app.")
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("Webcam opened but didn't return a frame.")
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            raise RuntimeError("Failed to encode the webcam frame.")
        return buf.tobytes()
    finally:
        cap.release()


if __name__ == "__main__":
    # Quick manual check: python vision.py
    data = capture_screen()
    with open("test_screen.jpg", "wb") as f:
        f.write(data)
    print(f"Saved test_screen.jpg ({len(data):,} bytes)")
