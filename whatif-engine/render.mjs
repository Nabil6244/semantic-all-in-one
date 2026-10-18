// What If renderer: node render.mjs <spec.json> [output.mp4]
// A local server for the page, its modules, three.js, models, textures and fonts; a hidden Chromium; window.renderFrame(t)
// for every frame; each JPEG piped to ffmpeg. WHATIF_STILLS="3,12.5" writes just those moments as JPEGs.
// stdout: one JSON object per line -- {"event":"progress","frame":n,"total":N}, {"event":"done",...}, {"event":"error","message":...}
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createCutter, resolveMedia } from './cutter.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const TYPES = { '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.webp': 'image/webp', '.jpeg': 'image/jpeg', '.mjs': 'text/javascript', '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf', '.jpg': 'image/jpeg', '.png': 'image/png', '.bin': 'application/octet-stream', '.wasm': 'application/wasm' };
const firstDir = (...dirs) => dirs.find((d) => d && fs.existsSync(d));

function loadPlaywright(spec) {
  for (const dir of [spec.playwright_dir, path.join(HERE, '..', 'flow-engine')].filter(Boolean)) {
    try { return createRequire(path.join(dir, 'package.json'))('playwright'); } catch { /* next */ }
  }
  throw new Error('Playwright not found (expected in flow-engine/node_modules).');
}
// three.js comes from this folder's node_modules, or the sibling StarMap engine's (the same pinned package)
const threeRoot = () => firstDir(path.join(HERE, 'node_modules', 'three'), path.join(HERE, '..', 'starmap-engine', 'node_modules', 'three'));

export const mediaDirOf = (spec, specDir) => (spec.media_dir ? path.resolve(specDir, spec.media_dir) : path.join(specDir, 'media'));

// A frame that takes longer than this means the page froze, not that it is slow (a normal frame takes well under a second).
const FRAME_TIMEOUT_MS = Number(process.env.WHATIF_FRAME_TIMEOUT_MS) || 60000;
const MAX_RESTARTS = 5;
class FrameTimeout extends Error {}
const withTimeout = (promise, ms, what) => {
  let timer;
  const limit = new Promise((_, fail) => { timer = setTimeout(() => fail(new FrameTimeout(`${what} took over ${ms / 1000} s`)), ms); });
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer));
};
// a frozen browser may not answer close() either: give it 10 s, then kill its process
async function closeQuietly(b) {
  if (!b) return;
  const proc = typeof b.process === 'function' ? b.process() : null;
  try { await withTimeout(b.close(), 10000, 'closing the browser'); }
  catch { try { if (proc) proc.kill('SIGKILL'); } catch { /* gone */ } }
}

