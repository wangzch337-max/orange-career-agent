// Only presentation state. No product data, network, or framework runtime.
export const SEEN_KEY = "orange_intro_seen_v1";
export const MUTED_KEY = "orange_intro_muted_v1";
export const TIMING = Object.freeze({ exit: 760, pause: 260, enter: 1450, respond: 560, leaf: 780, finish: 1500 });
export const REDUCED_TIMING = Object.freeze({ exit: 120, pause: 0, enter: 180, respond: 120, leaf: 120, finish: 180 });
// Reproducible suspended-core motion: right, left, down, up-right, right, left.
export const LEAF_DIRECTIONS = Object.freeze([
  [5, 7, 4], [-5, 7, -4], [1, 9, 3], [4, -4, -3], [6, 6, 5], [-6, 8, -5],
].map(direction => Object.freeze(direction)));

export function leafDirection(step, final = false) {
  return LEAF_DIRECTIONS[step % LEAF_DIRECTIONS.length].map(value => value * (final ? .7 : 1));
}

export function validAdvanceKey(event) {
  if (event.repeat || event.isComposing || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return false;
  return ["Enter", " ", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key) || event.key.length === 1;
}

export function createIntroState() {
  return { index: -1, phase: "ready", motion: "THINKING", lastAccepted: -Infinity, transition: null };
}

export function advanceIntro(state, now, count = 6) {
  if (!["ready", "speaking"].includes(state.phase) || now - state.lastAccepted < 380) return null;
  state.lastAccepted = now;
  if (state.index === count - 1) { state.phase = "finishing"; state.motion = "FINISH"; return "finish"; }
  state.index += 1;
  state.phase = "transitioning";
  state.motion = "RESPOND";
  return state.index === 0 ? "opening" : "advance";
}

export function readFlag(storage, key) {
  try { return storage.getItem(key) === "1"; } catch { return false; }
}

export function writeFlag(storage, key, enabled) {
  try { if (enabled) storage.setItem(key, "1"); else storage.removeItem(key); } catch { /* Session still usable with storage blocked. */ }
}

// Source-frame inspection: 0.50→1.45s and 4.50→5.45s are compatible regions.
// The overlap finishes well before the original 6.04s end. No native loop/rewind.
export const LOOP_CONFIG = Object.freeze({ inTime: .5, outTime: 4.5, crossfade: 1000, rate: .95 });
export function seamBlend(progress) {
  const smooth = value => { const x = Math.max(0, Math.min(1, value)); return x * x * (3 - 2 * x); };
  // Incoming reaches full coverage before outgoing falls. Keeping an opaque
  // lower buffer avoids revealing the unrelated poster or darkening the seam.
  return { incoming: smooth((progress - .24) / .46), outgoing: 1 - smooth((progress - .72) / .28) };
}

export function createSeamlessLoop(videos, viewport, reducedMotion, onStatus) {
  if (videos.length !== 2) throw new Error("Two local video buffers required");
  let active = 0, overlap = null, frame = null, running = false, started = false, disposed = false;
  let seams = 0;
  const listeners = [];
  const ready = video => video.readyState >= 2 && !video.seeking;
  function listen(video, name, callback) {
    video.addEventListener(name, callback);
    listeners.push(() => video.removeEventListener(name, callback));
  }
  function stop() {
    running = false;
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
    videos.forEach(video => video.pause());
  }
  function fail() {
    if (disposed || !running) return;
    stop();
    viewport.classList.remove("ready");
    onStatus("fallback");
  }
  function resetHidden(video, time = LOOP_CONFIG.inTime) {
    // Opacity is changed synchronously, without a CSS opacity transition.
    // Seeking a visible/dominant buffer is never permitted.
    video.style.opacity = "0";
    video.pause();
    try { video.currentTime = time; } catch { fail(); }
  }
  function reveal(video) {
    if (!ready(video)) return;
    video.classList.add("decoded");
    video.style.opacity = "1";
    viewport.classList.add("ready");
  }
  function play(video, after) {
    try {
      Promise.resolve(video.play()).then(() => { if (running && !disposed) after(); }).catch(fail);
    } catch { fail(); }
  }
  function tick() {
    if (!running || disposed || reducedMotion || !started) return;
    const outgoing = videos[active], incoming = videos[1 - active];
    if (!overlap && outgoing.currentTime >= LOOP_CONFIG.outTime && ready(incoming)) {
      overlap = { from: active, playing: false };
      incoming.style.zIndex = "2";
      outgoing.style.zIndex = "1";
      // The prepared hidden buffer is already decoded at the loop-in point.
      play(incoming, () => { if (overlap) overlap.playing = true; });
    }
    if (overlap?.playing) {
      if (!ready(incoming)) { fail(); return; }
      const progress = (incoming.currentTime - LOOP_CONFIG.inTime) / (LOOP_CONFIG.rate * LOOP_CONFIG.crossfade / 1000);
      const blend = seamBlend(progress);
      incoming.style.opacity = String(blend.incoming);
      outgoing.style.opacity = String(blend.outgoing);
      viewport.dataset.loopPhase = "overlap";
      if (progress >= 1) {
        incoming.style.opacity = "1";
        active = 1 - active;
        overlap = null;
        resetHidden(outgoing);
        viewport.dataset.seams = String(++seams);
        viewport.dataset.activeBuffer = String(active);
        viewport.dataset.loopPhase = "steady";
      }
    }
    // Decode/play failure cannot leave a visibly frozen final frame indefinitely.
    if (outgoing.ended) fail();
  }
  function schedule() {
    if (!running || reducedMotion || frame !== null) return;
    frame = window.requestAnimationFrame(() => { frame = null; tick(); schedule(); });
  }
  function firstFrame() {
    if (!running || started || !ready(videos[0])) return;
    if (reducedMotion) { reveal(videos[0]); onStatus("static"); return; }
    started = true;
    play(videos[0], () => { reveal(videos[0]); onStatus("playing"); schedule(); });
  }
  videos.forEach((video, index) => {
    video.muted = true;
    video.defaultMuted = true;
    video.volume = 0;
    video.loop = false;
    video.playbackRate = LOOP_CONFIG.rate;
    video.style.opacity = "0";
    video.style.zIndex = index === 0 ? "2" : "1";
    listen(video, "loadeddata", firstFrame);
    listen(video, "seeked", firstFrame);
    listen(video, "error", fail);
    listen(video, "timeupdate", tick);
    listen(video, "ended", tick);
  });
  return {
    start() {
      if (running || disposed) return;
      running = true;
      viewport.dataset.seams = "0";
      viewport.dataset.activeBuffer = "0";
      viewport.dataset.loopPhase = "steady";
      onStatus(reducedMotion ? "static" : "loading");
      resetHidden(videos[1]);
      if (reducedMotion) resetHidden(videos[0], 0);
      if (!running) return;
      firstFrame();
    },
    stop,
    destroy() { stop(); disposed = true; listeners.splice(0).forEach(remove => remove()); },
  };
}

// Module lifetime survives Streamlit reruns. No domain state is retained here.
let state = null;
let lastReplay = null;
let reported = false;
let muted = false;
let lastSession = null;

export default function(component) {
  const { parentElement, data, setStateValue } = component;
  const dialog = parentElement.querySelector(".intro");
  const sentence = parentElement.querySelector(".sentence");
  const hint = parentElement.querySelector(".hint");
  const mascot = parentElement.querySelector(".mascot");
  const leaf = parentElement.querySelector(".leaf");
  const videos = Array.from(parentElement.querySelectorAll(".thinking-video"));
  const videoViewport = parentElement.querySelector(".video-buffers");
  const mute = parentElement.querySelector(".mute");
  const skip = parentElement.querySelector(".skip");
  // Even accessing localStorage can throw in a restricted browser.
  let storage;
  try { storage = window.localStorage; } catch { storage = null; }
  // A Demo reset creates a fresh presentation mirror, not another first visit.
  if (data.presentation_session !== lastSession) {
    lastSession = data.presentation_session;
    reported = false;
  }
  const replay = Boolean(data.replay_token && data.replay_token !== lastReplay);
  if (replay) {
    lastReplay = data.replay_token;
    writeFlag(storage, SEEN_KEY, false);
    state = createIntroState();
    reported = false;
  }
  if (!state) {
    state = createIntroState();
    if (readFlag(storage, SEEN_KEY)) state.phase = "done";
  }
  muted = readFlag(storage, MUTED_KEY);
  let audio = null;
  let finishTimer = null;
  const transitionTimers = [];
  const pressed = new Set();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const timing = reducedMotion ? REDUCED_TIMING : TIMING;
  const videoLoop = createSeamlessLoop(videos, videoViewport, reducedMotion, status => { dialog.dataset.video = status; });
  dialog.dataset.audio = "not-created";
  delete dialog.dataset.lastCue;

  function reportComplete() {
    if (!reported) { reported = true; setStateValue("completed", true); }
  }
  function updateMute() {
    mute.textContent = muted ? "声音：关" : "声音：开";
    mute.setAttribute("aria-pressed", String(muted));
    mute.setAttribute("aria-label", muted ? "开启介绍声音" : "关闭介绍声音");
  }
  function closeAudio() {
    if (audio) { audio.close().catch(() => {}); audio = null; }
  }
  function cue(kind, event) {
    if (muted || !event.isTrusted) return;
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) { dialog.dataset.audio = "unavailable"; return; }
    try {
      if (!audio) audio = new AudioContext();
      const context = audio;
      context.resume().then(() => {
        if (muted || state.phase === "done" || context.state === "closed") return;
        const notes = kind === "opening" ? [523.25, 659.25] : kind === "finish" ? [523.25, 659.25, 783.99] : [440];
        const duration = kind === "advance" ? .075 : .20;
        notes.forEach((frequency, index) => {
          const start = context.currentTime + index * .12;
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          oscillator.type = "sine";
          oscillator.frequency.value = frequency;
          gain.gain.setValueAtTime(0, start);
          gain.gain.linearRampToValueAtTime(kind === "advance" ? .025 : .045, start + .012);
          gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
          oscillator.connect(gain);
          gain.connect(context.destination);
          oscillator.start(start);
          oscillator.stop(start + duration + .01);
          oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
        });
        dialog.dataset.audio = context.state;
        dialog.dataset.lastCue = kind;
      }).catch(() => { dialog.dataset.audio = "blocked"; });
    } catch { dialog.dataset.audio = "unavailable"; }
  }
  function setMotion(motion) {
    state.motion = motion;
    dialog.dataset.motion = motion;
  }
  function setSentence(text) {
    if (sentence.textContent === text) return;
    if (!text.includes("岗位")) { sentence.textContent = text; return; }
    // One real-text sentence, with a single word kept intact across natural wraps.
    const [before, after] = text.split("岗位");
    const word = document.createElement("span");
    word.className = "sentence-word";
    word.textContent = "岗位";
    sentence.replaceChildren(document.createTextNode(before), word, document.createTextNode(after));
  }
  function clearTransitionTimers() {
    transitionTimers.splice(0).forEach(id => window.clearTimeout(id));
  }
  function setLeafMotion(step, elapsed = 0, final = false) {
    const [x, y, angle] = leafDirection(step, final);
    leaf.style.setProperty("--leaf-x", `${x}px`);
    leaf.style.setProperty("--leaf-y", `${y}px`);
    leaf.style.setProperty("--leaf-angle", `${angle}deg`);
    leaf.style.setProperty("--leaf-delay", `${-elapsed}ms`);
    leaf.dataset.direction = String(step % LEAF_DIRECTIONS.length);
    if (!reducedMotion) leaf.classList.add("inertia");
  }
  function syncPresentation() {
    if (state.phase === "done" || state.phase === "finishing") return;
    const now = performance.now();
    const transition = state.transition;
    if (transition && now >= transition.settleAt) {
      state.phase = "speaking";
      state.transition = null;
    }
    hint.textContent = state.index < 0 ? "按任意键开始" : (navigator.maxTouchPoints > 0 ? "按任意键或轻触继续" : "按任意键继续");
    dialog.dataset.phase = state.phase;
    dialog.dataset.index = String(state.index);
    sentence.classList.remove("exiting", "entering");
    sentence.style.animationDelay = "0ms";
    if (!state.transition) {
      setSentence(state.index < 0 ? "" : data.messages[state.index]);
      leaf.classList.remove("inertia");
      dialog.dataset.textPhase = state.index < 0 ? "empty" : "hold";
      setMotion("THINKING");
      return;
    }
    const elapsed = now - transition.startAt;
    mascot.style.setProperty("--response-delay", `${-elapsed}ms`);
    if (now < transition.leafEndAt) setLeafMotion(state.index, elapsed);
    else leaf.classList.remove("inertia");
    if (now < transition.enterAt) {
      setSentence(transition.previousIndex < 0 ? "" : data.messages[transition.previousIndex]);
      if (transition.previousIndex >= 0) {
        sentence.style.animationDelay = `${-elapsed}ms`;
        sentence.classList.add("exiting");
      }
      dialog.dataset.textPhase = now < transition.exitAt ? "exit" : "pause";
      setMotion("RESPOND");
    } else {
      // Replace real text only after the outgoing sentence has fully faded.
      setSentence(data.messages[state.index]);
      sentence.style.animationDelay = `${-(now - transition.enterAt)}ms`;
      sentence.classList.add("entering");
      dialog.dataset.textPhase = "enter";
      setMotion("SPEAKING");
    }
  }
  function resumeTransition() {
    syncPresentation();
    if (!state.transition) return;
    const { exitAt, enterAt, leafEndAt, settleAt } = state.transition;
    function wakeAt(deadline) {
      const remaining = deadline - performance.now();
      // Browser timers round fractional delays and may wake just before a deadline.
      // Recheck, rather than losing the final settle event and locking input.
      if (remaining > 0) transitionTimers.push(window.setTimeout(() => wakeAt(deadline), Math.ceil(remaining)));
      else syncPresentation();
    }
    for (const deadline of new Set([exitAt, enterAt, leafEndAt, settleAt])) {
      if (deadline > performance.now()) wakeAt(deadline);
    }
  }
  function dismiss(skipIntro = false) {
    if (state.phase === "done") return;
    clearTransitionTimers();
    window.clearTimeout(finishTimer);
    state.transition = null;
    state.phase = "finishing";
    setMotion("FINISH");
    const now = performance.now();
    if (!state.finishAt || skipIntro) {
      state.skipFinish = skipIntro;
      state.finishAt = now + (skipIntro ? 180 : timing.finish);
      state.finishStart = now;
    }
    writeFlag(storage, SEEN_KEY, true);
    dialog.dataset.phase = "finishing";
    dialog.dataset.textPhase = "finish";
    sentence.classList.remove("exiting", "entering");
    sentence.style.animationDelay = "0ms";
    mascot.style.setProperty("--finish-delay", `${-(now - state.finishStart)}ms`);
    sentence.style.setProperty("--finish-delay", `${-(now - state.finishStart)}ms`);
    if (!state.skipFinish) {
      setSentence(data.messages[state.index]);
      setLeafMotion(data.messages.length, now - state.finishStart, true);
    }
    dialog.classList.add("finishing");
    if (state.skipFinish) { dialog.classList.add("skipping"); closeAudio(); }
    finishTimer = window.setTimeout(() => {
      state.phase = "done";
      dialog.close();
      videoLoop.destroy();
      closeAudio();
      detach();
      reportComplete();
    }, Math.max(0, Math.ceil(state.finishAt - now)));
  }
  function advance(event) {
    const now = performance.now();
    const previousIndex = state.index;
    const kind = advanceIntro(state, now, data.messages.length);
    if (!kind) return;
    cue(kind, event);
    if (kind === "finish") dismiss();
    else {
      clearTransitionTimers();
      // First contact has no outgoing sentence. Let the response land before
      // materializing 你好; later advances use the full exit/pause/enter lock.
      const enterDelay = kind === "opening" ? timing.respond : timing.exit + timing.pause;
      state.transition = {
        previousIndex, startAt: now, exitAt: now + (kind === "opening" ? timing.respond : timing.exit),
        enterAt: now + enterDelay,
        leafEndAt: now + timing.leaf,
        settleAt: now + enterDelay + timing.enter,
      };
      resumeTransition();
    }
  }
  function keydown(event) {
    if (!dialog.open || state.phase === "done") return;
    if (event.key === "Tab") return; // Native modal dialog owns focus containment.
    if (event.key === "Escape") return; // Native cancel handler provides Skip.
    // Enter/Space on an actual control must activate only that control.
    if (["Enter", " "].includes(event.key) && event.composedPath().some(node => node === mute || node === skip)) return;
    event.stopPropagation();
    if (!validAdvanceKey(event) || pressed.has(event.code || event.key)) return;
    event.preventDefault();
    pressed.add(event.code || event.key);
    advance(event);
  }
  function keyup(event) { pressed.delete(event.code || event.key); }
  function pointer(event) {
    if (!event.isPrimary || event.button !== 0 || event.composedPath().some(node => node === mute || node === skip)) return;
    // One pointerup covers mouse and touch; no duplicate click/touchend listeners.
    advance(event);
  }
  function muteClick(event) {
    event.stopPropagation();
    muted = !muted;
    writeFlag(storage, MUTED_KEY, muted);
    if (muted) closeAudio();
    updateMute();
  }
  function skipClick(event) { event.stopPropagation(); dismiss(true); }
  function cancel(event) { event.preventDefault(); dismiss(true); }
  function detach() {
    document.removeEventListener("keydown", keydown, true);
    document.removeEventListener("keyup", keyup, true);
    dialog.removeEventListener("pointerup", pointer);
    dialog.removeEventListener("cancel", cancel);
    mute.removeEventListener("click", muteClick);
    skip.removeEventListener("click", skipClick);
  }

  updateMute();
  syncPresentation();
  if (state.phase === "done") { videoLoop.destroy(); if (dialog.open) dialog.close(); reportComplete(); }
  else {
    videoLoop.start();
    dialog.classList.remove("finishing", "skipping");
    if (!dialog.open) dialog.showModal();
    dialog.focus();
    document.addEventListener("keydown", keydown, true);
    document.addEventListener("keyup", keyup, true);
    dialog.addEventListener("pointerup", pointer);
    dialog.addEventListener("cancel", cancel);
    mute.addEventListener("click", muteClick);
    skip.addEventListener("click", skipClick);
    // A rerun during the final transition resumes completion, not the script.
    if (state.phase === "finishing") dismiss();
    else if (state.transition) resumeTransition();
  }
  return () => {
    videoLoop.destroy();
    detach();
    window.clearTimeout(finishTimer);
    clearTransitionTimers();
    closeAudio();
    if (dialog.open) dialog.close();
  };
}
