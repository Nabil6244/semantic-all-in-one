// Post-event graphics rendered for real (no imagery, no network): each plugin draws where its layout says, the rain map's grid
// (a pakMap value_overlay from an .asc file) is coloured by the inch ramp, everything hides under full-screen footage, and a
// broken event stops the render with a message naming it.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { barsLayout, recordLayout, hydroLayout, rainLegendLayout, timelineLayout } from '../lib/wxu_post_charts.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WX_RENDER = path.join(HERE, '..', 'render.mjs');
const W = 1920, H = 1080, FPS = 2;

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;
let dir = null;
const tmp = () => (dir ||= fs.mkdtempSync(path.join(os.tmpdir(), 'weather-post-')));

const bars = [{ label: 'PORT ARTHUR', value: 47.48, text: '47.48', note: '' }, { label: 'HOUSTON HOBBY', value: 37.01, text: '37.01', note: '' },
  { label: 'HOUSTON (IAH)', value: 31.26, text: '31.26', note: '' }];
const hydroValues = Array.from({ length: 96 }, (_, i) => (i > 40 && i < 46 ? null : 5 + 30 * Math.exp(-((i - 50) ** 2) / 300)));

function spec(d, name, extra = {}) {
  // an .asc grid like weather/post/mrms.write_asc writes: 20 x 10 cells of 0.1 degree, 0 to 38 inches
  const rows = Array.from({ length: 10 }, (_, r) => Array.from({ length: 20 }, (_, c) => (c * 2).toFixed(2)).join(' '));
  fs.writeFileSync(path.join(d, 'rain.asc'), `ncols 20\nnrows 10\nxllcorner -97\nyllcorner 29\ncellsize 0.1\nnodata_value -9999\n${rows.join('\n')}\n`);
  return {
    width: W, height: H, fps: FPS, duration: 12, output: path.join(d, `${name}.mp4`), cache_dir: path.join(d, 'cache'), base_dir: d,
    imagery_enabled: false, flat_only: true, watermark: { text: 'Explains-It' },
    camera: { start: { lon: -96, lat: 29.5, zoom: 7 }, moves: [] },
    events: [{ id: 'rain', type: 'value_overlay', t_in: 0, t_out: 3, data: 'file:rain.asc', bbox: [-97, 29, -95, 30], ramp: [[1, '#A7D8F0'], [10, '#F2E03A'], [40, '#D58CF0']], min: 1, max: 40, opacity: 1, fade_in: 0.01 }],
    weather: { satellite: [], rasters: [], credits: [], events: [
      { id: 'leg', type: 'post_rainlegend', t_in: 0, t_out: 3, title: 'RAINFALL', unit: 'IN', sub: 'AUG 25 7 AM CDT – SEP 1 7 AM CDT', stops: [{ value: 1, color: '#A7D8F0', text: '1' }, { value: 40, color: '#D58CF0', text: '40' }], foot: 'MRMS radar estimate' },
      { id: 'chip', type: 'post_chip', t_in: 0, t_out: 3, lon: -95.36, lat: 29.98, label: 'HOUSTON (IAH)', value: '31.26 IN', count: true, sub: 'AUG 25–SEP 1 · OBSERVED', tag: '', kind: 'rain' },
      { id: 'bars', type: 'post_bars', t_in: 3, t_out: 6, title: 'RAINFALL TOTALS', sub: 'AUG 25–SEP 1, 2017 · OBSERVED', unit: 'IN', decimals: 2, bars, foot: 'Station data: NOAA RCC-ACIS' },
      { id: 'rec', type: 'post_record', t_in: 6, t_out: 9, headline: 'WETTEST DAY ON RECORD', place: 'HOUSTON AREA', value: '16.07 IN', date: 'AUG 27, 2017', prev_label: 'PREVIOUS RECORD', prev_value: '10.34 IN', prev_date: 'JUN 26, 1989', since: 'RECORDS SINCE 1888', foot: 'NOAA RCC-ACIS', kind: 'rain' },
      { id: 'tl', type: 'post_timeline', t_in: 6, t_out: 9, title: 'TIMELINE', ticks: Array.from({ length: 8 }, (_, k) => ({ f: (k + 0.5) / 8, label: `AUG ${24 + k}` })), marks: [{ f: 0.24, when: 'AUG 25 · 10 PM', title: 'LANDFALL', detail: 'CATEGORY 4 HURRICANE · 130 MPH' }, { f: 0.44, when: 'AUG 27', title: 'WETTEST DAY', detail: '16.07 IN' }] },
      { id: 'hy', type: 'post_hydrograph', t_in: 9, t_out: 12, title: 'BUFFALO BAYOU', sub: 'GAGE HEIGHT (FT)', values: hydroValues, per_day: 24, days: ['AUG 25', 'AUG 26', 'AUG 27', 'AUG 28'], lines: [{ label: 'MAJOR FLOOD 32.0 FT', value: 32, color: '#B03AF0' }], crest: { index: 50, text: '35.0 FT' } },
      { id: 'ba', type: 'post_beforeafter', t_in: 9, t_out: 12, frames: [{ at: 0, label: 'BEFORE', date: 'AUG 22, 2017' }, { at: 1.5, label: 'AFTER', date: 'AUG 31, 2017' }], crossfade: 1 },
    ] },
    ...extra,
  };
}

