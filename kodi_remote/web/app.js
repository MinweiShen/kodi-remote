import {formatTime, position, tapButton} from './core.js';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
let socket, state = {online:false, active:false}, control = false, receivedAt = performance.now();
let requestId = 0, retryTimer, toastTimer, draggingProgress = false, progressGeneration, sendingText = false;
let connecting = false, connectionVersion = 0;
let progressCancelled = false;
let menuOpen = false, dragLocked = false, samples = [], frame = 0, gesture = null, wheel = 0;
const pointers = new Map(), pending = new Map();
const store = {get(key, fallback) {try{return localStorage.getItem(key) ?? fallback;}catch{return fallback;}},
  set(key, value){try{localStorage.setItem(key,value);}catch{}}};
let sensitivity = Math.min(8,Math.max(1, Number(store.get('sensitivity',3)) || 3));
let acceleration = store.get('acceleration','true') === 'true';
let tab = store.get('menu-tab','playback');
if(tab==='navigation')tab='mouse';
if (!['playback','mouse','input','settings'].includes(tab)) tab = 'playback';

function toast(text, error=false) {
  $('#toast').textContent = text; $('#toast').classList.toggle('error',error); $('#toast').hidden=false;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>{$('#toast').hidden=true;}, error?6500:2200);
}
function ready() {return socket?.readyState === WebSocket.OPEN;}
function fire(action, data={}) {
  if (!ready() || (!control && action!=='takeover' && action!=='heartbeat')) return false;
  if (socket.bufferedAmount > 32768) {socket.close(); return false;}
  socket.send(JSON.stringify({action, ...data, generation:state.generation})); return true;
}
function command(action, data={}) {
  if (!ready() || (!control && action!=='takeover')) return Promise.reject(new Error('尚未连接，或请先接管控制'));
  const id=++requestId;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error('操作响应超时，请核对电视；不会自动重发'));},12000);
    pending.set(id,{resolve,reject,timer});
    socket.send(JSON.stringify({action, ...data, generation:state.generation, id}));
  });
}
async function act(action,data={}) {
  try {const result=await command(action,data); if(result.reason!==undefined) showChoices(result); else if(result.message) toast(result.message); return result;}
  catch(error){toast(error.message,true); return null;}
}
function flush() {
  if(frame) cancelAnimationFrame(frame); frame=0;
  if(samples.length) {fire('move',{samples});samples=[];}
}
function release() {
  flush(); fire('release'); pointers.clear(); gesture=null; dragLocked=false; wheel=0;
  $('#drag-indicator').hidden=true;
  $('#drag-toggle').textContent='锁定拖拽';$('#drag-toggle').setAttribute('aria-pressed','false');
}
function preferences(){fire('preferences',{sensitivity,acceleration});}
function selectTab(name) {
  release();
  tab=name;store.set('menu-tab',name);
  $$('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===name)));
  $$('[data-panel]').forEach(p=>p.hidden=p.dataset.panel!==name);
  $('.menu-content').scrollTop=0;
  $('.menu-content').classList.toggle('mouse-mode',name==='mouse');
}
function openMenu(open) {
  release(); menuOpen=open; $('#menu').hidden=!open;
  $('#main-navigation').inert=open;
  $('#menu-toggle').setAttribute('aria-expanded',String(open));
  $('#menu-toggle').setAttribute('aria-label',open?'关闭操作菜单':'打开操作菜单');
  if(open){selectTab(tab);$('#menu-close').focus({preventScroll:true});}
  else $('#menu-toggle').focus({preventScroll:true});
}
$('#menu-toggle').addEventListener('click',()=>openMenu(!menuOpen));
$('#menu-close').addEventListener('click',()=>openMenu(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menuOpen)openMenu(false);});
$$('[data-tab]').forEach(b=>b.addEventListener('click',()=>selectTab(b.dataset.tab)));

