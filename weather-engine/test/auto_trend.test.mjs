// temp_trend (phase 2): the chart's maths, the plugin's checks, and a real offline render (no imagery, no network).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { TREND, trendLayout, trendPoints, drawProgress, partialLine, popScale } from '../lib/wxu_auto_trend.mjs';
import { stripLayout, sourceLayout } from '../lib/wx_layout.mjs';
import { validateWxEvents } from '../lib/wx_draw.mjs';
import plugin from '../lib/layers/temp_trend.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const days = [[78, 57], [77, 59], [85, 62], [84, 66], [80, 68], [79, 64], [81, null]]
  .map(([hi, lo], i) => ({ dow: ['TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN', 'MON'][i], hi: `${hi}°`, hi_v: hi, lo: lo == null ? '' : `${lo}°`, lo_v: lo }));

test('the chart sits where the strip sits, inside the frame, clear of the source line', () => {
  for (let n = 3; n <= 7; n++) {
    const L = trendLayout(n), S = stripLayout(n);
    assert.equal(L.x, S.x); assert.equal(L.w, S.w);
    assert.equal(L.y + L.h, S.y + S.h, 'same bottom as the strip');
    assert.ok(L.x >= 0 && L.x + L.w <= 1920 && L.title.y >= 0);
    assert.ok(L.y + L.h <= sourceLayout(600).y, 'above the source line');
    assert.equal(L.cols.length, n);
  }
});

test('highs sit above lows on one scale; the warmest high is highest, the coldest low lowest; a missing low has no point', () => {
  const L = trendLayout(7), P = trendPoints(days, L);
  assert.equal(P.highs.length, 7); assert.equal(P.lows.length, 6);
  const top = Math.min(...P.highs.map((p) => p.y)), bottom = Math.max(...P.lows.map((p) => p.y));
  assert.equal(P.highs.find((p) => p.y === top).text, '85°');
  assert.equal(P.lows.find((p) => p.y === bottom).text, '57°');
  for (let i = 0; i < 6; i++) assert.ok(P.highs[i].y < P.lows[i].y);
  for (const p of [...P.highs, ...P.lows]) assert.ok(p.y >= L.plot.top && p.y <= L.plot.bottom);
  const flat = trendPoints([{ dow: 'A', hi: '70°', hi_v: 70, lo: '70°', lo_v: 70 }, { dow: 'B', hi: '70°', hi_v: 70 }, { dow: 'C', hi: '70°', hi_v: 70 }], trendLayout(3));
  assert.ok(flat.highs.every((p) => Number.isFinite(p.y)));
});

test('the lines draw in from the first day, and each point pops when its line reaches it', () => {
  assert.equal(drawProgress(10, 10, 7), -1);
  assert.equal(drawProgress(10 + TREND.delay + TREND.drawIn / 2, 10, 7), 3);
  assert.equal(drawProgress(100, 10, 7), 6);
  const L = trendLayout(7), P = trendPoints(days, L);
  assert.deepEqual(partialLine(P.highs, -1), []);
  const half = partialLine(P.highs, 2.5);
  assert.equal(half.length, 4);
  assert.ok(half[3].x > P.highs[2].x && half[3].x < P.highs[3].x);
  assert.equal(partialLine(P.lows, 6).length, 6);
  const tIn = 10, reach3 = tIn + TREND.delay + 0.5 * TREND.drawIn;
  assert.equal(popScale(reach3 - 0.01, tIn, 3, 7), 0);
  assert.ok(popScale(reach3 + TREND.pop * 0.6, tIn, 3, 7) > 1, 'overshoots');
  assert.ok(Math.abs(popScale(reach3 + TREND.pop, tIn, 3, 7) - 1) < 1e-9);
});

test('the plugin checks its events and the engine names the event', () => {
  assert.deepEqual(plugin.validate({ title: 'X', days }), []);
  assert.match(plugin.validate({ title: 'X', days: days.slice(0, 2) }).join(), /3 to 7 days/);
  assert.match(plugin.validate({ days }).join(), /needs title/);
  assert.match(plugin.validate({ title: 'X', days: [{ dow: 'A', hi: '1°' }, ...days.slice(0, 3)] }).join(), /day 1 needs dow, hi and hi_v/);
  const errs = validateWxEvents([{ id: 'wx_t', type: 'temp_trend', t_in: 0, t_out: 3, title: 'X', days: days.slice(0, 2) }], 10, [plugin]);
  assert.match(errs.join(), /weather\.events\[0\] \(wx_t\): temp_trend needs 3 to 7 days/);
});

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;

test('a real render draws the panel, the title chip, both lines and the numbers', { skip }, () => {
  const W = 1920, H = 1080, FPS = 5;
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'weather-trend-'));
  const spec = {
    width: W, height: H, fps: FPS, duration: 4, output: path.join(d, 'trend.mp4'), cache_dir: path.join(d, 'cache'), base_dir: d,
    imagery_enabled: false, flat_only: true, camera: { start: { lon: -96, lat: 37, zoom: 4.2 }, moves: [] }, events: [],
    weather: { events: [{ id: 'wx_trend', type: 'temp_trend', t_in: 0.2, t_out: 4, title: 'PHOENIX, AZ · HIGHS AND LOWS', days }], satellite: [], credits: [] },
  };
  const f = path.join(d, 'trend.json');
  fs.writeFileSync(f, JSON.stringify(spec));
  const r = spawnSync('node', [path.join(HERE, '..', 'render.mjs'), f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', spec.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  const n = 3 * FPS, fr = raw.subarray(n * W * H * 3, (n + 1) * W * H * 3);
  const px = (x, y) => { const i = (Math.round(y) * W + Math.round(x)) * 3; return [fr[i], fr[i + 1], fr[i + 2]]; };
  const L = trendLayout(7), P = trendPoints(days, L);
  const [pr, pg, pb] = px(L.x + 8, L.y + L.h / 2);
  assert.ok(pr < 40 && pg < 50 && pb < 60, `panel: ${[pr, pg, pb]}`);
  const [yr, yg, yb] = px(L.title.x + 6, L.title.y + L.title.h / 2);
  assert.ok(yr > 200 && yg > 180 && yb < 120, `title chip: ${[yr, yg, yb]}`);
  const mid = (a, b) => px((a.x + b.x) / 2, (a.y + b.y) / 2);
  const [hr, hg, hb] = mid(P.highs[0], P.highs[1]);
  assert.ok(hr > 200 && hg > 100 && hg < 180 && hb < 120, `the highs line is orange: ${[hr, hg, hb]}`);
  const [lr, lg, lb] = mid(P.lows[0], P.lows[1]);
  assert.ok(lb > 200 && lr < 140, `the lows line is blue: ${[lr, lg, lb]}`);
  let white = 0;
  const p = P.highs[2];
  for (let x = p.x - 30; x < p.x + 30; x += 2) for (let y = p.y - 44; y < p.y - 14; y += 2) { const [a, b, c] = px(x, y); if (a > 220 && b > 220 && c > 220) white++; }
  assert.ok(white > 20, `the number above the warmest high is drawn (${white} white samples)`);
  fs.rmSync(d, { recursive: true, force: true });
});
