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

import crypto from 'node:crypto';
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
import { fetchTile, cachePath } from './lib/tiles.mjs';
import { parsePointsCsv } from './lib/points.mjs';
import { footageShortcut } from './lib/footage_pass.mjs';
import { planSegments, frameCosts, segmentEvents } from './lib/segments.mjs';

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

// Tiles the renderer could not download (after fetchTile's retries), keyed "provider z/x/y". The page draws them from
// lower-resolution imagery instead (page.js); the counts go to the render log and the sidecar.
const tileFailures = new Map();

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
        const key = `${tile[1]} ${tile[2]}/${tile[3]}/${tile[4]}`;
        // already failed in this render (after its retries): answer at once, or every child tile falling back to it
        // would sit through the same retries again
        if (tileFailures.has(key)) { res.writeHead(503); return res.end(); }
        if (url.searchParams.get('refetch')) {
          // the page found the cached copy unreadable or blank: drop it and download the tile again
          try { fs.unlinkSync(cachePath(spec.cache_dir, provider, tile[2], tile[3], tile[4])); } catch { /* not cached, or cannot remove */ }
        }
        let buf;
        try {
          buf = await fetchTile(provider, tile[2], tile[3], tile[4], spec.cache_dir);
        } catch (err) {
          // a download failure is 503, never 404: the page must not mistake it for "no imagery here"
          tileFailures.set(key, String((err && err.message) || err));
          res.writeHead(503); return res.end();
        }
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
      else if (/^\/lib\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(HERE, url.pathname);
      else if (/^\/fonts\/[\w.-]+\.ttf$/.test(url.pathname)) file = path.join(HERE, 'assets', url.pathname);
      else if (/^\/gfx\/lib\/[\w-]+\.mjs$/.test(url.pathname) || /^\/gfx\/fonts\/[\w.-]+\.ttf$/.test(url.pathname)) file = path.join(HERE, '..', 'gfx-core', url.pathname.slice(5));   // gfx-core: the universal templates
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

  if (spec.plan_only) {
    // Segments for a render in pieces (lib/segments.mjs), each with the key that says whether last render's piece is still right
    const fingerprint = engineFingerprint();
    const segs = planSegments(spec.events, total, fps, { targetS: spec.segment_s ?? 30, minS: spec.segment_min_s ?? 10 });
    const costs = frameCosts(spec, total);
    emit({ event: 'segments', segments: segs.map((g) => {
      let cost = 0;
      for (let i = g.from; i < g.to; i++) cost += costs[i];
      return { ...g, cost: Math.round(cost), key: segmentKey(spec, g, fingerprint) };
    }), sidecar: { layer_facts: plan.layer_facts, credits: plan.credits, warnings: plan.warnings, imagery_used: [...plan.used], min_frame_km: plan.minFrameKm } });
    return;
  }

  // what this process draws: the whole video to spec.output, or the listed segments, each to its own file
  const jobs = Array.isArray(spec.segments) && spec.segments.length
    ? spec.segments.map((g) => ({ from: Number(g.from), to: Number(g.to), output: g.output }))
    : [{ from: 0, to: total, output: spec.output }];
  const media = prepareMedia(spec, { baseDir: spec.base_dir || path.dirname(path.resolve(process.argv[2])), ffmpeg: spec.ffmpeg || 'ffmpeg', lazy: spec.media_lazy === true, ffprobe: spec.ffprobe || 'ffprobe' });
  const server = await startServer(spec, plan, media);
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser = null, page = null, ffmpeg = null;
  const pageErrors = [];
  // The browser starts on the first frame that needs it: a piece that is all full-screen footage never starts one.
  async function openPage() {
    const { chromium } = loadPlaywright(spec);
    const launchOpts = {
      headless: true,
      args: process.env.PAKMAP_GL === 'software'
        ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
        : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
    };
    if (spec.browser_channel) launchOpts.channel = spec.browser_channel;
    browser = await chromium.launch(launchOpts);
    // pixel_scale 2 = 4K export: the same 1920x1080 layout drawn with twice the pixels (see page.js).
    page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: spec.pixel_scale || 1 });
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
  }
  const pageError = (err) => {
    const why = tileFailures.size ? ` Last download error: ${[...tileFailures.values()].pop()}` : '';
    const msg = String((err && err.message) || err).replace(/^page\.evaluate: (Error: )?/, '').split('\n    at ')[0];   // no page stack trace in the message
    return new Error(`${msg}${why}`);
  };
  const tileStats = async () => (page ? await page.evaluate(() => window.__tileStats || {}).catch(() => ({})) : {});
  try {
    // Hybrid: a frame that is only a full-screen video clip is that clip's frame (lib/footage_pass.mjs); pakMap: never
    const clipOnly = footageShortcut(spec, spec.events, media);
    const jobTotal = jobs.reduce((n, j) => n + (j.to - j.from), 0);
    let fromClips = 0, drawn = 0;
    const segmentsDone = [];
    // the map's tile memory is emptied where every piece starts (page.js freshStart), in a one-piece render too, so a piece
    // comes out the same whichever renderer draws it
    const pieceStarts = new Set(planSegments(spec.events, total, fps, { targetS: spec.segment_s ?? 30, minS: spec.segment_min_s ?? 10 }).map((g) => g.from));
    let needFresh = false;
    for (const job of jobs) {
      ffmpeg = spawn(spec.ffmpeg || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
        '-c:v', 'libx264', '-preset', spec.x264_preset || 'medium', '-crf', String(spec.crf ?? 18), '-pix_fmt', 'yuv420p', '-r', String(fps),
        '-metadata', 'comment=semantic-yt-studio:pakmap-scene', '-movflags', '+faststart', job.output], { stdio: ['pipe', 'ignore', 'pipe'] });
      let ffErr = '';
      ffmpeg.stderr.on('data', (d) => { ffErr += d; });
      const ffDone = new Promise((resolve) => ffmpeg.on('close', resolve));
      // an encoder that stops early is reported with its own message, not as a broken pipe
      let ffGone = null;
      ffmpeg.stdin.on('error', (err) => { ffGone = err; });
      const write = async (buf) => {
        if (ffGone || ffmpeg.exitCode !== null) {
          const code = await ffDone;
          throw new Error(`ffmpeg exited ${code}: ${ffErr.trim().slice(-500) || (ffGone && ffGone.message) || 'no message'}`);
        }
        if (!ffmpeg.stdin.write(buf)) await new Promise((r) => { ffmpeg.stdin.once('drain', r); ffmpeg.once('close', r); });
      };
      const before = await tileStats();
      let jobClips = 0;
      // The page encodes frame i while it draws frame i+1 (page.js drawFrame/takeFrame): at most one frame is waiting.
      let waiting = null;
      const flush = async () => {
        if (!waiting) return;
        const p = waiting; waiting = null;
        let b64;
        try { b64 = await p; } catch (err) { throw pageError(err); }
        await write(Buffer.from(b64, 'base64'));
      };
      const tick = (i) => {
        drawn++;
        if (drawn % 15 === 0 || drawn === jobTotal) emit({ event: 'progress', frame: drawn, total: jobTotal, at: i });
        if (i % 30 === 0 && spec.media_lazy === true) releaseClips(media.files, i / fps);
      };
      for (let i = job.from; i < job.to; i++) {
        if (i === job.from || pieceStarts.has(i)) needFresh = true;
        const direct = clipOnly(i / fps);
        if (direct) {
          await flush();
          fromClips++; jobClips++;
          await write(fs.readFileSync(direct));
          tick(i);
          continue;
        }
        if (!page) await openPage();
        else if (needFresh) await page.evaluate(() => window.freshStart());
        needFresh = false;
        try {
          await page.evaluate((t) => window.drawFrame(t), i / fps);
        } catch (err) {
          if (waiting) waiting.catch(() => {});
          throw pageError(err);
        }
        await flush();   // the previous frame, encoded while this one was drawn
        waiting = page.evaluate(() => window.takeFrame());
        waiting.catch(() => {});   // handled in flush
        tick(i);
      }
      await flush();
      ffmpeg.stdin.end();
      const code = await ffDone;
      if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${ffErr.trim().slice(-500)}`);
      const after = await tileStats();
      // a piece drawn with stand-in imagery is never kept for reuse (lib/segments.mjs); the counts say so
      segmentsDone.push({ from: job.from, to: job.to, output: job.output, frames_from_clips: jobClips, tiles_failed: (after.failed || 0) - (before.failed || 0) });
      if (jobs.length > 1 || spec.segments) emit({ event: 'segment', ...segmentsDone[segmentsDone.length - 1] });
    }
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    // Map imagery health for the render log: failed downloads and what stood in for them (never black land).
    const ts = await tileStats();
    // failed: map tiles whose own download failed or came back unreadable/blank (each was drawn from a stand-in,
    // counted in the next two); invalid: tiles that downloaded but stayed unreadable/blank after a fresh download;
    // download_failures: every failed download, including coarser tiles tried as stand-ins
    const tiles = { failed: ts.failed || 0, drawn_from_coarser_zoom: ts.fromParent || 0, drawn_from_coarser_layer: ts.fromCoarserLayer || 0,
      invalid: ts.invalid || 0, download_failures: tileFailures.size };
    emit({ event: 'tiles', ...tiles });
    if (tiles.failed) {
      const last = tileFailures.size ? ` (last download error: ${[...tileFailures.values()].pop()})` : '';
      emit({ event: 'warning', message: `map imagery: ${tiles.failed} map tile(s) could not be used (failed downloads, or ${tiles.invalid} unreadable or blank tile(s)); ${tiles.drawn_from_coarser_zoom} were drawn from the same imagery at a coarser zoom and ${tiles.drawn_from_coarser_layer} from a coarser imagery layer, so those areas look softer${last}` });
    }
    const sidecar = `${spec.output}.pakmap.json`;
    fs.writeFileSync(sidecar, JSON.stringify({ layer_facts: plan.layer_facts, credits: plan.credits, warnings: plan.warnings, imagery_used: [...plan.used], min_frame_km: plan.minFrameKm, frames: jobTotal, frames_from_clips: fromClips, tiles, segments: segmentsDone }, null, 2));
    emit({ event: 'done', output: spec.output, sidecar, frames: jobTotal });
  } finally {
    disposeMedia(media.files);   // the frame folders are this render's own: they never outlive it
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    if (browser) await browser.close().catch(() => {});
    server.close();
  }
}

// ---- reuse keys (pieces of the last render that can be used again) ----
const KEY_SKIP = new Set(['events', 'output', 'segments', 'plan_only', 'cache_dir', 'playwright_dir', 'browser_channel', 'ffmpeg', 'ffprobe', 'base_dir', 'segment_s', 'segment_min_s']);
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex');

/** The renderer's own code and bundled data: a change to any of them makes every piece stale. */
function engineFingerprint() {
  const files = [];
  const walk = (dir) => {
    for (const f of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(dir, f.name);
      if (f.isDirectory()) walk(p);
      else files.push(p);
    }
  };
  for (const d of ['lib', 'data', 'assets']) if (fs.existsSync(path.join(HERE, d))) walk(path.join(HERE, d));
  files.push(path.join(HERE, 'render.mjs'), path.join(HERE, 'page.js'), path.join(HERE, 'page.html'), path.join(MAPLIBRE_DIST, 'maplibre-gl.mjs'));
  const h = crypto.createHash('sha256');
  for (const f of files) {
    try { const st = fs.statSync(f); h.update(`${path.relative(HERE, f)}:${st.size}:${st.size < 4e6 ? sha(fs.readFileSync(f)) : st.mtimeMs}\n`); } catch { h.update(`${f}:missing\n`); }
  }
  h.update(`gl:${process.env.PAKMAP_GL || 'gpu'}`);
  return h.digest('hex');
}

/** Every file a value names (pictures, clips, point files), replaced by its size and modification time. */
function withFileStamps(value, baseDir) {
  if (typeof value === 'string') {
    if (value.length > 1024 || !/[\\/.]/.test(value)) return value;
    const p = path.isAbsolute(value) ? value : path.resolve(baseDir, value);
    try { const st = fs.statSync(p); if (st.isFile()) return `${value}@${st.size}:${Math.round(st.mtimeMs)}`; } catch { /* not a file */ }
    return value;
  }
  if (Array.isArray(value)) return value.map((v) => withFileStamps(v, baseDir));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, withFileStamps(v, baseDir)]));
  return value;
}

/** What segment g's frames depend on: the engine, the spec's settings, the camera, its own layers (with their files), and
 *  the timings of every full-screen clip (they pause the other layers' clocks). Same key, same frames. */
function segmentKey(spec, g, fingerprint) {
  const baseDir = spec.base_dir || '.';
  const globals = Object.fromEntries(Object.entries(spec).filter(([k]) => !KEY_SKIP.has(k)).sort(([a], [b]) => a.localeCompare(b)));
  const live = segmentEvents(spec.events, g, spec.fps).filter((e) => e.type !== 'media_full' || (e.t_in <= (g.to - 1) / spec.fps && e.t_out > g.from / spec.fps));
  const windows = (spec.events || []).filter((e) => e.type === 'media_full').map((e) => [e.t_in, e.t_out, e.dissolve_s ?? null, !!e.xfade_prev]);
  return sha(JSON.stringify({ fingerprint, globals: withFileStamps(globals, baseDir), from: g.from, to: g.to, windows, live: withFileStamps(live, baseDir) }));
}

main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
