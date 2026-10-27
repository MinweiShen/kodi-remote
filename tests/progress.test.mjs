import test from 'node:test';
import assert from 'node:assert/strict';

// Exercise the real page handlers with a delayed Kodi response and a manual animation clock.
class Element extends EventTarget {
  value='0'; disabled=false; hidden=false; dataset={}; style={setProperty(){}};
  classList={toggle(){}};
  setAttribute(){} replaceChildren(){} add(){} focus(){} blur(){}
  setPointerCapture(){} releasePointerCapture(){} hasPointerCapture(){return true;}
  getBoundingClientRect(){return {left:20,width:320};}
}
function emit(target,type,props={}) {
  const event=new Event(type,{cancelable:true});
  Object.assign(event,props); target.dispatchEvent(event);
}

test('seek bar interactions through the real page handlers',async t=>{
  const elements=new Map(), frames=[];
  const element=selector=>{if(!elements.has(selector))elements.set(selector,new Element());return elements.get(selector);};
  const document=Object.assign(new EventTarget(),{hidden:false,querySelector:element,querySelectorAll:()=>[],documentElement:element('html')});
  const window=Object.assign(new EventTarget(),{innerHeight:812});
  const state={online:true,active:true,generation:'video-1',duration:1000,time:100,speed:0,canseek:true};
  let socket;
  class Socket extends EventTarget {
    static OPEN=1; readyState=1; bufferedAmount=0; sent=[];
    constructor(){super();socket=this;}
    send(data){this.sent.push(JSON.parse(data));}
  }
  const originals=new Map(), realSetTimeout=globalThis.setTimeout;
  const globals={document,window,WebSocket:Socket,Option:class{},location:{protocol:'http:',host:'localhost',hash:''},
    localStorage:{getItem:()=>null},fetch:async()=>({ok:true,json:async()=>state}),
    setTimeout:(fn,delay)=>{const timer=realSetTimeout(fn,delay);timer.unref();return timer;},
    requestAnimationFrame:fn=>{frames.push(fn);return frames.length;},cancelAnimationFrame(){}};
  for(const [key,value] of Object.entries(globals)){originals.set(key,Object.getOwnPropertyDescriptor(globalThis,key));Object.defineProperty(globalThis,key,{configurable:true,writable:true,value});}
  try {
    await import('../kodi_remote/web/app.js?seek-regression');
    await new Promise(resolve=>setImmediate(resolve));
    emit(socket,'message',{data:JSON.stringify({type:'state',control:true,state})});
    const progress=element('#progress');
    const pointer=(type,x=253,extra={})=>emit(progress,type,{pointerId:1,clientX:x,button:0,isPrimary:true,...extra});
    const tick=()=>frames.shift()();
    const seeks=()=>socket.sent.filter(message=>message.action==='seek_to');
    const publish=patch=>emit(socket,'message',{data:JSON.stringify({type:'state',control:true,state:{...state,...patch}})});
    const acknowledge=async()=>{
      for(const message of seeks())emit(socket,'message',{data:JSON.stringify({type:'result',id:message.id,ok:true})});
      await new Promise(resolve=>setImmediate(resolve));
    };
    await t.test('release holds the preview through stale polls until Kodi confirms the position',async()=>{
      pointer('pointerdown');progress.value='750';emit(progress,'input');emit(progress,'change');
      pointer('pointerup');tick();
      assert.equal(Number(progress.value),750,'the old playback clock must not pull the slider back after release');
      assert.equal(seeks().length,1);assert.equal(seeks()[0].seconds,750);
      await acknowledge();publish({time:100});tick();
      assert.equal(Number(progress.value),750,'an old poll after the command reply must not pull the slider back');
      publish({time:749});tick();assert.equal(Number(progress.value),749);
    });
    await t.test('the whole track previews immediately and dragging commits only once',async()=>{
      const count=seeks().length;
      pointer('pointerdown',34);assert.equal(Number(progress.value),0);
      pointer('pointermove',180);publish({time:100});tick();
      assert.equal(Number(progress.value),500,'incoming playback state must not interrupt dragging');
      assert.equal(seeks().length,count,'moving must not send intermediate jumps');
      pointer('pointermove',500);assert.equal(Number(progress.value),1000);
      pointer('pointerup',500);emit(progress,'change');
      assert.equal(seeks().length,count+1);assert.equal(seeks().at(-1).seconds,1000);
      await acknowledge();
    });
    await t.test('cancelled touches and a changed video never submit a seek',()=>{
      const count=seeks().length;
      pointer('pointerdown');pointer('pointercancel');pointer('pointerup');
      assert.equal(seeks().length,count);
      pointer('pointerdown');publish({generation:'video-2'});pointer('pointerup');
      assert.equal(seeks().length,count);
    });
    await t.test('native keyboard and accessibility changes still seek',async()=>{
      publish({});progress.value='300';emit(progress,'input');emit(progress,'change');tick();
      assert.equal(Number(progress.value),300);assert.equal(seeks().at(-1).seconds,300);
      await acknowledge();
    });
    await t.test('a rejected jump releases the preview and returns to actual playback time',async()=>{
      pointer('pointerdown');pointer('pointerup');
      const seek=seeks().at(-1);
      emit(socket,'message',{data:JSON.stringify({type:'result',id:seek.id,ok:false,error:'test rejection'})});
      await new Promise(resolve=>setImmediate(resolve));tick();
      assert.equal(Number(progress.value),100);
    });
  } finally {
    for(const message of socket?.sent||[])if(message.id)emit(socket,'message',{data:JSON.stringify({type:'result',id:message.id,ok:true})});
    await new Promise(resolve=>setImmediate(resolve));
    for(const [key,descriptor] of originals){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}
  }
});
