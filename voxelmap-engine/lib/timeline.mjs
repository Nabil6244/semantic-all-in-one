// Story spec + narration timing -> everything the page draws at each moment. Pure.
//
// Narration-aware travel: the camera flies to a beat's place inside the silence before that beat's first sentence, and
// holds (with drift or an orbit) while it is spoken. Narration timing comes from a real voiceover (sentences with start/end,
// see tools/narration_timing.py) or, with none, is planned here from word counts with the beat's `gap` as the silence.

import { travelSeconds } from './camera3d.mjs';
import { chooseShot, shotFrames, direct, holdEndFrame, RUNG } from './director.mjs';

export { RUNG };
const MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
// Dates are YYYY-MM; a leading minus is a year before the common era ("-0753-04" = APR 753 BC).
const yearOf = (d) => Number(d.slice(0, d.length - 3)), monthOf = (d) => Number(d.slice(-2));
export const monthLabel = (d) => { const y = yearOf(d); return `${MON[monthOf(d) - 1]} ${y < 0 ? `${-y} BC` : y < 1000 ? `${y} AD` : y}`; };
export const monthIndex = (d) => yearOf(d) * 12 + monthOf(d) - 1;
const fromIndex = (i) => { const y = Math.floor(i / 12); return `${y < 0 ? '-' : ''}${String(Math.abs(y)).padStart(4, '0')}-${String((i % 12 + 12) % 12 + 1).padStart(2, '0')}`; };
const words = (s) => s.split(/\s+/).filter(Boolean).length;

export const CAPTION_CLEAR_GAP = 8;   // a silence longer than this empties the caption log...
export const CAPTION_LINGER = 3;      // ...this long after the last word
export const CARD_HOLD = 4.2;
export const CARD_SHOW = 5.5;     // seconds a photo card stays on screen when the story gives no hold
export const LIGHTS = ['day', 'dawn', 'sunset', 'night', 'fog'];
export const DEFAULT_CREDITS = ['Elevation: Terrain Tiles on AWS Open Data (Mapzen Terrarium)', 'Coastlines, countries and provinces: Natural Earth', 'Font: Monocraft by Idrees Hassan (SIL OFL 1.1)'];
export const MAX_SQUEEZE = 0.15;
// A globe beat with a long read leaves after this many seconds (its words go on over the descent): the opening never sits on a
// spinning planet for 10 s while the narrator tells the legend.
export const GLOBE_HOLD = 5.0;      // a move may run this much faster than its natural time to fit a real pause

/** Every beat's shot and framings, in story order (the director's choices, which depend on the shot before). */
export function framesFor(spec) {
  const out = []; let prevShot = null;
  spec.beats.forEach((b, i) => { const shot = chooseShot(spec, i, prevShot); out.push({ shot, ...shotFrames(b, shot, b.seed ?? i) }); prevShot = shot; });
  return out;
}

/** Planned narration when there is no voiceover: every sentence timed from its words; `gap` (or the move's time) before a beat. */
export function planNarration(spec, lead = 3.2) {
  const out = []; let t = lead;
  const frames = framesFor(spec);
  spec.beats.forEach((b, i) => {
    const need = i ? travelSeconds(frames[i - 1].end, frames[i].start) + 0.7 : 0;
    // a chapter's card goes on its first beat that is not a globe beat (on a globe opening, the descent carries it)
    const prevB = spec.beats[i - 1], chapterStart = i > 0 && b.rung !== 'globe' && (b.chapter !== prevB.chapter || (prevB.rung === 'globe' && prevB.chapter === b.chapter && !spec.beats.slice(0, i - 1).some((x) => x.chapter === b.chapter)));
    const gap = Math.max(b.gap ?? 0, need, chapterStart ? CARD_HOLD + 0.8 : 0, i ? 0.6 : 0);
    t += i ? gap : 0;
    b.sentences.forEach((text, k) => {
      const dur = Math.max(1.6, words(text) / spec.wpm * 60);
      out.push({ beat: i, text, start: +t.toFixed(3), end: +(t + dur).toFixed(3) });
      t += dur + (k < b.sentences.length - 1 ? 0.25 : 0);
    });
  });
  return out;
}

