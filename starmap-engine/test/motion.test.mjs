// Motion: the camera holds while a craft moves, the clock keeps its pace through a run of beats, and the generated paths
// have plausible shapes (a launch goes up then over, a landing comes straight down, a flyby bends round its body, a
// transfer between planets meets its target). Pure math, no browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { buildWorld } from '../lib/world.mjs';
import { createCamera } from '../lib/camera.mjs';
import { createClock } from '../lib/clock.mjs';
import { createTrajectory, trackProfile, kepler, lambert, trajectoryLookup } from '../lib/paths.mjs';

const bodies = JSON.parse(fs.readFileSync(new URL('../../starmap/catalog/bodies.json', import.meta.url), 'utf8')).world;
const len = (v) => Math.hypot(...v);
const sub = (a, b) => a.map((x, i) => x - b[i]);
const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
const angleDeg = (a, b) => (Math.acos(Math.min(1, Math.max(-1, dot(a, b) / len(a) / len(b)))) * 180) / Math.PI;

test('clock: a run of fast-forwards keeps its pace through the keys between them (no stop at a beat boundary)', () => {
  const keys = [{ t: 0, utc: '1969-07-16T13:32:00Z' }, { t: 8, utc: '1969-07-16T13:44:00Z' }, { t: 15, utc: '1969-07-16T14:10:00Z' }];
  const c = createClock({ keys }), rate = (t) => (+c.utc(t + 0.01) - +c.utc(t - 0.01)) / 0.02;
  assert.equal(c.utc(8).toISOString(), '1969-07-16T13:44:00.000Z');              // still passes through every key
  assert.ok(rate(8) > 0.5 * Math.min((12 * 60e3) / 8, (26 * 60e3) / 7), 'time keeps running at the beat boundary');
  assert.ok(Math.abs(rate(7.99) - rate(8.01)) / rate(8) < 0.05, 'no jolt in speed at the key');
  let last = -Infinity;
  for (let t = 0; t <= 15; t += 0.05) { const ms = +c.utc(t); assert.ok(ms >= last, `ran backwards at ${t}`); last = ms; }
  // a fast-forward on its own, or one next to a hold, still eases in and out
  const lone = createClock({ keys: [{ t: 0, utc: '2000-01-01T00:00:00Z' }, { t: 4, utc: '2000-01-02T00:00:00Z' }, { t: 8, utc: '2000-01-02T00:00:04Z' }] });
  const lr = (t) => (+lone.utc(t + 0.01) - +lone.utc(t - 0.01)) / 0.02;
  assert.ok(lr(3.99) < 0.05 * (86400e3 / 4), 'eases into a hold');
});

test('trackProfile: a launch rises almost straight up, then pitches over and flies level into orbit', () => {
  const g = { alt_far_km: 185 }, arcKm = 2000;
  const angle = (k) => { const [d0, h0] = trackProfile(g, k - 0.005), [d1, h1] = trackProfile(g, k + 0.005); return Math.atan2((h1 - h0) * 185, (d1 - d0) * arcKm) * 180 / Math.PI; };
  assert.deepEqual(trackProfile(g, 0), [0, 0]);
  assert.deepEqual(trackProfile(g, 1).map((x) => +x.toFixed(9)), [1, 1]);
  assert.ok(angle(0.02) > 45, `steep off the pad (${angle(0.02).toFixed(0)}°)`);
  assert.ok(angle(0.3) < angle(0.1) && angle(0.6) < angle(0.3), 'it pitches over steadily');
  assert.ok(angle(0.995) < 2, 'level at the end');
  let v = 0;
  for (let k = 0.01; k < 1; k += 0.01) { const s = trackProfile(g, k + 0.01)[0] - trackProfile(g, k)[0]; assert.ok(s >= v - 1e-9, 'always speeding up over the ground'); v = s; }
});

test('trackProfile: a landing brakes nearly level, hovers low, and comes straight down on the site', () => {
  const g = { site_at: 'end', alt_far_km: 15 };
  assert.deepEqual(trackProfile(g, 0), [1, 1]);
  const [d9, h9] = trackProfile(g, 0.9);
  assert.equal(d9, 0, 'over the site before the end');
  assert.ok(h9 * 15 > 0.1 && h9 * 15 <= 0.31, `a hover a few hundred metres up (${(h9 * 15000).toFixed(0)} m)`);
  assert.deepEqual(trackProfile(g, 1), [0, 0]);
  const [d1, h1] = trackProfile(g, 0.05);
  assert.ok((1 - d1) * 480 > 10 * (1 - h1) * 15, 'braking: far more ground than height early on');
  for (let k = 0; k < 1; k += 0.01) assert.ok(trackProfile(g, k + 0.01)[1] <= trackProfile(g, k)[1] + 1e-12, 'never climbs');
});

