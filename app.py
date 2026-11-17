"""Cat identification service.

POST /identify   upload a photo (form: file, key, optional user) -> JSON
                 {cat, best_guess, confidence, saved_as}; saves it to inbox/ and records a
                 `picture` row (source identify), no Discord
POST /litterbox  same as /identify (source litterbox), and also posts the result + photo
                 to Discord. The Pi sends user=pi. Optional form `location` (a location
                 name): which box the photo is of; missing means PI_LOCATION (default
                 basement). Labeling the photo copies it onto the litterbox event.
                 With form `cat` (and optional info, file, event_time, location): a visit
                 reported by hand from the app's Events tab. Works like /cough: the litterbox
                 event is recorded now (at event_time), a photo is optional (saved like
                 /identify's, source litterbox, linked to the event), `location` missing
                 means not known, posts to the litterbox Discord channel; returns null if
                 that webhook isn't set (the event is still recorded). An unknown location
                 gives 400 either way
POST /litterbox_clean  form: location, key, optional bag_changed (true/false, default
                 false), info, user, event_time -> records a litterbox_clean_event row
                 (event_time as for /cough; server_timestamp = arrival time). No Discord.
                 Returns {"status": 200, "location", "message"}. Unknown location or a bad
                 event_time: 400, nothing recorded
POST /cough      form: cat, key, optional info, user, file, event_time -> records a
                 cough event and posts to the cough Discord channel; returns null if that
                 webhook isn't set (the event is still recorded). A photo in `file` is
                 handled like /identify's (model guess, saved to inbox/ for labeling,
                 `picture` row with source identify), linked to the event, attached to the
                 Discord post, and returned as "photo" (the /identify JSON). event_time
                 (ISO 8601 with offset; missing = now; not in the future) is the event's
                 event_timestamp; the photo's picture row keeps its arrival time
GET  /label      page to label captured photos (grows the dataset); same page and
                 /api/* as label.py, see sorter_core.py and ui/. Optional ?user=<name>
                 records who labeled. Labeling Litten or Shinx with an event type (default
                 Litterbox for /litterbox photos) creates an event; see db.py.
GET/POST/PATCH/DELETE /vet_visit...  vet visits for the app's Vet tab, see vet_api.py
GET  /events     events (filter by cat, type, date range), totals and chart data for the
                 app's Events tab; GET /event_types; GET /picture/{id}/image serves an
                 event's photo. See events_api.py.
GET/POST/PATCH /chores, GET/POST/PATCH/DELETE /chore_events..., GET/POST/PATCH
                 /chore_requests..., GET/POST/PATCH /chore_starts...  household chores, when
                 they were done (and how long they took), requests that one needs doing,
                 and who is doing one right now, for the app's Chores page, see
                 chores_api.py. Requests, Dones, cancellations, starts and stops post to the
                 chores Discord channel (CHORES_DISCORD_WEBHOOK_URL; skipped if not set), see
                 chore_discord.py
POST /api/retrain  re-run training on data/ and hot-reload the model
GET  /health     is the model loaded, which classes it knows, how many training
                 photos each class has in data/ (the same ones train.py reads), how
                 many captures are waiting to be sorted in inbox/ (the "N left"
                 on /label), and which server build this is (the release tag and full
                 commit hash; "dev" and null for a local build), and per litterbox when
                 it was last cleaned and its bag last changed (UTC; null if never;
                 `litterboxes` is null if the database is down), and the active chores
                 with when each was last done and whether it's overdue (`chores`, the same
                 chore objects as GET /chores; null if the database is down):
                 {"model_loaded": true, "classes": ["Litten", "Shinx", "neither"],
                  "photos": {"Litten": 912, "Shinx": 703, "neither": 42},
                  "waiting_in_inbox": 17, "version": "v0.2.0",
                  "commit": "433c253...",
                  "litterboxes": [{"location": "basement", "name": "Basement",
                                   "last_cleaned": "2026-11-15T15:02:00+00:00",
                                   "bag_last_changed": null}, ...],
                  "chores": [{"id": 1, "name": "vacuum", "label_name": "Vacuum",
                              "warning_threshold_days": 7, "active": true,
                              "last_done": "2026-11-10T18:00:00+00:00",
                              "last_done_by": ["Ashley"],
                              "due_at": "2026-11-17T18:00:00+00:00", "overdue": false,
                              "request": null, "in_progress": null}, ...]}

`user` everywhere is a name from app_user (pi, Ashley, Mac); missing or unknown means the
system user. Database writes never fail a request: if Postgres is down they go to
inbox/_db_failed.jsonl (replay with replay_db_failed.py).
"""
import io
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import joblib
import requests
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import chores_api
import db
import events_api
import sorter_core
import vet_api
from embed import embed, open_image

