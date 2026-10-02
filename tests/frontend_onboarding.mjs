// Execute the real component without a browser/network. Native dialog layout is
// separately verified in Chromium; this harness checks event/state/audio lifecycles.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../ui/onboarding/frontend/onboarding.js', import.meta.url), 'utf8');
const module = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const scenario = process.argv[2];
const allVideos = [], rafs = new Map();
class Element {
  get textContent() { return this.children.length ? this.children.map(child => child.textContent).join('') : this.text; }
  set textContent(value) { this.text=value; this.children=[]; }
  replaceChildren(...children) { this.text=''; this.children=children; }
  constructor() {
    this.listeners = new Map(); this.dataset = {}; this.open = false; this.textContent = '';
    this.classes = new Set(); this.attributes = {};
    this.style = { properties: {}, setProperty: (key, value) => { this.style.properties[key] = value; } };
    this.classList = { add: (...keys) => keys.forEach(key => this.classes.add(key)), remove: (...keys) => keys.forEach(key => this.classes.delete(key)) };
  }
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(fn); }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  setAttribute(name, value) { this.attributes[name] = value; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  focus() {}
  fire(type, extra = {}) {
    const event = { isTrusted: true, key: 'Enter', code: 'Enter', isPrimary: true, button: 0,
      preventDefault() {}, stopPropagation() {}, composedPath: () => [this], ...extra };
    for (const fn of this.listeners.get(type) || []) fn(event);
  }
}
class Video extends Element {
  constructor() { super(); this.readyState=4; this.playCalls=0; this.pauseCalls=0; this.paused=true; this.seeking=false; this._time=0; this.duration=6.041667; this.seeks=[]; allVideos.push(this); }
  get currentTime() { return this._time; }
  set currentTime(value) { if(scenario==='loop-seek-error' && this.bufferId===1) throw Error('seek failed'); this.seeks.push({time:value,opacity:this.style.opacity}); this._time=value; }
  get ended() { return this.currentTime>=this.duration; }
  play() { this.playCalls++; this.paused=false; return scenario==='video-blocked' || (scenario==='loop-reject' && this.bufferId===1) ? Promise.reject(Error('blocked')) : Promise.resolve(); }
  pause() { this.pauseCalls++; this.paused=true; }
}
const doc = new Element();
doc.createElement = () => new Element();
doc.createTextNode = textContent => ({ textContent });
const flags = new Map();
const storage = { getItem: key => flags.get(key) ?? null, setItem: (key, value) => flags.set(key, value), removeItem: key => flags.delete(key) };
const timers = new Map();
let now = 0, timerId = 0, audioCreated = 0;
const frequencies = [];
class Audio {
  constructor() { audioCreated++; this.state = 'suspended'; this.currentTime = 0; }
  resume() { this.state = 'running'; return Promise.resolve(); }
  close() { this.state = 'closed'; return Promise.resolve(); }
  createOscillator() { return { frequency: { value: 0 }, connect() {}, disconnect() {}, start() { frequencies.push(this.frequency.value); }, stop() {} }; }
  createGain() { return { gain: { setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, disconnect() {} }; }
}
globalThis.document = doc;
globalThis.window = { localStorage: storage, AudioContext: Audio,
  matchMedia: () => ({ matches: scenario.startsWith('reduced') }),
  setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay, at: now + delay }); return timerId; },
  clearTimeout: id => timers.delete(id),
  requestAnimationFrame: fn => { rafs.set(++timerId,{fn,at:now+16}); return timerId; },
  cancelAnimationFrame: id => rafs.delete(id),
};
Object.defineProperty(globalThis, 'navigator', { value: { maxTouchPoints: scenario === 'touch' ? 1 : 0 }, configurable: true });
Object.defineProperty(globalThis, 'performance', { value: { now: () => now }, configurable: true });
const reports = [];
function mount(replay = null, session = 'test-session', messages = ['一','二','三','四','五','六']) {
  const elements = Object.fromEntries(['intro', 'sentence', 'hint', 'mascot', 'leaf', 'mute', 'skip', 'video-buffers'].map(key => [key, new Element()]));
  const videos = [new Video(),new Video()]; elements['thinking-video']=videos[0]; elements.videos=videos;
  videos.forEach((video,index)=>{video.bufferId=index;});
  if(scenario==='loop-delayed' || scenario==='loop-stalled') videos[1].readyState=0;
  if(scenario==='video-loading') elements['thinking-video'].readyState=0;
  const cleanup = module.default({ parentElement: { querySelector: selector => elements[selector.slice(1)], querySelectorAll: () => videos },
    data: { messages, replay_token: replay, presentation_session:session }, setStateValue: (key, value) => reports.push([key, value]) });
  return { ...elements, cleanup };
}
function move(ms) {
  const end = now + ms;
  function progress(to) { const seconds=(to-now)/1000; allVideos.filter(v=>!v.paused).forEach(v=>{v._time=Math.min(v.duration,v._time+seconds*v.playbackRate);}); now=to; }
  while (true) {
    const next = [...timers,...rafs].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
    if (!next) break;
    const [id, timer] = next; timers.delete(id); rafs.delete(id); progress(timer.at); timer.fn();
  }
  progress(end);
}
function flush() { while (timers.size) move(Math.max(...[...timers.values()].map(timer => timer.at)) - now); }
async function drift(ms) { for(let elapsed=0;elapsed<ms;) { const step=Math.min(16,ms-elapsed); move(step); elapsed+=step; await Promise.resolve(); } }
function key(key = 'Enter', extra = {}) { doc.fire('keydown', { key, code: key, ...extra }); doc.fire('keyup', { key, code: key }); }
if (scenario === 'pure') {
  for (const key of ['Enter',' ','a','中','ArrowLeft']) assert.equal(module.validAdvanceKey({key}), true);
  for (const key of ['Control','Meta','Alt','Shift','Tab','F1']) assert.equal(module.validAdvanceKey({key}), false);
  for (const field of ['repeat','isComposing','ctrlKey','metaKey','altKey','shiftKey']) assert.equal(module.validAdvanceKey({key:'a',[field]:true}), false);
  const state = module.createIntroState();
  assert.equal(module.advanceIntro(state, 0), 'opening');
  assert.equal(module.advanceIntro(state, 20), null);
  assert.equal(state.index, 0);
  assert.equal(state.motion,'RESPOND');
  assert.equal(module.advanceIntro(state, 1000),null); // Locked throughout the visual sequence.
  for (let index=1; index<6; index++) { state.phase='speaking'; assert.equal(module.advanceIntro(state,index*500),'advance'); }
  state.phase='speaking';
  assert.equal(module.advanceIntro(state,3000),'finish');
  assert.equal(module.advanceIntro(state,4000),null);
} else if (scenario === 'blocked-storage') {
  const blocked = { getItem() {throw Error();}, setItem() {throw Error();}, removeItem() {throw Error();} };
  assert.equal(module.readFlag(blocked,module.SEEN_KEY),false);
  module.writeFlag(blocked,module.SEEN_KEY,true);
  module.writeFlag(blocked,module.SEEN_KEY,false);
  Object.defineProperty(window, 'localStorage', { get() { throw Error(); } });
  const view = mount(); assert.equal(view.intro.open,true);
  view.skip.fire('click'); flush(); assert.deepEqual(reports,[['completed',true]]);
} else if (scenario === 'seen') {
  flags.set(module.SEEN_KEY,'1');
  const view=mount(); assert.equal(view.intro.open,false); assert.equal(audioCreated,0);
  view.cleanup(); mount(); assert.equal(reports.length,1);
} else if (scenario === 'replay-reset') {
  flags.set(module.SEEN_KEY,'1'); let view=mount(); assert.equal(view.intro.open,false);
  view.cleanup(); view=mount('request-one'); assert.equal(view.intro.open,true); assert.equal(flags.has(module.SEEN_KEY),false);
  view.skip.fire('click'); flush(); view.cleanup();
  view=mount(null,'after-reset'); assert.equal(view.intro.open,false); assert.equal(flags.get(module.SEEN_KEY),'1');
  assert.equal(reports.length,3); assert.deepEqual(reports.at(-1),['completed',true]);
} else if (scenario === 'rerun') {
  let view=mount(); key(); flush(); await Promise.resolve(); assert.equal(view.sentence.textContent,'一');
  view.cleanup(); view=mount(); assert.equal(view.sentence.textContent,'一'); assert.equal(view.intro.dataset.index,'0');
  assert.equal(audioCreated,1); assert.equal(frequencies.length,2);
} else if (scenario === 'skip' || scenario === 'reduced') {
  const view=mount(); assert.equal(audioCreated,0); view.skip.fire('click');
  assert.equal([...timers.values()][0].delay,180); flush();
  assert.equal(view.intro.open,false); assert.equal(flags.get(module.SEEN_KEY),'1');
  assert.deepEqual(reports,[['completed',true]]); assert.equal(doc.listeners.get('keydown').size,0);
} else if (scenario === 'repeat') {
  const view=mount(); doc.fire('keydown'); flush(); now+=500; doc.fire('keydown',{repeat:true}); doc.fire('keydown');
  assert.equal(view.intro.dataset.index,'0'); doc.fire('keyup'); now+=500; key(); assert.equal(view.intro.dataset.index,'1');
} else if (scenario === 'mute') {
  flags.set(module.MUTED_KEY,'1'); const view=mount(); key(); await Promise.resolve(); assert.equal(audioCreated,0);
  view.mute.fire('pointerup'); assert.equal(view.intro.dataset.index,'0');
  view.mute.fire('click'); assert.equal(flags.has(module.MUTED_KEY),false);
  flush(); key(); await Promise.resolve(); assert.equal(audioCreated,1);
} else if (scenario === 'touch') {
  const view=mount(); view.intro.fire('pointerup',{pointerType:'touch'});
  view.intro.fire('click'); assert.equal(view.intro.dataset.index,'0'); assert.equal(view.hint.textContent,'按任意键或轻触继续');
  now=1000; view.intro.fire('pointerup',{isPrimary:false}); assert.equal(view.intro.dataset.index,'0');
} else if (scenario === 'complete' || scenario === 'reduced-complete') {
  const view=mount(); assert.equal(audioCreated,0);
  for(let index=0;index<6;index++) { key(); flush(); if(scenario.startsWith('reduced')) move(100); await Promise.resolve(); }
  now+=500; key(); await Promise.resolve();
  assert.equal(view.intro.dataset.lastCue,'finish'); assert.equal(audioCreated,1); assert.equal(frequencies.length,10);
  assert.equal([...timers.values()][0].delay,scenario === 'reduced-complete' ? 180 : 1500); assert.equal(view.intro.open,true);
  flush(); assert.equal(view.intro.open,false); assert.deepEqual(reports,[['completed',true]]);
  now=5000; key(); assert.equal(reports.length,1); assert.equal(doc.listeners.get('keydown').size,0);
} else if (scenario === 'transition-order' || scenario === 'reduced-transition') {
  const timing = scenario.startsWith('reduced') ? module.REDUCED_TIMING : module.TIMING;
  const view = mount();
  assert.equal(view.intro.dataset.motion,'THINKING'); assert.equal(view.sentence.textContent,'');
  assert.equal(view.leaf.classes.has('inertia'),false);
  key(); assert.equal(view.sentence.textContent,''); assert.equal(view.intro.dataset.motion,'RESPOND');
  assert.equal(view.leaf.classes.has('inertia'),!scenario.startsWith('reduced'));
  move(timing.respond - 1); assert.equal(view.sentence.textContent,'');
  key('a'); assert.equal(view.intro.dataset.index,'0');
  move(1); assert.equal(view.sentence.textContent,'一'); assert.equal(view.intro.dataset.motion,'SPEAKING');
  assert.equal(view.sentence.classes.has('entering'),true);
  flush(); assert.equal(view.intro.dataset.motion,'THINKING'); assert.equal(view.leaf.classes.has('inertia'),false);
  assert.equal(timers.size,0); move(10000); assert.equal(view.sentence.textContent,'一');
  key(); assert.equal(view.sentence.textContent,'一'); assert.equal(view.sentence.classes.has('exiting'),true);
  move(timing.exit); assert.equal(view.sentence.textContent,timing.pause?'一':'二');
  if(timing.pause) { assert.equal(view.intro.dataset.textPhase,'pause'); move(timing.pause - 1); assert.equal(view.sentence.textContent,'一'); move(1); }
  assert.equal(view.sentence.textContent,'二'); assert.equal(view.sentence.classes.has('exiting'),false);
  flush(); assert.equal(view.intro.dataset.textPhase,'hold');
} else if (scenario === 'long-sentence') {
  const text='我会先了解你，再陪你一起理解岗位、发现值得继续探索的方向。';
  const view=mount(null,'test-session',['你好。','我叫 Orange。','我是你的 AI 职业探索伙伴。',text,'你不需要现在就知道所有答案。','准备好了吗？让我们开始吧。']);
  for(let index=0;index<4;index++) { key(); flush(); }
  assert.equal(view.sentence.textContent,text);
  assert.equal(view.sentence.children.length,3);
  assert.equal(view.sentence.children[1].textContent,'岗位');
  assert.equal(view.sentence.children[1].className,'sentence-word');
  key(); assert.equal(view.sentence.textContent,text); move(module.TIMING.exit + module.TIMING.pause);
  assert.equal(view.sentence.children.length,0); assert.equal(view.sentence.textContent,'你不需要现在就知道所有答案。');
} else if (scenario === 'early-timer') {
  const view=mount(); key(); move(module.TIMING.respond + 1000);
  const [id,timer] = [...timers].sort((a,b) => b[1].at-a[1].at)[0];
  timers.delete(id); now=timer.at-.4; timer.fn();
  assert.equal(view.intro.dataset.motion,'SPEAKING');
  assert.equal(timers.size,1); assert.equal([...timers.values()][0].delay,1);
  move(1); assert.equal(view.intro.dataset.motion,'THINKING'); assert.equal(timers.size,0);
  key(); assert.equal(view.intro.dataset.index,'1');
} else if (scenario === 'rapid-input') {
  const view=mount(); key(); await Promise.resolve();
  for(let index=0;index<10;index++) { move(40); key('a'); view.intro.fire('pointerup'); }
  assert.equal(view.intro.dataset.index,'0'); assert.equal(frequencies.length,2);
  flush(); key(); assert.equal(view.intro.dataset.index,'1');
} else if (scenario === 'leaf-sequence') {
  assert.deepEqual(module.LEAF_DIRECTIONS, [[5,7,4],[-5,7,-4],[1,9,3],[4,-4,-3],[6,6,5],[-6,8,-5]]);
  const view=mount();
  for(let index=0;index<6;index++) {
    key(); assert.equal(view.leaf.dataset.direction,String(index));
    const [x,y,angle] = module.LEAF_DIRECTIONS[index];
    assert.equal(view.leaf.style.properties['--leaf-x'],`${x}px`);
    assert.equal(view.leaf.style.properties['--leaf-y'],`${y}px`);
    assert.equal(view.leaf.style.properties['--leaf-angle'],`${angle}deg`);
    move(module.TIMING.respond); assert.equal(view.leaf.classes.has('inertia'),true);
    move(module.TIMING.leaf-module.TIMING.respond); assert.equal(view.leaf.classes.has('inertia'),false);
    flush(); assert.equal(view.intro.dataset.motion,'THINKING');
  }
  key(); assert.equal(view.intro.dataset.motion,'FINISH');
  assert.equal(view.leaf.style.properties['--leaf-x'],'3.5px');
} else if (scenario.startsWith('rerun-')) {
  let view=mount(); key(); flush(); key();
  const delay = {'rerun-exit':150,'rerun-pause':module.TIMING.exit+100,'rerun-enter':module.TIMING.exit+module.TIMING.pause+230,'rerun-finish':0}[scenario];
  if(scenario==='rerun-finish') {
    flush(); for(let index=2;index<6;index++) { key(); flush(); }
    key(); move(250);
  } else move(delay);
  await Promise.resolve(); const count=frequencies.length;
  const deadline = Math.max(...[...timers.values()].map(timer => timer.at));
  view.cleanup(); assert.equal(timers.size,0); assert.equal(doc.listeners.get('keydown').size,0);
  view=mount(); assert.equal(audioCreated,1); assert.equal(frequencies.length,count);
  if(scenario==='rerun-finish') {
    assert.equal(view.sentence.textContent,'六'); assert.equal(view.intro.dataset.motion,'FINISH');
    assert.equal([...timers.values()][0].delay,1250);
  } else {
    assert.equal(view.sentence.textContent,scenario==='rerun-enter'?'二':'一');
    assert.equal(view.intro.dataset.motion,scenario==='rerun-enter'?'SPEAKING':'RESPOND');
    assert.equal(Math.max(...[...timers.values()].map(timer => timer.at)),deadline);
  }
  flush();
  if(scenario==='rerun-finish') assert.deepEqual(reports,[['completed',true]]);
  else assert.equal(view.intro.dataset.textPhase,'hold');
} else if (scenario === 'skip-transition' || scenario === 'skip-enter') {
  const view=mount(); key(); if(scenario==='skip-enter') move(module.TIMING.respond+100);
  view.skip.fire('click'); assert.equal(timers.size,1); flush();
  assert.equal(view.intro.open,false); assert.equal(timers.size,0); assert.deepEqual(reports,[['completed',true]]);
} else if (scenario === 'replay-direction') {
  let view=mount(); for(let index=0;index<3;index++) { key(); flush(); }
  view.skip.fire('click'); flush(); view.cleanup(); view=mount('fresh-replay'); key();
  assert.equal(view.leaf.dataset.direction,'0'); assert.equal(view.intro.dataset.index,'0');
  assert.equal(view.sentence.textContent,''); assert.equal(view.intro.dataset.motion,'RESPOND');
} else if (scenario === 'cleanup-transition') {
  const view=mount(); key(); assert.ok(timers.size>0);
  view.cleanup(); assert.equal(timers.size,0); assert.equal(doc.listeners.get('keydown').size,0);
  move(5000); assert.deepEqual(reports,[]);
} else if (scenario==='video-properties') {
  const view=mount(); await Promise.resolve();
  for(const video of view.videos) { assert.equal(video.muted,true); assert.equal(video.defaultMuted,true); assert.equal(video.volume,0); assert.equal(video.loop,false); assert.equal(video.playbackRate,.95); }
  assert.equal(view.videos[0].playCalls,1); assert.equal(view.videos[1].playCalls,0);
  assert.equal(view.videos[0].classes.has('decoded'),true); assert.equal(audioCreated,0);
} else if (scenario==='video-blocked') {
  const view=mount(), video=view['thinking-video']; await Promise.resolve(); await Promise.resolve();
  assert.equal(view.intro.dataset.video,'fallback'); assert.equal(view['video-buffers'].classes.has('ready'),false);
  key(); flush(); assert.equal(view.sentence.textContent,'一'); assert.equal(video.playCalls,1);
} else if (scenario==='video-loading') {
  const view=mount(), video=view['thinking-video'];
  assert.equal(video.classes.has('decoded'),false); video.readyState=4; video.fire('loadeddata'); await Promise.resolve();
  assert.equal(video.classes.has('decoded'),true); video.fire('error');
  assert.equal(view.intro.dataset.video,'fallback'); key(); flush(); assert.equal(view.sentence.textContent,'一');
} else if (scenario==='reduced-video') {
  const view=mount(), video=view['thinking-video'];
  assert.equal(video.playCalls,0); assert.ok(video.pauseCalls>0); assert.equal(video.classes.has('decoded'),true);
  assert.equal(view.videos[1].playCalls,0); assert.equal(rafs.size,0);
  assert.equal(video.currentTime,0);
  assert.equal(view.intro.dataset.video,'static'); key(); flush(); assert.equal(now,300);
  assert.equal(view.leaf.classes.has('inertia'),false);
} else if (scenario==='video-hold') {
  const view=mount(); await drift(6500);
  assert.equal(view.intro.dataset.index,'-1'); assert.ok(view.videos.some(v=>!v.paused)); assert.equal(audioCreated,0);
  key(); await drift(2010); await drift(10000); assert.equal(view.sentence.textContent,'一'); assert.ok(view.videos.some(v=>!v.paused));
  key(); await drift(2470); assert.equal(view.intro.dataset.index,'1');
} else if (scenario==='video-cleanup') {
  const view=mount(), video=view['thinking-video']; key(); view.cleanup();
  assert.ok(view.videos.every(v=>v.paused)); assert.equal(rafs.size,0); assert.equal(video.listeners.get('loadeddata').size,0);
  assert.equal(video.listeners.get('error').size,0); assert.equal(timers.size,0);
  video.fire('loadeddata'); assert.deepEqual(reports,[]);
} else if (scenario==='video-finish') {
  const view=mount(), video=view['thinking-video'];
  for(let i=0;i<6;i++) { key(); await drift(i===0?2010:2470); }
  key(); assert.ok(view.videos.some(v=>!v.paused)); await drift(1499); assert.equal(view.intro.open,true);
  await drift(1); assert.equal(view.intro.open,false); assert.ok(view.videos.every(v=>v.paused)); assert.equal(rafs.size,0);
  assert.ok(view.videos.every(v=>[...v.listeners.values()].every(listeners=>listeners.size===0)));
  assert.deepEqual(reports,[['completed',true]]);
} else if (scenario==='video-replay') {
  let view=mount(), video=view['thinking-video']; view.skip.fire('click'); flush(); view.cleanup();
  assert.equal(video.paused,true); view=mount('video-replay');
  assert.equal(view['thinking-video'].playCalls,1); assert.equal(view.intro.dataset.index,'-1');
  assert.equal(audioCreated,0);
} else if (scenario==='lock-2470') {
  const view=mount(); key(); flush(); key(); const start=now;
  for(let i=0;i<24;i++) { move(100); key('a'); view.intro.fire('pointerup'); }
  assert.equal(view.intro.dataset.index,'1'); move(69); key(); assert.equal(view.intro.dataset.index,'1');
  move(1); assert.equal(now-start,2470); assert.equal(view.intro.dataset.textPhase,'hold');
  assert.equal(view.intro.dataset.index,'1'); key(); assert.equal(view.intro.dataset.index,'2');
} else if (scenario==='first-start') {
  const view=mount(); key(); move(559); assert.equal(view.sentence.textContent,'');
  move(1); assert.equal(view.sentence.textContent,'一'); move(1449); key();
  assert.equal(view.intro.dataset.index,'0'); move(1); assert.equal(view.intro.dataset.textPhase,'hold');
  assert.equal(now,2010);
} else if (scenario==='loop-blend') {
  assert.deepEqual(module.seamBlend(0),{incoming:0,outgoing:1});
  assert.deepEqual(module.seamBlend(1),{incoming:1,outgoing:0});
  let previous={incoming:0,outgoing:1}, ghosts=0;
  for(let i=0;i<=1000;i++) {
    const blend=module.seamBlend(i/1000);
    assert.ok(blend.incoming>=previous.incoming && blend.outgoing<=previous.outgoing);
    assert.ok(1-(1-blend.incoming)*(1-blend.outgoing)>.999999);
    if(blend.incoming>.25 && blend.incoming<.75) ghosts++;
    previous=blend;
  }
  assert.ok(ghosts<200); // Not a long 50/50/dim triple exposure.
} else if (scenario==='loop-sustained') {
  const view=mount(); await drift(30000);
  assert.equal(view.intro.dataset.video,'playing'); assert.equal(view.intro.dataset.index,'-1');
  assert.ok(Number(view['video-buffers'].dataset.seams)>=5);
  assert.equal(audioCreated,0); assert.equal(view.leaf.classes.has('inertia'),false);
  assert.deepEqual(view.leaf.style.properties,{});
  assert.ok(view.videos.every(v=>v.seeks.every(seek=>seek.opacity==='0')));
  assert.ok(view.videos.every(v=>v.playbackRate===.95 && v.currentTime<v.duration));
  assert.equal(rafs.size,1); assert.equal(timers.size,0);
} else if (scenario==='loop-timing') {
  const view=mount(); await drift(4700); assert.equal(view.videos[1].playCalls,0);
  await drift(80); assert.equal(view.videos[1].playCalls,1); assert.ok(view.videos[0].currentTime<view.videos[0].duration);
  await drift(1200); assert.equal(view['video-buffers'].dataset.seams,'1');
  assert.equal(view.videos[0].paused,true); assert.equal(view.videos[0].currentTime,.5);
  assert.equal(view.videos[0].style.opacity,'0'); assert.equal(view.videos[1].style.opacity,'1');
  await drift(4200); assert.equal(view['video-buffers'].dataset.seams,'2');
  assert.equal(view['video-buffers'].dataset.activeBuffer,'0'); assert.equal(view.videos[0].playCalls,2);
} else if (scenario==='loop-coverage') {
  const view=mount();
  for(let elapsed=0;elapsed<26000;elapsed+=16) {
    await drift(16);
    if(!view['video-buffers'].classes.has('ready')) continue;
    const [bottom,top]=[...view.videos].sort((a,b)=>Number(a.style.zIndex)-Number(b.style.zIndex));
    const coverage=Number(top.style.opacity)+(1-Number(top.style.opacity))*Number(bottom.style.opacity);
    assert.ok(coverage>.999999); assert.ok(view.videos.some(v=>!v.paused));
  }
} else if (scenario==='loop-delayed') {
  const view=mount(); await drift(4900); assert.equal(view.videos[1].playCalls,0);
  view.videos[1].readyState=4; view.videos[1].fire('loadeddata'); await drift(1400);
  assert.equal(view.intro.dataset.video,'playing'); assert.equal(view['video-buffers'].dataset.seams,'1');
} else if (scenario==='loop-stalled' || scenario==='loop-reject' || scenario==='loop-seek-error') {
  const view=mount(); await drift(7000);
  assert.equal(view.intro.dataset.video,'fallback'); assert.ok(view.videos.every(v=>v.paused));
  assert.equal(rafs.size,0); assert.equal(view['video-buffers'].classes.has('ready'),false);
  key(); await drift(2010); assert.equal(view.sentence.textContent,'一');
} else if (scenario==='loop-error') {
  const view=mount(); await drift(1000); view.videos[1].fire('error');
  assert.equal(view.intro.dataset.video,'fallback'); assert.ok(view.videos.every(v=>v.paused));
  assert.equal(rafs.size,0); view.cleanup();
  assert.ok(view.videos.every(v=>[...v.listeners.values()].every(listeners=>listeners.size===0)));
} else if (scenario==='loop-rerun') {
  let view=mount(); await drift(5100); assert.equal(view['video-buffers'].dataset.loopPhase,'overlap');
  const old=view, counts=old.videos.map(v=>v.playCalls); view.cleanup();
  assert.equal(rafs.size,0); assert.ok(old.videos.every(v=>v.paused));
  view=mount(); assert.equal(view['video-buffers'].dataset.seams,'0'); await drift(6000);
  assert.equal(view['video-buffers'].dataset.seams,'1'); assert.deepEqual(old.videos.map(v=>v.playCalls),counts);
  assert.equal(rafs.size,1); assert.equal(audioCreated,0);
} else if (scenario==='loop-cleanup') {
  const view=mount(); await drift(5100); view.cleanup();
  assert.equal(rafs.size,0); assert.equal(timers.size,0); assert.ok(view.videos.every(v=>v.paused));
  assert.ok(view.videos.every(v=>[...v.listeners.values()].every(listeners=>listeners.size===0)));
  const times=view.videos.map(v=>v.currentTime); await drift(30000);
  assert.deepEqual(view.videos.map(v=>v.currentTime),times); assert.deepEqual(reports,[]);
} else if (scenario==='loop-replay') {
  let view=mount(); await drift(9000); const old=view; view.skip.fire('click'); await drift(180); view.cleanup();
  assert.ok(old.videos.every(v=>[...v.listeners.values()].every(listeners=>listeners.size===0)));
  assert.ok(old.videos.every(v=>v.paused)); assert.equal(rafs.size,0);
  view=mount('clean-loop-replay'); await Promise.resolve();
  assert.equal(view['video-buffers'].dataset.seams,'0'); assert.equal(view['video-buffers'].dataset.activeBuffer,'0');
  assert.equal(view.intro.dataset.index,'-1'); await drift(6000); assert.equal(view['video-buffers'].dataset.seams,'1');
} else if (scenario==='reduced-loop') {
  const view=mount(); await drift(30000);
  assert.equal(view.intro.dataset.video,'static'); assert.equal(view.videos[0].currentTime,0);
  assert.ok(view.videos.every(v=>v.playCalls===0 && v.paused)); assert.equal(rafs.size,0);
  assert.equal(view['video-buffers'].dataset.seams,'0'); key(); await drift(300); assert.equal(view.sentence.textContent,'一');
} else if (scenario==='loop-buffer-limit') {
  assert.throws(()=>module.createSeamlessLoop([new Video()],new Element(),false,()=>{}));
  assert.throws(()=>module.createSeamlessLoop([new Video(),new Video(),new Video()],new Element(),false,()=>{}));
} else { throw Error('Unknown scenario'); }
console.log(`PASS ${scenario}`);
