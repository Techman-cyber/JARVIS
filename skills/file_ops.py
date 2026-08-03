import os
import shutil
import fnmatch
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _is_allowed(path: str) -> bool:
    """Only allow operating inside configured root folders, to stop a misparsed
    command from touching system files or anything outside your normal folders."""
    abs_path = os.path.abspath(os.path.expanduser(path))
    return any(
        abs_path.startswith(os.path.abspath(root)) for root in config.ALLOWED_ROOTS
    )


def open_file(path: str) -> str:
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"I can't find {path}."
    if not _is_allowed(path):
        return f"That's outside my allowed folders, so I won't open it. Add its folder to ALLOWED_ROOTS in config.py if you trust it."
    os.startfile(path)  # Windows-only
    return f"Opened {os.path.basename(path)}."


def search_files(query: str, root: str = None) -> str:
    roots = [root] if root else config.ALLOWED_ROOTS
    matches = []
    for r in roots:
        r = os.path.expanduser(r)
        if not os.path.isdir(r):
            continue
        for dirpath, _, filenames in os.walk(r):
            for name in filenames:
                if fnmatch.fnmatch(name.lower(), f"*{query.lower()}*"):
                    matches.append(os.path.join(dirpath, name))
            if len(matches) >= 20:
                break
    if not matches:
        return f"No files matching '{query}' found."
    listing = "\n".join(matches[:20])
    return f"Found {len(matches)} match(es):\n{listing}"


def read_file(path: str) -> str:
    path = os.path.expanduser(path)
    if not _is_allowed(path):
        return "That's outside my allowed folders."
    if not os.path.exists(path):
        return f"I can't find {path}."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content[:3000] + ("...\n[truncated]" if len(content) > 3000 else "")
    except Exception as e:
        return f"Couldn't read that file: {e}"


def write_file(path: str, content: str) -> str:
    path = os.path.expanduser(path)
    if not _is_allowed(path):
        return "That's outside my allowed folders."
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Wrote {len(content)} characters to {os.path.basename(path)}."


def delete_file(path: str) -> str:
    """Sends to Recycle Bin rather than permanently deleting, so mistakes are recoverable."""
    path = os.path.expanduser(path)
    if not _is_allowed(path):
        return "That's outside my allowed folders, so I won't delete it."
    if not os.path.exists(path):
        return f"I can't find {path}."
    try:
        from send2trash import send2trash
        send2trash(path)
        return f"Moved {os.path.basename(path)} to the Recycle Bin."
    except ImportError:
        return "The send2trash package isn't installed. Run: pip install send2trash"


def move_file(src: str, dst: str) -> str:
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    if not _is_allowed(src) or not _is_allowed(dst):
        return "Source or destination is outside my allowed folders."
    if not os.path.exists(src):
        return f"I can't find {src}."
    shutil.move(src, dst)
    return f"Moved {os.path.basename(src)} to {dst}."
