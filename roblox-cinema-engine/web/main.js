// The page runtime. window.renderFrame(t) draws one film frame: the scene (or two, in a transition) into half-float targets,
// the composite pass to the canvas, and the HUD. Every frame is a function of t alone, so a frame renders alone, in any order, or in
// a parallel part. A scene's world, cast and effects are built the first time a frame needs it and freed when it is two scenes behind.
import * as THREE from '/three/three.module.min.js';
import { assembleScene } from '../lib/assemble.mjs';
import { buildWorld } from './world3d.js';
import { buildCharacter, buildHeld, poseRig, setFace } from './character.js';
import { buildVehicle, poseVehicle } from './vehicle.js';
import { buildMap } from './map3d.js';
import { makeFxLayer } from './fx3d.js';
import { makeAtmosphere, makePost, PRESETS } from './look.js';
import { makeHud } from './hud.js';
import { stats as gfxStats, isSharedGeo } from './gfx.js';
import { makeProj } from '../lib/mapproj.mjs';
import { cardAt } from '../lib/horror.mjs';
import { drawCard, drawPicture } from './card_art.js';

const q = new URLSearchParams(location.search);
let plan, geo, renderer, post, camera, hud, W, H;
const runtimes = new Map();
const perf = { builds: [], frames: 0, maxDraw: 0, maxTris: 0, maxLive: 0, errors: [] };
const MAP_HEIGHT = 780;
const LAYER_ROOM = 3, LAYER_GLASS = 4; // people the film camera sees / doubles only a mirror sees
const cardImages = new Map();   // picture cards, loaded before the first frame: frames are drawn in one go and cannot wait for a file
let cardTex = null;             // the card on screen now; freed when the next one comes

async function init() {
  plan = await (await fetch('/plan.json')).json();
  geo = await (await fetch('/geo.json')).json();
  W = Number(q.get('w')) || plan.width; H = Number(q.get('h')) || plan.height;
  const canvas = document.getElementById('gl');
  canvas.width = W; canvas.height = H;
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance', preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(W, H, false);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.NoToneMapping; renderer.info.autoReset = false;
  document.documentElement.style.setProperty('--u', `${H / 1080}px`);
  document.getElementById('stage').style.cssText = `width:${W}px;height:${H}px`;
  post = makePost(renderer, W, H);
  camera = new THREE.PerspectiveCamera(40, W / H, 0.3, 5000); camera.layers.enable(LAYER_ROOM);
  plan.hud.credit = plan.hud.credit || null;
  hud = makeHud(document.getElementById('hud'), plan.hud, { duration: plan.duration });
  for (const s of plan.scenes) if (s.env === 'map') { const v = mapView(s); s.mapView = v; for (const sh of s.shots) sh.height = v.h * (sh.zoom || 1); }
  await Promise.all((plan.cards || []).filter((c) => c.image).map((c) => new Promise((done) => {
    const img = new Image(); img.onload = () => { cardImages.set(c.id, img); done(); };
    img.onerror = () => { console.warn(`card ${c.id}: the picture did not load, using the code-made card`); done(); };
    img.src = c.image;
  })));
  await document.fonts.ready;
  try { await document.fonts.load('700 40px Outfit'); await document.fonts.load('700 40px Inter'); } catch { /* fallback font */ }
}

