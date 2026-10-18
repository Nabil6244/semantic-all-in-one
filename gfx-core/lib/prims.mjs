// GFX-CORE PRIMITIVES: the drawing pieces universal templates are built from (charts, stat cards, tags, fact cards, styled text).
// draw(c, it, tr): c = { g, T, W, H }, it = a built item (lib/tpl.mjs), tr = seconds since the layer started. Positions are fractions of
// the frame ([0.5, 0.5] = centre); sizes are px at 1920 wide (T.S scales). Pure functions of tr: the same frame every time.
// Colours are palette names ("orange", "teal") resolved through the theme, so each niche wears its own look.
import { param, visibility } from './tpl.mjs';
import { col, clamp01, easeOut, easeInOut, overshoot, fmtNum, theme } from './theme.mjs';
import { styledText } from './textstyles.mjs';
import { NEWS_PRIMS } from './prims_news.mjs';
import { TP_PRIMS } from './prims_tp.mjs';
import { GEO_PRIMS } from './prims_geo.mjs';

const CYCLE = ['orange', 'green', 'blue', 'teal', 'red', 'yellow', 'purple'];
const num = (v, d = 0) => { const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/,/g, '')); return Number.isFinite(n) ? n : d; };
const rows = (it) => { let r = it.rows; if (typeof r === 'string') { try { r = JSON.parse(r); } catch { r = []; } } return Array.isArray(r) ? r : []; };
// an item with "follow": true sits on the point the niche adapter hands in (a place on the map, in frame fractions), else on its own "at"
const at = (c, it, tr, d = [0.05, 0.1]) => { const a = c.follow && it.follow ? c.follow : param(it, 'at', tr, d); return [a[0] * c.W, a[1] * c.H]; };
/** progress of this item's own arrival animation, 0..1 over dur seconds from its "in" time (plus a delay) */
const prog = (it, tr, dur = 1.2, delay = 0) => clamp01((tr - it._in - delay) / Math.max(0.05, dur));

// ---- tag: the small dark label box (top-left headline of a chart), letter-spaced caps --------------------------------------------
function tag(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr), px = it.size ?? 30, tr_ = it.track ?? 5, padX = 20, h = (it.h ?? px * 1.85) * T.S;
  const w = T.measure(String(it.text).toUpperCase(), px, 800, tr_) + padX * 2 * T.S, k = easeInOut(prog(it, tr, 0.5));
  g.save(); g.beginPath(); g.rect(x, y, w * k, h); g.clip();
  T.rect(x, y, w, h, it.bg ? col(it.bg) : theme().tagBg);
  T.text(String(it.text).toUpperCase(), x + padX * T.S, y + h / 2 + px * T.S * 0.35, { px, weight: 800, color: col(it.color, '#C9D2D8'), track: tr_, shadow: 0 });
  g.restore();
}

// ---- hbars: horizontal bars sized to the value, the name inside the bar, the number (and unit) after it ----------------------------
function hbars(c, it, tr) {
  const { g, T } = c, list = rows(it); if (!list.length) return;
  const [x0, y0] = at(c, it, tr, [0.04, 0.24]), rh = (it.row_h ?? 92) * T.S, gap = (it.gap ?? 50) * T.S, maxW = (it.w ?? 0.74) * c.W;
  const max = it.max ? num(it.max) : Math.max(...list.map((r) => num(r.value)), 1), unit = it.unit ?? '', dec = it.dec ?? null;
  list.forEach((r, i) => {
    const t0 = it._in + i * (it.stagger ?? 0.45), k = easeOut(clamp01((tr - t0) / (it.dur ?? 1.3))); if (k <= 0) return;
    const y = y0 + i * (rh + gap), v = num(r.value), name = String(r.label ?? '').toUpperCase(), color = col(r.color || CYCLE[i % CYCLE.length]);
    const lw = T.measure(name, 30, 800, 3) + 52 * T.S, full = Math.max(lw, (v / max) * maxW), bw = Math.max(lw * k, full * k);
    g.save(); g.globalAlpha *= clamp01(k * 4);
    const gr = g.createLinearGradient(x0, 0, x0 + bw, 0); gr.addColorStop(0, shade(color, -0.22)); gr.addColorStop(0.18, color); gr.addColorStop(1, color);
    g.fillStyle = gr; g.fillRect(x0, y, bw, rh);
    T.text(name, x0 + 26 * T.S, y + rh / 2 + 10 * T.S, { px: 30, weight: 800, color: col('ink'), track: 3, shadow: 0 });
    const vx = x0 + bw + 30 * T.S, shown = v * k, size = it.value_size ?? 66;
    const w = T.text(fmtNum(shown, dec ?? (Number.isInteger(v) ? 0 : 1)), vx, y + rh / 2 + size * T.S * 0.34, { px: size, weight: 800, color: '#F2F5F6', shadow: 0.3 });
    if (unit) T.text(String(unit).toUpperCase(), vx + w + 10 * T.S, y + rh / 2 + size * T.S * 0.34, { px: size * 0.42, weight: 800, color: '#E6ECEE', track: 1, shadow: 0 });
    g.restore();
  });
}
function shade(hex, amt) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex); if (!m) return hex;
  const n = parseInt(m[1], 16), f = (s) => Math.max(0, Math.min(255, Math.round(((n >> s) & 255) * (1 + amt))));
  return `rgb(${f(16)},${f(8)},${f(0)})`;
}