const STOP = new Set('a an and are as at be but by for from had has have he her his i in into is it its of on or our she so that the their them then there they this to was we were what when which who will with you your yes also just like about because been than very'.split(' '));
const tokens = (s) => new Set(String(s).toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w)).map((w) => w.replace(/(ies|es|s)$/, '')));
function overlap(a, b) { if (!a.size || !b.size) return 0; let n = 0; for (const w of a) if (b.has(w)) n++; return n / Math.sqrt(a.size * b.size); }

/**
 * Assign real voiceover sentences to beats by what they SAY, not by count. A voiceover is often the full script while the CSV
 * carries a shorter line per beat (Rome: 236 spoken sentences, 105 CSV sentences): pairing them one-to-one drifted every scene
 * away from its words and cut the film off where the CSV ran out. Every spoken sentence goes to one beat, in order (a beat
 * never comes back), each beat gets at least one, and the split maximises word overlap between each sentence and its beat's text,
 * with a small pull toward an even pace where the words say nothing. Captions show what is actually said.
 * When there are fewer spoken sentences than beats, the old one-to-one pairing is kept.
 */
export function attachNarration(spec, sentences) {
  const B = spec.beats.length, N = sentences.length;
  if (!N) return [];
  if (N < B) {
    const out = []; let j = 0;
    spec.beats.forEach((b, i) => { for (let k = 0; k < b.sentences.length && j < N; k++, j++) out.push({ ...sentences[j], beat: i, text: b.sentences[k] }); });
    return out;
  }
  const bt = spec.beats.map((b) => tokens([b.place, ...b.sentences].join(' ')));
  const st = sentences.map((x) => tokens(x.text || ''));
  const score = (j, i) => overlap(st[j], bt[i]) - 0.35 * Math.abs((j + 0.5) / N - (i + 0.5) / B);
  // dp[j][i]: best total with sentence j on beat i; from (j-1, i) stay or (j-1, i-1) advance
  const NEG = -1e9, dp = Array.from({ length: N }, () => new Float64Array(B).fill(NEG)), from = Array.from({ length: N }, () => new Int8Array(B));
  dp[0][0] = score(0, 0);
  for (let j = 1; j < N; j++) {
    const lo = Math.max(0, B - (N - j)), hi = Math.min(B - 1, j);
    for (let i = lo; i <= hi; i++) {
      const stay = dp[j - 1][i], adv = i ? dp[j - 1][i - 1] : NEG;
      if (stay >= adv) { dp[j][i] = stay + score(j, i); from[j][i] = 0; } else { dp[j][i] = adv + score(j, i); from[j][i] = 1; }
    }
  }
  const beatOf = new Array(N); let i = B - 1;
  for (let j = N - 1; j >= 0; j--) { beatOf[j] = i; if (j && from[j][i]) i--; }
  return sentences.map((x, j) => ({ ...x, beat: beatOf[j], text: x.text || spec.beats[beatOf[j]].sentences[0] || '' }));
}

