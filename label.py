#!/usr/bin/env python3
"""Photo sorter. Shows one photo at a time; tap Litten / Shinx / neither / both
and the file is moved into a folder. No installs needed (standard library only).

Usage:  python3 label.py /path/to/album/folder
Result: /path/to/album/folder_sorted/{Litten,Shinx,neither,both}/

Mouse:  drag on the photo to select a crop. Then a label button saves ONLY the
        cropped part (as a new JPEG, upright if you rotated) into that folder,
        and the original goes to _archived/. With no crop selected, a label
        button moves the whole photo as before.
Keys:   1 Litten   2 Shinx   3 neither   4 both
        Left/Right arrows rotate the view (applied to crops, not to whole-photo moves)
        K  keep the photo after a crop (to crop a second cat out of it)
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

PORT = 8765
LABELS = ["Litten", "Shinx", "neither", "both"]
ARCHIVE = "_archived"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}

if len(sys.argv) != 2 or not Path(sys.argv[1]).expanduser().is_dir():
    sys.exit("Usage: python3 label.py /path/to/album/folder")

SRC = Path(sys.argv[1]).expanduser().resolve()
OUT = SRC.parent / f"{SRC.name}_sorted"
TMP = Path(tempfile.mkdtemp(prefix="label_app_"))
LOCK = threading.Lock()
HISTORY = []  # ("move", dest, orig) or ("crop", crop_file, archived_or_None, orig)


def pending():
    items = []
    for p in SRC.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS and not p.name.startswith("."):
            items.append(p.relative_to(SRC).as_posix())
    return sorted(items)


def counts():
    return {
        l: sum(1 for _ in (OUT / l).iterdir()) if (OUT / l).is_dir() else 0 for l in LABELS
    }


def safe(rel):
    p = (SRC / rel).resolve()
    if SRC not in p.parents or not p.is_file():
        raise FileNotFoundError(rel)
    return p


def unique_dest(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    i = 1
    while dest.exists():  # same filename in two source folders, or repeat crops
        dest = folder / f"{stem}_{i}{suffix}"
        i += 1
    return dest


def move_to(rel, folder):
    src = safe(rel)
    dest = unique_dest(OUT / folder, src.name)
    shutil.move(str(src), str(dest))
    HISTORY.append(("move", dest, src))


def move(rel, label):
    if label not in LABELS:
        raise ValueError("bad label")
    move_to(rel, label)


def save_crop(rel, label, keep, data):
    if label not in LABELS:
        raise ValueError("bad label")
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("crop is not a JPEG")
    src = safe(rel)
    folder = OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    i = 1
    while (folder / f"{src.stem}_crop{i}.jpg").exists():
        i += 1
    crop = folder / f"{src.stem}_crop{i}.jpg"
    crop.write_bytes(data)
    archived = None
    if not keep:
        archived = unique_dest(OUT / ARCHIVE, src.name)
        shutil.move(str(src), str(archived))
    HISTORY.append(("crop", crop, archived, src))


def undo():
    if not HISTORY:
        return
    entry = HISTORY.pop()
    if entry[0] == "move":
        _, dest, orig = entry
    else:
        _, crop, dest, orig = entry
        crop.unlink(missing_ok=True)
    if dest is not None and dest.exists():
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(orig))


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


PAGE = """<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Cat sorter</title>
<style>
 body{margin:0;font-family:system-ui;background:#111;color:#eee;display:flex;flex-direction:column;height:100vh;user-select:none}
 #top{padding:10px 16px;display:flex;justify-content:space-between;font-size:15px;opacity:.85}
 #stage{flex:1;display:flex;align-items:center;justify-content:center;min-height:0;padding:0 12px;overflow:hidden}
 #view{border-radius:6px;cursor:crosshair;touch-action:none}
 #name{text-align:center;font-size:12px;opacity:.6;padding:4px}
 #bar{display:flex;gap:10px;padding:12px;justify-content:center;flex-wrap:wrap;align-items:center}
 button{font-size:22px;padding:16px 28px;border:0;border-radius:12px;cursor:pointer;color:#fff}
 button small{display:block;font-size:11px;opacity:.7}
 .b0{background:#c2692a}.b1{background:#3b7dd8}.b2{background:#555}.b3{background:#7b4bb5}
 .aux{background:#333;font-size:16px;padding:12px 18px}
 label{font-size:14px;opacity:.85;cursor:pointer}
</style>
<div id=top><span id=left></span><span id=cnt></span></div>
<div id=stage><canvas id=view></canvas></div>
<div id=name></div>
<div id=bar>
 <button class=b0 onmousedown="event.preventDefault()" onclick="lab(0)">Litten<small>1</small></button>
 <button class=b1 onmousedown="event.preventDefault()" onclick="lab(1)">Shinx<small>2</small></button>
 <button class=b2 onmousedown="event.preventDefault()" onclick="lab(2)">neither<small>3</small></button>
 <button class=b3 onmousedown="event.preventDefault()" onclick="lab(3)">both<small>4</small></button>
 <button class=aux onmousedown="event.preventDefault()" onclick="done()">Done, skip<small>Space</small></button>
 <button class=aux onmousedown="event.preventDefault()" onclick="undo()">Undo<small>U</small></button>
 <label><input type=checkbox id=keep onchange="keep=this.checked;this.blur();hint()"> keep photo after crop (K)</label>
</div>
<script>
const LABELS=__LABELS__;
let queue=[],busy=false,rot=0,sel=null,drag=null,scale=1,keep=false,current=null,img=null;
const cv=document.getElementById('view'),ctx=cv.getContext('2d');
const url=r=>'/img/'+r.split('/').map(encodeURIComponent).join('/');

// Map natural image pixels into "rotated space" (what you see, rotation applied clockwise).
function setRot(c,nw,nh){
  if(rot===90)c.translate(nh,0);else if(rot===180)c.translate(nw,nh);else if(rot===270)c.translate(0,nw);
  c.rotate(rot*Math.PI/180);
}
function rotSize(){const s=rot%180!==0;return s?[img.naturalHeight,img.naturalWidth]:[img.naturalWidth,img.naturalHeight];}

function draw(){
  if(!img||!img.naturalWidth)return;
  const st=document.getElementById('stage'),[rw,rh]=rotSize();
  scale=Math.min((st.clientWidth-24)/rw,(st.clientHeight-8)/rh);
  const dpr=window.devicePixelRatio||1;
  cv.style.width=rw*scale+'px';cv.style.height=rh*scale+'px';
  cv.width=Math.round(rw*scale*dpr);cv.height=Math.round(rh*scale*dpr);
  ctx.setTransform(scale*dpr,0,0,scale*dpr,0,0);
  ctx.save();setRot(ctx,img.naturalWidth,img.naturalHeight);ctx.drawImage(img,0,0);ctx.restore();
  if(sel){
    ctx.fillStyle='rgba(0,0,0,.55)';ctx.beginPath();
    ctx.rect(0,0,rw,rh);ctx.rect(sel.x,sel.y,sel.w,sel.h);ctx.fill('evenodd');
    ctx.strokeStyle='#fff';ctx.lineWidth=2/scale;ctx.strokeRect(sel.x,sel.y,sel.w,sel.h);
  }
}
window.addEventListener('resize',draw);

function hint(){
  const n=current||'';
  document.getElementById('name').textContent=n?(n+'  \\u00b7  '+(sel
    ?'crop selected: press a label to save just the crop'+(keep?' (photo stays for another crop)':' (then the photo is archived)')
    :'drag to crop \\u00b7 \\u2190 \\u2192 rotate')):'All sorted. You can close this tab.';
}

function pos(e){
  const r=cv.getBoundingClientRect(),[rw,rh]=rotSize();
  return [Math.max(0,Math.min(rw,(e.clientX-r.left)/scale)),Math.max(0,Math.min(rh,(e.clientY-r.top)/scale))];
}
cv.addEventListener('pointerdown',e=>{if(!img)return;cv.setPointerCapture(e.pointerId);drag=pos(e);sel=null;draw();hint();});
cv.addEventListener('pointermove',e=>{
  if(!drag)return;const [x,y]=pos(e);
  sel={x:Math.min(drag[0],x),y:Math.min(drag[1],y),w:Math.abs(x-drag[0]),h:Math.abs(y-drag[1])};draw();
});
cv.addEventListener('pointerup',()=>{
  if(!drag)return;drag=null;
  if(sel&&(sel.w<24||sel.h<24))sel=null;   // a plain click just clears the selection
  draw();hint();
});

function loadCurrent(){
  current=queue.length?queue[0]:null;sel=null;rot=0;img=null;
  if(!current){cv.style.display='none';hint();return;}
  cv.style.display='';
  const mine=current,im=new Image();
  im.onload=()=>{if(current===mine){img=im;draw();}};   // ignore a stale load after a quick tap
  im.src=url(mine);
  queue.slice(1).forEach(q=>{new Image().src=url(q)});
  hint();
}

async function refresh(){
  const s=await (await fetch('/api/state')).json();
  queue=s.queue;
  document.getElementById('left').textContent=s.remaining+' left';
  document.getElementById('cnt').textContent=LABELS.map(l=>l+' '+s.counts[l]).join(' \\u00b7 ');
  if((queue[0]||null)!==current)loadCurrent();else{draw();hint();}
}

function cropBlob(){
  return new Promise(res=>{
    const c=document.createElement('canvas');
    c.width=Math.max(1,Math.round(sel.w));c.height=Math.max(1,Math.round(sel.h));
    const x=c.getContext('2d');
    x.translate(-sel.x,-sel.y);
    setRot(x,img.naturalWidth,img.naturalHeight);
    x.drawImage(img,0,0);
    c.toBlob(res,'image/jpeg',0.95);
  });
}

async function run(fn){
  if(busy)return;busy=true;
  try{await fn();await refresh();}finally{busy=false;}
}
function lab(i){
  if(!current||!img)return;
  run(async()=>{
    if(sel){
      const blob=await cropBlob();
      const r=await fetch('/api/crop?name='+encodeURIComponent(current)+'&label='+encodeURIComponent(LABELS[i])+'&keep='+(keep?1:0),{method:'POST',body:blob});
      if(!r.ok)alert('Crop failed: '+await r.text());
      else if(keep)sel=null;
    }else{
      await fetch('/api/label',{method:'POST',body:JSON.stringify({name:current,label:LABELS[i]})});
    }
  });
}
function done(){if(current)run(()=>fetch('/api/archive',{method:'POST',body:JSON.stringify({name:current})}));}
function undo(){run(()=>fetch('/api/undo',{method:'POST',body:'{}'}));}

document.addEventListener('keydown',e=>{
  if('1234'.includes(e.key)&&e.key.length===1)lab(+e.key-1);
  else if(e.key==='u'||e.key==='z')undo();
  else if(e.key===' '){e.preventDefault();done();}
  else if(e.key==='Escape'){sel=null;draw();hint();}
  else if(e.key==='k'){const k=document.getElementById('keep');k.checked=!k.checked;keep=k.checked;hint();}
  else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){
    e.preventDefault();if(!img)return;
    rot=(rot+(e.key==='ArrowRight'?90:270))%360;sel=null;draw();hint();
  }
});
refresh();
</script>
""".replace("__LABELS__", json.dumps(LABELS))


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

    def do_GET(self):
        if self.path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            with LOCK:
                items = pending()
                state = {"remaining": len(items), "queue": items[:3], "counts": counts()}
            self._send(json.dumps(state).encode())
        elif self.path.startswith("/img/"):
            try:
                with LOCK:
                    path = displayable(safe(unquote(self.path[5:])))
                ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send(path.read_bytes(), ctype, cache="private, max-age=600")
            except Exception:
                self._send(b"not found", "text/plain", 404)
        else:
            self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        url = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            with LOCK:
                if url.path == "/api/label":
                    body = json.loads(raw or b"{}")
                    move(body["name"], body["label"])
                elif url.path == "/api/archive":
                    move_to(json.loads(raw or b"{}")["name"], ARCHIVE)
                elif url.path == "/api/undo":
                    undo()
                elif url.path == "/api/crop":
                    q = parse_qs(url.query)
                    save_crop(q["name"][0], q["label"][0], q.get("keep", ["0"])[0] == "1", raw)
                else:
                    self._send(b"not found", "text/plain", 404)
                    return
            self._send(b"{}")
        except Exception as e:
            self._send(json.dumps({"error": str(e)}).encode(), code=400)


if __name__ == "__main__":
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