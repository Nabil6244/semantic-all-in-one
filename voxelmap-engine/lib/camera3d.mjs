// The 3D camera: a list of segments (fly, orbit, hold) evaluated at any time t, plus an always-on drift. Independent of
// pakMap's 2D camera. State: { lon, lat, alt (km above ground), heading (deg, 0 = looking north), tilt (deg from straight
// down, null = follows altitude) }. Pure and deterministic: the same path and t always give the same camera.

import { distanceKm } from './geo.mjs';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const ease = (k) => { k = clamp(k, 0, 1); return k * k * k * (k * (6 * k - 15) + 10); };
const lerp = (a, b, k) => a + (b - a) * k;
const angLerp = (a, b, k) => { let d = ((b - a + 540) % 360) - 180; return a + d * k; };

/** Tilt from straight down that suits an altitude: top-down for maps, oblique near the ground. */
export function autoTilt(altKm) {
  const hi = 1200, lo = 6;
  if (altKm >= hi) return 0;
  if (altKm <= lo) return 58;
  const k = (Math.log(hi) - Math.log(altKm)) / (Math.log(hi) - Math.log(lo));
  return 58 * ease(k);
}

/** Seconds a move needs: longer for distance and for a big change of altitude. */
export function travelSeconds(from, to) {
  // the climb counts both ways: a hop between two ground sets rises to the arc's peak and comes back down
  const d = distanceKm(from, to), peak = Math.max(from.alt, to.alt, d * 0.85);
  const za = Math.log2(peak / from.alt) + Math.log2(peak / to.alt);
  return clamp(1.6 + 0.7 * Math.log2(1 + d / 80) + 0.3 * za, 2, 12);
}

/** Altitude (km) along a fly-to at eased progress e: log space, with an arc that rises for long hops. */
function flyAlt(a, b, d, e) {
  const la = Math.log(a.alt), lb = Math.log(b.alt), top = Math.max(la, lb);
  const peak = Math.log(Math.max(a.alt, b.alt, d * 0.85));
  return Math.exp(lerp(la, lb, e) + (peak > top ? (peak - top) * Math.sin(Math.PI * e) : 0));
}

/** A fly-to between two states. Ground speed is proportional to altitude (the screen moves at a steady rate): the ground
 *  point creeps while the camera is low and crosses the map while it is high, so leaving a ground set never jerks. */
export function flyAt(a, b, k) {
  const e = ease(k);
  const d = distanceKm(a, b);
  const N = 48;
  let total = 0, upTo = 0;
  for (let i = 0; i < N; i++) {
    const s0 = i / N, s1 = (i + 1) / N, seg = (flyAlt(a, b, d, s0) + flyAlt(a, b, d, s1)) / 2;
    total += seg;
    if (s1 <= e) upTo += seg; else if (s0 < e) upTo += seg * (e - s0) * N;
  }
  const pe = total > 0 ? upTo / total : e;
  return {
    lon: lerp(a.lon, b.lon, pe), lat: lerp(a.lat, b.lat, pe), alt: flyAlt(a, b, d, e),
    heading: angLerp(a.heading ?? 0, b.heading ?? 0, e),
    tilt: a.tilt == null && b.tilt == null ? null : lerp(a.tilt ?? autoTilt(a.alt), b.tilt ?? autoTilt(b.alt), e),
  };
}

/** A held shot's own motion (push, pullback, track, flyover): no arc; altitude in log space. 'linear' keeps a steady
 *  speed with short soft ends so it joins the moves before and after it without a jolt. */
export function moveAt(a, b, k, kind = 'inout') {
  const e = kind === 'linear' ? softLinear(k) : ease(k);
  return {
    lon: lerp(a.lon, b.lon, e), lat: lerp(a.lat, b.lat, e), alt: Math.exp(lerp(Math.log(a.alt), Math.log(b.alt), e)),
    heading: angLerp(a.heading ?? 0, b.heading ?? 0, e),
    tilt: a.tilt == null && b.tilt == null ? null : lerp(a.tilt ?? autoTilt(a.alt), b.tilt ?? autoTilt(b.alt), e),
  };
}
/** Linear in the middle, eased over the first and last 12%: continuous speed into and out of the segment. */
export function softLinear(k, r = 0.12) {
  k = clamp(k, 0, 1);
  const v = 1 / (1 - r); // top speed so the curve still ends at 1
  if (k < r) return (v * k * k) / (2 * r);
  if (k > 1 - r) return 1 - (v * (1 - k) * (1 - k)) / (2 * r);
  return v * (k - r / 2);
}

/** Evaluate a path [{type, t0, t1, from, to, deg}] at t. Before the first / after the last segment the camera holds. */
export function cameraAt(path, t) {
  if (!path.length) return { lon: 0, lat: 0, alt: 1000, heading: 0, tilt: null };
  let seg = path[0];
  for (const s of path) { if (s.t0 <= t) seg = s; else break; }
  const k = seg.t1 > seg.t0 ? clamp((t - seg.t0) / (seg.t1 - seg.t0), 0, 1) : 1;
  let c;
  if (seg.type === 'fly') c = flyAt(seg.from, seg.to, k);
  else if (seg.type === 'orbit') c = { ...seg.from, heading: (seg.from.heading ?? 0) + (seg.deg ?? 20) * k };
  else if (seg.type === 'move') c = moveAt(seg.from, seg.to, k, seg.ease);
  else c = { ...seg.from };
  return withDrift(c, t);
}

/** Never a frozen frame: a slow sway of heading and position, scaled to altitude, the same at the same t. */
export function withDrift(c, t) {
  const s = Math.sin(t * 0.21) * 0.6 + Math.sin(t * 0.083 + 1.3) * 0.4;
  const off = c.alt * 0.0009; // degrees of lon/lat per km of altitude
  return { ...c, heading: (c.heading ?? 0) + s * 1.6, lon: c.lon + Math.sin(t * 0.13) * off, lat: c.lat + Math.cos(t * 0.11) * off * 0.7 };
}

/** Camera state -> three.js placement in world units (cells). groundY(x,z) gives the block top under a point. */
export function placeCamera(c, geo, groundY, vfovDeg = 40) {
  const tw = geo.toWorld(c.lon, c.lat);
  const gy = groundY(tw.x, tw.z);
  const D = Math.max(0.004, c.alt / geo.kmPerCell); // down to ~10 m: ground shots fly low over human-scale dioramas
  const tilt = (c.tilt ?? autoTilt(c.alt)) * Math.PI / 180, hd = (c.heading ?? 0) * Math.PI / 180;
  const pos = { x: tw.x - Math.sin(hd) * Math.sin(tilt) * D, y: gy + Math.cos(tilt) * D, z: tw.z + Math.cos(hd) * Math.sin(tilt) * D };
  // straight down needs an "up" that points north on screen
  const up = { x: Math.sin(hd), y: Math.cos(tilt) < 0.999 ? 1 : 0, z: -Math.cos(hd) };
  return { pos, target: { x: tw.x, y: gy, z: tw.z }, up, near: Math.max(0.0002, D * 0.02), far: D * 8 + 400, fov: vfovDeg, distance: D };
}