// ---- columns: a dark card with a column chart (values above, letters below, a title and a small source line) ----------------------
function columns(c, it, tr) {
  const { g, T } = c, vals = (Array.isArray(it.values) ? it.values : String(it.values || '').split(/[;,|]/)).map((v) => num(v));
  if (!vals.length) return;
  const labels = Array.isArray(it.labels) ? it.labels : String(it.labels || '').split(/[;,|]/).map((s) => s.trim());
  const [x, y] = at(c, it, tr, [0.66, 0.12]), w = (it.w ?? 0.31) * c.W, h = (it.h ?? 0.52) * c.H, pad = 24 * T.S;
  const k0 = easeOut(prog(it, tr, 0.45)); if (k0 <= 0) return;
  g.save(); g.globalAlpha *= k0; T.panel(x, y, w, h);
  const [head, ...tail] = String(it.title || '').split('·'), th = 28;
  let tx = x + pad; const ty = y + pad + th * T.S * 0.85;
  tx += T.text(head.trim().toUpperCase(), tx, ty, { px: th, weight: 800, color: '#fff', track: 3, shadow: 0 });
  if (tail.length) T.text(' · ' + tail.join('·').trim().toUpperCase(), tx, ty, { px: th, weight: 800, color: col('muted'), track: 3, shadow: 0 });
  const foot = it.footnote ? 40 * T.S : 18 * T.S, top = y + pad + th * T.S + 52 * T.S, bottom = y + h - foot - 40 * T.S, ch = bottom - top;
  const max = it.max ? num(it.max) : Math.max(...vals, 1), n = vals.length, slot = (w - pad * 2) / n, bw = slot * 0.72;
  const color = col(it.color || 'blue');
  vals.forEach((v, i) => {
    const t0 = it._in + 0.3 + i * (it.stagger ?? 0.07), k = easeOut(clamp01((tr - t0) / 0.8)), bx = x + pad + i * slot + (slot - bw) / 2, bh = Math.max(2 * T.S, (v / max) * ch * k);
    const hi = it.highlight != null && Number(it.highlight) === i;
    g.fillStyle = hi ? col(it.highlight_color || 'orange') : color; g.fillRect(bx, bottom - bh, bw, bh);
    if (k > 0.35) T.text(fmtNum(v * k, it.dec ?? 0), bx + bw / 2, bottom - bh - 9 * T.S, { px: it.value_px ?? 20, weight: 800, color: '#fff', align: 'center', shadow: 0, alpha: clamp01((k - 0.35) * 3) });
    T.text(String(labels[i] ?? '').toUpperCase(), bx + bw / 2, bottom + 32 * T.S, { px: 22, weight: 800, color: '#C9D2D8', align: 'center', shadow: 0, track: 1 });
  });
  if (it.footnote) T.text(String(it.footnote).toUpperCase(), x + pad, y + h - 22 * T.S, { px: 17, weight: 700, color: col('muted'), track: 1, shadow: 0 });
  g.restore();
}

