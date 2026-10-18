// What If page (runs in the headless browser): window.renderFrame(t) -> JPEG (base64) of the frame at narration time t.
// A sequence of full-frame shots with hard cuts (lib/shots.mjs), a colour grade on the picture, graphics layers on top
// (layers/*.mjs, the registry in lib/layers.mjs), then vignette and grain. Everything is a pure function of t, so the same
// spec always gives the same video. This renderer shares no code with StarMap.
import { createRegistry, runLayers } from '/lib/layers.mjs';
import { registerBuiltins } from '/layers/index.mjs';
import { shotAt, driftAt, clipFrameIndex, sanitizeShots } from '/lib/shots.mjs';
import { tm } from '/layers/tm_theme.mjs';

const spec = await (await fetch('/spec.json')).json();
const W = spec.width, H = spec.height;
// never stop on a bad shot or layer: it is repaired or left out, and every repair is reported (render.mjs prints the warnings)
const warnings = [];
const warn = (m) => { if (warnings.length < 200) warnings.push(m); console.warn(`[whatif] ${m}`); };
for (const m of sanitizeShots(spec)) warn(m);
spec.shots.forEach((s, i) => { s.i = i; });   // a clip's frames are served as /footage/<its index in spec.shots>/<k>.jpg (cutter.mjs)
await Promise.all(['900 30px StarMapSans', '700 30px TMSans', '600 30px TMSans', '600 30px WIMono', '700 30px WIMono'].map((f) => document.fonts.load(f)));

const out = document.createElement('canvas'); out.width = W; out.height = H;
const ctx = out.getContext('2d');
const T = tm(ctx, W);
const look = { saturate: 0.82, contrast: 1.04, lift: '#080B10', vignette: 0.34, grain: 0.035, ...(spec.look || {}) };

// a picture or clip frame that does not arrive in LOAD_MS is asked for once more, then given up (its shot becomes a plate): a load
// that never finished froze render #016 for good
const LOAD_MS = 20000;
const loadOnce = (name, attempt) => new Promise((ok, fail) => {
  const im = new Image();
  const timer = setTimeout(() => { im.src = ''; fail(new Error(`image ${name} did not load in ${LOAD_MS / 1000} s`)); }, LOAD_MS);
  im.onload = () => { clearTimeout(timer); ok(im); };
  im.onerror = () => { clearTimeout(timer); fail(new Error(`image ${name} not found in media`)); };
  im.src = `/media/${encodeURIComponent(name)}${attempt ? `?retry=${attempt}` : ''}`;
});
const imageCache = new Map();
const loadImage = (name) => {
  if (!imageCache.has(name)) imageCache.set(name, loadOnce(name, 0).catch((e) => (/did not load/.test(e.message) ? loadOnce(name, 1) : Promise.reject(e))));
  return imageCache.get(name);
};
const fetchFrame = async (url) => {
  for (let attempt = 0; ; attempt++) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), LOAD_MS);
    try { const res = await fetch(url, { signal: ctl.signal }); return res.ok ? await res.blob() : null; }
    catch (e) { if (attempt >= 1 || e.name !== 'AbortError') throw new Error(`clip frame ${url} did not load in ${LOAD_MS / 1000} s`); }
    finally { clearTimeout(timer); }
  }
};
const loadTexture = async (name) => {
  const THREE = await import('/three/three.module.min.js');
  const t = await new THREE.TextureLoader().loadAsync(`/textures/${encodeURIComponent(name)}`); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
};
const loadModel = async (name) => {
  const { GLTFLoader } = await import('/three/addons/loaders/GLTFLoader.js');
  const { DRACOLoader } = await import('/three/addons/loaders/DRACOLoader.js');    // NASA's models are Draco-compressed
  const draco = new DRACOLoader().setDecoderPath('/three/addons/libs/draco/gltf/');
  return (await new GLTFLoader().setDRACOLoader(draco).loadAsync(`/models/${encodeURIComponent(name)}`)).scene;
};
let scene3d = null;
if ((spec.shots || []).some((s) => ['craft', 'globe', 'hero'].includes(s.kind))) {
  try {
    const { createScene3d } = await import('/lib/scene3d.mjs');
    scene3d = await createScene3d({ W, H, loadModel, loadTexture });
  } catch (e) { warn(`3D could not start (${e.message}); 3D shots are drawn as plates`); }
}

