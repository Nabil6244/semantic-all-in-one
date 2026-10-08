// The space camera: shots, and moves between them. Pure: the same t always gives the same camera.
//
// A shot: { target, distance | fill, az_deg, el_deg, light, orbit_deg_per_s }
//   target   "moon", "moon@23.47,0.67" (a surface point), "earth+moon" (a midpoint)
//   distance {"km": 900} / {"au": 5} / {"ly": 1e5}, or fill: 0.5 = the body spans half the frame height, or for a pair
//            ("earth+moon") fit: 1.6 = the pair spans 1/1.6 of the frame
//   az/el    the viewing direction: from the ground for a surface target (el = degrees above the local horizon), else in
//            space; with "light": "front" | "side" | "back" | "rim" the direction is measured from the Sun instead, so
//            a shot never lands on a body's night side by accident
//   orbit_deg_per_s  the camera circles the target while the shot holds
//   follow   { trajectory: id, motion?: {...} } instead of a target: the camera looks at a craft on its trajectory (where it
//            is at the frame's universe date, or along its motion); distance in km. Any trajectory, any body: a launch, a
//            landing, a flyby are the same follow shot (resolved from data by the compiler's visual actions)
//   face     { trajectory: id, utc }: look at the target from the side where that craft is at utc (its path in front)
//   keep     { trajectory: id, motion?, within: 0.5 }: the shot holds still and only turns when that craft nears the edge of
//            the frame (within: the share of the half field of view it may drift before the camera turns); not mid-glide
//   path     { trajectory: id, from_utc, to_utc, ref_utc, fit: 1.3, up: "radial" | "plane", side: 1 | -1, min_km }:
//            instead of a target, the stretch of a craft's path between two moments, framed whole and held: the camera
//            stands to the side of the stretch (el_deg above it, on the sunlit side unless side is given) so the craft
//            visibly CROSSES the frame while the camera stays still -- the action's own frame, worked out from the data
//            for any craft, any body
// spec.camera.still: [[t0, t1], ...] narration windows where the always-on drift eases to a stop (something on screen is
// moving -- a craft, a path being drawn -- so the camera has no reason to)
// A move: { t, dur, to: shot } glides there (dur 0 = a cut). Distance changes in log space (a steady feel across any
// number of orders of magnitude) and the look-at point only moves as far as keeps the subject being left in frame -- the
// motion the AstroMap demo clips proved out. Bodies move and turn with the universe clock, so every shot is re-resolved
// for the frame's own date (world.setTime is called by the caller first).
//
// Output positions are km from the ANCHOR body's centre (the body the camera is looking at), never from the root.
import { toKm } from './units.mjs';
import { anchorTarget, surfaceFrame } from './world.mjs';
import { motionWhen } from './timing.mjs';

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

/** The stretch of a trajectory a path shot frames: its points (frame coordinates), the centre of their bounds and the main
 *  direction of travel across it. With ref_utc it is worked out once, as the path stands at that moment, so the frame
 *  holds still however the drawn path shifts while the clock runs (a coast whose far end rides with its target);
 *  without, for the world's current date. */
