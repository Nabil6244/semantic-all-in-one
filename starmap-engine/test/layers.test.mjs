// Phase 2, the pure parts: the layer registry (a new layer is one register() call), narration-time timing, trajectories
// (samples, generators, joins, time), orbit planes and surface regions. No browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRegistry, runLayers, defaultLayers } from '../lib/layers.mjs';
import { opacityAt, progressAt, keyed } from '../lib/timing.mjs';
import { createTrajectory, orbitPlane, greatCircle } from '../lib/paths.mjs';
import { regionOutline, regionCentre } from '../lib/surface.mjs';
import { buildWorld } from '../lib/world.mjs';
import { registerBuiltins, BUILTIN_LAYERS } from '../layers/index.mjs';

const read = (f) => JSON.parse(fs.readFileSync(new URL(`../samples/${f}`, import.meta.url), 'utf8'));
const APOLLO2 = read('apollo11-phase2.json');
const MARS = read('mars-test-16s.json');
const len = (v) => Math.hypot(...v);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const angleDeg = (a, b) => Math.acos(Math.min(1, Math.max(-1, a.reduce((s, x, i) => s + x * b[i], 0) / len(a) / len(b)))) * 180 / Math.PI;

test('registry: a new layer type is added by registering it, nothing else', async () => {
  const reg = registerBuiltins(createRegistry());
  assert.deepEqual(reg.types(), ['atmosphere', 'body_labels', 'caption', 'channel_name', 'distance', 'footnote', 'galaxy_guide', 'link', 'marker',
    'mission_clock', 'orbit', 'photo_card', 'pointer', 'region', 'rings', 'spacecraft', 'stat_chip', 'status_badge', 'time_jump', 'title', 'tracker', 'trajectory']);
  // a brand-new type, defined here, used by a spec: the renderer's frame loop runs it with timing applied
  const seen = [];
  reg.register({ type: 'comet_tail', space: 'world', create: (def) => ({ def }), update: (inst, f) => seen.push(['u', f.t, +f.alpha.toFixed(2)]), draw: (inst, f) => seen.push(['d', f.t]) });
  const layers = await reg.instantiate([{ type: 'comet_tail', id: 'c1', start: 2, end: 4, fade_in: 1 }], {});
  for (const t of [1, 2.5, 3.5]) { runLayers(layers, { t }, 'update'); runLayers(layers, { t }, 'draw'); }
  assert.deepEqual(seen, [['u', 1, 0], ['u', 2.5, 0.5], ['d', 2.5], ['u', 3.5, 1], ['d', 3.5]]);
  // mistakes are caught with the layer named
  await assert.rejects(reg.instantiate([{ type: 'nope', id: 'x' }], {}), /layer x: unknown type "nope"/);
  assert.throws(() => reg.register({ type: 'comet_tail', space: 'world', create() {}, draw() {} }), /registered twice/);
  assert.throws(() => reg.register({ type: 'x', space: 'sky', create() {}, draw() {} }), /space must be/);
  // every built-in declares a space and at least one phase
  for (const L of BUILTIN_LAYERS) assert.ok(['world', 'screen'].includes(L.space) && (L.update || L.draw), L.type);
});

test('registry: world layers draw before screen layers, then spec order or z', async () => {
  const reg = createRegistry(), order = [];
  for (const [type, space] of [['a', 'screen'], ['b', 'world'], ['c', 'screen']]) reg.register({ type, space, create: () => type, draw: (i) => order.push(i) });
  const layers = await reg.instantiate([{ type: 'a' }, { type: 'b' }, { type: 'c', z: -1 }], {});
  runLayers(layers, { t: 0 }, 'draw');
  assert.deepEqual(order, ['b', 'c', 'a']);
});

test('Phase 1 specs without layers keep their look; specs with layers get exactly what they list', () => {
  assert.deepEqual(defaultLayers({ title: 'X' }).map((l) => l.type), ['body_labels', 'distance', 'mission_clock', 'title']);
  assert.deepEqual(defaultLayers({ layers: [] }), []);
});