const registry = registerBuiltins(createRegistry());
const layers = await registry.instantiate(spec.layers || [], { spec, W, H, loadImage, warn }, { lenient: true, warn });
const gradeFilter = `saturate(${look.saturate}) contrast(${look.contrast})`;

const TINTS = { cool: ['#0E131B', '#05070B'], warm: ['#24170F', '#0A0706'], blue: ['#0B2A4A', '#04101E'], dark: ['#0A0C11', '#040508'] };
// a diagram plate stands in deep space like the reference's (V3): the same seeded star sky every frame and every render part, under the
// tint, faint enough that a diagram on it stays the subject
const skyTile = (() => {
  const c = document.createElement('canvas'); c.width = W; c.height = H; const g = c.getContext('2d');
  let s = 4242; const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const k = H / 1080;
  for (let i = 0; i < 2600; i++) {                          // a soft Milky Way band, low and tilted
    const x = r() * W, along = x / W, y = H * (0.78 - 0.42 * along) + (r() + r() + r() - 1.5) * H * 0.16;
    g.fillStyle = `rgba(200,205,225,${0.012 + 0.03 * r()})`; g.beginPath(); g.arc(x, y, (6 + 18 * r()) * k, 0, Math.PI * 2); g.fill();
  }
  for (let i = 0; i < 2200; i++) {                          // stars, a few bright
    const x = r() * W, y = r() * H, b = r() ** 3, rad = (0.5 + 1.3 * b) * k;
    g.fillStyle = `rgba(${225 + 30 * r() | 0},${230 + 25 * r() | 0},255,${0.25 + 0.75 * b})`; g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.fill();
  }
  return c;
})();
const SKY_ALPHA = { cool: 0.85, dark: 0.75, blue: 0.6, warm: 0.35 };
function drawPlate(s) {
  const [inner, outer] = TINTS[s.tint] || TINTS.cool;
  const grd = ctx.createRadialGradient(W * 0.5, H * 0.46, H * 0.05, W * 0.5, H * 0.5, H * 1.05);
  grd.addColorStop(0, inner); grd.addColorStop(1, outer);
  ctx.fillStyle = grd; ctx.fillRect(0, 0, W, H);
  ctx.save(); ctx.globalAlpha *= SKY_ALPHA[s.tint] ?? 0.8; ctx.globalCompositeOperation = 'screen'; ctx.drawImage(skyTile, 0, 0); ctx.restore();
  if (s.title) T.text(String(s.title).toUpperCase(), W / 2, 96 * T.S, { font: T.sans(26, 800), track: 3, align: 'center', shadow: 0 });
  if (s.sub) T.text(String(s.sub).toUpperCase(), W / 2, 130 * T.S, { font: T.mono(17), track: 2, align: 'center', color: '#8E99A8', shadow: 0 });
}

function drawCover(img, d, fit) {
  const base = fit === 'contain' ? Math.min(W / img.width, H / img.height) : Math.max(W / img.width, H / img.height);
  const s = base * d.scale, sw = Math.min(img.width, W / s), sh = Math.min(img.height, H / s);
  const sx = Math.min(img.width - sw, Math.max(0, d.fx * img.width - sw / 2)), sy = Math.min(img.height - sh, Math.max(0, d.fy * img.height - sh / 2));
  if (fit === 'contain') { ctx.fillStyle = '#05070B'; ctx.fillRect(0, 0, W, H); }
  const dw = sw * s, dh = sh * s;
  ctx.drawImage(img, sx, sy, sw, sh, (W - dw) / 2, (H - dh) / 2, dw, dh);
}

