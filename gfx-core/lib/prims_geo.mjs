// GFX-CORE GEO + DATA PRIMITIVES: the map-native animation (route with a moving marker, flow arrows, distance ruler, chokepoint callout, heat
// spreading, border draw-on with the rest dimmed, territory year clock, location card, photo leader) and the remaining graph kinds (dial, bubbles,
// tally, number line, stacked bars, bar race, before/after slider, scoreboard). Map pieces need c.project(lon, lat) -> {x, y} in output pixels
// (the niche adapter provides it; without it they draw nothing). Same contract as prims.mjs: draw(c, it, tr).
import { param } from './tpl.mjs';
import { col, clamp01, easeOut, easeInOut, fmtNum, theme } from './theme.mjs';

const prog = (it, tr, dur = 1, delay = 0) => clamp01((tr - it._in - delay) / Math.max(0.05, dur));
const num = (v, d = 0) => { const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/,/g, '')); return Number.isFinite(n) ? n : d; };
const rowsOf = (v) => (Array.isArray(v) ? v : []);
const CYCLE = ['orange', 'green', 'blue', 'teal', 'red', 'yellow', 'purple'];
const pts = (c, it) => { const out = []; if (!c.project) return out; for (const p of (Array.isArray(it.points) ? it.points : [])) { if (!Array.isArray(p) || p.length < 2) continue; const q = c.project(p[0], p[1]); if (q) out.push([q.x, q.y]); } return out; };
const lens = (P) => { const L = [0]; for (let i = 1; i < P.length; i++) L.push(L[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1])); return L; };
const at_ = (P, k) => { const L = lens(P), want = clamp01(k) * L[L.length - 1]; for (let i = 1; i < P.length; i++) if (L[i] >= want) { const s = L[i] - L[i - 1] || 1, u = (want - L[i - 1]) / s; return { x: P[i - 1][0] + (P[i][0] - P[i - 1][0]) * u, y: P[i - 1][1] + (P[i][1] - P[i - 1][1]) * u, a: Math.atan2(P[i][1] - P[i - 1][1], P[i][0] - P[i - 1][0]), i }; } const n = P.length - 1; return { x: P[n][0], y: P[n][1], a: n ? Math.atan2(P[n][1] - P[n - 1][1], P[n][0] - P[n - 1][0]) : 0, i: n }; };
const strokeTo = (g, P, k) => { const L = lens(P), want = clamp01(k) * L[L.length - 1]; g.beginPath(); g.moveTo(P[0][0], P[0][1]); for (let i = 1; i < P.length; i++) { if (L[i] <= want) { g.lineTo(P[i][0], P[i][1]); continue; } const s = L[i] - L[i - 1] || 1, u = (want - L[i - 1]) / s; g.lineTo(P[i - 1][0] + (P[i][0] - P[i - 1][0]) * u, P[i - 1][1] + (P[i][1] - P[i - 1][1]) * u); break; } g.stroke(); };
const haversine = (a, b) => { const r = Math.PI / 180, dp = (b[1] - a[1]) * r, dl = (b[0] - a[0]) * r, h = Math.sin(dp / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dl / 2) ** 2; return 6371 * 2 * Math.asin(Math.min(1, Math.sqrt(h))); };
const arrow = (g, x, y, a, s, color) => { g.save(); g.fillStyle = color; g.translate(x, y); g.rotate(a); g.beginPath(); g.moveTo(0, 0); g.lineTo(-s, -s * 0.55); g.lineTo(-s * 0.7, 0); g.lineTo(-s, s * 0.55); g.closePath(); g.fill(); g.restore(); };
const chip = (c, text, x, y, { bg = theme().tagBg, color = '#fff', px = 24, align = 'center' } = {}) => { const { T, g } = c, w = T.measure(text, px, 800, 2) + 32 * T.S, h = px * T.S * 1.8, x0 = align === 'center' ? x - w / 2 : x; g.save(); g.fillStyle = bg; g.beginPath(); g.roundRect(x0, y - h / 2, w, h, 6 * T.S); g.fill(); g.restore(); T.text(text, x0 + 16 * T.S, y + px * T.S * 0.35, { px, weight: 800, color, track: 2, shadow: 0 }); return w; };