test('kepler and lambert: an orbit closes, and a transfer arc arrives where it was aimed', () => {
  const mu = 398600.4418, r = 7000, v = Math.sqrt(mu / r), P = 2 * Math.PI * Math.sqrt(r ** 3 / mu);
  assert.ok(len(sub(kepler([r, 0, 0], [0, 0, v], P, mu), [r, 0, 0])) < 1e-3);
  const muS = 1.32712440018e11, r1 = [1.496e8, 0, 0], r2 = [-1.5e8, 0, 1.6e8], tof = 250 * 86400;
  const { v1 } = lambert(r1, r2, tof, muS, [0, 1, 0]);
  assert.ok(len(sub(kepler(r1, v1, tof, muS), r2)) < 1, 'arrives within a kilometre');
  assert.ok(dot([r1[1] * v1[2] - r1[2] * v1[1], r1[2] * v1[0] - r1[0] * v1[2], r1[0] * v1[1] - r1[1] * v1[0]], [0, 1, 0]) > 0, 'prograde');
});

test('transfer between planets: a two-body arc from the real positions -- leaves Earth and meets Mars', () => {
  const w = buildWorld(bodies, { date: new Date('2020-07-30T11:50:00Z') });
  const T = createTrajectory(w, { id: 'cruise', frame: 'earth', generate: [{ kind: 'transfer', from: 'earth', to: 'mars', from_utc: '2020-07-30T11:50:00Z', to_utc: '2021-02-18T20:40:00Z' }] });
  for (const [u, near, far] of [['2020-07-30T11:50:00Z', 'earth', 10000], ['2021-02-18T20:40:00Z', 'mars', 10000]]) {
    w.setTime(new Date(u));
    assert.ok(len(sub(T.at(Date.parse(u)).position, w.vec('earth', near))) < far, `at ${near} on ${u}`);
  }
  // in between it is out in solar orbit, between the two planets' distances from the Sun, never back towards the Sun
  const mid = Date.parse('2020-11-01T00:00:00Z'); w.setTime(new Date(mid));
  const fromSun = len(sub(T.at(mid).position, w.vec('earth', 'sun'))) / 1.496e8;
  assert.ok(fromSun > 1.0 && fromSun < 1.7, `${fromSun.toFixed(2)} AU from the Sun`);
  assert.equal(T.samples[1].anchor, 'sun', 'a solar orbit');
  // the Moon from the Earth is not a planet-to-planet transfer, and dates that do not fit one direct coast (years, with
  // gravity assists the data does not describe) are not forced into a giant ellipse: the illustrated curve, as before
  const tl = createTrajectory(w, { id: 'tl', frame: 'earth', generate: [{ kind: 'transfer', from: 'earth', to: 'moon', from_utc: '2020-07-30T11:50:00Z', to_utc: '2020-08-02T11:50:00Z' }] });
  const slow = createTrajectory(w, { id: 'slow', frame: 'earth', generate: [{ kind: 'transfer', from: 'earth', to: 'mars', from_utc: '2020-07-30T11:50:00Z', to_utc: '2022-10-01T00:00:00Z' }] });
  assert.deepEqual([tl.samples[1].anchor, slow.samples[1].anchor], ['earth', 'earth']);
});

test('flyby: a hyperbola closest at periapsis_utc, at the periapsis height, bending round the body', () => {
  const w = buildWorld(bodies, { date: new Date('2030-01-01T00:00:00Z') });
  const tp = Date.parse('2030-01-01T12:00:00Z');
  const T = createTrajectory(w, { id: 'fb', frame: 'jupiter', generate: [{ kind: 'flyby', body: 'jupiter', periapsis_utc: '2030-01-01T12:00:00Z', periapsis_alt_km: 280000, v_inf_kms: 10, from_utc: '2029-12-29T12:00:00Z', to_utc: '2030-01-04T12:00:00Z' }] });
  const R = w.get('jupiter').radiusKm;
  let best = [Infinity, 0];
  for (let t = T.t0; t <= T.t1; t += 600e3) { const d = len(T.at(t).position); if (d < best[0]) best = [d, t]; }
  assert.ok(Math.abs(best[0] - (R + 280000)) < 2000, `closest ${Math.round(best[0] - R)} km up`);
  assert.ok(Math.abs(best[1] - tp) < 1800e3, 'closest at periapsis_utc');
  const a = T.at(T.t0), b = T.at(T.t1);
  const bend = angleDeg(a.direction, b.direction);
  assert.ok(bend > 20 && bend < 170, `the path turns ${bend.toFixed(0)}° round Jupiter`);
});

