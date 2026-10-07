// StarMap renderer: node render.mjs <spec.json> [output.mp4]
//
// Adapted copy of pakmap-engine/render.mjs (StarMap shares no code with pakMap): a local server for the page, its modules,
// three.js, textures and fonts; a hidden Chromium; window.renderFrame(t) for every frame; each JPEG piped to ffmpeg. The
// same spec always gives the same video. STARMAP_GL=software renders on the CPU (SwiftShader): the worst case of a PC
// without a usable graphics card.
//
// stdout: one JSON object per line -- {"event":"progress","frame":n,"total":N,"ms_per_frame":x}, {"event":"done",...},
// {"event":"error","message":...}
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const TYPES = { '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.webp': 'image/webp', '.jpeg': 'image/jpeg', '.mjs': 'text/javascript', '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf', '.jpg': 'image/jpeg', '.png': 'image/png' };

function loadPlaywright(spec) {
  for (const dir of [spec.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean)) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}

function startServer(spec, specDir) {
  const mediaDir = spec.media_dir ? path.resolve(specDir, spec.media_dir) : path.join(specDir, 'media');
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

async function main() {
  const specPath = process.argv[2];
  const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
  spec.output = process.argv[3] || spec.output || path.join(path.dirname(path.resolve(specPath)), 'starmap.mp4');
  const { width, height, fps } = spec;
  const total = Math.round(spec.duration * fps);
  const server = await startServer(spec, path.dirname(path.resolve(specPath)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(spec);
  const soft = process.env.STARMAP_GL === 'software';
  const browser = await chromium.launch({
    headless: true,
    args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
      : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'],
  });
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
        const b64 = await page.evaluate((tt) => window.renderFrame(tt), t);
        fs.writeFileSync(`${spec.output}.t${t}.jpg`, Buffer.from(b64, 'base64'));
      }
      if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
      emit({ event: 'done', stills: process.env.STARMAP_STILLS });
      return;
    }

    ffmpeg = spawn(spec.ffmpeg || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', spec.x264_preset || 'medium', '-crf', String(spec.crf ?? 18), '-pix_fmt', 'yuv420p', '-r', String(fps),
      '-movflags', '+faststart', spec.output], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ffErr = '';
    ffmpeg.stderr.on('data', (d) => { ffErr += d; });
    const ffDone = new Promise((resolve) => ffmpeg.on('close', resolve));
    const t0 = Date.now();
    let peakHeap = 0;
    for (let i = 0; i < total; i++) {
      const b64 = await page.evaluate((t) => window.renderFrame(t), i / fps);
      const jpg = Buffer.from(b64, 'base64');
      if (!ffmpeg.stdin.write(jpg)) await new Promise((r) => ffmpeg.stdin.once('drain', r));
      if (i % 30 === 0 || i === total - 1) {
        const heap = await page.evaluate(() => (performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null));
        if (heap > peakHeap) peakHeap = heap;
        emit({ event: 'progress', frame: i + 1, total, ms_per_frame: Math.round((Date.now() - t0) / (i + 1)), js_heap_mb: heap });
      }
    }
    ffmpeg.stdin.end();
    const code = await ffDone;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${ffErr.trim().slice(-500)}`);
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    const secs = (Date.now() - t0) / 1000;
    emit({ event: 'done', output: spec.output, frames: total, seconds: Math.round(secs * 10) / 10, x_realtime: Math.round(secs / spec.duration * 100) / 100, ms_per_frame: Math.round(secs * 1000 / total), peak_js_heap_mb: peakHeap });
  } finally {
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await browser.close().catch(() => {});
    server.close();
  }
}

main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