// Where the map camera looks and how high it sits so every pin and arrow end is in frame, above the subtitle band.
function mapView(s) {
  const P = makeProj(s.map.bbox), pts = [...s.map.pins.map((p) => [p.lon, p.lat]), ...s.map.arrows.flatMap((a) => [a.from, a.to])].map(([lo, la]) => P.toXZ(lo, la));
  if (!pts.length) return { h: MAP_HEIGHT, c: [0, 0, 120] };
  const xs = pts.map((p) => p[0]), zs = pts.map((p) => p[1]), x0 = Math.min(...xs), x1 = Math.max(...xs), z0 = Math.min(...zs), z1 = Math.max(...zs);
  const half = Math.tan(18 * Math.PI / 180), aspect = (Number(q.get('w')) || plan.width) / (Number(q.get('h')) || plan.height);
  const hx = ((x1 - x0) / 2 + 90) / (half * aspect * 0.9), hz = ((z1 - z0) / 2 + 80) / (half * 0.34);
  const h = Math.max(300, Math.min(1600, 1.45 * Math.max(hx, hz, MAP_HEIGHT * 0.55)));
  return { h, c: [(x0 + x1) / 2, 0, (z0 + z1) / 2 + h * 0.06] };
}

function sceneIndexAt(t) { const S = plan.scenes; let i = S.findIndex((s) => t >= s.t0 && t < s.t1); if (i < 0) i = t < S[0].t0 ? 0 : S.length - 1; return i; }

function ensure(i) {
  let rt = runtimes.get(i); if (rt) return rt;
  const t0 = performance.now(), s = plan.scenes[i];
  const sc = new THREE.Scene(), A = assembleScene(s), atm = makeAtmosphere(sc, s.light, s.weather, { fogScale: s.env === 'sea' ? 2.6 : 1, shadowSize: Number(q.get('shadow')) || 2048 }), P = atm.preset;
  rt = { i, s, A, sc, atm, P, rigs: [], vrigs: [], animates: [], lightPool: [], fxLayer: null, map: null };
  if (s.env === 'map') {
    const g = geo[s.id] || { countries: [], focus: [] };
    rt.map = buildMap(s, g, P); sc.add(rt.map); A.mapFocus = () => s.mapView.c;
  } else {
    const root = buildWorld(A.world, { night: !!P.night, water: P.water });
    root.traverse((o) => { if (o.userData && o.userData.animate) rt.animates.push(o.userData.animate); });
    sc.add(root);
    for (const a of A.stage.actors) {
      const rig = buildCharacter(a.look); rig.userData.actor = a; sc.add(rig); rt.rigs.push(rig);
      // horror: what this person holds, and when (plan scene.holds); the first person of the role holds it
      rig.userData.held = (s.holds || []).filter((h) => h.role === a.role && A.stage.actors.find((x) => x.role === a.role) === a)
        .map((h) => { const m = buildHeld(h.item, h.color); (h.hand === 'L' ? rig.userData.armL : rig.userData.armR).add(m); m.visible = false; return { h, m }; });
    }
    const glass = []; root.traverse((o) => { if (o.isReflector) glass.push(o); });
    if (glass.length && s.mirrorPlay?.length) {
      rt.doubles = A.stage.actors.map((a) => { const d = buildCharacter(a.look); d.userData.actor = a; d.traverse((o) => o.layers.set(LAYER_GLASS)); sc.add(d); return d; });
      for (const rig of rt.rigs) rig.traverse((o) => o.layers.set(LAYER_ROOM));
      for (const m of glass) m.camera.layers.enable(LAYER_GLASS);
    }
    for (const v of A.stage.vehicles) { const rig = buildVehicle(v.kind, v.color); rig.userData.veh = v; sc.add(rig); rt.vrigs.push(rig); }
    rt.fxLayer = makeFxLayer(); sc.add(rt.fxLayer.group);
    if (A.lights.length) for (let k = 0; k < 2; k++) { const L = new THREE.PointLight(0xffa860, 0, 120, 2); sc.add(L); rt.lightPool.push(L); }
  }
  perf.builds.push({ scene: s.id, env: s.env, ms: Math.round(performance.now() - t0), actors: rt.rigs.length, vehicles: rt.vrigs.length });
  runtimes.set(i, rt);
  for (const [k, old] of runtimes) if (k < i - 1 || k > i + 1) { dispose(old); runtimes.delete(k); }
  return rt;
}

