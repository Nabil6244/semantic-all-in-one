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
//   orbit_arc      a circular orbit around a body (plane by inclination/node, or "over this site with this heading");
//                  with to_altitude_km it widens or shrinks smoothly (orbit raising/lowering, a coast out to a distant orbit)
//   surface_track  a launch or a landing: along a great circle from/to a surface site -- a launch climbs vertically, then
//                  pitches over (a gravity turn) and is flying level when it reaches orbit; a landing brakes high and
//                  fast, pitches up, hovers and comes straight down on the site
//   transfer       a coast from one body to another. Between two bodies that orbit the same parent (Earth and Mars round
//                  the Sun), when the dates fit one direct coast, it is a two-body Kepler arc solved from the real
//                  positions (Lambert's problem: leave A at the departure time, meet B at the arrival time) -- a model, not
//                  flight data; otherwise (the Moon from the Earth; years of gravity assists the data does not describe) a
//                  smooth illustrated curve from a parking orbit to an arrival orbit. "model": "curve" | "lambert" overrides
//   flyby          a hyperbolic pass by a body: periapsis height, speed far away (v_inf) and the moment of closest
//                  approach give the real bend of the path (Kepler, the body's gravity alone)
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

// ---- two-body mechanics --------------------------------------------------------------------------------------------------
/** Gravitational parameters (km^3/s^2), used only by the modelled generators (Lambert transfers, flybys). A world entry
 *  may give its own "gm"; a generator may override with "gm". */
export const GM = {
  sun: 1.32712440018e11, mercury: 22031.8, venus: 324858.6, earth: 398600.4418, moon: 4902.80, mars: 42828.37,
  jupiter: 1.26686534e8, saturn: 3.7931187e7, uranus: 5.793939e6, neptune: 6.836529e6, pluto: 869.6,
};
export function gmOf(world, id, g = {}) {
  const v = g.gm ?? world.get(id)?.gm ?? GM[id];
  if (!(v > 0)) throw new Error(`no gravitational parameter for ${id} (give the generator or the world entry "gm")`);
  return v;
}
const stumpC = (z) => (z > 1e-8 ? (1 - Math.cos(Math.sqrt(z))) / z : z < -1e-8 ? (Math.cosh(Math.sqrt(-z)) - 1) / -z : 0.5 - z / 24);
const stumpS = (z) => {
  if (z > 1e-8) { const q = Math.sqrt(z); return (q - Math.sin(q)) / (q * q * q); }
  if (z < -1e-8) { const q = Math.sqrt(-z); return (Math.sinh(q) - q) / (q * q * q); }
  return 1 / 6 - z / 120;
};

/** Kepler propagation (universal variables): position after dt seconds from state (r0 km, v0 km/s) about mu. */
export function kepler(r0, v0, dt, mu) {
  const R0 = Math.hypot(...r0), V0 = Math.hypot(...v0), vr0 = dot(r0, v0) / R0, alpha = 2 / R0 - (V0 * V0) / mu, sq = Math.sqrt(mu);
  let x = sq * Math.abs(alpha) * dt;
  if (!(Math.abs(alpha) > 1e-12)) x = sq * dt / R0;                     // near-parabolic start
  for (let i = 0; i < 60; i++) {
    const z = alpha * x * x, C = stumpC(z), S = stumpS(z);
    const F = (R0 * vr0 / sq) * x * x * C + (1 - alpha * R0) * x * x * x * S + R0 * x - sq * dt;
    const dF = (R0 * vr0 / sq) * x * (1 - z * S) + (1 - alpha * R0) * x * x * C + R0;
    const step = F / dF;
    x -= step;
    if (Math.abs(step) < 1e-10 * (Math.abs(x) + 1)) break;
  }
  const z = alpha * x * x, f = 1 - (x * x / R0) * stumpC(z), gg = dt - (x * x * x / sq) * stumpS(z);
  return add(mul(r0, f), mul(v0, gg));
}

/** Lambert's problem (universal variables, zero revolutions): the velocity at r1 that reaches r2 after tof seconds about
 *  mu, travelling prograde about `north` (the short or long way round, whichever is prograde). */
