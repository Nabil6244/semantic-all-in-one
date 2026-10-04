// Chip geometry. Pure: text is measured through a function passed in
// (measure(text, px) -> width), so the page uses canvas measureText and the
// tests use a fixed-width stand-in. Everything is in 1080 p reference pixels.
import { GEOM } from './style.mjs';

export const FRAME = { w: 1920, h: 1080 };

/** Top-left HUD: title chip + subtitle chip. */
export function hudLayout({ label, sub }, measure) {
  const g = GEOM.title, s = GEOM.subtitle;
  const tw = measure(label, g.fontPx) + 2 * g.padX;
  const title = { x: g.x, y: g.y, w: Math.round(tw), h: g.h, r: g.radius, text: label, px: g.fontPx };
  let subtitle = null;
  if (sub) {
    const sw = measure(sub, s.fontPx) + 2 * s.padX;
    subtitle = { x: s.x, y: g.y + g.h + s.gap + 1, w: Math.round(sw), h: s.h, r: s.radius, text: sub, px: s.fontPx, words: sub.split(/\s+/).filter(Boolean) };
  }
  return { title, subtitle };
}

function anchorXY(anchor, w, h, frame) {
  const m = GEOM.margin;
  switch (anchor) {
    case 'bl': return [40, frame.h - m.bottom - h];
    case 'bc': return [Math.round((frame.w - w) / 2), frame.h - m.bottom - h];
    case 'tr': return [frame.w - m.right - w, 60];
    case 'tl': return [40, 190];
    case 'center': return [Math.round((frame.w - w) / 2), Math.round((frame.h - h) / 2)];
    case 'br':
    default: return [frame.w - m.right - w, frame.h - m.bottom - h];
  }
}

/** Stat chip: big yellow number over an optional small white sub-line, on a dark rounded panel. */
export function statLayout({ anchor = 'br', number, sub }, measure, frame = FRAME) {
  const g = GEOM.stat;
  const nw = measure(number, g.numberPx);
  const sw = sub ? measure(sub, g.subPx) : 0;
  const w = Math.max(g.minW, Math.round(Math.max(nw, sw) + 2 * g.padX));
  const numberCap = Math.round(g.numberPx * 0.7), subCap = Math.round(g.subPx * 0.7);
  const h = sub ? g.padTop + numberCap + g.gap + subCap + g.padBottom : g.padTop + numberCap + g.padBottom - 8;
  const [x, y] = anchorXY(anchor, w, h, frame);
  return {
    x, y, w, h, r: g.radius,
    number: { text: number, px: g.numberPx, cx: x + w / 2, baseline: y + g.padTop + numberCap },
    sub: sub ? { text: sub, px: g.subPx, cx: x + w / 2, baseline: y + g.padTop + numberCap + g.gap + subCap } : null,
  };
}

/** Caption chip: wide dark chip with yellow all-caps text and an optional tiny source line.
 *  Reference 2: 63 px text (44 px caps) on a 108 px high chip, i.e. 32 px above and below the caps. */
export function captionLayout({ text, sub, anchor = 'bc' }, measure, frame = FRAME) {
  const g = GEOM.caption;
  const lines = String(text).split('\n');
  const cap = Math.round(g.fontPx * 0.7), subCap = Math.round(g.subPx * 0.7);
  const tw = Math.max(...lines.map((l) => measure(l, g.fontPx)));
  const sw = sub ? measure(sub, g.subPx) : 0;
  const w = Math.round(Math.max(tw, sw) + 2 * g.padX);
  const textH = cap * lines.length + g.lineGap * (lines.length - 1);
  const h = g.padY * 2 + textH + (sub ? g.subGap + subCap : 0);
  const [x, y] = anchorXY(anchor, w, h, frame);
  return {
    x, y, w, h, r: g.radius,
    lines: lines.map((l, i) => ({ text: l, px: g.fontPx, cx: x + w / 2, baseline: y + g.padY + cap * (i + 1) + g.lineGap * i })),
    sub: sub ? { text: sub, px: g.subPx, cx: x + w / 2, baseline: y + g.padY + textH + g.subGap + subCap } : null,
  };
}

/** Marker label chip beside a map point. side: r | l | t | b. */
export function markerLayout({ x, y, label, value, side = 'r' }, measure) {
  const g = GEOM.marker;
  const text = value ? `${label} · ${value}` : label;
  const w = Math.round(measure(text, g.chipPx) + 2 * g.padX), h = g.chipH;
  let cx = x, cy = y;
  if (side === 'r') { cx = x + g.offset; cy = y - h / 2; }
  else if (side === 'l') { cx = x - g.offset - w; cy = y - h / 2; }
  else if (side === 't') { cx = x - w / 2; cy = y - g.offset - h; }
  else { cx = x - w / 2; cy = y + g.offset; }
  return { dot: { x, y, r: g.dot }, chip: { x: Math.round(cx), y: Math.round(cy), w, h, r: g.radius, text, px: g.chipPx } };
}

/** Pick the side with the most room (inside the safe frame) for a marker label. */
export function pickSide(x, y, w, h, frame = FRAME, prefer = ['r', 'l', 't', 'b']) {
  const g = GEOM.marker;
  const fits = {
    r: x + g.offset + w < frame.w - 40, l: x - g.offset - w > 40,
    t: y - g.offset - h > 40 && x - w / 2 > 40 && x + w / 2 < frame.w - 40,
    b: y + g.offset + h < frame.h - 120 && x - w / 2 > 40 && x + w / 2 < frame.w - 40,
  };
  return prefer.find((s) => fits[s]) || prefer[0];
}

