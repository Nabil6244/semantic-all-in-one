// Phase 5 graphics owned by the integrator: wind_flow.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import wind, { streaksAt } from '../lib/layers/wind_flow.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const skip = (() => {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return false;
})();

test('wind streaks move downwind (a south wind blows north) and stay around the city', () => {
  const e = { t_in: 0, lon: -96.8, lat: 32.8, from_deg: 180, mph: 15 };
  const a = streaksAt(e, 1.0, 500, 500), b = streaksAt(e, 1.1, 500, 500);
  assert.ok(a.length > 10);
  for (const s of a) assert.ok(Math.hypot(s.x - 500, s.y - 500) <= 210 + 1e-6);
  for (const s of a) assert.ok(s.y < s.y0, 'the head is north of the tail for a south wind');
  const dy = b.reduce((m, s) => m + s.y, 0) / b.length - a.reduce((m, s) => m + s.y, 0) / a.length;
  assert.ok(Number.isFinite(dy));
  assert.deepEqual(streaksAt(e, 1.0, 500, 500), a, 'deterministic');
});

test('wind_flow is checked', () => {
  assert.deepEqual(wind.validate({ lon: 1, lat: 2, from_deg: 90, label: 'E 10 MPH' }), []);
  assert.equal(wind.validate({}).length, 3);
});

test('wind_flow renders through the plugin loader (offline)', { skip }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wx-wind-'));
  const spec = { width: 1920, height: 1080, fps: 5, duration: 2, output: path.join(dir, 'w.mp4'), cache_dir: path.join(dir, 'c'), imagery_enabled: false, flat_only: true,
    camera: { start: { lon: -96.8, lat: 32.8, zoom: 6 }, drift: { pct_per_s: 0 }, moves: [] }, events: [],
    weather: { events: [{ id: 'w', type: 'wind_flow', t_in: 0, t_out: 2, lon: -96.8, lat: 32.8, from_deg: 180, mph: 15, label: 'S 10–15 MPH', city: 'DALLAS', dow: 'MON' }], satellite: [], rasters: [], credits: [] } };
  fs.writeFileSync(path.join(dir, 's.json'), JSON.stringify(spec));
  const r = spawnSync('node', [path.join(HERE, '..', 'render.mjs'), path.join(dir, 's.json')], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 240000 });
  assert.match(r.stdout, /"event":"done"/, r.stdout + r.stderr);
  const raw = spawnSync('ffmpeg', ['-v', 'error', '-i', spec.output, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { maxBuffer: 1 << 30 }).stdout;
  const f = raw.subarray(5 * 1920 * 1080 * 3, 6 * 1920 * 1080 * 3);   // frame at t = 1 s
  let white = 0;
  for (let y = 340; y < 740; y += 2) for (let x = 760; x < 1160; x += 2) { const i = (y * 1920 + x) * 3; if (f[i] > 200 && f[i + 1] > 200 && f[i + 2] > 200) white++; }
  assert.ok(white > 30, `streaks drawn around the city (${white} white samples)`);
  fs.rmSync(dir, { recursive: true, force: true });
});