export function lambert(r1, r2, tof, mu, north = [0, 1, 0]) {
  const R1 = Math.hypot(...r1), R2 = Math.hypot(...r2);
  let c = Math.max(-1, Math.min(1, dot(r1, r2) / (R1 * R2))), dth = Math.acos(c);
  if (dot(cross(r1, r2), north) < 0) dth = 2 * Math.PI - dth;
  if (Math.abs(Math.sin(dth)) < 1e-6) dth += dth < Math.PI ? 1e-4 : -1e-4;       // exactly opposite: the plane is undefined
  c = Math.cos(dth);
  const A = Math.sin(dth) * Math.sqrt((R1 * R2) / (1 - c)), sq = Math.sqrt(mu);
  const y = (z) => R1 + R2 + A * (z * stumpS(z) - 1) / Math.sqrt(stumpC(z));
  const F = (z) => { const yz = y(z); return Math.pow(yz / stumpC(z), 1.5) * stumpS(z) + A * Math.sqrt(yz) - sq * tof; };
  let lo = -4 * Math.PI * Math.PI, hi = 4 * Math.PI * Math.PI - 1e-6;
  for (let k = 0; k < 40 && y(lo) >= 0 && F(lo) > 0; k++) lo *= 2;          // a very fast (hyperbolic) transfer
  for (let i = 0; i < 300; i++) {                                        // F rises with z (where y >= 0): bisection is safe
    const mid = (lo + hi) / 2, ym = y(mid);
    if (ym < 0 || F(mid) < 0) lo = mid; else hi = mid;
    if (hi - lo < 1e-12) break;
  }
  const yz = y((lo + hi) / 2), f = 1 - yz / R1, g = A * Math.sqrt(yz / mu);
  return { v1: mul(sub(r2, mul(r1, f)), 1 / g), dth };
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
  if (g.to_altitude_km != null || g.to_radius != null) return widening(world, g, P, r, t0, t1, period, angle(t0));
  const n = Math.max(2, Math.ceil(Math.abs(angle(t1) - angle(t0)) / 360 * (g.samples_per_rev || 96)) + 1);
  const out = [];
  for (let i = 0; i < n; i++) { const t = t0 + (t1 - t0) * (i / (n - 1)); out.push({ utc: t, anchor: g.body, km: orbitPoint(P, r, angle(t)) }); }
  return out;
}

/** An orbit_arc with to_altitude_km (or to_radius): the orbit widens or shrinks smoothly from its starting radius to the
 *  target over the arc (orbit raising or lowering, or a coast out to a distant orbit), and its period runs from period_min
 *  to to_period_min. Illustrated: a series of burns on elliptical orbits is drawn as one smooth spiral in the same plane. */
