"""Cat identification service.

POST /identify   upload a photo -> JSON {cat, confidence}; saves it to inbox/, no Discord
POST /litterbox  same as /identify, and also posts the result + photo to Discord
GET  /label      page to label captured photos (grows the dataset); same page and
                 /api/* as label.py, see sorter_core.py and ui/
POST /api/retrain  re-run training on data/ and hot-reload the model
GET  /health     is the model loaded, which classes it knows, how many training
                 photos each class has in data/ (the same ones train.py reads), and
                 how many captures are waiting to be sorted in inbox/ (the "N left"
                 on /label):
                 {"model_loaded": true, "classes": ["Litten", "Shinx", "neither"],
                  "photos": {"Litten": 912, "Shinx": 703, "neither": 42},
                  "waiting_in_inbox": 17}
"""
import io
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

import joblib
import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

import sorter_core
from embed import embed, open_image

DATA = Path("data")
INBOX = Path("inbox")
MODEL_PATH = Path("model.joblib")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}  # same as train.py
MIN_CONF = float(os.environ.get("MIN_CONF", "0.75"))
API_KEY = os.environ.get("API_KEY", "")  # optional shared secret for /identify

INBOX.mkdir(exist_ok=True)
app = FastAPI(title="cat-id")
bundle = None


def load_model():
    global bundle
    bundle = joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


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


def check_request(key: str):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")
    if bundle is None:
        raise HTTPException(503, "model not trained yet")


def identify_photo(raw: bytes):
    """Classify one photo and keep it in inbox/ for later labeling (the prediction
    is encoded in the file name). Returns (json_result, image, discord_message)."""
    try:
        img = open_image(io.BytesIO(raw))
    except Exception:
        raise HTTPException(400, "not an image")

    cat, conf = classify(img)
    label = cat if conf >= MIN_CONF else "uncertain"

    name = f"{int(time.time())}_{label}_{conf:.2f}.jpg"
    img.save(INBOX / name, quality=92)

    if label == "neither":
        msg = "Motion at the litterbox, but no cat detected."
    elif label == "uncertain":
        msg = f"Litterbox visit: not sure which cat (best guess {cat}, {conf:.0%})."
    else:
        msg = f"**{label}** just used the litterbox ({conf:.0%} sure)."
    result = {"cat": label, "best_guess": cat, "confidence": round(conf, 3), "saved_as": name}
    return result, img, msg


@app.post("/identify")
async def identify(file: UploadFile = File(...), key: str = Form("")):
    """Identify the cat and save the photo. Returns JSON only, no Discord post."""
    check_request(key)
    result, _, _ = identify_photo(await file.read())
    return result


@app.post("/litterbox")
async def litterbox(file: UploadFile = File(...), key: str = Form("")):
    """Same as /identify (same JSON, same saved photo), and also posts the result
    and the photo to Discord. This is the one the Pi should call."""
    check_request(key)
    result, img, msg = identify_photo(await file.read())
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    post_discord(buf.getvalue(), msg)
    return result


def class_names():
    names = sorted(p.name for p in DATA.iterdir() if p.is_dir()) if DATA.exists() else []
    return names or ["Litten", "Shinx", "neither"]


# ---------- /label: the same page and API as label.py (logic in sorter_core.py) ----------
sorter = sorter_core.inbox_sorter(DATA, INBOX, class_names, retrain=True, delete=True)
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
    return sorter.config()


@app.get("/api/state")
def api_state():
    return sorter.state()


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
