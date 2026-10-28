import test from 'node:test';
import assert from 'node:assert/strict';
import { repairScene, WORLD_TYPES, CRAFT_KINDS } from '../lib/scene_gen.mjs';
import { validateShots, sanitizeShots } from '../lib/shots.mjs';

test('repairScene fills every default and never throws on garbage', () => {
  for (const sp of [{}, { world: { type: 'nope', palette: ['x'] } }, { craft: { kind: 'zzz', parts: [{ shape: 'bad' }] }, camera: { path: 'spin' } }, { layout: 'x', env: { clouds: 'no' }, light: { dir: [1] } }]) {
    const notes = repairScene(sp);
    assert.ok(Array.isArray(notes));
    assert.ok(['planet', 'craft', 'craft_over_planet'].includes(sp.layout));
    assert.ok(sp.camera.dist > 0 && sp.light.dir.length === 3 && sp.env.sky);
    if (sp.world) { assert.ok(WORLD_TYPES.includes(sp.world.type)); assert.ok(sp.world.palette.length >= 2); }
    if (sp.craft) assert.ok(CRAFT_KINDS.includes(sp.craft.kind));
  }
});

test('a scene shot needs a spec; one without becomes a plate', () => {
  const spec = { duration: 8, shots: [{ id: 'a', start: 0, end: 4, kind: 'scene', scene_spec: { world: { type: 'gas' } } }, { id: 'b', start: 4, end: 8, kind: 'scene' }] };
  assert.deepEqual(validateShots({ shots: [spec.shots[0]] }), []);
  const notes = sanitizeShots(spec);
  assert.equal(spec.shots[0].kind, 'scene');
  assert.equal(spec.shots[1].kind, 'plate');
  assert.ok(notes.some((n) => /scene_spec/.test(n)));
});

test('cutaway layers are sorted outside-in and a one-layer cutaway or bad field is repaired', () => {
  const sp = { world: { type: 'gas', cutaway: { layers: [{ r: 0.3, color: '#ffffff' }, { r: 1, color: 'nope' }, { r: 0.6, color: '#aa5500' }] }, field: { lines: 99, color: 'x' } } };
  repairScene(sp);
  assert.deepEqual(sp.world.cutaway.layers.map((l) => l.r), [1, 0.6, 0.3]);
  assert.equal(sp.world.field.lines, 24);
  const one = { world: { type: 'rock', cutaway: { layers: [{ r: 1, color: '#ffffff' }] } } };
  repairScene(one);
  assert.equal(one.world.cutaway, null);
});

test('cutaway labels are upper-cased, trimmed to 22 characters, and optional', () => {
  const sp = { world: { type: 'rock', cutaway: { layers: [{ r: 1, color: '#7a6a5a', label: '  crust  ' }, { r: 0.5, color: '#e0902a', label: 'a very very long layer name indeed' }, { r: 0.2, color: '#ffe060' }, { r: 0.1, color: '#ffffff', label: 5 }] } } };
  repairScene(sp);
  const [a, b, c, d] = sp.world.cutaway.layers;
  assert.equal(a.label, 'CRUST');
  assert.equal(b.label.length, 22);
  assert.equal(b.label, b.label.toUpperCase());
  assert.equal(c.label, '');
  assert.equal(d.label, '');
});