function trackOptions(selector, tracks, current, empty) {
  const select=$(selector), signature=JSON.stringify([tracks,current]);
  if(select.dataset.signature===signature)return;
  select.dataset.signature=signature;select.replaceChildren();
  if(!tracks.length){const o=new Option(empty,'');select.add(o);}
  for(const track of tracks){const label=[track.language,track.name].filter(Boolean).join(' · ')||`轨道 ${track.index+1}`;select.add(new Option(label,String(track.index)));}
  select.value=String(current);
}
function render(next) {
  const oldActive=state.active, oldGeneration=state.generation;
  state=next;receivedAt=performance.now();
  if(oldActive!==state.active || oldGeneration!==state.generation) {
    if(draggingProgress)progressCancelled=true;
    release();draggingProgress=false;$('#episode-choices').hidden=true;
  }
  const online=ready()&&state.online;
  $('#connection').textContent=!ready()?'已断线':state.demo?'演示 · 模拟 Kodi':!state.online?'Kodi 不可用':!control?'其他设备控制中':state.active?(state.speed===0?'已暂停':'正在播放'):'已连接';
  if(online&&state.input?.type==='keyboard')$('#connection').textContent=state.demo?'演示 · 等待文字输入':'等待文字输入';
  $('#now-playing').hidden=!(online&&state.active);
  $('#title').textContent=state.title||'';$('#full-title').textContent=state.title||'当前没有播放视频';
  $('#duration').textContent=formatTime(state.duration);
  $('#playback-state').textContent=state.speed===0?'暂停':'';
  const seekable=online&&control&&state.active&&state.canseek&&state.duration>0;
  $('#progress').disabled=!seekable;
  if(!draggingProgress)$('#progress').max=String(state.duration||1);
  $$('[data-player]').forEach(b=>b.disabled=!(online&&control&&state.active));
  $$('[data-seekable]').forEach(b=>b.disabled=!seekable);
  $$('[data-nav],[data-mouse],[data-volume],[data-action="mute"]').forEach(b=>b.disabled=!(online&&control));
  $('#playpause').textContent=state.speed===0?'继续播放':'暂停播放';
  $('#seek-note').hidden=seekable||!state.active;
  $('#seek-note').textContent='当前视频暂不支持跳转';
  $('#mute').textContent=state.muted?'取消静音':'静音';
  $('#volume-note').textContent=`Kodi 音量 ${state.volume??'—'}% · 音频直通时请用电视或功放调节`;
  $('#subtitle-enabled').checked=!!state.subtitleenabled;
  $('#subtitle-enabled').disabled=!(online&&control&&state.active&&state.subtitles?.length);
  trackOptions('#subtitle-track',state.subtitles||[],state.subtitle,'没有字幕');
  trackOptions('#audio-track',state.audio||[],state.audiostream,'没有音轨');
  $('#subtitle-track').disabled=!(online&&control&&state.active&&state.subtitles?.length);
  $('#audio-track').disabled=!(online&&control&&state.active&&state.audio?.length);
  $('#input-target').textContent=state.input?`Kodi 输入目标：${state.input.title}`:'请在 Kodi 中重新打开搜索或文字输入框，以确认输入目标。';
  $('#send-text').disabled=sendingText||!(online&&control&&state.input?.type==='keyboard');
  $('#control-status').textContent=!ready()?'已断线':!state.online?'遥控服务在线 · Kodi 未连接':control?'当前设备正在控制':'另一设备正在控制';
  $('#takeover').hidden=control||!ready();$('#demo-note').hidden=!state.demo;
  $('#drag-toggle').disabled=!(online&&control);
  $('#touchpad').classList.toggle('unavailable',!(online&&control));
}
function animateProgress() {
  if(state.active&&!draggingProgress){const value=position(state,receivedAt,performance.now());$('#progress').value=String(value);$('#elapsed').textContent=formatTime(value);}
  requestAnimationFrame(animateProgress);
}
requestAnimationFrame(animateProgress);

