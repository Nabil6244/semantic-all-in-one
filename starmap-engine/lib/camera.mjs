// The space camera: shots, and moves between them. Pure: the same t always gives the same camera.
//
// A shot: { target, distance | fill, az_deg, el_deg, light, orbit_deg_per_s }
//   target   "moon", "moon@23.47,0.67" (a surface point), "earth+moon" (a midpoint)
//   distance {"km": 900} / {"au": 5} / {"ly": 1e5}, or fill: 0.5 = the body spans half the frame height
//   az/el    the viewing direction: from the ground for a surface target (el = degrees above the local horizon), else in
//            space; with "light": "front" | "side" | "back" | "rim" the direction is measured from the Sun instead, so
//            a shot never lands on a body's night side by accident
//   orbit_deg_per_s  the camera circles the target while the shot holds
// A move: { t, dur, to: shot } glides there (dur 0 = a cut). Distance changes in log space (a steady feel across any
// number of orders of magnitude) and the look-at point only moves as far as keeps the subject being left in frame -- the
// motion the AstroMap demo clips proved out. Bodies move and turn with the universe clock, so every shot is re-resolved
// for the frame's own date (world.setTime is called by the caller first).
//
// Output positions are km from the ANCHOR body's centre (the body the camera is looking at), never from the root.
import { toKm } from './units.mjs';
import { anchorTarget, surfaceFrame } from './world.mjs';

const RAD = Math.PI / 180;
export const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * k * (k * (6 * k - 15) + 10); };   // smootherstep
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((x) => x / l); };
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const LIGHT_AZ = { front: 25, side: 75, back: 165, rim: 150 };

function slerp(a, b, k) {
  const th = Math.acos(Math.max(-1, Math.min(1, dot(a, b))));
  if (th < 1e-6) return a.slice();
  const s = Math.sin(th), wa = Math.sin((1 - k) * th) / s, wb = Math.sin(k * th) / s;
  return [a[0] * wa + b[0] * wb, a[1] * wa + b[1] * wb, a[2] * wa + b[2] * wb];
}
const rotateAbout = (v, axis, deg) => {   // Rodrigues
  const a = deg * RAD, c = Math.cos(a), s = Math.sin(a), k = norm(axis), d = dot(k, v), x = cross(k, v);
  return v.map((vi, i) => vi * c + x[i] * s + k[i] * d * (1 - c));
};
/** A direction from az/el in a frame whose vertical is `up` and whose reference horizontal is `ref`. */
function dirIn(up, ref, az, el) {
  const north = norm(ref.map((c, i) => c - up[i] * dot(ref, up)));
  const east = cross(north, up);
  const a = az * RAD, e = el * RAD;
  return norm(up.map((u, i) => u * Math.sin(e) + (north[i] * Math.cos(a) + east[i] * Math.sin(a)) * Math.cos(e)));
}

function shotState(world, shot, tanHalf, sunId) {
  const at = anchorTarget(world, shot.target);
  const body = world.get(at.anchor);
  const dist = shot.fill ? (body.radiusKm / tanHalf) / shot.fill : toKm(shot.distance);
  const sf = surfaceFrame(world, shot.target);
  const up = sf ? sf.normal : [0, 1, 0];
  let dir;
  if (shot.light && sunId && sunId !== at.anchor) {
    // measured from the Sun: az 0 = the camera between the Sun and the target, so "front" sees the lit face
    const toSun = norm(world.vec(at.anchor, sunId).map((c, i) => c - at.local[i]));
    const az = (LIGHT_AZ[shot.light] ?? 25) + (shot.az_deg || 0);
    dir = dirIn(up, toSun, az, shot.el_deg ?? 15);
  } else if (sf) {
    const ref = Math.abs(dot(up, [0, 1, 0])) > 0.99 ? [1, 0, 0] : [0, 1, 0];   // local north (towards the pole)
    dir = dirIn(up, ref, shot.az_deg || 0, shot.el_deg || 0);
  } else {
    // in the target's own frame: el = degrees above ITS equator or plane (a galaxy's disk, a planet's equator), and the
    // camera's up is its north, so "55 degrees above the Milky Way" means above the galactic plane
    const B = world.orientation(at.anchor);
    return { ...at, dist, dir: dirIn(B.y, B.z, shot.az_deg || 0, shot.el_deg || 0), up: B.y, orbit: shot.orbit_deg_per_s || 0 };
  }
  return { ...at, dist, dir, up, orbit: shot.orbit_deg_per_s || 0 };
}

function lookWeight(gap, from, to, d, k, tanHalf) {
  if (gap <= 0) return k;
  const f = (dist) => smooth(Math.min(1, (0.7 * tanHalf * dist) / gap));   // how much of the gap fits in view
  const f0 = f(from.dist), f1 = f(to.dist);
  if (Math.abs(f1 - f0) < 1e-6) return k;
  return Math.min(1, Math.max(0, (f(d) - f0) / (f1 - f0)));
}

/** spec.camera = { start: shot, moves: [{ t, dur, to: shot }] } -> camera(t) = { anchor, position, target, up, distance }. */
export function createCamera(world, cam) {
  const tanHalf = Math.tan(((cam.fov_deg || 40) / 2) * RAD);
  const sunId = cam.sun || [...world.nodes.values()].find((n) => n.kind === 'star')?.id;
  const sorted = (cam.moves || []).slice().sort((a, b) => a.t - b.t);
  const shots = [cam.start, ...sorted.map((m) => m.to)];
  const moves = sorted.map((m, i) => ({ t0: m.t, t1: m.t + (m.dur ?? 4), i }));
  const drift = cam.drift_deg_per_s || 0;
  return function at(t) {
    let idx = 0, move = null, held = 0;
    for (const m of moves) {
      if (t >= m.t1) { idx = m.i + 1; held = m.t1; continue; }
      if (t > m.t0) move = m;
      break;
    }
    let s;
    if (!move) {
      const st = shotState(world, shots[idx], tanHalf, sunId);
      s = { ...st, target: st.local };
      if (st.orbit) s.dir = rotateAbout(st.dir, st.up, st.orbit * (t - held));
    } else {
      const from = shotState(world, shots[move.i], tanHalf, sunId), to = shotState(world, shots[move.i + 1], tanHalf, sunId);
      const between = world.vec(from.anchor, to.anchor);
      const gapVec = [0, 1, 2].map((j) => between[j] + to.local[j] - from.local[j]);
      const k = move.t1 > move.t0 ? smooth((t - move.t0) / (move.t1 - move.t0)) : 1;
      const d = Math.exp(Math.log(from.dist) + (Math.log(to.dist) - Math.log(from.dist)) * k);
      const w = lookWeight(Math.hypot(...gapVec), from, to, d, k, tanHalf);
      // anchored to whichever target the look-at point is nearer: the numbers stay small where the viewer looks
      const target = w < 0.5 ? from.local.map((v, j) => v + gapVec[j] * w) : to.local.map((v, j) => v - gapVec[j] * (1 - w));
      s = { anchor: w < 0.5 ? from.anchor : to.anchor, target, dist: d, dir: norm(slerp(from.dir, to.dir, k)), up: norm(slerp(from.up, to.up, k)) };
    }
    let dir = s.dir;
    if (drift) dir = rotateAbout(dir, s.up, drift * t);      // a slow always-on drift keeps a held shot alive
    const position = s.target.map((v, i) => v + dir[i] * s.dist);
    return { anchor: s.anchor, position, target: s.target, up: s.up, distance: s.dist };
  };
}
