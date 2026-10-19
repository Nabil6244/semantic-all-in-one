// Frame-by-frame overlap check of a What If spec, without a browser: node tools/overlap_audit.mjs <spec.json> [--fps 10]
// Every layer is drawn on a recording canvas at each sampled frame; the canvas keeps the box of every piece of text (font size,
// alignment, letter spacing and the current transform included) and of every card / panel a layer fills, with the opacity it was
// drawn at. Two layers clash when one's visible text overlaps the other's visible text or card. One JSON line on stdout:
// { clashes: [{ a, b, start, end, a_text, b_text, area }], frames }, a and b being indexes into spec.layers.
// Text widths are estimated from the font (the page measures real glyphs), so boxes are approximate within a few percent.
import fs from 'node:fs';
import { createRegistry } from '../lib/layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';
import { sanitizeShots, shotAt } from '../lib/shots.mjs';
import { opacityAt } from '../lib/timing.mjs';

const VISIBLE = 0.35;          // a layer drawn fainter than this (fading in or out) is not counted
const MIN_OVERLAP_PX = 600;    // at 1920x1080: smaller touches (a letter's corner) are not a clash
const WIDTH_K = { display: 0.66, mono: 0.6, sans: 0.56 };

function fontInfo(font) {
  const m = /(\d+(?:\.\d+)?)px\s*(.*)$/.exec(String(font || ''));
  const px = m ? parseFloat(m[1]) : 10;
  const fam = m ? m[2] : '';
  const kind = /StarMapSans|Montserrat/i.test(fam.split(',')[0]) ? 'display' : /Mono|Menlo|Consolas/i.test(fam) ? 'mono' : 'sans';
  return { px, kind, bold: /\b(7|8|9)00\b|bold/i.test(font) };
}