test('timing: narration seconds, fades, held reveals', () => {
  const L = { start: 10, end: 20, fade_in: 1, fade_out: 2 };
  assert.equal(opacityAt(L, 9.9), 0); assert.equal(opacityAt(L, 10.5), 0.5); assert.equal(opacityAt(L, 15), 1);
  assert.equal(opacityAt(L, 19), 0.5); assert.equal(opacityAt(L, 20.1), 0);
  assert.equal(opacityAt({}, 1e6), 1);
  assert.equal(opacityAt({ start: 0, fade_in: 0 }, 0), 1);
  assert.equal(progressAt({ t0: 2, t1: 4 }, 3), 0.5);
  assert.equal(keyed([{ t: 0, v: 0 }, { t: 2, v: 10 }, { t: 5, v: 10 }], 1), 5);
  // pure in t: the same moment after an interruption gives the same state
  assert.equal(opacityAt(L, 12.34), opacityAt(L, 12.34));
});

test('trajectory: samples, Catmull-Rom through them, placed in time by their timestamps', () => {
  const w = buildWorld([{ id: 'earth', radius: { km: 6371 } }]);
  const tr = createTrajectory(w, { id: 't', samples: [
    { utc: '2030-01-01T00:00:00Z', anchor: 'earth', km: [7000, 0, 0] },
    { utc: '2030-01-01T00:10:00Z', anchor: 'earth', km: [0, 0, -7000] },
    { utc: '2030-01-01T00:30:00Z', anchor: 'earth', km: [-7000, 0, 0] }] });
  assert.deepEqual(tr.at(Date.parse('2030-01-01T00:10:00Z')).position, [0, 0, -7000]);    // passes through samples
  assert.equal(tr.at(Date.parse('2030-01-01T00:20:00Z')).index, 1.5);                       // uneven sample spacing
  assert.equal(tr.at(Date.parse('2029-12-31T00:00:00Z')).phase, 'before');
  assert.equal(tr.at(Date.parse('2030-02-01T00:00:00Z')).phase, 'after');
  assert.throws(() => createTrajectory(w, { id: 'bad', samples: [{ utc: '2030-01-01T00:00:00Z', anchor: 'earth', km: [1, 0, 0] }, { utc: '2029-01-01T00:00:00Z', anchor: 'earth', km: [2, 0, 0] }] }), /must increase/);
  assert.throws(() => createTrajectory(w, { id: 'g', generate: [{ kind: 'warp' }] }), /unknown generator "warp"/);
});

