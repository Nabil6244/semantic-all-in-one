// Map-scene renderer: node render.mjs <spec.json>
//
// Draws an animated satellite map (MapLibre in a hidden, temporary Chromium)
// frame by frame and pipes the frames to ffmpeg. Deliberately separate from
// flow-engine: its own process, its own throwaway browser (no persistent
// profile), and a local file server on a random free port (never the Flow
// engine's fixed port).
//
// Every frame waits until all tiles are loaded before capture, so the same
// spec always produces the same video.
//
// stdout: one JSON object per line — {"event":"progress","frame":n,"total":N}
//         then {"event":"done","output":...} or {"event":"error","message":...}

import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MAPLIBRE_DIST = path.join(HERE, 'node_modules', 'maplibre-gl', 'dist');
const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8';

function emit(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }

function loadPlaywright(spec) {
  const candidates = [spec.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean);
  for (const dir of candidates) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}

function fetchTile(z, y, x, cacheDir) {
  const file = path.join(cacheDir, 'nasa_blue_marble', String(z), String(y), `${x}.jpg`);
  if (fs.existsSync(file)) return Promise.resolve(fs.readFileSync(file));
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      https.get(`${GIBS}/${z}/${y}/${x}.jpeg`, { timeout: 20000 }, (res) => {
        if (res.statusCode !== 200) {
          res.resume();
          if (res.statusCode >= 500 && n < 3) return setTimeout(() => attempt(n + 1), 500 * (n + 1));
          return reject(new Error(`tile ${z}/${y}/${x}: HTTP ${res.statusCode}`));
        }
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const buf = Buffer.concat(chunks);
          fs.mkdirSync(path.dirname(file), { recursive: true });
          const tmp = `${file}.${process.pid}.tmp`;
          fs.writeFileSync(tmp, buf);
          fs.renameSync(tmp, file);
          resolve(buf);
        });
      }).on('error', (err) => (n < 3 ? setTimeout(() => attempt(n + 1), 500 * (n + 1)) : reject(err)))
        .on('timeout', function () { this.destroy(new Error('timeout')); });
    };
    attempt(0);
  });
}

function startServer(spec) {
  const types = { '.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css', '.ttf': 'font/ttf', '.html': 'text/html', '.json': 'application/json' };
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://x');
      const tile = url.pathname.match(/^\/tiles\/(\d+)\/(\d+)\/(\d+)\.jpg$/);
      if (tile) {
        const buf = await fetchTile(tile[1], tile[2], tile[3], spec.cache_dir);
        res.writeHead(200, { 'Content-Type': 'image/jpeg' });
        return res.end(buf);
      }
      let file = null;
      if (url.pathname === '/' || url.pathname === '/index.html') file = path.join(HERE, 'page.html');
      else if (url.pathname === '/page.js') file = path.join(HERE, 'page.js');
      else if (url.pathname === '/spec.json') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify(spec.scene));
      } else if (url.pathname === '/font.ttf') file = spec.font_path;
      else if (url.pathname.startsWith('/maplibre/')) file = path.join(MAPLIBRE_DIST, path.basename(url.pathname));
      if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': types[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    } catch (err) {
      res.writeHead(502); res.end(String(err && err.message || err));
    }
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function main() {
  const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const { width, height, fps, duration } = spec.scene;
  const total = Math.max(1, Math.round(duration * fps));
  const server = await startServer(spec);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(spec);
  const launchOpts = {
    headless: true,
    // Graphics card when the machine has a usable one; Chromium falls back to
    // its software renderer (SwiftShader) by itself when it doesn't.
    // MAP_ENGINE_GL=software forces the fallback (tests / broken drivers).
    args: process.env.MAP_ENGINE_GL === 'software'
      ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
      : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
  };
  if (spec.browser_channel) launchOpts.channel = spec.browser_channel;
  const browser = await chromium.launch(launchOpts);
  let ffmpeg = null;
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') pageErrors.push(m.text()); });
    page.on('requestfailed', (r) => pageErrors.push(`request failed: ${r.url()} ${r.failure() && r.failure().errorText}`));
    await page.goto(`${origin}/index.html`);
    try {
      await page.waitForFunction(() => window.__mapReady === true || window.__mapError, null, { timeout: 60000 });
    } catch (err) {
      throw new Error(`map page did not start: ${pageErrors.slice(0, 5).join(' | ') || err.message}`);
    }
    const setupError = await page.evaluate(() => window.__mapError || null);
    if (setupError) throw new Error(`map setup failed: ${setupError}`);

    ffmpeg = spawn(spec.ffmpeg, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(fps),
      // Marks the file as a map clip: renders hold its last frame instead of
      // looping it (a zoom that jumps back to the start looks broken).
      '-metadata', 'comment=semantic-yt-studio:map-scene',
      '-movflags', '+faststart', spec.output], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ffErr = '';
    ffmpeg.stderr.on('data', (d) => { ffErr += d; });
    const ffDone = new Promise((resolve) => ffmpeg.on('close', resolve));

    let tDraw = 0, tShot = 0;
    for (let i = 0; i < total; i++) {
      const t0 = Date.now();
      const b64 = await page.evaluate((t) => window.renderFrame(t), i / fps);
      const t1 = Date.now();
      const jpg = Buffer.from(b64, 'base64');
      tDraw += t1 - t0; tShot += Date.now() - t1;
      if (!ffmpeg.stdin.write(jpg)) await new Promise((r) => ffmpeg.stdin.once('drain', r));
      if (i % 10 === 0 || i === total - 1) emit({ event: 'progress', frame: i + 1, total });
    }
    ffmpeg.stdin.end();
    const code = await ffDone;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${ffErr.trim().slice(-500)}`);
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    emit({ event: 'done', output: spec.output, frames: total, draw_ms: tDraw, capture_ms: tShot });
  } finally {
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await browser.close().catch(() => {});
    server.close();
  }
}

main().catch((err) => {
  emit({ event: 'error', message: String(err && err.message || err) });
  process.exit(1);
});
