// Shared materials, geometries and procedural textures (the asset cache in the browser). Everything is keyed, so a colour,
// a face or a window pattern is made once per film, whatever the number of characters or buildings using it.
import * as THREE from '/three/three.module.min.js';
import { RoundedBoxGeometry } from '/three/addons/geometries/RoundedBoxGeometry.js';

export const stats = { materials: 0, textures: 0, geometries: 0 };
const matCache = new Map(), geoCache = new Map(), texCache = new Map();
// textures use a generator seeded by their key, so the same film draws the same grain on every run
let R = Math.random;
const seeded = (key) => { let h = 2166136261; for (let i = 0; i < key.length; i++) { h ^= key.charCodeAt(i); h = Math.imul(h, 16777619); } return () => { h = (Math.imul(h ^ (h >>> 15), 2246822507) + 0x6d2b79f5) | 0; return ((h >>> 0) % 1e6) / 1e6; }; };

/** smooth plastic, the block-game material */
export function plastic(color, opts = {}) {
  const key = `p:${color}:${opts.rough ?? 0.55}:${opts.metal ?? 0}:${opts.map ? opts.map.uuid : ''}:${opts.emissive || ''}:${opts.transparent ? opts.opacity : ''}:${opts.side || ''}:${opts.vc ? 1 : 0}`;
  let m = matCache.get(key);
  if (!m) {
    m = new THREE.MeshStandardMaterial({ color: new THREE.Color(color), roughness: opts.rough ?? 0.55, metalness: opts.metal ?? 0, map: opts.map || null,
      emissive: opts.emissive ? new THREE.Color(opts.emissive) : new THREE.Color(0), emissiveIntensity: opts.emissiveIntensity ?? 1,
      transparent: !!opts.transparent, opacity: opts.opacity ?? 1, side: opts.side === 'double' ? THREE.DoubleSide : THREE.FrontSide, vertexColors: !!opts.vc, depthWrite: opts.depthWrite ?? true });
    matCache.set(key, m); stats.materials++;
  }
  return m;
}

const sharedGeos = new Set();
export const isSharedGeo = (g) => sharedGeos.has(g);
export function geo(key, make) { let g = geoCache.get(key); if (!g) { g = make(); geoCache.set(key, g); sharedGeos.add(g); stats.geometries++; } return g; }
export const box = (w, h, d) => geo(`b:${w}:${h}:${d}`, () => new THREE.BoxGeometry(w, h, d));
export const rbox = (w, h, d, r = 0.08) => geo(`rb:${w}:${h}:${d}:${r}`, () => new RoundedBoxGeometry(w, h, d, 2, r));
export const cyl = (rt, rb, h, seg = 16) => geo(`c:${rt}:${rb}:${h}:${seg}`, () => new THREE.CylinderGeometry(rt, rb, h, seg));
export const sphere = (r, ws = 16, hs = 12, phiLen = Math.PI * 2, thLen = Math.PI) => geo(`s:${r}:${ws}:${hs}:${phiLen}:${thLen}`, () => new THREE.SphereGeometry(r, ws, hs, 0, phiLen, 0, thLen));
export const cone = (r, h, seg = 12) => geo(`co:${r}:${h}:${seg}`, () => new THREE.ConeGeometry(r, h, seg));

