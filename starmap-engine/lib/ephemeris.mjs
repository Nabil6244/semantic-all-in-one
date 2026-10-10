// Where things really are, for any date: planets and the Moon from astronomy-engine (offline, MIT), and each body's
// orientation from the IAU rotation model (north pole + prime meridian), so Earth turns to the right hour, the Moon keeps
// its near side to Earth, and a landing site is in the light it really had.
//
// Engine axes: J2000 equatorial (EQJ) with y = celestial north: engine [x, y, z] = EQJ [x, z, -y] (a rotation, so
// handedness is kept). Galactic directions use the IAU galactic pole and centre.
import { KM_PER_AU, KM_PER_LY } from './units.mjs';

const A = globalThis.Astronomy ?? await import('astronomy-engine').then((m) => (m.RotationAxis ? m : m.default));
const RAD = Math.PI / 180;

export const eqjToEngine = ([x, y, z]) => [x, z, -y];
const radec = (raDeg, decDeg) => eqjToEngine([Math.cos(decDeg * RAD) * Math.cos(raDeg * RAD), Math.cos(decDeg * RAD) * Math.sin(raDeg * RAD), Math.sin(decDeg * RAD)]);
export const radecToEngine = radec;

const BODIES = { mercury: 'Mercury', venus: 'Venus', earth: 'Earth', moon: 'Moon', mars: 'Mars', jupiter: 'Jupiter', saturn: 'Saturn',
  uranus: 'Uranus', neptune: 'Neptune', pluto: 'Pluto', sun: 'Sun' };
// Jupiter's four large moons: astronomy-engine's JupiterMoons (positions relative to Jupiter, J2000 equatorial).
const JUPITER_MOONS = new Set(['io', 'europa', 'ganymede', 'callisto']);
export const knownBody = (name) => !!BODIES[String(name).toLowerCase()] || JUPITER_MOONS.has(String(name).toLowerCase());

const time = (date) => A.MakeTime(date instanceof Date ? date : new Date(date));

/** Offset (km, engine axes) of a body from its parent at `date`: a planet from the Sun, the Moon from Earth. */
export function offsetOf(name, date) {
  const key = name.toLowerCase();
  if (JUPITER_MOONS.has(key)) {                                  // a Galilean moon, from Jupiter
    const m = A.JupiterMoons(time(date))[key];
    return eqjToEngine([m.x, m.y, m.z]).map((c) => c * KM_PER_AU);
  }
  const b = BODIES[key];
  if (!b) throw new Error(`no ephemeris for ${name}`);
  const t = time(date);
  const v = b === 'Moon' ? A.GeoMoon(t) : A.HelioVector(A.Body[b], t);
  return eqjToEngine([v.x, v.y, v.z]).map((c) => c * KM_PER_AU);
}

/** The body's own axes at `date`, as an engine-space basis {x, y, z} (y = its north pole) plus its prime-meridian angle
 *  W (degrees). Surface longitude L sits at x*cos(W+L) - z*sin(W+L) on the equator (the convention world.surfaceDir uses). */
export function orientationOf(name, date) {
  const b = BODIES[name.toLowerCase()];
  if (!b) return null;
  if (b === 'Earth') {
    // Earth: the pole is celestial north and the turn is Greenwich sidereal time. (The IAU pole formula lands a hair past
    // 90 degrees for dates before 2000; astronomy-engine then reports it from the other side of the pole, which turns the
    // prime meridian round by 180 degrees: noon became midnight. Precession of the pole, 0.2 degrees, is not visible.)
    return { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1], w: A.SiderealTime(time(date)) * 15 };
  }
  const ax = A.RotationAxis(A.Body[b], time(date));
  const P = radec(ax.ra * 15, ax.dec);                         // north pole
  const Z = [0, 1, 0];                                          // celestial north (engine y)
  let Q = [Z[1] * P[2] - Z[2] * P[1], Z[2] * P[0] - Z[0] * P[2], Z[0] * P[1] - Z[1] * P[0]];   // node: Z x P
  const ql = Math.hypot(...Q);
  Q = ql < 1e-9 ? [1, 0, 0] : Q.map((c) => c / ql);
  const zAxis = [Q[1] * P[2] - Q[2] * P[1], Q[2] * P[0] - Q[0] * P[2], Q[0] * P[1] - Q[1] * P[0]];   // Q x P
  return { x: Q, y: P, z: zAxis, w: ax.spin };
}

// ---- the galaxy, as seen from the Sun ------------------------------------------------------------------------------------
export const GALACTIC_NORTH = radec(192.85948, 27.12825);        // IAU galactic north pole (J2000)
export const GALACTIC_CENTRE = radec(266.40499, -28.93617);      // direction of Sgr A*
export const SUN_TO_CENTRE_LY = 26000;

/** Offset of the Sun from the galactic centre (km): opposite the centre's direction. */
export function sunFromGalacticCentre() {
  return GALACTIC_CENTRE.map((c) => -c * SUN_TO_CENTRE_LY * KM_PER_LY);
}
