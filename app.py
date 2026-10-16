"""Cat identification service.

POST /identify   upload a photo -> JSON {cat, confidence}; also posts to Discord
GET  /label      mobile-friendly page to label captured photos (grows the dataset)
POST /retrain    re-run training on data/ and hot-reload the model
"""
import html
import io
import os
import subprocess
import time
from pathlib import Path

import joblib
import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from embed import embed, open_image

DATA = Path("data")
INBOX = Path("inbox")
MODEL_PATH = Path("model.joblib")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")
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


@app.post("/identify")
async def identify(file: UploadFile = File(...), key: str = Form("")):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")
    if bundle is None:
        raise HTTPException(503, "model not trained yet")
    raw = await file.read()
    try:
        img = open_image(io.BytesIO(raw))
    except Exception:
        raise HTTPException(400, "not an image")

    cat, conf = classify(img)
    label = cat if conf >= MIN_CONF else "uncertain"

    # Keep every capture for later labeling; prediction is encoded in the name.
    name = f"{int(time.time())}_{label}_{conf:.2f}.jpg"
    img.save(INBOX / name, quality=92)

    if label == "neither":
        msg = "Motion at the litterbox, but no cat detected."
    elif label == "uncertain":
        msg = f"Litterbox visit: not sure which cat (best guess {cat}, {conf:.0%})."
    else:
        msg = f"**{label}** just used the litterbox ({conf:.0%} sure)."
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    post_discord(buf.getvalue(), msg)
    return {"cat": label, "best_guess": cat, "confidence": round(conf, 3), "saved_as": name}


@app.get("/inbox/{name}")
def inbox_file(name: str):
    p = INBOX / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


def class_names():
    names = sorted(p.name for p in DATA.iterdir() if p.is_dir()) if DATA.exists() else []
    return names or ["Litten", "Shinx", "neither"]


@app.get("/label", response_class=HTMLResponse)
def label_page():
    files = sorted(INBOX.glob("*.jpg"), reverse=True)[:30]
    rows = []
    for f in files:
        btns = "".join(
            f'<button name="label" value="{html.escape(c)}">{html.escape(c)}</button>'
            for c in class_names()
        )
        rows.append(
            f'<form method="post" action="/label" class="card">'
            f'<img src="/inbox/{f.name}"><div class="guess">{html.escape(f.stem)}</div>'
            f'<input type="hidden" name="name" value="{f.name}">{btns}'
            f'<button name="label" value="__delete__" class="del">delete</button></form>'
        )
    body = "".join(rows) or "<p>Inbox empty. Nothing to label.</p>"
    return f"""<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Label cats</title>
<style>body{{font-family:system-ui;margin:12px;background:#111;color:#eee}}
.card{{background:#1c1c1c;border-radius:12px;padding:10px;margin-bottom:14px}}
img{{width:100%;border-radius:8px}}.guess{{font-size:12px;opacity:.6;margin:4px 0}}
button{{font-size:18px;padding:12px 16px;margin:4px 4px 0 0;border-radius:10px;border:0}}
.del{{background:#5a2a2a;color:#fff}}</style>
<h2>Label captures ({len(files)} shown)</h2>{body}
<form method="post" action="/retrain"><button>Retrain model now</button></form>"""


@app.post("/label")
def label(name: str = Form(...), label: str = Form(...)):
    src = INBOX / Path(name).name
    if not src.exists():
        raise HTTPException(404)
    if label == "__delete__":
        src.unlink()
    else:
        if label not in class_names():
            raise HTTPException(400, "unknown class")
        dest = DATA / label
        dest.mkdir(parents=True, exist_ok=True)
        src.rename(dest / src.name)
    return RedirectResponse("/label", status_code=303)


@app.post("/retrain")
def retrain():
    r = subprocess.run(["python", "train.py"], capture_output=True, text=True)
    load_model()
    if r.returncode != 0:
        raise HTTPException(500, r.stderr[-2000:])
    return RedirectResponse("/label", status_code=303)


@app.get("/health")
def health():
    return {"model_loaded": bundle is not None, "classes": bundle["classes"] if bundle else []}
