// Cinematic camera. A shot = behaviour + subject + time span; cameraAt() gives position, aim and lens for any time. Moves
// are eased over the whole shot (no snap starts), subjects are smoothed over a second (no jitter from walking bodies), and
// constrain() keeps the camera above terrain, water and roofs and out of walls, raising it gently ahead of obstacles.

import { clamp, lerp, smooth, smoother, easeInOut } from './rng.mjs';
import { clearanceAt } from './world.mjs';

export const BEHAVIOURS = ['establishing_wide', 'aerial_geo', 'low_angle', 'follow', 'over_shoulder', 'ground_track', 'vehicle_follow', 'flyover', 'orbit',
  'dolly_in', 'dolly_out', 'crane_up', 'descend', 'rise', 'side_track', 'push_in', 'pullback_reveal', 'establishing_interior', 'map_overview', 'map_dive', 'static_close',
  // slow horror moves (lib/horror.mjs): creep toward a face, hold and breathe (never frozen), walk just behind the hero
  'creep_in', 'hold_breathe', 'behind_follow', 'hand_close', 'handover'];

// lens per behaviour (vertical fov, degrees) and how far it may go below the subject's scale
const FOV = { establishing_wide: 38, aerial_geo: 34, low_angle: 46, follow: 44, over_shoulder: 40, ground_track: 42, vehicle_follow: 42, flyover: 46, orbit: 40,
  dolly_in: 38, dolly_out: 40, crane_up: 42, descend: 40, rise: 42, side_track: 38, push_in: 30, pullback_reveal: 42, establishing_interior: 52, map_overview: 30, map_dive: 34, static_close: 32, creep_in: 34, hold_breathe: 32, behind_follow: 46, hand_close: 30, handover: 38 };

const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const polar = (yaw, dist, h) => [Math.sin(yaw) * dist, h, Math.cos(yaw) * dist];

/** shot: {behaviour, t0, t1, yaw (side the camera sits on), scale (subject size), dist, height, subjectEnd?}
 *  subj(t) -> [x,y,z] subject point ; dirAt(t) -> yaw the subject moves toward (for follow shots) */
