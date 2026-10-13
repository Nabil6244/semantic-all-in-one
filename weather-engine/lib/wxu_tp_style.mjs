// Weather Teamplate's look, as pure maths (no canvas, so the tests can check it): colours, type sizes, where each graphic sits in
// 1920x1080 reference pixels and when each part of it appears. Measured from the reference video the style was built from
// (docs/weather/teamplate.md): heavy white keyword titles with the key word in a red box, orange place/fact tags, small black
// context tags at the top, a serif italic date over a tracked title for chapter cards, and big count-up numbers.
// The Weather style never uses these (its plugins draw their own types); a Teamplate render converts its events in Python.

export const TP = {
  red: '#D3122B',
  orange: '#E8552B',
  black: 'rgba(10,10,12,0.92)',
  white: '#FFFFFF',
  shadow: 'rgba(0,0,0,0.55)',
  serif: "Georgia, 'Times New Roman', 'Liberation Serif', serif",
  keyword: { px: 100, minPx: 64, weight: 900, spacing: 1.5, gap: 28, boxPadX: 24, boxH: 138, maxW: 1560, lineGap: 22, left: 210, cy: 520, stagger: 0.28, wordIn: 0.18, boxWipe: 0.22 },
  chapter: { kickerPx: 46, titlePx: 92, minPx: 56, weight: 500, spacing: 7, left: 230, kickerY: 612, titleY: 724, kickerIndent: 46, maxW: 1460, kickerIn: 0.45, titleDelay: 0.55, titleWipe: 0.9 },
  tag: { black: { px: 20, h: 40, padX: 18, top: 50, spacing: 2.2, weight: 700 }, orange: { px: 32, h: 60, padX: 22, cy: 486, spacing: 0.6, weight: 700 } },
  stat: { valuePx: 156, labelPx: 30, subPx: 22, left: 300, baseline: 604, gap: 30, typeS: 0.6, compactPx: 24, compactH: 46, compactTop: 50, right: 72 },
  place: { px: 28, h: 48, padX: 16, rise: 64, dot: 7, ring: 46, pulseS: 1.6 },
  lower: { left: 72, bottom: 92, titlePx: 56, kickerPx: 20, subPx: 22, kickerH: 36 },
  vignette: { map: 0.38, dip: 0.34, flat: 0.40 },
};

const clamp01 = (v) => Math.max(0, Math.min(1, v));
export const easeOut = (k) => 1 - Math.pow(1 - clamp01(k), 3);

/** The keyword card's lines: [{words: [{text, accent}], width}], laid out from measured word widths (`measure(text, px)`).
 *  One line when it fits; otherwise the words before the key word on the first line(s), the key word on the last line (as in
 *  "EROSION PLANS / LACKING"). The type shrinks (never below minPx) until the widest line fits. */
export function keywordLayout(words, accent, measure) {
  const K = TP.keyword;
  for (let px = K.px; px >= K.minPx; px -= 4) {
    const w = (t, a) => measure(t, px) + (a ? 2 * K.boxPadX : 0);
    const all = words.map((t, i) => ({ text: t, accent: i === accent, w: w(t, i === accent) }));
    const width = (ws) => ws.reduce((s, x) => s + x.w, 0) + K.gap * (ws.length - 1);
    if (width(all) <= K.maxW) return { px, lines: [{ words: all, width: width(all) }], align: 'center' };
    const head = all.filter((x) => !x.accent), key = all.filter((x) => x.accent);
    const lines = [];
    let cur = [];
    for (const x of head) {
      if (cur.length && width([...cur, x]) > K.maxW) { lines.push(cur); cur = []; }
      cur.push(x);
    }
    if (cur.length) lines.push(cur);
    lines.push(key);
    if (lines.every((l) => width(l) <= K.maxW) && lines.length <= 3) return { px, lines: lines.map((l) => ({ words: l, width: width(l) })), align: 'left' };
  }
  const px = K.minPx, all = words.map((t, i) => ({ text: t, accent: i === accent, w: measure(t, px) + (i === accent ? 2 * K.boxPadX : 0) }));
  return { px, lines: [{ words: all, width: all.reduce((s, x) => s + x.w, 0) + K.gap * (all.length - 1) }], align: 'center' };
}

