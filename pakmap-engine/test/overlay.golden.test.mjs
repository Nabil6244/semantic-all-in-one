// Golden-frame tests for the overlay layers. A real render (flat green background,
// no imagery, no network) is decoded to pixels and the chips are measured against
// the numbers taken from the reference videos (docs/pakmap/phase0/phase0-report.md).
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
const W = 1920, H = 1080, FPS = 10;

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;

const spec = (dir) => ({
  width: W, height: H, fps: FPS, duration: 8,
  output: path.join(dir, 'golden.mp4'), cache_dir: path.join(dir, 'cache'),
  imagery_enabled: false, flat_only: true,
  watermark: { text: 'Explains-It' },
  camera: { start: { lon: 0, lat: 0, zoom: 5 }, drift: { pct_per_s: 0 }, moves: [] },
  events: [
    { id: 'hud', type: 'hud_title', t_in: 0.5, t_out: 8, label: 'PART 1', sub: 'THE EMPTY HALF' },
    { id: 'stat', type: 'stat', anchor: 'br', t_in: 0.5, t_out: 8, value_from: 312700, value_to: 312700, format: '#,##0 KM', sub: 'POLAND · NORTHERN KENYA 313,100 KM²' },
    { id: 'cap', type: 'caption', anchor: 'bl', t_in: 0.5, t_out: 8, text: "SOMETHING YOU CAN'T SEE" },
    { id: 'mk', type: 'marker', t_in: 0.5, t_out: 8, lon: 0, lat: 8, label: 'GARISSA', value: '163,000', side: 'r' },
    { id: 'flow', type: 'line', kind: 'flow', t_in: 1.0, t_out: 8, coords: [[-9, 1], [9, 1]] },
    { id: 'dots', type: 'dots', t_in: 3.0, t_out: 8, seed: 1, reveal_s: 3.1, random: { bbox: [-8, -6, 8, -1], n: 1500, seed: 2, uniform: 1 } },
  ],
});