// ---- map-native -------------------------------------------------------------------------------------------------------------------------
// a route draws itself, a marker travels along it, start and end named
function route(c, it, tr) {
  const { g, T } = c, P = pts(c, it); if (P.length < 2) return; const k = easeInOut(prog(it, tr, it.dur ?? 3.5)), color = col(it.color || 'orange');
  g.save(); g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = 'rgba(0,0,0,0.5)'; g.lineWidth = 9 * T.S; strokeTo(g, P, k); g.strokeStyle = color; g.lineWidth = 6 * T.S; strokeTo(g, P, k);
  const e = at_(P, k); const place = (p, name, alpha) => { if (!name) return; g.fillStyle = '#fff'; g.beginPath(); g.arc(p[0], p[1], 8 * T.S, 0, Math.PI * 2); g.fill(); g.strokeStyle = color; g.lineWidth = 3 * T.S; g.stroke(); chip(c, String(name).toUpperCase(), p[0], p[1] - 40 * T.S, { px: 22 }); };
  g.globalAlpha *= 1; place(P[0], it.from_label); if (k > 0.98) place(P[P.length - 1], it.to_label);
  arrow(g, e.x, e.y, e.a, 24 * T.S, color); g.fillStyle = '#fff'; g.beginPath(); g.arc(e.x, e.y, 7 * T.S, 0, Math.PI * 2); g.fill(); g.restore();
  if (it.label && k > 0.5) { const m = at_(P, 0.5); chip(c, String(it.label).toUpperCase(), m.x, m.y - 44 * T.S, { px: 24, bg: color, color: col('ink') }); }
}

// dashes flow along a route with chevrons (trade, supply, migration)
function flowarrows(c, it, tr) {
  const { g, T } = c, P = pts(c, it); if (P.length < 2) return; const color = col(it.color || 'yellow'), k = easeOut(prog(it, tr, 0.8)), total = lens(P).at(-1), t = tr - it._in;
  g.save(); g.globalAlpha *= k; g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = 'rgba(0,0,0,0.4)'; g.lineWidth = (it.width ?? 12) * T.S + 4 * T.S; g.beginPath(); P.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
  g.strokeStyle = color; g.lineWidth = (it.width ?? 12) * T.S; g.globalAlpha *= 0.55; g.setLineDash([22 * T.S, 18 * T.S]); g.lineDashOffset = -t * 90 * T.S; g.beginPath(); P.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke(); g.setLineDash([]); g.globalAlpha /= 0.55;
  const step = 150 * T.S, n = Math.max(1, Math.floor(total / step)); for (let i = 0; i < n; i++) { const f = ((i / n) + t * 0.12) % 1, p = at_(P, f); arrow(g, p.x, p.y, p.a, 22 * T.S, color); } g.restore();
}

// a distance ruler between two points: a dashed line that draws, end dots, the great-circle distance in a chip
function ruler(c, it, tr) {
  const { g, T } = c, A = it.points?.[0], B = it.points?.[1]; if (!c.project || !A || !B) return; const a = c.project(A[0], A[1]), b = c.project(B[0], B[1]); if (!a || !b) return;
  const k = easeInOut(prog(it, tr, 1.6)), km = haversine(A, B), color = col(it.color || 'yellow'), unit = it.unit === 'mi' ? 'MI' : 'KM', val = it.unit === 'mi' ? km * 0.621371 : km;
  g.save(); g.strokeStyle = color; g.lineWidth = 4 * T.S; g.setLineDash([16 * T.S, 12 * T.S]); g.lineCap = 'round'; g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 8 * T.S; g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(a.x + (b.x - a.x) * k, a.y + (b.y - a.y) * k); g.stroke(); g.setLineDash([]);
  for (const [p, f] of [[a, 0], [b, 0.95]]) if (k >= f) { g.fillStyle = '#fff'; g.beginPath(); g.arc(p.x, p.y, 8 * T.S, 0, Math.PI * 2); g.fill(); g.strokeStyle = color; g.lineWidth = 3 * T.S; g.stroke(); }
  g.restore(); if (k > 0.6) chip(c, `${fmtNum(val * easeOut((k - 0.6) / 0.4), 0)} ${unit}`, (a.x + b.x) / 2, (a.y + b.y) / 2 - 36 * T.S, { px: 30, bg: color, color: col('ink') });
  if (it.from_label) chip(c, String(it.from_label).toUpperCase(), a.x, a.y + 44 * T.S, { px: 20 }); if (it.to_label && k > 0.95) chip(c, String(it.to_label).toUpperCase(), b.x, b.y + 44 * T.S, { px: 20 });
}