/** Channel-name watermark: where the text and its small play-triangle sit. position: 'br' (reference) or 'bl'. */
export function watermarkLayout({ text, position = 'br' }, measure, frame = FRAME) {
  const g = GEOM.watermark, w = measure(text, g.fontPx) + text.length * 1; // letter spacing 1 px
  const left = position === 'bl';
  const textX = left ? g.left + g.icon : frame.w - g.right - w;
  const iconX = textX - g.icon;
  return { textX, iconX, baseline: frame.h - g.bottom, w, px: g.fontPx, position: left ? 'bl' : 'br' };
}

/** Card size for a shape name or explicit width ([w,h] from the references: 420x303 landscape). */
export function cardSize({ shape = 'landscape', w }) {
  const [bw, bh] = GEOM.card[shape] || GEOM.card.landscape;
  return w ? { w, h: Math.round((w * bh) / bw) } : { w: bw, h: bh };
}

/** A card placed at a screen anchor. Anchors: tl tr ml mr bl br center. */
export function cardRect({ anchor = 'tr', shape, w, offset = [0, 0] }, frame = FRAME) {
  const { w: cw, h: ch } = cardSize({ shape, w }), m = GEOM.card.margin;
  const h = anchor === 'center' ? 'c' : anchor.slice(-1), v = anchor === 'center' ? 'c' : anchor[0]; // tl tr ml mr bl br
  const x = h === 'l' ? m.left : h === 'r' ? frame.w - m.right - cw : Math.round((frame.w - cw) / 2);
  const y = v === 't' ? m.top : v === 'b' ? frame.h - m.bottom - ch : Math.round((frame.h - ch) / 2);
  return { x: x + offset[0], y: y + offset[1], w: cw, h: ch };
}

/** The label chip under a card: yellow, centred, 6 px below the card. */
export function cardLabelRect(card, label, measure) {
  const g = GEOM.card, w = Math.round(measure(label, g.labelPx) + 2 * g.labelPadX);
  return { x: Math.round(card.x + card.w / 2 - w / 2), y: card.y + card.h + g.labelGap, w, h: g.labelH, r: g.labelRadius, text: label, px: g.labelPx };
}

/**
 * A row of 3-7 cards along the bottom: cards shrink as they multiply (3 cards: 420 px wide,
 * 6 cards: 240 px, the way both references do it). align: center | left | right.
 */
export function stripLayout(n, { align = 'center' } = {}, frame = FRAME) {
  const g = GEOM.strip;
  if (n < g.minCards || n > g.maxCards) throw new Error(`a filmstrip needs ${g.minCards}-${g.maxCards} cards (got ${n})`);
  const gap = n <= 3 ? g.gapWide : g.gap, cw = Math.min(g.maxCardW, Math.floor((g.maxWidth - (n - 1) * gap) / n)), ch = Math.round(cw / g.aspect);
  const total = n * cw + (n - 1) * gap;
  const x0 = align === 'left' ? GEOM.card.margin.left : align === 'right' ? frame.w - GEOM.card.margin.right - total : Math.round((frame.w - total) / 2);
  const y = frame.h - g.bottom - ch - GEOM.card.labelH - GEOM.card.labelGap;
  return Array.from({ length: n }, (_, i) => ({ x: x0 + i * (cw + gap), y, w: cw, h: ch }));
}

/** Sticker box: height is a fraction of the frame, width follows the picture; anchored by the bottom-centre. */
export function stickerRect({ x, y, aspect, heightFrac = GEOM.sticker.heightFrac }, frame = FRAME) {
  const h = Math.round(frame.h * heightFrac), w = Math.round(h * aspect);
  return { x: Math.round(x - w / 2), y: Math.round(y - h), w, h };
}

/** Cover-fit source rectangle: which part of an image of size iw x ih fills a w x h box. */
export function coverCrop(iw, ih, w, h) {
  const s = Math.max(w / iw, h / ih), sw = w / s, sh = h / s;
  return { sx: (iw - sw) / 2, sy: (ih - sh) / 2, sw, sh };
}

/** Zone label (a county name on its region): a chip centred on a map point, no dot. */
export function zoneLayout({ x, y, text }, measure) {
  const g = GEOM.zone, w = Math.round(measure(text, g.chipPx) + 2 * g.padX);
  return { x: Math.round(x - w / 2), y: Math.round(y - g.chipH / 2), w, h: g.chipH, r: g.radius, text, px: g.chipPx };
}

/** A stat chip may be placed anywhere (the references move it per shot): pos overrides the anchor. */
export function applyPos(rect, pos) {
  if (!pos) return rect;
  const dx = (pos.x ?? rect.x) - rect.x, dy = (pos.y ?? rect.y) - rect.y;
  const out = { ...rect, x: rect.x + dx, y: rect.y + dy };
  if (rect.number) out.number = { ...rect.number, cx: rect.number.cx + dx, baseline: rect.number.baseline + dy };
  if (rect.sub) out.sub = { ...rect.sub, cx: rect.sub.cx + dx, baseline: rect.sub.baseline + dy };
  if (rect.lines) out.lines = rect.lines.map((l) => ({ ...l, cx: l.cx + dx, baseline: l.baseline + dy }));
  return out;
}
