"""Shared sorting logic for label.py (Mac, album folder) and app.py (server, inbox).

Both programs show the same web page (ui/label.html + label.css + label.js) and
speak the same small HTTP API. This module is everything behind that API that
does not depend on the web framework: the action log, undo stack, label / crop /
archive moves, and the JSON the page asks for.

Each program supplies only what differs: where photos are listed from, where a
label's folder is, and where skipped photos go. See `Sorter(...)` and
`inbox_sorter(...)` below.

The API (same in both programs):
  GET  /api/config            labels, title, whether a Retrain button is shown
  GET  /api/state             photos left, next few names, count per label
  GET  /api/log?since=N       history entries after id N
  GET  /img/<name>            the photo
  GET  /ui/<file>             label.html / label.css / label.js
  GET  /asset/<file>          button artwork from img_src/
  POST /api/label             {"name", "label"}   move the whole photo
  POST /api/crop?name=&label=&keep=0|1   body = JPEG bytes
  POST /api/archive           {"name"}            done / skip
  POST /api/delete            {"name"}            server only: delete the file (undo restores it)
  POST /api/undo
  POST /api/keep?on=0|1       only records the toggle in the history

Optional, server only: every POST may carry ?user=<name> (the app's "who am I"), and label /
crop may carry an event type ("event_type" in the label body, &event_type= on crop; "none"
means no event, left out means the default for the photo). They are passed to `on_action`,
which app.py uses to update the database. label.py passes no `on_action`, so it ignores them.
"""
import json
import shutil
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI_DIR = HERE / "ui"
ASSET_DIR = HERE / "img_src"
ARCHIVE = "_archived"
BOTH = "both"
INBOX_EXTS = {".jpg", ".jpeg", ".png", ".webp"}  # same as train.py


def _plain(name: str) -> bool:
    return bool(name) and name == Path(name).name and not name.startswith(".")


def ui_file(name: str):
    """A file from ui/ (page, css, js), or None. Plain names only."""
    p = UI_DIR / name
    return p if _plain(name) and p.is_file() else None


def asset_file(name: str):
    """Button artwork from img_src/, or None. Plain .png names only."""
    p = ASSET_DIR / name
    return p if _plain(name) and name.lower().endswith(".png") and p.is_file() else None


