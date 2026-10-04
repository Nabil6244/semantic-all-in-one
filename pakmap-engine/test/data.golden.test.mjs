// Data layers in a real render (flat green background, no imagery, no network):
// the rainfall overlay is coloured from the bundled CHIRPS grid and clipped to Kenya, the Poland
// outline keeps Poland's real size, streaks and dots land where they should.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { lonLatToWorld, metersPerPixel } from '../lib/camera.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RENDER = path.join(HERE, '..', 'render.mjs');
const W = 1920, H = 1080, FPS = 5, CENTER = { lon: 37.9, lat: 0.6, zoom: 5.9 };
const BG = [59, 93, 58];

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  if (!fs.existsSync(path.join(HERE, '..', '..', 'map_scene', 'data', 'countries.json.gz'))) return 'countries data not found';
  return null;
}
const skip = toolsAvailable() || false;

let cached = null;
function render() {
  if (cached) return cached;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-data-golden-'));
  const spec = {
    width: W, height: H, fps: FPS, duration: 12, output: path.join(dir, 'd.mp4'), cache_dir: path.join(dir, 'cache'),
    imagery_enabled: false, flat_only: true,
    camera: { start: CENTER, drift: { pct_per_s: 0 }, moves: [] },
    events: [
      { id: 'rain', type: 'value_overlay', t_in: 0.5, t_out: 8, data: 'bundled:rainfall_chirps', clip_iso: ['KEN'], opacity: 1, fade_in: 0.2 },
      { id: 'pol', type: 'ghost_shape', t_in: 0.5, t_out: 8, iso: 'POL', to: { lon: 30.5, lat: 1.0 }, fade_in: 0.2, fill_opacity: 0.5 },
      { id: 'fillsom', type: 'fill', iso: ['SOM'], role: 'compare', opacity: 0.6, t_in: 0.5, t_out: 8, fade_in: 0.2 },
      { id: 'streak', type: 'streak', t_in: 8.5, t_out: 12, region_iso: ['KEN'], n: 60, seed: 3, stagger_s: 0.5, draw_s: 0.4 },
      { id: 'dots', type: 'dots', t_in: 8.5, t_out: 12, data: 'bundled:populated_places', region_iso: ['KEN'], per_million: 150, seed: 2, reveal_s: 0.5, color: '#FBE040' },
    ],
  };
  const f = path.join(dir, 'spec.json');
  fs.writeFileSync(f, JSON.stringify(spec));
  const r = spawnSync('node', [RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 300000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const plan = JSON.parse(r.stdout.split('\n').find((l) => l.includes('"event":"plan"')));
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', spec.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  cached = { raw, plan, side: JSON.parse(fs.readFileSync(`${spec.output}.pakmap.json`, 'utf8')) };
  return cached;
}
const frameAt = (t) => { const n = Math.round(t * FPS); return render().raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const toPx = (lon, lat) => {
  const [cx, cy] = lonLatToWorld(CENTER.lon, CENTER.lat), [x, y] = lonLatToWorld(lon, lat), k = 512 * Math.pow(2, CENTER.zoom);
  return [Math.round(W / 2 + (x - cx) * k), Math.round(H / 2 + (y - cy) * k)];
};
function mean(f, lon, lat, r = 5) {
  const [px, py] = toPx(lon, lat); let s = [0, 0, 0], n = 0;
  for (let y = py - r; y <= py + r; y++) for (let x = px - r; x <= px + r; x++) { const i = (y * W + x) * 3; s[0] += f[i]; s[1] += f[i + 1]; s[2] += f[i + 2]; n++; }
  return s.map((v) => v / n);
}
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: got ${a}, want ${b} +/- ${tol}`);
const isBg = (c) => c.every((v, i) => Math.abs(v - BG[i]) < 6);

test('rainfall overlay: dry north-west is orange/yellow, the wet western highlands are green-blue, outside Kenya is untouched', { skip }, () => {
  const f = frameAt(4);
  const dry = mean(f, 35.6, 3.12), wet = mean(f, 34.75, 0.28);
  assert.ok(dry[0] > 190 && dry[2] < 120, `Lodwar should be warm (orange/yellow), got ${dry.map(Math.round)}`);
  assert.ok(wet[2] > wet[0] + 25 || wet[1] > wet[0] + 40, `Kakamega should be cool (green/blue), got ${wet.map(Math.round)}`);
  assert.ok(isBg(mean(f, 45, -3)), 'ocean east of Kenya has no overlay');
  assert.ok(isBg(mean(f, 38, 6.5, 3)), 'Ethiopia has no overlay: it is clipped to Kenya');
});

test('rainfall overlay fades in and is gone after its window', { skip }, () => {
  assert.ok(isBg(mean(frameAt(0.2), 35.6, 3.12)), 'not there before it starts');
  assert.ok(!isBg(mean(frameAt(2), 35.6, 3.12)));
  const c = mean(frameAt(8.2), 35.6, 3.12);
  assert.ok(isBg(c), `gone after t_out, got ${c.map(Math.round)}`);
});

test('Poland outline keeps Poland\'s true size when moved onto the equator', { skip }, () => {
  const f = frameAt(4), [cx, cy] = toPx(30.5, 1.0);
  // count pixels that carry the blue fill tint inside a box around the moved shape
  let n = 0;
  for (let y = cy - 260; y < cy + 260; y++) for (let x = cx - 400; x < cx + 400; x++) {
    if (x < 0 || y < 0 || x >= W || y >= H) continue;
    const i = (y * W + x) * 3, r = f[i], g = f[i + 1], b = f[i + 2];
    if (b > 100 && r < 60 && b > g) n++;
  }
  const mpp = metersPerPixel(1.0, CENTER.zoom), km2 = (n * mpp * mpp) / 1e6;
  assert.ok(Math.abs(km2 - 312696) / 312696 < 0.12, `Poland measured ${Math.round(km2)} km2 on screen, expected about 312,700`);
});

test('layer facts are reported for the author: areas, data range, dot count', { skip }, () => {
  const facts = Object.fromEntries(render().plan.layer_facts.map((x) => [x.id, x]));
  assert.ok(Math.abs(facts.pol.area_km2 - 312696) / 312696 < 0.02);
  assert.ok(facts.rain.data_range[1] > 1800);
  assert.ok(facts.dots.dots > 200);
  assert.ok(render().side.credits.attribution.some((a) => /CHIRPS/.test(a)));
  assert.ok(render().side.credits.attribution.some((a) => /Natural Earth/.test(a)));
});

test('streaks are drawn over Kenya and dots cluster around the big towns', { skip }, () => {
  const f = frameAt(11.5);
  const [x0, y0] = toPx(33.9, 5), [x1, y1] = toPx(41.9, -4.7);
  let white = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const i = (y * W + x) * 3; if (f[i] > 200 && f[i + 1] > 200 && f[i + 2] > 200) white++; }
  assert.ok(white > 500, `white streak pixels: ${white}`);
  const yellow = (lon, lat, r = 60) => { const [px, py] = toPx(lon, lat); let n = 0; for (let y = py - r; y < py + r; y++) for (let x = px - r; x < px + r; x++) { const i = (y * W + x) * 3; if (f[i] > 235 && f[i + 1] > 205 && f[i + 2] < 110) n++; } return n; };
  assert.ok(yellow(36.82, -1.29) > yellow(35.6, 3.12) * 2, 'more dots around Nairobi than around Lodwar');
});

test('fill events: a country is tinted with its role colour for exactly its window, with a white outline', { skip }, () => {
  const inside = (t) => mean(frameAt(t), 46.0, 4.5);
  const t4 = inside(4), tint = [0.6 * 0x4a + 0.4 * BG[0], 0.6 * 0x7f + 0.4 * BG[1], 0.6 * 0xb5 + 0.4 * BG[2]];
  t4.forEach((v, i) => near(v, tint[i], 14, `fill colour channel ${i}`));
  assert.ok(isBg(inside(0.2)), 'not there before it starts');
  assert.ok(isBg(inside(8.2)), 'gone after it ends');
  assert.ok(isBg(mean(frameAt(4), 39.5, 6.0, 3)), 'neighbouring Ethiopia stays untouched');
});
