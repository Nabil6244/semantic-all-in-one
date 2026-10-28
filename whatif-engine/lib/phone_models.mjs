// PHONE MODELS: a parametric, code-built phone that approximates any handset from a small spec, plus a preset catalog
// (whatif-engine/data/phones.json). Drop-in for product.mjs's buildPhone: same scene scale and orientation -- a THREE.Group centred
// on the origin, height 2 units along +y, screen facing +z, back (and camera bump) facing -z, buttons on the +x / -x edges.
//   model: { id, brand, name, w_mm, h_mm, d_mm, corner_mm, frame: "flat" | "rounded", frame_finish: "polished" | "brushed" | "matte",
//            frame_color: "#hex", back_color: "#hex", back_finish: "matte" | "glossy",
//            camera: { layout: one of PHONE_LAYOUTS, lenses?: [{ x, y, r }] (mm from the top-left of the back, seen from behind), flash: true },
//            wordmark?: "SAMSUNG", screen: { cutout: "punch" | "island" | "notch", bezel_mm }, buttons: "right" | "left" | "both",
//            colors?: [{ name, frame_color, back_color }], color?: "Titanium Silverblue" }
//   resolvePhone("galaxy s27 ultra") / resolvePhone({ id: "iphone_17_pro", color: "Cosmic Orange" }) -> a full model (preset + overrides;
//   an unknown name gives a sensible generic for its brand).
//   buildPhoneModel(THREE, model, { envMap, shot, screenMap? }) -> THREE.Group (userData: { W, H, D, model }).
// Deterministic: no Math.random (a seeded rng keyed on the model id).

export const PHONE_LAYOUTS = ['galaxy_ultra', 'galaxy_s', 'iphone_pro', 'iphone_base', 'pixel_bar', 'round_island', 'square_island', 'vertical_pill', 'galaxy_s27_island', 'galaxy_s27_video'];

// ---------- catalog ----------
let CATALOG = [];
try {
  if (typeof process !== 'undefined' && process.versions && process.versions.node) {
    const fs = await import('node:fs');
    CATALOG = JSON.parse(fs.readFileSync(new URL('../data/phones.json', import.meta.url), 'utf8')).phones || [];
  } else if (typeof fetch === 'function') {
    const r = await fetch(new URL('../data/phones.json', import.meta.url));
    if (r.ok) CATALOG = (await r.json()).phones || [];
  }
} catch { CATALOG = []; }
export function setPhoneCatalog(list) { if (Array.isArray(list)) CATALOG = list; else if (list && Array.isArray(list.phones)) CATALOG = list.phones; }
export function phoneCatalog() { return CATALOG; }

