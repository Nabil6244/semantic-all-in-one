// AGENT KIT helpers for scene pages:  import * as K from '/agent_kit/lib/kit.js';
// Everything is a pure function of t, so any frame can be drawn in any order.

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;
/** 0..1 progress of t through [start, start + dur], eased. */
export const prog = (t, start, dur, ease = easeOutCubic) => ease(clamp((t - start) / Math.max(1e-6, dur)));

export const linear = (k) => k;
export const easeOutCubic = (k) => 1 - (1 - k) ** 3;
export const easeInOutCubic = (k) => (k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2);
export const easeOutExpo = (k) => (k >= 1 ? 1 : 1 - 2 ** (-10 * k));
export const easeOutBack = (k, s = 1.70158) => 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2;
export const easeInOutSine = (k) => -(Math.cos(Math.PI * k) - 1) / 2;

/** Fade in at `start`, fade out ending at `end` (seconds); 0..1. */
export const life = (t, start, end, fadeIn = 0.4, fadeOut = 0.4) =>
  Math.min(easeOutCubic(clamp((t - start) / fadeIn)), easeInOutSine(clamp((end - t) / fadeOut)));

/** Seeded random numbers: const r = rand(7); r() -> 0..1, the same every run. */
export function rand(seed = 1) {
  let s = seed >>> 0 || 1;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

/** The first n characters of text at time t (typing at cps characters a second from start). */
export const typed = (text, t, start, cps = 30) => text.slice(0, Math.max(0, Math.floor((t - start) * cps)));

/** A number counting from a to b between start and start + dur, formatted with thousands separators. */
export function countUp(t, start, dur, a, b, decimals = 0) {
  const v = lerp(a, b, prog(t, start, dur, easeOutExpo));
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Slow camera push: a CSS transform string for a Ken Burns move over the scene duration. */
export function kenBurns(t, dur, { from = 1.0, to = 1.08, dx = 0, dy = 0 } = {}) {
  const k = easeInOutSine(clamp(t / dur));
  return `scale(${lerp(from, to, k)}) translate(${lerp(0, dx, k)}px, ${lerp(0, dy, k)}px)`;
}

/** Stroke draw-on for an SVG path element: set its dash so it is drawn from 0 to k (0..1). */
export function drawOn(el, k) {
  const L = el.__len || (el.__len = el.getTotalLength());
  el.style.strokeDasharray = `${L}`;
  el.style.strokeDashoffset = `${L * (1 - clamp(k))}`;
}

/** Wait for every <img> on the page (use in window.sceneReady). */
export const imagesReady = () => Promise.all([...document.images].map((im) => (im.complete ? 0 : new Promise((r) => { im.onload = im.onerror = r; }))));

/** A file on disk as a URL the scene server can serve:  K.file('/Users/me/clip/photo.jpg') */
export const file = (abs) => '/@fs' + abs;

// ---- Hook moves: small, sharp events that keep eyes on the screen ------------------------------------------------
// Each returns a value for time t; `at` is when the event happens (scene seconds). Use 2-4 per scene, on the key words.

/** Punch-in: a quick zoom bump at `at` that settles back (1 -> 1+amt -> 1). Put on a reveal or a key word. */
export const punch = (t, at, amt = 0.06, dur = 0.45) => {
  const k = (t - at) / dur;
  return k < 0 || k > 1 ? 1 : 1 + amt * Math.sin(Math.PI * k) * (1 - k * 0.3);
};

/** Camera shake [dx, dy] in px, decaying after `at` (impacts, "frightening", "collapse"). Seeded, so frames repeat. */
export function shake(t, at, amp = 14, dur = 0.5, seed = 3) {
  const k = (t - at) / dur;
  if (k < 0 || k > 1) return [0, 0];
  const f = Math.floor((t - at) * 30), r = rand(seed * 1000 + f), d = amp * (1 - k) ** 2;
  return [(r() * 2 - 1) * d, (r() * 2 - 1) * d];
}

/** White flash opacity at `at` (0..1); use on a hard reveal or a cut inside a scene. */
export const flash = (t, at, dur = 0.25) => { const k = (t - at) / dur; return k < 0 || k > 1 ? 0 : (1 - k) ** 2; };

/** Slam: an element lands from big to its size with a tiny overshoot. Returns a CSS transform. */
export const slam = (t, at, from = 2.2, dur = 0.35) => {
  const k = clamp((t - at) / dur);
  const s = k >= 1 ? 1 : lerp(from, 1, easeOutExpo(k)) + Math.sin(k * Math.PI) * 0.04;
  return `scale(${s})`;
};

/** Wipe reveal as a CSS clip-path, from a side: 'left' | 'right' | 'up' | 'down' | 'circle'. */
export function wipe(t, at, dur = 0.5, from = 'left') {
  const k = easeInOutCubic(clamp((t - at) / dur)) * 100, r = 100 - k;
  return { left: `inset(0 ${r}% 0 0)`, right: `inset(0 0 0 ${r}%)`, up: `inset(${r}% 0 0 0)`, down: `inset(0 0 ${r}% 0)`,
    circle: `circle(${k * 0.75}% at 50% 50%)` }[from];
}

/** Marker highlight behind a word: width 0..100% (put it on a span's ::before or a sibling bar). */
export const highlight = (t, at, dur = 0.35) => easeOutCubic(clamp((t - at) / dur)) * 100;

/** Slow camera drift for a whole scene, so nothing is ever still: a CSS transform. */
export const drift = (t, dur, { zoom = 0.05, x = -20, y = -8 } = {}) => {
  const k = easeInOutSine(clamp(t / dur));
  return `scale(${1 + zoom * k}) translate(${x * k}px, ${y * k}px)`;
};

/** Parallax: offset in px for a layer at `depth` (0 = far, 1 = near) during a drift. */
export const parallax = (t, dur, depth, px = 60) => -px * depth * easeInOutSine(clamp(t / dur));

/** Stagger: the start time of item i in a list that starts at `at`. */
export const stagger = (at, i, gap = 0.1) => at + i * gap;

// ---- Word times: scene() injects window.WORDS = [{w, s, e}] with times relative to the scene start ----------------

/** The scene time when `word` (first match, case-insensitive, punctuation ignored) is spoken, or `fallback`. */
export function when(word, fallback = 0, nth = 0) {
  const clean = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
  const want = clean(word), hits = (window.WORDS || []).filter((w) => clean(w.w) === want || clean(w.w).startsWith(want));
  return hits[nth] ? hits[nth].s : fallback;
}

/** Karaoke-style caption: the words spoken so far in this scene (pass max words shown). */
export const spokenSoFar = (t, max = 12) => (window.WORDS || []).filter((w) => w.s <= t).slice(-max).map((w) => w.w).join(' ');

/** Map projection from the `map` tool's <name>.json: [x, y] in px for a longitude/latitude. */
export function lonlat(proj, lon, lat) {
  const r = Math.PI / 180, y = Math.log(Math.tan(Math.PI / 4 + Math.max(-85, Math.min(85, lat)) * r / 2));
  return [(lon * r - proj.x0) * proj.scale + proj.ox, (proj.y1 - y) * proj.scale + proj.oy];
}

/** Inline an SVG file into an element (so its paths can be styled and animated):  await K.inlineSvg(el, '/@scene/med.svg') */
export async function inlineSvg(el, url) { el.innerHTML = await (await fetch(url)).text(); return el.querySelector('svg'); }