function dispose(rt) {
  rt.sc.traverse((o) => {
    if (o.isReflector) { o.dispose(); return; }
    if (o.geometry && !isSharedGeo(o.geometry)) o.geometry.dispose();
    if (o.shadow && o.shadow.map) o.shadow.map.dispose();
  });
  rt.sc.clear();
}

const camPos = new THREE.Vector3(), tgt = new THREE.Vector3();
function drawScene(rt, t, target) {
  const { A, s } = rt, cam = A.cameraAt(t);
  camera.fov = cam.fov; camera.aspect = W / H; camera.position.set(...cam.pos); camera.up.set(Math.sin(cam.roll || 0), Math.cos(cam.roll || 0), 0);
  camera.lookAt(cam.target[0], cam.target[1], cam.target[2]); camera.updateProjectionMatrix(); camera.updateMatrixWorld();
  camPos.copy(camera.position); tgt.set(...cam.target);
  for (const f of rt.animates) f(t);
  for (const rig of rt.rigs) {
    const st = A.actorAt(rig.userData.actor, t), dx = st.x - camPos.x, dz = st.z - camPos.z;
    if (dx * dx + dz * dz > 650 * 650) { rig.visible = false; continue; }
    rig.visible = true; rig.position.set(st.x, st.y, st.z); rig.rotation.y = st.yaw; poseRig(rig, st.pose, t);
    for (const { h, m } of rig.userData.held || []) { m.visible = t >= h.t0 && t < h.t1; if (m.visible && h.hand === 'R') rig.userData.armR.rotation.set(-1.0, 0, 0.04); else if (m.visible) rig.userData.armL.rotation.set(-0.05, 0, -0.06); }
  }
  for (const d of rt.doubles || []) {
    const v = A.reflectionAt(d.userData.actor, t); d.visible = v.visible; if (!v.visible) continue;
    d.position.set(v.x, v.y, v.z); d.rotation.y = v.yaw; poseRig(d, v.pose, t); setFace(d, v.face);
  }
  for (const rig of rt.vrigs) poseVehicle(rig, A.vehicleAt(rig.userData.veh, t));
  let live = 0;
  if (rt.fxLayer) live = rt.fxLayer.update(A, t, camPos, s.weather);
  if (rt.map) rt.map.userData.animate(t);
  if (rt.lightPool.length) {
    const act = [];
    for (const L of A.lights) {
      if (L.type === 'flash') { const k = 1 - (t - L.t) / 0.45; if (k > 0 && k < 1) act.push({ L, I: 9000 * L.intensity * k * k, d: Math.hypot(L.x - camPos.x, L.z - camPos.z) }); }
      else act.push({ L, I: 900 * (0.8 + 0.2 * Math.sin(t * 17 + L.x) * Math.sin(t * 9.3 + L.z)), d: Math.hypot(L.x - camPos.x, L.z - camPos.z) });
    }
    act.sort((a, b) => a.d - b.d);
    rt.lightPool.forEach((pl, k) => { const a = act[k]; if (!a) { pl.intensity = 0; return; } pl.position.set(a.L.x, a.L.y, a.L.z); pl.intensity = a.I; pl.color.set(a.L.type === 'flash' ? 0xffd9a0 : 0xff9a50); });
  }
  rt.atm.update(t, camPos, tgt);
  if (rt.atm.lamp) rt.atm.lamp.position.set(0, 11, 0);
  renderer.setRenderTarget(target); renderer.clear(); renderer.render(rt.sc, camera);
  return live;
}