const grainTile = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'), im = g.createImageData(256, 256);
  let s = 7; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let i = 0; i < im.data.length; i += 4) { const v = 128 + (rnd() - 0.5) * 255; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255; }
  g.putImageData(im, 0, 0); return c;
})();

// the journey's own craft (V3 0:38 "YOU / ON BOARD"): a thin ring on it and a short leader line to its label, faded in as the shot settles
let markerAt = null;
function drawMarker(s, t, at) {
  const k = Math.min(1, Math.max(0, (t - s.start - 0.5) / 0.4)) * Math.min(1, Math.max(0, (s.end - t) / 0.3));
  if (k <= 0.01) return;
  const S = T.S, r = 13 * S, lx = at.x + 64 * S, ly = at.y - 30 * S;
  ctx.save(); ctx.globalAlpha = 0.92 * k; ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 1.6 * S;
  ctx.beginPath(); ctx.arc(at.x, at.y, r, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(at.x + r * 0.75, at.y - r * 0.66); ctx.lineTo(lx - 6 * S, ly + 6 * S); ctx.stroke();
  const [l1, l2] = String(s.marker).toUpperCase().split('\n');
  T.text(l1, lx, ly, { font: T.sans(22, 800), track: 2, shadow: 0.6 });
  if (l2) T.text(l2, lx, ly + 22 * S, { font: T.mono(15, 600), track: 1.6, color: '#C9D2DD', shadow: 0.5 });
  ctx.restore();
}

async function drawShot(s, t) {
  if (s.broken) { ctx.save(); drawPlate(s); ctx.restore(); return; }
  try { await drawShotRaw(s, t); }
  catch (e) {
    // a picture, clip frame or 3D model that will not load: this shot becomes a plate for the rest of the video
    s.broken = true;
    warn(`shot ${s.id} (${s.kind}) drawn as a plate from ${t.toFixed(2)} s: ${e.message}`);
    ctx.restore(); ctx.save(); ctx.filter = 'none'; ctx.globalAlpha = 1; drawPlate(s); ctx.restore();
  }
}

async function drawShotRaw(s, t) {
  const g = s.grade || {}, filter = g.saturate != null || g.contrast != null
    ? `saturate(${g.saturate ?? look.saturate}) contrast(${g.contrast ?? look.contrast})` : gradeFilter;
  const d = driftAt(s, t);
  ctx.save();
  if (s.kind === 'black') { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); ctx.restore(); return; }
  if (s.kind === 'plate') { drawPlate(s); ctx.restore(); return; }
  ctx.filter = filter;
  if (s.kind === 'image' && s.compose === 'letterbox') {
    // a real photograph as the reference shows it (V1 6:40): the whole picture, full width, centred -- over a blurred, darkened copy of itself
    const img = await loadImage(s.file);
    ctx.filter = 'blur(28px) brightness(0.38) saturate(0.7)'; drawCover(img, { scale: 1.12, fx: 0.5, fy: 0.5 }); ctx.filter = filter;
    const fit = Math.min(W / img.width, H * 0.62 / img.height), dw = img.width * fit * d.scale, dh = img.height * fit * d.scale;
    ctx.drawImage(img, (W - dw) / 2, H * 0.40 - dh / 2, dw, dh);
  } else if (s.kind === 'image' && s.compose === 'card_right') {
    // the reference's photo card (V3 1:46 Jupiter, 1:54 Io): the whole picture framed on the right half, a thin border, the block at the left
    const img = await loadImage(s.file);
    ctx.filter = 'blur(30px) brightness(0.28) saturate(0.6)'; drawCover(img, { scale: 1.12, fx: 0.5, fy: 0.5 }); ctx.filter = filter;
    const bw = W * 0.42, bh = H * 0.7, fit = Math.min(bw / img.width, bh / img.height) * d.scale, dw = img.width * fit, dh = img.height * fit;
    const x = W * 0.73 - dw / 2, y = H * 0.5 - dh / 2;
    ctx.drawImage(img, x, y, dw, dh);
    ctx.filter = 'none'; ctx.strokeStyle = 'rgba(255,255,255,0.22)'; ctx.lineWidth = 1.5 * T.S; ctx.strokeRect(x, y, dw, dh); ctx.filter = filter;
  } else if (s.kind === 'image') drawCover(await loadImage(s.file), d, s.fit);
  else if (s.kind === 'video') {
    const blob = await fetchFrame(`/footage/${s.i}/${clipFrameIndex(s, t, spec.fps)}.jpg`);
    if (!blob) throw new Error(`video shot ${s.id}: frame missing at ${t.toFixed(2)} s`);
    const bmp = await createImageBitmap(blob);
    // a clip drifts too (1.00 -> 1.03): never a frozen frame, never a hard crop of the picture
    const k = d.scale; ctx.translate(W / 2, H / 2); ctx.scale(k, k); ctx.translate(-W / 2, -H / 2); ctx.drawImage(bmp, 0, 0, W, H); bmp.close();
  } else {
    if (!scene3d) throw new Error('3D is not available');
    const cv = await scene3d.draw(s, t);
    ctx.translate(W / 2, H / 2); ctx.scale(d.scale, d.scale); ctx.translate(-W / 2, -H / 2); ctx.drawImage(cv, 0, 0);
    const a = s.marker && scene3d.anchor ? scene3d.anchor() : null;
    markerAt = a ? { x: W / 2 + (a.x - W / 2) * d.scale, y: H / 2 + (a.y - H / 2) * d.scale } : null;
  }
  ctx.filter = 'none';
  if (look.lift) { ctx.save(); ctx.globalCompositeOperation = 'lighten'; ctx.fillStyle = look.lift; ctx.fillRect(0, 0, W, H); ctx.restore(); }
  ctx.restore();
  if (s.marker && markerAt && s.kind === 'craft') drawMarker(s, t, markerAt);
}

