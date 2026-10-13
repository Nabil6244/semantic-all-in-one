// Where the weather graphics sit, in 1920x1080 reference pixels (pure: no canvas, so the tests can check it).
// They keep clear of pakMap's own furniture: the HUD title (top left), stat chips (bottom right), the watermark
// (bottom right) and the frame margins in pakmap-engine/lib/style.mjs GEOM.margin.
import { GEOM } from '../../pakmap-engine/lib/style.mjs';
import { FRAME, pickSide } from '../../pakmap-engine/lib/layout.mjs';

export const WX = {
  strip: { cellW: 196, h: 236, bottom: 112, radius: 18, padX: 18, titleH: 44, titlePx: 24, dowPx: 26, icon: 76, hiPx: 46, loPx: 32, popPx: 22 },
  now: { w: 440, h: 232, top: 52, radius: 18, titleH: 44, titlePx: 24, icon: 104, tempPx: 96, textPx: 26, footPx: 18 },
  marker: { h: 66, radius: 12, icon: 50, tempPx: 44, cityPx: 20, tagPx: 15, padX: 12, gap: 10, offset: 22, dot: 9 },
  legend: { left: 44, rowH: 40, px: 20, swatch: 22, padX: 16, padY: 12, radius: 12, gap: 8 },
  source: { left: 44, baselineFromBottom: 30, px: 18, padX: 12, h: 30, radius: 8 },
};

/** The forecast strip: a panel centred at the bottom, one column per day. */
export function stripLayout(nDays) {
  const s = WX.strip;
  const w = Math.min(FRAME.w - GEOM.margin.left - GEOM.margin.right, nDays * s.cellW + 2 * s.padX);
  const x = Math.round((FRAME.w - w) / 2), y = FRAME.h - s.bottom - s.h;
  const cellW = (w - 2 * s.padX) / nDays;
  const cells = Array.from({ length: nDays }, (_, i) => ({ x: x + s.padX + i * cellW, w: cellW, cx: x + s.padX + (i + 0.5) * cellW }));
  return { x, y, w, h: s.h, r: s.radius, title: { x, y: y - s.titleH + 6, h: s.titleH, px: s.titlePx }, cells };
}

/** The "now" card: top right by default (tr), or top left (tl). */
export function nowLayout(anchor = 'tr') {
  const n = WX.now;
  const x = anchor === 'tl' ? GEOM.margin.left : FRAME.w - GEOM.margin.right - n.w;
  return { x, y: n.top + n.titleH, w: n.w, h: n.h, r: n.radius, title: { x, y: n.top, h: n.titleH, px: n.titlePx } };
}

/** A temperature marker: a dot at the city and a chip beside it (the side is kept for the whole shot). */
export function tempChipLayout({ x, y, side, width }) {
  const m = WX.marker, h = m.h, o = m.offset;
  const sides = {
    r: { cx: x + o, cy: y - h / 2 },
    l: { cx: x - o - width, cy: y - h / 2 },
    t: { cx: x - width / 2, cy: y - o - h },
    b: { cx: x - width / 2, cy: y + o },
  };
  const p = sides[side] || sides.r;
  return { x: p.cx, y: p.cy, w: width, h, r: m.radius };
}

const hits = (r, taken) => taken.some((o) => r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h);

/** True when a chip on `side` would cover one of the chips already on screen (`taken`: rects). */
export function chipCovers(x, y, width, side, taken = []) {
  return hits(tempChipLayout({ x, y, side, width }), taken);
}

/** The side for a temperature chip: a forced side as given; otherwise pakMap's pick, unless that chip would cover a chip
 *  already on screen (`taken`: rects) or leave the frame, then the first side that does neither (else pakMap's pick). */
export function chooseSide(x, y, width, side, taken = []) {
  if (side && side !== 'auto') return side;
  const first = pickSide(x, y, width + WX.marker.offset, WX.marker.h);
  const fits = (s) => {
    const r = tempChipLayout({ x, y, side: s, width });
    const inFrame = r.x >= 0 && r.y >= 0 && r.x + r.w <= FRAME.w && r.y + r.h <= FRAME.h;
    return inFrame && !hits(r, taken);
  };
  return [first, 'r', 'l', 't', 'b'].find(fits) || first;
}

/** The alert legend: a column of chips at the left, vertically centred. */
export function legendLayout(n, widest) {
  const g = WX.legend;
  const w = widest + g.swatch + 3 * g.padX, h = n * g.rowH + (n - 1) * g.gap + 2 * g.padY;
  return { x: g.left, y: Math.round((FRAME.h - h) / 2), w, h, r: g.radius };
}

/** The source line: one short line at the bottom left. */
export function sourceLayout(textW) {
  const s = WX.source;
  return { x: s.left, y: FRAME.h - s.baselineFromBottom - s.h + 9, w: textW + 2 * s.padX, h: s.h, r: s.radius, baseline: FRAME.h - s.baselineFromBottom };
}
