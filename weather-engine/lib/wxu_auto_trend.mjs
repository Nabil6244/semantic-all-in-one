// The temperature trend chart (lib/layers/temp_trend.mjs), its pure maths: where the panel sits, where each high and low point
// lands, and how far the lines have drawn at time t. 1920x1080 reference pixels; no canvas, so the tests can check it.
const FRAME_W = 1920, FRAME_H = 1080;
const MARGIN = { left: 44, right: 63 };   // pakmap-engine/lib/style.mjs GEOM.margin

export const TREND = { cellW: 196, h: 300, bottom: 112, radius: 18, padX: 18, titleH: 44, titlePx: 24, dowPx: 24, numPx: 26,
  plotTop: 46, plotBottom: 78, dot: 7, drawIn: 1.4, delay: 0.3, pop: 0.35 };

/** The panel: centred at the bottom where the forecast strip sits, one column per day. */
export function trendLayout(nDays) {
  const s = TREND;
  const w = Math.min(FRAME_W - MARGIN.left - MARGIN.right, nDays * s.cellW + 2 * s.padX);
  const x = Math.round((FRAME_W - w) / 2), y = FRAME_H - s.bottom - s.h;
  const cellW = (w - 2 * s.padX) / nDays;
  const cols = Array.from({ length: nDays }, (_, i) => x + s.padX + (i + 0.5) * cellW);
  return { x, y, w, h: s.h, r: s.radius, cellW, cols, plot: { top: y + s.plotTop, bottom: y + s.h - s.plotBottom },
    title: { x, y: y - s.titleH + 6, h: s.titleH, px: s.titlePx }, dowY: y + s.h - 26 };
}

/** Points of the two lines: highs and lows on one shared scale (the lowest low at the bottom, the highest high at the top). */
export function trendPoints(days, L) {
  const vals = days.flatMap((d) => [d.hi_v, d.lo_v]).filter((v) => Number.isFinite(v));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const top = L.plot.top + 20, bottom = L.plot.bottom - 20;   // room for the numbers above the highs and below the lows
  const y = (v) => (hi === lo ? (top + bottom) / 2 : bottom - ((v - lo) / (hi - lo)) * (bottom - top));
  const highs = days.map((d, i) => ({ x: L.cols[i], y: y(d.hi_v), text: d.hi, i }));
  const lows = days.map((d, i) => (Number.isFinite(d.lo_v) ? { x: L.cols[i], y: y(d.lo_v), text: d.lo, i } : null)).filter(Boolean);
  return { highs, lows };
}

/** How far the lines have drawn at t, in points (0 .. n-1): they start after a short delay and reach the last day in drawIn s. */
export function drawProgress(t, tIn, n) {
  if (n <= 1) return t >= tIn + TREND.delay ? 0 : -1;
  const k = (t - tIn - TREND.delay) / TREND.drawIn;
  return k < 0 ? -1 : Math.min(1, k) * (n - 1);
}

/** The visible part of a line at progress p: whole points up to p and the point part-way to the next one. */
export function partialLine(pts, p) {
  if (p < 0 || !pts.length) return [];
  const out = [];
  for (const q of pts) {
    if (q.i <= p) out.push({ x: q.x, y: q.y });
  }
  const last = pts.findIndex((q) => q.i > p);
  if (last > 0) {
    const a = pts[last - 1], b = pts[last], f = (p - a.i) / (b.i - a.i);
    out.push({ x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f });
  }
  return out;
}

/** A point's pop (0..1+, overshooting) once the line reaches it. */
export function popScale(t, tIn, i, n) {
  const reach = tIn + TREND.delay + (n <= 1 ? 0 : (i / (n - 1)) * TREND.drawIn);
  const k = Math.max(0, Math.min(1, (t - reach) / TREND.pop));
  if (k <= 0) return 0;
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2);
}
