// The pure core (no browser): units across scales, the world as data, precision along the frame tree, real positions and
// rotations checked against history, the two clocks, and the camera's moves and shot options.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { formatDistance, toKm, KM_PER_AU, KM_PER_LY } from '../lib/units.mjs';
import { buildWorld, surfaceDir, anchorTarget } from '../lib/world.mjs';
import { createCamera } from '../lib/camera.mjs';
import { createClock } from '../lib/clock.mjs';

const APOLLO = JSON.parse(fs.readFileSync(new URL('../samples/apollo11-30s.json', import.meta.url), 'utf8'));
const FLIGHT = JSON.parse(fs.readFileSync(new URL('../samples/spike-30s.json', import.meta.url), 'utf8'));
// a made-up world with fixed circles: exact numbers for the precision checks
const FIXED = [
  { id: 'milkyway', kind: 'galaxy', radius: { ly: 52000 } },
  { id: 'sun', parent: 'milkyway', kind: 'star', radius: { km: 696000 }, offset: { vector: [1, 0, 0.35], distance: { ly: 26000 } } },
  { id: 'earth', parent: 'sun', kind: 'body', radius: { km: 6371 }, offset: { orbit: { au: 1 }, angle_deg: 40 } },
  { id: 'moon', parent: 'earth', kind: 'body', radius: { km: 1737.4 }, offset: { orbit: { km: 384400 }, angle_deg: 160, incline_deg: 5 }, face: { toward: 'sun', point: [23.47, 0.67] } },
];
const sub = (a, b) => a.map((v, i) => v - b[i]);
const len = (v) => Math.hypot(...v);
const angleDeg = (a, b) => (Math.acos(Math.min(1, Math.max(-1, a.reduce((s, v, i) => s + v * b[i], 0) / len(a) / len(b)))) * 180) / Math.PI;
const sunElevation = (w, body, lon, lat) => 90 - angleDeg(w.surfaceNormal(body, lon, lat), sub(w.vec(body, 'sun'), w.surfaceOffset(body, lon, lat)));

test('distances read the way a documentary says them, at every scale', () => {
  assert.equal(formatDistance(700), '700 KM');
  assert.equal(formatDistance(384400), '384,400 KM');
  assert.equal(formatDistance(54.6e6), '54.6 MILLION KM');
  assert.equal(formatDistance(5.2 * KM_PER_AU), '5.2 AU');
  assert.equal(formatDistance(26000 * KM_PER_LY), '26,000 LIGHT-YEARS');
  assert.equal(formatDistance(2.5e6 * KM_PER_LY), '2.5 MILLION LIGHT-YEARS');
  assert.equal(toKm({ au: 1 }), KM_PER_AU);
  assert.equal(toKm({ ly: 1 }), KM_PER_LY);
});

test('precision: distances are measured along the frame tree, never through the root', () => {
  const w = buildWorld(FIXED);
  assert.ok(Math.abs(len(w.vec('sun', 'earth')) - KM_PER_AU) < 1e-6, 'Earth 1 AU from the Sun, to the millimetre');
  assert.ok(Math.abs(len(w.vec('earth', 'moon')) - 384400) < 1e-9);
  assert.ok(Math.abs(len(sub(w.position('earth'), w.position('sun'))) - KM_PER_AU) > 1, 'root-based positions are coarse (why vec exists)');
  assert.deepEqual(anchorTarget(w, 'moon').local, [0, 0, 0]);
  assert.ok(Math.abs(len(anchorTarget(w, 'moon@23.47,0.67').local) - 1737.4) < 1e-9);
  assert.ok(Math.abs(len(anchorTarget(w, 'earth+moon').local) - 192200) < 1e-6);
  assert.throws(() => buildWorld([{ id: 'x', parent: 'nowhere' }]), /parent nowhere/);
  assert.throws(() => anchorTarget(w, 'pluto'), /unknown target pluto/);
});

test('"face" turns a body so a surface point faces another body', () => {
  const w = buildWorld(FIXED);
  assert.ok(angleDeg(w.surfaceNormal('moon', 23.47, 0.67), w.vec('moon', 'sun')) < 2);
});

test('real positions and rotations agree with history', () => {
  const w = buildWorld(APOLLO.world);
  w.setTime('1969-07-16T17:22:00Z');                                       // local solar noon at the Cape
  assert.ok(Math.abs(sunElevation(w, 'earth', -80.6, 28.5) - 82.5) < 1.5, 'Sun high over Cape Canaveral at solar noon');
  w.setTime('1969-07-16T05:22:00Z');
  assert.ok(sunElevation(w, 'earth', -80.6, 28.5) < -35, 'and below the horizon at midnight');
  w.setTime('1969-07-20T20:17:40Z');                                       // Apollo 11 lands
  assert.ok(Math.abs(sunElevation(w, 'moon', 23.47, 0.67) - 10.8) < 1.0, 'Tranquility Base: Sun about 10.8 degrees up at landing');
  assert.ok(Math.abs(len(w.vec('earth', 'moon')) - 389456) < 2000, 'Moon about 389,000 km away at landing');
  assert.ok(angleDeg(w.surfaceNormal('moon', 0, 0), w.vec('moon', 'earth')) < 9, 'the near side faces Earth (within libration)');
  assert.ok(Math.abs(len(w.vec('sun', 'earth')) / KM_PER_AU - 1.016) < 0.003, 'Earth near aphelion in July');
  assert.ok(Math.abs(len(w.vec('milkyway', 'sun')) / KM_PER_LY - 26000) < 1, 'the Sun 26,000 ly from the galactic centre');
});

