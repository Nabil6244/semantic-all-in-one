import test from 'node:test';
import assert from 'node:assert/strict';
import { auditSpec, recordingCanvas } from '../tools/overlap_audit.mjs';
import { opacityAt } from '../lib/timing.mjs';

const base = (layers) => ({ width: 1920, height: 1080, fps: 30, duration: 10, shots: [{ id: 's1', start: 0, end: 10, kind: 'plate' }], layers });
const metric = (value, unit, anchor, start, end) => ({ type: 'tm_metric', value, unit, anchor, size: 'large', start, end, fade_in: 0.05, fade_out: 0.3 });

test('overlap audit: two big numbers in the same place at the same time are a clash, with its time', async () => {
  const r = await auditSpec(base([metric('17', 'KM/S', 'upper_left', 1, 6), metric('3.6', 'AU', 'upper_left', 3, 8)]));
  assert.equal(r.clashes.length, 1);
  const c = r.clashes[0];
  assert.deepEqual([c.a, c.b], [0, 1]);
  assert.ok(c.start >= 3 && c.start < 3.5 && c.end <= 6.1, JSON.stringify(c));
});

test('overlap audit: the same two numbers one after the other, or in different corners, are not', async () => {
  assert.equal((await auditSpec(base([metric('17', 'KM/S', 'upper_left', 1, 4), metric('3.6', 'AU', 'upper_left', 4.1, 8)]))).clashes.length, 0);
  assert.equal((await auditSpec(base([metric('17', 'KM/S', 'upper_left', 1, 6), metric('3.6', 'AU', 'lower_right', 3, 8)]))).clashes.length, 0);
});

test('recording canvas: text boxes follow alignment and transforms', () => {
  const { g, take } = recordingCanvas(1920, 1080);
  g.font = '900 100px StarMapSans, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.save(); g.translate(960, 540); g.fillText('AB', 0, 0); g.restore();
  const [t] = take();
  assert.ok(Math.abs((t.box[0] + t.box[2]) / 2 - 960) < 1 && Math.abs((t.box[1] + t.box[3]) / 2 - 540) < 1, JSON.stringify(t.box));
  g.fillStyle = 'rgba(0,0,0,0.2)'; g.fillRect(0, 0, 100, 100);       // a faint wash is a backdrop, not a card
  g.fillStyle = 'rgba(10,13,18,0.85)'; g.fillRect(0, 0, 100, 100);
  assert.equal(take().length, 1);
});

test('mute windows: a layer steps back inside them and fades around them; no mute changes nothing', () => {
  const d = { start: 0, end: 100, fade_in: 0, fade_out: 0, mute: [[10, 20]] };
  assert.equal(opacityAt(d, 5), 1);
  assert.equal(opacityAt(d, 15), 0);
  assert.ok(opacityAt(d, 9.85) > 0 && opacityAt(d, 9.85) < 1);
  assert.equal(opacityAt(d, 25), 1);
  assert.equal(opacityAt({ start: 0, end: 100, fade_in: 0, fade_out: 0 }, 15), 1);
});

test('footage filter: Lanczos scaling for every clip, a light unsharp mask only for a clip marked upscale', async () => {
  const { footageFilter } = await import('../cutter.mjs');
  const plain = footageFilter({ id: 's1' }, 1920, 1080, 30), up = footageFilter({ id: 's2', upscale: true }, 1920, 1080, 30);
  assert.match(plain, /scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080/);
  assert.doesNotMatch(plain, /unsharp/);
  assert.match(up, /unsharp=5:5:0\.7/);
});