// ---- trend: a line chart in a card (draws itself, area under it, the last value lands as a labelled dot) --------------------------
function trend(c, it, tr) {
  const { g, T } = c, vals = (Array.isArray(it.values) ? it.values : String(it.values || '').split(/[;,|]/)).map((v) => num(v)); if (vals.length < 2) return;
  const labels = Array.isArray(it.labels) ? it.labels : String(it.labels || '').split(/[;,|]/).map((s) => s.trim());
  const [x, y] = at(c, it, tr, [0.1, 0.18]), w = (it.w ?? 0.8) * c.W, h = (it.h ?? 0.6) * c.H, pad = 30 * T.S;
  const k0 = easeOut(prog(it, tr, 0.45)); if (k0 <= 0) return;
  g.save(); g.globalAlpha *= k0; T.panel(x, y, w, h);
  T.text(String(it.title || '').toUpperCase(), x + pad, y + pad + 24 * T.S, { px: 28, weight: 800, color: '#fff', track: 3, shadow: 0 });
  const L = x + pad + 40 * T.S, R = x + w - pad - 70 * T.S, top = y + pad + 90 * T.S, bot = y + h - pad - 50 * T.S;
  const lo = it.min != null ? num(it.min) : Math.min(...vals) - (Math.max(...vals) - Math.min(...vals)) * 0.1, hi = it.max != null ? num(it.max) : Math.max(...vals) + (Math.max(...vals) - Math.min(...vals)) * 0.1;
  const px = (i) => L + ((R - L) * i) / (vals.length - 1), py = (v) => bot - ((v - lo) / Math.max(1e-9, hi - lo)) * (bot - top);
  g.strokeStyle = 'rgba(255,255,255,0.08)'; g.lineWidth = 1.5 * T.S;
  for (let i = 0; i <= 3; i++) { const yy = top + ((bot - top) * i) / 3; g.beginPath(); g.moveTo(L, yy); g.lineTo(R, yy); g.stroke(); T.text(fmtNum(hi - ((hi - lo) * i) / 3, it.dec ?? 0), L - 10 * T.S, yy + 6 * T.S, { px: 17, weight: 700, color: col('muted'), align: 'right', shadow: 0 }); }
  const k = easeInOut(prog(it, tr, it.dur ?? 2.2, 0.3)), pos = k * (vals.length - 1), idx = Math.floor(pos), frac = pos - idx, color = col(it.color || 'teal');
  const pts = []; for (let i = 0; i <= idx && i < vals.length; i++) pts.push([px(i), py(vals[i])]);
  if (idx < vals.length - 1) { const a = vals[idx], b = vals[idx + 1]; pts.push([px(idx + frac), py(a + (b - a) * frac)]); }
  if (pts.length > 1) {
    g.beginPath(); pts.forEach(([a, b], i) => (i ? g.lineTo(a, b) : g.moveTo(a, b))); g.lineTo(pts[pts.length - 1][0], bot); g.lineTo(pts[0][0], bot); g.closePath();
    const gr = g.createLinearGradient(0, top, 0, bot); gr.addColorStop(0, `${color}55`.length === 9 ? `${color}55` : color); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.globalAlpha *= 0.55; g.fill(); g.globalAlpha /= 0.55;
    g.lineWidth = 4 * T.S; g.lineJoin = 'round'; g.strokeStyle = color; g.beginPath(); pts.forEach(([a, b], i) => (i ? g.lineTo(a, b) : g.moveTo(a, b))); g.stroke();
    const [ex, ey] = pts[pts.length - 1]; g.fillStyle = '#fff'; g.beginPath(); g.arc(ex, ey, 7 * T.S, 0, Math.PI * 2); g.fill();
    const cur = vals[Math.min(vals.length - 1, idx)] + ((vals[Math.min(vals.length - 1, idx + 1)] - vals[Math.min(vals.length - 1, idx)]) * frac);
    T.text(fmtNum(cur, it.dec ?? 0) + (it.unit ? ` ${String(it.unit).toUpperCase()}` : ''), ex, ey - 18 * T.S, { px: 26, weight: 800, color: '#fff', align: 'center', shadow: 0.4 });
  }
  const step = Math.max(1, Math.ceil(vals.length / 10));
  labels.forEach((lb, i) => { if (i % step === 0 || i === vals.length - 1) T.text(String(lb), px(i), bot + 30 * T.S, { px: 18, weight: 700, color: col('muted'), align: 'center', shadow: 0 }); });
  if (it.footnote) T.text(String(it.footnote).toUpperCase(), x + pad, y + h - 16 * T.S, { px: 16, weight: 700, color: col('muted'), track: 1, shadow: 0 });
  g.restore();
}