let frames = null;
function render() {
  if (frames) return frames;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-golden-'));
  const f = path.join(dir, 'spec.json');
  fs.writeFileSync(f, JSON.stringify(spec(dir)));
  const r = spawnSync('node', [RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', path.join(dir, 'golden.mp4'), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  frames = { raw, dir, count: raw.length / (W * H * 3) };
  return frames;
}
const frameAt = (t) => { const F = render(); const n = Math.round(t * FPS); return F.raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const px = (f, x, y) => { const i = (y * W + x) * 3; return [f[i], f[i + 1], f[i + 2]]; };
function bbox(f, pred, x0 = 0, y0 = 0, x1 = W, y1 = H) {
  let minx = 1e9, miny = 1e9, maxx = -1, maxy = -1, n = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
    const i = (y * W + x) * 3;
    if (pred(f[i], f[i + 1], f[i + 2])) { n++; if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; }
  }
  return { minx, miny, maxx, maxy, n, w: maxx - minx + 1, h: maxy - miny + 1 };
}
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: got ${a}, want ${b} +/- ${tol}`);
const isWhite = (r, g, b) => r > 240 && g > 240 && b > 240;
const isYellow = (r, g, b) => r > 235 && g > 205 && b < 110;
const isPanel = (r, g, b) => r < 30 && g < 40 && b < 60 && b >= r;

test('HUD: title chip is 67 px high at x=45, y=37 (Reference 1 and 2)', { skip }, () => {
  const f = frameAt(3);
  const t = bbox(f, isWhite, 0, 0, 700, 108);
  near(t.miny, 37, 1, 'title top'); near(t.minx, 45, 2, 'title left'); near(t.h, 67, 2, 'title height');
});

test('HUD: subtitle chip is 39 px high, 8-9 px under the title, at x=44', { skip }, () => {
  const f = frameAt(3);
  const s = bbox(f, (r, g, b) => r > 8 && r < 30 && g > 8 && g < 30 && b > 8 && b < 30, 0, 108, 700, 170);
  near(s.miny, 112, 2, 'subtitle top'); near(s.h, 39, 2, 'subtitle height'); near(s.minx, 44, 2, 'subtitle left');
});

test('subtitle words appear one after another and then stay', { skip }, () => {
  const textPixels = (t) => bbox(frameAt(t), isWhite, 50, 114, 700, 150).n;
  const series = [0.6, 0.9, 1.0, 1.1, 1.3, 2.0].map(textPixels);
  for (let i = 1; i < series.length; i++) assert.ok(series[i] >= series[i - 1], `subtitle text shrank: ${series}`);
  assert.ok(series[0] < series[series.length - 1] * 0.3, 'at the start almost no words show yet');
  assert.ok(series[series.length - 1] > 200, 'all words show at the end');
});

test('stat chip: 156 px high with a sub-line, 63 px from the right edge, 66 px from the bottom', { skip }, () => {
  const f = frameAt(3);
  const p = bbox(f, isPanel, 900, 700, W, H);
  near(p.h, 156, 5, 'stat height'); near(W - 1 - p.maxx, 63, 3, 'right margin'); near(H - 1 - p.maxy, 66, 3, 'bottom margin');
});

test('stat chip: number is 60 px tall (cap height) and yellow', { skip }, () => {
  const f = frameAt(3);
  const all = bbox(f, isYellow, 1100, 800, 1900, 960);
  const first = bbox(f, isYellow, all.minx, 800, all.minx + 45, 960); // first digit only: the comma would hang below the baseline
  near(first.h, 60, 4, 'number cap height');
});

test('line draw: head-first, starts at once, eases out, finished after about 0.9 s', { skip }, () => {
  const orange = (r, g, b) => r > 220 && g > 120 && g < 175 && b < 90;
  const count = (t) => bbox(frameAt(t), orange, 0, 300, W, 700).n;
  const c = [1.1, 1.3, 1.6, 1.9, 2.4].map(count);
  assert.ok(c[0] > 0, 'a visible line on the first frame after the start (no ease-in)');
  for (let i = 1; i < c.length; i++) assert.ok(c[i] >= c[i - 1], `line shrank: ${c}`);
  near(c[3] / c[4], 1, 0.03, 'line done at 0.9 s');
  assert.ok(c[0] / c[4] > 0.15 && c[0] / c[4] < 0.5, `ease-out: 0.1 s in, already well past a ninth drawn (${(c[0] / c[4]).toFixed(2)})`);
});

test('dot density: reveals linearly over about 3.1 s', { skip }, () => {
  const yellowDots = (t) => bbox(frameAt(t), isYellow, 200, 570, 1500, 840).n;
  const total = yellowDots(7.0);
  assert.ok(total > 2000, `dots should be visible (${total})`);
  near(yellowDots(4.5) / total, 0.5, 0.12, 'half way through the reveal');
  near(yellowDots(3.5) / total, 0.16, 0.12, 'early in the reveal');
});

test('watermark is drawn bottom right', { skip }, () => {
  const w = bbox(frameAt(3), (r, g, b) => r > 150 && g > 150 && b > 150, 1650, 1020, W, H); // drawn at 60% opacity
  assert.ok(w.n > 100, 'watermark text should show');
});

test('caption: 44 px caps, chip 108 px high, 66 px above the bottom edge (Reference 2)', { skip }, () => {
  const f = frameAt(3);
  const panel = bbox(f, isPanel, 0, 880, 1100, H);
  near(panel.h, 108, 4, 'caption chip height'); near(H - 1 - panel.maxy, 66, 3, 'bottom margin');
  const yel = bbox(f, isYellow, panel.minx, panel.miny, panel.maxx, panel.maxy);
  const firstLetter = bbox(f, isYellow, yel.minx, panel.miny, yel.minx + 40, panel.maxy);
  near(firstLetter.h, 44, 4, 'caption cap height');
});

test('marker: white ring dot, dark label chip 52 px high beside it with white text', { skip }, () => {
  const f = frameAt(3);
  // dot sits at lat 8 -> 8 degrees north of the centre; find the chip as the dark block right of centre
  const ring = bbox(f, isWhite, 930, 100, 990, 300);
  assert.ok(ring.n > 40, 'ring dot visible');
  const cx = Math.round((ring.minx + ring.maxx) / 2), cy = Math.round((ring.miny + ring.maxy) / 2);
  const chip = bbox(f, (r, g, b) => r < 60 && g < 80 && b < 80 && b >= r - 5, cx + 20, cy - 40, cx + 520, cy + 40);
  near(chip.h, 52, 4, 'marker chip height');
  const text = bbox(f, isWhite, chip.minx + 4, chip.miny, chip.maxx, chip.maxy);
  assert.ok(text.n > 300, 'white label text inside the chip');
  near(chip.minx - cx, 27, 5, 'chip starts 27 px from the dot centre');
});

test('watermark: the channel name is upper-cased; bottom-left puts it in the other corner', { skip }, () => {
  const light = (r, g, b) => r > 150 && g > 150 && b > 150;
  assert.equal(bbox(frameAt(3), light, 60, 1020, 500, H).n, 0, 'nothing bottom left by default');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-wm-'));
  const s2 = spec(dir); s2.duration = 1; s2.events = []; s2.watermark = { text: 'my channel', position: 'bl' }; s2.output = path.join(dir, 'wm.mp4');
  const f = path.join(dir, 'spec.json'); fs.writeFileSync(f, JSON.stringify(s2));
  const r = spawnSync('node', [RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 120000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', s2.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  const fr = raw.subarray(5 * W * H * 3, 6 * W * H * 3);
  assert.ok(bbox(fr, light, 60, 1020, 500, H).n > 100, 'channel name bottom left');
  assert.equal(bbox(fr, light, 1500, 1020, W, H).n, 0, 'nothing bottom right');
});
