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
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

PORT = 8765
LABELS = ["Litten", "Shinx", "neither", "both"]
ARCHIVE = "_archived"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}
# Button artwork lives in the img_src folder next to this script.
# Only these six filenames are ever served.
IMG_DIR = Path(__file__).resolve().parent / "img_src"
ASSETS = {
    "litten_pokemon.png", "shinx_pokemon.png", "neither.png",
    "both.png", "done_skip.png", "undo.png",
    "keep_original.png", "dont_keep.png",
}

if len(sys.argv) != 2 or not Path(sys.argv[1]).expanduser().is_dir():
    sys.exit("Usage: python3 label.py /path/to/album/folder")

SRC = Path(sys.argv[1]).expanduser().resolve()
OUT = SRC.parent / f"{SRC.name}_sorted"
TMP = Path(tempfile.mkdtemp(prefix="label_app_"))
LOCK = threading.Lock()
# Undo stack: ("move", dest, orig, (title, detail)) or
#             ("crop", crop_file, archived_or_None, orig, (title, detail))
HISTORY = []
LOG = []  # read-only action log for the History panel (lives until the script stops)


def log(kind, title, detail="", label=None):
    LOG.append({
        "id": len(LOG) + 1, "t": time.strftime("%H:%M:%S"),
        "kind": kind, "title": title, "detail": detail, "label": label,
    })


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


def move_to(rel, folder, kind, title, detail=None):
    src = safe(rel)
    dest = unique_dest(OUT / folder, src.name)
    shutil.move(str(src), str(dest))
    detail = detail or src.name
    HISTORY.append(("move", dest, src, (title, detail)))
    log(kind, title, detail, folder if folder in LABELS else None)


def archive(rel):
    """Done/skip. If crops were taken from this photo (and not undone), call it
    "Crop done"; otherwise it is a plain "Skipped"."""
    src = safe(rel)
    n = sum(1 for e in HISTORY if e[0] == "crop" and e[3] == src)
    if n:
        detail = f"{src.name} · {n} crop{'s' if n != 1 else ''} saved · original archived"
        move_to(rel, ARCHIVE, "done", "Crop done", detail)
    else:
        move_to(rel, ARCHIVE, "skip", "Skipped (archived)")


def move(rel, label):
    if label not in LABELS:
        raise ValueError("bad label")
    move_to(rel, label, "move", f"Moved to {label}")


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
    title = f"Crop saved to {label}"
    detail = f"{src.name} → {crop.name} · original {'kept' if keep else 'archived'}"
    HISTORY.append(("crop", crop, archived, src, (title, detail)))
    log("crop", title, detail, label)