const GENERIC = {
  samsung: { brand: 'Samsung', name: 'Galaxy', w_mm: 77.6, h_mm: 162.8, d_mm: 8.2, corner_mm: 9, frame: 'flat', frame_finish: 'brushed', frame_color: '#9aa1a8', back_color: '#3b4148', back_finish: 'matte', camera: { layout: 'galaxy_ultra', flash: true }, wordmark: 'SAMSUNG', screen: { cutout: 'punch', bezel_mm: 1.3 }, buttons: 'right' },
  apple: { brand: 'Apple', name: 'iPhone', w_mm: 71.9, h_mm: 150.0, d_mm: 8.8, corner_mm: 11, frame: 'flat', frame_finish: 'brushed', frame_color: '#b9bcc0', back_color: '#c9ccd0', back_finish: 'matte', camera: { layout: 'iphone_pro', flash: true }, screen: { cutout: 'island', bezel_mm: 1.2 }, buttons: 'both' },
  google: { brand: 'Google', name: 'Pixel', w_mm: 72.0, h_mm: 152.8, d_mm: 8.5, corner_mm: 12, frame: 'rounded', frame_finish: 'polished', frame_color: '#c8c8c4', back_color: '#e9e6df', back_finish: 'glossy', camera: { layout: 'pixel_bar', flash: true }, wordmark: 'G', screen: { cutout: 'punch', bezel_mm: 1.6 }, buttons: 'right' },
  round: { brand: 'Generic', name: 'Phone', w_mm: 75.5, h_mm: 162.5, d_mm: 8.6, corner_mm: 11, frame: 'rounded', frame_finish: 'polished', frame_color: '#2a2c30', back_color: '#1f2226', back_finish: 'matte', camera: { layout: 'round_island', flash: true }, screen: { cutout: 'punch', bezel_mm: 1.4 }, buttons: 'right' },
  generic: { brand: 'Generic', name: 'Phone', w_mm: 74.0, h_mm: 160.0, d_mm: 8.3, corner_mm: 10, frame: 'flat', frame_finish: 'matte', frame_color: '#8f969d', back_color: '#2b3036', back_finish: 'matte', camera: { layout: 'square_island', flash: true }, screen: { cutout: 'punch', bezel_mm: 1.5 }, buttons: 'right' },
};
const BRAND_KEYS = [
  [/samsung|galaxy/, 'samsung', 'SAMSUNG'], [/apple|iphone/, 'apple', ''], [/google|pixel/, 'google', 'G'],
  [/oneplus/, 'round', 'OnePlus'], [/xiaomi|redmi|poco/, 'round', 'Xiaomi'], [/vivo/, 'round', 'vivo'], [/oppo/, 'round', 'OPPO'],
  [/honor/, 'round', 'HONOR'], [/huawei/, 'round', 'HUAWEI'], [/nothing/, 'generic', 'Nothing'], [/motorola|moto/, 'generic', 'M'],
  [/sony|xperia/, 'generic', 'SONY'],
];
const norm = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const tokens = (s) => norm(s).split(' ').filter(Boolean);
const isObj = (v) => v && typeof v === 'object' && !Array.isArray(v);
function merge(a, b) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b || {})) { if (v === undefined) continue; out[k] = isObj(v) && isObj(a[k]) ? merge(a[k], v) : v; }
  return out;
}
function findPreset(q) {
  const n = norm(q); if (!n) return null;
  const nid = n.replace(/ /g, '_');
  let hit = CATALOG.find((p) => p.id === nid || norm(p.id) === n || norm(p.name) === n || (p.aliases || []).some((a) => norm(a) === n));
  if (hit) return hit;
  const qt = tokens(q); let best = null, bestScore = 0;
  for (const p of CATALOG) {
    const pt = new Set([...tokens(p.name), ...tokens(p.brand), ...(p.aliases || []).flatMap(tokens)]);
    let score = 0; for (const t of qt) if (pt.has(t)) score += /^\d+$/.test(t) ? 2 : 1;
    const miss = tokens(p.name).filter((t) => !qt.includes(t)).length;           // "galaxy s25" should not land on "s25 ultra"
    score -= miss * 0.4;
    const numsQ = qt.filter((t) => /\d/.test(t)), numsP = tokens(p.name).filter((t) => /\d/.test(t));
    if (numsQ.length && numsP.length && !numsQ.some((t) => numsP.includes(t))) score -= 1.5;
    if (score > bestScore) { bestScore = score; best = p; }
  }
  return bestScore >= 1.5 ? best : null;
}
function genericFor(q) {
  const n = norm(q);
  for (const [re, key, mark] of BRAND_KEYS) if (re.test(n)) {
    const g = merge(GENERIC[key], {}); if (mark !== undefined && key !== 'apple') g.wordmark = mark || undefined;
    if (key === 'apple' && !/pro/.test(n)) g.camera = { layout: 'iphone_base', flash: true };
    if (key === 'samsung' && !/ultra/.test(n)) g.camera = { layout: 'galaxy_s', flash: true };
    return g;
  }
  return merge(GENERIC.generic, {});
}
export function resolvePhone(idOrSpec) {
  const spec = isObj(idOrSpec) ? idOrSpec : { id: idOrSpec };
  const key = spec.preset || spec.id || spec.name || spec.object || '';
  const hit = findPreset(key) || (spec.name && findPreset(spec.name)) || null;
  const base = hit || genericFor(`${spec.brand || ''} ${key}`);
  const { preset, object, ...over } = spec;
  if (hit) { if (over.id !== undefined && over.id !== hit.id) delete over.id; if (over.name !== undefined && findPreset(over.name) === hit) delete over.name; }
  else if (over.id === undefined && typeof key === 'string') over.id = norm(key).replace(/ /g, '_') || 'phone';
  else if (over.id !== undefined) over.id = norm(over.id).replace(/ /g, '_') || 'phone';
  if (!hit && over.name === undefined && key) over.name = String(key);
  let m = merge(base, over);
  if (!m.id) m.id = norm(m.name).replace(/ /g, '_') || 'phone';
  if (!m.name) m.name = String(key || 'Phone');
  const pick = spec.color || spec.colour;
  if (pick && Array.isArray(m.colors)) {
    const words = norm(pick).split(' ').filter((w) => w && w !== 'titanium');   // "Titanium White" still finds "White"
    const c = m.colors.find((o) => norm(o.name) === norm(pick)) || m.colors.find((o) => norm(o.name).includes(norm(pick)))
      || m.colors.find((o) => words.some((w) => norm(o.name).split(' ').includes(w)));
    if (c) m = merge(m, { frame_color: c.frame_color, back_color: c.back_color, color: c.name });
  } else if (!spec.frame_color && !spec.back_color && Array.isArray(m.colors) && m.colors[0] && !m.color) {
    m.color = m.colors[0].name; m.frame_color = m.colors[0].frame_color; m.back_color = m.colors[0].back_color;
  }
  m.camera = merge({ layout: 'square_island', flash: true }, m.camera || {});
  if (!PHONE_LAYOUTS.includes(m.camera.layout)) m.camera.layout = 'square_island';
  m.screen = merge({ cutout: 'punch', bezel_mm: 1.5 }, m.screen || {});
  for (const [k, d] of [['w_mm', 74], ['h_mm', 160], ['d_mm', 8.3], ['corner_mm', 10]]) if (!(Number(m[k]) > 0)) m[k] = d;
  m.frame = m.frame === 'rounded' ? 'rounded' : 'flat';
  m.frame_finish = ['polished', 'brushed', 'matte', 'satin'].includes(m.frame_finish) ? m.frame_finish : 'brushed';
  m.back_finish = ['glossy', 'satin'].includes(m.back_finish) ? m.back_finish : 'matte';
  m.buttons = ['right', 'left', 'both'].includes(m.buttons) ? m.buttons : 'right';
  m.frame_color = m.frame_color || '#9aa1a8'; m.back_color = m.back_color || '#2b3036';
  return m;
}

// ---------- geometry helpers ----------
function seeded(str) {
  let h = 2166136261; for (const ch of String(str)) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  let s = h >>> 0; return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}