async function connect() {
  if(connecting || ready())return;
  connecting=true;const version=++connectionVersion;
  clearTimeout(retryTimer);
  try {const response=await fetch('/api/state');if(response.status===401){$('#login').hidden=false;return;}if(!response.ok)throw new Error('服务不可用');render(await response.json());}
  catch {toast('无法连接遥控服务',true);retryTimer=setTimeout(connect,2500);return;}
  finally {connecting=false;}
  if(document.hidden)return;
  if(version!==connectionVersion){connect();return;}
  $('#login').hidden=true;
  const ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);
  socket=ws;
  let ownHeartbeat;
  ws.addEventListener('open',()=>{ownHeartbeat=setInterval(()=>fire('heartbeat'),4000);});
  ws.addEventListener('message',event=>{
    let msg;try{msg=JSON.parse(event.data);}catch{return;}
    if(msg.type==='state') {const previous=control;control=msg.control;render(msg.state);if(control&&!previous)preferences();}
    else if(msg.type==='revoked'){control=false;release();render(state);toast('控制已由另一设备接管',true);}
    else if(msg.type==='result') {
      const p=pending.get(msg.id);
      if(p){clearTimeout(p.timer);pending.delete(msg.id);msg.ok?p.resolve(msg):p.reject(new Error(msg.error));}
      else if(!msg.ok)toast(msg.error,true);
    }
  });
  ws.addEventListener('close',()=>{
    clearInterval(ownHeartbeat);
    if(socket!==ws)return;
    control=false;pointers.clear();samples=[];gesture=null;dragLocked=false;
    $('#drag-indicator').hidden=true;
    $('#drag-toggle').textContent='锁定拖拽';$('#drag-toggle').setAttribute('aria-pressed','false');
    for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('连接已断开，请核对电视；操作不会自动重发'));}pending.clear();
    render({...state,online:false});if(!document.hidden)retryTimer=setTimeout(connect,2000);
  });
}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;try{
  const response=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({secret:$('#secret').value})});
  if(!response.ok)throw new Error(await response.text());$('#secret').value='';$('#login-error').textContent='';await connect();
}catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;}});
$('#reconnect').addEventListener('click',()=>{release();if(socket)socket.close();else connect();});
$('#takeover').addEventListener('click',()=>act('takeover'));
document.addEventListener('visibilitychange',()=>{if(document.hidden){++connectionVersion;release();clearTimeout(retryTimer);socket?.close();}else connect();});
window.addEventListener('pagehide',()=>{release();socket?.close();});
function viewport(){document.documentElement.style.setProperty('--viewport-height',`${window.visualViewport?.height||window.innerHeight}px`);}
window.visualViewport?.addEventListener('resize',()=>{release();viewport();});window.addEventListener('resize',()=>{release();viewport();});viewport();

$$('[data-action]').forEach(b=>b.addEventListener('click',()=>act(b.dataset.action)));
$$('[data-seek]').forEach(b=>b.addEventListener('click',()=>act('seek',{seconds:Number(b.dataset.seek)})));
$$('[data-volume]').forEach(b=>b.addEventListener('click',()=>act('volume',{delta:Number(b.dataset.volume)})));
$$('[data-nav]').forEach(b=>b.addEventListener('click',()=>act('nav',{key:b.dataset.nav})));
$$('[data-click]').forEach(b=>b.addEventListener('click',()=>{release();act('click',{button:b.dataset.click});}));
$$('[data-episode]').forEach(b=>b.addEventListener('click',()=>act('episode',{direction:Number(b.dataset.episode)})));
function showChoices(result) {
  $('#episode-choices').hidden=false;$('#episode-reason').textContent=result.reason;
  $('#episode-list').replaceChildren();
  for(const choice of result.choices){const button=document.createElement('button');button.textContent=choice.name;button.addEventListener('click',()=>act('choose_episode',{choice:choice.id}));$('#episode-list').append(button);}
  $('#episode-choices').scrollIntoView({block:'nearest'});
}
$('#subtitle-enabled').addEventListener('change',()=>act('subtitle',{index:$('#subtitle-enabled').checked?'on':'off'}));
$('#subtitle-track').addEventListener('change',()=>act('subtitle',{index:Number($('#subtitle-track').value)}));
$('#audio-track').addEventListener('change',()=>act('audio',{index:Number($('#audio-track').value)}));
let composing=false;
$('#text').addEventListener('compositionstart',()=>{composing=true;});$('#text').addEventListener('compositionend',()=>{composing=false;});
$('#text-form').addEventListener('submit',async e=>{e.preventDefault();if(composing){toast('请先完成输入法选字');return;}
  if(sendingText)return;sendingText=true;
  const text=$('#text').value;$('#send-text').disabled=true;const result=await act('text',{text,input_id:state.input?.id});if(result&&$('#text').value===text)$('#text').value='';sendingText=false;$('#text').blur();render(state);
});
$('#sensitivity').value=String(sensitivity);$('#sensitivity-value').textContent=sensitivity.toFixed(2);$('#acceleration').checked=acceleration;
$('#sensitivity').addEventListener('input',()=>{sensitivity=Number($('#sensitivity').value);$('#sensitivity-value').textContent=sensitivity.toFixed(2);store.set('sensitivity',sensitivity);preferences();});
$('#acceleration').addEventListener('change',()=>{acceleration=$('#acceleration').checked;store.set('acceleration',acceleration);preferences();});
$('#drag-toggle').addEventListener('click',()=>{
  if(dragLocked){release();return;}
  flush();dragLocked=true;fire('button',{button:'left',down:true});$('#drag-indicator').hidden=false;
  $('#drag-toggle').textContent='释放拖拽';$('#drag-toggle').setAttribute('aria-pressed','true');
});