function widening(world, g, P, r0, t0, t1, period0, a0) {
  const r1 = g.to_radius != null ? toKm(g.to_radius) : world.get(g.body).radiusKm + g.to_altitude_km;
  const period1 = g.to_period_min != null ? g.to_period_min * 60000 : period0;
  const ease = (s) => s * s * (3 - 2 * s);                                       // no kink where it joins the orbits either side
  const revs = Math.abs(t1 - t0) / Math.min(period0, period1);                    // enough samples for the fastest part
  const n = Math.max(2, Math.ceil(revs * (g.samples_per_rev || 96)) + 1, g.samples || 0);
  const out = [];
  let a = a0;
  for (let i = 0; i < n; i++) {
    const s = i / (n - 1), t = t0 + (t1 - t0) * s;
    if (i) {   // advance the angle by this step at the period in the middle of the step
      const mid = ease((i - 0.5) / (n - 1));
      a += 360 * ((t1 - t0) / (n - 1)) / (period0 + (period1 - period0) * mid);
    }
    out.push({ utc: t, anchor: g.body, km: orbitPoint(P, r0 + (r1 - r0) * ease(s), a) });
  }
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

/** Where a launch or a landing is at time fraction k (0 = the start of the track, 1 = its end): [ground, height], both
 *  0..1 -- ground from the site (0) to the far end (1), height from the site's (0) to alt_far_km (1).
 *    launch  (gravity turn): rises off the pad slowly, goes up almost vertically, pitches over and is flying LEVEL as it
 *            reaches orbit height -- its ground speed still building at the end
 *    landing (powered descent): braking -- high, fast and nearly level -- then pitching up as it slows, a hover over the
 *            site at a few hundred metres, and the last part straight down
 *  "profile": "simple" with alt_curve / ground_curve keeps the old power curves. Illustrated shapes, not flight data. */
export function trackProfile(g, k, endPace = 2.5) {
  const landing = g.site_at === 'end';
  if (g.profile === 'simple' || g.alt_curve != null || g.ground_curve != null) {
    const s = landing ? 1 - k : k;
    return [Math.pow(s, g.ground_curve ?? 1.6), 1 - Math.pow(1 - s, g.alt_curve ?? 2.2)];
  }
  if (!landing) {
    // ground: slow off the pad, always speeding up, and at the end endPace times the average ground speed (1.5..3; the
    // generator picks it so the climb ends at orbital speed where the track's numbers allow)
    const q = Math.min(3, Math.max(1.5, endPace)), climb = (x) => (1 - Math.pow(1 - x, 2.2)) * (x / (x + 0.06));
    return [(3 - q) * k * k + (q - 2) * k * k * k, climb(k) / climb(1)];
  }
  const far = g.alt_far_km ?? 100, hover = Math.min(1, Math.min(0.3, 0.02 * far) / Math.max(1e-6, far - (g.alt_site_km || 0)));
  const kv = g.vertical_frac ?? 0.1;                                     // the share of the time spent coming straight down
  if (k >= 1 - kv) { const x = (k - (1 - kv)) / kv; return [0, hover * (1 - x * x * (3 - 2 * x))]; }
  const q = k / (1 - kv);
  return [Math.pow(1 - q, 2), hover + (1 - hover) * Math.pow(1 - q, 1.5)];
}

function genSurfaceTrack(world, g) {
  // site_at "start" = a launch (leaves the site climbing); "end" = a landing (arrives at the site descending). The far end
  // is arc_deg along the heading (launch) or arc_deg back against it (landing), at alt_far_km. The ground track is a great
  // circle on the body at the sample's moment; the shape over time is trackProfile's.
  const landing = g.site_at === 'end';
  const t0 = ms(g.from_utc), t1 = ms(g.to_utc), n = g.samples || (landing ? 120 : 90);
  const [lon, lat] = g.site;
  const siteAlt = g.alt_site_km || 0, farAlt = g.alt_far_km ?? 100, arc = g.arc_deg ?? 10, heading = g.heading_deg ?? 90;
  // a launch reaches orbit at the circular speed at alt_far_km (when the body's gravity is known): how fast it is going
  // at the end, relative to its average over the ground
  let pace = 2.5;
  const mu = g.gm ?? world.get(g.body)?.gm ?? GM[g.body], R = world.get(g.body).radiusKm;
  if (!landing && mu && t1 > t0) pace = Math.sqrt(mu / (R + farAlt)) * ((t1 - t0) / 1000) / Math.max(1e-6, (arc * RAD) * R);
  const out = [];
  for (let i = 0; i < n; i++) {
    const k = i / (n - 1), [d, h] = trackProfile(g, k, pace);
    const [lo, la] = greatCircle(lon, lat, landing ? heading + 180 : heading, arc * d);
    const lla = [lo, la, siteAlt + (farAlt - siteAlt) * h], utc = t0 + (t1 - t0) * k;
    // "track": "space" (default) fixes each point in space at its own moment, so the path joins an orbit cleanly however
    // long ago the launch was; "surface" keeps the path on the turning ground (a landing: it stays on the site afterwards)
    out.push(g.track === 'surface' ? { utc, anchor: g.body, lla }
      : { utc, anchor: g.body, km: atDate(world, utc, () => world.surfaceOffset(g.body, lla[0], lla[1], lla[2])) });
  }
  return out;
}

// ---- transfers ------------------------------------------------------------------------------------------------------------
/** The body two bodies both orbit (Earth and Mars: the Sun), or null (the Moon and the Earth: one orbits the other). */
function commonParent(world, a, b) {
  const pa = world.get(a)?.parent, pb = world.get(b)?.parent;
  return pa && pa === pb && pa !== a && pa !== b ? pa : null;
}

function genTransfer(world, g, ctx = {}) {
  const C = g.model === 'curve' ? null : (g.central || commonParent(world, g.from, g.to));
  const mu = C ? (g.gm ?? world.get(C)?.gm ?? GM[C]) : null;
  if (C && mu && (g.model === 'lambert' || (g.model == null && directFits(world, g, C, mu, ctx)))) return lambertTransfer(world, g, C, ctx);
  if (g.model === 'lambert') throw new Error(`transfer ${g.from} -> ${g.to}: "model": "lambert" needs a central body ("central") with a known gm`);
  return curveTransfer(world, g, ctx);
}

/** Do the dates fit one direct coast? Within about a Hohmann transfer's time between the two distances (0.3x to 1.6x).
 *  A mission that took years with gravity assists the dataset does not describe would come out as a misleading giant
 *  ellipse: it stays an illustrated curve. */
function directFits(world, g, C, mu, { prev, next } = {}) {
  const { A, Bd, t0, t1 } = transferEnds(world, g, prev, next);
  const r1 = Math.hypot(...atDate(world, t0, () => world.vec(C, A))), r2 = Math.hypot(...atDate(world, t1, () => world.vec(C, Bd)));
  const hohmann = Math.PI * Math.sqrt(((r1 + r2) / 2) ** 3 / mu), tof = (t1 - t0) / 1000;
  return tof > 0.3 * hohmann && tof < 1.6 * hohmann;
}

/** Departure and arrival points of a transfer, relative to its from/to bodies (shared by both models). */
function transferEnds(world, g, prev, next) {
  const A = g.from, Bd = g.to;
  const end = g.continue ? endOf(world, prev, A) : null;
  if (g.continue && !end) throw new Error('transfer "continue" needs a previous segment');
  const t0 = ms(g.from_utc ?? end.utcMs), t1 = ms(g.to_utc ?? (g.arrive === 'next' && next ? next.from_utc ?? next.periapsis_utc : undefined));
  if (!Number.isFinite(t1)) throw new Error('transfer needs to_utc (or "arrive": "next" before an orbit_arc with from_utc)');
  return { A, Bd, end, t0, t1 };
}

/** A two-body Kepler arc about C from where the craft leaves A to where it meets B (Lambert's problem). */
function lambertTransfer(world, g, C, { prev, next } = {}) {
  const { A, Bd, end, t0, t1 } = transferEnds(world, g, prev, next);
  const mu = gmOf(world, C, g), north = world.orientation(C).y;
  const cA0 = atDate(world, t0, () => world.vec(C, A)), cB1 = atDate(world, t1, () => world.vec(C, Bd));
  const ab = sub(cB1, atDate(world, t1, () => world.vec(C, A)));
  // leaving: where the previous segment ended, or a parking orbit on the side facing away from the Sun-ward line
  const P0 = end ? end.position : mul(norm(ab), world.get(A).radiusKm + (g.depart_alt_km ?? 300));
  let P3;
  if (g.arrive === 'next' && next) {
    const st = atDate(world, t1, () => (next.kind === 'flyby' ? flybyState(world, next, t1) : orbitArcState(world, next, t1)));
    P3 = st.position;
  } else P3 = mul(norm(sub([0, 0, 0], ab)), world.get(Bd).radiusKm + (g.arrive_alt_km ?? 300));
  const r1 = add(cA0, P0), r2 = add(cB1, P3), tof = (t1 - t0) / 1000;
  const { v1 } = lambert(r1, r2, tof, mu, north);
  const n = g.samples || 160, out = [];
  for (let i = 0; i < n; i++) {
    // denser near both ends, where a beat watches the craft leave and arrive
    const tau = (1 - Math.cos(Math.PI * (i / (n - 1)))) / 2, t = t0 + (t1 - t0) * tau;
    out.push({ utc: t, anchor: C, km: i === 0 ? r1 : i === n - 1 ? r2 : kepler(r1, v1, (t - t0) / 1000, mu) });
  }
  return out;
}

function curveTransfer(world, g, { prev, next } = {}) {
  // A smooth coast from body `from` to body `to`: a cubic curve leaving tangentially and arriving tangentially.
  // Departure: "continue": true leaves from where the previous segment ended, along its direction of travel; otherwise from
  // a circular orbit at depart_deg (measured in the plane of `to`'s motion around `from`, from the from->to line).
  // Arrival: "arrive": "next" joins the next segment's orbit (an orbit_arc around `to`) exactly where it starts; otherwise
  // an orbit at arrive_deg, prograde (+1) or retrograde (-1). follow_target lets the far half of the drawn line ride with the
  // target as it moves, so the line still meets it in later shots; the craft's own position at its own time is unchanged.
  const { A, Bd, end, t0, t1 } = transferEnds(world, g, prev, next);
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
    if (!next || !['orbit_arc', 'flyby'].includes(next.kind) || next.body !== Bd) throw new Error(`transfer "arrive": "next" needs an orbit_arc or a flyby around ${Bd} next`);
    const st = atDate(world, t1, () => (next.kind === 'flyby' ? flybyState(world, next, t1) : orbitArcState(world, next, t1)));
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

// ---- flybys ----------------------------------------------------------------------------------------------------------------
/** The periapsis state of a flyby spec: { rp, vp, P } (P: the plane; u = towards periapsis, v = the motion there). */
function flybyPeri(world, g) {
  const tp = ms(g.periapsis_utc);
  if (!Number.isFinite(tp)) throw new Error('flyby needs periapsis_utc (the moment of closest approach)');
  const mu = gmOf(world, g.body, g), R = world.get(g.body).radiusKm;
  const rp = g.periapsis_km ?? R + (g.periapsis_alt_km ?? R);
  const vinf = g.v_inf_kms ?? 6;
  const P = orbitPlane(world, g.body, g.plane || {}, tp);
  return { tp, mu, rp, vp: Math.sqrt(vinf * vinf + (2 * mu) / rp), P, retro: g.direction === 'retrograde' ? -1 : 1 };
}
/** Where a flyby puts the craft at `when`: { position, direction } relative to its body. */
function flybyState(world, g, when) {
  const F = flybyPeri(world, g), r0 = mul(F.P.u, F.rp), v0 = mul(F.P.v, F.vp * F.retro), dt = (when - F.tp) / 1000;
  const p = kepler(r0, v0, dt, F.mu), q = kepler(r0, v0, dt + 1, F.mu);
  return { position: p, direction: norm(sub(q, p)) };
}
function genFlyby(world, g, { prev } = {}) {
  // a hyperbola about the body: closest at periapsis_utc, periapsis_alt_km above the surface (or periapsis_km from the
  // centre), v_inf_kms far away; its plane like an orbit's ({inclination_deg, node_deg} or {through, heading_deg} -- the
  // point of closest approach and the direction of travel there). from_utc / to_utc bound the drawn pass ("continue": from
  // where the previous segment ended in time).
  const F = flybyPeri(world, g), r0 = mul(F.P.u, F.rp), v0 = mul(F.P.v, F.vp * F.retro);
  const pe = prev && prev.length ? ms(prev[prev.length - 1].utc) : null;
  const t0 = ms(g.from_utc ?? (g.continue && pe != null ? pe : F.tp - 86400000)), t1 = ms(g.to_utc ?? F.tp + (F.tp - t0));
  const n = g.samples || 200, out = [];
  for (let i = 0; i < n; i++) {
    // samples bunched towards periapsis, where the path bends (evenly spaced in an angle-like parameter)
    const x = -1 + 2 * (i / (n - 1)), w = Math.sinh(x * 3) / Math.sinh(3);
    const t = i === 0 ? t0 : i === n - 1 ? t1 : (w < 0 ? F.tp + (F.tp - t0) * w : F.tp + (t1 - F.tp) * w);
    out.push({ utc: t, anchor: g.body, km: kepler(r0, v0, (t - F.tp) / 1000, F.mu) });
  }
  return out;
}

export const GENERATORS = { orbit_arc: genOrbitArc, surface_track: genSurfaceTrack, transfer: genTransfer, flyby: genFlyby };

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

/** The spec's trajectories by id, built on first use (for the camera's follow shots; the same pure function the trajectory
 *  layers use, so the camera looks exactly where the craft is). */
export function trajectoryLookup(world, layers = []) {
  const defs = new Map(layers.filter((L) => L.type === 'trajectory' && L.id).map((L) => [L.id, L]));
  const built = new Map();
  return (id) => {
    if (!built.has(id)) { const d = defs.get(id); built.set(id, d ? createTrajectory(world, d) : null); }
    return built.get(id);
  };
}