/** Where each word of a keyword layout sits: [{text, accent, x, y (baseline), w, line}] in 1080p units. */
export function keywordPositions(layout) {
  const K = TP.keyword, lineH = K.boxH + K.lineGap, n = layout.lines.length;
  const top = K.cy - (n * lineH - K.lineGap) / 2;
  const out = [];
  layout.lines.forEach((line, li) => {
    let x = layout.align === 'center' ? (1920 - line.width) / 2 : K.left;
    const baseline = top + li * lineH + K.boxH / 2 + layout.px * 0.36;
    for (const wd of line.words) { out.push({ ...wd, x, y: baseline, line: li }); x += wd.w + K.gap; }
  });
  return out;
}

/** How far word i has appeared at t (0..1): one after another, `stagger` apart. */
export const wordIn = (t, t0, i) => easeOut((t - t0 - i * TP.keyword.stagger) / TP.keyword.wordIn);

/** The chapter card's title wipe (0..1) and kicker fade (0..1) at t. */
export function chapterProgress(t, t0) {
  const C = TP.chapter;
  return { kicker: easeOut((t - t0) / C.kickerIn), title: clamp01((t - t0 - C.titleDelay) / C.titleWipe) };
}

/** The black context tag (top centre) or the orange fact tag (centre): its box for a text `textW` wide. */
export function tagRect(tone, textW) {
  const T = TP.tag[tone] || TP.tag.black, w = textW + 2 * T.padX;
  const y = tone === 'orange' ? T.cy - T.h / 2 : T.top;
  return { x: (1920 - w) / 2, y, w, h: T.h };
}

/** The count-up stat: which phase it is in at t ('none' | 'big' | 'compact') and how much of its label is typed (0..1). */
export function statPhase(e, t) {
  if (t < e.big_in) return { phase: 'none', typed: 0 };
  if (t < e.big_out) return { phase: 'big', typed: clamp01((t - e.big_in - 0.35 - (e.count_s ?? 2)) / TP.stat.typeS) };
  return { phase: 'compact', typed: 1 };
}

/** The compact stat tag, top right: its box for a text `textW` wide. */
export function compactRect(textW) {
  const S = TP.stat, w = textW + 2 * 18;
  return { x: 1920 - S.right - w, y: S.compactTop, w, h: S.compactH };
}

/** A place tag above its point, or below when the space above is taken (`taken`: rects) or off frame. */
export function placeRect(x, y, textW, taken = []) {
  const P = TP.place, w = textW + 2 * P.padX;
  const hits = (r) => taken.some((o) => r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h);
  const above = { x: Math.min(1920 - 40 - w, Math.max(40, x - w / 2)), y: y - P.rise - P.h, w, h: P.h, side: 'above' };
  if (above.y >= 40 && !hits(above)) return above;
  return { ...above, y: y + P.rise, side: 'below' };
}

/** The pulse ring's radius and strength at t (repeats every pulseS seconds). */
export function pulse(t, t0) {
  const P = TP.place, k = (((t - t0) % P.pulseS) + P.pulseS) % P.pulseS / P.pulseS;
  return { r: P.dot + (P.ring - P.dot) * easeOut(k), a: 1 - k };
}

/** 1 outside the `hide` windows ([[a, b], ...]: a title card is up), fading to 0 inside them. */
export function shown(hide, t, fade = 0.3) {
  let k = 1;
  for (const [a, b] of hide || []) k = Math.min(k, Math.max(0, Math.min(1, Math.max((a - t) / fade, (t - b) / fade))));
  return k;
}
