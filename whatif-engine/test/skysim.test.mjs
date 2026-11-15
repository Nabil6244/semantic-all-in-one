// Sky Sim in the What If engine: shot kind `sky`, the sk_* layers, held-step easing and the camera.
import test from 'node:test';
import assert from 'node:assert/strict';
import { KINDS, sanitizeShots } from '../lib/shots.mjs';
import { BUILTIN_LAYERS } from '../layers/index.mjs';
import { skyAt, cameraAt, BUILT_LOOKS } from '../lib/skysim_sky.mjs';
import { heatOf } from '../lib/skysim_land.mjs';

test('sky is a shot kind and survives repair', () => {
  assert.ok(KINDS.includes('sky'));
  const spec = { duration: 10, shots: [{ id: 'a', start: 0, end: 10, kind: 'sky', look: 'space', sky: { object: 'sun', angular_deg: 0.5, flux_x: 1 } }] };
  sanitizeShots(spec);
  assert.equal(spec.shots[0].kind, 'sky');
});

test('sk_* layers are registered and reject empty data', () => {
  const types = BUILTIN_LAYERS.map((L) => L.type);
  for (const t of ['sk_stats', 'sk_readout', 'sk_clocks', 'sk_title', 'sk_scalering', 'sk_leader', 'sk_subtitle']) assert.ok(types.includes(t), t);
  const stats = BUILTIN_LAYERS.find((L) => L.type === 'sk_stats');
  assert.throws(() => stats.create({ type: 'sk_stats', rows: [] }));
});

test('a held step eases from the last sky to its own in log space', () => {
  const s = { start: 10, end: 20, sky: { angular_deg: 10, flux_x: 100 }, sky_from: { angular_deg: 0.1, flux_x: 1 } };
  assert.ok(Math.abs(skyAt(s, 10).angular_deg - 0.1) < 1e-9);
  assert.ok(Math.abs(skyAt(s, 20).angular_deg - 10) < 1e-9);
  const mid = skyAt(s, 13.5).angular_deg;                  // halfway through the 7 s ease: the geometric middle
  assert.ok(Math.abs(mid - 1) < 1e-6, String(mid));
});

test('the camera is never fully still unless asked', () => {
  const s = { start: 0, end: 10, camera: 'drift' };
  assert.notEqual(cameraAt(s, 0).scale, cameraAt(s, 10).scale);
  assert.equal(cameraAt({ ...s, camera: 'static' }, 5).scale, 1);
  assert.deepEqual(BUILT_LOOKS, ['space', 'moon_surface', 'landscape', 'lake']);
});

test('the landscape heat ladder follows the light (TON 618 rungs)', () => {
  const at = (f) => heatOf(f);
  assert.ok(at(3e-16).L < -15, 'no floor above the naked-eye limit');    // 10.8 billion ly: invisible
  assert.ok(at(3.5e-8).raw < 0.05);                                       // 1 million ly: still night
  assert.ok(at(0.035).raw > 0.5 && at(0.035).burn === 0);                 // 1,000 ly: a blue sky
  assert.ok(at(1).raw > 0.95 && at(1).scorch < 0.1);                      // 187 ly: daylight
  assert.ok(at(14).burn > 0.7 && at(14).melt < 0.05);                     // 50 ly: the forest burns
  assert.ok(at(3.5e6).melt === 1 && at(3.5e6).sky < 0.4);                 // 0.1 ly: lava, the camera stops down
});

test('the lake look: real-ridge sampling, a seeded fallback skyline, and the object above the ridge', async () => {
  const { fallbackRidges, objectPlace } = await import('../lib/skysim_lake.mjs');
  const R = fallbackRidges();
  assert.equal(R.layers.length, 3);
  assert.equal(R.az_deg.length, R.layers[0].deg.length);
  assert.ok(R.layers[0].deg.every((d, i) => d >= R.layers[1].deg[i] - 1e-9), 'the far skyline is never below the mid one');
  const peak = Math.max(...R.layers[0].deg.filter((_, i) => Math.abs(R.az_deg[i]) <= 12));
  const el = objectPlace(R, { angular_deg: 0.5 }, 24, 648, 1);
  assert.ok(el > peak, 'a point of light sits above the skyline');
  assert.ok(el * 24 < 648, 'and inside the frame');
});

test('the air: navy night (never black), blue day, deep blue when stopped down', async () => {
  const { airAt } = await import('../lib/skysim_air.mjs');
  const night = airAt(1e-12), day = airAt(1), blinding = airAt(1e5);
  assert.ok(Math.max(...night.zenith) >= 10 && Math.max(...night.zenith) < 40);
  assert.ok(day.zenith[2] > day.zenith[0] * 2, 'the day sky is blue');
  assert.ok(blinding.zenith[2] > blinding.zenith[0] * 2 && blinding.zenith[2] < day.zenith[2], 'stopped down: darker blue, not white or brown');
});