function pathStretch(world, traj, p, sunId, stretchMemo) {
  if (p.ref_utc == null || !stretchMemo) return stretchAt(traj, p);
  const key = `${traj.id}|${p.from_utc}|${p.to_utc}|${p.ref_utc}`;
  if (!stretchMemo.has(key)) {
    const was = world.date;
    world.setTime(new Date(p.ref_utc));
    try {
      const st = stretchAt(traj, p);
      // the Sun's side, fixed at that moment too: over a long stretch the Sun moves round, and the view must not flip
      if (sunId && sunId !== traj.frame) st.toSun = norm(world.vec(traj.frame, sunId).map((c, i) => c - st.centre[i]));
      stretchMemo.set(key, st);
    } finally { world.setTime(was); }
    if (stretchMemo.size > 256) stretchMemo.delete(stretchMemo.keys().next().value);
  }
  return stretchMemo.get(key);
}
function stretchAt(traj, p) {
  const a = Date.parse(p.from_utc), b = Date.parse(p.to_utc), n = 24, pts = [];
  for (let i = 0; i <= n; i++) pts.push(traj.at(a + (b - a) * (i / n)).position);
  const lo = [0, 1, 2].map((i) => Math.min(...pts.map((q) => q[i]))), hi = [0, 1, 2].map((i) => Math.max(...pts.map((q) => q[i])));
  const centre = lo.map((v, i) => (v + hi[i]) / 2);
  let chord = pts[n].map((v, i) => v - pts[0][i]);
  if (Math.hypot(...chord) < 1e-9 * (Math.hypot(...centre) + 1)) chord = pts[n >> 1].map((v, i) => v - pts[0][i]);   // a closed loop
  // the plane the stretch bends in (a flyby's swing, a transfer's arc), when it bends at all
  const sa = pts[n >> 1].map((v, i) => v - pts[0][i]), sb = pts[n].map((v, i) => v - pts[0][i]), pn = cross(sa, sb);
  const normal = Math.hypot(...pn) > 1e-3 * Math.hypot(...sa) * Math.hypot(...sb) ? norm(pn) : null;
  return { pts, centre, chord: norm(chord), normal };
}

/** Where to stand for a path shot: to the side of the stretch, raised el_deg towards the outward direction, far enough back
 *  that every point fits (aspect-aware) with fit to spare. */
function pathView(world, shot, at, st, tanHalf, aspect, sunId) {
  const B = world.orientation(at.anchor);
  // "up" for the view: away from the body (a launch, a landing: the sky above), or off the plane the stretch bends in
  // (a flyby, a transfer: seen from above its arc), on the north side
  const north = st.normal ? (dot(st.normal, B.y) < 0 ? st.normal.map((c) => -c) : st.normal) : B.y;
  let out = Math.hypot(...st.centre) > 0 ? norm(st.centre) : B.y;
  if (shot.path.up === 'plane' && st.normal) out = north;
  // a stretch heading straight out from the body (a departure) has "away from the body" along its own line: lean the
  // reference towards the plane it travels in instead -- smoothly, so the view never flips as the stretch changes
  const sin = Math.hypot(...cross(st.chord, out)), w = smooth((sin - 0.25) / 0.45);
  if (w < 1) out = norm(out.map((c, i) => c * w + north[i] * (1 - w)));
  let side = cross(st.chord, out);
  if (Math.hypot(...side) < 1e-6) side = cross(st.chord, Math.abs(dot(st.chord, B.y)) < 0.9 ? B.y : [1, 0, 0]);
  side = norm(side);
  if (shot.path.side) side = side.map((c) => c * Math.sign(shot.path.side));
  else {
    // the sunlit side, leaning north when the Sun is edge-on to the stretch (one smooth rule, so the side never flips
    // from one frame to the next)
    const toSun = st.toSun || (sunId && sunId !== at.anchor ? norm(world.vec(at.anchor, sunId).map((c, i) => c - st.centre[i])) : B.y);
    if (dot(side, toSun) + 0.3 * dot(side, B.y) < 0) side = side.map((c) => -c);
  }
  out = norm(out.map((c, i) => c - st.chord[i] * dot(out, st.chord)));
  const e = (shot.el_deg ?? 25) * RAD;
  const dir = norm(side.map((c, i) => c * Math.cos(e) + out[i] * Math.sin(e)));
  let up = out.map((c, i) => c - dir[i] * dot(out, dir));
  if (Math.hypot(...up) < 1e-6) up = side.map((c, i) => c - dir[i] * dot(side, dir));
  up = norm(up);
  const right = cross(dir, up), fit = shot.path.fit ?? 1.3;
  let dist = 0;
  for (const q of st.pts) {
    const o = q.map((v, i) => v - st.centre[i]);
    dist = Math.max(dist, dot(o, dir) + Math.max(Math.abs(dot(o, up)) * fit / tanHalf, Math.abs(dot(o, right)) * fit / (tanHalf * aspect)));
  }
  dist = Math.max(dist, shot.path.min_km ?? 0, 1e-3);
  const R = world.get(at.anchor)?.radiusKm || 0;            // never inside the body: step back until the camera is outside it
  for (let k = 0; k < 12 && Math.hypot(...st.centre.map((v, i) => v + dir[i] * dist)) < R * 1.03; k++) dist *= 1.25;
  return { dist, dir, up };
}