export function shotCamera(shot, t, subj, dirAt = () => 0) {
  const u = clamp((t - shot.t0) / Math.max(0.01, shot.t1 - shot.t0), 0, 1), e = smoother(u), ee = easeInOut(u);
  const S = shot.scale || 1, yaw = shot.yaw ?? 0.6, P = subj(t);
  let pos, tgt = [P[0], P[1] + 2.5 * S, P[2]], fov = FOV[shot.behaviour] || 40;
  switch (shot.behaviour) {
    case 'establishing_wide': { const d = (shot.dist || 210) * S, h = (shot.height || 70) * S; pos = add(P, polar(yaw + e * 0.18, d * (1 - e * 0.06), h * (1 - e * 0.08))); tgt = [P[0], P[1] + 4, P[2]]; break; }
    case 'aerial_geo': { const h = (shot.height || 300) * S; pos = add(P, polar(yaw + e * 0.12, h * 0.55 * (1 - e * 0.12), h * (1 - e * 0.1))); tgt = P; break; }
    case 'low_angle': { const d = (shot.dist || 13) * S; pos = add(P, polar(yaw + e * 0.12, d * (1 - e * 0.1), 1.2)); tgt = [P[0], P[1] + 4.2 * S, P[2]]; break; }
    case 'follow': { const dy = dirAt(t) + Math.PI, d = (shot.dist || 18) * S; pos = add(P, polar(dy + 0.25, d, (shot.height || 7) * S)); tgt = add(P, polar(dy + Math.PI, 12 * S, 2.5)); break; }
    case 'vehicle_follow': { const dy = dirAt(t) + Math.PI + (shot.side || 0.5), d = (shot.dist || 34) * S; pos = add(P, polar(dy - e * 0.25, d * (1 - e * 0.1), (shot.height || 12) * S)); tgt = add(P, polar(dirAt(t), 8 * S, 1)); break; }
    case 'over_shoulder': { const Q = shot.lookAt || add(P, polar(yaw + Math.PI, 10, 0)); const dx = Q[0] - P[0], dz = Q[2] - P[2], L = Math.hypot(dx, dz) || 1;
      pos = [P[0] - dx / L * 4.5 * S + dz / L * 1.8 * S, P[1] + 5.6 * S, P[2] - dz / L * 4.5 * S - dx / L * 1.8 * S]; tgt = [lerp(P[0], Q[0], 0.85), Q[1] + 3.8 * S, lerp(P[2], Q[2], 0.85)];
      pos = add(pos, [dz / L * e * 1.2, 0, -dx / L * e * 1.2]); break; }
    case 'ground_track': { const d = (shot.dist || 18) * S, side = yaw + Math.PI / 2; pos = add(P, polar(side, d, 2.4 * S)); tgt = [P[0], P[1] + 2.6 * S, P[2]]; break; }
    case 'side_track': { const d = (shot.dist || 46) * S, base = shot.base || P, k = lerp(-1, 1, e) * (shot.travel || 30) * S;
      pos = add(base, add(polar(yaw, d, (shot.height || 9) * S), [Math.cos(yaw) * k, 0, -Math.sin(yaw) * k])); tgt = add(base, [Math.cos(yaw) * k * 0.9, 3 * S, -Math.sin(yaw) * k * 0.9]);
      if (!shot.base) { tgt = [P[0], P[1] + 3 * S, P[2]]; } break; }
    case 'flyover': { const L = (shot.travel || 260) * S, h = (shot.height || 60) * S, base = shot.base || P, dirY = shot.dir ?? yaw;
      const k = lerp(-0.5, 0.5, u) * L; pos = add(base, [Math.sin(dirY) * k, h, Math.cos(dirY) * k]); tgt = add(base, [Math.sin(dirY) * (k + h * 1.6), 0, Math.cos(dirY) * (k + h * 1.6)]); break; }
    case 'orbit': { const d = (shot.dist || 30) * S; pos = add(P, polar(yaw + (t - shot.t0) * (shot.rate || 0.09), d, (shot.height || 9) * S)); break; }
    case 'dolly_in': case 'push_in': { const d0 = (shot.dist || (shot.behaviour === 'push_in' ? 16 : 70)) * S, d1 = d0 * (shot.behaviour === 'push_in' ? 0.55 : 0.6);
      pos = add(P, polar(yaw, lerp(d0, d1, ee), (shot.height || (shot.behaviour === 'push_in' ? 4.6 : 14)) * S)); if (shot.behaviour === 'push_in') tgt = [P[0], P[1] + 4.4 * S, P[2]]; break; }
    case 'dolly_out': { const d0 = (shot.dist || 30) * S; pos = add(P, polar(yaw, lerp(d0, d0 * 1.7, ee), (shot.height || 8) * S * lerp(1, 1.5, ee))); break; }
    case 'crane_up': { const d = (shot.dist || 30) * S; pos = add(P, polar(yaw + e * 0.1, d * lerp(1, 1.25, e), lerp(2.2, (shot.height || 38), ee) * S)); tgt = [P[0], P[1] + lerp(4, 0, e) * S, P[2]]; break; }
    case 'descend': { const h0 = (shot.height || 240) * S, h1 = (shot.low || 16) * S, h = lerp(h0, h1, smooth(u)), d = lerp(h0 * 0.55, (shot.dist || 40) * S, smooth(u));
      pos = add(P, polar(yaw + e * 0.2, d, h)); tgt = [P[0], P[1] + lerp(0, 3, u) * S, P[2]]; break; }
    case 'rise': { const h0 = (shot.low || 6) * S, h1 = (shot.height || 150) * S; pos = add(P, polar(yaw - e * 0.2, lerp((shot.dist || 22) * S, h1 * 0.8, ee), lerp(h0, h1, ee))); tgt = [P[0], P[1] + lerp(3, 0, e), P[2]]; break; }
    case 'pullback_reveal': { const d0 = (shot.dist || 10) * S, d1 = (shot.far || 150) * S; pos = add(P, polar(yaw + e * 0.3, lerp(d0, d1, ee), lerp(3.5, d1 * 0.42, ee))); tgt = [P[0], P[1] + lerp(3, 0, e), P[2]]; break; }
    case 'establishing_interior': { pos = [lerp(-17, -12, e), 10.5, lerp(11, 9, e)]; tgt = [2, 2.5, -3]; break; }
    case 'static_close': { pos = add(P, polar(yaw, (shot.dist || 9) * S, 4.4 * S)); tgt = [P[0], P[1] + 4.3 * S, P[2]]; pos = add(pos, [Math.sin(t * 0.3) * 0.15, Math.sin(t * 0.21) * 0.1, 0]); break; }
    case 'creep_in': { const d0 = (shot.dist || 20) * S; pos = add(P, polar(yaw + e * 0.05, lerp(d0, d0 * 0.72, smooth(u)), lerp(5, 4.6, u) * S)); tgt = [P[0], P[1] + 4.3 * S, P[2]]; break; }
    case 'hold_breathe': { const d = (shot.dist || 11) * S * lerp(1, 0.96, u); pos = add(P, polar(yaw, d, 4.6 * S)); tgt = [P[0], P[1] + 4.3 * S, P[2]];
      pos = add(pos, [Math.sin(t * 0.5) * 0.35, Math.sin(t * 0.37) * 0.2, Math.cos(t * 0.43) * 0.25]); break; }
    case 'behind_follow': { const dy = dirAt(t) + Math.PI, d = (shot.dist || 10) * S; pos = add(P, polar(dy + 0.12, d, (shot.height || 4.8) * S)); tgt = add(P, polar(dy + Math.PI, 14 * S, 3.2)); break; }
    case 'handover': { pos = add(P, polar(yaw + e * 0.06, lerp(12, 10, ee), 1.4)); tgt = [P[0], P[1] + 0.8, P[2]]; break; }   // side on: both people and the thing passing between them
    case 'hand_close': { const d = lerp(4.4, 3.3, ee) * S; pos = add(P, polar(yaw + e * 0.08, d, 1.3 * S)); tgt = P; pos = add(pos, [Math.sin(t * 0.5) * 0.08, Math.sin(t * 0.37) * 0.05, 0]); break; }   // a small thing in a hand
    case 'map_overview': { const h = shot.height || 520; pos = add(P, [0, h * lerp(1, 0.9, ee), h * 0.32 * lerp(1, 0.85, ee)]); tgt = P; break; }
    case 'map_dive': { const h0 = shot.height || 420, h1 = shot.low || 30; const h = h0 * Math.pow(h1 / h0, ee); pos = add(P, [0, h, h * 0.36]); tgt = P; break; }
    default: pos = add(P, polar(yaw, 40, 12)); break;
  }
  return { pos, target: tgt, fov, roll: shot.roll ? shot.roll * Math.sin(u * Math.PI) : 0 };
}