function roundedRect(THREE, w, h, r) {
  r = Math.min(r, w / 2 - 1e-5, h / 2 - 1e-5);
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.absarc(x + w - r, y + r, r, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - r); s.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2, false);
  s.lineTo(x + r, y + h); s.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + r); s.absarc(x + r, y + r, r, Math.PI, Math.PI * 1.5, false);
  return s;
}
function circleShape(THREE, r) { const s = new THREE.Shape(); s.absarc(0, 0, r, 0, Math.PI * 2, false); return s; }
// an extruded shape centred on z = 0, bevelled; segs = bevel segments (crisp chamfer at 2-3, soft round at 8+)
function extrude(THREE, shape, depth, bevel, mat, segs = 6, curve = 40) {
  bevel = Math.min(bevel, depth / 2 - 1e-5);
  const geo = new THREE.ExtrudeGeometry(shape, { depth: Math.max(0.0002, depth - 2 * bevel), bevelEnabled: bevel > 0, bevelThickness: bevel,
    bevelSize: bevel, bevelSegments: segs, curveSegments: curve });
  geo.translate(0, 0, -(depth - 2 * bevel) / 2);
  return new THREE.Mesh(geo, mat);
}
const hasDOM = () => typeof document !== 'undefined' && typeof document.createElement === 'function';
function canvas(w, h) { if (!hasDOM()) return null; const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); return g ? { c, g } : null; }
function brushedTexture(THREE, rnd) {
  const cv = canvas(512, 512); if (!cv) return null; const { c, g } = cv;
  g.fillStyle = '#9a9a9a'; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 3600; i++) { const v = 115 + rnd() * 120 | 0; g.fillStyle = `rgba(${v},${v},${v},0.33)`; g.fillRect(rnd() * 512, rnd() * 512, 40 + rnd() * 260, 1); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(1, 3); t.anisotropy = 8; return t;
}
function lockScreen(THREE, model, shot) {
  const cv = canvas(540, 1170); if (!cv) return null; const { c, g } = cv;
  const tint = new THREE.Color(model.back_color), hsl = {}; tint.getHSL(hsl);
  const col = (l, s = 0.55, dh = 0) => `hsl(${((hsl.h + dh) * 360) | 0},${Math.round(Math.max(0.25, s) * 100)}%,${Math.round(l * 100)}%)`;
  const bg = g.createLinearGradient(0, 0, 540, 1170); bg.addColorStop(0, col(0.16)); bg.addColorStop(0.6, col(0.08, 0.5, 0.06)); bg.addColorStop(1, col(0.03));
  g.fillStyle = bg; g.fillRect(0, 0, 540, 1170);
  const orb = g.createRadialGradient(380, 820, 20, 380, 820, 520); orb.addColorStop(0, col(0.55, 0.8, -0.05)); orb.addColorStop(1, 'rgba(0,0,0,0)');
  g.globalAlpha = 0.85; g.fillStyle = orb; g.fillRect(0, 0, 540, 1170); g.globalAlpha = 1;
  const scr = (shot && shot.screen) || {};
  g.fillStyle = 'rgba(255,255,255,0.94)'; g.textAlign = 'center';
  g.font = '600 30px TMSans, sans-serif'; g.fillText(scr.date ?? 'Tue 27 Oct', 270, 250);
  g.font = '800 190px TMSans, sans-serif'; g.fillText(scr.time ?? '09:41', 270, 430);
  g.fillStyle = '#04050a'; const cut = model.screen.cutout;
  if (cut === 'island') { g.beginPath(); g.roundRect(190, 26, 160, 46, 23); g.fill(); }
  else if (cut === 'notch') { g.beginPath(); g.roundRect(150, -30, 240, 92, 30); g.fill(); }
  else { g.beginPath(); g.arc(270, 44, 13, 0, Math.PI * 2); g.fill(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function wordmarkTexture(THREE, text) {
  const cv = canvas(1024, 256); if (!cv) return null; const { c, g } = cv;
  g.fillStyle = '#000'; g.fillRect(0, 0, 1024, 256); g.fillStyle = '#fff'; g.textAlign = 'center'; g.textBaseline = 'middle';
  let px = 150; const w = String(text);
  const font = () => `700 ${px}px TMSans, Helvetica, Arial, sans-serif`;
  g.font = font(); while (px > 30 && g.measureText(w).width > 940) { px -= 6; g.font = font(); }
  if (g.letterSpacing !== undefined && /^[A-Z ]+$/.test(w)) g.letterSpacing = `${Math.round(px * 0.08)}px`;
  g.fillText(w, 512, 132);
  const t = new THREE.CanvasTexture(c); t.anisotropy = 8; return t;
}

// ---------- camera layouts (mm from the top-left of the back as seen from behind; island: { shape, x, y, w, h, r }) ----------
function layoutOf(model) {
  const w = model.w_mm, L = model.camera.layout, out = { island: null, lenses: [], flash: null, extras: [] };
  switch (L) {
    case 'galaxy_ultra':
      out.lenses = [{ x: 13, y: 13, r: 7.2 }, { x: 13, y: 30, r: 7.2 }, { x: 13, y: 47, r: 7.2 }, { x: 27, y: 14.5, r: 5.4 }];
      out.flash = { x: 27, y: 27, r: 2.2 }; out.extras = [{ x: 27, y: 34, r: 1.4, kind: 'sensor' }]; break;
    case 'galaxy_s':
      out.lenses = [{ x: 12.5, y: 12, r: 5.8 }, { x: 12.5, y: 25.5, r: 5.8 }, { x: 12.5, y: 39, r: 5.8 }];
      out.flash = { x: 23, y: 12, r: 2.0 }; break;
    case 'iphone_pro': {
      const s = Math.min(40, w * 0.52);
      out.island = { shape: 'rect', x: 4.5 + s / 2, y: 4.5 + s / 2, w: s, h: s, r: 9 };
      const k = s / 38;
      out.lenses = [{ x: 4.5 + 11 * k, y: 4.5 + 10.5 * k, r: 7.4 * k }, { x: 4.5 + 11 * k, y: 4.5 + 27.5 * k, r: 7.4 * k }, { x: 4.5 + 27 * k, y: 4.5 + 19 * k, r: 7.4 * k }];
      out.flash = { x: 4.5 + 29.5 * k, y: 4.5 + 7 * k, r: 2.3 }; out.extras = [{ x: 4.5 + 29.5 * k, y: 4.5 + 31 * k, r: 2.6, kind: 'lidar' }, { x: 4.5 + 20 * k, y: 4.5 + 34 * k, r: 0.7, kind: 'mic' }]; break;
    }
    case 'iphone_base':
      out.island = { shape: 'rect', x: 20, y: 20, w: 31, h: 31, r: 8 };
      out.lenses = [{ x: 12, y: 12, r: 6.4 }, { x: 28, y: 28, r: 6.4 }]; out.flash = { x: 28, y: 11, r: 2.0 }; out.extras = [{ x: 20.5, y: 20.5, r: 0.7, kind: 'mic' }]; break;
    case 'pixel_bar':
      out.island = { shape: 'bar', x: w / 2, y: 22, w: w + 0.2, h: 16, r: 8 };
      out.inner = { x: w / 2 - 3, y: 22, w: w * 0.62, h: 11.5, r: 5.75 };
      out.lenses = [{ x: w / 2 - 15, y: 22, r: 5.0 }, { x: w / 2 - 3, y: 22, r: 5.0 }, { x: w / 2 + 9, y: 22, r: 4.2 }];
      out.flash = { x: w / 2 + 22, y: 19.5, r: 1.8 }; out.extras = [{ x: w / 2 + 22, y: 24.5, r: 1.3, kind: 'sensor' }]; break;
    case 'round_island': {
      const R = Math.min(19, w * 0.25), cx = w / 2, cy = 8 + R;
      out.island = { shape: 'circle', x: cx, y: cy, w: R * 2, h: R * 2, r: R };
      const o = R * 0.47, lr = R * 0.3;
      out.lenses = [{ x: cx - o, y: cy - o, r: lr }, { x: cx + o, y: cy - o, r: lr }, { x: cx - o, y: cy + o, r: lr }, { x: cx + o, y: cy + o, r: lr * 0.85 }];
      out.flash = { x: cx + R + 4, y: cy - 4, r: 1.8 }; out.extras = [{ x: cx, y: cy, r: 0.9, kind: 'sensor' }]; break;
    }
    case 'vertical_pill':
      out.island = { shape: 'rect', x: 14, y: 26, w: 17, h: 40, r: 8.5 };
      out.lenses = [{ x: 14, y: 15, r: 6.2 }, { x: 14, y: 32.5, r: 6.2 }]; out.flash = { x: 14, y: 51, r: 2.0 }; break;
    case 'galaxy_s27_island': {   // S27 Ultra leak: big two-level rounded plate, two big lenses on top, a pill (3rd lens + LED + laser AF) below
      const g = 3.6, iw = w * 0.73, ih = model.h_mm * 0.32, x0 = g, y0 = g, cx = x0 + iw / 2;
      out.island = { shape: 'rect', x: cx, y: y0 + ih / 2, w: iw, h: ih, r: 9.5 };
      out.plateau = { x: cx, y: y0 + ih / 2, w: iw - 2.6, h: ih - 2.6, r: 8.2 };       // the upper step of the CAD's stepped edge
      const lr = iw * 0.15, ly = y0 + ih * 0.27;
      out.lenses = [{ x: cx - iw * 0.2, y: ly, r: lr, ring: 1.24 }, { x: cx + iw * 0.2, y: ly, r: lr, ring: 1.24 }];
      const py = y0 + ih * 0.62, pw = iw * 0.58, ph = ih * 0.2;
      out.pill = { x: cx, y: py, w: pw, h: ph, r: ph / 2 };
      out.pillLenses = [{ x: cx - pw / 2 + ph / 2 + 0.6, y: py, r: ph * 0.36 }];
      out.flash = { x: cx + pw * 0.06, y: py, r: ph * 0.14 };
      out.extras = [{ x: cx + pw * 0.26, y: py, r: ph * 0.17, kind: 'sensor' }];
      out.magnet = { x: w / 2, y: model.h_mm * 0.54, r: w * 0.3 };
      break;
    }
    case 'galaxy_s27_video': {    // "Introducing The Galaxy S27 Ultra" video design, measured from the back close-ups (fractions of phone width):
      // satin plateau in the back colour: 2.5 mm margins, ~93% wide, top 3.3% -> bottom 58% of the width, corner ~8%;
      // two big stacked lenses (outer dia 21.6% w) at x 17% / y 18.7% + 42.6%; a vertical black capsule (w 15.7%, y 13.8%-47.5%)
      // at x 41.3% holding the LED (y 30%) and a small lens (y 40%).
      const k = w, g = 0.033 * k, ih = 0.547 * k, iw = w - 2 * g;
      out.island = { shape: 'rect', x: w / 2, y: g + ih / 2, w: iw, h: ih, r: 0.085 * k };
      const lr = 0.099 * k;
      out.lenses = [{ x: 0.17 * k, y: 0.187 * k, r: lr, ring: 1.09 }, { x: 0.17 * k, y: 0.426 * k, r: lr, ring: 1.09 }];
      const pw = 0.157 * k, pt = 0.138 * k, pb = 0.475 * k;
      out.pill = { x: 0.413 * k, y: (pt + pb) / 2, w: pw, h: pb - pt, r: pw / 2, style: 'glass' };
      out.flash = { x: 0.413 * k, y: 0.30 * k, r: 0.016 * k };
      out.pillLenses = [{ x: 0.413 * k, y: 0.40 * k, r: 0.034 * k }];
      break;
    }
    case 'square_island':
    default:
      out.island = { shape: 'rect', x: 21, y: 21, w: 32, h: 32, r: 7 };
      out.lenses = [{ x: 13.5, y: 13.5, r: 5.6 }, { x: 28.5, y: 13.5, r: 5.6 }, { x: 13.5, y: 28.5, r: 5.6 }];
      out.flash = { x: 28.5, y: 28.5, r: 2.0 }; break;
  }
  if (Array.isArray(model.camera.lenses) && model.camera.lenses.length) out.lenses = model.camera.lenses.map((l) => ({ x: +l.x, y: +l.y, r: +l.r || 5, ring: +l.ring || undefined }));
  if (model.camera.flash === false) out.flash = null;
  return out;
}

// ---------- the builder ----------
export function buildPhoneModel(THREE, model, { envMap = null, shot = {}, screenMap = null } = {}) {
  const m = model && model.camera && model.screen ? model : resolvePhone(model || 'phone');
  const rnd = seeded(m.id || m.name || 'phone');
  const s = 2 / m.h_mm, mm = (v) => v * s;
  const W = mm(m.w_mm), H = 2, D = mm(m.d_mm), CR = mm(m.corner_mm);
  const frameCol = new THREE.Color(m.frame_color), backCol = new THREE.Color(m.back_color);
  const brushed = brushedTexture(THREE, rnd);
  const fin = m.frame_finish;
  const frameMat = new THREE.MeshPhysicalMaterial({ color: frameCol, metalness: 1, envMap,
    roughness: fin === 'polished' ? 0.09 : fin === 'brushed' ? 0.3 : fin === 'satin' ? 0.36 : 0.5, roughnessMap: fin === 'polished' || fin === 'satin' ? null : brushed,
    anisotropy: fin === 'brushed' ? 0.75 : fin === 'matte' ? 0.2 : 0, anisotropyRotation: Math.PI / 2,
    clearcoat: fin === 'polished' ? 0.6 : 0.1, clearcoatRoughness: 0.08, envMapIntensity: fin === 'polished' ? 1.7 : 1.35 });
  const glossy = m.back_finish === 'glossy';
  const light = backCol.getHSL({}).l > 0.72;   // white/near-white backs blow out under the studio rig: tame the reflections, keep the tone
  const satin = m.back_finish === 'satin';   // frosted, matte-satin glass (no gloss, no brushing)
  const backMat = satin
    ? new THREE.MeshPhysicalMaterial({ color: light ? backCol.clone().multiplyScalar(0.7) : backCol, metalness: 0, envMap, roughness: 0.55, clearcoat: 0.12, clearcoatRoughness: 0.6,
      sheen: 0.25, sheenRoughness: 0.7, sheenColor: backCol.clone().lerp(new THREE.Color('#ffffff'), 0.3), ior: 1.5, envMapIntensity: light ? 0.6 : 0.95 })
    : new THREE.MeshPhysicalMaterial({ color: light ? backCol.clone().multiplyScalar(0.62) : backCol, metalness: 0.05, envMap, roughness: glossy ? 0.08 : 0.52,
    clearcoat: light ? 0.5 : 1, clearcoatRoughness: glossy ? 0.03 : 0.55, sheen: glossy || light ? 0 : 0.35, sheenRoughness: 0.6, sheenColor: backCol.clone().lerp(new THREE.Color('#ffffff'), 0.35),
    ior: 1.5, envMapIntensity: light ? 0.55 : glossy ? 1.6 : 1.1 });
  const darkMetal = new THREE.MeshPhysicalMaterial({ color: '#16191f', metalness: 1, roughness: 0.32, envMap, envMapIntensity: 1.0 });
  const glassBlack = new THREE.MeshPhysicalMaterial({ color: '#020306', metalness: 0.1, roughness: 0.03, clearcoat: 1, clearcoatRoughness: 0.02, envMap, envMapIntensity: 1.8 });
  const holeMat = new THREE.MeshPhysicalMaterial({ color: '#020203', metalness: 0, roughness: 0.9 });
  const antennaMat = new THREE.MeshPhysicalMaterial({ color: frameCol.clone().multiplyScalar(0.55).lerp(new THREE.Color('#40444a'), 0.5), metalness: 0, roughness: 0.6, clearcoat: 0.4, envMap, envMapIntensity: 0.6 });
  const grp = new THREE.Group();

  // frame: flat sides get a crisp chamfer, rounded sides a soft roll
  const fb = m.frame === 'rounded' ? D * 0.42 : mm(0.45);
  grp.add(extrude(THREE, roundedRect(THREE, W - 2 * fb, H - 2 * fb, Math.max(0.005, CR - fb)), D, fb, frameMat, m.frame === 'rounded' ? 12 : 3, 48));
  // back glass, flush with a hair of lip
  const bt = mm(0.7), inset = m.frame === 'rounded' ? fb * 0.85 : mm(0.9);
  const back = extrude(THREE, roundedRect(THREE, W - 2 * inset, H - 2 * inset, Math.max(0.005, CR - inset)), bt, bt * 0.35, backMat, 4, 48);
  const backZ = -D / 2 - bt / 2 + mm(0.25); back.position.z = backZ; grp.add(back);
  const backFace = backZ - bt / 2;

  // front: black glass, the picture, a faint reflective sheen
  const fi = m.frame === 'rounded' ? fb * 0.7 : mm(0.7);
  const fw = W - 2 * fi, fh = H - 2 * fi, fr = Math.max(0.005, CR - fi);
  const bezel = extrude(THREE, roundedRect(THREE, fw, fh, fr), mm(0.7), mm(0.25), glassBlack, 4, 48); bezel.position.z = D / 2 - mm(0.1); grp.add(bezel);
  const bz = mm(m.screen.bezel_mm ?? 1.5), sw = fw - 2 * bz, sh = fh - 2 * bz, sr = Math.max(0.004, fr - bz);
  const scrGeo = new THREE.ShapeGeometry(roundedRect(THREE, sw, sh, sr), 32);
  const uv = scrGeo.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, (uv.getX(i) + sw / 2) / sw, (uv.getY(i) + sh / 2) / sh);
  const map = screenMap || lockScreen(THREE, m, shot);
  const scr = new THREE.Mesh(scrGeo, new THREE.MeshBasicMaterial({ map, color: map ? '#d8d8dc' : '#05070c', toneMapped: false }));
  scr.position.z = D / 2 + mm(0.27); grp.add(scr);
  const sheen = new THREE.Mesh(scrGeo.clone(), new THREE.MeshPhysicalMaterial({ color: '#000', transparent: true, opacity: 0.12, roughness: 0.02, metalness: 0, clearcoat: 1, envMap, envMapIntensity: 0.9, depthWrite: false }));
  sheen.position.z = D / 2 + mm(0.32); grp.add(sheen);

  // back coordinates: mm from the top-left as seen from behind -> model x is mirrored
  const bx = (x) => W / 2 - mm(x), by = (y) => H / 2 - mm(y);
  const lay = layoutOf(m);
  const cam = new THREE.Group(); grp.add(cam);
  let lensBase = backFace;
  if (lay.island) {
    const I = lay.island, depth = mm(L_ISLAND[m.camera.layout] ?? 1.6);
    const shape = I.shape === 'circle' ? circleShape(THREE, mm(I.r)) : roundedRect(THREE, mm(I.w), mm(I.h), mm(I.r));
    const islandMat = I.shape === 'bar' || m.camera.layout === 'iphone_pro' ? frameMat
      : satin ? new THREE.MeshPhysicalMaterial({ color: light ? backCol.clone().multiplyScalar(0.68) : backCol.clone().multiplyScalar(0.97), metalness: 0, roughness: 0.42, clearcoat: 0.25, clearcoatRoughness: 0.4,
        sheen: 0.3, sheenRoughness: 0.6, sheenColor: backCol.clone().lerp(new THREE.Color('#ffffff'), 0.35), envMap, envMapIntensity: light ? 0.7 : 1.05 })
      : new THREE.MeshPhysicalMaterial({ color: backCol.clone().multiplyScalar(light ? 0.6 : 0.92), metalness: light ? 0.1 : 0.3, roughness: glossy ? 0.08 : 0.35, clearcoat: 1, clearcoatRoughness: 0.05, envMap, envMapIntensity: light ? 0.7 : 1.4 });
    const isl = extrude(THREE, shape, depth, depth * 0.45, islandMat, 8, 64);
    isl.position.set(bx(I.x), by(I.y), backFace - depth / 2 + mm(0.1)); cam.add(isl);
    if (I.shape === 'circle') {   // the bright chamfered ring that circular modules wear
      const ring = new THREE.Mesh(new THREE.TorusGeometry(mm(I.r) * 0.985, mm(0.55), 16, 128), frameMat);
      ring.position.set(bx(I.x), by(I.y), backFace - depth + mm(0.1)); cam.add(ring);
    }
    if (lay.inner) {              // Pixel visor: black glass strip inside the metal bar
      const N = lay.inner, g = extrude(THREE, roundedRect(THREE, mm(N.w), mm(N.h), mm(N.r)), mm(0.5), mm(0.2), glassBlack, 4, 48);
      g.position.set(bx(N.x), by(N.y), backFace - depth - mm(0.15)); cam.add(g);
    }
    lensBase = backFace - depth + mm(0.1);
    if (lay.plateau) {            // second, smaller step on top of the plate (stepped plateau edge)
      const P = lay.plateau, pd = mm(0.7);
      const pl = extrude(THREE, roundedRect(THREE, mm(P.w), mm(P.h), mm(P.r)), pd, pd * 0.5, islandMat, 6, 64);
      pl.position.set(bx(P.x), by(P.y), lensBase - pd / 2 + mm(0.05)); cam.add(pl);
      lensBase -= pd - mm(0.05);
    }
  }
  if (lay.magnet) {               // Qi2 magnet ring: a hairline in the glass
    const G = lay.magnet, mg = new THREE.Mesh(new THREE.RingGeometry(mm(G.r) - mm(0.14), mm(G.r) + mm(0.14), 160),
      new THREE.MeshBasicMaterial({ color: backCol.getHSL({}).l > 0.5 ? '#000000' : '#ffffff', transparent: true, opacity: 0.07, depthWrite: false }));
    mg.rotation.y = Math.PI; mg.position.set(bx(G.x), by(G.y), backFace - mm(0.03)); grp.add(mg);
  }
  // real camera glass: near-black with only a faint blue/violet AR cast (never amber/green)
  const AR = ['#3a4dff', '#5a3cff', '#2f6bff'];
  const arCol = new THREE.Color(AR[(rnd() * AR.length) | 0]);
  // cover glass: reflections only over a dark see-through tint (WebGL transmission blurs the bright scene behind it -> milky lenses)
  const coverGlass = new THREE.MeshPhysicalMaterial({ color: '#000000', metalness: 0, roughness: 0.0, transparent: true, opacity: 0.5, depthWrite: false,
    clearcoat: 1, clearcoatRoughness: 0.0, envMap, envMapIntensity: 0.9, specularIntensity: 1, ior: 1.77 });
  const elementMat = new THREE.MeshPhysicalMaterial({ color: '#010205', metalness: 0.2, roughness: 0.04, clearcoat: 1, clearcoatRoughness: 0.02,
    iridescence: 0.45, iridescenceIOR: 1.45, iridescenceThicknessRange: [260, 340], envMap, envMapIntensity: 0.7 });
  // lens collars: same metal as the frame but kept off the bloom threshold (bright frames read as glowing rings)
  const collarMat = frameMat.clone(); collarMat.envMapIntensity = Math.min(frameMat.envMapIntensity, light ? 0.75 : 1.1); collarMat.roughness = Math.max(frameMat.roughness, 0.22);
  if (light || frameCol.getHSL({}).l > 0.7) collarMat.color = frameCol.clone().multiplyScalar(0.62);
  const slotGlass = glassBlack.clone(); slotGlass.color = new THREE.Color('#010103'); slotGlass.envMapIntensity = 0.6;
  const barrelDark = new THREE.MeshPhysicalMaterial({ color: '#020204', metalness: 0.3, roughness: 0.6, envMap, envMapIntensity: 0.25 });
  const arMat = new THREE.MeshPhysicalMaterial({ color: arCol.clone().multiplyScalar(0.06), emissive: arCol, emissiveIntensity: 0.025, metalness: 0.3, roughness: 0.12,
    iridescence: 0.35, iridescenceIOR: 1.4, iridescenceThicknessRange: [260, 340], envMap, envMapIntensity: 1.1, side: THREE.DoubleSide });
  const innerRingMat = new THREE.MeshPhysicalMaterial({ color: '#0b0d14', metalness: 0.9, roughness: 0.25, envMap, envMapIntensity: 0.9, side: THREE.DoubleSide });
  const V = (r, h) => new THREE.Vector2(r, h);
  const lathe = (pts, mat) => { const g = new THREE.LatheGeometry(pts, 96); g.rotateX(-Math.PI / 2); return new THREE.Mesh(g, mat); };
  const floating = !lay.island;
  const lens = (L) => {
    const R = mm(L.r), l = new THREE.Group(), rise = mm(L.flush ? 0.5 : floating ? 1.6 : 1.1), o = L.ring || 1.16, q = (o - 1) / 0.16;
    l.position.set(bx(L.x), by(L.y), L.base ?? lensBase);
    // metal collar: a stepped, chamfered ring standing proud of the surface (lathe height h -> z = -h, outward)
    l.add(lathe([V(R * o, -0.0002), V(R * o, rise * 0.35), V(R * (1 + 0.13 * q), rise * 0.75), V(R * (1 + 0.07 * q), rise), V(R * 1.0, rise), V(R * 0.99, rise * 0.6), V(R * 0.95, rise * 0.55)], collarMat));
    l.add(lathe([V(R * 0.95, rise * 0.55), V(R * 0.93, -mm(1.2)), V(R * 0.2, -mm(1.4))], barrelDark));                     // barrel wall + floor (sinks into the body)
    const ar = new THREE.Mesh(new THREE.RingGeometry(R * 0.5, R * 0.88, 96), arMat); ar.rotation.y = Math.PI; ar.position.z = -rise * 0.05; l.add(ar);   // AR-coated ring
    for (const [a, b2, z] of [[0.86, 0.885, 0.07], [0.66, 0.68, 0.12], [0.44, 0.455, 0.18], [0.3, 0.31, 0.22]]) {   // inner element rings
      const rr = new THREE.Mesh(new THREE.RingGeometry(R * a, R * b2, 96), innerRingMat); rr.rotation.y = Math.PI; rr.position.z = -R * z * 0.5; l.add(rr);
    }
    const el = new THREE.Mesh(new THREE.SphereGeometry(R * 0.55, 48, 24, 0, Math.PI * 2, 0, 0.75), elementMat);                // the dark front element
    el.geometry.scale(1, 0.45, 1); el.geometry.rotateX(-Math.PI / 2); el.geometry.translate(0, 0, R * 0.05); l.add(el);
    const pupil = new THREE.Mesh(new THREE.CircleGeometry(R * 0.16, 48), new THREE.MeshBasicMaterial({ color: '#000000' })); pupil.rotation.y = Math.PI; pupil.position.z = -R * 0.2; l.add(pupil);
    const cov = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.99, R * 0.99, mm(0.5), 96), coverGlass);                       // sapphire cover glass
    cov.rotation.x = Math.PI / 2; cov.position.z = -rise * 0.82; l.add(cov);
    cam.add(l);
  };
  lay.lenses.forEach(lens);
  if (lay.pill) {                 // the pill: metal rim (or a plain black glass capsule), black glass slot, lens + flash + sensor inside
    const P = lay.pill;
    if (P.style !== 'glass') {
      const rim = extrude(THREE, roundedRect(THREE, mm(P.w + 1.4), mm(P.h + 1.4), mm(P.r + 0.7)), mm(0.6), mm(0.2), collarMat, 4, 64);
      rim.position.set(bx(P.x), by(P.y), lensBase - mm(0.25)); cam.add(rim);
    }
    const slot = extrude(THREE, roundedRect(THREE, mm(P.w), mm(P.h), mm(P.r)), mm(0.5), mm(0.15), slotGlass, 4, 64);
    slot.position.set(bx(P.x), by(P.y), lensBase - mm(0.45)); cam.add(slot);
    lensBase -= mm(0.7);
    (lay.pillLenses || []).forEach((L) => lens({ ...L, flush: true, ring: 1.1 }));
  }
  if (lay.flash) {
    const f = lay.flash, fl = new THREE.Group(); fl.position.set(bx(f.x), by(f.y), lensBase - mm(0.05));
    const lensF = new THREE.Mesh(new THREE.CircleGeometry(mm(f.r), 48), new THREE.MeshPhysicalMaterial({ color: '#f3e6c8', emissive: '#ffcf8a', emissiveIntensity: 0.25, roughness: 0.25, clearcoat: 1, envMap, envMapIntensity: 1.2 }));
    lensF.rotation.y = Math.PI; fl.add(lensF);
    const rim = new THREE.Mesh(new THREE.RingGeometry(mm(f.r), mm(f.r) * 1.25, 48), darkMetal); rim.rotation.y = Math.PI; rim.position.z = -mm(0.01); fl.add(rim);
    cam.add(fl);
  }
  for (const e of lay.extras) {
    const d = new THREE.Mesh(new THREE.CircleGeometry(mm(e.r), 32), e.kind === 'mic' ? holeMat : glassBlack);
    d.rotation.y = Math.PI; d.position.set(bx(e.x), by(e.y), lensBase - mm(0.05)); cam.add(d);
  }

  // wordmark: low-contrast, slightly embossed print on the back glass
  if (m.wordmark) {
    const tex = wordmarkTexture(THREE, m.wordmark);
    if (tex) {
      const ww = Math.min(W * 0.42, mm(32)), wh = ww / 4;
      const mark = new THREE.Mesh(new THREE.PlaneGeometry(ww, wh), new THREE.MeshPhysicalMaterial({ color: backCol.clone().lerp(new THREE.Color(backCol.getHSL({}).l > 0.5 ? '#000' : '#fff'), 0.18),
        alphaMap: tex, transparent: true, bumpMap: tex, bumpScale: 1.2, metalness: 0.5, roughness: 0.3, clearcoat: 1, envMap, envMapIntensity: 1.3, depthWrite: false }));
      mark.rotation.y = Math.PI; mark.position.set(0, -H * 0.3, backFace - mm(0.02)); grp.add(mark);
    }
  }

  // side keys (bevelled pills standing off the frame), USB-C, speaker grille, mic, antenna bands
  const key = (side, y, len) => {
    const k = extrude(THREE, roundedRect(THREE, mm(1.2), len, mm(0.6)), D * 0.38, mm(0.25), frameMat, 4, 24);
    k.rotation.y = Math.PI / 2; k.position.set(side * (W / 2 + mm(0.25)), y, 0); grp.add(k);
  };
  const R_ = 1, L_ = -1, b = m.buttons;
  if (b === 'right') { key(R_, H * 0.22, mm(26)); key(R_, H * 0.04, mm(13)); }
  else if (b === 'left') { key(L_, H * 0.22, mm(26)); key(L_, H * 0.04, mm(13)); }
  else { key(R_, H * 0.12, mm(18)); key(L_, H * 0.26, mm(11)); key(L_, H * 0.17, mm(11)); key(L_, H * 0.33, mm(6)); }
  const port = extrude(THREE, roundedRect(THREE, mm(8.6), mm(2.8), mm(1.4)), mm(1.2), mm(0.2), glassBlack, 3, 24);
  port.rotation.x = Math.PI / 2; port.position.set(0, -H / 2 + mm(0.4), 0); grp.add(port);
  const hole = (x, r) => { const h = new THREE.Mesh(new THREE.CylinderGeometry(mm(r), mm(r), mm(1.2), 20), holeMat); h.position.set(x, -H / 2 + mm(0.4), 0); grp.add(h); };
  for (let i = 0; i < 6; i++) hole(mm(9 + i * 2.1), 0.55);        // speaker grille
  hole(-mm(9), 0.45); hole(-mm(11), 0.45);                          // mics
  const top = new THREE.Mesh(new THREE.CylinderGeometry(mm(0.4), mm(0.4), mm(1.2), 16), holeMat); top.position.set(-mm(14), H / 2 - mm(0.4), 0); grp.add(top);
  const band = (x, y, vertical) => {   // a thin plastic break through the metal frame
    const g = new THREE.BoxGeometry(vertical ? mm(0.6) : mm(0.3), vertical ? mm(0.3) : mm(0.6), D * 0.86);
    const a = new THREE.Mesh(g, antennaMat); a.position.set(x, y, 0); grp.add(a);
  };
  const ex = W / 2 + mm(0.02), ey = H / 2 + mm(0.02);
  band(ex, H / 2 - mm(17), false); band(-ex, H / 2 - mm(17), false); band(ex, -H / 2 + mm(17), false); band(-ex, -H / 2 + mm(17), false);
  band(W / 2 - mm(14), ey, true); band(-W / 2 + mm(14), -ey, true);

  grp.userData = { W, H, D, model: m, scale_per_mm: s };
  return grp;
}
// island heights (mm) per layout
const L_ISLAND = { iphone_pro: 1.9, iphone_base: 1.5, pixel_bar: 2.2, round_island: 2.4, square_island: 1.6, vertical_pill: 1.4, galaxy_s27_island: 0.9, galaxy_s27_video: 1.1 };