// ---- number: one big number counting up, with a unit and a small caption above ------------------------------------------------------
function number(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.5, 0.5]), k = easeOut(prog(it, tr, it.dur ?? 1.8)), from = num(it.from, 0), to = num(it.to ?? it.value, 0), px = it.size ?? 200;
  const v = from + (to - from) * k, dec = it.dec ?? (Number.isInteger(to) ? 0 : 1), align = it.align || 'center';
  if (it.caption) T.text(String(it.caption).toUpperCase(), x, y - px * T.S * 0.95, { px: it.caption_size ?? 30, weight: 800, color: col(it.caption_color || 'muted'), track: 6, align, shadow: 0 });
  const txt = (it.prefix || '') + fmtNum(v, dec), w = T.measure(txt, px, 900, 0), unit = it.unit ? String(it.unit).toUpperCase() : '';
  const uw = unit ? T.measure(unit, px * 0.3, 800, 2) + 16 * T.S : 0, total = w + uw, sx = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
  T.text(txt, sx, y, { face: 'display', px, weight: it.weight ?? 900, color: col(it.color || 'white'), shadow: 0.5, glow: it.glow ? col(it.glow) : null });
  if (unit) T.text(unit, sx + w + 16 * T.S, y, { px: px * 0.3, weight: 800, color: col(it.unit_color || 'muted'), track: 2, shadow: 0 });
  if (it.sub) T.text(String(it.sub).toUpperCase(), x, y + px * T.S * 0.28, { px: it.sub_size ?? 28, weight: 700, color: col('muted'), track: 4, align, shadow: 0 });
}

// ---- ring: a percentage as a ring that fills, number in the middle -------------------------------------------------------------------
function ring(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.5, 0.5]), r = (it.r ?? 0.2) * c.H, k = easeInOut(prog(it, tr, it.dur ?? 2)), v = clamp01(num(it.value, 0) / (it.max ? num(it.max) : 100)) * k;
  const lw = (it.width ?? 26) * T.S, color = col(it.color || 'teal');
  g.save(); g.lineCap = 'round'; g.lineWidth = lw; g.strokeStyle = 'rgba(255,255,255,0.1)'; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.stroke();
  g.strokeStyle = color; g.shadowColor = color; g.shadowBlur = 16 * T.S; g.beginPath(); g.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * v); g.stroke(); g.restore();
  T.text(fmtNum(num(it.value, 0) * k, it.dec ?? 0) + (it.unit ?? '%'), x, y + (it.size ?? 96) * T.S * 0.18, { face: 'display', px: it.size ?? 96, weight: 900, color: '#fff', align: 'center', shadow: 0.4 });
  if (it.label) T.text(String(it.label).toUpperCase(), x, y + r + 62 * T.S, { px: 28, weight: 800, color: '#fff', track: 4, align: 'center', shadow: 0 });
  if (it.sub) T.text(String(it.sub).toUpperCase(), x, y + r + 100 * T.S, { px: 20, weight: 700, color: col('muted'), track: 2, align: 'center', shadow: 0 });
}

// ---- versus: two big numbers with names and a VS badge --------------------------------------------------------------------------------
function versus(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.5, 0.5]), k = easeOut(prog(it, tr, 1.5)), gapx = (it.spread ?? 0.26) * c.W, px = it.size ?? 170;
  [[-1, it.a], [1, it.b]].forEach(([s, side], i) => {
    if (!side) return; const color = col(side.color || (i ? 'blue' : 'orange')), cx = x + s * gapx, v = num(side.value) * k;
    T.text(String(side.label || '').toUpperCase(), cx, y - px * T.S * 0.78, { px: 34, weight: 800, color, track: 5, align: 'center', shadow: 0 });
    const w = T.text(fmtNum(v, side.dec ?? 0), cx, y, { px, weight: 900, color: '#fff', align: 'center', shadow: 0.5 });
    if (side.unit) T.text(String(side.unit).toUpperCase(), cx, y + 52 * T.S, { px: 30, weight: 800, color: col('muted'), track: 3, align: 'center', shadow: 0 });
    g.fillStyle = color; g.fillRect(cx - 110 * T.S, y + px * T.S * 0.2 + (side.unit ? 70 * T.S : 20 * T.S), 220 * T.S * k, 6 * T.S);
  });
  g.save(); g.fillStyle = col('ink'); g.strokeStyle = 'rgba(255,255,255,0.5)'; g.lineWidth = 2 * T.S; g.beginPath(); g.arc(x, y - px * T.S * 0.3, 40 * T.S * overshoot(k), 0, Math.PI * 2); g.fill(); g.stroke(); g.restore();
  T.text('VS', x, y - px * T.S * 0.3 + 11 * T.S, { px: 30, weight: 900, color: '#fff', align: 'center', shadow: 0, track: 2 });
}

