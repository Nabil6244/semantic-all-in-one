// Trajectories: where a spacecraft is at any universe moment, and the path it draws. Pure math, no browser.
//
// The renderer only ever reads SAMPLES -- time-stamped points relative to a body:
//   { "utc": "1969-07-16T16:16:00Z", "anchor": "earth", "km": [x, y, z] }        inertial, engine axes (km from the centre)
//   { "utc": "...", "anchor": "moon", "lla": [lon, lat, alt_km] }                fixed to the turning surface
// Between samples the position is a Catmull-Rom spline through the points (smooth, passes through every sample), placed in
// time by the samples' own timestamps -- so a real flight dataset (e.g. state vectors from JPL Horizons converted to these
// samples) replaces an illustrated one without any renderer change.
//
// GENERATORS build illustrated samples from a few numbers; they are explicitly not flight data:
//   orbit_arc      a circular orbit around a body (plane by inclination/node, or "over this site with this heading")
//   surface_track  a launch or a landing: along a great circle from/to a surface site, climbing or descending
//   transfer       a coast from one body to another (a smooth curve from a parking orbit to an arrival orbit)
import { toKm } from './units.mjs';

const RAD = Math.PI / 180;
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const ms = (u) => (typeof u === 'number' ? u : Date.parse(u));

/** Run fn with the world moved to a date, then put it back. */
function atDate(world, when, fn) {
  const was = world.date;
  world.setTime(new Date(when));
  try { return fn(); } finally { world.setTime(was); }
}

// ---- orbits -------------------------------------------------------------------------------------------------------------
/** The plane of a circular orbit around `body`: { u, v, n, epochMs } with position(angle) = r (cos a u + sin a v), moving
 *  towards +v. Two ways to give it (both generic):
 *    { inclination_deg, node_deg, epoch }       tilted from the body's equator; node measured from the body's x axis
 *    { through: [lon, lat], heading_deg, epoch } passing over a surface site at `epoch`, travelling on that heading
 *                                                (0 = north, 90 = east): "the orbit that flies over the landing site" */
export function orbitPlane(world, body, plane = {}, fallbackEpoch) {
  const epochMs = ms(plane.epoch ?? fallbackEpoch ?? world.date);
  return atDate(world, epochMs, () => {
    const B = world.orientation(body);
    let u, v;
    if (plane.through) {
      const [lon, lat] = plane.through;
      const s = world.surfaceNormal(body, lon, lat);
      const east = norm(cross(B.y, s)), north = cross(s, east), h = (plane.heading_deg ?? 90) * RAD;
      u = s; v = norm(add(mul(north, Math.cos(h)), mul(east, Math.sin(h))));
    } else {
      const om = (plane.node_deg || 0) * RAD, inc = (plane.inclination_deg || 0) * RAD;
      u = norm(add(mul(B.x, Math.cos(om)), mul(B.z, Math.sin(om))));
      const prograde = cross(B.y, u);
      v = norm(add(mul(prograde, Math.cos(inc)), mul(B.y, Math.sin(inc))));
    }
    return { u, v, n: norm(cross(u, v)), epochMs };
  });
}
export const orbitPoint = (P, r, deg) => add(mul(P.u, r * Math.cos(deg * RAD)), mul(P.v, r * Math.sin(deg * RAD)));

/** The radius of an orbit spec: radius {km|au}, or altitude_km above the body's surface. */
export function orbitRadius(world, body, o) {
  if (o.radius != null) return toKm(o.radius);
  return world.get(body).radiusKm + (o.altitude_km || 0);
}

/** A sample's position relative to `body` at the sample's OWN moment (for joining segments). */
function inertial(world, s, body) {
  return atDate(world, ms(s.utc), () => add(world.vec(body, s.anchor), s.km || world.surfaceOffset(s.anchor, s.lla[0], s.lla[1], s.lla[2] || 0)));
}
/** Where the previous segment left off: { at, utcMs, position, velocityDir } relative to `body`. */
function endOf(world, prev, body) {
  if (!prev || prev.length < 2) return null;
  const a = prev[prev.length - 2], b = prev[prev.length - 1];
  const pa = inertial(world, a, body), pb = inertial(world, b, body);
  return { utcMs: ms(b.utc), position: pb, velocityDir: norm(sub(pb, pa)) };
}