def undo():
    if not HISTORY:
        log("undo", "Nothing to undo")
        return
    entry = HISTORY.pop()
    if entry[0] == "move":
        _, dest, orig, (title, detail) = entry
    else:
        _, crop, dest, orig, (title, detail) = entry
        crop.unlink(missing_ok=True)
    if dest is not None and dest.exists():
        orig.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(orig))
    log("undo", f"Undid: {title}", detail)


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
 body{margin:0;font-family:system-ui;background:#111;color:#eee;display:flex;height:100vh;user-select:none}
 #col{flex:1;min-width:0;display:flex;flex-direction:column;position:relative}
 #top{padding:10px 16px;display:flex;align-items:center;gap:14px;font-size:15px}
 #left{flex:0 0 auto;opacity:.85}
 #cnt{flex:1;text-align:right;opacity:.85}
 #cnt span{display:inline-block}
 #histbtn{width:auto;height:auto;padding:6px 12px;font-size:13px;border-radius:8px;background:#2a2a2a;display:inline-block}
 #histbtn[aria-pressed=true]{background:#454545}
 #histbtn kbd{font:inherit;font-size:11px;opacity:.6;margin-left:4px}
 #stage{flex:1;display:flex;align-items:center;justify-content:center;min-height:0;padding:0 12px;overflow:hidden}
 #view{border-radius:6px;cursor:crosshair;touch-action:none}
 #name{text-align:center;font-size:12px;opacity:.6;padding:4px}
 #bar{display:flex;gap:10px;padding:12px;justify-content:center;flex-wrap:wrap;align-items:center}
 button{border:0;border-radius:12px;cursor:pointer;color:#fff;width:120px;height:90px;padding:0;
   background:#333 center/contain no-repeat;display:flex;align-items:flex-end;justify-content:center}
 button:hover{filter:brightness(1.1)}
 .tip{opacity:0;transition:opacity .12s;pointer-events:none;margin-bottom:6px;padding:3px 10px;border-radius:8px;
   background:rgba(0,0,0,.72);font-size:16px;line-height:1.25;text-align:center;white-space:nowrap}
 .tip small{display:block;font-size:11px;opacity:.75}
 button:hover .tip,button.noimg .tip{opacity:1}   /* no artwork found: always show the label */
 .b0{background-image:url(/asset/litten_pokemon.png);background-color:#d62828}
 .b1{background-image:url(/asset/shinx_pokemon.png);background-color:#f4c20d}
 .b2{background-image:url(/asset/neither.png);background-color:#555}
 .b3{background-image:url(/asset/both.png);background-color:#7b4bb5}
 .done{background-image:url(/asset/done_skip.png);background-color:#333}
 .undo{background-image:url(/asset/undo.png);background-color:#333}
 .keep{background-image:url(/asset/dont_keep.png);background-color:#555}
 .keep.on{background-image:url(/asset/keep_original.png);background-color:#d4af37}

 /* --- feedback: ring flash on the button, colour flash around the photo, counter bump --- */
 @keyframes ring{
   0%{transform:scale(.94);box-shadow:0 0 0 0 rgba(255,255,255,.95),0 0 18px 4px rgba(255,255,255,.7)}
   40%{transform:scale(1.03)}
   100%{transform:scale(1);box-shadow:0 0 0 10px rgba(255,255,255,0),0 0 18px 4px rgba(255,255,255,0)}}
 button.ring{animation:ring .38s ease-out}
 @keyframes pf{
   0%{box-shadow:0 0 0 8px var(--fc),0 0 26px 8px var(--fc)}
   100%{box-shadow:0 0 0 8px transparent,0 0 26px 8px transparent}}
 #view.pflash{animation:pf .5s ease-out}
 @keyframes bump{
   0%{transform:scale(1)}
   35%{transform:scale(1.35);color:#fff;text-shadow:0 0 10px var(--ac)}
   100%{transform:scale(1)}}
 .bump{animation:bump .6s ease-out}

 /* --- history panel: chat-style, read-only --- */
 #hist{width:300px;flex:0 0 300px;display:flex;flex-direction:column;background:#161616;border-left:1px solid #2a2a2a}
 #hist.hide{display:none}
 #hhead{padding:12px 14px;font-size:14px;font-weight:600;border-bottom:1px solid #2a2a2a;display:flex;justify-content:space-between;align-items:baseline}
 #hhead small{font-weight:400;opacity:.55;font-size:12px}
 #hlist{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px;user-select:text}
 #hlist .empty{opacity:.45;font-size:13px;text-align:center;margin-top:24px}
 @keyframes pop{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
 .msg{background:#232323;border-radius:12px 12px 12px 3px;padding:7px 10px;border-left:4px solid var(--ac,#888);animation:pop .2s ease-out}
 .msg .row{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
 .msg b{font-size:13px}
 .msg time{font-size:11px;opacity:.5;white-space:nowrap}
 .msg .d{font-size:12px;opacity:.65;margin-top:2px;word-break:break-all}
 #hfoot{padding:8px 14px;font-size:11px;opacity:.5;border-top:1px solid #2a2a2a;text-align:center}
</style>
<div id=col>
<div id=top><span id=left></span><span id=cnt></span><button id=histbtn aria-pressed="true" aria-label="Show or hide history" onmousedown="event.preventDefault()" onclick="toggleHist()">History<kbd>H</kbd></button></div>
<div id=stage><canvas id=view></canvas></div>
<div id=name></div>
<div id=bar>
 <button class=b0 data-img="litten_pokemon.png" aria-label="Litten" onmousedown="event.preventDefault()" onclick="lab(0)"><span class=tip>Litten<small>1</small></span></button>
 <button class=b1 data-img="shinx_pokemon.png" aria-label="Shinx" onmousedown="event.preventDefault()" onclick="lab(1)"><span class=tip>Shinx<small>2</small></span></button>
 <button class=b2 data-img="neither.png" aria-label="neither" onmousedown="event.preventDefault()" onclick="lab(2)"><span class=tip>neither<small>3</small></span></button>
 <button class=b3 data-img="both.png" aria-label="Both" onmousedown="event.preventDefault()" onclick="lab(3)"><span class=tip>both<small>4</small></span></button>
 <button class=done data-img="done_skip.png" aria-label="Done/Skip" onmousedown="event.preventDefault()" onclick="done()"><span class=tip>Done, skip<small>Space</small></span></button>
 <button class=undo data-img="undo.png" aria-label="Undo" onmousedown="event.preventDefault()" onclick="undo()"><span class=tip>Undo<small>U</small></span></button>
 <button id=keepbtn class=keep data-img="keep_original.png dont_keep.png" aria-label="Keep photo after crop" aria-pressed="false" onmousedown="event.preventDefault()" onclick="toggleKeep()"><span class=tip></span></button>
</div>
</div>
<aside id=hist>
 <div id=hhead><span>History</span><small id=hcount>0 actions</small></div>
 <div id=hlist><div class=empty>Nothing yet. Your actions will appear here.</div></div>
 <div id=hfoot>Read-only log of this session</div>
</aside>
<script>
const LABELS=__LABELS__;
let queue=[],busy=false,rot=0,sel=null,drag=null,scale=1,keep=false,current=null,img=null;
const cv=document.getElementById('view'),ctx=cv.getContext('2d');
const url=r=>'/img/'+r.split('/').map(encodeURIComponent).join('/');

// ---------- feedback helpers ----------
const COLORS={Litten:'#d62828',Shinx:'#f4c20d',neither:'#9a9a9a',both:'#7b4bb5'};
const KIND_COLORS={skip:'#bdbdbd',done:'#6fcf97',undo:'#ff9f1c',keep:'#d4af37',error:'#ff4d4d'};
const BTN=['.b0','.b1','.b2','.b3'];
const accent=e=>(e.label&&COLORS[e.label])||KIND_COLORS[e.kind]||'#888';
function restart(el,cls){el.classList.remove(cls);void el.offsetWidth;el.classList.add(cls);}
function ring(sel){const b=document.querySelector(sel);if(b)restart(b,'ring');}      // option 2: ring flash on the button
function pflash(color){cv.style.setProperty('--fc',color);restart(cv,'pflash');}       // option 6: colour flash around the photo
document.addEventListener('animationend',e=>e.target.classList.remove('ring','pflash','bump'));

// option 5: one span per counter so only the one that changed bumps
const cntEl=document.getElementById('cnt');let prevCounts=null;
LABELS.forEach((l,i)=>{
  if(i)cntEl.append(' \\u00b7 ');
  const s=document.createElement('span');s.id='c_'+l;s.style.setProperty('--ac',COLORS[l]);s.textContent=l+' 0';cntEl.append(s);
});

// history panel: read-only, newest at the bottom like a chat
let histCount=0,lastId=null,pulling=Promise.resolve();
function addMsg(e){
  const list=document.getElementById('hlist');
  const stick=list.scrollHeight-list.scrollTop-list.clientHeight<60;   // only follow if already at the bottom
  const empty=list.querySelector('.empty');if(empty)empty.remove();
  const m=document.createElement('div');m.className='msg';m.style.setProperty('--ac',accent(e));
  const row=document.createElement('div');row.className='row';
  const b=document.createElement('b');b.textContent=e.title;
  const tm=document.createElement('time');tm.textContent=e.t;
  row.append(b,tm);m.append(row);
  if(e.detail){const d=document.createElement('div');d.className='d';d.textContent=e.detail;m.append(d);}
  list.append(m);
  document.getElementById('hcount').textContent=(++histCount)+(histCount===1?' action':' actions');
  if(stick)list.scrollTop=list.scrollHeight;
}
async function doPull(){
  const r=await (await fetch('/api/log?since='+(lastId||0))).json();
  const fresh=r.entries;
  fresh.forEach(addMsg);
  if(fresh.length){
    // A failed action turns the photo flash red (it is also logged in History).
    // Not on page load: entries that already existed then are old news.
    if(lastId!==null&&fresh.some(e=>e.kind==='error'))pflash(KIND_COLORS.error);
    lastId=fresh[fresh.length-1].id;
  }else if(lastId===null)lastId=0;
}
function pullLog(){pulling=pulling.then(doPull,doPull);return pulling;}   // serialised so entries never double up

let histOn=true;
try{histOn=localStorage.getItem('hist')!=='0';}catch(_){}
function renderHist(){
  document.getElementById('hist').classList.toggle('hide',!histOn);
  document.getElementById('histbtn').setAttribute('aria-pressed',String(histOn));
  if(histOn){const l=document.getElementById('hlist');l.scrollTop=l.scrollHeight;}
}
function toggleHist(){
  histOn=!histOn;
  try{localStorage.setItem('hist',histOn?'1':'0');}catch(_){}
  renderHist();ring('#histbtn');
}

// Map natural image pixels into "rotated space" (what you see, rotation applied clockwise).
function setRot(c,nw,nh){
  if(rot===90)c.translate(nh,0);else if(rot===180)c.translate(nw,nh);else if(rot===270)c.translate(0,nw);
  c.rotate(rot*Math.PI/180);
}
function rotSize(){const s=rot%180!==0;return s?[img.naturalHeight,img.naturalWidth]:[img.naturalWidth,img.naturalHeight];}

function draw(){
  if(!img||!img.naturalWidth)return;
  const st=document.getElementById('stage'),[rw,rh]=rotSize();
  scale=Math.min((st.clientWidth-24)/rw,(st.clientHeight-20)/rh);   // margin leaves room for the photo flash
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
new ResizeObserver(()=>draw()).observe(document.getElementById('stage'));   // also fires when the history panel opens or closes

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
  LABELS.forEach(l=>{
    const el=document.getElementById('c_'+l),txt=l+' '+s.counts[l];
    if(el.textContent!==txt){el.textContent=txt;if(prevCounts)restart(el,'bump');}
  });
  prevCounts=s.counts;
  if((queue[0]||null)!==current)loadCurrent();else{draw();hint();}
  await pullLog();
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
  try{await fn();await refresh();}
  catch(err){document.getElementById('name').textContent='Lost contact with the sorter. Is label.py still running?';pflash(KIND_COLORS.error);}
  finally{busy=false;}
}
function lab(i){
  if(!current||!img)return;
  run(async()=>{
    ring(BTN[i]);pflash(COLORS[LABELS[i]]);                       // instant feedback, for clicks and keys alike
    if(sel){
      const blob=await cropBlob();
      const r=await fetch('/api/crop?name='+encodeURIComponent(current)+'&label='+encodeURIComponent(LABELS[i])+'&keep='+(keep?1:0),{method:'POST',body:blob});
      if(r.ok&&keep)sel=null;       // a failure is logged by the server and appears in History
    }else{
      await fetch('/api/label',{method:'POST',body:JSON.stringify({name:current,label:LABELS[i]})});
    }
  });
}
function done(){
  if(current)run(()=>{ring('.done');pflash(KIND_COLORS.skip);return fetch('/api/archive',{method:'POST',body:JSON.stringify({name:current})});});
}
function undo(){
  run(()=>{ring('.undo');pflash(KIND_COLORS.undo);return fetch('/api/undo',{method:'POST',body:'{}'});});
}

document.addEventListener('keydown',e=>{
  if('1234'.includes(e.key)&&e.key.length===1)lab(+e.key-1);
  else if(e.key==='u'||e.key==='z')undo();
  else if(e.key===' '){e.preventDefault();done();}
  else if(e.key==='Escape'){sel=null;draw();hint();}
  else if(e.key==='k')toggleKeep();
  else if(e.key==='h')toggleHist();
  else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){
    e.preventDefault();if(!img)return;
    rot=(rot+(e.key==='ArrowRight'?90:270))%360;sel=null;draw();hint();
  }
});
// If a button's artwork is missing from img_src/, show its label permanently instead.
document.querySelectorAll('#bar button[data-img]').forEach(b=>{
  b.dataset.img.split(' ').forEach(n=>{
    const t=new Image();t.onerror=()=>b.classList.add('noimg');t.src='/asset/'+n;
  });
});
function renderKeep(){
  const b=document.getElementById('keepbtn');
  b.classList.toggle('on',keep);
  b.setAttribute('aria-pressed',String(keep));
  b.querySelector('.tip').innerHTML=(keep?'Keep original':"Don't keep")+'<small>K</small>';
}
function toggleKeep(){
  keep=!keep;renderKeep();hint();ring('#keepbtn');
  fetch('/api/keep?on='+(keep?1:0),{method:'POST'}).then(pullLog).catch(()=>{});   // so the toggle shows in the history
}
renderKeep();
renderHist();
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
        elif self.path.startswith("/api/log"):
            try:
                since = int(parse_qs(urlparse(self.path).query).get("since", ["0"])[0])
            except ValueError:
                since = 0
            with LOCK:
                entries = LOG[max(since, 0):]
            self._send(json.dumps({"entries": entries}).encode())
        elif self.path.startswith("/img/"):
            try:
                with LOCK:
                    path = displayable(safe(unquote(self.path[5:])))
                ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self._send(path.read_bytes(), ctype, cache="private, max-age=600")
            except Exception:
                self._send(b"not found", "text/plain", 404)
        elif self.path.startswith("/asset/") and self.path[7:] in ASSETS:
            f = IMG_DIR / self.path[7:]
            if f.is_file():
                self._send(f.read_bytes(), "image/png", cache="private, max-age=600")
            else:
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
                    archive(json.loads(raw or b"{}")["name"])
                elif url.path == "/api/undo":
                    undo()
                elif url.path == "/api/keep":   # only records the toggle in the history log
                    on = parse_qs(url.query).get("on", ["0"])[0] == "1"
                    log("keep", "Keep original: on" if on else "Keep original: off")
                elif url.path == "/api/crop":
                    q = parse_qs(url.query)
                    save_crop(q["name"][0], q["label"][0], q.get("keep", ["0"])[0] == "1", raw)
                else:
                    self._send(b"not found", "text/plain", 404)
                    return
            self._send(b"{}")
        except Exception as e:
            with LOCK:
                log("error", "Action failed", f"{type(e).__name__}: {e}")
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