// a chokepoint: a pulsing ring on the strait, two short parallel "banks", and a card with its name, width and one fact
function chokepoint(c, it, tr) {
  const { g, T } = c, p = c.project && it.follow && c.follow ? { x: c.follow[0] * c.W, y: c.follow[1] * c.H } : null; if (!p) return; const k = easeOut(prog(it, tr, 0.5)), t = tr - it._in, pulse = (t % 1.4) / 1.4, color = col(it.color || 'red');
  g.save(); g.globalAlpha *= clamp01(k * 2); g.strokeStyle = color; g.lineWidth = 3 * T.S; g.beginPath(); g.arc(p.x, p.y, (16 + 50 * pulse) * T.S, 0, Math.PI * 2); g.globalAlpha *= 1 - pulse; g.stroke(); g.globalAlpha /= Math.max(0.01, 1 - pulse);
  g.lineWidth = 5 * T.S; g.lineCap = 'round'; for (const s of [-1, 1]) { g.beginPath(); g.moveTo(p.x - 40 * T.S, p.y + s * 26 * T.S); g.lineTo(p.x + 40 * T.S, p.y + s * 26 * T.S); g.stroke(); }
  g.fillStyle = '#fff'; g.beginPath(); g.arc(p.x, p.y, 7 * T.S, 0, Math.PI * 2); g.fill();
  const w = 460 * T.S, h = (it.fact ? 150 : 104) * T.S, x = Math.min(c.W - w - 40 * T.S, p.x + 90 * T.S), y = Math.max(40 * T.S, p.y - h - 60 * T.S);
  g.strokeStyle = 'rgba(255,255,255,0.6)'; g.lineWidth = 2 * T.S; g.beginPath(); g.moveTo(p.x + 10 * T.S, p.y - 10 * T.S); g.lineTo(x, y + h); g.stroke(); T.panel(x, y, w, h, { r: 8 });
  g.fillStyle = color; g.fillRect(x, y, 6 * T.S, h); T.text(String(it.name || '').toUpperCase(), x + 26 * T.S, y + 40 * T.S, { px: 28, weight: 900, color: '#fff', track: 2, shadow: 0 });
  if (it.width_km) T.text(`${it.width_km} KM WIDE`, x + 26 * T.S, y + 76 * T.S, { px: 22, weight: 800, color: color, track: 2, shadow: 0 }); if (it.fact) T.text(String(it.fact), x + 26 * T.S, y + 118 * T.S, { px: 22, weight: 500, color: '#E4EAED', shadow: 0 });
  g.restore();
}

// heat spreading from one or more points: soft blobs that grow, warm colours
function heat(c, it, tr) {
  const { g, T } = c; if (!c.project) return; const P = pts(c, it); if (!P.length) return; const k = easeOut(prog(it, tr, it.dur ?? 3)), base = (it.radius ?? 0.22) * c.H, color = it.color || '255,90,30';
  g.save(); g.globalCompositeOperation = 'screen'; P.forEach(([x, y], i) => { const r = base * k * (0.8 + 0.4 * ((i * 37) % 5) / 5) * (1 + 0.04 * Math.sin((tr - it._in) * 2 + i)); const gr = g.createRadialGradient(x, y, 0, x, y, Math.max(1, r)); gr.addColorStop(0, `rgba(${color},0.75)`); gr.addColorStop(0.5, `rgba(${color},0.32)`); gr.addColorStop(1, `rgba(${color},0)`); g.fillStyle = gr; g.beginPath(); g.arc(x, y, Math.max(1, r), 0, Math.PI * 2); g.fill(); }); g.restore();
  if (it.label) T.text(String(it.label).toUpperCase(), P[0][0], P[0][1] - base * k * 0.9 - 14 * T.S, { px: 26, weight: 800, color: '#fff', track: 3, align: 'center', shadow: 0.6, alpha: k });
}

// the border draws itself around the region and everything outside it is dimmed; the name sits at the centre
function spotlight(c, it, tr) {
  const { g, T } = c; if (!c.project) return; const polys = Array.isArray(it.polys) ? it.polys : []; if (!polys.length) return; const k = easeOut(prog(it, tr, 0.9)), dr = easeInOut(prog(it, tr, it.dur ?? 2.2)), color = col(it.color || 'teal');
  const ring = (r) => r.map((p) => { const q = c.project(p[0], p[1]); return q ? [q.x, q.y] : null; }).filter(Boolean);
  const rings = []; for (const poly of polys) for (const r of poly) { const R = ring(r); if (R.length > 2) rings.push(R); }
  if (!rings.length) return; g.save(); g.globalAlpha *= k; g.fillStyle = `rgba(4,8,12,${it.dim ?? 0.62})`; g.beginPath(); g.rect(0, 0, c.W, c.H); for (const R of rings) { g.moveTo(R[0][0], R[0][1]); for (let i = 1; i < R.length; i++) g.lineTo(R[i][0], R[i][1]); g.closePath(); } g.fill('evenodd'); g.restore();
  g.save(); g.lineJoin = 'round'; g.lineCap = 'round'; g.strokeStyle = color; g.lineWidth = 4 * T.S; g.shadowColor = color; g.shadowBlur = 14 * T.S; for (const R of rings) strokeTo(g, [...R, R[0]], dr); g.restore();
  if (it.label) { let sx = 0, sy = 0, n = 0; for (const R of rings.slice(0, 1)) for (const p of R) { sx += p[0]; sy += p[1]; n++; } if (n) T.text(String(it.label).toUpperCase(), sx / n, sy / n, { face: 'display', px: it.size ?? 64, weight: 900, color, track: 8, align: 'center', glow: 'rgba(45,224,200,0.55)', alpha: easeOut(prog(it, tr, 0.8, 0.8)), shadow: 0.5 }); }
}

