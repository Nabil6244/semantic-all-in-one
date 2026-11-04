// Procedural animation for blocky characters. A pose is a few joint angles (radians); every state is a function of time, so
// any frame can be computed on its own (deterministic, renderable out of order). Characters follow a schedule of states with
// 0.3 s blends between them; a breathing/glance layer runs under every state so nobody is ever frozen in place.
//
// Joints: limbs rotate at the shoulder/hip (R6 style: rigid limbs, no elbows/knees). x = swing forward (+) / back (-),
// z = out to the side (+ = away from the body). root.y lifts/sinks the whole body (studs), root.pitch leans it.

import { clamp, lerp, smooth } from './rng.mjs';

export const STATES = ['idle', 'walk', 'run', 'march', 'turn', 'look', 'point', 'talk', 'gesture', 'listen', 'salute', 'crouch', 'cover', 'carry',
  'enter_vehicle', 'exit_vehicle', 'climb', 'fall', 'react', 'aim', 'fire', 'wade', 'parachute', 'cheer', 'wave', 'sit', 'ride', 'hands_up', 'crawl', 'lie'];

/** Ground speed (studs/s) of the moving states; 0 = stays on its spot. */
export const SPEED = { walk: 4.2, march: 4.6, run: 9.5, wade: 2.6, crawl: 1.2, carry: 3.4, climb: 1.4, enter_vehicle: 3.5, exit_vehicle: 3.5 };

const base = () => ({ root: { y: 0, pitch: 0, roll: 0, yaw: 0 }, torso: { pitch: 0, yaw: 0 }, head: { yaw: 0, pitch: 0 },
  armL: { x: 0, z: 0.04 }, armR: { x: 0, z: 0.04 }, legL: { x: 0, z: 0 }, legR: { x: 0, z: 0 }, gun: 'carry', flash: 0, chute: 0 });

const S = Math.sin, C = Math.cos;