function render(s, d) {
  const f = path.join(d, `${path.basename(s.output, '.mp4')}.json`);
  fs.writeFileSync(f, JSON.stringify(s));
  return spawnSync('node', [WX_RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 300000 });
}
const decode = (file) => spawnSync('ffmpeg', ['-v', 'error', '-i', file, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
const frame = (raw, t) => { const n = Math.round(t * FPS); return raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const px = (f, x, y) => { const i = (Math.round(y) * W + Math.round(x)) * 3; return [f[i], f[i + 1], f[i + 2]]; };
const isPanel = ([r, g, b]) => r < 40 && g < 50 && b < 60;
const isYellow = ([r, g, b]) => r > 200 && g > 180 && b < 120;
const isGrass = ([r, g, b]) => Math.abs(r - 0x3b) < 12 && Math.abs(g - 0x5d) < 12 && Math.abs(b - 0x3a) < 12;   // the offline background

test('every post-event graphic draws where its layout says', { skip }, (t) => {
  const d = tmp();
  const r = render(spec(d, 'all'), d);
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = decode(path.join(d, 'all.mp4'));
  const f1 = frame(raw, 2.5), f2 = frame(raw, 5.5), f3 = frame(raw, 8.5), f4 = frame(raw, 11.5);
  // the rain grid is coloured (not the plain background) and the legend panel sits bottom left
  const g = rainLegendLayout(2);
  assert.ok(isPanel(px(f1, g.x + 6, g.y + g.h / 2)), `rain legend panel: ${px(f1, g.x + 6, g.y + g.h / 2)}`);
  assert.ok(!isGrass(px(f1, 990, 545)), `rain map drawn at the centre: ${px(f1, 990, 545)}`);
  const B = barsLayout(3);
  assert.ok(isPanel(px(f2, B.x + 8, B.y + B.h / 2)), 'bars panel');
  // the longest bar is fully grown: its far end is coloured, not the dark track
  const end = px(f2, B.barX + B.barMax - 6, B.rows[0].cy);
  assert.ok(end[2] > 150, `first bar reaches the end of its track: ${end}`);
  const R = recordLayout();
  assert.ok(isPanel(px(f3, R.x + 8, R.y + R.h - 8)), 'record badge panel');
  const stamp = px(f3, R.x + R.w / 2 - 150, R.y + 40);
  assert.ok(stamp[2] > 150 && stamp[0] < 100, `blue rain stamp: ${stamp}`);
  const T = timelineLayout();
  assert.ok(isYellow(px(f3, T.axisX + 30, T.axisY)), `timeline axis drawn in: ${px(f3, T.axisX + 30, T.axisY)}`);
  const Hy = hydroLayout(hydroValues, [{ value: 32 }]);
  assert.ok(isPanel(px(f4, Hy.x + 8, Hy.y + Hy.h - 8)), 'hydrograph panel');
  assert.ok(isPanel(px(f4, W - 63 - 40, 48 + 20)), `before/after label top right: ${px(f4, W - 63 - 40, 68)}`);
  t.diagnostic(`frames in ${d}`);
});

test('post-event graphics hide under full-screen footage', { skip }, () => {
  const d = tmp();
  const img = path.join(d, 'red.png');
  spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=1920x1080', '-frames:v', '1', img]);
  const s = spec(d, 'cover');
  s.events = [...s.events, { id: 'foot', type: 'media_full', t_in: 4, t_out: 5.5, media: 'red.png' }];
  const r = render(s, d);
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const B = barsLayout(3), p = px(frame(decode(path.join(d, 'cover.mp4')), 5), B.x + 8, B.y + B.h / 2);
  assert.ok(p[0] > 200 && p[1] < 60, `footage covers the bars: ${p}`);
});

test('a broken post-event graphic stops the render and is named', { skip }, () => {
  const d = tmp();
  const s = spec(d, 'bad');
  s.weather.events.push({ id: 'oops', type: 'post_bars', t_in: 1, t_out: 2, title: 'X', bars: [] });
  const r = render(s, d);
  assert.match(r.stdout + r.stderr, /oops.*post_bars needs 1 to 8 bars/);
});

test.after(() => { if (dir && !process.env.KEEP_POST_FRAMES) fs.rmSync(dir, { recursive: true, force: true }); });