DATA = Path("data")
INBOX = Path("inbox")
MODEL_PATH = Path("model.joblib")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
COUGH_DISCORD_WEBHOOK = os.environ.get("COUGH_DISCORD_WEBHOOK_URL", "")
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}  # same as train.py
MIN_CONF = float(os.environ.get("MIN_CONF", "0.75"))
API_KEY = os.environ.get("API_KEY", "")  # optional shared secret for /identify
EDMONTON_TZ = ZoneInfo("America/Edmonton")
# Which build this is (set in the Dockerfile from build args; release.yml passes the tag and
# commit). "dev" / None for a local build.
SERVER_VERSION = os.environ.get("CAT_ID_VERSION") or "dev"
SERVER_COMMIT = os.environ.get("CAT_ID_COMMIT") or None
# The box the Pi's camera watches: /litterbox photos sent without a `location` are of it.
PI_LOCATION = os.environ.get("PI_LOCATION", "basement")

INBOX.mkdir(exist_ok=True)
app = FastAPI(title="cat-id")
app.include_router(vet_api.router)
app.include_router(events_api.router)
app.include_router(chores_api.router)
bundle = None
model_version = None  # model.joblib's modified time (UTC), stored on each picture row


def load_model():
    global bundle, model_version
    bundle = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None
    model_version = (datetime.fromtimestamp(MODEL_PATH.stat().st_mtime, timezone.utc)
                     .isoformat(timespec="seconds") if bundle is not None else None)


load_model()


def classify(img):
    vec = embed([img])
    probs = bundle["clf"].predict_proba(vec)[0]
    i = int(probs.argmax())
    return bundle["classes"][i], float(probs[i])


def post_discord(jpeg: bytes, text: str):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(
            DISCORD_WEBHOOK,
            data={"content": text},
            files={"file": ("cat.jpg", jpeg, "image/jpeg")},
            timeout=15,
        )
    except requests.RequestException as e:
        print("discord post failed:", e)


def check_key(key: str):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")


def check_request(key: str):
    check_key(key)
    if bundle is None:
        raise HTTPException(503, "model not trained yet")


def identify_photo(raw: bytes, tasks: BackgroundTasks, *, received: datetime, source: str, user: str,
                   location: str | None = None):
    """Classify one photo and keep it in inbox/ for later labeling (the prediction
    is encoded in the file name), and record it as a `picture` row once the response has
    been sent. `received` is when the request arrived (UTC); `location` the litterbox it
    is of, if any.
    Returns (json_result, image, discord_message)."""
    try:
        img = open_image(io.BytesIO(raw))
    except Exception:
        raise HTTPException(400, "not an image")

    if bundle is not None:
        cat, conf = classify(img)
        label = cat if conf >= MIN_CONF else "uncertain"
        name = f"{int(time.time())}_{label}_{conf:.2f}.jpg"
    else:  # only /cough gets here: /identify and /litterbox answer 503 first
        cat = conf = label = None
        name = f"{int(time.time())}_unknown.jpg"
    img.save(INBOX / name, quality=92)
    # After the response, so the Pi and the app never wait on the database.
    tasks.add_task(db.safe_write, "picture", {
        "event_timestamp": received, "best_guess": cat, "confidence": conf,
        "predicted_label": label, "filename": name, "file_path": str(INBOX / name),
        "source": source, "user": user or None, "model_version": model_version,
        "location": location,
    })

    if label == "neither":
        msg = "Motion at the litterbox, but no cat detected."
    elif label == "uncertain":
        msg = f"Litterbox visit: not sure which cat (best guess {cat}, {conf:.0%})."
    else:
        msg = f"**{label}** just used the litterbox ({conf:.0%} sure)."
    result = {"cat": label, "best_guess": cat,
              "confidence": round(conf, 3) if conf is not None else None, "saved_as": name}
    return result, img, msg


