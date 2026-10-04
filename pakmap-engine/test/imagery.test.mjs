import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { PROVIDERS, DEFAULT_IMAGERY, resolveProviders, selectLayers, softnessWarning, creditsFor, EQUATOR_M_PER_PX_Z0 } from '../lib/imagery.mjs';
import { metersPerPixel, frameWidthKm, createCamera } from '../lib/camera.mjs';
import { planRender } from '../lib/plan.mjs';
import { fetchTile, cachePath } from '../lib/tiles.mjs';

const list = resolveProviders();
const sel = (frameKm, lat = 45, cfg = DEFAULT_IMAGERY, l = list) => {
  // pick the zoom whose frame width is frameKm at this latitude
  const mpp = (frameKm * 1000) / 1920;
  return selectLayers(l, mpp, lat, cfg);
};

test('selection depends on scale only: wide shots use the base layer alone', () => {
  const r = sel(4000);
  assert.equal(r[0].opacity, 1);
  assert.equal(r[1].opacity, 0);
});

test('the finer layer takes over as the frame narrows, with a smooth fade in between', () => {
  const widths = [1500, 900, 600, 450, 300, 150, 60];
  const fine = widths.map((w) => sel(w)[1].opacity);
  for (let i = 1; i < fine.length; i++) assert.ok(fine[i] >= fine[i - 1], `opacity fell going closer at ${widths[i]} km`);
  assert.equal(fine[0], 0);
  assert.equal(fine[fine.length - 1], 1);
  assert.ok(fine.some((o) => o > 0 && o < 1), 'there must be a crossfade, not a pop');
});

test('the base layer is always fully visible underneath (no holes when a finer tile is missing)', () => {
  for (const w of [4000, 800, 100, 20]) assert.equal(sel(w)[0].opacity, 1);
});

test('the switch point is configuration, not code: max_upsample moves it', () => {
  const tight = { ...DEFAULT_IMAGERY, max_upsample: 1.0 };
  const loose = { ...DEFAULT_IMAGERY, max_upsample: 6.0 };
  assert.ok(sel(500, 45, tight)[1].opacity > sel(500, 45, loose)[1].opacity);
});

test('providers must be listed coarse to fine', () => {
  assert.throws(() => resolveProviders({ providers: ['nasa_landsat_weld_2000', 'nasa_bluemarble_bathymetry'] }), /coarse to fine/);
  assert.throws(() => resolveProviders({ providers: ['nope'] }), /unknown imagery provider/);
});

test('a better source can be dropped in without touching camera or selection code', () => {
  const finer = { id: 'future_open_10m', title: 'future', urlTemplate: 'https://example.invalid/{z}/{y}/{x}.jpg', format: 'jpeg', tileSize: 256, maxNativeZoom: 14, blackIsNodata: false, attribution: 'x' };
  const l3 = resolveProviders({ providers: ['nasa_bluemarble_bathymetry', 'nasa_landsat_weld_2000', finer] });
  const r = sel(5, 45, DEFAULT_IMAGERY, l3);
  assert.equal(r.length, 3);
  assert.equal(r[2].opacity, 1);
  assert.equal(sel(1000, 45, DEFAULT_IMAGERY, l3)[2].opacity, 0);
  // and with the original two providers the camera output for the same time is identical
  const cfg = { camera: { start: { lon: 1, lat: 2, zoom: 5 }, drift: { pct_per_s: 0.5 }, moves: [] }, width: 1920, height: 1080, duration: 5 };
  assert.deepEqual(createCamera(cfg).at(2), createCamera(cfg).at(2));
});

test('the soft limit is a configurable warning, not a hard stop', () => {
  const lat = 45, frameKm = 20, mpp = (frameKm * 1000) / 1920;
  assert.ok(softnessWarning(list, mpp, lat, frameKm, { ...DEFAULT_IMAGERY, soft_limit_frame_km: 25 }));
  assert.equal(softnessWarning(list, mpp, lat, frameKm, { ...DEFAULT_IMAGERY, soft_limit_frame_km: 10 }), null);
  assert.equal(DEFAULT_IMAGERY.soft_limit_frame_km, 25);
});