// territory over time: a big year counting between two years, with the share (or area) it holds as a bar and a number
function yearclock(c, it, tr) {
  const { g, T } = c, k = easeInOut(prog(it, tr, it.dur ?? 5)), y0 = num(it.year_from, 1900), y1 = num(it.year_to, 2000), v0 = num(it.value_from, 0), v1 = num(it.value_to, 100), year = Math.round(y0 + (y1 - y0) * k), v = v0 + (v1 - v0) * k, x = c.W * 0.06, y = c.H * 0.2, color = col(it.color || 'gold'), max = num(it.max, Math.max(v0, v1) * 1.1 || 100);
  g.save(); g.globalAlpha *= easeOut(prog(it, tr, 0.4)); T.text(String(year), x, y + 110 * T.S, { face: 'display', px: 190, weight: 700, color: '#fff', shadow: 0.7 });
  if (it.label) T.text(String(it.label).toUpperCase(), x + 6 * T.S, y + 170 * T.S, { px: 26, weight: 800, color: col('muted'), track: 5, shadow: 0 });
  T.rect(x, y + 210 * T.S, 520 * T.S, 18 * T.S, 'rgba(255,255,255,0.14)', 3); T.rect(x, y + 210 * T.S, 520 * T.S * clamp01(v / max), 18 * T.S, color, 3);
  T.text(`${fmtNum(v, it.dec ?? 0)}${it.unit ? ' ' + String(it.unit).toUpperCase() : ''}`, x, y + 285 * T.S, { px: 44, weight: 800, color, shadow: 0.4 }); g.restore();
}

// a location card: name, coordinates, one fact, joined to the place by a leader line (follow = the place)
function locationcard(c, it, tr) {
  const { g, T } = c, p = it.follow && c.follow ? { x: c.follow[0] * c.W, y: c.follow[1] * c.H } : null; if (!p) return; const k = easeOut(prog(it, tr, 0.5)), w = 480 * T.S, h = (it.fact ? 170 : 120) * T.S;
  const right = p.x < c.W * 0.55, x = right ? Math.min(c.W - w - 40 * T.S, p.x + 110 * T.S) : Math.max(40 * T.S, p.x - 110 * T.S - w), y = Math.max(40 * T.S, Math.min(c.H - h - 40 * T.S, p.y - h / 2 - 70 * T.S));
  g.save(); g.globalAlpha *= clamp01(k * 2); g.strokeStyle = '#fff'; g.lineWidth = 3 * T.S; g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(p.x + (x + (right ? 0 : w) - p.x) * k, p.y + (y + h / 2 - p.y) * k); g.stroke(); g.fillStyle = '#fff'; g.beginPath(); g.arc(p.x, p.y, 8 * T.S, 0, Math.PI * 2); g.fill();
  g.translate(0, (1 - k) * 14 * T.S); T.panel(x, y, w, h, { r: 8 }); g.fillStyle = col(it.accent || 'orange'); g.fillRect(x, y, 6 * T.S, h);
  T.text(String(it.name || '').toUpperCase(), x + 26 * T.S, y + 44 * T.S, { px: 32, weight: 900, color: '#fff', track: 2, shadow: 0 }); if (it.coords) T.text(String(it.coords), x + 26 * T.S, y + 82 * T.S, { px: 20, weight: 600, color: col('muted'), track: 2, shadow: 0 });
  if (it.fact) T.text(String(it.fact), x + 26 * T.S, y + 130 * T.S, { px: 22, weight: 500, color: '#E4EAED', shadow: 0 }); g.restore();
}

