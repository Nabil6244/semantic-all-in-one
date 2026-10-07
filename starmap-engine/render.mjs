// StarMap renderer: node render.mjs <spec.json> [output.mp4]
//
// Adapted copy of pakmap-engine/render.mjs (StarMap shares no code with pakMap): a local server for the page, its modules,
// three.js, textures and fonts; a hidden Chromium; window.renderFrame(t) for every frame; each JPEG piped to ffmpeg. The
// same spec always gives the same video. STARMAP_GL=software renders on the CPU (SwiftShader): the worst case of a PC
// without a usable graphics card.
//
// With spec.segment_cache (a folder), only the chunks whose fingerprint changed are drawn again (lib/segments.mjs); the
// others come from that folder and the chunks are joined without re-encoding.
//
// stdout: one JSON object per line -- {"event":"progress","frame":n,"total":N,"ms_per_frame":x}, {"event":"done",...},
// {"event":"error","message":...}
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createCutter } from './cutter.mjs';
import { planChunks, chunkFingerprints, engineFingerprint } from './lib/segments.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const TYPES = { '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.webp': 'image/webp', '.jpeg': 'image/jpeg', '.mjs': 'text/javascript', '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf', '.jpg': 'image/jpeg', '.png': 'image/png' };

function loadPlaywright(spec) {
  for (const dir of [spec.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean)) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}

export const mediaDirOf = (spec, specDir) => (spec.media_dir ? path.resolve(specDir, spec.media_dir) : path.join(specDir, 'media'));

