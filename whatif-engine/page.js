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

const imageCache = new Map();
const loadImage = (name) => {
  if (!imageCache.has(name)) imageCache.set(name, new Promise((ok, fail) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => fail(new Error(`image ${name} not found in media`)); im.src = `/media/${encodeURIComponent(name)}`; }));
  return imageCache.get(name);
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
function drawPlate(s) {
  const [inner, outer] = TINTS[s.tint] || TINTS.cool;
  const grd = ctx.createRadialGradient(W * 0.5, H * 0.46, H * 0.05, W * 0.5, H * 0.5, H * 1.05);
  grd.addColorStop(0, inner); grd.addColorStop(1, outer);
  ctx.fillStyle = grd; ctx.fillRect(0, 0, W, H);
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
  } else if (s.kind === 'image') drawCover(await loadImage(s.file), d, s.fit);
  else if (s.kind === 'video') {
    const res = await fetch(`/footage/${s.i}/${clipFrameIndex(s, t, spec.fps)}.jpg`);
    if (!res.ok) throw new Error(`video shot ${s.id}: frame missing at ${t.toFixed(2)} s`);
    const bmp = await createImageBitmap(await res.blob());
    // a clip drifts too (1.00 -> 1.03): never a frozen frame, never a hard crop of the picture
    const k = d.scale; ctx.translate(W / 2, H / 2); ctx.scale(k, k); ctx.translate(-W / 2, -H / 2); ctx.drawImage(bmp, 0, 0, W, H); bmp.close();
  } else {
    if (!scene3d) throw new Error('3D is not available');
    const cv = await scene3d.draw(s, t);
    ctx.translate(W / 2, H / 2); ctx.scale(d.scale, d.scale); ctx.translate(-W / 2, -H / 2); ctx.drawImage(cv, 0, 0);
  }
  ctx.filter = 'none';
  if (look.lift) { ctx.save(); ctx.globalCompositeOperation = 'lighten'; ctx.fillStyle = look.lift; ctx.fillRect(0, 0, W, H); ctx.restore(); }
  ctx.restore();
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

window.renderFrame = async (t) => {
  const s = shotAt(spec.shots, t);
  await drawShot(s, t);
  runLayers(layers, { t, W, H, g: ctx, spec, shot: s, claims: [] }, 'draw', (L) => L.def.type !== 'tm_fade', warn);
  finish(t);
  runLayers(layers, { t, W, H, g: ctx, spec, shot: s, claims: [] }, 'draw', (L) => L.def.type === 'tm_fade', warn);   // a fade covers everything, grain too
  return out.toDataURL('image/jpeg', 0.92).slice('data:image/jpeg;base64,'.length);
};
window.__whatif = { layers, shots: spec.shots, warnings };
window.__ready = true;
