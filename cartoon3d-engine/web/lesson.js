// Kids Learn page: the tutor in a world, toy props that pop in on the spoken word, word cards, count numbers,
// "Your turn!" badges and word-lit captions. window.renderFrame(t) is a pure function of t.
import * as THREE from '/three/three.module.min.js';
import { buildToon, poseToon } from './toon.js';
import { buildTutor } from './tutor.js';
import { loadHost3D, poseHost3D } from './host3d.js';
import { RoomEnvironment } from '/three/addons/environments/RoomEnvironment.js';
import { buildWorld } from './worlds.js';
import { buildProp } from './props.js';
import { COLORS } from './props.js';

const q = new URLSearchParams(location.search);
let plan, renderer, scene, camera, host, W, H;
const el = {}, last = {};
const propRigs = [];

const clamp01 = (x) => Math.max(0, Math.min(1, x));
const backOut = (x) => { const c = 1.9; x = clamp01(x); return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); };
const smooth = (x) => { x = clamp01(x); return x * x * (3 - 2 * x); };
// Pop in over 0.4 s with overshoot, shrink away over 0.25 s before t1.
const popScale = (t, t0, t1) => (t < t0 || t > t1 ? 0 : backOut((t - t0) / 0.4) * (1 - smooth((t - (t1 - 0.25)) / 0.25)));


// Prop moves from the plan: up/down shift height, big/small change size, fast/slow drive a side-to-side run, hop is a jump.
const TARGET = { up: ['dy', 0.3], down: ['dy', -0.2], big: ['sc', 1.45], small: ['sc', 0.55] };
const SPEED = { fast: 2.4, slow: 0.28 };
function moveState(p, t) {
  const st = { dy: 0, sc: 1, dx: 0, hop: 0 }, A = (p.anims || []).filter((a) => a.t <= t);
  for (const ch of ['dy', 'sc']) {
    let v = ch === 'sc' ? 1 : 0;
    const seq = A.filter((a) => TARGET[a.kind] && TARGET[a.kind][0] === ch);
    seq.forEach((a, k) => { const to = TARGET[a.kind][1], end = seq[k + 1] ? seq[k + 1].t : t; const u = smooth((Math.min(t, end) - a.t) / 0.5); v = v + (to - v) * u; });
    st[ch] = v;
  }
  let phase = 0; const runs = A.filter((a) => SPEED[a.kind]);
  runs.forEach((a, k) => { const end = runs[k + 1] ? runs[k + 1].t : t; phase += (end - a.t) * SPEED[a.kind] * Math.PI * 2; });
  if (runs.length) st.dx = Math.sin(phase) * 0.24;
  for (const a of A) if (a.kind === 'hop') { const u = (t - a.t) / 0.45; if (u < 1) st.hop = Math.max(st.hop, Math.sin(u * Math.PI) * 0.12); }
  return st;
}

async function init() {
  plan = await (await fetch('/plan.json')).json();
  W = Number(q.get('w')) || plan.width; H = Number(q.get('h')) || plan.height;
  const canvas = document.getElementById('gl'); canvas.width = W; canvas.height = H;
  document.documentElement.style.setProperty('--u', `${H / 1080}px`);
  document.getElementById('stage').style.cssText = `width:${W}px;height:${H}px`;
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(W, H, false);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.outputColorSpace = THREE.SRGBColorSpace;
  scene = new THREE.Scene();
  const world = buildWorld(plan.world || 'playroom'); world.setup(scene); scene.add(world.root);
  if (plan.host === 'host3d') {                  // the approved 3D host: PBR materials need a soft environment besides the world's lights
    host = await loadHost3D('/host.glb');
    scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture; scene.environmentIntensity = 0.35;
  } else host = plan.host === 'toon' ? buildToon({ palette: plan.palette || 'sunny' }) : buildTutor({ name: plan.look || 'maya' });
  host.userData.seed = 3; host.position.x = plan.tutorX; scene.add(host);
  for (const p of plan.props) { const g = new THREE.Group(), m = buildProp(p.kind, p.color); m.traverse((o) => { if (o.isMesh) o.castShadow = true; }); g.add(m); g.position.set(p.x, p.y, 0.15); g.visible = false; scene.add(g); propRigs.push({ p, g, m }); }
  camera = new THREE.PerspectiveCamera(34, W / H, 0.1, 200);
  for (const k of ['cap', 'card', 'badge', 'nums']) el[k] = document.getElementById(k);
  el.numDivs = plan.props.map((p) => { if (!p.n) return null; const d = document.createElement('div'); d.className = 'num'; d.textContent = p.n; el.nums.appendChild(d); return d; });
  await document.fonts.ready; try { await document.fonts.load('800 40px Outfit'); } catch { /* fallback */ }
}

