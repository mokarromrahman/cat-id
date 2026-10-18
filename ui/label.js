// Shared by label.py (Mac sorter) and app.py (/label on the server).
// The labels, title and whether to show "Retrain" come from GET /api/config.
let LABELS=[],CFG={};
let queue=[],busy=false,rot=0,sel=null,drag=null,scale=1,keep=false,current=null,img=null;
const cv=document.getElementById('view'),ctx=cv.getContext('2d');
const url=r=>'/img/'+r.split('/').map(encodeURIComponent).join('/');
const $=id=>document.getElementById(id);

// ---------- feedback helpers ----------
const COLORS={Litten:'#d62828',Shinx:'#f4c20d',neither:'#9a9a9a',both:'#7b4bb5'};
const EXTRA=['#2a9d8f','#e76f51','#4d908e','#9b5de5'];   // for any other class folder
const KIND_COLORS={skip:'#bdbdbd',done:'#6fcf97',undo:'#ff9f1c',keep:'#d4af37',error:'#ff4d4d',retrain:'#4ea1ff',delete:'#c0392b'};
let BTN=[];   // BTN[i] is the button for LABELS[i]
const colorOf=l=>COLORS[l]||EXTRA[Math.max(0,LABELS.indexOf(l))%EXTRA.length];
const accent=e=>(e.label&&colorOf(e.label))||KIND_COLORS[e.kind]||'#888';
function restart(el,cls){el.classList.remove(cls);void el.offsetWidth;el.classList.add(cls);}
function ring(target){const b=typeof target==='string'?document.querySelector(target):target;if(b)restart(b,'ring');}   // ring flash on the button
function pflash(color){cv.style.setProperty('--fc',color);restart(cv,'pflash');}       // colour flash around the photo
document.addEventListener('animationend',e=>e.target.classList.remove('ring','pflash','bump'));

// one span per counter so only the one that changed bumps
const cntEl=$('cnt');let prevCounts=null;

