// Weather renderer: node render.mjs <spec.json>
//
// A COPY of pakmap-engine/render.mjs (fork record: UPSTREAM.json; drift report: tools/check_upstream.mjs). Changes from
// the original, and nothing else: pakMap's modules, MapLibre and font are used from ../pakmap-engine (imported, never
// edited); the page and the weather graphics are weather-engine's own; spec.weather adds timed satellite layers (served
// through the same tile cache; a tile outside the satellite picture answers 204) and weather graphics (lib/wx_draw.mjs);
// temperature markers whose city stays off screen are reported; the sidecar is <output>.weather.json.
//
// --- the original header follows ---
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
import { planRender } from '../pakmap-engine/lib/plan.mjs';
import { resolveSpecData } from '../pakmap-engine/lib/datasets.mjs';
import { prepareMedia, materializeClip, releaseClips, disposeMedia } from '../pakmap-engine/lib/media.mjs';
import { fetchTile, cachePath } from '../pakmap-engine/lib/tiles.mjs';
import { parsePointsCsv } from '../pakmap-engine/lib/points.mjs';
import { validateWxEvents } from './lib/wx_draw.mjs';
import { rasterProviders, validateRasters } from './lib/wx_raster.mjs';

/** The graphics plugins in lib/layers/ (each: export default { type, draw, validate?, order? }). */
async function loadPlugins() {
  const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), 'lib', 'layers');
  const names = fs.existsSync(dir) ? fs.readdirSync(dir).filter((n) => n.endsWith('.mjs')).sort() : [];
  const out = [];
  for (const n of names) out.push({ file: n, mod: (await import(new URL(`./lib/layers/${n}`, import.meta.url))).default });
  return out;
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAK = path.join(HERE, '..', 'pakmap-engine');   // pakMap's engine: its modules, MapLibre and font (read only)
const MAPLIBRE_DIST = path.join(PAK, 'node_modules', 'maplibre-gl', 'dist');
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

// Tiles the renderer could not download (after fetchTile's retries), keyed "provider z/x/y". The page draws them from
// lower-resolution imagery instead (page.js); the counts go to the render log and the sidecar.
const tileFailures = new Map();
let radarActive = 0; const radarQueue = [];
const radarSlot = () => new Promise((r) => { if (radarActive < 4) { radarActive++; r(); } else radarQueue.push(r); });
const radarDone = () => { const n = radarQueue.shift(); if (n) n(); else radarActive--; };