// ---- ranklist: a ranked list in a card (rank, name, a thin value bar, value) ------------------------------------------------------------
function ranklist(c, it, tr) {
  const { g, T } = c, list = rows(it); if (!list.length) return;
  const [x, y] = at(c, it, tr, [0.1, 0.12]), w = (it.w ?? 0.5) * c.W, rh = (it.row_h ?? 74) * T.S, pad = 28 * T.S, head = 86 * T.S, h = head + list.length * rh + pad;
  const k0 = easeOut(prog(it, tr, 0.45)); if (k0 <= 0) return;
  g.save(); g.globalAlpha *= k0; T.panel(x, y, w, h);
  T.text(String(it.title || '').toUpperCase(), x + pad, y + pad + 24 * T.S, { px: 28, weight: 800, color: '#fff', track: 3, shadow: 0 });
  const max = it.max ? num(it.max) : Math.max(...list.map((r) => num(r.value)), 1);
  list.forEach((r, i) => {
    const t0 = it._in + 0.3 + i * 0.28, k = easeOut(clamp01((tr - t0) / 0.9)); if (k <= 0) return; const ry = y + head + i * rh, color = col(r.color || (i === 0 ? 'gold' : 'blue'));
    g.save(); g.globalAlpha *= clamp01(k * 3);
    T.text(String(i + 1), x + pad + 18 * T.S, ry + rh * 0.62, { px: 30, weight: 900, color, align: 'center', shadow: 0 });
    T.text(String(r.label || '').toUpperCase(), x + pad + 60 * T.S, ry + rh * 0.46, { px: 26, weight: 800, color: '#fff', track: 2, shadow: 0 });
    const bx = x + pad + 60 * T.S, bw = (w - pad * 2 - 60 * T.S - 150 * T.S) * (num(r.value) / max) * k; g.fillStyle = color; g.fillRect(bx, ry + rh * 0.6, Math.max(2, bw), 7 * T.S);
    T.text(fmtNum(num(r.value) * k, r.dec ?? 0) + (it.unit ? ` ${String(it.unit).toUpperCase()}` : ''), x + w - pad, ry + rh * 0.62, { px: 26, weight: 800, color: '#fff', align: 'right', shadow: 0 });
    g.restore();
  });
  g.restore();
}

// ---- fact: the numbered fact card of a "10 facts" video: huge numeral, headline on a colour bar, a body line --------------------------
function fact(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.07, 0.3]), accent = col(it.accent || 'yellow'), nk = overshoot(prog(it, tr, 0.55)), hk = easeOut(prog(it, tr, 0.7, 0.25)), bk = easeOut(prog(it, tr, 0.8, 0.55));
  const big = it.num_size ?? 330, nstr = String(it.num ?? '1');
  if (it.kicker) T.text(String(it.kicker).toUpperCase(), x, y - big * T.S * 0.72, { px: 28, weight: 800, color: col('muted'), track: 8, shadow: 0, alpha: hk });
  g.save(); g.translate(x, y); g.scale(0.7 + 0.3 * nk, 0.7 + 0.3 * nk); g.translate(-x, -y);
  g.globalAlpha *= clamp01(nk * 3); g.font = T.font(big, 900); g.lineJoin = 'round'; g.lineWidth = 5 * T.S; g.strokeStyle = accent; g.textAlign = 'left'; g.textBaseline = 'alphabetic';
  g.fillStyle = accent; g.globalAlpha *= 0.22; g.fillText(nstr, x, y); g.globalAlpha /= 0.22; g.lineWidth = 6 * T.S; g.strokeText(nstr, x, y); g.restore();
  const nw = T.measure(nstr, big, 900) * 1.0 + 40 * T.S, hx = x + nw, hy = y - big * T.S * 0.62, ph = 30 * T.S, title = String(it.title || '').toUpperCase(), tpx = it.title_size ?? 64;
  const tw = T.measure(title, tpx, 900, 2) + ph * 2;
  g.save(); g.beginPath(); g.rect(hx, hy - tpx * T.S * 0.25, tw * hk, tpx * T.S * 1.55); g.clip();
  T.rect(hx, hy - tpx * T.S * 0.25, tw, tpx * T.S * 1.55, accent);
  T.text(title, hx + ph, hy + tpx * T.S * 0.82, { px: tpx, weight: 900, color: col('ink'), track: 2, shadow: 0 }); g.restore();
  if (it.body) {
    const lines = String(it.body).split('|'); lines.forEach((ln, i) => T.text(ln.trim(), hx + 4 * T.S, hy + tpx * T.S * 1.55 + 58 * T.S + i * 50 * T.S, { px: it.body_size ?? 36, weight: 600, color: '#E4EAED', shadow: 0.4, alpha: bk }));
  }
}

