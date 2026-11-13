// Life around the city, all pure and decided by the plan (same world + story + seed = same film): farm fields on open
// land near the city, ships on the water, how far each water point is from the shore (shallow turquoise edge, foam),
// and what an event brings on screen (a siege camp with engines and banners, a fleet on the water, fire and smoke).
// Node plans them; the page only draws them.
import { rng, hash, noise2 } from './growth.mjs';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const isWet = (T, k) => T.hs[k] < 0 || T.ls[k] > -1e3;

/** Distance (m) from each coarse-grid vertex to the nearest land vertex: 0 on land, larger further out to sea.
 *  n*n Float32, the terrain's own vertex grid (row 0 north). Two-pass chamfer. */
export function shoreDistance(T) {
  const { n, sp } = T, D = new Float32Array(n * n), INF = 1e9, dg = sp * Math.SQRT2;
  for (let k = 0; k < n * n; k++) D[k] = isWet(T, k) ? INF : 0;
  const relax = (k, k2, w) => { if (D[k2] + w < D[k]) D[k] = D[k2] + w; };
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const k = j * n + i; if (!D[k]) continue;
    if (i > 0) relax(k, k - 1, sp);
    if (j > 0) { relax(k, k - n, sp); if (i > 0) relax(k, k - n - 1, dg); if (i < n - 1) relax(k, k - n + 1, dg); }
  }
  for (let j = n - 1; j >= 0; j--) for (let i = n - 1; i >= 0; i--) {
    const k = j * n + i; if (!D[k]) continue;
    if (i < n - 1) relax(k, k + 1, sp);
    if (j < n - 1) { relax(k, k + n, sp); if (i < n - 1) relax(k, k + n + 1, dg); if (i > 0) relax(k, k + n - 1, dg); }
  }
  for (let k = 0; k < n * n; k++) if (D[k] >= INF) D[k] = 5000;
  return D;
}

/** Shore distance at (x, z) (nearest vertex). */
export function shoreAt(T, D, x, z) {
  const i = Math.round((x - T.x0) / T.sp), j = Math.round((z - T.x0) / T.sp);
  if (i < 0 || j < 0 || i >= T.n || j >= T.n) return 5000;   // past the world's edge: open water or land, far from any shore
  return D[j * T.n + i];
}

/** Sea lanes: straight runs over open water (at least `clear` m from any shore), ships sail them back and forth.
 *  Each: {ax, az, bx, bz, len, speed (m/s), phase, size}. Ordered: the first ones appear first as the city grows. */
export function makeShips(T, D, { seed = 5, count = 140, clear = 45 } = {}) {
  const R = rng(seed), out = [], lim = T.half - 30;
  for (let tries = 0; tries < count * 40 && out.length < count; tries++) {
    const x = (R() * 2 - 1) * lim, z = (R() * 2 - 1) * lim;
    if (shoreAt(T, D, x, z) < clear * 1.5) continue;
    const a = R() * Math.PI * 2, dx = Math.cos(a), dz = Math.sin(a);
    const reach = (sgn) => {   // how far the lane runs each way before it nears a shore or the world's edge
      let s = 0;
      while (s < 1400) { const px = x + dx * sgn * (s + 20), pz = z + dz * sgn * (s + 20); if (Math.abs(px) > lim || Math.abs(pz) > lim || shoreAt(T, D, px, pz) < clear) break; s += 20; }
      return s;
    };
    const f = reach(1), b = reach(-1), len = f + b;
    if (len < 260) continue;
    out.push({ ax: x - dx * b, az: z - dz * b, bx: x + dx * f, bz: z + dz * f, len, speed: 9 + R() * 9, phase: R() * len * 2, size: 0.75 + R() * 0.7 });
  }
  return out;
}

/** How many ships sail at a population: a village has a few boats, a great port a crowded sea. */
export const shipsFor = (pop, total) => clamp(pop / 2500, Math.min(3, total), total);

/** Where a ship of a lane is at time t: position and heading (it turns round at each end). */
export function shipAt(s, t) {
  const L = s.len, u = ((t * s.speed + s.phase) % (2 * L) + 2 * L) % (2 * L), back = u > L, k = back ? 2 - u / L : u / L;
  const e = k * k * (3 - 2 * k) * 0.3 + k * 0.7;   // eases off near the ends so the turn is not a snap
  const x = s.ax + (s.bx - s.ax) * e, z = s.az + (s.bz - s.az) * e;
  const ang = Math.atan2(s.bz - s.az, s.bx - s.ax) + (back ? Math.PI : 0);
  return { x, z, ang };
}

