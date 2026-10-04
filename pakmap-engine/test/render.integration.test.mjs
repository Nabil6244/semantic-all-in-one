// Real render through the real page and ffmpeg, no network and no imagery
// (flat colour instead of tiles): proves the renderer is deterministic, honours
// the camera timeline and writes the sidecar. Skipped when Chromium/ffmpeg
// are not available on the machine.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RENDER = path.join(HERE, '..', 'render.mjs');

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable();

const baseSpec = (dir, name) => ({
  width: 480, height: 270, fps: 10, duration: 2,
  output: path.join(dir, name), cache_dir: path.join(dir, 'cache'),
  imagery_enabled: false, flat_only: true, debug_hud: true,
  camera: { start: { lon: 20, lat: 45, zoom: 3 }, drift: { pct_per_s: 0.6, heading_deg: 90 }, moves: [{ type: 'push_in', t: 0.5, dur: 1.0, to: { zoom: 4 } }] },
});

function render(spec, dir, name) {
  const specFile = path.join(dir, `${name}.json`);
  fs.writeFileSync(specFile, JSON.stringify(spec));
  const r = spawnSync('node', [RENDER, specFile], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 120000 });
  const events = r.stdout.trim().split('\n').filter(Boolean).map((l) => JSON.parse(l));
  return { r, events };
}
const frameHashes = (file) => spawnSync('ffmpeg', ['-v', 'error', '-i', file, '-f', 'framemd5', '-'], { encoding: 'utf8' }).stdout
  .split('\n').filter((l) => /^\d/.test(l)).map((l) => l.split(',').pop().trim());

test('same spec renders the exact same frames twice', { skip: skip || false }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-it-'));
  const a = render(baseSpec(dir, 'a.mp4'), dir, 'a'), b = render(baseSpec(dir, 'b.mp4'), dir, 'b');
  assert.equal(a.events.at(-1).event, 'done', a.r.stdout + a.r.stderr);
  assert.equal(b.events.at(-1).event, 'done', b.r.stdout + b.r.stderr);
  const ha = frameHashes(path.join(dir, 'a.mp4')), hb = frameHashes(path.join(dir, 'b.mp4'));
  assert.equal(ha.length, 20);
  assert.deepEqual(ha, hb);
  assert.ok(new Set(ha).size > 10, 'frames should differ from each other (the camera moves)');
});

test('a bad timeline fails before any browser starts, with a clear message', { skip: skip || false }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-it-'));
  const spec = baseSpec(dir, 'bad.mp4');
  spec.camera.moves = [{ type: 'teleport', t: 0, dur: 1, to: { zoom: 2 } }];
  const { events, r } = render(spec, dir, 'bad');
  assert.equal(r.status, 1);
  const last = events.at(-1);
  assert.equal(last.event, 'error');
  assert.match(last.message, /type must be/);
  assert.equal(fs.existsSync(path.join(dir, 'bad.mp4')), false);
});

test('the sidecar records credits, imagery used and the narrowest frame', { skip: skip || false }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-it-'));
  const { events } = render(baseSpec(dir, 'c.mp4'), dir, 'c');
  assert.equal(events.at(-1).event, 'done');
  const side = JSON.parse(fs.readFileSync(path.join(dir, 'c.mp4.pakmap.json'), 'utf8'));
  assert.equal(side.frames, 20);
  assert.ok(Array.isArray(side.credits.attribution));
  assert.ok(side.min_frame_km > 0);
});

test('overlays render deterministically too (chips, counters, dots, lines)', { skip: skip || false }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-it-'));
  const mk = (name) => ({
    ...baseSpec(dir, name), duration: 3,
    events: [
      { id: 'hud', type: 'hud_title', t_in: 0.2, t_out: 3, label: 'PART 1', sub: 'THE EMPTY HALF' },
      { id: 'stat', type: 'stat', anchor: 'br', t_in: 0.2, t_out: 3, value_from: 0, value_to: 54, format: '0% OF THE LAND', sub: 'DEMO' },
      { id: 'line', type: 'line', kind: 'flow', t_in: 0.3, t_out: 3, coords: [[10, 40], [30, 50]] },
      { id: 'dots', type: 'dots', t_in: 0.3, t_out: 3, seed: 4, random: { bbox: [15, 40, 30, 50], n: 400, seed: 9 } },
    ],
  });
  const a = render(mk('oa.mp4'), dir, 'oa'), b = render(mk('ob.mp4'), dir, 'ob');
  assert.equal(a.events.at(-1).event, 'done', a.r.stdout + a.r.stderr);
  assert.equal(b.events.at(-1).event, 'done', b.r.stdout + b.r.stderr);
  assert.deepEqual(frameHashes(path.join(dir, 'oa.mp4')), frameHashes(path.join(dir, 'ob.mp4')));
});

test('an overlay timeline that breaks the rules is refused before rendering', { skip: skip || false }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-it-'));
  const spec = baseSpec(dir, 'bad2.mp4');
  spec.events = [1, 2, 3].map((i) => ({ id: `s${i}`, type: 'stat', value_to: i, t_in: 0, t_out: 2 }));
  const { events, r } = render(spec, dir, 'bad2');
  assert.equal(r.status, 1);
  assert.match(events.at(-1).message, /3 stat chips/);
});

test('zooming out into the globe leaves clean space around it, not the earlier larger globes', { skip: skip || false }, () => {
  // Regression: the 2D compositing canvas kept the previous frame, and the globe leaves the sky transparent, so on a
  // zoom-out (a smaller globe every frame) the earlier globes showed through as rippled bands.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-it-'));
  const spec = baseSpec(dir, 'g.mp4');
  Object.assign(spec, { flat_only: false, debug_hud: false, duration: 1.6 });
  spec.camera = { start: { lon: -150, lat: 55, zoom: 3 }, drift: { pct_per_s: 0 }, moves: [{ type: 'pull_back', t: 0, dur: 1.2, to: { zoom: 1.7 } }] };
  const { events, r } = render(spec, dir, 'g');
  assert.equal(events.at(-1).event, 'done', r.stdout + r.stderr);
  const W = spec.width, H = spec.height, n = Math.round(spec.duration * spec.fps);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', path.join(dir, 'g.mp4'), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 28 }).stdout;
  assert.equal(raw.length, W * H * 3 * n);
  const px = (frame, x, y) => { const o = frame * W * H * 3 + (y * W + x) * 3; return [raw[o], raw[o + 1], raw[o + 2]]; };
  for (const frame of [n - 6, n - 1]) {
    for (const [x, y] of [[2, 2], [W - 3, 2], [2, H - 3], [W - 3, H - 3]]) {
      const [rr, gg, bb] = px(frame, x, y);
      assert.ok(rr + gg + bb < 60, `frame ${frame}: corner (${x},${y}) is ${rr},${gg},${bb}, expected dark space (a leftover of an earlier frame)`);
    }
  }
});