function startServer(spec, specDir, cutter) {
  const mediaDir = mediaDirOf(spec, specDir);
  const addons = path.join(HERE, 'node_modules', 'three', 'examples', 'jsm');
  const pageSpec = JSON.stringify(spec);
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    let file = null;
    if (url.pathname === '/spec.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(pageSpec); }
    if (url.pathname === '/' || url.pathname === '/index.html') file = path.join(HERE, 'page.html');
    else if (url.pathname === '/page.js') file = path.join(HERE, 'page.js');
    else if (/^\/(lib|layers)\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(HERE, url.pathname);
    else if (url.pathname.startsWith('/three/addons/')) { const f = path.resolve(addons, decodeURIComponent(url.pathname.slice('/three/addons/'.length))); if (f.startsWith(addons + path.sep)) file = f; }
    else if (/^\/footage\/\d+\/\d+\.jpg$/.test(url.pathname) && cutter) { const [, , i, k] = url.pathname.split('/'); file = cutter.frameFile(Number(i), parseInt(k, 10)); }
    else if (/^\/cardframe\/\d+\/\d+\.jpg$/.test(url.pathname) && cutter) { const [, , i, k] = url.pathname.split('/'); file = cutter.cardFrameFile(Number(i), parseInt(k, 10)); }
    else if (url.pathname.startsWith('/media/')) file = path.join(mediaDir, path.basename(decodeURIComponent(url.pathname)));
    else if (url.pathname === '/three/three.module.min.js') file = path.join(HERE, 'node_modules', 'three', 'build', 'three.module.min.js');
    else if (url.pathname === '/astronomy/astronomy.browser.min.js') file = path.join(HERE, 'node_modules', 'astronomy-engine', 'astronomy.browser.min.js');
    else if (/^\/catalogs\/[\w.-]+\.json$/.test(url.pathname)) file = path.join(HERE, 'assets', 'catalogs', path.basename(url.pathname));
    else if (/^\/textures\/[\w.-]+$/.test(url.pathname)) file = path.join(spec.texture_dir || path.join(HERE, 'assets', 'textures'), path.basename(url.pathname));
    else if (/^\/fonts\/[\w.-]+\.ttf$/.test(url.pathname)) file = path.join(HERE, 'assets', 'fonts', path.basename(url.pathname));
    if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

/** The chunks, in order, as one video: joined without re-encoding (every chunk has the same encoder settings). */
function joinChunks(spec, chunks, output) {
  const list = `${output}.chunks.txt`;
  fs.writeFileSync(list, chunks.map((c) => `file '${c.file.replace(/\\/g, '/').replace(/'/g, "'\\''")}'`).join('\n') + '\n');
  const r = spawnSync(spec.ffmpeg || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', output], { encoding: 'utf8' });
  fs.rmSync(list, { force: true });
  if (r.status !== 0) throw new Error(`joining the chunks failed: ${(r.stderr || '').trim().slice(-400)}`);
}

/** Keep the chunks of this render and of the one before it (undoing an edit is then free); delete the rest, and any
 *  half-written chunk. */
function pruneCache(dir, chunks) {
  const now = chunks.map((c) => path.basename(c.file)), log = path.join(dir, 'renders.json');
  let seen = {};
  try { seen = JSON.parse(fs.readFileSync(log, 'utf8')); } catch { /* first render */ }
  const same = (seen.current || []).join() === now.join();
  const before = same ? (seen.previous || []) : (seen.current || []);   // an unchanged re-render keeps the one before too
  const keep = new Set([...now, ...before, 'renders.json']);
  for (const name of fs.readdirSync(dir)) if (!keep.has(name)) fs.rmSync(path.join(dir, name), { force: true });
  if (!same) fs.writeFileSync(log, JSON.stringify({ current: now, previous: before }));
}

async function main() {
  const specPath = process.argv[2];
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  spec.output = process.argv[3] || spec.output || path.join(path.dirname(path.resolve(specPath)), 'starmap.mp4');
  const { width, height, fps } = spec;
  const total = Math.round(spec.duration * fps);
  const specDir = path.dirname(path.resolve(specPath));
  const soft = process.env.STARMAP_GL === 'software';
  const cacheDir = spec.segment_cache && !process.env.STARMAP_STILLS ? path.resolve(spec.segment_cache) : null;
  let chunks = [{ i: 0, k0: 0, k1: total }], keys = null;
  if (cacheDir) {
    fs.mkdirSync(cacheDir, { recursive: true });
    chunks = planChunks(total, fps);
    keys = chunkFingerprints(spec, chunks, { mediaDir: mediaDirOf(spec, specDir), extra: `${engineFingerprint(HERE)}|${soft ? 'sw' : 'hw'}` });
    chunks.forEach((c, n) => { c.file = path.join(cacheDir, `${keys[n]}.mp4`); c.cached = fs.existsSync(c.file); });
    const reused = chunks.filter((c) => c.cached);
    emit({ event: 'cache', chunks: chunks.length, reused: reused.length, frames_reused: reused.reduce((a, c) => a + c.k1 - c.k0, 0), total });
    if (reused.length === chunks.length) {
      joinChunks(spec, chunks, spec.output);
      pruneCache(cacheDir, chunks);
      emit({ event: 'progress', frame: total, total, ms_per_frame: 0 });
      emit({ event: 'done', output: spec.output, frames: total, seconds: 0, reused_frames: total, drawn_frames: 0 });
      return;
    }
  }
  const cutter = createCutter({ spec, mediaDir: mediaDirOf(spec, specDir), ffmpeg: spec.ffmpeg || 'ffmpeg' });
  if (cutter.plan.problems.length) { cutter.cleanup(); throw new Error(`footage: ${cutter.plan.problems.join('; ')}`); }
  for (const w of cutter.plan.warnings) emit({ event: 'warning', message: w });
  try { await cutter.prepareCards(); } catch (err) { cutter.cleanup(); throw err; }     // before the page gets the spec (frame counts)
  const server = await startServer(spec, specDir, cutter);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(spec);
  const launchOpts = {
    headless: true,
    args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
      : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
  };
  if (spec.browser_channel) launchOpts.channel = spec.browser_channel;   // the app's choice (e.g. an installed Chrome), as for pakMap
  const browser = await chromium.launch(launchOpts);
  let ffmpeg = null;
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') pageErrors.push(m.text()); });
    await page.goto(`${origin}/index.html`);
    try {
      await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 120000 });
    } catch (err) {
      throw new Error(`page did not start: ${pageErrors.slice(0, 5).join(' | ') || err.message}`);
    }
    const setupError = await page.evaluate(() => window.__error || null);
    if (setupError) throw new Error(`scene setup failed: ${setupError}`);
    const gl = await page.evaluate(() => {
      const c = document.createElement('canvas').getContext('webgl2'); if (!c) return 'none';
      const ext = c.getExtension('WEBGL_debug_renderer_info'); return ext ? c.getParameter(ext.UNMASKED_RENDERER_WEBGL) : c.getParameter(c.RENDERER);
    });
    emit({ event: 'gpu', renderer: gl, mode: soft ? 'software' : 'hardware' });
    if (process.env.STARMAP_STILLS) {   // quick look: STARMAP_STILLS="0,4,12" writes those moments as JPEGs next to the output
      for (const t of process.env.STARMAP_STILLS.split(',').map(Number)) {
        await cutter.ensure(t, { keepAll: true });
        const b64 = await page.evaluate((tt) => window.renderFrame(tt), t);
        fs.writeFileSync(`${spec.output}.t${t}.jpg`, Buffer.from(b64, 'base64'));
      }
      if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
      emit({ event: 'done', stills: process.env.STARMAP_STILLS });
      return;
    }

    const encode = (out) => {
      const p = spawn(spec.ffmpeg || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
        '-c:v', 'libx264', '-preset', spec.x264_preset || 'medium', '-crf', String(spec.crf ?? 18), '-pix_fmt', 'yuv420p', '-r', String(fps),
        '-movflags', '+faststart', out], { stdio: ['pipe', 'ignore', 'pipe'] });
      let err = '';
      p.stderr.on('data', (d) => { err += d; });
      const done = new Promise((resolve) => p.on('close', (code) => resolve({ code, err })));
      return { p, done };
    };
    const t0 = Date.now();
    let peakHeap = 0, drawn = 0, doneFrames = 0;
    for (const c of chunks) {
      if (c.cached) { doneFrames += c.k1 - c.k0; emit({ event: 'progress', frame: doneFrames, total, ms_per_frame: drawn ? Math.round((Date.now() - t0) / drawn) : 0 }); continue; }
      const part = cacheDir ? c.file.replace(/\.mp4$/, '.part.mp4') : spec.output;
      const enc = encode(part);
      ffmpeg = enc.p;
      for (let i = c.k0; i < c.k1; i++) {
        await cutter.ensure(i / fps);
        const b64 = await page.evaluate((t) => window.renderFrame(t), i / fps);
        const jpg = Buffer.from(b64, 'base64');
        if (!ffmpeg.stdin.write(jpg)) await new Promise((r) => ffmpeg.stdin.once('drain', r));
        drawn++; doneFrames++;
        if (i % 30 === 0 || i === total - 1) {
          const heap = await page.evaluate(() => (performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null));
          if (heap > peakHeap) peakHeap = heap;
          emit({ event: 'progress', frame: doneFrames, total, ms_per_frame: Math.round((Date.now() - t0) / drawn), js_heap_mb: heap });
        }
      }
      ffmpeg.stdin.end();
      const { code, err } = await enc.done;
      if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${err.trim().slice(-500)}`);
      if (cacheDir) fs.renameSync(part, c.file);            // only a finished chunk ever carries its fingerprint's name
    }
    if (cacheDir) { joinChunks(spec, chunks, spec.output); pruneCache(cacheDir, chunks); }
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    const secs = (Date.now() - t0) / 1000;
    emit({ event: 'done', output: spec.output, frames: total, seconds: Math.round(secs * 10) / 10, x_realtime: Math.round(secs / spec.duration * 100) / 100, ms_per_frame: Math.round(secs * 1000 / Math.max(1, drawn)), peak_js_heap_mb: peakHeap, footage: cutter.stats, drawn_frames: drawn, reused_frames: total - drawn });
  } finally {
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await browser.close().catch(() => {});
    server.close();
    cutter.cleanup();
  }
}

main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
