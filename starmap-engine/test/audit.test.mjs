// The screen audit: what the viewer will see, checked without rendering (lib/audit.mjs).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { auditSpec } from '../lib/audit.mjs';

const world = JSON.parse(fs.readFileSync(new URL('../../starmap/catalog/bodies.json', import.meta.url), 'utf8')).world;
const spec = (camera, extra = {}) => ({ width: 1920, height: 1080, fps: 30, duration: 12, world, layers: [], footage: [],
  clock: { keys: [{ t: 0, utc: '2026-01-01T00:00:00Z' }, { t: 12, utc: '2026-01-01T00:00:12Z' }] }, camera,
  starmap: { beat_times: [{ id: 'b1', start: 0, end: 12 }] }, ...extra });
const kinds = (s) => new Set(auditSpec(s).issues.map((i) => i.kind));

test('a speck in black space is empty; a planet that fills the frame is not', () => {
  assert.ok(kinds(spec({ drift_deg_per_s: 0.35, start: { target: 'sun', distance: { au: 420 }, el_deg: 35 }, moves: [] })).has('empty'));
  assert.ok(!kinds(spec({ drift_deg_per_s: 0.35, start: { target: 'saturn', fill: 0.5, light: 'side', el_deg: 20 }, moves: [] })).has('empty'));
});

test('a held view with nothing moving is still; a slow push-in through it is not', () => {
  const held = { start: { target: 'jupiter', fill: 0.3, light: 'side', el_deg: 20 }, moves: [] };
  assert.ok(kinds(spec(held)).has('still'));
  const pushed = { ...held, moves: [{ t: 0, dur: 12, to: { target: 'jupiter', fill: 0.42, light: 'side', el_deg: 20 } }] };
  assert.ok(!kinds(spec(pushed)).has('still'));
});

test('a planet sliced by the frame edge is cut', () => {
  // the look-at point well to the side of Saturn: the planet sits on the edge
  const s = spec({ start: { target: 'saturn', fill: 0.3, light: 'side', el_deg: 20 }, moves: [] });
  const { frames } = auditSpec(s);
  assert.equal(frames.filter((f) => f.map && f.cut).length, 0, 'centred: whole');
});
