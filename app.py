"""Cat identification service.

POST /identify   upload a photo (form: file, key, optional user) -> JSON
                 {cat, best_guess, confidence, saved_as}; saves it to inbox/ and records a
                 `picture` row (source identify), no Discord
POST /litterbox  same as /identify (source litterbox), and also posts the result + photo
                 to Discord. The Pi sends user=pi.
POST /cough      form: cat, key, optional info, optional user -> records a cough event and
                 posts to the cough Discord channel; returns null if that webhook isn't set
                 (the event is still recorded)
GET  /label      page to label captured photos (grows the dataset); same page and
                 /api/* as label.py, see sorter_core.py and ui/. Optional ?user=<name>
                 records who labeled. Labeling Litten or Shinx with an event type (default
                 Litterbox for /litterbox photos) creates an event; see db.py.
GET/POST/PATCH/DELETE /vet_visit...  vet visits for the app's Vet tab, see vet_api.py
GET  /events     events (filter by cat, type, date range), totals and chart data for the
                 app's Events tab; GET /event_types; GET /picture/{id}/image serves an
                 event's photo. See events_api.py.
POST /api/retrain  re-run training on data/ and hot-reload the model
GET  /health     is the model loaded, which classes it knows, how many training
                 photos each class has in data/ (the same ones train.py reads), and
                 how many captures are waiting to be sorted in inbox/ (the "N left"
                 on /label):
                 {"model_loaded": true, "classes": ["Litten", "Shinx", "neither"],
                  "photos": {"Litten": 912, "Shinx": 703, "neither": 42},
                  "waiting_in_inbox": 17}

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
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import joblib
import requests
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

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

INBOX.mkdir(exist_ok=True)
app = FastAPI(title="cat-id")
app.include_router(vet_api.router)
app.include_router(events_api.router)
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


def identify_photo(raw: bytes, tasks: BackgroundTasks, *, received: datetime, source: str, user: str):
    """Classify one photo and keep it in inbox/ for later labeling (the prediction
    is encoded in the file name), and record it as a `picture` row once the response has
    been sent. `received` is when the request arrived (UTC).
    Returns (json_result, image, discord_message)."""
    try:
        img = open_image(io.BytesIO(raw))
    except Exception:
        raise HTTPException(400, "not an image")

    cat, conf = classify(img)
    label = cat if conf >= MIN_CONF else "uncertain"

    name = f"{int(time.time())}_{label}_{conf:.2f}.jpg"
    img.save(INBOX / name, quality=92)
    # After the response, so the Pi and the app never wait on the database.
    tasks.add_task(db.safe_write, "picture", {
        "event_timestamp": received, "best_guess": cat, "confidence": conf,
        "predicted_label": label, "filename": name, "file_path": str(INBOX / name),
        "source": source, "user": user or None, "model_version": model_version,
    })

    if label == "neither":
        msg = "Motion at the litterbox, but no cat detected."
    elif label == "uncertain":
        msg = f"Litterbox visit: not sure which cat (best guess {cat}, {conf:.0%})."
    else:
        msg = f"**{label}** just used the litterbox ({conf:.0%} sure)."
    result = {"cat": label, "best_guess": cat, "confidence": round(conf, 3), "saved_as": name}
    return result, img, msg


@app.post("/identify")
async def identify(tasks: BackgroundTasks, file: UploadFile = File(...), key: str = Form(""),
                   user: str = Form("")):
    """Identify the cat and save the photo. Returns JSON only, no Discord post."""
    received = db.utcnow()
    check_request(key)
    result, _, _ = identify_photo(await file.read(), tasks, received=received, source="identify", user=user)
    return result


@app.post("/litterbox")
async def litterbox(tasks: BackgroundTasks, file: UploadFile = File(...), key: str = Form(""),
                    user: str = Form("")):
    """Same as /identify (same JSON, same saved photo), and also posts the result
    and the photo to Discord. This is the one the Pi should call."""
    received = db.utcnow()
    check_request(key)
    result, img, msg = identify_photo(await file.read(), tasks, received=received, source="litterbox", user=user)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    post_discord(buf.getvalue(), msg)
    return result

@app.post("/cough")
async def cough(tasks: BackgroundTasks, cat: str = Form(""), key: str = Form(""),
                info: str = Form(""), user: str = Form("")):
    """Record a cough event (no event if `cat` isn't Litten or Shinx) and post it to the
    cough Discord channel. Returns null when that webhook isn't set."""
    received = db.utcnow()
    check_key(key)
    tasks.add_task(db.safe_write, "cough", {"cat": cat, "user": user or None,
                                            "notes": info.strip() or None,
                                            "event_timestamp": received})
    if not COUGH_DISCORD_WEBHOOK:
        return
    info = info.strip() or "No additional info."
    timestamp = received.astimezone(EDMONTON_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
    msg = f"**{cat}** just had cough attack at {timestamp}. Additional info: {info}"
    try:
        requests.post(
            COUGH_DISCORD_WEBHOOK,
            data={"content": msg},
            timeout=15,
        )
    except requests.RequestException as e:
        print("discord post failed:", e)
        return {"status": 500, "cat": cat, "message": f"Failed to send cough report to Discord: {e}", "timestamp": timestamp}
    return {"status": 200, "cat": cat, "message": "Cough report sent to Discord."}

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
    }
