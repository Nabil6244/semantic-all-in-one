// Pure maths of the Weather News graphics (no canvas, so the tests can check it): the counter's count-up, how many report
// dots have appeared, the radar legend's dBZ scale and where the news panels sit (1920x1080 reference pixels, clear of
// pakMap's HUD title top left, the alert legend middle left, the clock chip and source line bottom left, the watermark
// bottom right).
import { GEOM } from '../../pakmap-engine/lib/style.mjs';
import { FRAME } from '../../pakmap-engine/lib/layout.mjs';

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const easeOutCubic = (k) => 1 - Math.pow(1 - k, 3);

/** The number a counter shows at t: 0 at t_in + delay, the full value count_s later (eased, whole numbers). */
export function countAt(e, t, delay = 0.35) {
  const k = clamp01((t - e.t_in - delay) / Math.max(0.01, e.count_s ?? 2));
  return Math.round(easeOutCubic(k) * e.value);
}

/** How many of the points (each with `at`, narration seconds) have appeared by t, per kind: {total, byKind}. */
export function revealed(points, t) {
  const byKind = {};
  let total = 0;
  for (const p of points || []) if (p.at <= t) { total++; byKind[p.kind] = (byKind[p.kind] || 0) + 1; }
  return { total, byKind };
}

/** How far a point has popped in (0..1) at t. */
export const popIn = (p, t, dur = 0.3) => clamp01((t - p.at) / dur);

/** x on the radar legend's bar of a dBZ value (the bar runs from the first stop to the last). */
export function dbzX(dbz, stops, x0, w) {
  const a = stops[0].dbz, b = stops[stops.length - 1].dbz;
  return x0 + clamp01((dbz - a) / (b - a)) * w;
}

export const NEWS = {
  legend: { w: 400, h: 92, right: GEOM.margin.right, bottom: 120, barH: 16, px: 15, titlePx: 16 },
  counter: { top: 52, minW: 300, h: 168, padX: 26, labelPx: 22, valuePx: 92, subPx: 16 },
  reports: { right: GEOM.margin.right, rowH: 38, px: 19, padX: 16, padY: 12, dot: 9, titleH: 34 },
  points: { chipH: 34, px: 18, padX: 12, offset: 16 },
  credit: { left: 44, bottom: 72, h: 40, px: 19, padX: 16 },
};

/** The radar legend: bottom right, above the watermark. */
export function legendRect() {
  const L = NEWS.legend;
  return { x: FRAME.w - L.right - L.w, y: FRAME.h - L.bottom - L.h, w: L.w, h: L.h };
}

/** The counter panel at an anchor (tr | tl | br | bl), `w` wide. */
export function counterRect(anchor, w) {
  const C = NEWS.counter;
  const right = anchor === 'tr' || anchor === 'br';
  const top = anchor === 'tr' || anchor === 'tl';
  const x = right ? FRAME.w - GEOM.margin.right - w : GEOM.margin.left;
  const y = top ? C.top + (anchor === 'tl' ? 90 : 0) : FRAME.h - 140 - C.h;   // tl sits under the HUD title
  return { x, y, w, h: C.h };
}

/** The storm-reports legend: right side, vertically centred. */
export function reportsRect(rows, widest) {
  const R = NEWS.reports;
  const w = Math.max(260, widest + 3 * R.padX + 2 * R.dot + 70), h = R.titleH + rows * R.rowH + 2 * R.padY;
  return { x: FRAME.w - R.right - w, y: Math.round((FRAME.h - h) / 2), w, h };
}

/** A storm point's label chip: right of the dot, else left when it would leave the frame. */
export function pointChip(x, y, w) {
  const P = NEWS.points;
  const right = { x: x + P.offset, y: y - P.chipH / 2, w, h: P.chipH };
  if (right.x + w <= FRAME.w - GEOM.margin.right) return right;
  return { x: x - P.offset - w, y: y - P.chipH / 2, w, h: P.chipH };
}

/** The credit chip on footage: bottom left. */
export function creditRect(w) {
  const C = NEWS.credit;
  return { x: C.left, y: FRAME.h - C.bottom - C.h, w, h: C.h };
}