function mapPins(rt, t) {
  if (!rt.map) return [];
  const placed = [], bw = (txt) => txt.length * 0.032 * H + 0.03 * H, bh = 0.06 * H;
  return rt.map.userData.labels(t).map((p) => { const v = new THREE.Vector3(...p.world).project(camera); return { text: p.text, x: (v.x * 0.5 + 0.5) * W, y: (-v.y * 0.5 + 0.5) * H }; })
    .filter((p) => p.x > 0 && p.x < W && p.y > 0.08 * H && p.y < 0.66 * H)
    .filter((p) => { const r = { x0: p.x - bw(p.text) / 2, x1: p.x + bw(p.text) / 2, y0: p.y - bh, y1: p.y }; if (placed.some((o) => r.x0 < o.x1 && r.x1 > o.x0 && r.y0 < o.y1 && r.y1 > o.y0)) return false; placed.push(r); return true; });
}

/** a card as a texture in display colour, painted once. A picture that fails to paint falls back to the code-made card, so it is never blank. */
function cardTexture(card) {
  if (cardTex && cardTex.id === card.id) return cardTex.tex;
  if (cardTex) cardTex.tex.dispose();
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d'), img = cardImages.get(card.id);
  try { if (img) drawPicture(g, W, H, img); else drawCard(g, W, H, card); } catch (e) { perf.errors.push(`card ${card.id}: ${e.message}`); drawCard(g, W, H, { ...card, kind: 'note', text: card.text || card.what || card.time || '…' }); }
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.NoColorSpace; tex.generateMipmaps = false; tex.minFilter = THREE.LinearFilter;
  cardTex = { id: card.id, tex };
  return tex;
}

function renderFrame(t) {
  const t0 = performance.now();
  renderer.info.reset();
  const i = sceneIndexAt(t), s = plan.scenes[i], cur = ensure(i);
  let prev = null, mode = 0, p = 0, live = 0;
  const tr = s.transitionIn, dur = tr.dur || 0, u = dur ? (t - s.t0) / dur : 2;
  const modeOf = { dissolve: 1, dip: 2, clouds: 3, map_dive: 3 }[tr.type] || 0;
  if (modeOf && u >= 0 && u < 1) {
    if (i === 0) { if (modeOf === 2) { mode = 2; p = 0.5 + u * 0.5; } }
    else { mode = modeOf; p = u; prev = ensure(i - 1); }
  }
  // the last second fades to black
  const left = plan.duration - t;
  if (left < 1.0 && mode === 0) { mode = 2; p = 0.5 * (1 - Math.max(0, left)); }
  live = drawScene(cur, t, post.targets[0]);
  const pins = mapPins(cur, t);
  const curRt = cur;
  if (prev) drawScene(prev, t, post.targets[1]);
  else if (mode === 2 && i === 0 && p >= 0.5) { /* fade up from black: the same target as both sides */ }
  const cd = plan.cards ? cardAt(plan.cards, t) : null;
  post.composite(post.targets[0], prev ? post.targets[1] : post.targets[0], mode, p, curRt.P, prev ? prev.P : curRt.P, cd ? { tex: cardTexture(cd.card), a: cd.a, zoom: 1 - 0.05 * cd.u, t, dim: cd.card.kind === 'phone_screen' || cd.card.kind === 'clock' ? 1 : /night/.test(s.light) ? 0.62 : 0.92 } : null);   // paper is lit by the night it lies in; a screen gives its own light
  hud.update(t, { pins });
  const inf = renderer.info.render;
  perf.frames++; perf.maxDraw = Math.max(perf.maxDraw, inf.calls); perf.maxTris = Math.max(perf.maxTris, inf.triangles); perf.maxLive = Math.max(perf.maxLive, live);
  return { ms: performance.now() - t0, calls: inf.calls, tris: inf.triangles, live, scene: s.id };
}

window.renderFrame = renderFrame;
window.__perf = () => ({ ...perf, gfx: { ...gfxStats }, memory: renderer ? { geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures } : null, heap: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : null });
window.__presets = Object.keys(PRESETS);
window.addEventListener('error', (e) => { perf.errors.push(String(e.message)); });
init().then(() => { window.__ready = true; }).catch((e) => { window.__error = String((e && e.stack) || e); console.error(e); });
