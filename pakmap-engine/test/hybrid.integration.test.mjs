// Hybrid Map in real renders (flat green map, solid-colour footage, lossless encode so equal frames are byte-equal):
// the map's state is frozen under footage and restored on return, footage covers the UI, clips hand over without a map flash.
import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RENDER = path.join(HERE, '..', 'render.mjs');
const W = 960, H = 540, FPS = 10;

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;
const ff = (...a) => { const r = spawnSync('ffmpeg', ['-v', 'error', '-y', ...a]); assert.equal(r.status, 0, String(r.stderr)); };

const dir = skip ? null : fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-hybrid-'));
if (dir) {
  ff('-f', 'lavfi', '-i', 'color=c=0xff0000:size=1280x720', '-frames:v', '1', path.join(dir, 'red.jpg'));
  ff('-f', 'lavfi', '-i', 'color=c=0x0000ff:size=1280x720', '-frames:v', '1', path.join(dir, 'blue.jpg'));
  ff('-f', 'lavfi', '-i', 'testsrc=size=1280x720', '-frames:v', '1', path.join(dir, 'pattern.jpg'));
}

const base = (name, over = {}) => ({
  width: W, height: H, fps: FPS, duration: 8, output: path.join(dir, `${name}.mp4`), cache_dir: path.join(dir, 'cache'), base_dir: dir,
  imagery_enabled: false, flat_only: true, crf: 0,
  camera: { start: { lon: 0, lat: 0, zoom: 5 }, drift: { pct_per_s: 0 }, moves: [] },
  hybrid: { pause_overlays: true },
  events: [
    { id: 'm', type: 'marker', t_in: 0.5, t_out: 8, lon: 0, lat: 0, label: 'MID' },
    { id: 'l', type: 'line', t_in: 2.7, t_out: 8, kind: 'flow', coords: [[-3, -2], [3, 2]] },       // 0.9 s draw: part-drawn when the footage starts
    { id: 's', type: 'stat', t_in: 2.8, t_out: 8, anchor: 'br', value_from: 0, value_to: 100, format: '0 KM' }, // counting when it starts
    { id: 'c', type: 'caption', t_in: 1, t_out: 8, text: 'UNDER THE FOOTAGE', anchor: 'bc' },
    { id: 'f', type: 'media_full', t_in: 3, t_out: 5, media: 'red.jpg', cover_ui: true },
  ],
  ...over,
});