export function buildTimeline(spec, narration = null) {
  const said = narration ? attachNarration(spec, narration) : planNarration(spec);
  const warnings = [];
  const firstOf = (i) => said.find((s) => s.beat === i), lastOf = (i) => [...said].reverse().find((s) => s.beat === i);
  const end = said.length ? said[said.length - 1].end + 3.5 : 10;

  // camera: every move flies inside the silence before its beat; the director's shot runs through the beat's speech
  const frames = framesFor(spec), beats = [], notes = [];
  let prevEnd = 0, prevFrame = null, leftEarly = false;
  spec.beats.forEach((b, i) => {
    const f = firstOf(i), l = lastOf(i);
    if (!f) { warnings.push(`beat ${b.id} has no narration`); return; }
    let travelT0 = f.start, travelT1 = f.start;
    if (prevFrame) {
      const need = travelSeconds(prevFrame, frames[i].start), silence = f.start - prevEnd;
      // a tight silence first gives up the margins (leave 0.1 s after the last word, land 0.2 s before the next), then
      // lets the move run up to MAX_SQUEEZE faster; only a move that still does not fit runs into the narration
      const [lead, land] = silence - 0.6 >= need ? [0.2, 0.4] : [0.1, 0.2];
      travelT1 = Math.max(prevEnd + lead + 0.1, f.start - land);
      travelT0 = Math.max(prevEnd + lead, travelT1 - need);
      if (leftEarly) { travelT0 = prevEnd; travelT1 = prevEnd + need; }   // the globe let go mid-speech: fly at the move's own pace
      const fit = travelT1 - travelT0;
      if (!leftEarly && fit < need - 0.01) {
        if (fit >= need * (1 - MAX_SQUEEZE)) notes.push(`beat ${b.id}: move squeezed to ${fit.toFixed(2)} s from ${need.toFixed(2)} s to fit the silence`);
        else { travelT1 = travelT0 + need * (1 - MAX_SQUEEZE); warnings.push(`beat ${b.id}: the silence before it is ${silence.toFixed(1)} s, the move needs at least ${(need * (1 - MAX_SQUEEZE)).toFixed(1)} s; the move runs into the narration`); }
      }
    }
    const longGlobe = b.rung === 'globe' && i < spec.beats.length - 1 && l.end - Math.max(f.start, travelT1) > GLOBE_HOLD + 1;
    prevEnd = longGlobe ? Math.max(f.start, travelT1) + GLOBE_HOLD : Math.max(l.end, travelT1 + 0.5); prevFrame = longGlobe ? frames[i].end : holdEndFrame(b, frames[i].shot, b.seed ?? i, prevEnd - travelT1); leftEarly = longGlobe;
    beats.push({ i, holdT1: prevEnd, id: b.id, date: b.date, rung: b.rung, shot: frames[i].shot, travelT0, travelT1, speakT0: f.start, speakT1: l.end, site: b.site, lon: b.lon, lat: b.lat, seed: b.seed, chapter: b.chapter, territory: b.territory, place: b.place });
  });
  const { camera, shots } = direct(spec, beats, end);

  // date box: the beat's month from the moment the camera leaves for it; a skip of over a year steps through months
  const dates = [];
  beats.forEach((b, k) => {
    const prevD = k ? beats[k - 1].date : null;
    const gapI = prevD ? monthIndex(b.date) - monthIndex(prevD) : 0;
    if (gapI > 12) {
      const steps = 4, span = Math.min(2.4, Math.max(1, b.speakT0 - b.travelT0 - 0.3));
      for (let s = 1; s <= steps; s++) dates.push({ t: b.travelT0 + span * (s / steps), label: monthLabel(fromIndex(monthIndex(prevD) + Math.round(gapI * s / steps))) });
    } else dates.push({ t: k ? b.travelT0 : 0, label: monthLabel(b.date) });
  });

  // chapter cards: in the silence before the chapter's first sentence
  const chapters = [];
  spec.chapters.forEach((c, n) => {
    const first = beats.find((x) => x.chapter === c.id), b = beats.find((x) => x.chapter === c.id && x.rung !== 'globe') || first;
    if (!b) return;
    const opensOnGlobe = first && first.rung === 'globe' && b !== first;
    const t0 = n === 0 && !opensOnGlobe ? Math.max(0.3, b.speakT0 - CARD_HOLD) : b.travelT0 + 0.3;
    const t1 = Math.max(t0 + 2.5, Math.min(t0 + CARD_HOLD, b.speakT0 + 0.8));
    if (b.speakT0 - b.travelT0 < 2.5 && (n > 0 || opensOnGlobe)) warnings.push(`chapter ${c.id}: the card has under 2.5 s of silence`);
    chapters.push({ n: n + 1, id: c.id, title: c.title, date: monthLabel(b.date), t: n === 0 ? 0 : first.travelT0, cardT0: t0, cardT1: t1 });
  });

  // captions: one sentence per line, tagged with its beat's month
  const captions = said.map((s) => ({ t0: s.start, t1: s.end, text: s.text, tag: `[${monthLabel(spec.beats[s.beat].date)}]` }));

  // territory: a beat that names a state switches to it when the camera leaves for that beat
  const terr = [];
  beats.forEach((b) => { if (b.territory) terr.push({ t: b.travelT0 + 0.6, key: b.territory }); });

  // a globe opening carries the film's title over the planet until the descent begins
  const g0 = beats[0] && beats[0].rung === 'globe' ? beats[0] : null, next = g0 && beats[1];
  const title = g0 ? { text: spec.title, sub: spec.subtitle || '', t0: 0.4, t1: next ? next.travelT0 + 0.4 : g0.speakT1 } : null;
  // light: a beat's preset from the moment the camera leaves for it (default day); the page blends over LIGHT_BLEND s
  const lights = [{ t: 0, preset: 'day' }];
  beats.forEach((bb) => { const L = spec.beats[bb.i].light || 'day'; if (L !== lights[lights.length - 1].preset) lights.push({ t: bb.travelT0, preset: L }); });
  for (const L of lights) if (!LIGHTS.includes(L.preset)) warnings.push(`light "${L.preset}" is unknown (use ${LIGHTS.join(', ')})`);
  // map-scale effects: live from the camera's departure for their beat until 2 s after its last word
  const effects = [];
  beats.forEach((bb) => { for (const e of spec.beats[bb.i].effects || []) effects.push({ ...e, t0: bb.travelT0, t1: bb.speakT1 + 2, beat: bb.id }); });
  // museum objects: an inset while their beat is spoken; the item bar keeps every object shown so far
  const museum = [];
  beats.forEach((bb) => { const m = spec.beats[bb.i].museum; if (m) museum.push({ ...m, t0: bb.speakT0, t1: bb.speakT1 + 1.5, beat: bb.id }); });
  // photo cards: a card appears on the sentence it shows (found by its words), else at its stated second, else spread over the beat
  const cards = [];
  beats.forEach((bb) => {
    const list = spec.beats[bb.i].cards || [];
    list.forEach((c, k) => {
      const mine = said.filter((x) => x.beat === bb.i), ct = tokens(c.words || '');
      let t0 = null;
      if (c.t != null) t0 = bb.speakT0 + Number(c.t);
      else if (ct.size) { let best = 0; for (const x of mine) { const o = overlap(tokens(x.text || ''), ct); if (o > best) { best = o; t0 = x.start; } } }
      const hold = c.hold ?? CARD_SHOW;
      if (t0 == null) t0 = bb.speakT0 + 1 + Math.max(0, bb.speakT1 - bb.speakT0 - hold - 1) * (list.length > 1 ? k / (list.length - 1) : 0.15);
      const t1 = Math.min(t0 + hold, bb.speakT1 + 1.5);
      if (t1 - t0 < 2) { warnings.push(`beat ${bb.id}: photo card "${c.label || c.asset}" has under 2 s on screen and is dropped`); return; }
      cards.push({ id: `${bb.id}.${k + 1}`, beat: bb.id, asset: c.asset, label: c.label, kind: c.kind, lon: c.lon, lat: c.lat, anchor: c.anchor, t0: +t0.toFixed(2), t1: +t1.toFixed(2) });
    });
  });
  // a card with no anchor takes the first of the two free sides that no other card uses at the same time
  cards.sort((a, b) => a.t0 - b.t0);
  for (const c of cards) if (!c.anchor) { const used = cards.filter((o) => o !== c && o.anchor && o.t0 < c.t1 && o.t1 > c.t0).map((o) => o.anchor); c.anchor = ['mr', 'ml'].find((a) => !used.includes(a)) || 'mr'; }
  // a globe ending carries the credits panel and the end card
  const last = beats[beats.length - 1];
  const credits = last && last.rung === 'globe' && spec.credits !== false
    ? { t0: last.travelT1, t1: end, lines: [...(spec.credits_lines || []), ...DEFAULT_CREDITS], endcard: spec.endcard || '' } : null;
  return { duration: +end.toFixed(3), narration: said, camera, shots, beats, dates, chapters, captions, territory: terr, title, lights, effects, museum, cards, credits, warnings, notes };
}

// ---- queries used by the page (and the tests) ----

export function at(list, t) { let v = null; for (const x of list) { if (x.t <= t) v = x; else break; } return v; }

/** Caption lines on screen at t: up to two, newest last; the log clears inside a long silence. */
export function captionsAt(captions, t) {
  const started = captions.filter((c) => c.t0 <= t);
  if (!started.length) return [];
  const last = started[started.length - 1], next = captions[started.length];
  const silence = next ? next.t0 - last.t1 : Infinity;
  if (t > last.t1 + CAPTION_LINGER && silence > CAPTION_CLEAR_GAP) return [];
  return started.slice(-2).map((c, i, a) => ({ ...c, old: i < a.length - 1 }));
}
