import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createCamera, validateCamera, TimelineError, lonLatToWorld, metersPerPixel, frameWidthKm } from '../lib/camera.mjs';

const spec = JSON.parse(fs.readFileSync(new URL('../samples/spike-60s.json', import.meta.url), 'utf8'));
const W = spec.width, H = spec.height, D = spec.duration;
const cam = () => createCamera({ camera: spec.camera, width: W, height: H, duration: D });
const noDrift = () => createCamera({ camera: { ...spec.camera, drift: { pct_per_s: 0 } }, width: W, height: H, duration: D });

// screen distance (px) between two camera states, measured at the larger zoom
function screenPx(a, b) {
  const [ax, ay] = lonLatToWorld(a.lon, a.lat), [bx, by] = lonLatToWorld(b.lon, b.lat);
  let dx = bx - ax; if (dx > 0.5) dx -= 1; if (dx < -0.5) dx += 1;
  return Math.hypot(dx, by - ay) * 512 * Math.pow(2, Math.max(a.zoom, b.zoom));
}

test('the camera is deterministic: same spec, same path', () => {
  const a = cam(), b = cam();
  for (let t = 0; t <= D; t += 0.37) assert.deepEqual(a.at(t), b.at(t));
});

test('no jumps anywhere: motion over a tiny time step is tiny, including at every move boundary', () => {
  const c = cam(), eps = 1 / 1000;
  const edges = spec.camera.moves.flatMap((m) => [m.t, m.t + m.dur]);
  for (const e of [0, ...edges, D - 2 * eps]) {
    for (const t of [e - eps, e, e + eps]) {
      if (t < 0 || t + eps > D) continue;
      const a = c.at(t), b = c.at(t + eps);
      assert.ok(screenPx(a, b) < 3, `jump of ${screenPx(a, b).toFixed(2)}px near t=${t}`);
      assert.ok(Math.abs(a.zoom - b.zoom) < 0.01, `zoom jump near t=${t}`);
    }
  }
});

test('whole-path smoothness at 30 fps: no frame moves more than 12% of the frame width', () => {
  const c = cam();
  let worst = 0;
  for (let i = 0; i < D * 30; i++) worst = Math.max(worst, screenPx(c.at(i / 30), c.at((i + 1) / 30)) / W);
  assert.ok(worst < 0.12, `worst frame step ${(worst * 100).toFixed(1)}% of width`);
});

test('idle drift never stops: during a hold the map still moves 0.4-0.9% of frame width per second', () => {
  const c = createCamera({ camera: { start: { lon: 10, lat: 50, zoom: 5 }, drift: { pct_per_s: 0.6, heading_deg: 90 }, moves: [] }, width: W, height: H, duration: 10 });
  const pctPerS = (screenPx(c.at(2), c.at(3)) / W) * 100;
  assert.ok(pctPerS > 0.4 && pctPerS < 0.9, `drift ${pctPerS.toFixed(3)} %/s`);
});

test('drift carries on through a move (position stays continuous through a fly_to start)', () => {
  const c = cam();
  assert.ok(screenPx(c.at(11.99), c.at(12.01)) < 10);
});

test('fly_to arrives exactly at its target', () => {
  const end = noDrift().at(7.0);
  assert.ok(Math.abs(end.zoom - 3.0) < 1e-6);
  assert.ok(Math.abs(end.lon - 95) < 1e-6 && Math.abs(end.lat - 60) < 1e-6);
});

test('every move lands on its target: drift never drags the camera off course', () => {
  const c = cam();
  for (const m of spec.camera.moves) {
    if (m.type !== 'fly_to') continue;
    const a = c.at(m.t + m.dur);
    const [ex, ey] = lonLatToWorld(m.to.lon, m.to.lat), [ax, ay] = lonLatToWorld(a.lon, a.lat);
    let dx = ax - ex; if (dx > 0.5) dx -= 1; if (dx < -0.5) dx += 1;
    const offPx = Math.hypot(dx, ay - ey) * 512 * Math.pow(2, m.to.zoom);
    // only the drift of the shot itself may remain (a few per cent of the frame); before the fix it ended ~20 degrees off
    assert.ok(offPx < W * 0.15, `fly_to at ${m.t}s ends ${offPx.toFixed(0)}px off its target`);
  }
});

test('a move starts gently: the speed does not jump when a move begins', () => {
  const c = cam(), h = 0.03;
  const speed = (t) => screenPx(c.at(t - 0.02), c.at(t + 0.02)) / 0.04;
  for (const m of spec.camera.moves) {
    const before = speed(m.t - h), after = speed(m.t + h);
    assert.ok(Math.abs(after - before) < W * 0.02, `speed jumps from ${before.toFixed(0)} to ${after.toFixed(0)} px/s at ${m.t}s`);
  }
});

test('push_in goes steadily deeper and never reverses', () => {
  const c = cam();
  let prev = c.at(17).zoom;
  for (let t = 17.1; t <= 23; t += 0.1) { const z = c.at(t).zoom; assert.ok(z >= prev - 1e-9); prev = z; }
});

test('the route east over the date line takes the short way (longitude keeps increasing)', () => {
  const c = noDrift();
  let prev = c.at(40.5).lon;
  for (let t = 41; t <= 47.5; t += 0.5) { const lon = c.at(t).lon; assert.ok(lon >= prev - 1e-6, `lon went back at t=${t}`); prev = lon; }
  assert.ok(prev > 180, `unwrapped longitude should pass 180 (got ${prev})`);
});

test('a long fly_to eases in and out: slow at both ends, fastest in the middle', () => {
  const c = noDrift();
  const v = (t) => screenPx(c.at(t), c.at(t + 0.05)) / 0.05;
  assert.ok(v(40.55) < v(43.5) * 0.3);
  assert.ok(v(47.4) < v(43.5) * 0.3);
});

test('top-down only: the camera never carries tilt or rotation', () => {
  assert.deepEqual(Object.keys(cam().at(20)).sort(), ['lat', 'lon', 'zoom']);
});

test('timeline validation names the problem', () => {
  const s = { lon: 0, lat: 0, zoom: 1 };
  assert.match(validateCamera({ start: s, moves: [{ type: 'teleport', t: 0, dur: 1, to: { zoom: 2 } }] }, 10).join(), /type must be/);
  assert.match(validateCamera({ start: s, moves: [{ type: 'push_in', t: 0, dur: 5, to: { zoom: 2 } }, { type: 'push_in', t: 3, dur: 5, to: { zoom: 3 } }] }, 10).join(), /overlap|before the previous move ends/);
  assert.match(validateCamera({ start: s, moves: [{ type: 'push_in', t: 8, dur: 5, to: { zoom: 2 } }] }, 10).join(), /ends after the video/);
  assert.throws(() => createCamera({ camera: { moves: [] }, width: W, height: H, duration: 5 }), TimelineError);
});

test('scale helpers: frame width follows zoom and latitude', () => {
  assert.ok(Math.abs(frameWidthKm(0, 5, 1920) - (metersPerPixel(0, 5) * 1920) / 1000) < 1e-9);
  assert.ok(frameWidthKm(60, 5, 1920) < frameWidthKm(0, 5, 1920));
  assert.ok(Math.abs(frameWidthKm(0, 6, 1920) * 2 - frameWidthKm(0, 5, 1920)) < 1e-6);
});
