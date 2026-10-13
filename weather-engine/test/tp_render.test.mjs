// Weather Teamplate's graphics in a real render (no imagery, no network): the chapter card, a keyword card with its red box,
// the dip under the cards, the context tag, the count-up stat and a place tag that steps aside while a card is up.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { tagRect, TP } from '../lib/wxu_tp_style.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WX_RENDER = path.join(HERE, '..', 'render.mjs');
const W = 1920, H = 1080, FPS = 5;

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;

function spec(dir) {
  return {
    width: W, height: H, fps: FPS, duration: 14, output: path.join(dir, 'tp.mp4'), cache_dir: path.join(dir, 'cache'), base_dir: dir,
    imagery_enabled: false, flat_only: true,
    camera: { start: { lon: -84, lat: 27, zoom: 5.2 }, moves: [] },
    events: [],
    weather: {
      events: [
        { id: 'ch', type: 'tp_title', kind: 'chapter', title: 'HURRICANE IAN', kicker: 'SEPTEMBER 2022', t_in: 0.4, t_out: 4.0 },
        { id: 'kw', type: 'tp_title', kind: 'keyword', words: ['THE', 'PATH'], accent: 1, t_in: 6.0, t_out: 9.0 },
        { id: 'tag', type: 'tp_tag', tone: 'black', text: 'NHC BEST TRACK', t_in: 9.1, t_out: 14 },
        { id: 'st', type: 'tp_stat', value: 5, label: 'EXTREME WIND WARNINGS', sub: 'NWS', count_s: 1, t_in: 6, t_out: 14, big_in: 9.2, big_out: 12.4 },
        { id: 'pl', type: 'tp_place', lon: -84, lat: 27, text: 'FORT MYERS', t_in: 4.5, t_out: 14, hide: [[5.9, 9.3]] },
        { id: 'd1', type: 'tp_dip', t_in: 0.3, t_out: 4.3 },
        { id: 'd2', type: 'tp_dip', t_in: 5.9, t_out: 12.7 },
        { id: 'v', type: 'tp_vignette', t_in: 0, t_out: 14 },
      ],
      satellite: [], rasters: [], credits: [],
    },
  };
}

const frame = (raw, t) => { const n = Math.round(t * FPS); return raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const px = (f, x, y) => { const i = (Math.round(y) * W + Math.round(x)) * 3; return [f[i], f[i + 1], f[i + 2]]; };
const lum = (f, x0, y0, x1, y1) => { let s = 0, n = 0; for (let y = y0; y < y1; y += 4) for (let x = x0; x < x1; x += 4) { const [r, g, b] = px(f, x, y); s += r + g + b; n++; } return s / n; };
const count = (f, x0, y0, x1, y1, ok) => { let n = 0; for (let y = y0; y < y1; y += 2) for (let x = x0; x < x1; x += 2) if (ok(px(f, x, y))) n++; return n; };
const white = ([r, g, b]) => r > 225 && g > 225 && b > 225;
const red = ([r, g, b]) => r > 170 && g < 60 && b < 80;
const orange = ([r, g, b]) => r > 200 && g > 60 && g < 120 && b < 80;
let dir = null;

test('teamplate cards, tags and numbers render where their layouts say', { skip }, () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'weather-tp-'));
  const s = spec(dir);
  const f = path.join(dir, 'tp.json');
  fs.writeFileSync(f, JSON.stringify(s));
  const r = spawnSync('node', [WX_RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', s.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  const C = TP.chapter;
  // the chapter title is wiped in by 3 s (white letters at its baseline), and the frame is dimmed under it
  assert.ok(count(frame(raw, 3), C.left, C.titleY - 70, C.left + 900, C.titleY, white) > 200, 'chapter title');
  assert.ok(lum(frame(raw, 3), 0, 0, 400, 300) < lum(frame(raw, 5), 0, 0, 400, 300) - 20, 'the dip darkens the frame');
  // the keyword card: a red box around the key word in the middle of the frame
  assert.ok(count(frame(raw, 8), 600, 420, 1400, 620, red) > 500, 'red key-word box');
  assert.ok(count(frame(raw, 8), 400, 420, 1400, 620, white) > 300, 'white words');
  // the place tag steps aside under the card, and is back after it
  const at = (t) => count(frame(raw, t), 700, 380, 1220, 560, orange);
  assert.ok(at(5.4) > 100, `place tag before the card: ${at(5.4)}`);
  assert.equal(count(frame(raw, 7.6), 0, 0, W, H, orange), 0, 'no orange tag while the card is up');
  // the black context tag at the top centre
  const t = tagRect('black', 200);
  const [r0, g0, b0] = px(frame(raw, 13), t.x + 4, t.y + 4);
  assert.ok(r0 < 30 && g0 < 30 && b0 < 30, 'black tag');
  // the stat has counted to its value: big white digits left of centre
  assert.ok(count(frame(raw, 11.5), TP.stat.left - 20, TP.stat.baseline - 120, TP.stat.left + 160, TP.stat.baseline, white) > 300, 'stat digits');
  // then a compact orange tag top right
  assert.ok(count(frame(raw, 13.5), 1300, 40, 1860, 110, orange) > 300, 'compact stat tag');
});

test.after(() => { if (dir) fs.rmSync(dir, { recursive: true, force: true }); });