/** Pose of one state at local time u (seconds since the state began), for a person with phase offset ph (0..1). */
export function statePose(state, u, ph = 0, opts = {}) {
  const p = base(), w = 2 * Math.PI;
  const breathe = S(w * (u * 0.28 + ph)) * 0.025;
  p.armL.x = breathe; p.armR.x = -breathe;
  p.head.yaw = S(w * (u * 0.07 + ph * 3)) * 0.18;
  p.head.pitch = S(w * (u * 0.11 + ph)) * 0.04;
  switch (state) {
    case 'idle': p.root.y = breathe * 0.4; p.gun = opts.armed ? 'carry' : 'none'; break;
    case 'listen': p.head.pitch = -0.08 + S(w * (u * 0.5 + ph)) * 0.05; p.head.yaw *= 0.3; p.armL.x = 0.1; p.armR.x = 0.1; p.armL.z = 0.15; p.armR.z = 0.15; p.gun = 'none'; break;
    case 'look': p.head.yaw = S(w * (u * 0.22 + ph)) * 0.75; p.torso.yaw = p.head.yaw * 0.3; break;
    case 'turn': p.root.yaw = smooth(u / 0.8) * (opts.turn ?? Math.PI * 0.5); p.legL.x = S(w * u * 1.6) * 0.35 * (u < 0.8 ? 1 : 0); p.legR.x = -p.legL.x; break;
    case 'walk': case 'march': case 'carry': {
      const f = state === 'march' ? 1.75 : 1.5, a = state === 'march' ? 0.75 : 0.6, s = S(w * (u * f + ph));
      p.legL.x = s * a; p.legR.x = -s * a; p.armL.x = -s * a * (state === 'carry' ? 0.1 : 0.85); p.armR.x = s * a * 0.85;
      p.root.y = Math.abs(C(w * (u * f + ph))) * 0.12; p.root.pitch = 0.04;
      if (state === 'carry') { p.armL.x = 1.25; p.armR.x = 1.25; p.armL.z = -0.15; p.armR.z = -0.15; p.gun = 'back'; }
      if (opts.armed && state !== 'carry') { p.armR.x = 0.55; p.armL.x = 0.9; p.armL.z = -0.35; p.gun = 'port'; }
      break;
    }
    case 'run': case 'wade': {
      const f = state === 'wade' ? 1.1 : 2.4, a = state === 'wade' ? 0.5 : 1.0, s = S(w * (u * f + ph));
      p.legL.x = s * a; p.legR.x = -s * a; p.armL.x = -s * a * 0.9; p.armR.x = s * a * 0.9;
      p.root.y = Math.abs(C(w * (u * f + ph))) * (state === 'wade' ? 0.06 : 0.3); p.root.pitch = state === 'wade' ? 0.12 : 0.22;
      if (opts.armed) { p.armR.x = 0.75 + s * 0.08; p.armL.x = 1.05; p.armL.z = -0.4; p.gun = 'port'; }
      break;
    }
    case 'crawl': { const s = S(w * (u * 0.9 + ph)); p.root.pitch = 1.45; p.root.y = -1.9; p.armL.x = 2.6 + s * 0.4; p.armR.x = 2.6 - s * 0.4; p.legL.x = s * 0.3; p.legR.x = -s * 0.3; p.gun = 'back'; break; }
    case 'point': { const k = smooth(u / 0.45); p.armR.x = lerp(0, 1.55, k); p.armR.z = -0.05; p.torso.yaw = -0.15 * k; p.head.yaw = -0.1 * k; p.armR.x += S(w * u * 0.6) * 0.03; p.gun = 'none'; break; }
    case 'talk': {
      const g = S(w * (u * 0.55 + ph)), g2 = S(w * (u * 0.31 + ph * 2));
      p.armR.x = 0.5 + Math.max(0, g) * 0.6; p.armR.z = 0.1 + g2 * 0.08; p.armL.x = 0.2 + Math.max(0, -g) * 0.35; p.head.pitch = S(w * u * 1.7) * 0.05; p.torso.yaw = g2 * 0.08; p.gun = 'none'; p.talking = 1; break;
    }
    case 'gesture': { const g = S(w * (u * 0.45 + ph)); p.armR.x = 0.9 + g * 0.3; p.armR.z = 0.35 + g * 0.2; p.armL.x = 0.9 - g * 0.3; p.armL.z = 0.35 - g * 0.2; p.gun = 'none'; p.talking = 1; break; }
    case 'salute': { const k = smooth(u / 0.35) * (u > 2.4 ? 1 - smooth((u - 2.4) / 0.4) : 1); p.armR.x = 2.55 * k; p.armR.z = -0.55 * k; p.head.yaw = 0; p.gun = 'none'; break; }
    case 'crouch': { p.root.y = -0.8; p.root.pitch = 0.25; p.legL.x = 1.25; p.legR.x = 0.15; p.armL.x = 0.9; p.armR.x = 0.75; p.armL.z = -0.3; p.gun = 'port'; break; }
    case 'cover': {
      const peek = Math.max(0, S(w * (u * 0.18 + ph))) ** 3;
      p.root.y = -0.95 + peek * 0.5; p.root.pitch = 0.35 - peek * 0.2; p.legL.x = 1.3; p.legR.x = 0.25; p.armL.x = 1.2; p.armR.x = 1.0; p.armL.z = -0.3; p.head.yaw = S(w * (u * 0.3 + ph)) * 0.4; p.gun = 'port'; break;
    }
    case 'aim': case 'fire': {
      p.armR.x = 1.5; p.armL.x = 1.6; p.armL.z = -0.55; p.armR.z = -0.05; p.head.pitch = 0.05; p.torso.yaw = -0.12; p.gun = 'aim';
      if (state === 'fire') { const cyc = (u * (opts.rate || 2.2) + ph * 3) % 1; p.flash = cyc < 0.12 ? 1 : 0; p.armR.x -= cyc < 0.15 ? 0.12 : 0; p.armL.x -= cyc < 0.15 ? 0.12 : 0; p.root.pitch = cyc < 0.15 ? -0.04 : 0.02; }
      break;
    }
    case 'react': { const k = Math.exp(-u * 2.5); p.root.pitch = -0.3 * k; p.armL.x = 1.2 * k; p.armR.x = 1.4 * k; p.armL.z = 0.5 * k; p.armR.z = 0.5 * k; p.head.pitch = -0.2 * k; p.root.y = -0.3 * k; break; }
    case 'fall': { const k = smooth(u / 0.7); p.root.pitch = -1.45 * k; p.root.y = -2.0 * k; p.armL.z = 0.9 * k; p.armR.z = 0.9 * k; p.gun = 'drop'; break; }
    case 'lie': { p.root.pitch = -1.5; p.root.y = -2.0; p.armL.z = 0.8; p.armR.z = 0.6; p.head.yaw = 0.2; p.gun = 'drop'; break; }
    case 'climb': { const s = S(w * (u * 1.2 + ph)); p.armL.x = 2.6 + s * 0.4; p.armR.x = 2.6 - s * 0.4; p.legL.x = 0.6 + s * 0.6; p.legR.x = 0.6 - s * 0.6; p.root.pitch = -0.1; p.gun = 'back'; break; }
    case 'parachute': { const sway = S(w * (u * 0.35 + ph)); p.armL.x = 2.8; p.armR.x = 2.8; p.armL.z = 0.25; p.armR.z = 0.25; p.legL.x = 0.15 + sway * 0.1; p.legR.x = 0.15 - sway * 0.1; p.root.roll = sway * 0.12; p.chute = 1; p.gun = 'back'; break; }
    case 'cheer': { const s = Math.abs(S(w * (u * 1.1 + ph))); p.armL.x = 2.6 + s * 0.4; p.armR.x = 2.6 - s * 0.2; p.armL.z = 0.35; p.armR.z = 0.35; p.root.y = s * 0.45; p.gun = 'none'; break; }
    case 'wave': { const s = S(w * (u * 1.4 + ph)); p.armR.x = 2.7; p.armR.z = 0.35 + s * 0.35; p.gun = 'none'; break; }
    case 'hands_up': { const k = smooth(u / 0.5); p.armL.x = 2.9 * k; p.armR.x = 2.9 * k; p.armL.z = 0.2; p.armR.z = 0.2; p.head.pitch = 0.15; p.gun = 'drop'; break; }
    case 'sit': case 'ride': { p.legL.x = 1.57; p.legR.x = 1.57; p.root.y = -1.0; p.armL.x = 0.5; p.armR.x = 0.5; if (state === 'ride') { p.root.y = -1.0 + S(w * (u * 2.1 + ph)) * 0.05; } p.gun = opts.armed ? 'upright' : 'none'; break; }
    case 'enter_vehicle': case 'exit_vehicle': { const s = S(w * (u * 1.5 + ph)); p.legL.x = s * 0.55; p.legR.x = -s * 0.55; p.armL.x = -s * 0.5 + 0.3; p.armR.x = s * 0.5 + 0.3; p.root.y = Math.abs(C(w * (u * 1.5 + ph))) * 0.1; p.gun = 'port'; break; }
    default: break;
  }
  return p;
}