// Indoor moves: [distance start, end (fraction of the room behind the subject), height start, end, side swing start, end].
// Outdoor distances (70, 150...) only pinned the camera to a wall, so a room gets its own table and every move stays in the room.
const ROOM_MOVES = { dolly_in: [1, 0.62, 6.4, 5.8, 0.25, 0.1], push_in: [0.7, 0.45, 5.6, 5.4, 0.12, 0.05], dolly_out: [0.5, 1, 5.6, 7.5, 0.1, 0.3], pullback_reveal: [0.42, 1, 5, 8.5, 0.35, 0.1],
  crane_up: [0.7, 0.85, 2.6, 11, 0.3, 0.4], rise: [0.55, 0.9, 4, 11, -0.2, 0.2], descend: [0.9, 0.55, 11, 5, 0.3, 0.1], low_angle: [0.62, 0.55, 1.5, 1.5, 0.5, 0.6], follow: [0.6, 0.6, 6.5, 6.5, 0.2, 0.2],
  ground_track: [0.65, 0.65, 4.5, 4.5, 0.7, 0.35], side_track: [0.75, 0.75, 6, 6, -0.65, 0.65], orbit: [0.72, 0.72, 7, 7, -0.5, 0.5], static_close: [0.46, 0.42, 5.3, 5.3, 0.2, 0.17],
  creep_in: [0.8, 0.5, 5.6, 5.3, 0.1, 0.04], hold_breathe: [0.5, 0.47, 5.3, 5.2, 0.18, 0.15], behind_follow: [0.6, 0.6, 6, 6, 0.15, 0.15] };