// a photo card at the side with a leader line to the place it shows
function photoleader(c, it, tr) {
  const { g, T } = c, p = it.follow && c.follow ? { x: c.follow[0] * c.W, y: c.follow[1] * c.H } : null; if (!p) return; const img = c.image ? c.image(it.image) : null, k = easeOut(prog(it, tr, 0.6)), w = 520 * T.S, h = 340 * T.S, right = p.x < c.W * 0.5, x = right ? c.W - w - 60 * T.S : 60 * T.S, y = c.H * 0.2 + (1 - k) * 24 * T.S;
  g.save(); g.globalAlpha *= clamp01(k * 2); g.strokeStyle = '#fff'; g.lineWidth = 3 * T.S; g.beginPath(); g.moveTo(p.x, p.y); g.lineTo(p.x + (x + (right ? 0 : w) - p.x) * k, p.y + (y + h / 2 - p.y) * k); g.stroke(); g.fillStyle = '#fff'; g.beginPath(); g.arc(p.x, p.y, 8 * T.S, 0, Math.PI * 2); g.fill();
  g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 22 * T.S; g.fillStyle = '#F4F4F2'; g.fillRect(x - 8 * T.S, y - 8 * T.S, w + 16 * T.S, h + 16 * T.S); g.shadowColor = 'transparent';
  if (img) { const ar = img.width / img.height, br = w / h; let sw = img.width, sh = img.height, sx = 0, sy = 0; if (ar > br) { sw = img.height * br; sx = (img.width - sw) / 2; } else { sh = img.width / br; sy = (img.height - sh) / 2; } g.drawImage(img, sx, sy, sw, sh, x, y, w, h); } else { g.fillStyle = '#3a3d42'; g.fillRect(x, y, w, h); }
  if (it.caption) T.text(String(it.caption).toUpperCase(), x, y + h + 44 * T.S, { px: 22, weight: 800, color: '#fff', track: 3, shadow: 0.6 }); g.restore();
}

// ---- data ---------------------------------------------------------------------------------------------------------------------------------
// a half-circle gauge with a needle that swings to the value
function dial(c, it, tr) {
  const { g, T } = c, [x, y] = (() => { const a = param(it, 'at', tr, [0.5, 0.62]); return [a[0] * c.W, a[1] * c.H]; })(), r = (it.r ?? 0.26) * c.H, k = easeOut(prog(it, tr, it.dur ?? 2)), max = num(it.max, 100), v = num(it.value), a = Math.PI + Math.PI * clamp01(v / max) * k, lw = 34 * T.S;
  g.save(); g.lineCap = 'butt'; g.lineWidth = lw; const zones = [['green', 0.5], ['yellow', 0.8], ['red', 1]]; let s = Math.PI; for (const [cn, e] of zones) { g.strokeStyle = col(cn); g.globalAlpha *= 0.85; g.beginPath(); g.arc(x, y, r, s, Math.PI + Math.PI * e); g.stroke(); g.globalAlpha /= 0.85; s = Math.PI + Math.PI * e; }
  g.strokeStyle = '#fff'; g.lineWidth = 8 * T.S; g.lineCap = 'round'; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * (r - 10 * T.S), y + Math.sin(a) * (r - 10 * T.S)); g.stroke(); g.fillStyle = '#fff'; g.beginPath(); g.arc(x, y, 16 * T.S, 0, Math.PI * 2); g.fill(); g.restore();
  T.text(fmtNum(v * k, it.dec ?? 0) + (it.unit ?? ''), x, y + 110 * T.S, { face: 'display', px: 96, weight: 900, color: '#fff', align: 'center', shadow: 0.5 }); if (it.label) T.text(String(it.label).toUpperCase(), x, y + 160 * T.S, { px: 26, weight: 800, color: col('muted'), track: 5, align: 'center', shadow: 0 });
  T.text('0', x - r, y + 40 * T.S, { px: 20, weight: 700, color: col('muted'), align: 'center', shadow: 0 }); T.text(fmtNum(max, 0), x + r, y + 40 * T.S, { px: 20, weight: 700, color: col('muted'), align: 'center', shadow: 0 });
}

// proportional bubbles side by side (area = value), the value inside, the name below
function bubbles(c, it, tr) {
  const { g, T } = c, rs = rowsOf(it.rows).slice(0, 6); if (!rs.length) return; const max = Math.max(...rs.map((r) => num(r.value)), 1), R = Math.min(0.2 * c.H, (c.W * 0.84) / (rs.length * 2.3)), cy = c.H * 0.5;
  rs.forEach((r, i) => { const k = easeOut(clamp01((tr - it._in - 0.2 - i * 0.3) / 0.7)); if (k <= 0) return; const rad = R * Math.sqrt(num(r.value) / max) * k, cx = c.W * (0.08 + 0.84 * ((i + 0.5) / rs.length)), color = col(r.color || CYCLE[i % CYCLE.length]);
    g.save(); g.fillStyle = color; g.globalAlpha *= 0.85; g.beginPath(); g.arc(cx, cy, rad, 0, Math.PI * 2); g.fill(); g.globalAlpha /= 0.85; g.strokeStyle = 'rgba(255,255,255,0.7)'; g.lineWidth = 3 * T.S; g.stroke(); g.restore();
    T.text(fmtNum(num(r.value) * k, r.dec ?? 0), cx, cy + 12 * T.S, { px: Math.max(22, Math.min(54, rad / T.S / 1.5)), weight: 900, color: col('ink'), align: 'center', shadow: 0 }); T.text(String(r.label || '').toUpperCase(), cx, cy + R + 54 * T.S, { px: 24, weight: 800, color: '#fff', track: 2, align: 'center', shadow: 0.4, alpha: k }); });
  if (it.title) T.text(String(it.title).toUpperCase(), c.W * 0.06, c.H * 0.16, { px: 30, weight: 800, color: '#fff', track: 4, shadow: 0 });
}