/** Lowest rank in buckets of `B` metres: the first year anything of the city stands there. */
function rankBuckets(lots, B) {
  const m = new Map();
  for (const l of lots) { const k = Math.floor(l.x / B) * 100003 + Math.floor(l.z / B); if (!(m.get(k) <= l.rank)) m.set(k, l.rank); }
  return (x0, z0, x1, z1) => {
    let best = Infinity;
    for (let i = Math.floor(x0 / B); i <= Math.floor(x1 / B); i++) for (let j = Math.floor(z0 / B); j <= Math.floor(z1 / B); j++) {
      const r = m.get(i * 100003 + j); if (r !== undefined && r < best) best = r;
    }
    return best;
  };
}

export const FIELD_COLORS = [0xb8b06a, 0xc9b36e, 0x9fae5c, 0x8c9e52, 0xa58f5c, 0xd1c07a, 0x7e9a4f, 0xb59a63];

/**
 * Farm fields on gentle open land. A field is tilled once the city has houses within ~600 m (`near`) and gives way when
 * the city builds over it (`over`). Each: {x, z, y, h (box height), w, d, rot, near, over, c (colour index), stripes}.
 */
export function makeFields(T, lots, { seed = 9, density = 1, max = 9000 } = {}) {
  if (!lots.length || density <= 0.02) return [];
  const R = rng(seed), out = [], near = rankBuckets(lots, 100), over = rankBuckets(lots, 30), lim = T.half - 60, step = 62;
  for (let z = -lim; z < lim; z += step) for (let x = -lim; x < lim; x += step) {
    if (R() > 0.78 * density) continue;
    const cx = x + (R() - 0.5) * step * 0.5, cz = z + (R() - 0.5) * step * 0.5;
    const w = 34 + R() * 34, d = 24 + R() * 26, rot = (noise2(cx, cz, 900, seed) - 0.5) * Math.PI * 1.4 + (R() - 0.5) * 0.12;
    const c = Math.cos(rot), s = Math.sin(rot), ys = [];
    let bad = false;
    for (const [u, v] of [[0, 0], [1, 1], [1, -1], [-1, 1], [-1, -1]]) {
      const px = cx + c * u * w / 2 - s * v * d / 2, pz = cz + s * u * w / 2 + c * v * d / 2;
      const y = T.heightAt(px, pz); if (y < 2 || T.waterAt?.(px, pz)) { bad = true; break; } ys.push(y);
    }
    if (bad) continue;
    const top = Math.max(...ys), low = Math.min(...ys);
    if (top - low > Math.max(w, d) * 0.06) continue;   // too steep to plough
    const n = near(cx - 600, cz - 600, cx + 600, cz + 600); if (!Number.isFinite(n)) continue;
    const r = Math.max(w, d) / 2 + 12, o = over(cx - r, cz - r, cx + r, cz + r);
    if (o <= n) continue;   // built over before it was ever farmed
    out.push({ x: cx, z: cz, y: top + 0.25, h: top - low + 0.9, w, d, rot, near: n, over: o, c: Math.floor(R() * FIELD_COLORS.length), stripes: 5 + Math.floor(R() * 9) });
    if (out.length >= max) return out;
  }
  return out;
}

/** Trees standing on a field are cleared when it is first tilled. */
export function clearTreesForFields(trees, fields) {
  const B = 80, grid = new Map();
  fields.forEach((f, i) => { const k = Math.floor(f.x / B) * 100003 + Math.floor(f.z / B); (grid.get(k) || grid.set(k, []).get(k)).push(i); });
  for (const t of trees) {
    const i0 = Math.floor(t.x / B), j0 = Math.floor(t.z / B);
    for (let i = i0 - 1; i <= i0 + 1; i++) for (let j = j0 - 1; j <= j0 + 1; j++) for (const fi of grid.get(i * 100003 + j) || []) {
      const f = fields[fi], dx = t.x - f.x, dz = t.z - f.z, c = Math.cos(f.rot), s = Math.sin(f.rot);
      const u = dx * c + dz * s, v = -dx * s + dz * c;
      if (Math.abs(u) < f.w / 2 + 3 && Math.abs(v) < f.d / 2 + 3 && f.near < t.rank) t.rank = f.near;
    }
  }
  return trees;
}

/** Field visibility at `need` houses: 0..1 (rises as the city nears, goes when it is built over). */
export function fieldShown(f, need, ramp) {
  return clamp((need - f.near) / ramp, 0, 1) * clamp((f.over - need) / ramp, 0, 1);
}

/**
 * What an event shows. A siege: the attackers' camp at the event's focus (tents, siege engines that fire, banners) and,
 * when there is water within reach, a fleet; fire and quake are drawn in the page from the event's centre and radius.
 * Returns {camp: [[x, y, z, rot, kind]], fleet: [[x, z, rot]]}; kind 0 tent, 1 engine, 2 banner.
 */
