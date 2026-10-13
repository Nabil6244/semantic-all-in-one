// Weather News graphics in a real render (no imagery, no network): the counter, the radar legend, storm points with a
// label, storm reports with their PRELIMINARY legend, and an NHC-style cone (pakMap fill) and dashed track (pakMap line).
// Tile loops (radar/satellite) need network: their maths is in news_unit / the Python tests, and they are rendered for real
// in the phase-3 report.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { counterRect, legendRect, reportsRect } from '../lib/wxu_news_anim.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WX_RENDER = path.join(HERE, '..', 'render.mjs');
const W = 1920, H = 1080, FPS = 5;

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;

const ramp = [[5, '#04E9E7'], [20, '#02FD02'], [35, '#FDF802'], [50, '#FD0000'], [65, '#F800FD'], [75, '#FDFDFD']].map(([dbz, color]) => ({ dbz, color }));
function spec(dir) {
  return {
    width: W, height: H, fps: FPS, duration: 6, output: path.join(dir, 'news.mp4'), cache_dir: path.join(dir, 'cache'), base_dir: dir,
    imagery_enabled: false, flat_only: true, watermark: { text: 'Explains-It' },
    camera: { start: { lon: -84, lat: 27, zoom: 5.2 }, moves: [] },
    events: [
      { id: 'hud', type: 'hud_title', t_in: 0.2, t_out: 6, label: 'HURRICANE IAN', sub: 'TEST' },
      { id: 'cone', type: 'fill', t_in: 0.2, t_out: 6, polys: [[[[-84, 24], [-80, 24], [-79, 31], [-83, 31], [-84, 24]]]], color: '#FFFFFF', opacity: 0.35, outline_color: '#FFFFFF' },
      { id: 'trk', type: 'line', kind: 'connector', t_in: 0.2, t_out: 6, coords: [[-82.6, 25.5], [-82.0, 27.0], [-81.0, 29.0]], color: '#FFFFFF', width: 4, draw_s: 1 },
    ],
    weather: {
      events: [
        { id: 'cnt', type: 'counter', t_in: 0.2, t_out: 6, value: 46, label: 'TORNADO REPORTS', sub: 'PRELIMINARY · SPC', anchor: 'tr', count_s: 1 },
        { id: 'leg', type: 'radar_legend', t_in: 0.2, t_out: 6, stops: ramp, labels: [{ dbz: 20, text: 'LIGHT' }, { dbz: 50, text: 'HEAVY' }, { dbz: 65, text: 'HAIL' }], title: 'RADAR' },
        { id: 'pts', type: 'storm_points', t_in: 0.2, t_out: 6, name: 'IAN', points: [
          { lon: -82.6, lat: 25.5, at: 0.5, color: '#FF8F20', label: 'CAT 4 · 155 MPH · WED 2 PM', size: 12, ring: true },
          { lon: -81.0, lat: 29.0, at: 1.0, color: '#FFFFCC', label: '' }] },
        { id: 'rep', type: 'storm_reports', t_in: 0.2, t_out: 6, title: 'STORM REPORTS', sub: 'PRELIMINARY',
          points: [{ lon: -86, lat: 30, kind: 'tornado', at: 0.5 }, { lon: -85, lat: 31, kind: 'hail', at: 0.7 }],
          legend: [{ kind: 'tornado', label: 'TORNADO', color: '#FF2020', total: 1 }, { kind: 'hail', label: 'HAIL', color: '#22C55E', total: 1 }] },
        { id: 'src', type: 'source_line', t_in: 0.2, t_out: 6, text: 'Data: NOAA National Hurricane Center · test' },
      ],
      satellite: [], rasters: [], credits: [],
    },
  };
}

const frame = (raw, t) => { const n = Math.round(t * FPS); return raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const px = (f, x, y) => { const i = (Math.round(y) * W + Math.round(x)) * 3; return [f[i], f[i + 1], f[i + 2]]; };
const isPanel = ([r, g, b]) => r < 40 && g < 50 && b < 60;
const near = ([r, g, b], [R, G, B], tol = 40) => Math.abs(r - R) < tol && Math.abs(g - G) < tol && Math.abs(b - B) < tol;
let dir = null;

test('news graphics render where their layouts say', { skip }, () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'weather-news-'));
  const s = spec(dir);
  const f = path.join(dir, 'news.json');
  fs.writeFileSync(f, JSON.stringify(s));
  const r = spawnSync('node', [WX_RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  if (process.env.WX_NEWS_FRAME) spawnSync('ffmpeg', ['-v', 'error', '-y', '-ss', '4', '-i', s.output, '-frames:v', '1', process.env.WX_NEWS_FRAME]);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', s.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  const fr = frame(raw, 4);
  // counter panel (top right) with its yellow bar, and a white digit
  const c = counterRect('tr', 300);
  assert.ok(isPanel(px(fr, 1920 - 63 - 20, c.y + c.h / 2)), `counter panel: ${px(fr, 1920 - 63 - 20, c.y + c.h / 2)}`);
  // radar legend: the bar's first colour (cyan) at its left end
  const L = legendRect();
  assert.ok(near(px(fr, L.x + 20, L.y + 48), [4, 233, 231], 60), `legend bar start: ${px(fr, L.x + 20, L.y + 48)}`);
  assert.ok(isPanel(px(fr, L.x + 6, L.y + 6)), 'legend panel');
  // storm reports legend panel on the right
  const R = reportsRect(2, 100);
  assert.ok(isPanel(px(fr, R.x + R.w - 6, R.y + 6)), `reports panel: ${px(fr, R.x + R.w - 6, R.y + 6)}`);
  // the orange category-4 dot is drawn somewhere on the map
  let orange = 0;
  for (let y = 100; y < 1000; y += 2) for (let x = 100; x < 1800; x += 2) if (near(px(fr, x, y), [255, 143, 32], 30)) orange++;
  assert.ok(orange > 20, `cat-4 dot pixels: ${orange}`);
  // the counter has finished counting by t = 4 (its digits are white inside the panel)
  let white = 0;
  for (let y = c.y + 50; y < c.y + 130; y += 2) for (let x = 1920 - 63 - 280; x < 1920 - 63 - 20; x += 2) { const [a, b, d] = px(fr, x, y); if (a > 230 && b > 230 && d > 230) white++; }
  assert.ok(white > 60, `counter digits: ${white}`);
});

test.after(() => { if (dir) fs.rmSync(dir, { recursive: true, force: true }); });