// a dot tally: n dots (each = `per` units) filling a grid one after another, a counter beside it
function tally(c, it, tr) {
  const { g, T } = c, total = Math.min(200, Math.max(1, Math.round(num(it.total, 100) / Math.max(1e-9, num(it.per, 1))))), cols = it.cols ?? Math.ceil(Math.sqrt(total * 1.8)), rowsN = Math.ceil(total / cols), size = Math.min(0.62 * c.W / cols, 0.6 * c.H / rowsN), x0 = c.W * 0.08, y0 = c.H * 0.22;
  const k = easeInOut(prog(it, tr, it.dur ?? 3)), shown = Math.floor(total * k), hi = Math.round(total * clamp01(num(it.highlight, 0) / Math.max(1e-9, num(it.total, 100))));
  for (let i = 0; i < total; i++) { const cx = x0 + (i % cols + 0.5) * size, cy = y0 + (Math.floor(i / cols) + 0.5) * size; g.fillStyle = i < shown ? (i < hi ? col(it.color || 'orange') : 'rgba(255,255,255,0.85)') : 'rgba(255,255,255,0.12)'; g.beginPath(); g.arc(cx, cy, size * 0.32, 0, Math.PI * 2); g.fill(); }
  T.text(fmtNum(num(it.total, 100) * k, 0), c.W * 0.74, c.H * 0.46, { face: 'display', px: 150, weight: 900, color: '#fff', shadow: 0.5 }); T.text(`${String(it.label || '').toUpperCase()}`, c.W * 0.74, c.H * 0.46 + 56 * T.S, { px: 26, weight: 800, color: col('muted'), track: 4, shadow: 0 });
  if (it.per) T.text(`1 DOT = ${fmtNum(num(it.per), 0)}`, x0, y0 - 28 * T.S, { px: 22, weight: 800, color: col('muted'), track: 3, shadow: 0 });
}

// a number line with labelled points that appear in turn (log scale option for things that differ by orders of magnitude)
function numberline(c, it, tr) {
  const { g, T } = c, rs = rowsOf(it.rows).slice(0, 8); if (!rs.length) return; const vals = rs.map((r) => num(r.value)), f = it.log ? (v) => Math.log10(Math.max(1e-9, v)) : (v) => v, lo = Math.min(...vals.map(f)), hi = Math.max(...vals.map(f)), x0 = c.W * 0.08, x1 = c.W * 0.92, y = c.H * 0.54, k = easeInOut(prog(it, tr, 1));
  g.save(); g.strokeStyle = 'rgba(255,255,255,0.45)'; g.lineWidth = 4 * T.S; g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 + (x1 - x0) * k, y); g.stroke(); g.restore();
  if (it.title) T.text(String(it.title).toUpperCase(), x0, c.H * 0.2, { px: 30, weight: 800, color: '#fff', track: 4, shadow: 0 });
  rs.forEach((r, i) => { const t0 = it._in + 0.6 + i * 0.5, a = easeOut(clamp01((tr - t0) / 0.5)); if (a <= 0) return; const px = x0 + (x1 - x0) * (hi === lo ? 0.5 : (f(num(r.value)) - lo) / (hi - lo)), up = i % 2 === 0, color = col(r.color || CYCLE[i % CYCLE.length]);
    g.save(); g.globalAlpha *= a; g.strokeStyle = color; g.lineWidth = 3 * T.S; g.beginPath(); g.moveTo(px, y); g.lineTo(px, y + (up ? -1 : 1) * 70 * T.S * a); g.stroke(); g.fillStyle = color; g.beginPath(); g.arc(px, y, 11 * T.S, 0, Math.PI * 2); g.fill();
    T.text(fmtNum(num(r.value), r.dec ?? 0), px, y + (up ? -96 : 124) * T.S, { px: 40, weight: 900, color: '#fff', align: 'center', shadow: 0.4 }); T.text(String(r.label || '').toUpperCase(), px, y + (up ? -134 : 160) * T.S, { px: 20, weight: 800, color: col('muted'), track: 2, align: 'center', shadow: 0 }); g.restore(); });
}