// ---- region_label: a place name over a highlighted area (the map adapter draws the outline; this is the name) ------------------------------
function region_label(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.5, 0.5]), k = easeOut(prog(it, tr, 0.8)), color = col(it.color || 'teal'), px = it.size ?? 64;
  const txt = String(it.text || '').toUpperCase();
  T.text(txt, x, y, { face: 'display', px, weight: 900, color, track: 10, align: 'center', glow: 'rgba(45,224,200,0.55)', alpha: k, shadow: 0.5 });
  if (it.sub) T.text(String(it.sub).toUpperCase(), x, y + px * T.S * 0.62, { px: it.sub_size ?? 26, weight: 700, color: '#E4EAED', track: 5, align: 'center', shadow: 0.6, alpha: easeOut(prog(it, tr, 0.8, 0.4)) });
}

// ---- lowerthird: a name strip bottom-left -----------------------------------------------------------------------------------------------------
function lowerthird(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.04, 0.84]), k = easeOut(prog(it, tr, 0.6)), accent = col(it.accent || 'orange');
  const tw = Math.max(T.measure(String(it.title || '').toUpperCase(), 40, 900, 3), it.sub ? T.measure(String(it.sub).toUpperCase(), 22, 700, 3) : 0) + 60 * T.S;
  g.save(); g.beginPath(); g.rect(x, y - 20 * T.S, (tw + 14 * T.S) * k, 140 * T.S); g.clip();
  T.rect(x, y, 10 * T.S, 100 * T.S, accent); T.rect(x + 10 * T.S, y, tw, 100 * T.S, theme().tagBg);
  T.text(String(it.title || '').toUpperCase(), x + 40 * T.S, y + 46 * T.S, { px: 40, weight: 900, color: '#fff', track: 3, shadow: 0 });
  if (it.sub) T.text(String(it.sub).toUpperCase(), x + 40 * T.S, y + 80 * T.S, { px: 22, weight: 700, color: col('muted'), track: 3, shadow: 0 });
  g.restore();
}

// ---- text: a line in any text style (lib/textstyles.mjs) -----------------------------------------------------------------------------------------
function text(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.5, 0.5]);
  const raw = String(it.text ?? ''), shown = it.case === 'keep' ? raw : raw.toUpperCase();
  styledText(T, g, shown, x, y, it.style || 'plain', prog(it, tr, it.dur ?? 1.4),
    { px: it.size ?? 96, weight: it.weight ?? 900, color: col(it.color, '#fff'), track: it.track ?? 0, align: it.align || 'center', accent: it.accent, face: it.face ?? 'display', glow: it.glow ? col(it.glow) : null, shadow: it.shadow ?? 0.4 });
}

