// Re-rendering only what changed: each chunk's fingerprint moves with what shows in it, and only with that.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { planChunks, chunkFingerprints, fileFingerprint } from '../lib/segments.mjs';

const world = [{ id: 'sun', kind: 'star', radius: { km: 696000 } }, { id: 'earth', parent: 'sun', kind: 'body', radius: { km: 6371 }, offset: { ephemeris: 'earth' } }];
const base = () => ({
  width: 320, height: 180, fps: 10, duration: 12, world, clock: { utc: '2026-01-01T00:00:00Z' },
  camera: { start: { target: 'earth', fill: 0.5 }, moves: [{ t: 9, dur: 2, to: { target: 'earth', fill: 0.3 } }] },
  layers: [{ type: 'caption', text: 'EARLY', start: 0.5, end: 2.5 }, { type: 'caption', text: 'LATE', start: 5, end: 7 }],
  footage: [],
});
const keys = (spec, mediaDir) => chunkFingerprints(spec, planChunks(Math.round(spec.duration * spec.fps), spec.fps), { mediaDir });
const changed = (a, b) => a.map((k, i) => (k === b[i] ? null : i)).filter((i) => i !== null);

test('chunks: whole frames of CHUNK_S, the last one shorter', () => {
  assert.deepEqual(planChunks(100, 10, 4), [{ i: 0, k0: 0, k1: 40 }, { i: 1, k0: 40, k1: 80 }, { i: 2, k0: 80, k1: 100 }]);
});

test('a layer edit redraws only the chunks it is on screen in', () => {
  const a = keys(base()), s = base();
  s.layers[1].text = 'LATER';                                       // on screen 5-7 s: the 4-8 s chunk
  assert.deepEqual(changed(a, keys(s)), [1]);
  assert.deepEqual(changed(a, keys(base())), [], 'the same spec gives the same fingerprints');
});

test('a camera move redraws the chunks it moves in and the ones after it holds', () => {
  const s = base();
  s.camera.moves[0].to.fill = 0.2;                                  // 9-11 s, then held to the end
  assert.deepEqual(changed(keys(base()), keys(s)), [2]);
  const d = base(); d.clock = { utc: '2026-06-01T00:00:00Z' };     // the date moves every body: everything
  assert.deepEqual(changed(keys(base()), keys(d)), [0, 1, 2]);
});

test('media count by content: a renumbered file is the same picture, a new picture is not', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'starmap-seg-'));
  try {
    fs.writeFileSync(path.join(dir, '001_card.jpg'), 'picture one');
    fs.writeFileSync(path.join(dir, '002_card.jpg'), 'picture one');
    fs.writeFileSync(path.join(dir, '003_other.jpg'), 'picture two');
    const s = base(); s.layers.push({ type: 'photo_card', image: '001_card.jpg', start: 5, end: 7 });
    const a = keys(s, dir);
    s.layers[2].image = '002_card.jpg';
    assert.deepEqual(changed(a, keys(s, dir)), [], 'renamed, same content');
    s.layers[2].image = '003_other.jpg';
    assert.deepEqual(changed(a, keys(s, dir)), [1]);
    assert.equal(fileFingerprint(path.join(dir, 'nope.jpg')), 'missing');
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('back-to-back footage (each clip linked to the next) fingerprints, and a clip swap redraws only its chunks', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'starmap-seg-'));
  try {
    for (const n of ['a.jpg', 'b.jpg', 'c.jpg']) fs.writeFileSync(path.join(dir, n), `picture ${n}`);
    const s = base();
    s.footage = [{ id: 'f1', image: 'a.jpg', start: 4.5, end: 6.5 }, { id: 'f2', image: 'b.jpg', start: 6.5, end: 9 }];
    const a = keys(s, dir);
    s.footage[0].image = 'c.jpg';
    assert.deepEqual(changed(a, keys(s, dir)), [1]);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
