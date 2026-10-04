// Photo cards, filmstrip, sticker and full-screen interludes in a real render: flat green
// background, synthetic pictures (solid colours) so every pixel can be predicted.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { lonLatToWorld, createCamera } from '../lib/camera.mjs';
import { stripLayout, cardRect } from '../lib/layout.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RENDER = path.join(HERE, '..', 'render.mjs');
const W = 1920, H = 1080, FPS = 10, BG = [59, 93, 58];

function toolsAvailable() {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
}
const skip = toolsAvailable() || false;
const ff = (...a) => { const r = spawnSync('ffmpeg', ['-v', 'error', '-y', ...a]); assert.equal(r.status, 0, String(r.stderr)); };

let cached = null;
function render() {
  if (cached) return cached;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-media-golden-'));
  ff('-f', 'lavfi', '-i', 'color=c=0x285ac8:size=1280x720', '-frames:v', '1', path.join(dir, 'blue.jpg'));
  ff('-f', 'lavfi', '-i', 'color=c=0xe6821e:size=1280x720', '-frames:v', '1', path.join(dir, 'orange.jpg'));
  ff('-f', 'lavfi', '-i', 'color=c=red:size=200x300', '-vf', "format=rgba,geq=r=220:g=30:b=30:a='if(gt(X,99),255,0)'", '-frames:v', '1', path.join(dir, 'sticker.png'));
  ff('-f', 'lavfi', '-i', 'color=c=0xff00ff:size=640x360:rate=10:duration=3', '-pix_fmt', 'yuv420p', path.join(dir, 'clip.mp4'));
  const cards = ['blue', 'orange', 'blue', 'orange', 'blue', 'orange'].map((c, i) => ({ media: `${c}.jpg`, label: `CARD ${i + 1}` }));
  const spec = {
    width: W, height: H, fps: FPS, duration: 14, output: path.join(dir, 'm.mp4'), cache_dir: path.join(dir, 'cache'), base_dir: dir,
    imagery_enabled: false, flat_only: true,
    camera: { start: { lon: 0, lat: 0, zoom: 5 }, drift: { pct_per_s: 1.2, heading_deg: 70 }, moves: [] },
    events: [
      { id: 'hud', type: 'hud_title', t_in: 0.5, t_out: 14, label: 'PART 1', sub: 'THE EMPTY HALF' },
      { id: 'dot', type: 'cluster', t_in: 0.5, t_out: 14, points: [[3, 2]], size: 30, color: '#FBE040' },
      { id: 'pip', type: 'pip', t_in: 1.0, t_out: 4.0, anchor: 'tr', shape: 'landscape', media: 'blue.jpg', label: 'LABEL' },
      { id: 'strip', type: 'filmstrip', t_in: 4.5, t_out: 8.0, cards },
      { id: 'stk', type: 'sticker', t_in: 8.2, t_out: 9.8, media: 'sticker.png', lon: 0, lat: 0, height_frac: 0.4 },
      { id: 'full', type: 'media_full', t_in: 10.0, t_out: 12.0, media: 'clip.mp4', dissolve_s: 0.5 },
      { id: 'pip2', type: 'pip', t_in: 10.6, t_out: 11.8, anchor: 'tl', shape: 'landscape', media: 'orange.jpg', label: 'OVER FOOTAGE' },
      { id: 'over', type: 'stat', anchor: 'bc', t_in: 10.5, t_out: 11.9, value_from: 8, value_to: 8, format: '0 TIME ZONES' },
    ],
  };
  const f = path.join(dir, 'spec.json');
  fs.writeFileSync(f, JSON.stringify(spec));
  const r = spawnSync('node', [RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 300000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', spec.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  cached = { raw };
  return cached;
}
const frameAt = (t) => { const n = Math.round(t * FPS); return render().raw.subarray(n * W * H * 3, (n + 1) * W * H * 3); };
const px = (f, x, y) => { const i = (y * W + x) * 3; return [f[i], f[i + 1], f[i + 2]]; };
function bbox(f, pred, x0 = 0, y0 = 0, x1 = W, y1 = H) {
  let minx = 1e9, miny = 1e9, maxx = -1, maxy = -1, n = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const i = (y * W + x) * 3; if (pred(f[i], f[i + 1], f[i + 2])) { n++; if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; } }
  return { minx, miny, maxx, maxy, n, w: maxx - minx + 1, h: maxy - miny + 1 };
}
// where a map point is on screen at time t, from the same camera the renderer uses
const CAMERA = { camera: { start: { lon: 0, lat: 0, zoom: 5 }, drift: { pct_per_s: 1.2, heading_deg: 70 }, moves: [] }, width: W, height: H, duration: 14, freeze: [[10, 12]] };
const screenOf = (lon, lat, t) => {
  const c = createCamera(CAMERA).at(t), [cx, cy] = lonLatToWorld(c.lon, c.lat), [x, y] = lonLatToWorld(lon, lat), k = 512 * Math.pow(2, c.zoom);
  return [W / 2 + (x - cx) * k, H / 2 + (y - cy) * k];
};
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: got ${a}, want ${b} +/- ${tol}`);
const isWhite = (r, g, b) => r > 238 && g > 238 && b > 238;
const isYellow = (r, g, b) => r > 235 && g > 205 && b < 110;
const isBlue = (r, g, b) => b > 170 && r < 70 && g < 120;
const isOrange = (r, g, b) => r > 200 && g > 100 && g < 160 && b < 70;

test('photo card: 420 x 303 white-bordered card, 63 px from the right edge, picture inside, yellow label under it', { skip }, () => {
  // the card is anchored to the map, so it moves with the camera drift from the moment it appears
  const f = frameAt(2.5), want = cardRect({ anchor: 'tr' });
  const [x1, y1] = screenOf(0, 0, 1.0), [x2, y2] = screenOf(0, 0, 2.5), dx = x2 - x1, dy = y2 - y1;
  const card = bbox(f, isWhite, 1200, 100, W, 600);
  near(card.w, 420, 3, 'card width'); near(card.h, 303, 3, 'card height'); near(card.maxx, 1857 + dx, 3, 'right edge (63 px margin, plus the drift since it appeared)'); near(card.miny, want.y + dy, 3, 'top');
  const c = px(f, Math.round(1647 + dx), Math.round(want.y + dy + 150));
  assert.ok(isBlue(...c), `picture shows inside the card (${c})`);
  const label = bbox(f, isYellow, 1200, Math.round(want.y + dy + want.h), W, Math.round(want.y + dy + want.h + 120));
  near(label.h, 42, 3, 'label chip height'); near(label.miny - (want.y + dy + want.h), 6, 3, 'label gap');
});

test('photo card: snaps in translucent, fades out plainly, gone afterwards', { skip }, () => {
  const centre = (t) => { const [dx, dy] = [screenOf(0, 0, t)[0] - screenOf(0, 0, 1.0)[0], screenOf(0, 0, t)[1] - screenOf(0, 0, 1.0)[1]]; return px(frameAt(t), Math.round(1647 + dx), Math.round(340 + dy)); };
  const first = centre(1.0), mid = centre(3.8), done = centre(4.3);
  assert.ok(first[2] > 90 && first[2] < 150, `first frame is about 40 % picture over the map (${first})`);
  assert.ok(isBlue(...centre(2.5)));
  assert.ok(mid[2] > 90 && mid[2] < 170, `fading out (${mid})`);
  assert.deepEqual(done.map((v, i) => Math.abs(v - BG[i]) < 8), [true, true, true], 'gone after t_out');
});

test('filmstrip: six cards of 240 px on a 256 px pitch, picking up the right pictures, each with its label', { skip }, () => {
  const f = frameAt(7.0), rects = stripLayout(6);
  const [sx, sy] = [screenOf(0, 0, 7.0)[0] - screenOf(0, 0, 4.5)[0], screenOf(0, 0, 7.0)[1] - screenOf(0, 0, 4.5)[1]].map(Math.round);
  const y = rects[0].y + Math.round(rects[0].h / 2) + sy;
  rects.forEach((r, i) => {
    const mid = px(f, r.x + sx + Math.round(r.w / 2), y);
    assert.ok(i % 2 === 0 ? isBlue(...mid) : isOrange(...mid), `card ${i + 1} shows the ${i % 2 ? 'orange' : 'blue'} picture (${mid})`);
    const label = bbox(f, isYellow, r.x + sx, r.y + r.h + sy, r.x + sx + r.w, r.y + r.h + sy + 80);
    assert.ok(label.n > 200, `card ${i + 1} has its yellow label`);
  });
  const row = [];
  for (let x = 0; x < W; x++) { const [r, g, b] = px(f, x, y); row.push(isBlue(r, g, b) || isOrange(r, g, b)); }
  const segs = []; let s = null;
  row.forEach((v, x) => { if (v && s === null) s = x; if (!v && s !== null) { segs.push([s, x - 1]); s = null; } });
  assert.equal(segs.length, 6, `six picture areas in a row (${segs.length})`);
  near(segs[1][0] - segs[0][0], 256, 3, 'pitch');
  near(segs[0][1] - segs[0][0] + 1 + 10, 240, 3, 'card width (picture + 2 x 5 px border)');
});

test('filmstrip cards arrive one after another', { skip }, () => {
  const f = frameAt(4.8), rects = stripLayout(6), sx = 0;
  const [, dy0] = [0, screenOf(0, 0, 4.8)[1] - screenOf(0, 0, 4.5)[1]], y = rects[0].y + Math.round(rects[0].h / 2) + Math.round(dy0);
  const shown = rects.map((r) => !px(f, r.x + 120 + sx + Math.round(screenOf(0, 0, 4.8)[0] - screenOf(0, 0, 4.5)[0]), y).every((v, i) => Math.abs(v - BG[i]) < 8));
  assert.deepEqual(shown, [true, true, false, false, false, false], 'at 0.3 s only the first two cards are in');
});

test('sticker: 40 % of the frame high, standing on its map point, transparent parts stay transparent', { skip }, () => {
  const f = frameAt(9.0);
  const red = bbox(f, (r, g, b) => r > 180 && g < 70 && b < 70, 300, 0, 1700, H);
  near(red.h, 432, 4, 'sticker height'); near(red.w, 144, 5, 'only the opaque half of the picture');
  near(red.maxy, screenOf(0, 0, 9.0)[1], 3, 'bottom sits on the map point (which has drifted with the camera)');
});

test('full-screen interlude: a linear cross-dissolve both ways, HUD and stat chip stay on top', { skip }, () => {
  const mag = (t) => px(frameAt(t), 960, 540);
  near(mag(10.0)[0], BG[0], 8, 'nothing yet at t_in');
  near(mag(10.25)[0], (255 + BG[0]) / 2, 22, 'half way through the dissolve in');
  assert.ok(mag(11.0)[0] > 235 && mag(11.0)[1] < 20 && mag(11.0)[2] > 235, `fully magenta in the middle (${mag(11.0)})`);
  near(mag(11.75)[0], (255 + BG[0]) / 2, 22, 'half way through the dissolve out');
  near(mag(12.2)[0], BG[0], 8, 'gone after t_out');
  const hud = bbox(frameAt(11.0), isWhite, 0, 0, 700, 108);
  near(hud.h, 67, 2, 'HUD title chip still drawn over the footage');
  assert.ok(bbox(frameAt(11.0), isYellow, 700, 800, 1300, 1000).n > 500, 'stat chip number still drawn over the footage');
});

test('the map holds still under the interlude and carries on drifting afterwards', { skip }, () => {
  const centroid = (t) => { const b = bbox(frameAt(t), isYellow, 0, 150, W, 800); return [(b.minx + b.maxx) / 2, (b.miny + b.maxy) / 2, b.n]; };
  const before = centroid(10.0), after = centroid(12.0), early = centroid(2), later = centroid(4);
  assert.ok(before[2] > 100 && after[2] > 100, 'the tracking dot is visible');
  near(after[0], before[0], 1.6, 'x unchanged across the interlude'); near(after[1], before[1], 1.6, 'y unchanged across the interlude');
  assert.ok(Math.hypot(later[0] - early[0], later[1] - early[1]) > 8, 'before the interlude the map drifts');
  assert.ok(Math.hypot(centroid(13.5)[0] - after[0], centroid(13.5)[1] - after[1]) > 8, 'and it drifts again afterwards');
});

test('a photo card can sit over the full-screen footage (cards are drawn above the interlude)', { skip }, () => {
  const f = frameAt(11.2);
  const card = bbox(f, isWhite, 0, 150, 900, 620);
  near(card.w, 420, 4, 'card width over the footage'); near(card.h, 303, 4, 'card height over the footage');
  const [dx, dy] = [screenOf(0, 0, 11.2)[0] - screenOf(0, 0, 10.6)[0], screenOf(0, 0, 11.2)[1] - screenOf(0, 0, 10.6)[1]];
  assert.ok(isOrange(...px(f, Math.round(44 + 210 + dx), Math.round(190 + 150 + dy))), 'its picture shows on top of the magenta footage');
});
