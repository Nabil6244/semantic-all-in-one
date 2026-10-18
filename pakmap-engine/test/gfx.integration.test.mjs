// gfx-core templates inside a real pakMap render (offline: flat colour, no tiles): a map_template event draws its template over the map,
// follows a place on the map, and leaves the frames without it untouched. Skipped when Chromium/ffmpeg are missing.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { validateEvents } from '../lib/events.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RENDER = path.join(HERE, '..', 'render.mjs');
const tpl = (fam, id) => JSON.parse(fs.readFileSync(path.join(HERE, '..', '..', 'gfx-core', 'templates', fam, `${id}.json`), 'utf8'));
const skip = (() => {
  if (spawnSync('ffmpeg', ['-version']).status !== 0) return 'ffmpeg not found';
  try { createRequire(path.join(HERE, '..', '..', 'flow-engine', 'package.json'))('playwright'); } catch { return 'playwright not found'; }
  return null;
})();

const spec = (dir, name, events) => ({
  width: 960, height: 540, fps: 10, duration: 5, output: path.join(dir, name), cache_dir: path.join(dir, 'cache'),
  imagery_enabled: false, flat_only: true,
  camera: { start: { lon: 20, lat: 45, zoom: 3 }, drift: { pct_per_s: 0.6, heading_deg: 90 }, moves: [] }, events,
});
function render(s, dir, name) {
  const f = path.join(dir, `${name}.json`); fs.writeFileSync(f, JSON.stringify(s));
  const r = spawnSync('node', [RENDER, f], { encoding: 'utf8', env: { ...process.env, PAKMAP_GL: 'software' }, timeout: 180000 });
  return { r, last: JSON.parse(r.stdout.trim().split('\n').filter(Boolean).at(-1)) };
}
const frameAt = (video, t, out) => spawnSync('ffmpeg', ['-v', 'error', '-y', '-ss', String(t), '-i', video, '-frames:v', '1', out]);
const md5 = (f) => spawnSync('md5', ['-q', f], { encoding: 'utf8' }).stdout.trim();

test('validation: a map_template needs a template with items, and follow needs lon/lat', () => {
  const ok = { id: 'a', type: 'map_template', t_in: 0, t_out: 3, template: tpl('stats', 'rank_bars') };
  assert.deepEqual(validateEvents([ok], 5).errors, []);
  assert.match(validateEvents([{ ...ok, template: null }], 5).errors.join(' '), /needs template/);
  assert.match(validateEvents([{ ...ok, follow: { lon: 1 } }], 5).errors.join(' '), /follow/);
});

test('a map_template draws over the map, follows a place, and the frames without it are unchanged', { skip: skip || false }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-gfx-'));
  const events = [
    { id: 'cols', type: 'map_template', t_in: 0.2, t_out: 4.5, template: tpl('stats', 'month_columns'), slots: {} },
    { id: 'reg', type: 'map_template', t_in: 0.2, t_out: 4.5, template: tpl('geo', 'region_label'), slots: { label: 'KIMBERLEY', tag: 'EXTREMES IN THE NORTH' }, follow: { lon: 20, lat: 45 } },
  ];
  const a = render(spec(dir, 'a.mp4', events), dir, 'a'), base = render(spec(dir, 'b.mp4', []), dir, 'b');
  assert.equal(a.last.event, 'done', a.r.stdout + a.r.stderr);
  assert.equal(base.last.event, 'done', base.r.stdout + base.r.stderr);
  for (const [v, n] of [['a.mp4', 'a_3'], ['b.mp4', 'b_3'], ['a.mp4', 'a_0'], ['b.mp4', 'b_0']]) frameAt(path.join(dir, v), n.endsWith('3') ? 3.5 : 0, path.join(dir, `${n}.png`));
  assert.notEqual(md5(path.join(dir, 'a_3.png')), md5(path.join(dir, 'b_3.png')), 'the template must change the frame');
  assert.equal(md5(path.join(dir, 'a_0.png')), md5(path.join(dir, 'b_0.png')), 'before t_in the frame is the plain map');
  fs.copyFileSync(path.join(dir, 'a_3.png'), process.env.GFX_SAMPLE_OUT || path.join(dir, 'sample.png'));
});