test('the universe clock: holds, fast-forwards smoothly, and reads mission elapsed time', () => {
  const c = createClock(APOLLO.clock);
  assert.equal(c.utc(0).toISOString(), '1969-07-16T13:32:00.000Z');
  assert.equal(c.utc(1.5).toISOString(), '1969-07-16T13:32:01.500Z');            // real time between the first keys
  assert.equal(c.utc(26).toISOString(), '1969-07-20T20:17:40.000Z');
  assert.equal(c.met(26), 'T+ 102:45:40');                                       // the real landing time
  let last = -Infinity;                                                          // 1969 is before 1970: negative timestamps
  for (let t = 0; t <= 30; t += 0.1) { const ms = +c.utc(t); assert.ok(ms >= last, `the clock ran backwards at ${t}`); last = ms; }
  assert.equal(createClock({ utc: '2000-01-01T00:00:00Z' }).utc(10).toISOString(), '2000-01-01T00:00:10.000Z');
  assert.throws(() => createClock({ keys: [{ t: 0, utc: 'soon' }] }), /ISO date/);
});

test('camera: log zoom across 20 orders of magnitude, the subject never dropped, deterministic', () => {
  const w = buildWorld(FLIGHT.world, { date: FLIGHT.clock.utc });
  const cam = createCamera(w, { fov_deg: 40, ...FLIGHT.camera });
  let last = 0;
  for (let t = 0; t <= 30; t += 0.25) { const d = cam(t).distance; assert.ok(d >= last * 0.999, `distance shrank at ${t}s`); last = d; }
  const toBody = (c, id) => sub(w.vec(c.anchor, id), c.position);
  for (let t = 4; t <= 8; t += 0.25) {
    const c = cam(t);
    assert.ok(angleDeg(sub(c.target, c.position), toBody(c, 'moon')) < 20, `Moon left the frame at ${t}s`);
  }
  for (let t = 19; t <= 24; t += 0.25) {
    const c = cam(t);
    if (c.distance < 1000 * KM_PER_LY) assert.ok(angleDeg(sub(c.target, c.position), toBody(c, 'sun')) < 20, `Sun left the frame at ${t}s`);
  }
  assert.equal(cam(0).anchor, 'moon');
  assert.ok(len(cam(0).position) < 5000, 'near the Moon the numbers are hundreds of km, not light-years');
  assert.deepEqual(cam(12.34), cam(12.34));
});

test('shot options: surface shots from the ground, fill, light, and angles in the target\'s own frame', () => {
  const w = buildWorld(APOLLO.world, { date: '1969-07-19T17:21:50Z' });
  // a surface shot: outside the body, horizon level
  const s = createCamera(w, { fov_deg: 40, start: { target: 'moon@23.47,0.67', distance: { km: 500 }, az_deg: 0, el_deg: 20 } })(0);
  assert.ok(len(s.position) > 1737.4);
  assert.ok(angleDeg(s.up, w.surfaceNormal('moon', 23.47, 0.67)) < 1e-3);
  // fill: the Moon spans the asked share of the frame height
  const f = createCamera(w, { fov_deg: 40, start: { target: 'moon', fill: 0.5 } })(0);
  assert.ok(Math.abs(1737.4 / f.distance / Math.tan(20 * Math.PI / 180) - 0.5) < 1e-9);
  // light: front puts the camera on the Sun's side, back on the night side
  const lit = (light) => { const c = createCamera(w, { fov_deg: 40, start: { target: 'moon', fill: 0.5, light, el_deg: 0 } })(0); return angleDeg(c.position, w.vec('moon', 'sun')); };
  assert.ok(lit('front') < 40 && lit('back') > 140, `front ${lit('front')}, back ${lit('back')}`);
  // a galaxy shot measures elevation from the galactic plane
  const g = createCamera(w, { fov_deg: 40, start: { target: 'milkyway', distance: { ly: 1e5 }, el_deg: 90 } })(0);
  assert.ok(angleDeg(g.position, w.orientation('milkyway').y) < 1e-6, 'el 90 = straight above the galactic plane');
  // fit: a pair of bodies framed by their separation
  const pair = createCamera(w, { fov_deg: 40, start: { target: 'earth+moon', fit: 2 } })(0);
  assert.ok(Math.abs(pair.distance - Math.hypot(...w.vec('earth', 'moon')) / Math.tan(20 * Math.PI / 180)) < 1e-6);
  // orbit: the camera circles while the shot holds
  const o = createCamera(w, { fov_deg: 40, start: { target: 'moon', fill: 0.4, orbit_deg_per_s: 10 } });
  assert.ok(Math.abs(angleDeg(o(0).position, o(3).position) - 30) < 0.5);
});