function genOrbitArc(world, g, { prev } = {}) {
  // "continue": true takes the plane, radius and starting point from where the previous segment ended (an orbit entered
  // from a launch or a burn), so the craft never jumps
  const end = g.continue ? endOf(world, prev, g.body) : null;
  if (g.continue && !end) throw new Error('orbit_arc "continue" needs a previous segment');
  const t0 = ms(g.from_utc ?? end.utcMs), t1 = ms(g.to_utc);
  let P, r;
  if (end) {
    const u = norm(end.position);
    const v = norm(sub(end.velocityDir, mul(u, dot(end.velocityDir, u))));
    P = { u, v, n: norm(cross(u, v)), epochMs: end.utcMs };
    r = g.altitude_km != null || g.radius != null ? orbitRadius(world, g.body, g) : Math.hypot(...end.position);
  } else {
    P = orbitPlane(world, g.body, g.plane, t0);
    r = orbitRadius(world, g.body, g);
  }
  const period = (g.period_min || 120) * 60000;
  const angle = (t) => (end ? 0 : (g.phase_deg || 0)) + 360 * (t - P.epochMs) / period;
  const n = Math.max(2, Math.ceil(Math.abs(angle(t1) - angle(t0)) / 360 * (g.samples_per_rev || 96)) + 1);
  const out = [];
  for (let i = 0; i < n; i++) { const t = t0 + (t1 - t0) * (i / (n - 1)); out.push({ utc: t, anchor: g.body, km: orbitPoint(P, r, angle(t)) }); }
  return out;
}

/** Where an orbit_arc spec puts the craft at `when`: { position, direction } relative to its body. */
function orbitArcState(world, g, when) {
  const P = orbitPlane(world, g.body, g.plane, ms(g.from_utc));
  const r = orbitRadius(world, g.body, g), a = (g.phase_deg || 0) + 360 * (when - P.epochMs) / ((g.period_min || 120) * 60000);
  return { position: orbitPoint(P, r, a), direction: norm(add(mul(P.u, -Math.sin(a * RAD)), mul(P.v, Math.cos(a * RAD)))) };
}

// ---- launches and landings ------------------------------------------------------------------------------------------------
/** The point `arcDeg` along a great circle from (lon, lat) on a heading (degrees from north, clockwise). */
export function greatCircle(lon, lat, headingDeg, arcDeg) {
  const p1 = lat * RAD, d = arcDeg * RAD, h = headingDeg * RAD;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(h));
  const l2 = lon * RAD + Math.atan2(Math.sin(h) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [((l2 / RAD + 540) % 360) - 180, p2 / RAD];
}

function genSurfaceTrack(world, g) {
  // site_at "start" = a launch (leaves the site climbing); "end" = a landing (arrives at the site descending). The far end
  // is arc_deg along the heading (launch) or arc_deg back against it (landing), at alt_far_km. The ground track is a great
  // circle on the body at the sample's moment.
  const t0 = ms(g.from_utc), t1 = ms(g.to_utc), n = g.samples || 80;
  const [lon, lat] = g.site, landing = g.site_at === 'end';
  const siteAlt = g.alt_site_km || 0, farAlt = g.alt_far_km ?? 100, arc = g.arc_deg ?? 10, heading = g.heading_deg ?? 90;
  const climb = (s) => 1 - Math.pow(1 - s, g.alt_curve ?? 2.2);           // steep near the site, levelling off far away
  const ground = (s) => Math.pow(s, g.ground_curve ?? 1.6);                // slow over the ground near the site
  const out = [];
  for (let i = 0; i < n; i++) {
    const k = i / (n - 1), s = landing ? 1 - k : k;                       // s: 0 at the site, 1 at the far end
    const [lo, la] = greatCircle(lon, lat, landing ? heading + 180 : heading, arc * ground(s));
    const lla = [lo, la, siteAlt + (farAlt - siteAlt) * climb(s)], utc = t0 + (t1 - t0) * k;
    // "track": "space" (default) fixes each point in space at its own moment, so the path joins an orbit cleanly however
    // long ago the launch was; "surface" keeps the path on the turning ground (a landing: it stays on the site afterwards)
    out.push(g.track === 'surface' ? { utc, anchor: g.body, lla }
      : { utc, anchor: g.body, km: atDate(world, utc, () => world.surfaceOffset(g.body, lla[0], lla[1], lla[2])) });
  }
  return out;
}

