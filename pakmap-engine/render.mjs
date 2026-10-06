// pakMap renderer: node render.mjs <spec.json>
//
// One long-lived MapLibre instance in a hidden, temporary Chromium; the camera
// timeline (lib/camera.mjs) is evaluated for every frame, the map is waited on
// until all tiles are drawn, and the frame is piped to ffmpeg -- so the same
// spec always produces the same video. Separate process from map-engine (Map
// Facts) and flow-engine: its own browser, its own random local port.
//
// stdout: one JSON object per line --
//   {"event":"plan", ...}  {"event":"progress","frame":n,"total":N}
//   {"event":"warning",...}  then {"event":"done",...} or {"event":"error","message":...}

import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import zlib from 'node:zlib';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { planRender } from './lib/plan.mjs';
import { resolveSpecData } from './lib/datasets.mjs';
import { prepareMedia, materializeClip, releaseClips, disposeMedia } from './lib/media.mjs';
import { fetchTile } from './lib/tiles.mjs';
import { parsePointsCsv } from './lib/points.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAPLIBRE_DIST = path.join(HERE, 'node_modules', 'maplibre-gl', 'dist');
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');

function loadPlaywright(spec) {
  for (const dir of [spec.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean)) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}

let countriesCache = null;
function countriesGeoJSON(spec) {
  if (countriesCache) return countriesCache;
  const file = spec.countries_path || path.join(HERE, '..', 'map_scene', 'data', 'countries.json.gz');
  const raw = JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8'));
  countriesCache = JSON.stringify({
    type: 'FeatureCollection',
    features: raw.features.map((f) => ({ type: 'Feature', properties: { iso: f.iso, name: f.n }, geometry: f.g })),
  });
  return countriesCache;
}