function startServer(spec, specDir, cutter) {
  const mediaDir = mediaDirOf(spec, specDir), three = threeRoot(), pageSpec = JSON.stringify(spec);
  const modelDir = spec.model_dir || path.join(HERE, 'assets', 'models'), texDir = spec.texture_dir || path.join(HERE, 'assets', 'textures');
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://x');
    let file = null;
    const safe = (base, name) => { const f = path.resolve(base, decodeURIComponent(name)); return f.startsWith(path.resolve(base) + path.sep) ? f : null; };
    if (url.pathname === '/spec.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(pageSpec); }
    if (url.pathname === '/' || url.pathname === '/index.html') file = path.join(HERE, 'page.html');
    else if (url.pathname === '/page.js') file = path.join(HERE, 'page.js');
    else if (/^\/(lib|layers)\/[\w-]+\.mjs$/.test(url.pathname)) file = path.join(HERE, url.pathname);
    else if (/^\/footage\/\d+\/\d+\.jpg$/.test(url.pathname) && cutter) { const [, , i, k] = url.pathname.split('/'); file = cutter.frameFile(Number(i), parseInt(k, 10)); }
    else if (url.pathname.startsWith('/media/')) file = safe(mediaDir, url.pathname.slice(7));
    else if (url.pathname.startsWith('/models/')) file = safe(modelDir, url.pathname.slice(8));
    else if (url.pathname.startsWith('/textures/')) file = safe(texDir, url.pathname.slice(10));
    else if (url.pathname === '/three/three.module.min.js' && three) file = path.join(three, 'build', 'three.module.min.js');
    else if (url.pathname.startsWith('/three/addons/') && three) file = safe(path.join(three, 'examples', 'jsm'), url.pathname.slice(14));
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
  spec.output = process.argv[3] || spec.output || path.join(path.dirname(path.resolve(specPath)), 'whatif.mp4');
  const { width, height, fps } = spec, total = Math.round(spec.duration * fps), specDir = path.dirname(path.resolve(specPath));
  // a video shot whose file is a still picture (a stock or Visual Plan choice that returned an image): drawn as a picture with the slow
  // drift -- ffmpeg told to loop a single image as a clip never finishes (a still render hung 43 minutes on one)
  for (const s of spec.shots || []) {
    if (s.kind === 'video' && s.file && /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i.test(s.file)) {
      emit({ event: 'warning', message: `shot ${s.id}: ${s.file} is a picture, not a clip; drawn as a still` });
      s.kind = 'image';
      s.drift = s.drift || { from: 1.0, to: 1.04, fx: 0.5, fy: 0.5 };
    }
  }
  // a picture or clip that is not on disk: that shot is drawn as a plate (reported), never a stop
  for (const s of spec.shots || []) {
    if (['image', 'video'].includes(s.kind) && s.file && !fs.existsSync(resolveMedia(s.file, mediaDirOf(spec, specDir)))) {
      emit({ event: 'warning', message: `shot ${s.id}: ${s.file} is not on disk; drawn as a plate` });
      s.kind = 'plate';
    }
  }
  const cutter = createCutter({ spec, mediaDir: mediaDirOf(spec, specDir), ffmpeg: spec.ffmpeg || 'ffmpeg' });
  if (cutter.problems.length) { cutter.cleanup(); throw new Error(`footage: ${cutter.problems.join('; ')}`); }
  const server = await startServer(spec, specDir, cutter);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(spec);
  const soft = process.env.WHATIF_GL === 'software';
  const launchOpts = { headless: true, args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
    : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'] };
  if (spec.browser_channel) launchOpts.channel = spec.browser_channel;
  const pageErrors = [];
  // one browser and page; opened again by the watchdog when a frame freezes
  const openPage = async () => {
    const b = await chromium.launch(launchOpts);
    try {
      const pg = await b.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
      pg.on('pageerror', (e) => pageErrors.push(String(e)));
      pg.on('console', (m) => { if (m.type() === 'error') pageErrors.push(m.text()); });
      await pg.goto(`${origin}/index.html`);
      try { await pg.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 120000 }); }
      catch (err) { throw new Error(`page did not start: ${pageErrors.slice(0, 5).join(' | ') || err.message}`); }
      const setupError = await pg.evaluate(() => window.__error || null);
      if (setupError) throw new Error(`scene setup failed: ${setupError}`);
      return { browser: b, page: pg };
    } catch (e) { await closeQuietly(b); throw e; }
  };
  let { browser, page } = await openPage();
  let ffmpeg = null;
  try {
    emit({ event: 'gpu', mode: soft ? 'software' : 'hardware' });
    if (process.env.WHATIF_STILLS) {
      for (const t of process.env.WHATIF_STILLS.split(',').map(Number)) {
        await cutter.ensure(t, { keepAll: true });
        const b64 = await page.evaluate((tt) => window.renderFrame(tt), t);
        fs.writeFileSync(`${spec.output}.t${t}.jpg`, Buffer.from(b64, 'base64'));
      }
      if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
      emit({ event: 'done', stills: process.env.WHATIF_STILLS });
      return;
    }
    ffmpeg = spawn(spec.ffmpeg || 'ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', spec.x264_preset || 'medium', '-crf', String(spec.crf ?? 18), '-pix_fmt', 'yuv420p', '-r', String(fps), '-movflags', '+faststart', spec.output], { stdio: ['pipe', 'ignore', 'pipe'] });
    let err = ''; ffmpeg.stderr.on('data', (d) => { err += d; });
    const closed = new Promise((resolve) => ffmpeg.on('close', (code) => resolve(code)));
    const t0 = Date.now();
    let last = null, reused = 0, restarts = 0;
    // a part of a parallel render draws only its frames [from, to): every frame is a function of its time alone, so the parts
    // joined are the same frames one render makes (whatif/engine_runner.py splits at shot cuts)
    const [from, to] = Array.isArray(spec.frame_range) ? spec.frame_range.map(Number) : [0, total];
    for (let i = from; i < to; i++) {
      await cutter.ensure(i / fps);
      // tests only: the page freezes once at this frame, as render #016's did
      if (process.env.WHATIF_TEST_FREEZE_AT && i === Number(process.env.WHATIF_TEST_FREEZE_AT) && restarts === 0) {
        await page.evaluate(() => { window.renderFrame = () => new Promise(() => {}); });
      }
      let b64 = null;
      for (let k = 0; k < 2 && b64 === null; k++) {
        try { b64 = await withTimeout(page.evaluate((t) => window.renderFrame(t), i / fps), FRAME_TIMEOUT_MS, `frame ${i}`); }
        catch (e) {
          if (e instanceof FrameTimeout) {
            // the page froze (render #016 waited 11 minutes on one picture, then the 6-hour limit): a fresh browser draws it again
            if (restarts >= MAX_RESTARTS) throw new Error(`the page froze ${restarts + 1} times (last at frame ${i} of ${total}); stopped`);
            restarts++;
            emit({ event: 'warning', message: `frame ${i} (${(i / fps).toFixed(1)} s) took over ${FRAME_TIMEOUT_MS / 1000} s: the page froze; restarting the browser and continuing from this frame (restart ${restarts} of ${MAX_RESTARTS})` });
            await closeQuietly(browser);
            ({ browser, page } = await openPage());
          }
          if (k === 1 && last === null) throw e;
          if (k === 1) emit({ event: 'warning', message: `frame ${i} could not be drawn (${String(e.message || e).slice(0, 200)}); the frame before it is used` });
        }
      }
      if (b64 === null) { b64 = last; reused++; }
      last = b64;
      if (!ffmpeg.stdin.write(Buffer.from(b64, 'base64'))) await new Promise((r) => ffmpeg.stdin.once('drain', r));
      if ((i - from) % 30 === 0 || i === to - 1) emit({ event: 'progress', frame: i - from + 1, total: to - from, ms_per_frame: Math.round((Date.now() - t0) / (i - from + 1)) });
    }
    ffmpeg.stdin.end();
    const code = await closed;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${err.trim().slice(-500)}`);
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    const repairs = await page.evaluate(() => (window.__whatif && window.__whatif.warnings) || []).catch(() => []);
    for (const m of repairs.slice(0, 40)) emit({ event: 'warning', message: m });
    if (reused) emit({ event: 'warning', message: `${reused} frame(s) repeated the frame before them` });
    for (const m of cutter.problems) emit({ event: 'warning', message: `${m}; that shot was drawn as a plate` });
    emit({ event: 'done', output: spec.output, frames: to - from, seconds: Math.round((Date.now() - t0) / 100) / 10 });
  } finally {
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await closeQuietly(browser);
    server.close(); cutter.cleanup();
  }
}
main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
