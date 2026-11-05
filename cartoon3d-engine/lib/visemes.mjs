// Lip-sync for the 3D host: Edge word timings + voice loudness -> per-frame Meta viseme weights.
// Tuned and accepted at host Gate 5 (authoring/host/stage5_clip.mjs): spelling rules + a word list, loudness gating,
// 40 ms visual lead, smooth bumps, 25 ms attack / 60 ms release, total articulation capped at 1.3.

const RULES = [[/^th/, 'TH'], [/^(sh|ch|tch)/, 'CH'], [/^ck/, 'kk'], [/^ng/, 'nn'], [/^(ee|ea|ie)/, 'E'], [/^(oo|ue|ew)/, 'U'], [/^ou$/, 'U'], [/^(ou|ow)/, 'aa'], [/^y(?=[aeiou])/, null],
  [/^c(?=[eiy])/, 'SS'], [/^c/, 'kk'], [/^(ai|ay|ei)/, 'E'], [/^a/, 'aa'], [/^e/, 'E'], [/^[iy]/, 'I'], [/^o/, 'O'], [/^u/, 'U'], [/^[bpm]/, 'PP'], [/^[fv]/, 'FF'], [/^[szc]/, 'SS'],
  [/^x/, 'kk'], [/^[tdl]/, 'DD'], [/^n/, 'nn'], [/^[kgq]/, 'kk'], [/^r/, 'RR'], [/^w/, 'U'], [/^j/, 'CH'], [/^[h']/, null]];
// Common preschool words that spelling gets wrong.
const DICT = { the: 'DD aa', a: 'aa', to: 'DD U', do: 'DD U', you: 'U', your: 'U RR', one: 'U aa nn', two: 'DD U', said: 'SS E DD', says: 'SS E SS', what: 'U aa DD', where: 'U E RR',
  are: 'aa RR', is: 'I SS', was: 'U aa SS', friend: 'FF RR E nn DD', friends: 'FF RR E nn DD SS', hello: 'E DD O', hi: 'aa I', great: 'kk RR E DD', good: 'kk U DD', look: 'DD U kk',
  "let's": 'DD E DD SS', some: 'SS aa PP', something: 'SS aa PP TH I nn', come: 'kk aa PP', love: 'DD aa FF', all: 'O DD', ball: 'PP O DD', now: 'nn aa U', know: 'nn O', eye: 'aa I', eyes: 'aa I SS',
  find: 'FF aa I nn DD', night: 'nn aa I DD', light: 'DD aa I DD', right: 'RR aa I DD', blue: 'PP DD U', who: 'U', why: 'U aa I', my: 'PP aa I', by: 'PP aa I', bye: 'PP aa I', yes: 'I E SS',
  yellow: 'I E DD O', red: 'RR E DD', green: 'kk RR I nn', orange: 'O RR I nn CH', purple: 'PP RR PP DD', pink: 'PP I nn kk', white: 'U aa I DD', black: 'PP DD aa kk', brown: 'PP RR aa nn',
  cat: 'kk aa DD', dog: 'DD O kk', cow: 'kk aa U', pig: 'PP I kk', sheep: 'CH I PP', frog: 'FF RR O kk', duck: 'DD aa kk', car: 'kk aa RR', up: 'aa PP', down: 'DD aa nn', big: 'PP I kk', small: 'SS PP O DD',
  three: 'TH RR I', four: 'FF O RR', five: 'FF aa I FF', six: 'SS I kk SS', seven: 'SS E FF E nn', eight: 'E DD', nine: 'nn aa I nn', ten: 'DD E nn', again: 'aa kk E nn', turn: 'DD E RR nn' };
const VOW = new Set(['aa', 'E', 'I', 'O', 'U']);
export const VISEMES = ['aa', 'E', 'I', 'O', 'U', 'PP', 'FF', 'TH', 'DD', 'kk', 'CH', 'SS', 'nn', 'RR'];

export function wordVisemes(word) {
  const key = String(word).toLowerCase().replace(/[^a-z']/g, ''); if (DICT[key]) return DICT[key].split(' ');
  let w = key; if (w.length > 2 && w.endsWith('e') && !/[aeiou]e$/.test(w)) w = w.slice(0, -1);
  const out = [];
  while (w.length) {
    const r = RULES.find(([re]) => re.test(w)); if (!r) { w = w.slice(1); continue; }
    w = w.slice(w.match(r[0])[0].length);
    if (r[1] && !(out.length && (out.at(-1) === r[1] || (VOW.has(r[1]) && VOW.has(out.at(-1)))))) out.push(r[1]);
  }
  return out;
}

const sstep = (e0, e1, x) => { const u = Math.min(1, Math.max(0, (x - e0) / (e1 - e0))); return u * u * (3 - 2 * u); };
const bump = (x, c, h) => (Math.abs(x - c) < h ? 0.5 * (1 + Math.cos(Math.PI * (x - c) / h)) : 0);

/**
 * words: [{text, t0, t1}] in seconds on the video timeline. envelope: loudness 0..1 per frame at envFps.
 * Returns { fps, names, frames } where frames[i] is an array of weights (0..100 integers) for `names` at frame i.
 */
export function visemeTrack(words, envelope, envFps, duration, fps = 30, { lead = 0.04, hz = 120 } = {}) {
  const items = [];
  for (const wd of words) {
    const v = wordVisemes(wd.text), wt = v.map((x) => (VOW.has(x) ? 2 : 1)), tot = wt.reduce((a, b) => a + b, 0) || 1; let t = wd.t0;
    v.forEach((x, i) => { const d = (wd.t1 - wd.t0) * wt[i] / tot; items.push({ v: x, c: t + d / 2, hw: (d * 0.6 + 0.04) * 1.15, peak: x === 'PP' ? 1 : VOW.has(x) ? 1.15 : 0.85 }); t += d; });
  }
  const loud = (t) => { if (!envelope || !envelope.length) return 1; const k = t * envFps, i = Math.floor(k), f = k - i; return i < 0 || i >= envelope.length - 1 ? 0 : envelope[i] * (1 - f) + envelope[i + 1] * f; };
  const names = VISEMES.filter((n) => items.some((it) => it.v === n)), y = Object.fromEntries(names.map((n) => [n, 0]));
  const N = Math.ceil(duration * hz), step = hz / fps, frames = []; let start = 0;
  items.sort((a, b) => a.c - b.c);
  for (let i = 0; i < N; i++) {
    const tt = i / hz + lead, k = {};
    while (start < items.length && items[start].c + items[start].hw < tt) start++;
    for (let j = start; j < items.length && items[j].c - items[j].hw <= tt; j++) { const it = items[j], a = it.peak * bump(tt, it.c, it.hw); if (a > (k[it.v] || 0)) k[it.v] = a; }
    const L = loud(tt), g = sstep(0.02, 0.2, L) * (0.6 + 0.55 * L);            // open with the real voice, shut in the gaps
    for (const n in k) if (n !== 'PP') k[n] *= g;
    const sum = Object.values(k).reduce((a, b) => a + b, 0); if (sum > 1.3) for (const n in k) k[n] *= 1.3 / sum;
    for (const n of names) { const x = k[n] || 0, a = 1 - Math.exp(-1 / (hz * (x > y[n] ? 0.025 : 0.06))); y[n] += (x - y[n]) * a; }
    if (i % step < 1) frames.push(names.map((n) => Math.round(y[n] * 100)));
  }
  return { fps, names, frames };
}