// ---- transfers ------------------------------------------------------------------------------------------------------------
function genTransfer(world, g, { prev, next } = {}) {
  // A smooth coast from body `from` to body `to`: a cubic curve leaving tangentially and arriving tangentially.
  // Departure: "continue": true leaves from where the previous segment ended, along its direction of travel; otherwise from
  // a circular orbit at depart_deg (measured in the plane of `to`'s motion around `from`, from the from->to line).
  // Arrival: "arrive": "next" joins the next segment's orbit (an orbit_arc around `to`) exactly where it starts; otherwise
  // an orbit at arrive_deg, prograde (+1) or retrograde (-1). follow_target lets the far half of the drawn line ride with the
  // target as it moves, so the line still meets it in later shots; the craft's own position at its own time is unchanged.
  const A = g.from, Bd = g.to;
  const end = g.continue ? endOf(world, prev, A) : null;
  if (g.continue && !end) throw new Error('transfer "continue" needs a previous segment');
  const t0 = ms(g.from_utc ?? end.utcMs), t1 = ms(g.to_utc ?? (g.arrive === 'next' && next ? next.from_utc : undefined));
  if (!Number.isFinite(t1)) throw new Error('transfer needs to_utc (or "arrive": "next" before an orbit_arc with from_utc)');
  const n = g.samples || 160;
  const ab0 = atDate(world, t0, () => world.vec(A, Bd)), ab1 = atDate(world, t1, () => world.vec(A, Bd));
  const e1 = norm(ab1);
  let nrm = cross(ab0, ab1);
  if (Math.hypot(...nrm) < 1e-9 * Math.hypot(...ab0) * Math.hypot(...ab1)) nrm = world.orientation(A).y;
  nrm = norm(nrm);
  const e2 = norm(cross(nrm, e1));
  const inPlane = (deg) => add(mul(e1, Math.cos(deg * RAD)), mul(e2, Math.sin(deg * RAD)));
  const tangent = (deg, dir) => mul(add(mul(e1, -Math.sin(deg * RAD)), mul(e2, Math.cos(deg * RAD))), dir);
  let P0, T0, P3, T3;
  if (end) { P0 = end.position; T0 = end.velocityDir; }
  else { const da = g.depart_deg ?? 180; P0 = mul(inPlane(da), world.get(A).radiusKm + (g.depart_alt_km ?? 300)); T0 = tangent(da, 1); }
  if (g.arrive === 'next') {
    if (!next || next.kind !== 'orbit_arc' || next.body !== Bd) throw new Error(`transfer "arrive": "next" needs an orbit_arc around ${Bd} next`);
    const st = atDate(world, t1, () => orbitArcState(world, next, t1));
    P3 = add(ab1, st.position); T3 = st.direction;
  } else {
    const aa = g.arrive_deg ?? 180;
    P3 = add(ab1, mul(inPlane(aa), world.get(Bd).radiusKm + (g.arrive_alt_km ?? 100))); T3 = tangent(aa, g.arrive_dir ?? -1);
  }
  const L = Math.hypot(...sub(P3, P0));
  const P1 = add(P0, mul(T0, L * (g.bulge ?? 0.5))), P2 = sub(P3, mul(T3, L * (g.arrive_bulge ?? 0.25)));
  const bez = (s) => { const q = 1 - s; return [0, 1, 2].map((i) => q * q * q * P0[i] + 3 * q * q * s * P1[i] + 3 * q * s * s * P2[i] + s * s * s * P3[i]); };
  // arc-length table: equal steps of travelled distance, then the coast's speed profile (fast after departure, slowing)
  const M = 400, len = [0]; let prevP = bez(0);
  for (let i = 1; i <= M; i++) { const p = bez(i / M); len.push(len[i - 1] + Math.hypot(...sub(p, prevP))); prevP = p; }
  const atLength = (f) => { const want = f * len[M]; let i = 1; while (i < M && len[i] < want) i++; const k = (want - len[i - 1]) / ((len[i] - len[i - 1]) || 1); return (i - 1 + k) / M; };
  const travelled = (tau) => 1 - Math.pow(1 - tau, g.speed_curve ?? 1.7);
  const out = [];
  for (let i = 0; i < n; i++) {
    const tau = i / (n - 1), s = atLength(travelled(tau));
    const smp = { utc: t0 + (t1 - t0) * tau, anchor: A, km: bez(s) };
    if (g.follow_target !== false) {
      const w = Math.min(1, Math.max(0, (s - 0.5) / 0.5)); smp.follow = { body: Bd, weight: w * w * (3 - 2 * w), ref: ab1 };
    }
    out.push(smp);
  }
  return out;
}

export const GENERATORS = { orbit_arc: genOrbitArc, surface_track: genSurfaceTrack, transfer: genTransfer };

// ---- the trajectory object ------------------------------------------------------------------------------------------------
const catmull = (p0, p1, p2, p3, u) => {
  const u2 = u * u, u3 = u2 * u;
  return [0, 1, 2].map((i) => 0.5 * (2 * p1[i] + (-p0[i] + p2[i]) * u + (2 * p0[i] - 5 * p1[i] + 4 * p2[i] - p3[i]) * u2 + (-p0[i] + 3 * p1[i] - 3 * p2[i] + p3[i]) * u3));
};