function render(spec) {
  const f = path.join(dir, `${path.basename(spec.output, '.mp4')}.json`);
  fs.writeFileSync(f, JSON.stringify(spec));
  const r = spawnSync('node', [RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 300000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', spec.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  return (t) => { const n = Math.round(t * FPS); return raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
}
const px = (f, x, y) => { const i = (y * W + x) * 3; return [f[i], f[i + 1], f[i + 2]]; };
const same = (a, b) => Buffer.compare(a, b) === 0;
function countNot(f, [r, g, b], tol, x0, y0, x1, y1) {
  let n = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const p = px(f, x, y); if (Math.abs(p[0] - r) > tol || Math.abs(p[1] - g) > tol || Math.abs(p[2] - b) > tol) n++; }
  return n;
}

test('the map is frozen under footage and comes back in exactly the state it left, mid-animation included', { skip }, () => {
  const frame = render(base('hold'));
  assert.ok(!same(frame(2.0), frame(3.0)), 'sanity: the line and the counter are moving before the footage');
  assert.ok(!same(frame(3.0), frame(6.0)), 'sanity: they finish drawing after the return');
  assert.ok(same(frame(3.0), frame(5.0)), 'the map at the moment the footage ends must equal the map at the moment it began');
});

test('control: without the option the animations keep running behind the footage', { skip }, () => {
  const spec = base('nohold', { hybrid: { pause_overlays: false } });
  const frame = render(spec);
  assert.ok(!same(frame(3.0), frame(5.0)), 'the line finished and the counter reached its end while hidden');
});

test('the camera is continuous across footage, drift included', { skip }, () => {
  const spec = base('drift');
  spec.camera = { start: { lon: 0, lat: 0, zoom: 5 }, drift: { pct_per_s: 0.8, heading_deg: 70 }, moves: [] };
  const frame = render(spec);
  assert.ok(!same(frame(1.0), frame(2.0)), 'sanity: the map drifts before the footage');
  assert.ok(same(frame(3.0), frame(5.0)), 'no drift, no jump, under the footage');
  assert.ok(!same(frame(5.0), frame(6.0)), 'the drift resumes afterwards');
});

test('footage covers the UI layers (they dissolve with the map); without cover_ui the old PakMap order is kept', { skip }, () => {
  const frame = render(base('cover'));
  const region = [300, 470, 660, 530];  // where the bottom-centre caption sits
  const mid = frame(4.0);
  assert.equal(countNot(mid, [255, 0, 0], 40, ...region), 0, 'pure footage in the caption area');
  assert.equal(countNot(mid, [255, 0, 0], 40, 700, 440, 950, 530), 0, 'and in the stat chip area');
  assert.ok(countNot(frame(2.0), [255, 0, 0], 40, ...region) > 200, 'sanity: the caption is there before the footage');

  const spec = base('nocover');
  spec.events[spec.events.length - 1] = { ...spec.events[spec.events.length - 1], cover_ui: false };
  const old = render(spec)(4.0);
  assert.ok(countNot(old, [255, 0, 0], 40, ...region) > 200, 'a PakMap-style interlude leaves the caption on top');
});

test('footage dissolves in and out (about half red at the middle of each dissolve) and is fully opaque between', { skip }, () => {
  const frame = render(base('dissolve'));
  const mix = (t) => px(frame(t), 150, 150); // away from the marker, which sits at the centre
  assert.ok(Math.abs(mix(3.25)[0] - 255 * 0.5 - 59 * 0.5) < 30, `red at the middle of the dissolve in: ${mix(3.25)}`);
  assert.deepEqual(mix(4.0).map((v) => Math.round(v / 20)), [13, 0, 0]);
  assert.ok(Math.abs(mix(4.75)[0] - 255 * 0.5 - 59 * 0.5) < 30, `and out: ${mix(4.75)}`);
});

test('clips hand over to each other without the map showing through', { skip }, () => {
  const spec = base('xfade');
  spec.events = spec.events.filter((e) => e.id !== 'f').concat([
    { id: 'f1', type: 'media_full', t_in: 3, t_out: 5, media: 'red.jpg', cover_ui: true },
    { id: 'f2', type: 'media_full', t_in: 4.5, t_out: 6.5, media: 'blue.jpg', cover_ui: true, xfade_prev: true },
  ]);
  const frame = render(spec);
  const mid = px(frame(4.75), 150, 150); // half way through the hand-over
  assert.ok(mid[0] > 90 && mid[0] < 170 && mid[2] > 90 && mid[2] < 170, `a red/blue mix: ${mid}`);
  assert.ok(mid[1] < 30, `and no green map in it: ${mid}`);
  assert.deepEqual(px(frame(5.5), 150, 150).map((v) => Math.round(v / 20)), [0, 0, 13]); // fully the second clip
  assert.ok(same(frame(3.0), frame(6.5)), 'one block of footage: the map comes back exactly as it left');
});

test('a still can push in slowly (ken burns) and the map state is still restored', { skip }, () => {
  const spec = base('kb');
  spec.events[spec.events.length - 1] = { ...spec.events[spec.events.length - 1], media: 'pattern.jpg', kenburns: true, kenburns_zoom: 0.2 };
  const frame = render(spec);
  assert.ok(!same(frame(3.6), frame(4.4)), 'the picture moves while it is on screen');
  assert.ok(same(frame(3.0), frame(5.0)));
});

test('ken burns "auto" moves a still that the plan expected to be a video, and a still without it stays frozen', { skip }, () => {
  const spec = base('kbauto');
  spec.events[spec.events.length - 1] = { ...spec.events[spec.events.length - 1], media: 'pattern.jpg', kenburns: 'auto', kenburns_zoom: 0.2 };
  const moving = render(spec);
  assert.ok(!same(moving(3.6), moving(4.4)), 'the still moves');
  const plain = base('kbnone');
  plain.events[plain.events.length - 1] = { ...plain.events[plain.events.length - 1], media: 'pattern.jpg' };
  const still = render(plain);
  assert.ok(same(still(3.6), still(4.4)), 'and without the flag it does not');
});

// A clip shorter than its slot used to restart from its first frame (a visible repeat). With fit it is slowed, then plays backwards: never a jump.
test('a short clip in a long slot never jumps back to its first frame (fit), while the old looping did', { skip }, () => {
  ff('-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=10:duration=2', '-pix_fmt', 'yuv420p', path.join(dir, 'short.mp4'));
  const mk = (name, extra) => base(name, { duration: 9, media_lazy: true, events: [{ id: 'f', type: 'media_full', t_in: 1, t_out: 7, media: 'short.mp4', cover_ui: true, loop: true, ...extra }] });
  // number each distinct picture in order of first appearance, then look at the biggest step between neighbouring output frames
  const biggestStep = (frame) => {
    const ids = new Map(); let prev = null, worst = 0;
    for (let t = 1.6; t < 6.4; t += 0.1) {
      const h = crypto.createHash('md5').update(frame(t)).digest('hex');
      if (!ids.has(h)) ids.set(h, ids.size);
      const k = ids.get(h);
      if (prev !== null) worst = Math.max(worst, Math.abs(k - prev));
      prev = k;
    }
    return { worst, distinct: ids.size };
  };
  const looped = biggestStep(render(mk('loop', {})));
  const fitted = biggestStep(render(mk('fit', { fit: 'slow' })));
  assert.ok(looped.worst >= 5, `the old behaviour jumps back to the start (step of ${looped.worst} pictures)`);
  assert.ok(fitted.worst <= 1, `fitted: neighbouring output frames are neighbouring pictures (step ${fitted.worst})`);
  assert.ok(fitted.distinct >= 15, 'and it really plays through the clip');
});