@app.post("/identify")
async def identify(tasks: BackgroundTasks, file: UploadFile = File(...), key: str = Form(""),
                   user: str = Form("")):
    """Identify the cat and save the photo. Returns JSON only, no Discord post."""
    received = db.utcnow()
    check_request(key)
    result, _, _ = identify_photo(await file.read(), tasks, received=received, source="identify", user=user)
    return result


def check_location(name: str) -> str | None:
    """A location name from a form, stripped; None if empty. 400 if it isn't a known one."""
    name = name.strip()
    if not name:
        return None
    known = [l["name"] for l in db.locations()]
    if name not in known:
        raise HTTPException(400, f"unknown location {name!r} (known: {', '.join(known)})")
    return name


@app.post("/litterbox")
async def litterbox(tasks: BackgroundTasks, file: UploadFile | None = File(None),
                    key: str = Form(""), user: str = Form(""), cat: str = Form(""),
                    info: str = Form(""), event_time: str = Form(""),
                    location: str = Form("")):
    """Same as /identify (same JSON, same saved photo), and also posts the result
    and the photo to Discord. This is the one the Pi should call. `location` is the box
    the photo is of (missing: PI_LOCATION).
    With `cat` (the app's Add litterbox sheet): a litterbox visit reported by hand, like
    /cough: the event is recorded now, `file`, `info`, `event_time` and `location` are
    optional, see report_event()."""
    received = db.utcnow()
    if cat:
        check_key(key)
        where = check_location(location)
        return report_event(
            tasks, "litterbox_report", raw=await file.read() if file is not None else b"",
            cat=cat, info=info, user=user, received=received, event_time=event_time,
            source="litterbox", location=where,
            webhook=DISCORD_WEBHOOK, what="litterbox report",
            text=lambda ts, note: f"**{cat}** used the litterbox at {ts} (reported from the app). "
                                  f"Additional info: {note}")
    check_request(key)
    if file is None:
        raise HTTPException(400, "file is required (or send cat to report a visit by hand)")
    where = check_location(location) or PI_LOCATION
    result, img, msg = identify_photo(await file.read(), tasks, received=received,
                                      source="litterbox", user=user, location=where)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    post_discord(buf.getvalue(), msg)
    return result


@app.post("/cough")
async def cough(tasks: BackgroundTasks, cat: str = Form(""), key: str = Form(""),
                info: str = Form(""), user: str = Form(""),
                file: UploadFile | None = File(None), event_time: str = Form("")):
    """Record a cough event (no event if `cat` isn't Litten or Shinx) and post it to the
    cough Discord channel. Returns null when that webhook isn't set. Optional photo and
    event_time: see report_event()."""
    received = db.utcnow()
    check_key(key)
    return report_event(
        tasks, "cough", raw=await file.read() if file is not None else b"", cat=cat,
        info=info, user=user, received=received, event_time=event_time, source="identify",
        webhook=COUGH_DISCORD_WEBHOOK, what="cough report",
        text=lambda ts, note: f"**{cat}** just had cough attack at {ts}. Additional info: {note}")


# A picked event time may be this far ahead of the server's clock (phone clock drift).
CLOCK_SLACK = timedelta(minutes=5)


def parse_event_time(value: str, received: datetime) -> datetime:
    """`event_time` from the app (ISO 8601 with a UTC offset, e.g. 2026-11-14T21:41:00Z):
    when the event happened. Missing means when the request arrived. 400 if it can't be
    read, has no offset, or is in the future."""
    if not value.strip():
        return received
    try:
        t = datetime.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(400, "event_time must be an ISO 8601 date and time")
    if t.tzinfo is None:
        raise HTTPException(400, "event_time needs a UTC offset (e.g. ...Z or ...-06:00)")
    if t > received + CLOCK_SLACK:
        raise HTTPException(400, "event_time can't be in the future")
    return min(t.astimezone(timezone.utc), received)