function startServer(spec, plan, media) {
  const types = { '.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf' };
  const byId = Object.fromEntries(plan.providers.map((p) => [p.id, p]));
  // user point files (CSV lat,lon) named in the spec are read here and handed to the page as arrays
  const point_files = {};
  for (const [id, file] of Object.entries(spec.points_files || {})) {
    point_files[id] = parsePointsCsv(fs.readFileSync(path.resolve(spec.base_dir || '.', file), 'utf8'), spec.points_order || 'lat,lon');
  }
  const pageSpec = JSON.stringify({ ...spec, imagery: plan.imagery, providers: plan.providers, point_files, media_index: media.index });
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://x');
      const tile = url.pathname.match(/^\/tile\/([\w-]+)\/(\d+)\/(\d+)\/(\d+)$/);
      if (tile) {
        const provider = byId[tile[1]];
        if (!provider) { res.writeHead(404); return res.end(); }
        const buf = await fetchTile(provider, tile[2], tile[3], tile[4], spec.cache_dir);
        if (!buf) { res.writeHead(404); return res.end(); }
        res.writeHead(200, { 'Content-Type': provider.format === 'png' ? 'image/png' : 'image/jpeg' });
        return res.end(buf);
      }
      const med = url.pathname.match(/^\/media\/(m\d+)(?:\/(\d+))?$/);
      if (med) {
        const m = media.files[med[1]];
        if (!m) { res.writeHead(404); return res.end(); }
        if (m.lazy && !m.dir) materializeClip(m, { ffmpeg: spec.ffmpeg || 'ffmpeg', fps: spec.fps });
        let frame = Math.max(1, Number(med[2] ?? 1) + 1);
        if (m.count) frame = Math.min(frame, m.count);   // a lazy clip may hold a frame fewer than its length promised
        const f = m.file || path.join(m.dir, `${String(frame).padStart(5, '0')}.jpg`);
        if (!fs.existsSync(f)) { res.writeHead(404); return res.end(); }
        res.writeHead(200, { 'Content-Type': m.mime || 'image/jpeg' });
        return fs.createReadStream(f).pipe(res);
      }
      if (url.pathname === '/spec.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(pageSpec); }
      if (url.pathname === '/data/countries.geojson') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(countriesGeoJSON(spec)); }
      let file = null;
      if (url.pathname === '/' || url.pathname === '/index.html') file = path.join(HERE, 'page.html');
      else if (url.pathname === '/page.js') file = path.join(HERE, 'page.js');
      else if (/^\/lib\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(HERE, url.pathname);
      else if (/^\/fonts\/[\w.-]+\.ttf$/.test(url.pathname)) file = path.join(HERE, 'assets', url.pathname);
      else if (url.pathname.startsWith('/maplibre/')) file = path.join(MAPLIBRE_DIST, path.basename(url.pathname));
      if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    } catch (err) {
      res.writeHead(502); res.end(String((err && err.message) || err));
    }
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function main() {
  const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const resolved = await resolveSpecData(spec, { baseDir: spec.base_dir || path.dirname(path.resolve(process.argv[2])), countriesFile: spec.countries_path });
  spec.events = resolved.events;
  const plan = planRender(spec);
  plan.credits.attribution.push(...resolved.credits);
  // numbers the author may want to quote in a chip (areas, data ranges, dot counts)
  plan.layer_facts = resolved.events.filter((e) => ['value_overlay', 'ghost_shape', 'dots', 'streak'].includes(e.type) && (e.data || e.type !== 'dots')).map((e) => ({
    id: e.id, type: e.type, data: e.data, unit: e.unit, data_range: e.data_range, area_km2: e.area_km2, source_name: e.source_name,
    dots: e.type === 'dots' && e.points ? e.points.length : undefined, streaks: e.seeds?.length,
  }));
  const { width, height, fps } = spec;
  const { total } = plan;
  emit({ event: 'plan', layer_facts: plan.layer_facts, frames: total, min_frame_km: plan.minFrameKm, imagery_used: [...plan.used], credits: plan.credits });
  plan.warnings.forEach((w) => emit({ event: 'warning', message: w.message }));

  const media = prepareMedia(spec, { baseDir: spec.base_dir || path.dirname(path.resolve(process.argv[2])), ffmpeg: spec.ffmpeg || 'ffmpeg', lazy: spec.media_lazy === true, ffprobe: spec.ffprobe || 'ffprobe' });
  const server = await startServer(spec, plan, media);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(spec);
  const launchOpts = {
    headless: true,
    args: process.env.PAKMAP_GL === 'software'
      ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
      : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
  };
  if (spec.browser_channel) launchOpts.channel = spec.browser_channel;
  const browser = await chromium.launch(launchOpts);
  let ffmpeg = null;
  try {
    // pixel_scale 2 = 4K export: the same 1920x1080 layout drawn with twice the pixels (see page.js).
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: spec.pixel_scale || 1 });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') pageErrors.push(m.text()); });
    await page.goto(`${origin}/index.html`);
    try {
      await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 90000 });
    } catch (err) {
      throw new Error(`map page did not start: ${pageErrors.slice(0, 5).join(' | ') || err.message}`);
    }
    const setupError = await page.evaluate(() => window.__error || null);
    if (setupError) throw new Error(`map setup failed: ${setupError}`);

    ffmpeg = spawn(spec.ffmpeg || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', spec.x264_preset || 'medium', '-crf', String(spec.crf ?? 18), '-pix_fmt', 'yuv420p', '-r', String(fps),
      '-metadata', 'comment=semantic-yt-studio:pakmap-scene', '-movflags', '+faststart', spec.output], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ffErr = '';
    ffmpeg.stderr.on('data', (d) => { ffErr += d; });
    const ffDone = new Promise((resolve) => ffmpeg.on('close', resolve));

    for (let i = 0; i < total; i++) {
      const b64 = await page.evaluate((t) => window.renderFrame(t), i / fps);
      const jpg = Buffer.from(b64, 'base64');
      if (!ffmpeg.stdin.write(jpg)) await new Promise((r) => ffmpeg.stdin.once('drain', r));
      if (i % 15 === 0 || i === total - 1) emit({ event: 'progress', frame: i + 1, total });
      if (i % 30 === 0 && spec.media_lazy === true) releaseClips(media.files, i / fps);
    }
    ffmpeg.stdin.end();
    const code = await ffDone;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${ffErr.trim().slice(-500)}`);
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    const sidecar = `${spec.output}.pakmap.json`;
    fs.writeFileSync(sidecar, JSON.stringify({ layer_facts: plan.layer_facts, credits: plan.credits, warnings: plan.warnings, imagery_used: [...plan.used], min_frame_km: plan.minFrameKm, frames: total }, null, 2));
    emit({ event: 'done', output: spec.output, sidecar, frames: total });
  } finally {
    disposeMedia(media.files);   // the frame folders are this render's own: they never outlive it
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await browser.close().catch(() => {});
    server.close();
  }
}

main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