const ROOM_NEAR = 6.5, ROOM_FAR = 18;
const rayToWall = (room, P, ang) => {
  const dx = Math.sin(ang), dz = Math.cos(ang); let d = 1e9;
  if (dx > 1e-6) d = Math.min(d, (room.x1 - P[0]) / dx); if (dx < -1e-6) d = Math.min(d, (room.x0 - P[0]) / dx);
  if (dz > 1e-6) d = Math.min(d, (room.z1 - P[2]) / dz); if (dz < -1e-6) d = Math.min(d, (room.z0 - P[2]) / dz);
  return Math.max(0, d);
};
/** A shot inside a room. P = subject on the floor, Q = what the shot is about (the prop being spoken of, another person). The camera
 *  stands on the far side of P from Q, so P and Q share the frame, and never closer to P than a head-and-shoulders. beside = stand off to
 *  one side (a mirror: straight behind, the person's own head hides the reflection). */
export function roomCamera(shot, t, room, P, Q, small = false, beside = false, glass = null) {
  const u = clamp((t - shot.t0) / Math.max(0.01, shot.t1 - shot.t0), 0, 1), e = smoother(u), ee = easeInOut(u), beh = shot.behaviour;
  if (glass) { // the reflection is acting: past the shoulder, long lens, onto the face in the glass
    const side = P[0] < Q[0] - 1 ? 1 : -1;
    return { pos: [P[0] + side * 3.2, P[1] + 5.2, P[2] + lerp(2.6, 1.4, ee)], target: glass, fov: lerp(24, 19, ee), roll: 0 };
  }
  if ((beh === 'establishing_interior' || beh === 'establishing_wide') && room.wide) {
    const w = room.wide; return { pos: w.from.map((v, i) => lerp(v, w.to[i], e)), target: w.target, fov: 52, roll: 0 };
  }
  const apart = Math.hypot(P[0] - Q[0], P[2] - Q[2]), head = [P[0], P[1] + 4.4, P[2]];
  let base = apart > 1 ? Math.atan2(P[0] - Q[0], P[2] - Q[2]) : shot.yaw ?? 0.6;
  const off = [0, 0.5, -0.5, 1, -1, 1.5, -1.5, 2.2, -2.2, Math.PI].find((a) => rayToWall(room, P, base + a) >= 10) ?? 0; base += off;
  if (small) { // the thing itself: a ring, a phone, a plate
    const a = base + 0.35, d = lerp(6, 4.6, ee), pos = [Q[0] + Math.sin(a) * d, Q[1] + lerp(3, 2.2, ee), Q[2] + Math.cos(a) * d];
    return { pos, target: Q, fov: 36, roll: 0 };
  }
  if (beh === 'over_shoulder' && apart > 1) {
    const dx = (Q[0] - P[0]) / apart, dz = (Q[2] - P[2]) / apart, side = (Math.sin((shot.yaw || 0) * 7) >= 0 ? 1 : -1) * lerp(2.2, 3, e) * (beside ? 1.7 : 1);
    return { pos: [P[0] - dx * 5 + dz * side, P[1] + 6.4, P[2] - dz * 5 - dx * side], target: [Q[0], Q[1], Q[2]], fov: 42, roll: 0 };
  }
  const M = ROOM_MOVES[beh] || ROOM_MOVES.dolly_in, sign = Math.sin((shot.yaw || 0) * 7) >= 0 ? 1 : -1;
  const swing = Math.min(rayToWall(room, P, base + sign * M[4]), rayToWall(room, P, base + sign * M[5])) >= ROOM_NEAR ? sign : 0;
  const clear = beside && rayToWall(room, P, base + sign * 0.6) >= ROOM_NEAR ? sign * 0.6 : 0, ang = base + clear + swing * lerp(M[4], M[5], e), reach = Math.min(ROOM_FAR, rayToWall(room, P, ang));
  const d = Math.min(reach, Math.max(ROOM_NEAR, reach * lerp(M[0], M[1], ee)));
  const look = apart > 1 ? Math.min(0.3, 0.3 * d / apart) : 0; // the aim leans toward the prop but the person stays in frame
  const breathe = beh === 'hold_breathe' ? [Math.sin(t * 0.5) * 0.25, Math.sin(t * 0.37) * 0.15, Math.cos(t * 0.43) * 0.2] : [0, 0, 0];   // alive, never frozen
  return { pos: [P[0] + Math.sin(ang) * d + breathe[0], clamp(P[1] + lerp(M[2], M[3], ee) + breathe[1], room.y0, room.y1), P[2] + Math.cos(ang) * d + breathe[2]], target: head.map((v, i) => lerp(v, Q[i], look)), fov: 40, roll: 0 };
}

