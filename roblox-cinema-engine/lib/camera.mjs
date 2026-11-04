// Cinematic camera. A shot = behaviour + subject + time span; cameraAt() gives position, aim and lens for any time. Moves
// are eased over the whole shot (no snap starts), subjects are smoothed over a second (no jitter from walking bodies), and
// constrain() keeps the camera above terrain, water and roofs and out of walls, raising it gently ahead of obstacles.

import { clamp, lerp, smooth, smoother, easeInOut } from './rng.mjs';
import { clearanceAt } from './world.mjs';

export const BEHAVIOURS = ['establishing_wide', 'aerial_geo', 'low_angle', 'follow', 'over_shoulder', 'ground_track', 'vehicle_follow', 'flyover', 'orbit',
  'dolly_in', 'dolly_out', 'crane_up', 'descend', 'rise', 'side_track', 'push_in', 'pullback_reveal', 'establishing_interior', 'map_overview', 'map_dive', 'static_close'];

// lens per behaviour (vertical fov, degrees) and how far it may go below the subject's scale
const FOV = { establishing_wide: 38, aerial_geo: 34, low_angle: 46, follow: 44, over_shoulder: 40, ground_track: 42, vehicle_follow: 42, flyover: 46, orbit: 40,
  dolly_in: 38, dolly_out: 40, crane_up: 42, descend: 40, rise: 42, side_track: 38, push_in: 30, pullback_reveal: 42, establishing_interior: 52, map_overview: 30, map_dive: 34, static_close: 32 };

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
    case 'map_overview': { const h = shot.height || 520; pos = add(P, [0, h * lerp(1, 0.9, ee), h * 0.32 * lerp(1, 0.85, ee)]); tgt = P; break; }
    case 'map_dive': { const h0 = shot.height || 420, h1 = shot.low || 30; const h = h0 * Math.pow(h1 / h0, ee); pos = add(P, [0, h, h * 0.36]); tgt = P; break; }
    default: pos = add(P, polar(yaw, 40, 12)); break;
  }
  return { pos, target: tgt, fov, roll: shot.roll ? shot.roll * Math.sin(u * Math.PI) : 0 };
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
