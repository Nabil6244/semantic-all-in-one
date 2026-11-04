// Real browser test: two stills through render.mjs on the machine's GPU. Checks the page starts, draws non-blank different frames,
// and the caches work (few materials and geometries for hundreds of bodies). Run: node --test test/render.integration.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url));

test('two stills render: non-blank, different, caches small, no page errors', () => {
  const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'rce-')), 'x.mp4');
  const r = spawnSync('node', [path.join(HERE, '..', 'render.mjs'), '--csv', path.join(HERE, '..', 'samples', 'dday_1944.csv'), '--out', out, '--stills', '19.3,64.3'], { encoding: 'utf8', timeout: 240000 });
  const ev = r.stdout.trim().split('\n').map((l) => JSON.parse(l));
  assert.ok(!ev.some((e) => e.event === 'error'), r.stdout.slice(-400));
  const a = fs.readFileSync(`${out}.t19.3.jpg`), b = fs.readFileSync(`${out}.t64.3.jpg`);
  assert.ok(a.length > 30000 && b.length > 30000, 'blank frame'); assert.notDeepEqual(a, b);
  const perf = ev.find((e) => e.event === 'perf');
  assert.ok(perf.gfx.materials < 400 && perf.gfx.geometries < 400, JSON.stringify(perf.gfx));
  assert.ok(perf.builds.every((x) => x.ms < 3000));
  assert.ok(!ev.some((e) => e.event === 'warning' && /page:/.test(e.message)), 'page errors');
});