// stacked comparison bars: rows "CANADA:Energy=60; CANADA:Trade=40; USA:Energy=30; ..." = one bar per group, split into its parts
function stackbars(c, it, tr) {
  const { g, T } = c, rs = rowsOf(it.rows); if (!rs.length) return; const groups = []; const parts = [];
  for (const r of rs) { const [gname, part] = String(r.label || '').includes(':') ? String(r.label).split(':') : ['', r.label]; let gi = groups.findIndex((x) => x.name === gname.trim()); if (gi < 0) { groups.push({ name: gname.trim(), items: [] }); gi = groups.length - 1; } groups[gi].items.push({ part: part.trim(), v: num(r.value) }); if (!parts.includes(part.trim())) parts.push(part.trim()); }
  const maxT = Math.max(...groups.map((x) => x.items.reduce((a, b) => a + b.v, 0)), 1), x0 = c.W * 0.22, W = c.W * 0.68, bh = 96 * T.S, gap = 70 * T.S, y0 = c.H * 0.3;
  if (it.title) T.text(String(it.title).toUpperCase(), c.W * 0.06, c.H * 0.14, { px: 30, weight: 800, color: '#fff', track: 4, shadow: 0 });
  groups.forEach((gr, gi) => { const k = easeOut(clamp01((tr - it._in - 0.3 - gi * 0.5) / 1)); if (k <= 0) return; const y = y0 + gi * (bh + gap); T.text(gr.name.toUpperCase(), x0 - 28 * T.S, y + bh / 2 + 12 * T.S, { px: 30, weight: 900, color: '#fff', track: 2, align: 'right', shadow: 0 }); let x = x0;
    gr.items.forEach((s) => { const w = (s.v / maxT) * W * k; g.fillStyle = col(CYCLE[parts.indexOf(s.part) % CYCLE.length]); g.fillRect(x, y, w, bh); if (w > 120 * T.S) T.text(`${s.part.toUpperCase()}  ${fmtNum(s.v, 0)}`, x + 16 * T.S, y + bh / 2 + 10 * T.S, { px: 22, weight: 800, color: col('ink'), track: 1, shadow: 0 }); x += w; }); });
  parts.forEach((p, i) => { const lx = x0 + i * 200 * T.S, ly = y0 + groups.length * (bh + gap) - 20 * T.S; g.fillStyle = col(CYCLE[i % CYCLE.length]); g.fillRect(lx, ly, 22 * T.S, 22 * T.S); T.text(p.toUpperCase(), lx + 32 * T.S, ly + 18 * T.S, { px: 20, weight: 700, color: '#E4EAED', track: 1, shadow: 0 }); });
}

// a bar race: frames [{label: year, rows: [{label, value}]}] play in turn, bars re-ranking and growing between them
function barrace(c, it, tr) {
  const { g, T } = c, fr = (Array.isArray(it.frames) ? it.frames : []).filter((f) => f && Array.isArray(f.rows)); if (fr.length < 2) return; const dur = it.dur ?? 8, f = easeInOut(prog(it, tr, dur)) * (fr.length - 1), i0 = Math.min(fr.length - 2, Math.floor(f)), u = f - i0;
  const names = [...new Set(fr.flatMap((x) => x.rows.map((r) => String(r.label))))], val = (fi, n) => num((fr[fi].rows.find((r) => String(r.label) === n) || {}).value);
  const cur = names.map((n) => ({ n, v: val(i0, n) + (val(i0 + 1, n) - val(i0, n)) * u })).sort((a, b) => b.v - a.v).slice(0, it.top ?? 6), max = Math.max(...cur.map((x) => x.v), 1) , x0 = c.W * 0.2, W = c.W * 0.62, rh = 74 * T.S, y0 = c.H * 0.2;
  cur.forEach((r, i) => { const w = (r.v / max) * W, y = y0 + i * (rh + 16 * T.S), color = col(CYCLE[names.indexOf(r.n) % CYCLE.length]); g.fillStyle = color; g.fillRect(x0, y, w, rh); T.text(r.n.toUpperCase(), x0 - 20 * T.S, y + rh / 2 + 10 * T.S, { px: 26, weight: 800, color: '#fff', track: 2, align: 'right', shadow: 0 }); T.text(fmtNum(r.v, 0), x0 + w + 16 * T.S, y + rh / 2 + 12 * T.S, { px: 32, weight: 900, color: '#fff', shadow: 0.3 }); });
  const label = u < 0.5 ? fr[i0].label : fr[i0 + 1].label; T.text(String(label), c.W * 0.9, c.H * 0.88, { face: 'display', px: 150, weight: 700, color: 'rgba(255,255,255,0.85)', align: 'right', shadow: 0.5 }); if (it.title) T.text(String(it.title).toUpperCase(), c.W * 0.06, c.H * 0.1, { px: 30, weight: 800, color: '#fff', track: 4, shadow: 0 });
}