function finish(t) {
  if (look.vignette) {
    const grd = ctx.createRadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 1.05);
    grd.addColorStop(0, 'rgba(0,0,0,0)'); grd.addColorStop(1, `rgba(0,0,0,${look.vignette})`);
    ctx.save(); ctx.fillStyle = grd; ctx.fillRect(0, 0, W, H); ctx.restore();
  }
  if (look.grain) {
    const f = Math.round(t * (spec.fps || 30)), ox = (f * 73) % 256, oy = (f * 151) % 256;
    ctx.save(); ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = look.grain;
    ctx.fillStyle = ctx.createPattern(grainTile, 'repeat'); ctx.translate(-ox, -oy); ctx.fillRect(ox, oy, W, H); ctx.restore();
  }
}

// the corner instruments' boxes (fractions of the frame, from tm_clock / tm_mission): template text never lands inside one -- a kicker
// headline at the top left wrote over the light clock for the whole of #016
const HUD_BOXES = { tm_clock: [0.015, 0.02, 0.235, 0.155], tm_mission: [0.76, 0.02, 0.98, 0.17] };
const reservedAt = (t) => layers.filter((L) => HUD_BOXES[L.def.type] && (L.def.type !== 'tm_clock' || (L.def.mode || 'light') === 'light')
  && t >= (L.def.start ?? 0) && t <= (L.def.end ?? 1e9)).map((L) => HUD_BOXES[L.def.type]);

window.renderFrame = async (t) => {
  const s = shotAt(spec.shots, t);
  await drawShot(s, t);
  const reserved = reservedAt(t);
  runLayers(layers, { t, W, H, g: ctx, spec, shot: s, claims: [], reserved }, 'draw', (L) => L.def.type !== 'tm_fade', warn);
  finish(t);
  runLayers(layers, { t, W, H, g: ctx, spec, shot: s, claims: [] }, 'draw', (L) => L.def.type === 'tm_fade', warn);   // a fade covers everything, grain too
  return out.toDataURL('image/jpeg', 0.92).slice('data:image/jpeg;base64,'.length);
};
window.__whatif = { layers, shots: spec.shots, warnings };
window.__ready = true;
