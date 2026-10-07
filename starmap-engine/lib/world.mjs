// The world: a tree of reference frames built from DATA (the spec's "world" block, later a content pack). The engine knows
// only bodies, parents, offsets and orientations; Earth, the Moon, the Sun and the Milky Way are entries, not code.
//
//   { "id": "moon", "parent": "earth", "radius": {"km": 1737.4}, "offset": {"ephemeris": "moon"}, "rotation": "iau" }
//
// Offsets: {"ephemeris": "mars"} (real position for the current universe date), {"galactic": "sun"} (the Sun 26,000 ly from
// the galactic centre), {"orbit": {"au": 1.52}, "angle_deg": 75} (a fixed circle, for made-up worlds), {"km": [x, y, z]},
// or {"vector": [...], "distance": {...}}. Orientation: "rotation": "iau" (real pole and prime meridian), else spin_deg or
// "face": {"toward": "sun", "point": [lon, lat]}.
//
// Distances are measured ALONG the tree (vec), never by adding up positions from the root: at 26,000 light-years a 64-bit
// number only resolves tens of kilometres, while along the tree a metre near the Moon is still a metre.
import { toKm } from './units.mjs';
import { offsetOf, orientationOf, sunFromGalacticCentre, GALACTIC_NORTH, GALACTIC_CENTRE } from './ephemeris.mjs';

const RAD = Math.PI / 180;
const IDENTITY = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1], w: 0 };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };
const apply = (B, v) => [0, 1, 2].map((i) => B.x[i] * v[0] + B.y[i] * v[1] + B.z[i] * v[2]);

/** Unit direction of a surface point in a body's OWN axes (y = north), matching three.js SphereGeometry's texture layout
 *  (an equirectangular map whose left edge is longitude -180). spinDeg is the prime-meridian angle W. */
export function surfaceDir(lonDeg, latDeg, spinDeg = 0) {
  const phi = (lonDeg + 180 + spinDeg) * RAD, lat = latDeg * RAD;
  return [-Math.cos(phi) * Math.cos(lat), Math.sin(lat), Math.sin(phi) * Math.cos(lat)];
}

/** The Milky Way's own axes in engine coordinates: y = the galactic north pole; +z points from the centre towards the Sun,
 *  so a face-on image whose Sun sits below its centre is turned with that side towards the real Sun. */
export function galacticBasis() {
  const y = GALACTIC_NORTH, toSun = GALACTIC_CENTRE.map((c) => -c);
  const dot = toSun[0] * y[0] + toSun[1] * y[1] + toSun[2] * y[2];
  const z = norm(toSun.map((c, i) => c - y[i] * dot));
  return { x: cross(y, z), y, z, w: 0 };
}