def unique_dest(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while dest.exists():  # same filename twice, or repeat crops
        dest = folder / f"{stem}_{i}{suffix}"
        i += 1
    return dest


class Sorter:
    """
    labels()        -> list of label names, in button order
    pending()       -> sorted list of photo names still to sort
    resolve(name)   -> Path of that photo; raises FileNotFoundError if not allowed
    dest_dir(label) -> folder a photo labelled `label` is moved into
    archive_dir()   -> folder for done / skipped originals
    title, retrain  -> shown by the page
    on_action(action, info) -> optional; called after each label / crop / archive / delete /
                       undo has moved the files. A returned string is added to the History.
    """

    def __init__(self, *, labels, pending, resolve, dest_dir, archive_dir,
                 title="Cat sorter", retrain=False, delete=False, on_action=None):
        self._labels, self._pending, self._resolve = labels, pending, resolve
        self._dest_dir, self._archive_dir = dest_dir, archive_dir
        self.title, self.retrain, self.delete_ok = title, retrain, delete
        self._on_action = on_action
        self.lock = threading.RLock()
        # Undo stack: ("move", dest, orig, (title, detail)),
        #             ("crop", crop_file, archived_or_None, orig, (title, detail)) or
        #             ("delete", orig, file_bytes, (title, detail))
        self.history = []
        self.entries = []  # read-only action log for the History panel (in memory)

    # ---------- log ----------
    def log(self, kind, title, detail="", label=None):
        with self.lock:
            self.entries.append({
                "id": len(self.entries) + 1, "t": time.strftime("%H:%M:%S"),
                "kind": kind, "title": title, "detail": detail, "label": label,
            })

    def log_since(self, since):
        with self.lock:
            return {"entries": self.entries[max(since, 0):]}

    # ---------- what the page asks for ----------
    def config(self):
        return {"labels": self._labels(), "title": self.title,
                "retrain": self.retrain, "delete": self.delete_ok}

    def counts(self):
        return {l: sum(1 for p in self._dest_dir(l).iterdir() if p.is_file())
                if self._dest_dir(l).is_dir() else 0 for l in self._labels()}

    def state(self):
        with self.lock:
            items = self._pending()
            return {"remaining": len(items), "queue": items[:3], "counts": self.counts()}

    def remaining(self):
        """How many photos are still waiting to be sorted."""
        with self.lock:
            return len(self._pending())

    def file_path(self, name):
        with self.lock:
            return self._resolve(name)

    # ---------- actions ----------
    def _check(self, label):
        if label not in self._labels():
            raise ValueError("bad label")

    def _notify(self, action, info, meta):
        """Tell on_action what just happened. Never fails the action: the files have
        already moved, so a problem here is only logged in the History."""
        if self._on_action is None:
            return
        try:
            msg = self._on_action(action, {**info, **(meta or {})})
            if msg:
                self.log("db", msg)
        except Exception as e:
            self.log("error", "Database not updated", f"{type(e).__name__}: {e}")

    def _move_to(self, rel, folder, kind, title, detail=None, label=None):
        src = self._resolve(rel)
        dest = unique_dest(folder, src.name)
        shutil.move(str(src), str(dest))  # works across Docker mounts, unlike Path.rename
        detail = detail or src.name
        self.history.append(("move", dest, src, (title, detail)))
        self.log(kind, title, detail, label)
        return src, dest

    def move(self, rel, label, meta=None):
        self._check(label)
        src, dest = self._move_to(rel, self._dest_dir(label), "move", f"Moved to {label}", label=label)
        self._notify("label", {"name": src.name, "label": label, "file_path": str(dest)}, meta)

    def archive(self, rel, meta=None):
        """Done/skip. If crops were taken from this photo (and not undone), call it
        "Crop done"; otherwise it is a plain "Skipped"."""
        src = self._resolve(rel)
        n = sum(1 for e in self.history if e[0] == "crop" and e[3] == src)
        if n:
            detail = f"{src.name} · {n} crop{'s' if n != 1 else ''} saved · original archived"
            src, dest = self._move_to(rel, self._archive_dir(), "done", "Crop done", detail)
        else:
            src, dest = self._move_to(rel, self._archive_dir(), "skip", "Skipped (archived)")
        self._notify("archive", {"name": src.name, "file_path": str(dest)}, meta)

    def crop(self, rel, label, keep, data, meta=None):
        self._check(label)
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("crop is not a JPEG")
        src = self._resolve(rel)
        folder = self._dest_dir(label)
        folder.mkdir(parents=True, exist_ok=True)
        i = 1
        while (folder / f"{src.stem}_crop{i}.jpg").exists():
            i += 1
        crop = folder / f"{src.stem}_crop{i}.jpg"
        crop.write_bytes(data)
        archived = None
        if not keep:
            archived = unique_dest(self._archive_dir(), src.name)
            shutil.move(str(src), str(archived))
        title = f"Crop saved to {label}"
        detail = f"{src.name} → {crop.name} · original {'kept' if keep else 'archived'}"
        self.history.append(("crop", crop, archived, src, (title, detail)))
        self.log("crop", title, detail, label)
        self._notify("crop", {"name": src.name, "label": label, "crop_name": crop.name,
                              "crop_path": str(crop),
                              "archived_path": str(archived) if archived else None}, meta)

    def delete(self, rel, meta=None):
        """Really delete the file (the old /label page's delete button). The bytes
        are kept in memory for this session so Undo can bring it back."""
        if not self.delete_ok:
            raise PermissionError("delete is not enabled here")
        src = self._resolve(rel)
        data = src.read_bytes()
        src.unlink()
        self.history.append(("delete", src, data, ("Deleted", src.name)))
        self.log("delete", "Deleted", src.name)
        self._notify("delete", {"name": src.name}, meta)

    def undo(self, meta=None):
        if not self.history:
            self.log("undo", "Nothing to undo")
            return
        entry = self.history.pop()
        if entry[0] == "delete":
            _, orig, data, (title, detail) = entry
            orig.parent.mkdir(parents=True, exist_ok=True)
            orig.write_bytes(data)
            self.log("undo", f"Undid: {title}", detail)
            self._notify("undo", {"kind": "delete", "name": orig.name, "orig_path": str(orig)}, meta)
            return
        crop = None
        if entry[0] == "move":
            _, dest, orig, (title, detail) = entry
        else:
            _, crop, dest, orig, (title, detail) = entry
            crop.unlink(missing_ok=True)
        if dest is not None and dest.exists():
            orig.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(orig))
        self.log("undo", f"Undid: {title}", detail)
        info = {"kind": entry[0], "name": orig.name, "orig_path": str(orig)}
        if crop is not None:
            info["crop_path"] = str(crop)
        self._notify("undo", info, meta)

    # ---------- one entry point for every POST ----------
    def handle_post(self, route, query, raw):
        """route: 'label' | 'crop' | 'archive' | 'undo' | 'keep'.
        query: urllib.parse.parse_qs(...) dict. Returns (http_status, json_dict).
        A failure is logged so it shows up in the History panel."""
        try:
            meta = {"user": query.get("user", [None])[0]}
            with self.lock:
                if route == "label":
                    body = json.loads(raw or b"{}")
                    self.move(body["name"], body["label"],
                              {**meta, "event_type": body.get("event_type")})
                elif route == "archive":
                    self.archive(json.loads(raw or b"{}")["name"], meta)
                elif route == "delete":
                    if not self.delete_ok:
                        return 404, {"error": "not found"}
                    self.delete(json.loads(raw or b"{}")["name"], meta)
                elif route == "undo":
                    self.undo(meta)
                elif route == "keep":
                    on = query.get("on", ["0"])[0] == "1"
                    self.log("keep", "Keep original: on" if on else "Keep original: off")
                elif route == "crop":
                    self.crop(query["name"][0], query["label"][0],
                              query.get("keep", ["0"])[0] == "1", raw,
                              {**meta, "event_type": query.get("event_type", [None])[0]})
                else:
                    return 404, {"error": "not found"}
            return 200, {}
        except Exception as e:
            self.log("error", "Action failed", f"{type(e).__name__}: {e}")
            return 400, {"error": str(e)}


def inbox_sorter(data: Path, inbox: Path, classes, retrain=False, delete=False, on_action=None):
    """The server's flavour: photos come from inbox/, a label means data/<label>/,
    'both' is set aside in inbox/_both (it is not a training class), and skipped
    photos go to inbox/_archived. `classes()` returns the class folder names."""

    def labels():
        names = list(classes())
        return names if BOTH in names else names + [BOTH]

    def pending():
        return sorted(p.name for p in inbox.iterdir()
                      if p.is_file() and p.suffix.lower() in INBOX_EXTS and not p.name.startswith("."))

    def resolve(name):
        p = inbox / Path(name).name
        if not p.is_file():
            raise FileNotFoundError(name)
        return p

    def dest_dir(label):
        return data / label if label in classes() else inbox / f"_{label}"

    return Sorter(labels=labels, pending=pending, resolve=resolve, dest_dir=dest_dir,
                  archive_dir=lambda: inbox / ARCHIVE, title="Cat sorter (server)", retrain=retrain, delete=delete,
                  on_action=on_action)