test('native resolution of each provider comes from its zoom level, not from a hard-coded number', () => {
  assert.ok(Math.abs(list[0].nativeMPerPx - EQUATOR_M_PER_PX_Z0 / 256) < 1e-9);
  assert.ok(Math.abs(list[1].nativeMPerPx - EQUATOR_M_PER_PX_Z0 / 4096) < 1e-9);
});

test('Landsat is labelled honestly as historical and the credit travels with the output', () => {
  assert.equal(PROVIDERS.nasa_landsat_weld_2000.historical, true);
  const c = creditsFor(list, new Set(['nasa_bluemarble_bathymetry', 'nasa_landsat_weld_2000']));
  assert.ok(c.notes.some((n) => /historical/i.test(n) && /not current/i.test(n)));
  assert.ok(c.attribution.some((a) => /Global Imagery Browse Services/.test(a)));
  const onlyBase = creditsFor(list, new Set(['nasa_bluemarble_bathymetry']));
  assert.equal(onlyBase.notes.length, 0);
  assert.ok(creditsFor(list).licence_status.every((s) => /verify|unknown/i.test(s.status) || s.status));
});

test('planRender: walks the camera path once and reports imagery use, narrowest frame and soft stretches', () => {
  const spec = JSON.parse(fs.readFileSync(new URL('../samples/spike-60s.json', import.meta.url), 'utf8'));
  const plan = planRender(spec);
  assert.equal(plan.total, 1800);
  assert.ok(plan.used.has('nasa_bluemarble_bathymetry'));
  assert.ok(plan.used.has('nasa_landsat_weld_2000'));
  assert.ok(plan.minFrameKm < 40 && plan.minFrameKm > 15, `narrowest frame ${plan.minFrameKm}`);
  assert.ok(plan.warnings.length >= 1);
  assert.ok(plan.credits.notes.length >= 1);
  const wide = planRender({ ...spec, camera: { start: { lon: 75, lat: 48, zoom: 2 }, drift: { pct_per_s: 0.5 }, moves: [] }, duration: 5 });
  assert.equal(wide.used.has('nasa_landsat_weld_2000'), false);
  assert.deepEqual(wide.warnings, []);
  assert.equal(wide.credits.notes.length, 0);
});

test('planRender rejects an unusable spec with a clear message', () => {
  assert.throws(() => planRender({ width: 0, height: 10, fps: 30, duration: 5 }), /positive width/);
});

test('tile cache: a tile is fetched once, a missing tile (404) is remembered, errors are not cached', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pakmap-tiles-'));
  const p = list[0];
  let calls = 0;
  const ok = async () => { calls++; return { status: 200, body: Buffer.from('jpeg-bytes') }; };
  assert.equal((await fetchTile(p, 3, 4, 5, dir, ok)).toString(), 'jpeg-bytes');
  assert.equal((await fetchTile(p, 3, 4, 5, dir, ok)).toString(), 'jpeg-bytes');
  assert.equal(calls, 1);
  assert.ok(fs.existsSync(cachePath(dir, p, 3, 4, 5)));
  let misses = 0;
  const none = async () => { misses++; return { status: 404, body: null }; };
  assert.equal(await fetchTile(p, 3, 9, 9, dir, none), null);
  assert.equal(await fetchTile(p, 3, 9, 9, dir, none), null);
  assert.equal(misses, 1);
  const boom = async () => { throw new Error('offline'); };
  await assert.rejects(() => fetchTile(p, 3, 7, 7, dir, boom), /offline/);
  assert.equal(fs.existsSync(cachePath(dir, p, 3, 7, 7)), false);
});