// history panel: read-only, newest at the bottom like a chat
let histCount=0,lastId=null,pulling=Promise.resolve();
function addMsg(e){
  const list=$('hlist');
  const stick=list.scrollHeight-list.scrollTop-list.clientHeight<60;   // only follow if already at the bottom
  const empty=list.querySelector('.empty');if(empty)empty.remove();
  const m=document.createElement('div');m.className='msg';m.style.setProperty('--ac',accent(e));
  const row=document.createElement('div');row.className='row';
  const b=document.createElement('b');b.textContent=e.title;
  const tm=document.createElement('time');tm.textContent=e.t;
  row.append(b,tm);m.append(row);
  if(e.detail){const d=document.createElement('div');d.className='d';d.textContent=e.detail;m.append(d);}
  list.append(m);
  $('hcount').textContent=(++histCount)+(histCount===1?' action':' actions');
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

// History starts open on a wide screen and closed on a phone, then remembers your choice.
let histOn=!matchMedia('(max-width:760px)').matches;
try{const s=localStorage.getItem('hist');if(s!==null)histOn=s!=='0';}catch(_){}
function renderHist(){
  $('hist').classList.toggle('hide',!histOn);
  $('histbtn').setAttribute('aria-pressed',String(histOn));
  if(histOn){const l=$('hlist');l.scrollTop=l.scrollHeight;}
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
  const st=$('stage'),[rw,rh]=rotSize();
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
new ResizeObserver(()=>draw()).observe($('stage'));   // also fires when the history panel opens or closes

function hint(){
  const n=current||'';
  $('name').textContent=n?(n+'  ·  '+(sel
    ?'crop selected: press a label to save just the crop'+(keep?' (photo stays for another crop)':' (then the photo is archived)')
    :'drag to crop · rotate with ↺ ↻ or ← →')):'All sorted. You can close this tab.';
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
  $('left').textContent=s.remaining+' left';
  LABELS.forEach(l=>{
    const el=$('c_'+l),txt=l+' '+(s.counts[l]||0);
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
  catch(err){$('name').textContent='Lost contact with the server. Is it still running?';pflash(KIND_COLORS.error);}
  finally{busy=false;}
}
function lab(i){
  if(!current||!img||i>=LABELS.length)return;
  run(async()=>{
    ring(BTN[i]);pflash(colorOf(LABELS[i]));                       // instant feedback, for clicks and keys alike
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
function trash(){   // server only: delete the photo for good (Undo brings it back this session)
  if(current)run(()=>{ring('#delbtn');pflash(KIND_COLORS.delete);return fetch('/api/delete',{method:'POST',body:JSON.stringify({name:current})});});
}
function rotate(dir){
  if(!img)return;
  rot=(rot+(dir>0?90:270))%360;sel=null;draw();hint();ring(dir>0?'#rotr':'#rotl');
}

// Server only: retrain on data/ and reload the model. Takes a while, so the button
// shows progress; the result lands in History (see app.py).
async function retrain(){
  const b=$('retrain');if(b.disabled)return;
  b.disabled=true;b.textContent='Retraining…';
  const req=fetch('/api/retrain',{method:'POST'});
  setTimeout(()=>pullLog().catch(()=>{}),600);   // shows "Retraining started" while it runs
  try{await req;}catch(_){}
  b.disabled=false;b.textContent='Retrain';
  try{await pullLog();}catch(_){}
}

document.addEventListener('keydown',e=>{
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  if(e.key.length===1&&e.key>='1'&&e.key<='9')lab(+e.key-1);
  else if(e.key==='u'||e.key==='z')undo();
  else if(e.key===' '){e.preventDefault();done();}
  else if(e.key==='Escape'){sel=null;draw();hint();}
  else if(e.key==='Delete'||e.key==='Backspace'){if(CFG.delete){e.preventDefault();trash();}}
  else if(e.key==='k')toggleKeep();
  else if(e.key==='h')toggleHist();
  else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();rotate(e.key==='ArrowRight'?1:-1);}
});

function renderKeep(){
  const b=$('keepbtn');
  b.classList.toggle('on',keep);
  b.setAttribute('aria-pressed',String(keep));
  b.querySelector('.tip').innerHTML=(keep?'Keep original':"Don't keep")+'<small>K</small>';
}
function toggleKeep(){
  keep=!keep;renderKeep();hint();ring('#keepbtn');
  fetch('/api/keep?on='+(keep?1:0),{method:'POST'}).then(pullLog).catch(()=>{});   // so the toggle shows in the history
}

// If a button's artwork is missing from img_src/, show its label permanently instead.
function checkArt(b){
  (b.dataset.img||'').split(' ').filter(Boolean).forEach(n=>{
    const t=new Image();t.onerror=()=>b.classList.add('noimg');t.src='/asset/'+n;
  });
}

// ---------- start up: ask the server which labels exist, build the buttons ----------
async function init(){
  try{CFG=await (await fetch('/api/config')).json();}
  catch(_){$('name').textContent='Lost contact with the server. Is it still running?';return;}
  LABELS=CFG.labels;
  document.title=CFG.title||document.title;
  if(CFG.retrain)$('retrain').hidden=false;
  if(CFG.delete)$('delbtn').hidden=false;

  LABELS.forEach((l,i)=>{
    if(i)cntEl.append(' · ');
    const s=document.createElement('span');s.id='c_'+l;s.style.setProperty('--ac',colorOf(l));s.textContent=l+' 0';cntEl.append(s);
  });

  const bar=$('bar'),first=bar.firstElementChild;
  BTN=LABELS.map((l,i)=>{
    const b=document.createElement('button');
    b.className='lbl';b.dataset.label=l;b.setAttribute('aria-label',l);
    if(!COLORS[l])b.style.backgroundColor=colorOf(l);    // no preset colour/artwork for this class
    const art={Litten:'litten_pokemon.png',Shinx:'shinx_pokemon.png',neither:'neither.png',both:'both.png'}[l];
    if(art)b.dataset.img=art;else b.classList.add('noimg');
    const tip=document.createElement('span');tip.className='tip';tip.textContent=l;
    if(i<9){const k=document.createElement('small');k.textContent=String(i+1);tip.append(k);}
    b.append(tip);
    b.addEventListener('mousedown',e=>e.preventDefault());
    b.addEventListener('click',()=>lab(i));
    bar.insertBefore(b,first);
    return b;
  });
  document.querySelectorAll('#bar button[data-img]').forEach(checkArt);

  renderKeep();
  renderHist();
  refresh().catch(()=>{$('name').textContent='Lost contact with the server. Is it still running?';});
}
init();