export function buildWorld(spec, { date = new Date('2025-01-01T00:00:00Z') } = {}) {
  const nodes = new Map();
  for (const n of spec || []) {
    if (!n.id) throw new Error('every world entry needs an id');
    if (nodes.has(n.id)) throw new Error(`world entry ${n.id} is listed twice`);
    nodes.set(n.id, { ...n, radiusKm: toKm(n.radius ?? 0) });
  }
  for (const n of nodes.values()) {
    if (n.parent && !nodes.has(n.parent)) throw new Error(`${n.id}: parent ${n.parent} is not in the world`);
  }
  let now = new Date(date);
  const localCache = new Map(), orientCache = new Map();

  const localOf = (id) => {
    if (localCache.has(id)) return localCache.get(id);
    const n = nodes.get(id), o = n.offset || {};
    let v = [0, 0, 0];
    if (o.ephemeris) v = offsetOf(o.ephemeris, now);
    else if (o.galactic) v = sunFromGalacticCentre();
    else if (Array.isArray(o.km)) v = o.km.slice();
    else if (o.orbit != null) {
      const r = toKm(o.orbit), a = (o.angle_deg || 0) * RAD, inc = (o.incline_deg || 0) * RAD;
      v = [r * Math.cos(a), r * Math.sin(a) * Math.sin(inc), r * Math.sin(a) * Math.cos(inc)];
    } else if (o.vector) {
      const d = toKm(o.distance), u = norm(o.vector); v = u.map((c) => c * d);
    }
    localCache.set(id, v);
    return v;
  };
  const chain = (id) => { const out = []; for (let n = nodes.get(id); n; n = n.parent ? nodes.get(n.parent) : null) out.push(n.id); return out; };

  /** From body a's centre to body b's centre (km), along the tree through their nearest common ancestor. */
  const vec = (a, b) => {
    if (a === b) return [0, 0, 0];
    const ca = chain(a), cb = chain(b), common = ca.find((id) => cb.includes(id));
    const v = [0, 0, 0];
    for (const id of ca) { if (id === common) break; const l = localOf(id); v[0] -= l[0]; v[1] -= l[1]; v[2] -= l[2]; }
    for (const id of cb) { if (id === common) break; const l = localOf(id); v[0] += l[0]; v[1] += l[1]; v[2] += l[2]; }
    return v;
  };

  /** The body's axes at the current date: {x, y (north), z, w (prime meridian, deg)}. */
  const orientation = (id) => {
    if (orientCache.has(id)) return orientCache.get(id);
    const n = nodes.get(id);
    if (!n) throw new Error(`unknown body ${id}`);
    let B = IDENTITY;
    if (n.rotation === 'iau') B = orientationOf(n.ephemeris_name || n.id, now) || IDENTITY;
    else if (n.kind === 'galaxy') B = galacticBasis();
    else if (n.spin_deg != null) B = { ...IDENTITY, w: n.spin_deg };
    else if (n.face) {
      const d = vec(id, n.face.toward);
      B = { ...IDENTITY, w: Math.atan2(d[2], -d[0]) / RAD - (n.face.point[0] + 180) };
    }
    orientCache.set(id, B);
    return B;
  };

  /** A point on a body's surface, km from the body's centre, in engine axes. */
  const surfaceOffset = (id, lon, lat, altKm = 0) => {
    const n = nodes.get(id), B = orientation(id);
    return apply(B, surfaceDir(lon, lat, B.w)).map((c) => c * (n.radiusKm + altKm));
  };
  const surfaceNormal = (id, lon, lat) => { const B = orientation(id); return norm(apply(B, surfaceDir(lon, lat, B.w))); };

  /** Coarse absolute position from the root (for far-away bodies and checks only: not precise near anything). */
  const position = (id) => chain(id).reduce((acc, i) => { const l = localOf(i); return [acc[0] + l[0], acc[1] + l[1], acc[2] + l[2]]; }, [0, 0, 0]);

  return {
    nodes, vec, position, orientation, surfaceOffset, surfaceNormal, get: (id) => nodes.get(id),
    get date() { return now; },
    /** Move the whole world to a universe date (positions and rotations recomputed lazily). */
    setTime(d) { const ms = +new Date(d); if (ms !== +now) { now = new Date(ms); localCache.clear(); orientCache.clear(); } },
  };
}

/** An anchored point: { anchor: body id, local: km from that body's centre }. "moon", "moon@lon,lat", "earth+moon". */
export function anchorTarget(world, ref) {
  const s = String(ref);
  if (s.includes('+')) {
    const ids = s.split('+').map((x) => x.trim()), a = ids[0];
    const vs = ids.map((id) => world.vec(a, id));
    return { anchor: a, local: [0, 1, 2].map((i) => vs.reduce((acc, v) => acc + v[i], 0) / vs.length) };
  }
  const [id, at] = s.split('@'); const body = id.trim();
  if (!world.get(body)) throw new Error(`unknown target ${body}`);
  if (!at) return { anchor: body, local: [0, 0, 0] };
  const [lon, lat] = at.split(',').map(Number);
  return { anchor: body, local: world.surfaceOffset(body, lon, lat) };
}

/** For a surface target ("moon@lon,lat"): the local vertical there. null for other targets. */
export function surfaceFrame(world, ref) {
  if (!String(ref).includes('@')) return null;
  const [id, at] = String(ref).split('@');
  const [lon, lat] = at.split(',').map(Number);
  return { normal: world.surfaceNormal(id.trim(), lon, lat) };
}