function canvasTex(key, w, h, draw, opts = {}) {
  let t = texCache.get(key);
  if (t) return t;
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  R = seeded(key);
  draw(c.getContext('2d'), w, h);
  t = new THREE.CanvasTexture(c); t.colorSpace = opts.linear ? THREE.NoColorSpace : THREE.SRGBColorSpace;
  t.anisotropy = 4; if (opts.repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  if (opts.nearest) { t.magFilter = THREE.NearestFilter; }
  texCache.set(key, t); stats.textures++;
  return t;
}

/** A painted sign: text on a board (shop fascia, OPEN card, bus stop plate, timetable). hand = hand-lettered (uneven, script-like). */
export function signTexture(text, bg = '#f2ead8', fg = '#2a1f1a', { w = 512, h = 128, hand = false, glow = false } = {}) {
  return canvasTex(`sign:${text}:${bg}:${fg}:${w}:${h}:${hand}:${glow}`, w, h, (g) => {
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    g.strokeStyle = fg; g.globalAlpha = 0.35; g.lineWidth = Math.max(3, h * 0.05); g.strokeRect(h * 0.06, h * 0.06, w - h * 0.12, h - h * 0.12); g.globalAlpha = 1;
    const lines = String(text).split('\n'), size = Math.min(h * 0.62 / lines.length, (w * 0.86) / Math.max(...lines.map((l) => l.length)) * 1.7);
    g.font = `${hand ? 'italic ' : ''}bold ${Math.round(size)}px ${hand ? '"Comic Sans MS", "Marker Felt", cursive' : '"Helvetica Neue", Arial, sans-serif'}`;
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = fg;
    if (glow) { g.shadowColor = fg; g.shadowBlur = h * 0.12; }
    lines.forEach((l, k) => { const y = h / 2 + (k - (lines.length - 1) / 2) * size * 1.1; if (hand) { g.save(); g.translate(w / 2, y); g.rotate((R() - 0.5) * 0.08); g.fillText(l, 0, 0); g.restore(); } else g.fillText(l, w / 2, y); });
  });
}

/** The face decal: eyes, brows, mouth, facial hair, glasses — drawn on a transparent canvas, in the classic decal manner. */
export function faceTexture(face, mouthOpen = false) {
  const key = `face:${JSON.stringify(face)}:${mouthOpen}`;
  return canvasTex(key, 256, 256, (g) => {
    g.clearRect(0, 0, 256, 256);
    const ink = '#1b1b1d';
    g.fillStyle = ink; g.strokeStyle = ink; g.lineCap = 'round'; g.lineJoin = 'round';
    const ey = 108, ex = 56;
    // eyes
    for (const s of [-1, 1]) {
      const x = 128 + s * ex;
      if (face.eyes === 'dots') { g.beginPath(); g.ellipse(x, ey, 13, 16, 0, 0, 7); g.fill(); }
      else if (face.eyes === 'ovals') { g.beginPath(); g.ellipse(x, ey, 12, 22, 0, 0, 7); g.fill(); g.fillStyle = '#fff'; g.beginPath(); g.arc(x - 3, ey - 8, 4.5, 0, 7); g.fill(); g.fillStyle = ink; }
      else if (face.eyes === 'narrow') { g.lineWidth = 12; g.beginPath(); g.moveTo(x - 16, ey); g.lineTo(x + 16, ey); g.stroke(); }
      else if (face.eyes === 'wide') { g.fillStyle = '#fff'; g.beginPath(); g.ellipse(x, ey, 20, 22, 0, 0, 7); g.fill(); g.fillStyle = ink; g.beginPath(); g.arc(x + s * 2, ey + 2, 10, 0, 7); g.fill(); }
      else { g.beginPath(); g.ellipse(x, ey + 3, 13, 12, 0, 0, 7); g.fill(); g.lineWidth = 6; g.beginPath(); g.moveTo(x - 16, ey - 10); g.lineTo(x + 16, ey - 10); g.stroke(); }
      // brows
      g.lineWidth = 10;
      const by = ey - 34;
      if (face.brows === 'flat') { g.beginPath(); g.moveTo(x - 18, by); g.lineTo(x + 18, by); g.stroke(); }
      else if (face.brows === 'stern') { g.beginPath(); g.moveTo(x - 18 * s, by - 6); g.lineTo(x + 18 * s, by + 6); g.stroke(); }
      else if (face.brows === 'worried') { g.beginPath(); g.moveTo(x - 18 * s, by + 6); g.lineTo(x + 18 * s, by - 8); g.stroke(); }
      else if (face.brows === 'raised') { g.beginPath(); g.arc(x, by + 14, 20, Math.PI * 1.2, Math.PI * 1.8); g.stroke(); }
    }
    if (face.glasses) { g.lineWidth = 6; for (const s of [-1, 1]) { g.beginPath(); g.arc(128 + s * ex, ey, 27, 0, 7); g.stroke(); } g.beginPath(); g.moveTo(128 - ex + 27, ey); g.lineTo(128 + ex - 27, ey); g.stroke(); }
    // mouth
    const my = 178; g.lineWidth = 11;
    const m = mouthOpen ? 'open' : face.mouth;
    if (m === 'smile') { g.beginPath(); g.arc(128, my - 30, 46, Math.PI * 0.18, Math.PI * 0.82); g.stroke(); }
    else if (m === 'grin') { g.beginPath(); g.moveTo(86, my - 8); g.quadraticCurveTo(128, my + 40, 170, my - 8); g.closePath(); g.fill(); g.fillStyle = '#fff'; g.fillRect(100, my - 6, 56, 9); g.fillStyle = ink; }
    else if (m === 'flat') { g.beginPath(); g.moveTo(100, my); g.lineTo(156, my); g.stroke(); }
    else if (m === 'frown') { g.beginPath(); g.arc(128, my + 36, 40, Math.PI * 1.22, Math.PI * 1.78); g.stroke(); }
    else if (m === 'open') { g.beginPath(); g.ellipse(128, my, 20, 16, 0, 0, 7); g.fill(); }
    else if (m === 'determined') { g.beginPath(); g.moveTo(98, my + 4); g.lineTo(158, my - 4); g.stroke(); }
    else if (m === 'smirk') { g.beginPath(); g.moveTo(100, my); g.quadraticCurveTo(140, my + 8, 162, my - 12); g.stroke(); }
    if (face.facial === 'mustache') { g.beginPath(); g.moveTo(92, my - 18); g.quadraticCurveTo(128, my - 40, 164, my - 18); g.quadraticCurveTo(128, my - 24, 92, my - 18); g.fill(); }
    if (face.facial === 'beard') { g.globalAlpha = 0.9; g.beginPath(); g.moveTo(60, 150); g.quadraticCurveTo(128, 270, 196, 150); g.quadraticCurveTo(128, 205, 60, 150); g.fill(); g.globalAlpha = 1; }
    if (face.facial === 'stubble') { g.globalAlpha = 0.22; for (let i = 0; i < 160; i++) { const a = R() * Math.PI, r = 50 + R() * 30; g.fillRect(128 + Math.cos(a) * r * 1.1, 150 + Math.sin(a) * r * 0.9, 3, 3); } g.globalAlpha = 1; }
    if (face.scar) { g.lineWidth = 4; g.strokeStyle = '#8a3a3a'; g.beginPath(); g.moveTo(178, 70); g.lineTo(168, 140); g.stroke(); }
  });
}

/** torso / pants decal: uniform details drawn over the base colour */
export function torsoTexture(look) {
  const key = `torso:${look.torso}:${look.shirt}:${look.belt}:${look.tie}:${look.gear.join()}`;
  return canvasTex(key, 256, 256, (g, w, h) => {
    g.fillStyle = look.shirt; g.fillRect(0, 0, w, h);
    const dark = 'rgba(0,0,0,0.22)', light = 'rgba(255,255,255,0.14)';
    // subtle fabric grain
    for (let i = 0; i < 900; i++) { g.fillStyle = R() < 0.5 ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.035)'; g.fillRect(R() * w, R() * h, 2, 2); }
    if (look.torso.startsWith('uniform') || look.torso === 'police' || look.torso === 'coveralls') {
      g.fillStyle = dark; g.fillRect(0, 0, w, 26); // collar shadow
      g.fillStyle = light; g.beginPath(); g.moveTo(92, 0); g.lineTo(128, 52); g.lineTo(164, 0); g.fill();
      g.fillStyle = dark; g.fillRect(126, 40, 4, 160);
      for (let y = 66; y < 190; y += 34) { g.fillStyle = 'rgba(0,0,0,0.35)'; g.beginPath(); g.arc(136, y, 5, 0, 7); g.fill(); }
      for (const x of [40, 158]) { g.fillStyle = dark; g.fillRect(x, 70, 58, 46); g.fillStyle = light; g.fillRect(x, 70, 58, 8); }
      if (look.belt) { g.fillStyle = look.belt; g.fillRect(0, 206, w, 26); g.fillStyle = '#b9a46a'; g.fillRect(112, 208, 32, 22); }
      if (look.torso === 'uniform_officer') { g.fillStyle = '#c8b46a'; for (const x of [30, 196]) g.fillRect(x, 6, 30, 10); g.fillStyle = 'rgba(160,40,40,0.8)'; g.fillRect(40, 130, 46, 12); g.fillStyle = 'rgba(60,90,160,0.8)'; g.fillRect(40, 142, 46, 10); }
      if (look.gear.includes('webbing')) { g.strokeStyle = look.belt || '#4a4030'; g.lineWidth = 18; g.beginPath(); g.moveTo(40, 0); g.lineTo(90, 210); g.moveTo(216, 0); g.lineTo(166, 210); g.stroke(); }
      if (look.gear.includes('medbag') || look.hat?.medic) { g.fillStyle = '#f0f0f0'; g.fillRect(96, 90, 64, 64); g.fillStyle = '#c62828'; g.fillRect(118, 98, 20, 48); g.fillRect(104, 112, 48, 20); }
    } else if (look.torso === 'suit') {
      g.fillStyle = '#f2f2f2'; g.beginPath(); g.moveTo(84, 0); g.lineTo(128, 120); g.lineTo(172, 0); g.fill();
      g.fillStyle = look.tie || '#7a1f24'; g.beginPath(); g.moveTo(118, 10); g.lineTo(138, 10); g.lineTo(144, 120); g.lineTo(128, 140); g.lineTo(112, 120); g.fill();
      g.fillStyle = 'rgba(0,0,0,0.25)'; g.beginPath(); g.moveTo(84, 0); g.lineTo(118, 110); g.lineTo(70, 40); g.fill(); g.beginPath(); g.moveTo(172, 0); g.lineTo(138, 110); g.lineTo(186, 40); g.fill();
      for (const y of [160, 196]) { g.fillStyle = 'rgba(0,0,0,0.4)'; g.beginPath(); g.arc(128, y, 5, 0, 7); g.fill(); }
    } else if (look.torso === 'overalls') {
      g.fillStyle = '#3f5a7a'; g.fillRect(60, 90, 136, 166); g.fillRect(70, 0, 22, 100); g.fillRect(164, 0, 22, 100); g.fillStyle = '#c9b46a'; g.fillRect(74, 92, 12, 12); g.fillRect(170, 92, 12, 12);
    } else if (look.torso === 'sailor') {
      g.fillStyle = '#20283a'; g.beginPath(); g.moveTo(60, 0); g.lineTo(128, 90); g.lineTo(196, 0); g.fill(); g.fillStyle = '#fff'; g.fillRect(70, 4, 116, 6);
    } else if (look.torso === 'flight_jacket') {
      g.fillStyle = '#d9c9a8'; g.fillRect(0, 0, w, 40); g.fillStyle = dark; g.fillRect(126, 40, 4, 200); g.fillStyle = 'rgba(0,0,0,0.3)'; g.fillRect(0, 226, w, 30);
    } else if (look.torso === 'jacket') {
      g.fillStyle = dark; g.fillRect(122, 0, 12, 256); g.fillStyle = light; g.fillRect(0, 0, w, 18);
    } else {
      g.fillStyle = light; g.beginPath(); g.moveTo(100, 0); g.lineTo(128, 30); g.lineTo(156, 0); g.fill();
      if (Math.abs(look.shirt.charCodeAt(2) % 3) === 0) { g.fillStyle = 'rgba(255,255,255,0.16)'; for (let x = 0; x < w; x += 32) g.fillRect(x, 0, 12, h); }
    }
  });
}

/** classic studs: the block-game baseplate surface (on roofs, decks, crates and the map's baseplate) */
export function studTexture(color) {
  return canvasTex(`stud:${color}`, 128, 128, (g) => {
    g.fillStyle = color; g.fillRect(0, 0, 128, 128);
    for (const [x, y] of [[32, 32], [96, 32], [32, 96], [96, 96]]) {
      const gr = g.createRadialGradient(x - 6, y - 6, 2, x, y, 22); gr.addColorStop(0, 'rgba(255,255,255,0.35)'); gr.addColorStop(0.6, 'rgba(255,255,255,0.05)'); gr.addColorStop(1, 'rgba(0,0,0,0.25)');
      g.fillStyle = gr; g.beginPath(); g.arc(x, y, 19, 0, 7); g.fill();
    }
  }, { repeat: true });
}

/** windows for a facade: rows of panes with frames, a few lit at night */
export function facadeTexture(wall, floors, night, seed, style) {
  return canvasTex(`fac:${wall}:${floors}:${night}:${seed % 7}:${style}`, 256, 256, (g, w, h) => {
    g.fillStyle = wall; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 1400; i++) { g.fillStyle = `rgba(0,0,0,${R() * 0.05})`; g.fillRect(R() * w, R() * h, 3, 3); }
    if (style === 'stone_house' || style === 'church' || style === 'barn') { g.strokeStyle = 'rgba(0,0,0,0.07)'; for (let y = 0; y < h; y += 16) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); } }
    const rows = Math.max(1, floors), cols = 4, fh = h / rows;
    let r = seed;
    for (let ry = 0; ry < rows; ry++) for (let cx = 0; cx < cols; cx++) {
      r = (r * 1103515245 + 12345) & 0x7fffffff;
      const x = 18 + cx * (w - 36) / cols + 6, y = ry * fh + fh * 0.28, ww = (w - 36) / cols - 18, hh = fh * 0.46;
      if (ry === rows - 1 && cx === 1 && style !== 'church') { g.fillStyle = '#3a2a1c'; g.fillRect(x, ry * fh + fh * 0.3, ww, fh * 0.7); continue; }
      g.fillStyle = 'rgba(0,0,0,0.35)'; g.fillRect(x - 4, y - 4, ww + 8, hh + 8);
      const lit = night && (r % 5 < 2);
      g.fillStyle = lit ? '#ffcf7a' : night ? '#1c2430' : '#5d7286'; g.fillRect(x, y, ww, hh);
      if (!lit) { g.fillStyle = 'rgba(255,255,255,0.18)'; g.fillRect(x, y, ww * 0.35, hh); }
      if (style === 'concrete_block') { g.fillStyle = 'rgba(0,0,0,0.28)'; g.fillRect(x - 6, y - 8, ww + 12, 6); g.fillStyle = 'rgba(255,255,255,0.35)'; g.fillRect(x - 6, ry * fh + fh - 5, ww + 12, 5); }
      else { g.fillStyle = 'rgba(240,240,235,0.85)'; g.fillRect(x + ww / 2 - 2, y, 4, hh); g.fillRect(x, y + hh / 2 - 2, ww, 4); }
    }
  });
}

/** a fine grain for terrain and plaster (multiplied over vertex colours) */
export function grainTexture() {
  return canvasTex('grain', 256, 256, (g) => {
    g.fillStyle = '#bdbdbd'; g.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 9000; i++) { const v = 150 + Math.floor(R() * 105); g.fillStyle = `rgb(${v},${v},${v})`; g.fillRect(R() * 256, R() * 256, 2 + R() * 3, 2 + R() * 3); }
  }, { repeat: true });
}

export function labelTexture(text, opts = {}) {
  return canvasTex(`lbl:${text}:${JSON.stringify(opts)}`, opts.w || 512, opts.h || 128, (g, w, h) => {
    g.clearRect(0, 0, w, h); g.font = `${opts.weight || 800} ${opts.size || 64}px ${opts.font || 'HudTitle'}`; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillStyle = opts.color || '#fff'; g.fillText(text, w / 2, h / 2);
  });
}

export function mapNoteTexture() { return null; }