function mouthAt(t) { const e = plan.envelope, k = t * plan.envFps, i = Math.floor(k), f = k - i; return !e || i < 0 || i >= e.length - 1 ? 0 : e[i] * (1 - f) + e[i + 1] * f; }
function gestureAt(t) {
  let cur = null, prev = null; for (const g of plan.gestures) if (g.t <= t) { prev = cur; cur = g; }
  if (!cur) return { gesture: 'idle', turn: 0 };
  const gw = Math.min(1, (t - cur.t) / 0.35), s = { gesture: cur.gesture, gt: t - cur.t, gw, emotion: cur.emotion || 'happy', beat: cur.beat };
  if (gw < 1 && prev) s.prev = { gesture: prev.gesture, gt: t - prev.t, beat: prev.beat };
  // Glance at the props while presenting them, but come back to the child (camera) at the end of each line.
  const lookP = cur.look === 'props' ? 1 : 0, lookPrev = prev && prev.look === 'props' ? 1 : 0, line = plan.lines.find((l) => t >= l.t0 - 0.2 && t < l.t1);
  const glance = line ? (t - line.t0 < 1.1 || line.t1 - t > 0.6) : false;
  s.turn = (lookPrev + (lookP - lookPrev) * smooth(gw)) * (glance && lookP ? 0.32 : 0.08);
  return s;
}

// 3D host camera: one shot per spoken line, eased over 0.8 s. Props on screen -> two-shot of host and props;
// "your turn"/repeat lines (even with a toy still out) -> head-and-shoulders close-up so the child can watch her mouth; other lines -> medium shot of the host.
// Each shot is [look x, look y, distance]; the camera stays square to the set.
const SHOTS = { two: null, medium: [0, 1.4, 1.75], close: [0, 1.5, 1.2] };
let camCuts = null;
function hostShots() {
  const hx = plan.tutorX, cuts = [];
  const during = (l) => plan.props.filter((p) => p.t0 - 0.2 < l.t1 && (p.t1 ?? plan.duration) > l.t0 + 0.3);   // every prop seen in the line
  const T17 = Math.tan(17 * Math.PI / 180);
  for (const l of plan.lines) {
    const ps = during(l);
    let shot;
    if (l.type === 'repeat') shot = [hx, ...SHOTS.close.slice(1)];                   // speech modelling: watch her mouth
    else if (ps.length) {
      const r = (p) => 0.24 * p.s, right = Math.max(...ps.map((p) => p.x + r(p))) + 0.12, left = hx - 0.45, cy = 1.38;
      const top = Math.max(...ps.map((p) => p.y + r(p))) + 0.12, bottom = Math.min(...ps.map((p) => p.y - r(p))) - 0.05;
      const d = Math.max(1.75, (right - left) / 2 / T17 / camera.aspect, (top - cy) / T17, (cy - bottom) / T17);
      shot = [(left + right) / 2, cy, d];
    } else shot = [hx, ...SHOTS.medium.slice(1)];
    cuts.push({ t: Math.max(0, l.t0 - 0.35), shot });
  }
  return cuts.length ? cuts : [{ t: 0, shot: [hx, ...SHOTS.medium.slice(1)] }];
}
function hostCamera(t) {
  camCuts = camCuts || hostShots();
  let k = 0; while (k + 1 < camCuts.length && camCuts[k + 1].t <= t) k++;
  const cur = camCuts[k].shot, prev = k ? camCuts[k - 1].shot : cur, e = smooth((t - camCuts[k].t) / 0.8);
  const [x, y, d] = cur.map((v, i) => prev[i] + (v - prev[i]) * e);
  const sway = Math.sin(t * 0.21) * 0.03 * d, push = Math.sin(((t % 12) / 12) * Math.PI) * 0.04 * d;
  camera.position.set(x + sway, y + 0.06, d - push); camera.lookAt(x, y, 0);
}

