#!/usr/bin/env python3
"""Photo sorter. Shows one photo at a time; tap Litten / Shinx / neither / both
and the file is moved into a folder. No installs needed (standard library only).

Usage:  python3 label.py /path/to/album/folder
Result: /path/to/album/folder_sorted/{Litten,Shinx,neither,both}/

The page itself (ui/label.html, label.css, label.js) and the sorting logic
(sorter_core.py) are shared with the /label page on the server (app.py), so keep
this file next to the ui/ and img_src/ folders.

Mouse:  drag on the photo to select a crop. Then a label button saves ONLY the
        cropped part (as a new JPEG, upright if you rotated) into that folder,
        and the original goes to _archived/. With no crop selected, a label
        button moves the whole photo as before.
Keys:   1 Litten   2 Shinx   3 neither   4 both
        Left/Right arrows (or the rotate buttons) rotate the view (applied to
        crops, not to whole-photo moves)
        K  toggle "keep original" (the gold button): keep the photo after a crop
           so you can crop a second cat out of it
        H  show/hide the History panel (a read-only log of this session's actions,
           kept in memory until the script stops)
        Space  done with this photo: move it to _archived/ without labelling
        Esc  clear crop selection      U or Z  undo last action
Stop with Ctrl+C any time; run it again later and it resumes where you left off
(handled photos are no longer in the source folder).
"""
import hashlib
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from sorter_core import ARCHIVE, Sorter, asset_file, ui_file

PORT = 8765
LABELS = ["Litten", "Shinx", "neither", "both"]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}

if len(sys.argv) != 2 or not Path(sys.argv[1]).expanduser().is_dir():
    sys.exit("Usage: python3 label.py /path/to/album/folder")

SRC = Path(sys.argv[1]).expanduser().resolve()
OUT = SRC.parent / f"{SRC.name}_sorted"
TMP = Path(tempfile.mkdtemp(prefix="label_app_"))


def pending():
    items = []
    for p in SRC.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS and not p.name.startswith("."):
            items.append(p.relative_to(SRC).as_posix())
    return sorted(items)


def safe(rel):
    p = (SRC / rel).resolve()
    if SRC not in p.parents or not p.is_file():
        raise FileNotFoundError(rel)
    return p


S = Sorter(
    labels=lambda: LABELS,
    pending=pending,
    resolve=safe,
    dest_dir=lambda label: OUT / label,
    archive_dir=lambda: OUT / ARCHIVE,
    title="Cat sorter",
)


def displayable(path: Path) -> Path:
    """Browsers other than Safari can't show HEIC; convert with macOS's sips."""
    if path.suffix.lower() not in {".heic", ".heif"}:
        return path
    cached = TMP / (hashlib.md5(str(path).encode()).hexdigest() + ".jpg")
    if not cached.exists():
        subprocess.run(
            ["sips", "-s", "format", "jpeg", str(path), "--out", str(cached)],
            capture_output=True,
        )
    return cached if cached.exists() else path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype="application/json", code=200, cache="no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj).encode(), code=code)

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/":
            self._send(ui_file("label.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/config":
            self._json(S.config())
        elif path == "/api/state":
            self._json(S.state())
        elif path == "/api/log":
            try:
                since = int(parse_qs(url.query).get("since", ["0"])[0])
            except ValueError:
                since = 0
            self._json(S.log_since(since))
        elif path.startswith("/img/"):
            try:
                f = displayable(S.file_path(unquote(path[5:])))
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                self._send(f.read_bytes(), ctype, cache="private, max-age=600")
            except Exception:
                self._send(b"not found", "text/plain", 404)
        elif path.startswith("/ui/") and ui_file(path[4:]):
            f = ui_file(path[4:])
            ctype = mimetypes.guess_type(f.name)[0] or "text/plain"
            self._send(f.read_bytes(), f"{ctype}; charset=utf-8")
        elif path.startswith("/asset/") and asset_file(path[7:]):
            self._send(asset_file(path[7:]).read_bytes(), "image/png", cache="private, max-age=600")
        else:
            self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        url = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        code, body = S.handle_post(url.path.removeprefix("/api/"), parse_qs(url.query), raw)
        self._json(body, code)


if __name__ == "__main__":
    if not ui_file("label.html"):
        sys.exit("Can't find ui/label.html next to label.py. Run it from the cat-id folder.")
    n = len(pending())
    print(f"{n} photos to sort in {SRC}")
    print(f"Sorted photos go to {OUT}")
    print(f"Open http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