// ---- chapter: the "NEXT" title card: tiny tracked kicker, big display title, a thin rule that draws under it ------------------------------------
function chapter(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.06, 0.66]), kk = easeOut(prog(it, tr, 0.7)), tk = easeOut(prog(it, tr, 0.9, 0.2)), rk = easeInOut(prog(it, tr, 1.1, 0.5)), px = it.size ?? 92, accent = col(it.accent || 'gold');
  if (it.kicker) T.text(String(it.kicker).toUpperCase(), x, y - px * T.S * 1.55 - (String(it.title || '').split('|').length - 1) * px * T.S * 1.05, { px: 22, weight: 600, color: accent, track: 9, shadow: 0, alpha: kk });
  const lines = String(it.title || '').split('|').map((s) => s.trim());
  lines.forEach((ln, i) => {
    const ly = y - (lines.length - 1 - i) * px * T.S * 1.05;
    g.save(); g.beginPath(); g.rect(x - 10 * T.S, ly - px * T.S * 0.95, c.W, px * T.S * 1.3); g.clip();
    T.text(ln, x, ly + (1 - tk) * px * T.S * 0.5, { face: 'display', px, weight: it.weight ?? 600, color: col(it.color, '#F4EFE6'), shadow: 0.55, alpha: clamp01(tk * 2.2) }); g.restore();
  });
  const rw = (it.rule_w ?? 0.2) * c.W * rk; g.fillStyle = accent; g.fillRect(x, y + px * T.S * 0.42, rw, Math.max(2, 2 * T.S));
}

// ---- quote: a gold bar, an italic display quote, a small tracked attribution ---------------------------------------------------------------
function quote(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.08, 0.62]), k = easeOut(prog(it, tr, 0.8)), px = it.size ?? 64, accent = col(it.accent || 'gold');
  const lines = String(it.text || '').split('|').map((s) => s.trim()), lh = px * T.S * 1.2, h = lines.length * lh + (it.by ? 70 * T.S : 20 * T.S);
  g.save(); g.globalAlpha *= clamp01(k * 2); g.fillStyle = accent; g.fillRect(x, y - lh * 0.85, 4 * T.S, h * k);
  T.text('“', x + 26 * T.S, y - lh * 0.55, { face: 'display', px: px * 1.5, weight: 700, color: accent, shadow: 0 });
  lines.forEach((ln, i) => { const lk = easeOut(clamp01((tr - it._in - 0.25 - i * 0.28) / 0.7)); T.text(ln, x + 34 * T.S, y + i * lh + (1 - lk) * 16 * T.S, { face: 'display', italic: true, px, weight: 500, color: '#F4EFE6', shadow: 0.5, alpha: lk }); });
  if (it.by) T.text(String(it.by).toUpperCase(), x + 34 * T.S, y + lines.length * lh + 14 * T.S, { px: 20, weight: 600, color: accent, track: 6, shadow: 0, alpha: easeOut(prog(it, tr, 0.6, 0.9)) });
  g.restore();
}

// ---- photocards: framed pictures on the grid plate, a serif caption and a gold rule under each (1-3 cards) -------------------------------------
function drawFramed(c, img, x, y, w, h, k, accent) {
  const { g, T } = c; g.save(); g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 24 * T.S; g.shadowOffsetY = 8 * T.S; g.fillStyle = '#0c0d0f'; g.fillRect(x - 5 * T.S, y - 5 * T.S, w + 10 * T.S, h + 10 * T.S); g.restore();
  g.save(); g.beginPath(); g.rect(x, y, w, h); g.clip();
  if (img) { const ar = img.width / img.height, br = w / h; let sw = img.width, sh = img.height, sx = 0, sy = 0; if (ar > br) { sw = img.height * br; sx = (img.width - sw) / 2; } else { sh = img.width / br; sy = (img.height - sh) / 2; } const z = 1 + 0.05 * k; g.translate(x + w / 2, y + h / 2); g.scale(z, z); g.translate(-(x + w / 2), -(y + h / 2)); g.drawImage(img, sx, sy, sw, sh, x, y, w, h); }
  else { const gr = g.createLinearGradient(x, y, x + w, y + h); gr.addColorStop(0, '#3a3d42'); gr.addColorStop(1, '#1c1e21'); g.fillStyle = gr; g.fillRect(x, y, w, h); }
  g.restore(); g.strokeStyle = accent; g.globalAlpha *= 0.55; g.lineWidth = 1.5 * T.S; g.strokeRect(x - 5 * T.S, y - 5 * T.S, w + 10 * T.S, h + 10 * T.S);
}
function photocards(c, it, tr) {
  const { g, T } = c, list = rows(it); if (!list.length) return;
  const n = Math.min(3, list.length), cw = (it.card_w ?? (n === 1 ? 0.5 : n === 2 ? 0.36 : 0.27)) * c.W, ch = cw * (it.ratio ?? 0.62), gap = 0.04 * c.W, total = n * cw + (n - 1) * gap, accent = col(it.accent || 'gold');
  const x0 = (c.W - total) / 2, y0 = (it.y ?? 0.3) * c.H;
  if (it.grid !== false) { g.save(); g.strokeStyle = 'rgba(255,255,255,0.04)'; g.lineWidth = 1; const s = 48 * T.S; for (let gx = 0; gx < c.W; gx += s) { g.beginPath(); g.moveTo(gx, 0); g.lineTo(gx, c.H); g.stroke(); } for (let gy = 0; gy < c.H; gy += s) { g.beginPath(); g.moveTo(0, gy); g.lineTo(c.W, gy); g.stroke(); } g.restore(); }
  list.slice(0, n).forEach((r, i) => {
    const k = easeOut(clamp01((tr - it._in - i * 0.45) / 0.8)); if (k <= 0) return; const x = x0 + i * (cw + gap), y = y0 + (1 - k) * 26 * T.S;
    g.save(); g.globalAlpha *= clamp01(k * 2.5); drawFramed(c, c.image ? c.image(r.image || r.media) : null, x, y, cw, ch, clamp01((tr - it._in) / 8), accent);
    T.text(r.label || r.caption || '', x, y + ch + 52 * T.S, { face: 'display', px: it.caption_size ?? 36, weight: 500, color: '#EDE6D8', shadow: 0, alpha: easeOut(clamp01((tr - it._in - 0.5 - i * 0.45) / 0.6)) });
    g.fillStyle = accent; g.fillRect(x, y + ch + 72 * T.S, cw * easeInOut(clamp01((tr - it._in - 0.6 - i * 0.45) / 0.9)), Math.max(2, 2 * T.S)); g.restore();
  });
}

