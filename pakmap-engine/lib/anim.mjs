// Pure timing curves for the overlay layers (no canvas, no DOM): everything
// returns numbers so the tests can assert on them.
import { TIMING } from './style.mjs';

export const clamp01 = (v) => Math.max(0, Math.min(1, v));
export const easeOut = (t) => 1 - Math.pow(1 - t, 3);
export const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** 0..1 visibility of a layer that lives from tIn to tOut with a fade at each end. */
export function lifeAlpha(t, tIn, tOut, fadeIn = TIMING.chipIn, fadeOut = TIMING.chipOut) {
  if (t < tIn || t >= tOut) return 0;
  const a = fadeIn > 0 ? clamp01((t - tIn) / fadeIn) : 1;
  const b = fadeOut > 0 ? clamp01((tOut - t) / fadeOut) : 1;
  return Math.min(easeOut(a), b);
}

/** How many words of an n-word text are showing (word-by-word reveal). */
export function wordsVisible(t, t0, n, perWord = TIMING.wordSeconds) {
  if (t < t0) return 0;
  return Math.min(n, Math.floor((t - t0) / perWord + 1e-9) + 1);
}

/** Head-first draw progress 0..1: starts immediately, decelerates (ease-out only). */
export function lineProgress(t, t0, dur = TIMING.lineDraw) {
  return easeOut(clamp01((t - t0) / dur));
}

/** Title chip pop: scale/alpha in a couple of frames. */
export function popAt(t, t0, dur = TIMING.titlePop) {
  const k = clamp01((t - t0) / dur);
  return { alpha: k, scale: 0.92 + 0.08 * easeOut(k) };
}

/** Deterministic PRNG (mulberry32) so dot order never changes between renders. */
export function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Fixed reveal order for n points (a seeded shuffle). */
export function revealOrder(n, seed = 1) {
  const r = rng(seed), idx = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
  return idx;
}

/** Dot-density reveal: linear over `dur` seconds (measured on Reference 2). Returns how many dots show. */
export function dotsShown(t, t0, n, dur = TIMING.dotsReveal) {
  return Math.floor(n * clamp01((t - t0) / dur) + 1e-9);
}

/** Small clusters: each point pops `stagger` seconds after the previous one. */
export function clusterShown(t, t0, n, stagger = TIMING.pointStagger) {
  return t < t0 ? 0 : Math.min(n, Math.floor((t - t0) / stagger + 1e-9) + 1);
}

/**
 * PiP card entry (Reference 1, measured at 15 fps): about 115% size and 40% opacity for the first
 * frame, settling to 100% in 0.15-0.20 s, arriving from slightly up and to the right; the white
 * border appears during the settle. Exit is a plain fade (no shrink, no slide).
 */
export function cardState(t, tIn, tOut, inDur = TIMING.cardIn, outDur = TIMING.cardOut) {
  if (t < tIn || t >= tOut) return { alpha: 0, scale: 1, dx: 0, dy: 0, border: 0 };
  const k = easeOut(clamp01((t - tIn) / inDur)), out = clamp01((tOut - t) / outDur);
  return { alpha: (0.4 + 0.6 * k) * out, scale: 1.15 - 0.15 * k, dx: (1 - k) * 12, dy: (k - 1) * 9, border: k };
}

/** Which frame of a clip to show at time t: loops when `loop`, otherwise holds the last frame. */
export function clipFrame(t, tIn, fps, count, loop = false) {
  if (count <= 0) return 0;
  const n = Math.max(0, Math.floor((t - tIn) * fps + 1e-9));
  return loop ? n % count : Math.min(n, count - 1);
}

/** Crossfade between images inside one card: every `every` seconds the next image fades in over `fade` s. */
export function crossfadeAt(t, tIn, count, every, fade = TIMING.cardCrossfade) {
  if (count <= 1) return { from: 0, to: 0, mix: 0 };
  const since = Math.max(0, t - tIn), slot = Math.floor(since / every) % count, into = since - Math.floor(since / every) * every;
  const mix = into < fade && since >= every ? easeInOut(clamp01(into / fade)) : 0;
  const prev = (slot - 1 + count) % count;
  return mix > 0 ? { from: prev, to: slot, mix } : { from: slot, to: slot, mix: 0 };
}