/** Keep the camera above ground/water/roofs (with margin) and the line of sight clear; inside rooms keep it in the room. */
export function constrain(cam, world, margin = 1.6) {
  const p = [...cam.pos];
  const room = world.colliders.find((c) => c.inside);
  if (room) {
    p[0] = clamp(p[0], room.x0, room.x1); p[2] = clamp(p[2], room.z0, room.z1); p[1] = clamp(p[1], room.y0, room.y1);
    return { ...cam, pos: p };
  }
  // the highest obstacle in a small neighbourhood (so a single block does not make the camera hop)
  let need = -Infinity;
  for (const [dx, dz] of [[0, 0], [3, 0], [-3, 0], [0, 3], [0, -3]]) need = Math.max(need, clearanceAt(world, p[0] + dx, p[2] + dz));
  // line of sight: sample toward the target; if terrain blocks, lift the camera so the ray clears it
  const T = cam.target;
  for (let k = 1; k < 8; k++) {
    const f = k / 8, x = lerp(p[0], T[0], f), z = lerp(p[2], T[2], f), g = world.heightAt(x, z) + 0.6, yRay = lerp(p[1], T[1], f);
    if (g > yRay && f < 0.9) need = Math.max(need, p[1] + (g - yRay) / (1 - f));
  }
  p[1] = Math.max(p[1], need + margin);
  return { ...cam, pos: p };
}

/** Largest per-frame camera move inside a shot list, ignoring cuts: [{t, d}] sorted worst first (used by the jump test). */
export function cameraJumps(samples, cutTimes, fps) {
  const out = [];
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i];
    if (cutTimes.some((c) => c > a.t && c <= b.t + 1e-6)) continue;
    const d = Math.hypot(b.pos[0] - a.pos[0], b.pos[1] - a.pos[1], b.pos[2] - a.pos[2]);
    const scale = Math.max(4, Math.hypot(a.pos[0] - a.target[0], a.pos[1] - a.target[1], a.pos[2] - a.target[2]));
    out.push({ t: b.t, d, rel: d / scale * fps });
  }
  return out.sort((x, y) => y.rel - x.rel);
}