export function planEvent(T, D, ev, { seed = 3 } = {}) {
  const R = rng(seed + Math.round(ev.x * 7 + ev.z * 13)), camp = [], fleet = [];
  if (ev.kind !== 'siege') return { camp, fleet };
  const r = clamp(ev.r * 0.7, 120, 700), want = [90, 12, 14];
  for (let kind = 0; kind < 3; kind++) {
    let n = 0;
    for (let tries = 0; tries < want[kind] * 30 && n < want[kind]; tries++) {
      const a = R() * Math.PI * 2, d = Math.sqrt(R()) * r * (kind === 1 ? 0.6 : 1), x = ev.x + Math.cos(a) * d, z = ev.z + Math.sin(a) * d;
      const y = T.heightAt(x, z); if (y < 1.5 || T.waterAt?.(x, z) || T.slopeAt(x, z, 10) > 0.25) continue;
      camp.push([x, y, z, R() * Math.PI * 2, kind]); n++;
    }
  }
  // the fleet: open water nearest the camp (up to ~3.5 km away), ships at least 30 m apart
  const cand = [];
  for (let j = 0; j < T.n; j += 2) for (let i = 0; i < T.n; i += 2) {
    const k = j * T.n + i; if (D[k] < 50) continue;
    const x = T.x0 + i * T.sp, z = T.x0 + j * T.sp, d = Math.hypot(x - ev.x, z - ev.z);
    if (d < 3500) cand.push([d, x, z]);
  }
  cand.sort((a, b) => a[0] - b[0]);
  if (cand.length) {
    const cx = cand[0][1], cz = cand[0][2], ang = Math.atan2(ev.z - cz, ev.x - cx);
    for (let tries = 0; tries < 900 && fleet.length < 60; tries++) {
      const x = cx + (R() - 0.5) * 900, z = cz + (R() - 0.5) * 900;
      if (shoreAt(T, D, x, z) < 40 || fleet.some(([fx, fz]) => Math.hypot(fx - x, fz - z) < 30)) continue;
      fleet.push([x, z, ang + (R() - 0.5) * 0.5]);
    }
  }
  return { camp, fleet };
}

/** Points where streets cross a wall's line: the wall gets a gatehouse there. Main and secondary streets only. */
export function wallGates(points, roads, { minGap = 120 } = {}) {
  const out = [];
  const cross = (p, p2, q, q2) => {
    const r = [p2[0] - p[0], p2[1] - p[1]], s = [q2[0] - q[0], q2[1] - q[1]], den = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(den) < 1e-9) return null;
    const qp = [q[0] - p[0], q[1] - p[1]], t = (qp[0] * s[1] - qp[1] * s[0]) / den, u = (qp[0] * r[1] - qp[1] * r[0]) / den;
    return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? [p[0] + r[0] * t, p[1] + r[1] * t] : null;
  };
  for (const rd of roads) {
    if (rd.c > 2) continue;
    for (let i = 0; i + 1 < points.length; i++) for (let k = 0; k + 1 < rd.p.length; k++) {
      const hit = cross(points[i], points[i + 1], rd.p[k], rd.p[k + 1]);
      if (hit && !out.some(([x, z]) => Math.hypot(x - hit[0], z - hit[1]) < minGap)) out.push(hit);
    }
  }
  return out;
}

/** Fire / smoke seeds for an event: fixed points over its disc (frac = distance from the centre / radius). A siege's
 *  seeds are where its guns land: a band between the camp and the city centre (the world's origin). */
export function eventSeeds(ev, n = 420) {
  const out = [];
  let cx = ev.x, cz = ev.z, r = ev.r;
  if (ev.kind === 'siege') {
    const d = Math.hypot(ev.x, ev.z) || 1;
    cx = ev.x - (ev.x / d) * Math.min(d * 0.8, ev.r + 350); cz = ev.z - (ev.z / d) * Math.min(d * 0.8, ev.r + 350); r = ev.r * 0.7;
  }
  for (let i = 0; i < n; i++) {
    const a = hash(i, 101 + (ev.year | 0)) * Math.PI * 2, f = Math.sqrt(hash(i, 202 + (ev.year | 0)));
    out.push({ x: cx + Math.cos(a) * f * r, z: cz + Math.sin(a) * f * r, f, h: hash(i, 303) });
  }
  return out;
}

/** Where the camera looks during an event: a siege is framed between the camp and the walls it attacks. */
export function eventFocus(ev) {
  if (ev.kind !== 'siege') return { x: ev.x, z: ev.z };
  const d = Math.hypot(ev.x, ev.z) || 1, k = Math.min(d * 0.35, ev.r * 0.5 + 120) / d;
  return { x: ev.x - ev.x * k, z: ev.z - ev.z * k };
}
