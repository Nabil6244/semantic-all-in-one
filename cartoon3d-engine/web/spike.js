// Step-1 spike: one toon character in a small sunny park, mouth driven by the voice, blinking, gestures from the plan.
// window.renderFrame(t) is a pure function of t.
import * as THREE from '/three/three.module.min.js';
import { buildToon, poseToon, part, toonMat } from './toon.js';
import { buildTutor } from './tutor.js';
import { buildNora } from './char_nora.js';
import { buildWorld } from './worlds.js';

const q = new URLSearchParams(location.search);
let plan, renderer, scene, camera, toon, cap, W, H, lastCap = '';


async function init() {
  plan = await (await fetch('/plan.json')).json();
  W = Number(q.get('w')) || plan.width; H = Number(q.get('h')) || plan.height;
  const canvas = document.getElementById('gl'); canvas.width = W; canvas.height = H;
  document.documentElement.style.setProperty('--u', `${H / 1080}px`);
  document.getElementById('stage').style.cssText = `width:${W}px;height:${H}px`;
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(W, H, false);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  scene = new THREE.Scene();
  const world = buildWorld(plan.world || 'playroom'); world.setup(scene); scene.add(world.root);
  toon = plan.host === 'nora' ? buildNora({ name: plan.look || 'nora' })
    : plan.host === 'tutor' ? buildTutor({ name: plan.look || 'maya' })
    : buildToon({ palette: plan.palette || 'sunny' });
  toon.userData.seed = 3; scene.add(toon);
  camera = new THREE.PerspectiveCamera(34, W / H, 0.1, 200);
  cap = document.getElementById('cap');
  await document.fonts.ready; try { await document.fonts.load('800 40px Outfit'); } catch { /* fallback */ }
}

// Mouth opening at time t from the per-frame voice envelope.
function mouthAt(t) {
  const e = plan.envelope, k = t * plan.envFps, i = Math.floor(k), f = k - i;
  if (!e || i < 0 || i >= e.length - 1) return 0;
  return e[i] * (1 - f) + e[i + 1] * f;
}

// Gesture at t, with a 0.35 s blend from the previous gesture.
function gestureAt(t) {
  const G = plan.gestures; let cur = null, prev = null;
  for (const g of G) { if (g.t <= t) { prev = cur; cur = g; } }
  if (!cur) return { gesture: 'idle' };
  const gw = Math.min(1, (t - cur.t) / 0.35);
  const s = { gesture: cur.gesture, gt: t - cur.t, gw, emotion: cur.emotion || 'happy' };
  if (gw < 1 && prev) s.prev = { gesture: prev.gesture, gt: t - prev.t };
  return s;
}

window.renderFrame = (t) => {
  const s = gestureAt(t); s.open = mouthAt(t);
  poseToon(toon, t, s);
  // Camera: slow push in with a gentle drift, always framing the face and hands.
  const u = t / plan.duration, ez = u * u * (3 - 2 * u);
  if (plan.host === 'tutor' || plan.host === 'nora') {
    // Teacher framing: medium shot (waist up), eye level, the tutor talks straight into the lens.
    camera.position.set(Math.sin(t * 0.25) * 0.12, 1.55, 2.8 - ez * 0.45);
    camera.lookAt(0, 1.42, 0);
  } else {
    camera.position.set(Math.sin(t * 0.25) * 0.3, 1.2 - ez * 0.08, 4.3 - ez * 1.1);
    camera.lookAt(0, 1.0, 0);
  }
  const clouds = scene.getObjectByName('clouds'); if (clouds) clouds.position.x = t * 0.25;
  renderer.render(scene, camera);
  // Captions: the current line, the spoken word highlighted.
  const line = plan.lines.find((l) => t >= l.t0 && t < l.t1 + 0.25);
  const html = line ? line.words.map((w) => `<span class="w${t >= w.t0 && t < w.t1 + 0.12 ? ' on' : ''}">${w.text}</span>`).join('') : '';
  if (html !== lastCap) { cap.innerHTML = html; lastCap = html; }
  return { t, open: +s.open.toFixed(2), gesture: s.gesture };
};

init().then(() => { window.__ready = true; }).catch((e) => { window.__error = String((e && e.stack) || e); });