function shotState(world, shot, tanHalf, sunId, ctx = {}) {
  let at;
  if (shot.path) {
    const traj = ctx.trajectory && ctx.trajectory(shot.path.trajectory);
    if (!traj) throw new Error(`camera: path needs trajectory ${shot.path.trajectory}`);
    const st = pathStretch(world, traj, shot.path, sunId, ctx.memo);
    at = { anchor: traj.frame, local: st.centre };
    return { ...at, ...pathView(world, shot, at, st, tanHalf, ctx.aspect || 16 / 9, sunId), orbit: 0 };
  }
  if (shot.follow) {
    const traj = ctx.trajectory && ctx.trajectory(shot.follow.trajectory);
    if (!traj) throw new Error(`camera: follow needs trajectory ${shot.follow.trajectory}`);
    const when = shot.follow.motion ? motionWhen(shot.follow.motion, ctx.t ?? 0) : +world.date;
    at = { anchor: traj.frame, local: traj.at(when).position };
  } else at = anchorTarget(world, shot.target);
  const body = world.get(at.anchor);
  let dist;
  if (shot.fill) dist = (body.radiusKm / tanHalf) / shot.fill;
  else if (shot.fit && String(shot.target).includes('+')) {
    // "earth+moon" with fit: 1.6 -> far enough that the pair spans 1/1.6 of the frame height (at the shot's own date)
    const ids = String(shot.target).split('+').map((x) => x.trim()), span = Math.hypot(...world.vec(ids[0], ids[ids.length - 1]));
    dist = (span / 2 / tanHalf) * shot.fit;
  } else dist = toKm(shot.distance);
  if (shot.face && !shot.follow) {
    // facing a craft: the camera looks at the body from the side where that craft is at face.utc (raised el_deg towards the
    // Sun), so the stretch of its path the beat shows is on the near side, not hidden behind the planet
    const traj = ctx.trajectory && ctx.trajectory(shot.face.trajectory);
    if (traj) {
      const off = world.vec(at.anchor, traj.frame), cp = traj.at(Date.parse(shot.face.utc)).position;
      const side = norm([0, 1, 2].map((i) => off[i] + cp[i] - at.local[i]));
      const toward = sunId && sunId !== at.anchor ? norm(world.vec(at.anchor, sunId).map((c, i) => c - at.local[i])) : world.orientation(at.anchor).y;
      let lift = toward.map((c, i) => c - side[i] * dot(toward, side));
      if (Math.hypot(...lift) < 1e-6) lift = world.orientation(at.anchor).y;
      lift = norm(lift);
      const e = (shot.el_deg ?? 30) * RAD;
      let dir = norm(side.map((c, i) => c * Math.cos(e) + lift[i] * Math.sin(e)));
      if (shot.az_deg) dir = rotateAbout(dir, lift, shot.az_deg);           // a slow drift round the body
      return { ...at, dist, dir, up: world.orientation(at.anchor).y, orbit: 0 };
    }
  }
  if (shot.follow && shot.look !== 'free') {
    // following a craft: the camera stands OUTSIDE it, looking back towards the body it moves around (the planet, the Moon,
    // the Sun), raised el_deg towards the Sun (so a craft over the night side still has the lit limb behind it; north when
    // the body IS the Sun) -- the craft in front, the world behind it, whatever the orbit
    const B = world.orientation(at.anchor), base = norm(at.local);
    const toward = sunId && sunId !== at.anchor ? norm(world.vec(at.anchor, sunId).map((c, i) => c - at.local[i])) : B.y;
    let lift = toward.map((c, i) => c - base[i] * dot(toward, base));
    if (Math.hypot(...lift) < 1e-6) lift = Math.abs(base[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1];
    lift = norm(lift);
    const e = (shot.el_deg ?? 25) * RAD;
    let dir = norm(base.map((c, i) => c * Math.cos(e) + lift[i] * Math.sin(e)));
    if (shot.az_deg) dir = rotateAbout(dir, base, shot.az_deg);
    return { ...at, dist, dir, up: lift, orbit: 0 };
  }
  const sf = shot.follow ? null : surfaceFrame(world, shot.target);
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
    if (shot.fit && String(shot.target).includes('+') && shot.az_deg == null) {
      // a pair framed by its separation is seen side-on (perpendicular to the line between them), el above that side
      const ids = String(shot.target).split('+').map((x) => x.trim());
      const sep = norm(world.vec(ids[0], ids[ids.length - 1]));
      let side = cross(sep, B.y);
      if (Math.hypot(...side) < 1e-6) side = cross(sep, [1, 0, 0]);
      side = norm(side);
      const up = norm(cross(side, sep)), e = (shot.el_deg || 0) * RAD;
      return { ...at, dist, dir: norm(side.map((c, i) => c * Math.cos(e) + up[i] * Math.sin(e))), up, orbit: shot.orbit_deg_per_s || 0 };
    }
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

/** spec.camera = { start: shot, moves: [{ t, dur, to: shot }] } -> camera(t) = { anchor, position, target, up, distance }.
 *  dateAt(t) (the universe clock) lets a glide leave from the shot as it stood when the glide began: a view fixed to a
 *  turning surface does not spin round with a planet while the clock races during the move. */
export function createCamera(world, cam, { trajectory, dateAt } = {}) {
  const tanHalf = Math.tan(((cam.fov_deg || 40) / 2) * RAD);
  const sunId = cam.sun || [...world.nodes.values()].find((n) => n.kind === 'star')?.id;
  const sorted = (cam.moves || []).slice().sort((a, b) => a.t - b.t);
  const shots = [cam.start, ...sorted.map((m) => m.to)];
  const moves = sorted.map((m, i) => ({ t0: m.t, t1: m.t + (m.dur ?? 4), i }));
  const drift = cam.drift_deg_per_s || 0, RAMP = 0.8, memo = new Map();
  // the drift's still windows, merged when their ramps would touch
  const still = [];
  for (const [a, b] of (cam.still || []).slice().sort((x, y) => x[0] - y[0])) {
    const last = still[still.length - 1];
    if (last && a - RAMP <= last[1] + RAMP) last[1] = Math.max(last[1], b); else still.push([a, b]);
  }
  /** Seconds of drift up to t: narration time minus the time spent still (the rate eases down and up over RAMP s). */
  const drifted = (t) => {
    let off = 0;
    for (const [a, b] of still) {
      if (t <= a - RAMP) break;
      if (t < a) off += (t - (a - RAMP)) ** 2 / (2 * RAMP);
      else if (t < b) off += RAMP / 2 + (t - a);
      else if (t < b + RAMP) off += RAMP / 2 + (b - a) + (t - b) - (t - b) ** 2 / (2 * RAMP);
      else off += RAMP + (b - a);
    }
    return t - off;
  };
  return function at(t) {
    let idx = 0, move = null, held = 0;
    for (const m of moves) {
      if (t >= m.t1) { idx = m.i + 1; held = m.t1; continue; }
      if (t > m.t0) move = m;
      break;
    }
    let s;
    const ctx = { trajectory, t, aspect: cam.aspect, memo };
    if (!move) {
      const st = shotState(world, shots[idx], tanHalf, sunId, ctx);
      s = { ...st, target: st.local };
      if (st.orbit) s.dir = rotateAbout(st.dir, st.up, st.orbit * (t - held));
    } else {
      const to = shotState(world, shots[move.i + 1], tanHalf, sunId, ctx);
      let from;
      if (dateAt) {
        const was = world.date;
        world.setTime(dateAt(move.t0));
        // its point stays relative to its body, so the body's own travel is still followed; only its turning is frozen
        try { from = shotState(world, shots[move.i], tanHalf, sunId, { ...ctx, t: move.t0 }); } finally { world.setTime(was); }
      } else from = shotState(world, shots[move.i], tanHalf, sunId, ctx);
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
    if (drift) dir = rotateAbout(dir, s.up, drift * drifted(t));   // a slow drift keeps a quiet shot alive; it rests while things move
    const position = s.target.map((v, i) => v + dir[i] * s.dist);
    // keep: the camera stays where it is and only TURNS when a craft is about to leave the frame (a soft follow, not a chase).
    // During a glide the two shots' corrections are blended, so a hand-over between beats never jumps.
    const kept = (keep) => {
      const tr = keep && trajectory ? trajectory(keep.trajectory) : null;
      if (!tr) return s.target;
      const when = keep.motion ? motionWhen(keep.motion, t) : +world.date;
      const off = world.vec(s.anchor, tr.frame), cp = tr.at(when).position;
      const craft = [0, 1, 2].map((i) => off[i] + cp[i] - position[i]);
      const look = s.target.map((v, i) => v - position[i]), L = Math.hypot(...look), C = Math.hypot(...craft);
      if (!(L > 0 && C > 0)) return s.target;
      // how far it may drift is measured on the screen, towards where it is: a wide frame lets it go further sideways
      const lu = norm(look), cu = norm(craft), right = norm(cross(lu, s.up)), upv = cross(right, lu);
      const sx = dot(cu, right), sy = dot(cu, upv), sl = Math.hypot(sx, sy) || 1, aspect = cam.aspect || 16 / 9;
      const reach = Math.atan((keep.within ?? 0.5) * tanHalf / Math.sqrt((sx / sl / aspect) ** 2 + (sy / sl) ** 2));
      const th = Math.acos(Math.max(-1, Math.min(1, dot(look, craft) / (L * C)))), lim = reach;
      if (th <= lim) return s.target;
      // a craft far off to the side or behind (mid-glide, a whole other place) is not chased: the turn fades out
      // smoothly past 70 degrees, so the correction never whips round
      const fade = smooth((100 * RAD - th) / (30 * RAD));
      if (fade <= 0) return s.target;
      const nd = slerp(norm(look), norm(craft), ((th - lim) / th) * fade);
      return position.map((v, i) => v + nd[i] * L);
    };
    let target = s.target;
    if (move) {
      // mid-glide nothing is kept: each shot's correction only matters near its own end of the glide (so the hand-over
      // is continuous), and the glide itself never swings round after a craft
      const k = move.t1 > move.t0 ? smooth((t - move.t0) / (move.t1 - move.t0)) : 1;
      // the shot being left may only finish a reframe it was already making when the move began: the move itself carries
      // the craft about the frame, and a reframe starting mid-move would fight it (the look-at point swung 12,000 km)
      const mk = `reframing@${move.i}`;
      if (!memo.has(mk)) {
        const was = world.date;
        if (dateAt) world.setTime(dateAt(move.t0));
        try { memo.set(mk, !!at(move.t0).reframing); } finally { world.setTime(was); }
      }
      // the shot being arrived at does not reframe during the move either (it turned the camera after a craft the move
      // had left behind, then let go in one frame): it eases in once the move has settled, below
      const a = memo.get(mk) ? shots[move.i].keep : null;
      if (a) {
        const ta = kept(a), wa = (1 - k) ** 3;
        target = s.target.map((v, i) => v + (ta[i] - v) * wa);
      }
    } else if (shots[idx].keep) {
      const ease = idx > 0 ? smooth((t - held) / 1.5) : 1;      // after a move, the reframe fades in instead of switching on
      const tk = kept(shots[idx].keep);
      target = ease >= 1 ? tk : s.target.map((v, i) => v + (tk[i] - v) * ease);
    }
    if (target !== s.target && target.some((v, i) => Math.abs(v - s.target[i]) > 1e-9)) {
      const L = Math.hypot(...target.map((v, i) => v - position[i]));
      return { anchor: s.anchor, position, target, up: s.up, distance: L, reframing: true };
    }
    return { anchor: s.anchor, position, target: s.target, up: s.up, distance: s.dist };
  };
}