test('orbit_arc to_altitude_km: an orbit widens or shrinks smoothly, joining the segment before it without a jump', () => {
  const w = buildWorld([{ id: 'earth', radius: { km: 6371 } }]);
  const tr = createTrajectory(w, { id: 'raise', generate: [
    { kind: 'orbit_arc', body: 'earth', altitude_km: 200, period_min: 90, from_utc: '2030-01-01T00:00:00Z', to_utc: '2030-01-01T03:00:00Z' },
    { kind: 'orbit_arc', body: 'earth', continue: true, to_altitude_km: 60000, period_min: 90, to_period_min: 2600, to_utc: '2030-01-10T00:00:00Z' },
  ] });
  const r = (p) => Math.hypot(...p);
  const S = tr.samples, P = tr.points();
  assert.ok(Math.abs(r(P[0]) - 6571) < 1e-6);
  assert.ok(Math.abs(r(P[P.length - 1]) - 66371) < 1e-6);                                  // ends at the target radius
  for (let i = 1; i < P.length; i++) assert.ok(r(P[i]) >= r(P[i - 1]) - 1e-6, `radius never shrinks while raising (${i})`);
  const join = S.findIndex((s) => s.ms === Date.parse('2030-01-01T03:00:00Z'));
  assert.ok(join > 0 && Math.abs(r(P[join + 1]) - 6571) < 5, 'no jump where the spiral leaves the circular orbit');
  const steps = P.slice(1).map((p, i) => Math.hypot(...p.map((c, k) => c - P[i][k])));
  assert.ok(Math.max(...steps) < 0.2 * 66371, 'no jump anywhere');
  // the period slows towards to_period_min: the last day sweeps a smaller angle than the first
  const ang = (a, b) => Math.acos(Math.max(-1, Math.min(1, (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (r(a) * r(b)))));
  const at = (iso) => tr.at(Date.parse(iso)).position;
  assert.ok(ang(at('2030-01-09T00:00:00Z'), at('2030-01-09T01:00:00Z')) < ang(at('2030-01-01T04:00:00Z'), at('2030-01-01T05:00:00Z')));
});

test('generators: launch, orbit, transfer and lunar orbit join without jumps; landing ends on the site', () => {
  const w = buildWorld(APOLLO2.world, { date: '1969-07-16T13:32:00Z' });
  const csmDef = APOLLO2.layers.find((l) => l.id === 'apollo11_csm'), lmDef = APOLLO2.layers.find((l) => l.id === 'apollo11_lm');
  const csm = createTrajectory(w, csmDef), lm = createTrajectory(w, lmDef);
  const pos = (tr, utc) => { w.setTime(utc); return tr.at(Date.parse(utc)).position; };
  // launch starts on the pad
  const pad = (() => { w.setTime('1969-07-16T13:32:00Z'); return w.surfaceOffset('earth', -80.604, 28.608); })();
  assert.ok(len(sub(pos(csm, '1969-07-16T13:32:00Z'), pad)) < 1, 'lifts off from the pad');
  // continuity across every segment join: a step of 1 s never moves the craft far
  for (const utc of ['1969-07-16T13:43:49Z', '1969-07-16T16:16:16Z', '1969-07-19T17:21:50Z']) {
    const t = Date.parse(utc), a = pos(csm, new Date(t - 1000).toISOString()), b = pos(csm, new Date(t + 1000).toISOString());
    assert.ok(len(sub(a, b)) < 40, `jump at ${utc}: ${len(sub(a, b)).toFixed(1)} km in 2 s`);
  }
  // the drawn path has no jumps either, hours later (a launch track fixed to the turning ground would drift off the orbit)
  w.setTime('1969-07-16T16:10:00Z');
  const P = csm.points(), join = csm.indexAt(Date.parse('1969-07-16T13:43:49Z'));
  for (let i = 1; i < join + 20; i++) assert.ok(len(sub(P[i], P[i - 1])) < 600, `path gap at sample ${i}`);
  // parking orbit altitude is held; lunar orbit is 110 km above the Moon
  w.setTime('1969-07-16T15:00:00Z');
  assert.ok(Math.abs(len(csm.at(Date.parse('1969-07-16T15:00:00Z')).position) - 6371 - 190) < 2);
  w.setTime('1969-07-20T00:00:00Z');
  const fromMoon = sub(csm.at(Date.parse('1969-07-20T00:00:00Z')).position, w.vec('earth', 'moon'));
  assert.ok(Math.abs(len(fromMoon) - 1737.4 - 110) < 1, `lunar orbit radius ${len(fromMoon)}`);
  // the lander touches down exactly at the site at the landing time, and stays there
  w.setTime('1969-07-20T20:17:40Z');
  const site = w.surfaceOffset('moon', 23.47, 0.67);
  assert.ok(len(sub(lm.at(Date.parse('1969-07-20T20:17:40Z')).position, site)) < 0.01);
  w.setTime('1969-07-20T21:00:00Z');
  assert.ok(len(sub(lm.at(Date.parse('1969-07-20T21:00:00Z')).position, w.surfaceOffset('moon', 23.47, 0.67))) < 0.01, 'stays on the turning surface');
});

test('orbit planes: "over this site on this heading" really passes over the site', () => {
  const w = buildWorld(APOLLO2.world, { date: '1969-07-20T20:17:40Z' });
  const P = orbitPlane(w, 'moon', { through: [23.47, 0.67], heading_deg: 268, epoch: '1969-07-20T20:17:40Z' });
  assert.ok(angleDeg(P.u, w.surfaceNormal('moon', 23.47, 0.67)) < 1e-6);
  const ahead = w.surfaceNormal('moon', ...greatCircle(23.47, 0.67, 268, 1));          // one degree along the heading
  const along = P.u.map((c, i) => c * Math.cos(Math.PI / 180) + P.v[i] * Math.sin(Math.PI / 180));
  assert.ok(angleDeg(ahead, along) < 0.01, 'and travels along the heading');
  const Q = orbitPlane(w, 'moon', { inclination_deg: 90, node_deg: 0 });
  assert.ok(angleDeg(Q.n, w.orientation('moon').y) > 89.99, 'inclination 90 = a polar orbit');
});

test('surface regions: circles and polygons on any body', () => {
  const ring = regionOutline({ circle: { lon: 23.47, lat: 0.67, radius_km: 22 } }, 1737.4);
  const w = buildWorld([{ id: 'moon', radius: { km: 1737.4 } }]);
  const c = w.surfaceOffset('moon', 23.47, 0.67);
  for (const [lo, la] of ring) assert.ok(Math.abs(angleDeg(w.surfaceOffset('moon', lo, la), c) * Math.PI / 180 * 1737.4 - 22) < 0.01);
  const mc = regionCentre(ring); assert.ok(Math.abs(mc[0] - 23.47) < 1e-6 && Math.abs(mc[1] - 0.67) < 0.01);
  assert.equal(regionOutline({ polygon: [[0, 0], [10, 0], [10, 10], [0, 0]] }, 1).length, 3);
  assert.throws(() => regionOutline({ polygon: [[0, 0], [1, 1]] }, 1), /at least three/);
});

test('no mission in the renderer: page, layers and lib name no mission, craft or place', () => {
  const files = ['../page.js', ...fs.readdirSync(new URL('../layers/', import.meta.url)).map((f) => `../layers/${f}`),
    ...fs.readdirSync(new URL('../lib/', import.meta.url)).map((f) => `../lib/${f}`)];
  const banned = /apollo|tranquil|eagle|columbia|armstrong|aldrin|jezero|kennedy|artemis|voyager/i;
  for (const f of files) {
    const code = fs.readFileSync(new URL(f, import.meta.url), 'utf8').split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*\*)/.test(l)).join('\n');
    const m = code.match(banned);
    assert.ok(!m, `${f} names "${m && m[0]}" in code`);
  }
});