/** def: { id, frame?, samples?: [...], generate?: [{kind, ...}] } -> a trajectory. Positions are km in the FRAME body's
 *  coordinates (default: the first sample's anchor), re-evaluated for the world's current date. */
export function createTrajectory(world, def) {
  let raw = (def.samples || []).map((s) => ({ ...s }));
  const gens = [].concat(def.generate || []);
  for (const [k, g] of gens.entries()) {
    const fn = GENERATORS[g.kind];
    if (!fn) throw new Error(`trajectory ${def.id}: unknown generator "${g.kind}" (known: ${Object.keys(GENERATORS).join(', ')})`);
    const s = fn(world, g, { prev: raw, next: gens[k + 1] });
    if (raw.length && s.length && ms(s[0].utc) <= ms(raw[raw.length - 1].utc)) s.shift();      // segments share an endpoint
    raw = raw.concat(s);
  }
  if (raw.length < 2) throw new Error(`trajectory ${def.id}: needs at least two samples`);
  const samples = raw.map((s) => {
    if (!world.get(s.anchor)) throw new Error(`trajectory ${def.id}: unknown anchor ${s.anchor}`);
    if (!s.km && !s.lla) throw new Error(`trajectory ${def.id}: every sample needs km or lla`);
    return { ...s, ms: ms(s.utc) };
  });
  for (let i = 1; i < samples.length; i++) if (!(samples[i].ms > samples[i - 1].ms)) throw new Error(`trajectory ${def.id}: sample times must increase (sample ${i})`);
  const frame = def.frame || samples[0].anchor;
  const t0 = samples[0].ms, t1 = samples[samples.length - 1].ms;

  let cacheKey = null, cache = null;
  /** Every sample's position in the frame body's coordinates, for the world's current date. */
  const points = () => {
    const key = +world.date;
    if (key === cacheKey) return cache;
    const toAnchor = new Map();
    cache = samples.map((s) => {
      if (!toAnchor.has(s.anchor)) toAnchor.set(s.anchor, world.vec(frame, s.anchor));
      let p = add(toAnchor.get(s.anchor), s.km || world.surfaceOffset(s.anchor, s.lla[0], s.lla[1], s.lla[2] || 0));
      if (s.follow && s.follow.weight > 0) p = add(p, mul(sub(world.vec(s.anchor, s.follow.body), s.follow.ref), s.follow.weight));
      return p;
    });
    cacheKey = key;
    return cache;
  };
  const indexAt = (when) => {
    if (when <= t0) return 0;
    if (when >= t1) return samples.length - 1;
    let lo = 0, hi = samples.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (samples[mid].ms <= when) lo = mid; else hi = mid; }
    return lo + (when - samples[lo].ms) / (samples[hi].ms - samples[lo].ms);
  };
  /** The point at a fractional sample index (Catmull-Rom between samples). */
  const pointAtIndex = (x) => {
    const P = points(), last = P.length - 1;
    const i = Math.min(last - 1, Math.max(0, Math.floor(x))), u = Math.min(1, Math.max(0, x - i));
    return catmull(P[Math.max(0, i - 1)], P[i], P[i + 1], P[Math.min(last, i + 2)], u);
  };
  return {
    id: def.id, frame, samples, t0, t1, points, indexAt, pointAtIndex,
    /** Where the craft is at universe time `when` (ms or Date): { position, direction, index, phase } in frame coordinates.
     *  phase: "before" (not launched yet), "flying", "after" (the path has ended). */
    at(when) {
      const w = +when, x = indexAt(w);
      const p = pointAtIndex(x), q = pointAtIndex(Math.min(samples.length - 1, x + 0.05)), r = pointAtIndex(Math.max(0, x - 0.05));
      const d = sub(q, r);
      return { position: p, direction: Math.hypot(...d) > 0 ? norm(d) : null, index: x, phase: w < t0 ? 'before' : w > t1 ? 'after' : 'flying' };
    },
    /** A smooth polyline through the samples from index a to b (frame coordinates), `per` points per sample gap. */
    polyline(a = 0, b = samples.length - 1, per = 4) {
      const out = [];
      if (b <= a) return out;
      const steps = Math.max(1, Math.ceil((b - a) * per));
      for (let k = 0; k <= steps; k++) out.push(pointAtIndex(a + (b - a) * (k / steps)));
      return out;
    },
  };
}
