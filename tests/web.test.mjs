import test from 'node:test';
import assert from 'node:assert/strict';
import {formatTime,position,tapButton} from '../kodi_remote/web/core.js';

test('playback clock stops when paused and clamps to duration',()=>{
  assert.equal(position({active:true,time:10,duration:20,speed:1},1000,4000),13);
  assert.equal(position({active:true,time:10,duration:20,speed:0},1000,4000),10);
  assert.equal(position({active:true,time:19,duration:20,speed:1},1000,4000),20);
  assert.equal(formatTime(6120),'01:42:00');
});
test('two finger tap is right click; scrolling, drags, cancelled gestures never click',()=>{
  const g={started:100,distance:2,maxFingers:2,cancelled:false,drag:false};
  assert.equal(tapButton(g,200),'right');
  assert.equal(tapButton({...g,distance:20},200),null);
  assert.equal(tapButton({...g,drag:true},200),null);
  assert.equal(tapButton({...g,cancelled:true},200),null);
  assert.equal(tapButton(g,600),null);
});
