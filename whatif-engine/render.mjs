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
import { createCutter } from './cutter.mjs';

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
  const cutter = createCutter({ spec, mediaDir: mediaDirOf(spec, specDir), ffmpeg: spec.ffmpeg || 'ffmpeg' });
  if (cutter.problems.length) { cutter.cleanup(); throw new Error(`footage: ${cutter.problems.join('; ')}`); }
  const server = await startServer(spec, specDir, cutter);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(spec);
  const soft = process.env.WHATIF_GL === 'software';
  const launchOpts = { headless: true, args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
    : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader', '--hide-scrollbars'] };
  if (spec.browser_channel) launchOpts.channel = spec.browser_channel;
  const browser = await chromium.launch(launchOpts);
  let ffmpeg = null;
  try {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
    const pageErrors = [];
    page.on('pageerror', (e) => pageErrors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') pageErrors.push(m.text()); });
    await page.goto(`${origin}/index.html`);
    try { await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 120000 }); }
    catch (err) { throw new Error(`page did not start: ${pageErrors.slice(0, 5).join(' | ') || err.message}`); }
    const setupError = await page.evaluate(() => window.__error || null);
    if (setupError) throw new Error(`scene setup failed: ${setupError}`);
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
    for (let i = 0; i < total; i++) {
      await cutter.ensure(i / fps);
      const b64 = await page.evaluate((t) => window.renderFrame(t), i / fps);
      if (!ffmpeg.stdin.write(Buffer.from(b64, 'base64'))) await new Promise((r) => ffmpeg.stdin.once('drain', r));
      if (i % 30 === 0 || i === total - 1) emit({ event: 'progress', frame: i + 1, total, ms_per_frame: Math.round((Date.now() - t0) / (i + 1)) });
    }
    ffmpeg.stdin.end();
    const code = await closed;
    if (code !== 0) throw new Error(`ffmpeg exited ${code}: ${err.trim().slice(-500)}`);
    if (pageErrors.length) emit({ event: 'warning', message: pageErrors.slice(0, 3).join(' | ') });
    emit({ event: 'done', output: spec.output, frames: total, seconds: Math.round((Date.now() - t0) / 100) / 10 });
  } finally {
    if (ffmpeg && ffmpeg.exitCode === null) { try { ffmpeg.stdin.destroy(); ffmpeg.kill('SIGKILL'); } catch { /* gone */ } }
    await browser.close().catch(() => {});
    server.close(); cutter.cleanup();
  }
}
main().catch((err) => { emit({ event: 'error', message: String((err && err.message) || err) }); process.exit(1); });