function startServer(spec, plan, media) {
  const types = { '.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf' };
  const wxSat = [...((spec.weather && spec.weather.satellite) || []).map((s) => s.provider), ...rasterProviders(spec)];
  const byId = Object.fromEntries([...plan.providers, ...wxSat].map((p) => [p.id, p]));
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
        const key = `${tile[1]} ${tile[2]}/${tile[3]}/${tile[4]}`;
        // already failed in this render (after its retries): answer at once, or every child tile falling back to it
        // would sit through the same retries again
        if (tileFailures.has(key)) { res.writeHead(503); return res.end(); }
        if (url.searchParams.get('refetch')) {
          // the page found the cached copy unreadable or blank: drop it and download the tile again
          try { fs.unlinkSync(cachePath(spec.cache_dir, provider, tile[2], tile[3], tile[4])); } catch { /* not cached, or cannot remove */ }
        }
        let buf;
        const limited = /^wx_radar_/.test(tile[1]);   // at most 4 radar tiles at once (be gentle with IEM)
        try {
          if (limited) await radarSlot();
          try { buf = await fetchTile(provider, tile[2], tile[3], tile[4], spec.cache_dir); } finally { if (limited) radarDone(); }
        } catch (err) {
          // a download failure is 503, never 404: the page must not mistake it for "no imagery here"
          tileFailures.set(key, String((err && err.message) || err));
          res.writeHead(503); return res.end();
        }
        if (!buf && wxSat.some((p) => p.id === tile[1])) { res.writeHead(204); return res.end(); }   // outside the satellite picture: nothing to draw, not an error
        if (!buf) { res.writeHead(404); return res.end(); }   // legitimately no imagery at this tile
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
      else if (/^\/pakmap-engine\/lib\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(PAK, 'lib', path.basename(url.pathname));
      else if (/^\/weather-engine\/lib\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(HERE, 'lib', path.basename(url.pathname));
      else if (/^\/weather-engine\/lib\/layers\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(HERE, 'lib', 'layers', path.basename(url.pathname));
      else if (url.pathname === '/weather-engine/plugins.mjs') {   // the plugin list, written for the page (it cannot list a folder)
        const names = fs.existsSync(path.join(HERE, 'lib', 'layers')) ? fs.readdirSync(path.join(HERE, 'lib', 'layers')).filter((n) => /^[\w-]+\.mjs$/.test(n)).sort() : [];
        const body = names.map((n, i) => `import p${i} from '/weather-engine/lib/layers/${n}';`).join('\n') + `\nexport default [${names.map((_, i) => `p${i}`).join(', ')}];\n`;
        res.writeHead(200, { 'Content-Type': 'text/javascript' }); return res.end(body);
      }
      else if (/^\/fonts\/[\w.-]+\.ttf$/.test(url.pathname)) file = path.join(PAK, 'assets', url.pathname);
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
  // the MRMS rain grid is credited through spec.weather.credits, not as pakMap's 'supplied by the author' grid
  plan.credits.attribution.push(...resolved.credits.filter((c) => !/^Grid data: mrms_[0-9a-f]{16}\.asc \(supplied by the author\)$/.test(c)));
  const plugins = await loadPlugins();
  const wxErrors = [...validateWxEvents((spec.weather && spec.weather.events) || [], spec.duration, plugins.map((p) => p.mod)),
    ...validateRasters((spec.weather && spec.weather.rasters) || [], spec.duration)];
  if (wxErrors.length) throw new Error(`weather layers: ${wxErrors.join('; ')}`);
  for (const c of (spec.weather && spec.weather.credits) || []) if (!plan.credits.attribution.includes(c)) plan.credits.attribution.push(c);
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
    // a failed tile (503) is reported with the tile counts below, not as a page error
    page.on('console', (m) => { if (m.type() === 'error' && !/status of 503/.test(m.text())) pageErrors.push(m.text()); });
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
      '-metadata', 'comment=semantic-yt-studio:weather-scene', '-movflags', '+faststart', spec.output], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ffErr = '';
    ffmpeg.stderr.on('data', (d) => { ffErr += d; });
    const ffDone = new Promise((resolve) => ffmpeg.on('close', resolve));

    for (let i = 0; i < total; i++) {
      let b64;
      try {
        b64 = await page.evaluate((t) => window.renderFrame(t), i / fps);
      } catch (err) {
        const why = tileFailures.size ? ` Last download error: ${[...tileFailures.values()].pop()}` : '';
        const msg = String((err && err.message) || err).replace(/^page\.evaluate: (Error: )?/, '').split('\n    at ')[0];   // no page stack trace in the message
        throw new Error(`${msg}${why}`);
      }
      const jpg = Buffer.from(b64, 'base64');
      if (!ffmpeg.stdin.write(jpg)) await new Promise((r) => ffmpeg.stdin.once('drain', r));
      if (i % 15 === 0 || i === total - 1) emit({ event: 'progress', frame: i + 1, total });
      if (i % 30 === 0 && spec.media_lazy === true) releaseClips(media.files, i / fps);
    }
    ffmpeg.stdin.end();
    const code = await ffDone;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${ffErr.trim().slice(-500)}`);
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    // weather QC: a temperature marker whose city is off screen for most of its time is a plan problem worth saying
    const wxStats = await page.evaluate(() => (window.__wxStats ? window.__wxStats() : {})).catch(() => ({}));
    for (const [id, st] of Object.entries(wxStats)) {
      const seen = st.on + st.off;
      if (seen && st.off / seen > 0.5) emit({ event: 'warning', message: `weather: ${id} (${st.city}) is off screen for ${Math.round((100 * st.off) / seen)}% of its time: the camera does not show that city then` });
    }
    // Map imagery health for the render log: failed downloads and what stood in for them (never black land).
    const ts = await page.evaluate(() => window.__tileStats || {}).catch(() => ({}));
    // failed: map tiles whose own download failed or came back unreadable/blank (each was drawn from a stand-in,
    // counted in the next two); invalid: tiles that downloaded but stayed unreadable/blank after a fresh download;
    // download_failures: every failed download, including coarser tiles tried as stand-ins
    const tiles = { failed: ts.failed || 0, drawn_from_coarser_zoom: ts.fromParent || 0, drawn_from_coarser_layer: ts.fromCoarserLayer || 0,
      invalid: ts.invalid || 0, download_failures: tileFailures.size, satellite_missing: ts.wxMissing || 0 };
    emit({ event: 'tiles', ...tiles });
    if (tiles.satellite_missing) emit({ event: 'warning', message: `satellite layer: ${tiles.satellite_missing} tile(s) could not be downloaded; the base map shows through there` });
    if (tiles.failed) {
      const last = tileFailures.size ? ` (last download error: ${[...tileFailures.values()].pop()})` : '';
      emit({ event: 'warning', message: `map imagery: ${tiles.failed} map tile(s) could not be used (failed downloads, or ${tiles.invalid} unreadable or blank tile(s)); ${tiles.drawn_from_coarser_zoom} were drawn from the same imagery at a coarser zoom and ${tiles.drawn_from_coarser_layer} from a coarser imagery layer, so those areas look softer${last}` });
    }
    const sidecar = `${spec.output}.weather.json`;
    fs.writeFileSync(sidecar, JSON.stringify({ layer_facts: plan.layer_facts, credits: plan.credits, warnings: plan.warnings, imagery_used: [...plan.used], min_frame_km: plan.minFrameKm, frames: total, tiles }, null, 2));
    emit({ event: 'done', output: spec.output, sidecar, frames: total });
  } finally {
    disposeMedia(media.files);   // the frame folders are this render's own: they never outlive it
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await browser.close().catch(() => {});
    server.close();
  }
}

main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