test('the Mars test mission uses only the same generic layers and builds', () => {
  const reg = registerBuiltins(createRegistry());
  for (const L of MARS.layers) assert.ok(reg.has(L.type), L.type);
  const w = buildWorld(MARS.world, { date: '2031-03-01T06:00:00Z' });
  for (const L of MARS.layers.filter((l) => l.type === 'trajectory')) {
    const tr = createTrajectory(w, L);
    assert.ok(tr.samples.length > 10);
  }
  const lander = createTrajectory(w, MARS.layers.find((l) => l.id === 'lander_path'));
  w.setTime('2031-03-01T11:59:00Z');
  assert.ok(len(sub(lander.at(Date.parse('2031-03-01T11:59:00Z')).position, w.surfaceOffset('mars', 77.45, 18.44))) < 0.01);
});

test('overlay: a line is cut where it goes behind the camera and where it leaves the frame', async () => {
  const { frontPart, clipToFrame } = await import('../lib/overlay.mjs');
  // a camera looking down -z (identity view): z < 0 is in front
  const f = { camera: { matrixWorldInverse: { elements: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] } } };
  assert.equal(frontPart(f, [0, 0, 5], [1, 1, 9]), null, 'all behind');
  const [a, b] = frontPart(f, [0, 0, -10], [0, 0, 10]);
  assert.deepEqual(a, [0, 0, -10]);
  assert.ok(b[2] < 0 && b[2] > -0.01, 'cut just in front of the camera');
  assert.deepEqual(clipToFrame([-100, 50], [300, 50], 200, 100), [[0, 50], [200, 50]]);
  assert.equal(clipToFrame([-100, -50], [-10, -5], 200, 100), null, 'off screen');
});

test('mission clock: its own T-zero, T- before it, a date only as precise as it is known', async () => {
  const { metText, dateText } = await import('../layers/mission_clock.mjs');
  const zero = Date.parse('2027-09-15T12:00:00Z');
  assert.equal(metText(zero - 3600e3, zero), 'T− 01:00:00');
  assert.equal(metText(zero + (102 * 3600 + 45 * 60 + 40) * 1000, zero), 'T+ 102:45:40');
  const day = 86400e3;
  assert.equal(metText(zero + 9.9 * day, zero), 'T+ 237:36:00', 'under ten days: hours, as a launch or Moon landing reads');
  assert.equal(metText(zero + 547.4 * day, zero), 'T+ 547 DAYS', 'a cruise: whole days');
  assert.equal(metText(zero + 12773 * day, zero), 'T+ 34 YEARS 354 DAYS', 'decades: years and days');
  assert.equal(metText(zero + 730.2 * day, zero), 'T+ 730 DAYS', 'just under two years is still days');
  assert.equal(metText(zero + 731 * day, zero), 'T+ 2 YEARS');
  assert.equal(metText(zero - 20 * day, zero), 'T− 20 DAYS', 'a countdown reads the same way');
  const d = new Date('2027-09-15T12:00:00Z');
  assert.equal(dateText(d, 'month'), 'SEP 2027');
  assert.equal(dateText(d, 'year'), '2027');
  assert.equal(dateText(d), '2027-09-15 12:00 UTC');
});