/** A 2D context that draws nothing and records boxes (in frame pixels) of text and filled shapes. */
export function recordingCanvas(W, H) {
  const mul = (a, b) => [a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
    a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]];
  const ap = (m, x, y) => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
  let st = { m: [1, 0, 0, 1, 0, 0], font: '10px sans-serif', align: 'start', base: 'alphabetic', alpha: 1, spacing: 0, fill: '#000' };
  const stack = [];
  const out = [];
  let path = null;
  const grad = { addColorStop() {} };
  const width = (s) => {
    const f = fontInfo(st.font);
    return String(s).length * f.px * WIDTH_K[f.kind] * (f.bold && f.kind === 'sans' ? 1.06 : 1) + String(s).length * st.spacing;
  };
  const boxOf = (pts) => {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  };
  // a shape counts as a card only when its fill is a solid, mostly opaque colour: gradients, patterns and faint washes are backdrops
  const solid = () => {
    const f = st.fill;
    if (typeof f !== 'string') return false;
    const m = /rgba?\(([^)]*)\)/i.exec(f);
    if (m) { const p = m[1].split(',').map((x) => parseFloat(x)); return p.length < 4 || p[3] >= 0.5; }
    if (/^#[0-9a-f]{8}$/i.test(f)) return parseInt(f.slice(7, 9), 16) / 255 >= 0.5;
    return f !== 'transparent';
  };
  const push = (kind, x0, y0, x1, y1, text = '') => {
    if (kind === 'shape' && !solid()) return;
    const b = boxOf([ap(st.m, x0, y0), ap(st.m, x1, y0), ap(st.m, x0, y1), ap(st.m, x1, y1)]);
    if (!(b.every(Number.isFinite))) return;
    out.push({ kind, box: b, alpha: st.alpha, text });
  };
  const textBox = (s, x, y) => {
    const f = fontInfo(st.font), w = width(s);
    const a = st.align === 'center' ? -w / 2 : (st.align === 'right' || st.align === 'end') ? -w : 0;
    const asc = f.px * 0.74, desc = f.px * 0.2;
    const top = st.base === 'top' || st.base === 'hanging' ? 0 : st.base === 'middle' ? -(asc + desc) / 2 + desc * 0.1 - asc * 0 : st.base === 'bottom' || st.base === 'ideographic' ? -(asc + desc) : -asc;
    const y0 = st.base === 'middle' ? y - (asc + desc) / 2 : y + top;
    push('text', x + a, y0, x + a + w, y0 + asc + desc, String(s));
  };
  const target = {
    canvas: { width: W, height: H },
    get globalAlpha() { return st.alpha; }, set globalAlpha(v) { st.alpha = Number.isFinite(v) ? v : st.alpha; },
    get font() { return st.font; }, set font(v) { st.font = v; },
    get fillStyle() { return st.fill; }, set fillStyle(v) { st.fill = v; },
    get textAlign() { return st.align; }, set textAlign(v) { st.align = v; },
    get textBaseline() { return st.base; }, set textBaseline(v) { st.base = v; },
    get letterSpacing() { return `${st.spacing}px`; }, set letterSpacing(v) { st.spacing = parseFloat(v) || 0; },
    save() { stack.push({ ...st, m: [...st.m] }); }, restore() { if (stack.length) st = stack.pop(); },
    translate(x, y) { st.m = mul(st.m, [1, 0, 0, 1, x, y]); }, scale(x, y) { st.m = mul(st.m, [x, 0, 0, y, 0, 0]); },
    rotate(r) { const c = Math.cos(r), s = Math.sin(r); st.m = mul(st.m, [c, s, -s, c, 0, 0]); },
    transform(a, b, c, d, e, f) { st.m = mul(st.m, [a, b, c, d, e, f]); },
    setTransform(a, b, c, d, e, f) { st.m = typeof a === 'object' && a ? [a.a, a.b, a.c, a.d, a.e, a.f] : [a, b, c, d, e, f]; },
    resetTransform() { st.m = [1, 0, 0, 1, 0, 0]; }, getTransform() { const [a, b, c, d, e, f] = st.m; return { a, b, c, d, e, f }; },
    measureText(s) { const f = fontInfo(st.font); return { width: width(s), actualBoundingBoxAscent: f.px * 0.74, actualBoundingBoxDescent: f.px * 0.2 }; },
    fillText(s, x, y) { textBox(s, x, y); }, strokeText(s, x, y) { textBox(s, x, y); },
    fillRect(x, y, w, h) { push('shape', x, y, x + w, y + h); },
    beginPath() { path = []; }, rect(x, y, w, h) { (path ||= []).push([x, y], [x + w, y + h]); },
    roundRect(x, y, w, h) { (path ||= []).push([x, y], [x + w, y + h]); },
    fill() { if (path && path.length) { const xs = path.map((p) => p[0]), ys = path.map((p) => p[1]); push('shape', Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)); } },
    createRadialGradient: () => grad, createLinearGradient: () => grad, createPattern: () => ({}), getLineDash: () => [],
    createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
    getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(Math.max(1, w * h * 4)), width: w, height: h }),
  };
  const g = new Proxy(target, {
    get(o, k) { if (k in o) return o[k]; return () => {}; },
    set(o, k, v) { o[k] = v; return true; },
  });
  return { g, take() { const r = out.splice(0); stack.length = 0; st = { ...st, m: [1, 0, 0, 1, 0, 0], alpha: 1 }; return r; } };
}

// the same corner-instrument boxes page.js passes as frame.reserved (template text is moved below them); keep in step with page.js
const HUD_BOXES = { tm_clock: [0.015, 0.02, 0.235, 0.155], tm_mission: [0.76, 0.02, 0.98, 0.17] };
const reservedAt = (layers, t) => layers.filter((L) => HUD_BOXES[L.def.type] && (L.def.type !== 'tm_clock' || (L.def.mode || 'light') === 'light')
  && t >= (L.def.start ?? 0) && t <= (L.def.end ?? 1e9)).map((L) => HUD_BOXES[L.def.type]);

const area = (b) => Math.max(0, b[2] - b[0]) * Math.max(0, b[3] - b[1]);
const inter = (a, b) => area([Math.max(a[0], b[0]), Math.max(a[1], b[1]), Math.min(a[2], b[2]), Math.min(a[3], b[3])]);