// a before / after picture slider: the divider sweeps across and reveals the second picture
function slider(c, it, tr) {
  const { g, T } = c, A = c.image ? c.image(it.before) : null, B = c.image ? c.image(it.after) : null, w = (it.w ?? 0.8) * c.W, h = w * 0.5625, x = (c.W - w) / 2, y = (c.H - h) / 2, k = easeInOut(prog(it, tr, it.dur ?? 4, 0.8)), cut = x + w * (0.08 + 0.84 * k);
  const draw = (img, x0, wd, shade) => { g.save(); g.beginPath(); g.rect(x0, y, wd, h); g.clip(); if (img) { const ar = img.width / img.height, br = w / h; let sw = img.width, sh = img.height, sx = 0, sy = 0; if (ar > br) { sw = img.height * br; sx = (img.width - sw) / 2; } else { sh = img.width / br; sy = (img.height - sh) / 2; } g.drawImage(img, sx, sy, sw, sh, x, y, w, h); } else { g.fillStyle = shade; g.fillRect(x, y, w, h); } g.restore(); };
  g.save(); g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 24 * T.S; g.fillStyle = '#000'; g.fillRect(x - 6 * T.S, y - 6 * T.S, w + 12 * T.S, h + 12 * T.S); g.restore();
  draw(B, x, w, '#3a5a7a'); draw(A, x, cut - x, '#7a5a3a'); g.fillStyle = '#fff'; g.fillRect(cut - 2 * T.S, y, 4 * T.S, h); g.beginPath(); g.arc(cut, y + h / 2, 22 * T.S, 0, Math.PI * 2); g.fill();
  chip(c, String(it.before_label || 'BEFORE').toUpperCase(), x + 70 * T.S, y + 40 * T.S, { px: 22 }); chip(c, String(it.after_label || 'AFTER').toUpperCase(), x + w - 70 * T.S, y + 40 * T.S, { px: 22, bg: col('gold'), color: col('ink') });
}

// a scoreboard of rivals: name and a big score each, the leader highlighted
function scoreboard(c, it, tr) {
  const { g, T } = c, rs = rowsOf(it.rows).slice(0, 4); if (!rs.length) return; const top = Math.max(...rs.map((r) => num(r.value))), cw = Math.min(0.26 * c.W, (0.86 * c.W) / rs.length - 30 * T.S), x0 = (c.W - (rs.length * cw + (rs.length - 1) * 30 * T.S)) / 2, y = c.H * 0.3;
  if (it.title) T.text(String(it.title).toUpperCase(), c.W / 2, c.H * 0.18, { px: 34, weight: 800, color: '#fff', track: 6, align: 'center', shadow: 0 });
  rs.forEach((r, i) => { const k = easeOut(clamp01((tr - it._in - 0.3 - i * 0.25) / 0.6)); if (k <= 0) return; const lead = num(r.value) === top, x = x0 + i * (cw + 30 * T.S), color = lead ? col('gold') : col('blue');
    g.save(); g.globalAlpha *= clamp01(k * 2); g.translate(0, (1 - k) * 30 * T.S); T.panel(x, y, cw, 360 * T.S, { r: 10 }); g.fillStyle = color; g.fillRect(x, y, cw, 8 * T.S);
    T.text(String(r.label || '').toUpperCase(), x + cw / 2, y + 80 * T.S, { px: 30, weight: 900, color: '#fff', track: 3, align: 'center', shadow: 0 }); T.text(fmtNum(num(r.value) * k, r.dec ?? 0), x + cw / 2, y + 230 * T.S, { face: 'display', px: 130, weight: 900, color, align: 'center', shadow: 0.4 });
    if (r.text) T.text(String(r.text).toUpperCase(), x + cw / 2, y + 300 * T.S, { px: 20, weight: 700, color: col('muted'), track: 2, align: 'center', shadow: 0 }); g.restore(); });
}

export const GEO_PRIMS = { route, flowarrows, ruler, chokepoint, heat, spotlight, yearclock, locationcard, photoleader, dial, bubbles, tally, numberline, stackbars, barrace, slider, scoreboard };