test('mission_clock: through a narration-paced motion the date shown is the craft\'s, not the held universe date', async () => {
  const clock = (await import('../layers/mission_clock.mjs')).default;
  const shown = [];
  const u = { S: 1, measure: () => 100, shadow() {}, noShadow() {}, box() {}, font: () => '' };
  const g = { save() {}, restore() {}, fillText: (t) => shown.push(t) };
  const def = { show: 'utc', date_precision: 'day', motions: [{ start: 80, end: 90, t0: 81.2, t1: 89.8, from_utc: '2016-09-08T23:05:00Z', to_utc: '2018-12-03T00:00:00Z' }] };
  const inst = clock.create(def);
  const frame = (t) => ({ t, date: new Date('2016-09-08T23:05:00Z'), u, g, W: 1920, alpha: 1, mu: (x) => x, claim() {}, clock: { met: () => null } });
  for (const t of [79, 81, 89.9]) clock.draw(inst, frame(t));
  assert.deepEqual(shown, ['8 SEP 2016', '8 SEP 2016', '3 DEC 2018']);
});

test('time jump: fully dark at the cut, clear before and after', async () => {
  const { dipAt } = await import('../layers/time_jump.mjs');
  const def = { at: 10, start: 9.55, end: 11.8 };
  assert.equal(dipAt(def, 9.4), 0);
  assert.equal(dipAt(def, 10), 1);
  assert.equal(dipAt(def, 9.95), 1, 'dark for the frames either side of the cut');
  assert.ok(dipAt(def, 10.3) > 0 && dipAt(def, 10.3) < 1);
  assert.equal(dipAt(def, 11), 0);
});

test('camera follow: a shot on any trajectory looks at the craft, from outside it, and keeps up with a narration-paced motion', async () => {
  const { buildWorld } = await import('../lib/world.mjs');
  const { createCamera } = await import('../lib/camera.mjs');
  const { trajectoryLookup } = await import('../lib/paths.mjs');
  const { motionWhen } = await import('../lib/timing.mjs');
  const world = buildWorld([{ id: 'earth', kind: 'body', radius: { km: 6371 } }], { date: new Date('2030-01-01T00:00:00Z') });
  const traj = { type: 'trajectory', id: 'probe', frame: 'earth', samples: [
    { utc: '2030-01-01T00:00:00Z', anchor: 'earth', km: [7000, 0, 0] }, { utc: '2030-01-01T01:00:00Z', anchor: 'earth', km: [0, 0, 9000] }] };
  const look = trajectoryLookup(world, [traj]);
  const motion = { t0: 0, t1: 10, from_utc: '2030-01-01T00:00:00Z', to_utc: '2030-01-01T01:00:00Z' };
  const cam = createCamera(world, { start: { target: 'earth', follow: { trajectory: 'probe', motion }, distance: { km: 500 }, el_deg: 20 }, moves: [] }, { trajectory: look });
  for (const t of [0, 5, 10]) {
    const c = cam(t), want = look('probe').at(motionWhen(motion, t)).position;
    assert.ok(c.target.every((v, i) => Math.abs(v - want[i]) < 1e-6), `looks at the craft at t=${t}`);
    assert.ok(Math.abs(c.distance - 500) < 1e-6);
    assert.ok(Math.hypot(...c.position) > Math.hypot(...c.target), 'the camera is outside the craft, the planet behind it');
  }
  assert.throws(() => createCamera(world, { start: { target: 'earth', follow: { trajectory: 'nope' }, distance: { km: 9 } } }, { trajectory: look })(0), /follow needs trajectory nope/);
});
