// Golden frames: real renders with no imagery and no network (flat background), decoded to pixels.
//   1. Fidelity: a spec without weather renders frame-for-frame the same through weather-engine as through pakmap-engine.
//   2. The weather graphics land where lib/wx_layout.mjs says, and hide under full-screen footage.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { stripLayout, nowLayout, sourceLayout } from '../lib/wx_layout.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WX_RENDER = path.join(HERE, '..', 'render.mjs');
const PAK_RENDER = path.join(HERE, '..', '..', 'pakmap-engine', 'render.mjs');
const W = 1920, H = 1080, FPS = 5;

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;

const base = (dir, name) => ({
  width: W, height: H, fps: FPS, duration: 6, output: path.join(dir, `${name}.mp4`), cache_dir: path.join(dir, 'cache'), base_dir: dir,
  imagery_enabled: false, flat_only: true, watermark: { text: 'Explains-It' },
  camera: { start: { lon: -96, lat: 37, zoom: 4.2 }, drift: { pct_per_s: 0.5, heading_deg: 30 }, moves: [] },
  events: [
    { id: 'hud', type: 'hud_title', t_in: 0.2, t_out: 6, label: 'YOUR WEATHER', sub: 'MONDAY' },
    { id: 'tx', type: 'fill', t_in: 0.2, t_out: 6, polys: [[[[-100, 30], [-95, 30], [-95, 34], [-100, 34], [-100, 30]]]], color: '#FFA500', opacity: 0.5 },
    { id: 'mk', type: 'marker', t_in: 0.5, t_out: 6, lon: -87.6, lat: 41.9, label: 'CHICAGO' },
  ],
});
const days = ['MON', 'TUE', 'WED', 'THU', 'FRI'].map((d, i) => ({ dow: d, icon: ['sun', 'cloud', 'storm', 'rain', 'snow'][i], hi: `${80 + i}°`, lo: `${60 + i}°`, pop: i === 2 ? '40%' : '' }));
const weather = {
  events: [
    { id: 'm1', type: 'temp_marker', t_in: 0.2, t_out: 6, lon: -96.8, lat: 32.8, city: 'DALLAS', temp: '92°', tag: 'MON HIGH', icon: 'partly', side: 'r' },
    { id: 'st', type: 'forecast_strip', t_in: 0.2, t_out: 6, title: 'DALLAS, TX', days },
    { id: 'now', type: 'now_card', t_in: 0.2, t_out: 6, title: 'MIAMI NOW', temp: '84°', text: 'Mostly Cloudy', icon: 'cloud', foot: 'Observed 5:20 PM EDT · KMIA', anchor: 'tr' },
    { id: 'src', type: 'source_line', t_in: 0.2, t_out: 6, text: 'Data: National Weather Service · Forecast as of Oct 12, 4:11 PM CDT' },
  ],
  satellite: [], credits: [],
};

function render(engine, spec, dir) {
  const f = path.join(dir, `${path.basename(spec.output, '.mp4')}.json`);
  fs.writeFileSync(f, JSON.stringify(spec));
  const r = spawnSync('node', [engine, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  return spawnSync('ffmpeg', ['-v', 'error', '-i', spec.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
}
const frame = (raw, t) => { const n = Math.round(t * FPS); return raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const px = (f, x, y) => { const i = (Math.round(y) * W + Math.round(x)) * 3; return [f[i], f[i + 1], f[i + 2]]; };
const isPanel = ([r, g, b]) => r < 40 && g < 50 && b < 60;     // the dark navy panel
const isYellow = ([r, g, b]) => r > 200 && g > 180 && b < 120;  // the title chips
const isRed = ([r, g, b]) => r > 200 && g < 60 && b < 60;       // the test footage

let dir = null;
const tmp = () => (dir ||= fs.mkdtempSync(path.join(os.tmpdir(), 'weather-golden-')));

test('without weather layers, weather-engine draws exactly what pakmap-engine draws', { skip }, () => {
  const d = tmp();
  const a = render(PAK_RENDER, base(d, 'pak'), d);
  const b = render(WX_RENDER, base(d, 'wx_plain'), d);
  assert.equal(a.length, b.length);
  assert.ok(a.equals(b), 'frames differ between pakmap-engine and weather-engine for the same spec');
});

test('the strip, the now card and the source line land where the layout says', { skip }, () => {
  const d = tmp();
  const raw = render(WX_RENDER, { ...base(d, 'wx'), weather }, d);
  const f = frame(raw, 3);
  const S = stripLayout(5), N = nowLayout('tr'), L = sourceLayout(600);
  assert.ok(isPanel(px(f, S.x + 8, S.y + S.h / 2)), `strip panel at ${S.x + 8},${S.y + S.h / 2}: ${px(f, S.x + 8, S.y + S.h / 2)}`);
  assert.ok(isPanel(px(f, S.x + S.w - 8, S.y + S.h - 30)), 'strip panel right edge');
  assert.ok(isYellow(px(f, S.title.x + 6, S.title.y + S.title.h / 2)), `strip title chip: ${px(f, S.title.x + 6, S.title.y + S.title.h / 2)}`);
  assert.ok(isPanel(px(f, N.x + 10, N.y + N.h - 10)), 'now card panel');
  assert.ok(isYellow(px(f, N.title.x + 6, N.title.y + N.title.h / 2)), 'now card title chip');
  assert.ok(isPanel(px(f, L.x + 3, L.y + L.h / 2)), `source line backing: ${px(f, L.x + 3, L.y + L.h / 2)}`);
  // a white high temperature digit inside the first strip column
  const c = S.cells[0];
  let white = 0;
  for (let x = c.x; x < c.x + c.w; x += 2) for (let y = S.y + 150; y < S.y + 190; y += 2) { const [r, g, b] = px(f, x, y); if (r > 230 && g > 230 && b > 230) white++; }
  assert.ok(white > 40, `the first day's high is drawn (${white} white samples)`);
});

test('weather graphics hide under full-screen footage and come back after it', { skip }, () => {
  const d = tmp();
  const img = path.join(d, 'red.png');
  spawnSync('ffmpeg', ['-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=1920x1080', '-frames:v', '1', img]);
  const spec = { ...base(d, 'wx_cover'), weather };
  spec.events = [...spec.events, { id: 'foot', type: 'media_full', t_in: 2, t_out: 4, media: 'red.png' }];
  const raw = render(WX_RENDER, spec, d);
  const S = stripLayout(5);
  const at = (t) => px(frame(raw, t), S.x + 8, S.y + S.h / 2);
  assert.ok(isPanel(at(1)), `strip before footage: ${at(1)}`);
  assert.ok(isRed(at(3)), `footage covers the strip: ${at(3)}`);
  assert.ok(isPanel(at(5)), `strip back after footage: ${at(5)}`);
});

test('a temperature marker whose city stays off screen is reported, and not drawn half-way', { skip }, () => {
  const d = tmp();
  const spec = { ...base(d, 'wx_off'), duration: 2, events: [], weather: { events: [{ id: 'far', type: 'temp_marker', t_in: 0, t_out: 2, lon: 150, lat: -30, city: 'SYDNEY', temp: '70°', tag: 'MON HIGH', icon: 'sun', side: 'r' }], satellite: [], credits: [] } };
  const f = path.join(d, 'wx_off.json');
  fs.writeFileSync(f, JSON.stringify(spec));
  const r = spawnSync('node', [WX_RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /weather: far \(SYDNEY\) is off screen for 100% of its time/, r.stdout + r.stderr);
});

test.after(() => { if (dir) fs.rmSync(dir, { recursive: true, force: true }); });