// ---- subtitle: lines of display text, the key words picked out in gold as they are spoken ----------------------------------------------------
function subtitle(c, it, tr) {
  const { g, T } = c, [x, y] = at(c, it, tr, [0.5, 0.88]), px = it.size ?? 50, ws = String(it.text || '').split(/\s+/).filter(Boolean), hi = new Set(String(it.highlight || '').toLowerCase().split(/[\s,]+/).filter(Boolean));
  const space = T.measure(' ', px, 500, 0, 'display'), widths = ws.map((w) => T.measure(w, px, 500, 0, 'display')), total = widths.reduce((a, b) => a + b, 0) + space * (ws.length - 1);
  let cx = x - total / 2; const spoken = clamp01((tr - it._in) / (it.dur ?? Math.max(1.2, ws.length * 0.33)));
  ws.forEach((w, i) => { const on = spoken * ws.length > i; T.text(w, cx, y, { face: 'display', px, weight: 500, color: hi.has(w.toLowerCase().replace(/[^\w']/g, '')) && on ? col('gold') : '#F4EFE6', shadow: 0.7, alpha: 0.35 + 0.65 * (on ? 1 : 0) }); cx += widths[i] + space; });
}

export const PRIMS = { ...NEWS_PRIMS, ...TP_PRIMS, ...GEO_PRIMS, chapter, quote, photocards, subtitle, tag, hbars, columns, trend, number, ring, versus, ranklist, fact, region_label, lowerthird, text };
export const PRIM_NAMES = Object.keys(PRIMS);

export function drawItem(c, it, tr) {
  const vis = visibility(it, tr);
  if (vis <= 0.002) return;
  const f = PRIMS[it.p];
  if (!f) throw new Error(`template primitive "${it.p}" is not one of ${PRIM_NAMES.join(', ')}`);
  const { g } = c;
  g.save(); g.globalAlpha = (c.alpha ?? 1) * vis;
  // exit animation: after its "out" time an item leaves by sliding or shrinking (it.exit = slide_left | slide_right | slide_up | slide_down | shrink) while it fades
  if (it.exit && it._out != null && tr > it._out) {
    const k = easeOut(clamp01((tr - it._out) / 0.3)), d = 70 * k * (c.T ? c.T.S : 1);
    if (it.exit === 'slide_left') g.translate(-d, 0); else if (it.exit === 'slide_right') g.translate(d, 0); else if (it.exit === 'slide_up') g.translate(0, -d); else if (it.exit === 'slide_down') g.translate(0, d);
    else if (it.exit === 'shrink') { g.translate(c.W / 2, c.H / 2); g.scale(1 - 0.25 * k, 1 - 0.25 * k); g.translate(-c.W / 2, -c.H / 2); }
  }
  f(c, it, tr);
  g.restore();
}