function setHtml(key, node, html) { if (last[key] !== html) { node.innerHTML = html; last[key] = html; } }

window.renderFrame = (t) => {
  const s = gestureAt(t); s.open = mouthAt(t);
  if (host.userData.host3d) poseHost3D(host, t, s, plan); else poseToon(host, t, s);
  if (host.userData.host3d) hostCamera(t);
  else {
    // Camera: medium two-shot of tutor and stage, a slow breathing push.
    const u = (t % 12) / 12, push = Math.sin(u * Math.PI) * 0.18;
    camera.position.set(0.05 + Math.sin(t * 0.21) * 0.1, 1.56, 2.95 - push); camera.lookAt(0.06, 1.42, 0);
  }
  // Props: pop in, bob, slow turn, pop out.
  for (const r of propRigs) {
    const k = popScale(t, r.p.t0, r.p.t1 ?? plan.duration); r.g.visible = k > 0.001;
    if (!r.g.visible) continue;
    const age = t - r.p.t0, mv = moveState(r.p, t); r.g.scale.setScalar(r.p.s * k * mv.sc);
    r.g.position.x = r.p.x + mv.dx;
    r.g.position.y = r.p.y + mv.dy + mv.hop * r.p.s + Math.sin(age * 2.4 + r.p.x * 5) * 0.012 * r.p.s; r.m.rotation.y = Math.sin(age * 0.9) * 0.35;
  }
  renderer.render(scene, camera);
  // Number bubbles over counted props.
  const v = new THREE.Vector3();
  propRigs.forEach((r, i) => {
    const d = el.numDivs[i]; if (!d) return;
    const k = popScale(t, r.p.t0 + 0.05, r.p.t1 ?? plan.duration);
    if (k <= 0.001) { if (d.style.display !== 'none') d.style.display = 'none'; return; }
    v.set(r.p.x, r.g.position.y + 0.14 * r.p.s + 0.06, 0.15).project(camera);
    d.style.display = 'block'; d.style.left = `${((v.x + 1) / 2) * W}px`; d.style.top = `${((1 - v.y) / 2) * H}px`; d.style.transform = `scale(${k.toFixed(3)})`;
  });
  // Word card.
  const c = plan.cards.find((x) => t >= x.t0 && t < x.t1);
  if (c) {
    const col = c.color ? (COLORS[c.color] || c.color) : null;
    setHtml('card', el.card, `${col ? `<span class="sw" style="background:${col}"></span>` : ''}${c.text}`);
    el.card.style.display = 'block'; el.card.style.borderColor = col || (c.sound ? '#51cf66' : c.big ? '#339af0' : '#ff922b');
    el.card.style.transform = `scale(${(popScale(t, c.t0, c.t1) * (c.big ? 1.25 : 1)).toFixed(3)}) rotate(${(Math.sin(t * 1.7) * 2).toFixed(2)}deg)`;
  } else el.card.style.display = 'none';
  // "Your turn!" badge with a gentle bounce.
  const b = plan.badges.find((x) => t >= x.t0 && t < x.t1);
  if (b) { setHtml('badge', el.badge, b.text); el.badge.style.display = 'block'; el.badge.style.transform = `translateX(-50%) scale(${(popScale(t, b.t0, b.t1) * (1 + Math.abs(Math.sin((t - b.t0) * 4)) * 0.05)).toFixed(3)})`; }
  else el.badge.style.display = 'none';
  // Captions.
  const line = plan.lines.find((l) => t >= l.t0 && t < l.t1 + 0.25);
  setHtml('cap', el.cap, line ? line.words.map((w) => `<span class="w${t >= w.t0 && t < w.t1 + 0.12 ? ' on' : ''}">${w.text}</span>`).join('') : '');
  return { t, open: +s.open.toFixed(2), gesture: s.gesture };
};

init().then(() => { window.__ready = true; }).catch((e) => { window.__error = String((e && e.stack) || e); });