function mixPose(a, b, k) {
  const out = base();
  for (const j of Object.keys(out)) {
    if (typeof out[j] !== 'object') { out[j] = k < 0.5 ? a[j] : b[j]; continue; }
    for (const c of Object.keys(out[j])) out[j][c] = lerp(a[j][c] ?? 0, b[j][c] ?? 0, k);
  }
  out.gun = k < 0.5 ? a.gun : b.gun; out.flash = k < 0.5 ? a.flash : b.flash; out.chute = lerp(a.chute || 0, b.chute || 0, k); out.talking = k < 0.5 ? a.talking : b.talking;
  return out;
}

/** Pose at film time t from a schedule [{t0, t1, state, opts}] (sorted, may have gaps -> idle), blending 0.3 s at changes. */
export function poseAt(schedule, t, ph = 0, defaults = {}) {
  if (!schedule || !schedule.length) return statePose('idle', t, ph, defaults);
  let i = schedule.findIndex((s) => t >= s.t0 && t < s.t1);
  if (i < 0) i = t < schedule[0].t0 ? 0 : schedule.length - 1;
  const cur = schedule[i], o = { ...defaults, ...(cur.opts || {}) };
  const p = statePose(cur.state, Math.max(0, t - cur.t0), ph, o);
  const prev = schedule[i - 1], B = 0.4;
  if (prev && t - cur.t0 < B) return mixPose(statePose(prev.state, t - prev.t0, ph, { ...defaults, ...(prev.opts || {}) }), p, smooth((t - cur.t0) / B));
  return p;
}

/** Distance travelled along the path by time t (only moving states advance; speed from SPEED or the segment's own). */
export function travelAt(schedule, t) {
  let d = 0;
  for (const s of schedule || []) {
    if (t <= s.t0) break;
    const v = s.speed ?? SPEED[s.state] ?? 0;
    d += v * (Math.min(t, s.t1) - s.t0);
  }
  return d;
}

/** Joint-angle change between two poses (used by the freeze test: a living character always moves a little). */
export function poseDelta(a, b) {
  let d = 0;
  for (const j of ['root', 'torso', 'head', 'armL', 'armR', 'legL', 'legR']) for (const c of Object.keys(a[j])) d += Math.abs((a[j][c] || 0) - (b[j][c] || 0));
  return d;
}

export const clampPose = (p) => { p.root.pitch = clamp(p.root.pitch, -1.6, 1.6); return p; };
