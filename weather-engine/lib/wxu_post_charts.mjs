// Post-event graphics, the pure parts (no canvas: the tests check them): where the panels sit, how bars grow and numbers
// count up, how a hydrograph scales, where timeline marks and their labels go. 1920x1080 reference pixels.
// The strings come from weather/layers/*.py; nothing here invents a number -- a count-up only runs up to the value it is given.
import { GEOM } from '../../pakmap-engine/lib/style.mjs';
import { FRAME } from '../../pakmap-engine/lib/layout.mjs';

export const POST = {
  top: 160,                 // below the HUD title and its subtitle
  bottom: FRAME.h - 112,    // above the source line and the raster clock chip
  right: FRAME.w - GEOM.margin.right,
  left: GEOM.margin.left,
  bars: { w: 660, titleH: 96, rowH: 66, foot: 54, radius: 18, barH: 34, labelW: 250, valueW: 120 },
  record: { w: 640, h: 380, radius: 20 },
  hydro: { w: 680, h: 420, radius: 18, padL: 70, padR: 28, padT: 96, padB: 64 },
  legend: { w: 700, h: 118, radius: 14 },
  timeline: { h: 272, radius: 18, padX: 46, level: 64, box: 58 },
  chip: { h: 70, radius: 12, padX: 16, gap: 12, offset: 24, dot: 10, valuePx: 40, labelPx: 20, subPx: 15 },
};

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const easeOut = (t) => 1 - Math.pow(1 - clamp01(t), 3);

/** A panel at the right (anchor 'r', default) or left ('l'), centred in the free band between the HUD and the source line. */
export function sidePanel(w, h, anchor = 'r') {
  const x = anchor === 'l' ? POST.left : POST.right - w;
  const y = Math.round(POST.top + Math.max(0, (POST.bottom - POST.top - h) / 2));
  return { x, y, w, h };
}

/** '31.26 IN' counted up from 0: the number part at progress k (0..1), with the same decimals and the rest of the text kept. */
export function countText(text, k, decimals = null) {
  const m = String(text).match(/^(-?)(\d+(?:\.(\d+))?)(.*)$/);
  if (!m) return String(text);
  const d = decimals ?? (m[3] ? m[3].length : 0);
  const v = Number(m[2]) * easeOut(k);
  return `${m[1]}${v.toFixed(d)}${m[4]}`;
}

/** The bar chart: panel and one row per bar (label | bar | value). */
export function barsLayout(n, anchor = 'r') {
  const b = POST.bars, h = b.titleH + n * b.rowH + b.foot;
  const P = sidePanel(b.w, h, anchor);
  const x0 = P.x + 28 + b.labelW, x1 = P.x + b.w - 28 - b.valueW;
  const rows = Array.from({ length: n }, (_, i) => ({ y: P.y + b.titleH + i * b.rowH, cy: P.y + b.titleH + i * b.rowH + b.rowH / 2 }));
  return { ...P, r: b.radius, rows, barX: x0, barMax: x1 - x0, valueX: P.x + b.w - 28 };
}

/** How far bar i has grown at t (bars start one after another, each growing for `dur` seconds). */
export function barGrow(t, t0, i, stagger = 0.18, dur = 0.9) {
  return easeOut((t - t0 - 0.35 - i * stagger) / dur);
}

/** Bar length in pixels for value v, the longest bar filling `max`. */
export function barLength(v, top, max) {
  return top > 0 ? Math.max(4, (v / top) * max) : 4;
}

/** The record badge panel. */
export function recordLayout(anchor = 'r') {
  const r = POST.record;
  return { ...sidePanel(r.w, r.h, anchor), r: r.radius };
}

/** Hydrograph: the plot box and the y range (a round step that holds the values, the flood lines and the crest). */
export function hydroLayout(values, lines = [], anchor = 'r') {
  const g = POST.hydro, P = sidePanel(g.w, g.h, anchor);
  const vals = values.filter((v) => v != null && Number.isFinite(v)).concat(lines.map((l) => l.value));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
  const step = niceStep((hi - lo) / 4 || 1);
  lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step + (hi % step === 0 ? step : 0);
  const box = { x: P.x + g.padL, y: P.y + g.padT, w: g.w - g.padL - g.padR, h: g.h - g.padT - g.padB };
  return { ...P, r: g.radius, box, lo, hi, step };
}

export function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p;
}

/** Hydrograph points [x, y] (null where the gauge has no value: the line breaks), for i in 0..upto. */
export function hydroPoints(values, L, upto = values.length - 1) {
  const n = Math.max(1, values.length - 1);
  return values.slice(0, Math.floor(upto) + 1).map((v, i) => (v == null ? null
    : [L.box.x + (i / n) * L.box.w, L.box.y + L.box.h - ((v - L.lo) / (L.hi - L.lo)) * L.box.h]));
}

/** The rain legend: a horizontal colour bar at the bottom left, one equal box per stop. */
export function rainLegendLayout(nStops) {
  const g = POST.legend, x = POST.left, y = POST.bottom - g.h;
  const barX = x + 22, barW = g.w - 44, cellW = barW / nStops;
  return { x, y, w: g.w, h: g.h, r: g.radius, barX, barY: y + 54, barH: 20, cellW, cells: Array.from({ length: nStops }, (_, i) => barX + i * cellW) };
}

/** The timeline band along the bottom and its axis. */
export function timelineLayout() {
  const g = POST.timeline, w = POST.right - POST.left, y = POST.bottom - g.h;
  return { x: POST.left, y, w, h: g.h, r: g.radius, axisX: POST.left + g.padX, axisW: w - 2 * g.padX, axisY: y + g.h - 58 };
}

/** Mark labels above the axis: each takes the lowest level (0, 1, 2) where it does not cover a label already placed. */
export function placeMarks(marks, L, widthOf) {
  const placed = [];
  return marks.map((m) => {
    const x = L.axisX + m.f * L.axisW, w = widthOf(m);
    let lx = Math.min(Math.max(x - w / 2, L.x + 12), L.x + L.w - 12 - w);
    let level = 0;
    while (level < 2 && placed.some((p) => p.level === level && lx < p.lx + p.w + 14 && p.lx < lx + w + 14)) level++;
    placed.push({ lx, w, level });
    return { ...m, x, lx, w, level };
  });
}

/** The before/after label at t: which frame's words show, and how far the next has faded in (as wx_raster's frameAt). */
export function baLabelAt(e, t) {
  const lt = t - e.t_in, fr = e.frames || [];
  let i = 0;
  for (let k = 0; k < fr.length; k++) if (fr[k].at <= lt + 1e-9) i = k;
  const next = fr[i + 1], xf = e.crossfade || 0;
  const mix = next && xf > 0 ? clamp01((lt - (next.at - xf)) / xf) : 0;
  return { index: mix >= 0.5 && next ? i + 1 : i, mix };
}

/** A value chip beside a map point: the side ('r', 'l', 't', 'b') keeps the chip inside the frame. */
export function chipLayout(x, y, w, side = 'auto') {
  const c = POST.chip, o = c.offset, h = c.h;
  const at = { r: [x + o, y - h / 2], l: [x - o - w, y - h / 2], t: [x - w / 2, y - o - h], b: [x - w / 2, y + o] };
  const fits = (s) => { const [cx, cy] = at[s]; return cx >= POST.left && cx + w <= POST.right && cy >= 40 && cy + h <= POST.bottom; };
  const s = side !== 'auto' && at[side] ? side : ['r', 'l', 't', 'b'].find(fits) || 'r';
  return { x: at[s][0], y: at[s][1], w, h, r: c.radius, side: s };
}