test('path shot: frames the stretch the beat shows and holds still while the craft crosses it', () => {
  const world = buildWorld(bodies, { date: new Date('1969-07-16T13:32:00Z') });
  const traj = { type: 'trajectory', id: 'up', frame: 'earth', generate: [{ kind: 'surface_track', body: 'earth', site: [-80.6, 28.6], site_at: 'start', heading_deg: 72, arc_deg: 18, alt_far_km: 185, from_utc: '1969-07-16T13:32:00Z', to_utc: '1969-07-16T13:44:00Z' }] };
  const shot = { path: { trajectory: 'up', from_utc: '1969-07-16T13:32:00Z', to_utc: '1969-07-16T13:44:00Z', fit: 1.3 }, el_deg: 20, keep: { trajectory: 'up', within: 0.8 } };
  const look = trajectoryLookup(world, [traj]);
  const clock = createClock({ keys: [{ t: 0, utc: '1969-07-16T13:32:00Z' }, { t: 8, utc: '1969-07-16T13:44:00Z' }] });
  const cam = createCamera(world, { fov_deg: 40, aspect: 16 / 9, drift_deg_per_s: 0.35, still: [[0, 8]], start: shot, moves: [] }, { trajectory: look });
  const tr = look('up'), tanHalf = Math.tan(20 * Math.PI / 180);
  let first = null, xs = [];
  for (let t = 0; t <= 8; t += 0.25) {
    world.setTime(clock.utc(t));
    const c = cam(t), fwd = sub(c.target, c.position);
    if (!first) first = fwd;
    assert.ok(angleDeg(first, fwd) < 0.05, `the camera holds (turned ${angleDeg(first, fwd).toFixed(3)}° by ${t} s)`);
    const q = sub(tr.at(+world.date).position, c.position), z = dot(q, fwd) / len(fwd);
    const right = [fwd[1] * c.up[2] - fwd[2] * c.up[1], fwd[2] * c.up[0] - fwd[0] * c.up[2], fwd[0] * c.up[1] - fwd[1] * c.up[0]];
    const x = dot(q, right) / len(right) / z / tanHalf, y = dot(q, c.up) / len(c.up) / z / tanHalf;
    assert.ok(Math.abs(x) < 16 / 9 && Math.abs(y) < 1, `the craft stays in frame at ${t} s`);
    xs.push(x);
  }
  assert.ok(Math.max(...xs) - Math.min(...xs) > 1.5, 'and it visibly crosses the frame');
});

test('still windows: the always-on drift rests while something moves, with no jump when it stops or starts', () => {
  const world = buildWorld(bodies, { date: new Date('2020-01-01T00:00:00Z') });
  const shot = { target: 'earth', fill: 0.5, light: 'side', el_deg: 20 };
  const drifting = createCamera(world, { fov_deg: 40, drift_deg_per_s: 1, start: shot }), resting = createCamera(world, { fov_deg: 40, drift_deg_per_s: 1, still: [[2, 6]], start: shot });
  const dirAt = (cam, t) => { const c = cam(t); return sub(c.position, c.target); };
  assert.ok(angleDeg(dirAt(resting, 3), dirAt(resting, 5)) < 1e-6, 'no drift inside the window');
  assert.ok(angleDeg(dirAt(drifting, 3), dirAt(drifting, 5)) > 1.5, 'drift without one');
  let prev = dirAt(resting, 0);
  for (let t = 1 / 30; t < 9; t += 1 / 30) { const d = dirAt(resting, t); assert.ok(angleDeg(prev, d) < 1.01 / 30 + 1e-6, `smooth at ${t.toFixed(2)} s`); prev = d; }
});

test('spacecraft: the model gives way to a screen-space marker only far away, by projected size (never by world size)', async () => {
  const { markerShare } = await import('../layers/spacecraft.mjs');
  // a ~10 m craft seen by a 1300 px focal length: 15,000 km (a liftoff shot) and 400,000 km (Earth-Moon) keep the model
  assert.equal(markerShare((0.01 / 15000) * 1300), 0);
  assert.equal(markerShare((0.01 / 400000) * 1300), 0);
  // Saturn, solar-system and heliosphere distances: the marker
  for (const km of [3.7e8, 7e9, 5e10]) assert.equal(markerShare((0.01 / km) * 1300), 1);
  const mid = markerShare(3e-6);
  assert.ok(mid > 0 && mid < 1, 'a decade of scale in between cross-fades');
});