export async function auditSpec(spec, { fps = 10 } = {}) {
  sanitizeShots(spec);
  const W = spec.width || 1920, H = spec.height || 1080, dur = spec.duration || (spec.shots.at(-1)?.end ?? 1);
  const scale = (W * H) / (1920 * 1080);
  if (typeof globalThis.document === 'undefined') globalThis.document = { createElement: () => ({ width: 300, height: 150, getContext: () => recordingCanvas(300, 150).g }) };
  const reg = registerBuiltins(createRegistry());
  const index = new Map((spec.layers || []).map((d, i) => [d, i]));
  const layers = await reg.instantiate(spec.layers || [], { spec, W, H, loadImage: async () => ({ width: 1200, height: 800 }), warn: () => {} }, { lenient: true });
  const rec = recordingCanvas(W, H);
  const open = new Map();          // "a|b" -> clash being extended
  const clashes = [];
  let frames = 0;
  for (let i = 0; i <= Math.floor(dur * fps); i++) {
    const t = i / fps;
    frames++;
    const drawn = [];
    const reserved = reservedAt(layers, t);
    for (const L of layers) {
      if (L.impl.space !== 'screen' || !L.impl.draw || L.broken) continue;
      const alpha = opacityAt(L.def, t) * (L.def.opacity ?? 1);
      if (alpha < VISIBLE) continue;
      try {
        rec.g.save(); L.impl.draw(L.inst, { t, W, H, g: rec.g, spec, shot: shotAt(spec.shots, t), claims: [], reserved, alpha, def: L.def }); rec.g.restore();
      } catch { /* the page switches a throwing layer off; nothing drawn */ }
      const items = rec.take().filter((x) => x.alpha >= VISIBLE && (x.kind === 'text' ? x.text.trim() : area(x.box) < 0.5 * W * H));
      if (items.length) drawn.push({ L, items });
    }
    const seen = new Set();
    for (let x = 0; x < drawn.length; x++) for (let y = x + 1; y < drawn.length; y++) {
      const A = drawn[x], B = drawn[y];
      let best = null;
      for (const p of A.items) for (const q of B.items) {
        if (p.kind !== 'text' && q.kind !== 'text') continue;              // two cards side by side are a layout, not a clash
        const o = inter(p.box, q.box);
        if (o >= MIN_OVERLAP_PX * scale && (!best || o > best.o)) best = { o, p, q };
      }
      if (!best) continue;
      const a = index.get(A.L.def), b = index.get(B.L.def), key = `${a}|${b}`;
      seen.add(key);
      const c = open.get(key);
      if (c) { c.end = +(t + 1 / fps).toFixed(3); c.area = Math.max(c.area, Math.round(best.o)); continue; }
      const n = { a, b, a_type: A.L.def.type, b_type: B.L.def.type, start: +t.toFixed(3), end: +(t + 1 / fps).toFixed(3),
        a_text: best.p.kind === 'text' ? best.p.text.slice(0, 40) : '[card]', b_text: best.q.kind === 'text' ? best.q.text.slice(0, 40) : '[card]', area: Math.round(best.o) };
      open.set(key, n); clashes.push(n);
    }
    for (const k of [...open.keys()]) if (!seen.has(k)) open.delete(k);
  }
  return { clashes, frames };
}

if (process.argv[1] && process.argv[1].endsWith('overlap_audit.mjs')) {
  const args = process.argv.slice(2);
  const fi = args.indexOf('--fps');
  const fps = fi >= 0 ? parseFloat(args[fi + 1]) : 10;
  const file = args.find((a, i) => !a.startsWith('--') && (fi < 0 || i !== fi + 1));
  const spec = JSON.parse(fs.readFileSync(file, 'utf8'));
  auditSpec(spec, { fps }).then((r) => { process.stdout.write(JSON.stringify(r) + '\n'); })
    .catch((e) => { process.stdout.write(JSON.stringify({ error: String(e && e.stack || e).split('\n').slice(0, 3).join(' | ') }) + '\n'); process.exitCode = 1; });
}