const progress=$('#progress');
progress.addEventListener('pointerdown',()=>{progressCancelled=false;draggingProgress=true;progressGeneration=state.generation;release();});
progress.addEventListener('keydown',()=>{progressCancelled=false;progressGeneration=state.generation;});
progress.addEventListener('input',()=>{draggingProgress=true;$('#elapsed').textContent=formatTime(Number(progress.value));});
progress.addEventListener('change',()=>{const value=Number(progress.value);draggingProgress=false;if(progressCancelled||(progressGeneration!==undefined&&progressGeneration!==state.generation))return;act('seek_to',{seconds:value});});
progress.addEventListener('pointercancel',()=>{draggingProgress=false;});
progress.addEventListener('pointerup',()=>setTimeout(()=>{draggingProgress=false;progressGeneration=undefined;},0));

const pad=$('#touchpad');
pad.addEventListener('contextmenu',e=>e.preventDefault());
pad.addEventListener('pointerdown',e=>{
  if(!menuOpen||tab!=='mouse'||!control||!state.online)return;
  e.preventDefault();pad.setPointerCapture(e.pointerId);
  if(pointers.size===0){gesture={started:performance.now(),distance:0,maxFingers:1,cancelled:false,drag:dragLocked};wheel=0;}
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,t:e.timeStamp});
  if(gesture){gesture.maxFingers=Math.max(gesture.maxFingers,pointers.size);if(pointers.size>2)gesture.cancelled=true;}
});
pad.addEventListener('pointermove',e=>{
  const previous=pointers.get(e.pointerId);if(!previous||!gesture||!menuOpen||tab!=='mouse')return;
  e.preventDefault();const dx=e.clientX-previous.x,dy=e.clientY-previous.y,dt=Math.max(1,Math.min(100,e.timeStamp-previous.t));
  pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,t:e.timeStamp});gesture.distance+=Math.hypot(dx,dy);
  if(gesture.cancelled)return;
  if(gesture.maxFingers===1){samples.push([dx,dy,dt]);if(samples.length>=64)flush();else if(!frame)frame=requestAnimationFrame(flush);}
  else if(pointers.size===2){flush();wheel+=dy/48;const steps=Math.trunc(wheel);if(steps){fire('scroll',{steps:Math.max(-20,Math.min(20,steps))});wheel-=steps;}}
});
function endPointer(e,cancelled=false){
  if(!pointers.has(e.pointerId))return;
  e.preventDefault();pointers.delete(e.pointerId);if(cancelled&&gesture)gesture.cancelled=true;
  if(pointers.size===0){flush();const button=tapButton(gesture,performance.now());if(button)fire('click',{button});fire('gesture_end');gesture=null;wheel=0;if(cancelled)release();}
}
pad.addEventListener('pointerup',e=>endPointer(e));pad.addEventListener('pointercancel',e=>endPointer(e,true));
pad.addEventListener('lostpointercapture',e=>{if(pointers.has(e.pointerId))release();});

// A fragment is accepted for setup, then removed immediately; secrets never enter query strings.
const fragment=decodeURIComponent(location.hash.slice(1));if(fragment){history.replaceState(null,'',location.pathname);$('#secret').value=fragment;}
selectTab(tab);connect();
