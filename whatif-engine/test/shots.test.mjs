import test from 'node:test';
import assert from 'node:assert/strict';
import { shotAt, driftAt, validateShots, clipFrameIndex } from '../lib/shots.mjs';
import { BUILTIN_LAYERS } from '../layers/index.mjs';
import { createRegistry } from '../lib/layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';

const shots = [{ id: 'a', start: 0, end: 6, kind: 'image', file: 'x.jpg' }, { id: 'b', start: 6, end: 11, kind: 'plate' }, { id: 'c', start: 11, end: 15, kind: 'globe', texture: 'v.jpg', exit: 'push' }];

test('shots: the shot at a time, hard cuts at the boundary', () => {
  assert.equal(shotAt(shots, 0).id, 'a');
  assert.equal(shotAt(shots, 5.999).id, 'a');
  assert.equal(shotAt(shots, 6).id, 'b');
  assert.equal(shotAt(shots, 99).id, 'c');
});

test('shots: validation names the shot', () => {
  assert.deepEqual(validateShots({ shots }), []);
  assert.match(validateShots({ shots: [{ id: 'z', start: 0, end: 1, kind: 'image' }] })[0], /shot z: image needs a file/);
  assert.match(validateShots({ shots: [{ id: 'z', start: 3, end: 1, kind: 'plate' }] })[0], /end must be after start/);
});

test('drift: never fully still, 1.00 -> 1.04, and a push at the end of an exit:push shot', () => {
  const a = driftAt(shots[0], 0), b = driftAt(shots[0], 3), c = driftAt(shots[0], 6);
  assert.ok(a.scale < b.scale && b.scale < c.scale);
  assert.ok(Math.abs(c.scale - 1.04) < 1e-6);
  assert.ok(driftAt(shots[2], 14.9).scale > driftAt(shots[2], 13).scale * 1.2);
});

test('clip frames follow the shot time and speed', () => {
  assert.equal(clipFrameIndex({ start: 10, speed: 1 }, 12, 30), 60);
  assert.equal(clipFrameIndex({ start: 10, speed: 2 }, 12, 30), 120);
});

test('every layer type registers once and is screen-space', () => {
  const reg = registerBuiltins(createRegistry());
  assert.equal(reg.types().length, BUILTIN_LAYERS.length);
  for (const t of reg.types()) assert.equal(reg.get(t).space, 'screen');
});

test('hero shots need a known scene; every kind is listed', () => {
  assert.deepEqual(validateShots({ shots: [{ id: 'h', start: 0, end: 5, kind: 'hero', scene: 'venera_ground' }] }), []);
  assert.match(validateShots({ shots: [{ id: 'h', start: 0, end: 5, kind: 'hero', scene: 'nope' }] })[0], /hero needs a scene/);
});

test('the new diagram layers register and validate their input', async () => {
  const { default: annotate } = await import('../layers/tm_annotate.mjs');
  const { default: discmap } = await import('../layers/tm_discmap.mjs');
  assert.throws(() => annotate.create({ label: 'x' }), /"x" and "y" are required/);
  assert.equal(annotate.create({ x: 0.5, y: 0.5 }).def.x, 0.5);
  assert.equal((await discmap.create({ keys: [{ t: 3, reach: 0.4 }, { t: 1, reach: 0.1 }] }, {})).keys[0].t, 1);
  for (const scene of ['cloud_airship', 'ship_engine', 'blackhole_disc', 'blackhole_top', 'blackhole_ring', 'blackhole_lensing', 'blackhole_horizon']) assert.deepEqual(validateShots({ shots: [{ id: 'h', start: 0, end: 5, kind: 'hero', scene }] }), []);
});