def report_event(tasks: BackgroundTasks, kind: str, *, raw: bytes, cat: str, info: str,
                 user: str, received: datetime, event_time: str, source: str, webhook: str,
                 what: str, text, location: str | None = None):
    """An event reported from the app with the cat picked by hand (/cough, /litterbox with
    `cat`). The db writer `kind` records it after the response (no event if `cat` isn't
    Litten or Shinx). An optional photo (`raw`) is handled like /identify's (model guess if
    the model is loaded, saved to inbox/ for labeling, `picture` row with `source`), linked
    to the event, attached to the Discord post and returned as "photo". A file that isn't
    an image gives 400 and nothing is recorded. Returns null when `webhook` isn't set.
    `event_time` (see parse_event_time) becomes the event's event_timestamp; the photo's
    picture row keeps the arrival time. `location` (a checked location name or None) goes
    on the event and its photo. `text(timestamp, note)` is the Discord message."""
    happened = parse_event_time(event_time, received)  # before anything is saved
    photo = None
    if raw:
        photo, img, _ = identify_photo(raw, tasks, received=received, source=source, user=user,
                                       location=location)
    # Added after the picture write, so the event can find its picture row.
    tasks.add_task(db.safe_write, kind, {"cat": cat, "user": user or None,
                                         "notes": info.strip() or None,
                                         "event_timestamp": happened,
                                         "photo": photo["saved_as"] if photo else None,
                                         "location": location})
    if not webhook:
        return None
    timestamp = happened.astimezone(EDMONTON_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    if received - happened > CLOCK_SLACK:  # set by hand to earlier: say when it was sent
        timestamp += f" (reported {received.astimezone(EDMONTON_TZ):%Y-%m-%d %H:%M})"
    msg = text(timestamp, info.strip() or "No additional info.")
    files = None
    if photo:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        files = {"file": ("photo.jpg", buf.getvalue(), "image/jpeg")}
    try:
        requests.post(webhook, data={"content": msg}, files=files, timeout=15)
    except requests.RequestException as e:
        print("discord post failed:", e)
        return {"status": 500, "cat": cat, "message": f"Failed to send {what} to Discord: {e}",
                "timestamp": timestamp}
    result = {"status": 200, "cat": cat, "message": f"{what.capitalize()} sent to Discord."}
    if photo:
        result["photo"] = photo
    return result


@app.post("/litterbox_clean")
def litterbox_clean(tasks: BackgroundTasks, location: str = Form(""), key: str = Form(""),
                    bag_changed: str = Form("false"), info: str = Form(""),
                    user: str = Form(""), event_time: str = Form("")):
    """A litterbox was cleaned (the app's Add event > Clean Litterbox). Recorded after the
    response like the other writes; no Discord post."""
    received = db.utcnow()
    check_key(key)
    where = check_location(location)
    if where is None:
        raise HTTPException(400, "location is required")
    flag = bag_changed.strip().lower()
    if flag not in ("true", "false", "1", "0", "yes", "no", "on", "off", ""):
        raise HTTPException(400, "bag_changed must be true or false")
    happened = parse_event_time(event_time, received)
    tasks.add_task(db.safe_write, "litterbox_clean", {
        "location": where, "user": user or None, "notes": info.strip() or None,
        "bag_changed": flag in ("true", "1", "yes", "on"),
        "event_timestamp": happened, "server_timestamp": received,
    })
    return {"status": 200, "location": where, "message": "Litterbox clean recorded."}


def class_names():
    names = sorted(p.name for p in DATA.iterdir() if p.is_dir()) if DATA.exists() else []
    return names or ["Litten", "Shinx", "neither"]


# ---------- /label: the same page and API as label.py (logic in sorter_core.py) ----------
def record_label_action(action, info):
    """sorter_core calls this after each label / crop / archive / delete / undo; the db.py
    writer of the same name updates picture and event rows. The returned text shows in the
    page's History."""
    return db.safe_write(action, info, on_fail="Database unavailable: saved for replay later")


sorter = sorter_core.inbox_sorter(DATA, INBOX, class_names, retrain=True, delete=True,
                                  on_action=record_label_action)
NO_CACHE = {"Cache-Control": "no-cache"}


def _file(path, **kw):
    if path is None:
        raise HTTPException(404)
    return FileResponse(path, **kw)


@app.get("/label")
def label_page():
    return _file(sorter_core.ui_file("label.html"), media_type="text/html", headers=NO_CACHE)


@app.get("/ui/{name}")
def ui_file(name: str):
    return _file(sorter_core.ui_file(name), headers=NO_CACHE)


@app.get("/asset/{name}")
def asset(name: str):
    return _file(sorter_core.asset_file(name), headers={"Cache-Control": "private, max-age=600"})


@app.get("/img/{name:path}")
def img(name: str):
    try:
        p = sorter.file_path(name)
    except FileNotFoundError:
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/config")
def api_config():
    # event_types turns on the label page's event picker (label.py doesn't send it)
    return {**sorter.config(), "event_types": db.event_types()}


@app.get("/api/state")
def api_state():
    # sources: {photo name: "litterbox" | "identify"} for the queue, so the page can preset
    # the event picker. A photo with no row is left out and gets the server's default.
    s = sorter.state()
    return {**s, "sources": db.picture_sources(s["queue"])}


@app.get("/api/log")
def api_log(since: int = 0):
    return sorter.log_since(since)


retrain_lock = threading.Lock()


def run_retrain():
    """Re-run train.py and hot-reload the model. Returns (http_status, json_dict)."""
    if not retrain_lock.acquire(blocking=False):
        sorter.log("error", "Retrain already running")
        return 409, {"error": "busy"}
    try:
        sorter.log("retrain", "Retraining started", "this can take a few minutes")
        r = subprocess.run(["python", "train.py"], capture_output=True, text=True)
        load_model()
        if r.returncode != 0:
            sorter.log("error", "Retrain failed", r.stderr[-300:])
            return 500, {"error": r.stderr[-2000:]}
        tail = [l for l in r.stdout.splitlines() if l.strip()]
        sorter.log("done", "Retrain finished", "\n".join(tail[-2:]))
        return 200, {}
    finally:
        retrain_lock.release()


@app.post("/api/retrain")  # used by the Retrain button on the page
def api_retrain():
    code, body = run_retrain()
    return JSONResponse(body, status_code=code)


@app.post("/retrain")  # the original endpoint, unchanged for curl/cron: redirects back to /label
def retrain():
    code, body = run_retrain()
    if code != 200:
        raise HTTPException(code, body["error"])
    return RedirectResponse("/label", status_code=303)


@app.post("/label")  # the original form endpoint: name + label ("__delete__" deletes)
def label_form(name: str = Form(...), label: str = Form(...)):
    route = "delete" if label == "__delete__" else "label"
    code, body = sorter.handle_post(route, {}, json.dumps({"name": name, "label": label}).encode())
    if code != 200:
        raise HTTPException(400, body.get("error", "failed"))
    return RedirectResponse("/label", status_code=303)


@app.get("/inbox/{name}")  # the original photo URL (same as /img/<name>)
def inbox_file(name: str):
    return img(name)


@app.post("/api/{route}")  # label, crop, archive, undo, keep
async def api_post(route: str, request: Request):
    code, body = sorter.handle_post(route, parse_qs(request.url.query), await request.body())
    return JSONResponse(body, status_code=code)


@app.get("/health")
def health():
    photos = {
        d.name: sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() in PHOTO_EXTS)
        for d in sorted(DATA.iterdir()) if d.is_dir()
    } if DATA.exists() else {}
    return {
        "model_loaded": bundle is not None,
        "classes": bundle["classes"] if bundle else [],
        "photos": photos,
        "waiting_in_inbox": sorter.remaining(),
        "version": SERVER_VERSION,
        "commit": SERVER_COMMIT,
        "litterboxes": db.litterbox_status(),
        "chores": db.chore_status(),
    }
