// Deterministic randomness. Every look, layout and particle comes from a seed, so the same story renders the same frames
// (and a frame can be rendered out of order: nothing depends on the frames before it).

/** 32-bit string hash (FNV-1a). */
export function hash(str) {
  let h = 0x811c9dc5;
  const s = String(str);
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}

/** mulberry32: a small fast PRNG. rng() -> [0,1). */
export function makeRng(seed) {
  let a = (typeof seed === 'number' ? seed : hash(seed)) >>> 0;
  const rng = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  rng.range = (lo, hi) => lo + (hi - lo) * rng();
  rng.int = (lo, hi) => Math.floor(lo + (hi - lo + 1) * rng());
  rng.pick = (arr) => arr[Math.floor(rng() * arr.length)];
  rng.chance = (p) => rng() < p;
  return rng;
}

/** Stateless hash noise in [0,1) for integer lattice points (used by particles: f(seed, i, k)). */
export function h01(a, b = 0, c = 0) {
  let h = Math.imul(a | 0, 0x27d4eb2d) ^ Math.imul(b | 0, 0x165667b1) ^ Math.imul(c | 0, 0x9e3779b1);
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** Smooth 2D value noise in [-1,1], seeded. */
export function valueNoise2(seed) {
  const s = hash(seed) | 0;
  const g = (x, z) => h01(x, z, s) * 2 - 1;
  const f = (t) => t * t * (3 - 2 * t);
  return (x, z) => {
    const xi = Math.floor(x), zi = Math.floor(z), xf = f(x - xi), zf = f(z - zi);
    const a = g(xi, zi), b = g(xi + 1, zi), c = g(xi, zi + 1), d = g(xi + 1, zi + 1);
    return a + (b - a) * xf + (c - a) * zf + (a - b - c + d) * xf * zf;
  };
}

/** Fractal noise: octaves of value noise. */
export function fbm2(seed, octaves = 4) {
  const ns = Array.from({ length: octaves }, (_, i) => valueNoise2(`${seed}:${i}`));
  return (x, z) => { let v = 0, amp = 0.5, fr = 1; for (const n of ns) { v += amp * n(x * fr, z * fr); amp *= 0.5; fr *= 2.03; } return v; };
}

export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export const smooth = (t) => { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); };
export const smoother = (t) => { t = clamp(t, 0, 1); return t * t * t * (t * (t * 6 - 15) + 10); };
export const easeInOut = (t) => { t = clamp(t, 0, 1); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
