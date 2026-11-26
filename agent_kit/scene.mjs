// AGENT KIT SCENE RENDERER: one HTML scene file -> one video clip (or a few still frames).
//
// The scene page draws any moment on request:   window.renderAt = async (t) => { ... }   (t in seconds from the scene start)
// Optional: window.sceneReady (a promise: fonts/images/textures loaded) and window.SCENE = { width, height, fps } overrides.
// Every frame must be a pure function of t (seeded randomness, no clocks), so frames can be drawn in any order by several workers.
//
//   node agent_kit/scene.mjs --html scene.html --out clip.mp4 --duration 6 [--fps 30 --w 1920 --h 1080 --workers 3]
//   node agent_kit/scene.mjs --html scene.html --stills 0.5,2,4 --outdir stills/        (PNG stills, nothing encoded)
//   node agent_kit/scene.mjs --html overlay.html --over media.mp4 --out clip.mp4 ...    (transparent page drawn over a clip)
//
// Pages are served from the repository root, so a scene can load /agent_kit/lib/kit.js, /agent_kit/lib/three.module.js and
// any file given by absolute path through /@fs/<absolute path>. One JSON line per event goes to stdout.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { launchChromium } from '../voxelmap-engine/lib/launch.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const FLOW = path.join(REPO, 'flow-engine');
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');

function parseArgs(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    if (!argv[i].startsWith('--')) continue;
    const k = argv[i].slice(2), v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) a[k] = true; else { a[k] = v; i++; }
  }
  return a;
}

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.css': 'text/css',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.gif': 'image/gif',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.ttf': 'font/ttf', '.otf': 'font/otf', '.woff2': 'font/woff2', '.woff': 'font/woff',
  '.glb': 'model/gltf-binary', '.hdr': 'application/octet-stream' };
const ALIAS = { '/agent_kit/lib/three.module.js': path.join(REPO, 'starmap-engine/node_modules/three/build/three.module.js'),
  '/agent_kit/lib/three.core.js': path.join(REPO, 'starmap-engine/node_modules/three/build/three.core.js') };

function serve(sceneDir) {
  const srv = http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    let file;
    if (ALIAS[p]) file = ALIAS[p];
    else if (p.startsWith('/@fs/')) file = p.slice(4);
    else if (p.startsWith('/@scene/')) file = path.join(sceneDir, p.slice(8));
    else file = path.join(REPO, p);
    fs.readFile(file, (err, buf) => {
      if (err) { res.writeHead(404); res.end('not found: ' + p); return; }
      let type = TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream';
      if (/^text\/|javascript|json/.test(type)) type += '; charset=utf-8';     // "·", "–" and non-English text stay right
      res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
      res.end(buf);
    });
  });
  return new Promise((ok) => srv.listen(0, '127.0.0.1', () => ok(srv)));
}

function ffmpeg(args) {
  const p = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: ['pipe', 'inherit', 'pipe'] });
  let err = '';
  p.stderr.on('data', (d) => { err += d; });
  const done = new Promise((ok, bad) => p.on('close', (c) => (c === 0 ? ok() : bad(new Error('ffmpeg: ' + err.trim().split('\n').slice(-3).join(' | '))))));
  return { p, done };
}

async function openPage(browser, url, W, H, transparent, words = null) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  if (words) await page.addInitScript((w) => { window.WORDS = w; }, words);   // this scene's spoken words, scene-relative times
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e.message || e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForFunction(() => typeof window.renderAt === 'function', null, { timeout: 20000 }).catch(() => {
    throw new Error('the scene page never defined window.renderAt(t)' + (errors.length ? ': ' + errors.slice(0, 3).join(' | ') : ''));
  });
  await page.evaluate(async (tr) => {
    if (tr) document.documentElement.style.background = document.body.style.background = 'transparent';
    if (window.sceneReady) await window.sceneReady;
    if (document.fonts) await document.fonts.ready;
  }, transparent);
  return { page, errors };
}

async function frame(page, t, W, H, png) {
  await page.evaluate(async (tt) => {
    await window.renderAt(tt);
    // CSS animations and transitions, if the page uses any, are seeked to t too
    for (const a of document.getAnimations ? document.getAnimations() : []) { a.pause(); a.currentTime = tt * 1000; }
  }, t);
  return page.screenshot({ type: png ? 'png' : 'jpeg', quality: png ? undefined : 92, omitBackground: png,
    clip: { x: 0, y: 0, width: W, height: H }, optimizeForSpeed: true });
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (!a.html) throw new Error('--html scene.html is required');
  const html = path.resolve(a.html);
  if (!fs.existsSync(html)) throw new Error('no scene file: ' + html);
  const srv = await serve(path.dirname(html));
  const url = `http://127.0.0.1:${srv.address().port}/@fs${html}`;
  const { chromium } = createRequire(path.join(FLOW, 'package.json'))('playwright');
  const launch = () => launchChromium(chromium, { headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=metal',
    '--hide-scrollbars', '--autoplay-policy=no-user-gesture-required'] }, { flowDir: FLOW, emit });
  let W = +(a.w || 1920), H = +(a.h || 1080), FPS = +(a.fps || 30);
  const over = a.over ? path.resolve(a.over) : '';
  const words = a.words ? JSON.parse(fs.readFileSync(path.resolve(a.words), 'utf8')) : null;
  const t0 = Date.now();
  const browsers = [];
  try {
    const b0 = await launch(); browsers.push(b0);
    const first = await openPage(b0, url, W, H, !!over, words);
    const cfg = await first.page.evaluate(() => window.SCENE || {});
    if (cfg.width && cfg.height && (cfg.width !== W || cfg.height !== H)) {
      W = cfg.width; H = cfg.height; await first.page.setViewportSize({ width: W, height: H });
    }
    if (cfg.fps) FPS = cfg.fps;

    if (a.stills) {                                       // a few PNG stills to look at: nothing encoded
      const outdir = path.resolve(a.outdir || path.join(path.dirname(html), 'stills'));
      fs.mkdirSync(outdir, { recursive: true });
      const files = [];
      for (const t of String(a.stills).split(',').map(Number)) {
        const f = path.join(outdir, `${path.basename(html, '.html')}_t${t.toFixed(2)}.png`);
        fs.writeFileSync(f, await frame(first.page, t, W, H, !!over));
        files.push(f);
      }
      emit({ event: 'done', stills: files, errors: first.errors.slice(0, 5) });
      return;
    }

    const dur = +(a.duration || cfg.duration || 5);
    const N = Math.max(1, Math.round(dur * FPS));
    const out = path.resolve(a.out || html.replace(/\.html$/, '.mp4'));
    const workers = Math.max(1, Math.min(+(a.workers || 2), 6, Math.ceil(N / 30)));
    const tmp = fs.mkdtempSync(path.join(path.dirname(out), '.seg_'));
    emit({ event: 'start', frames: N, fps: FPS, w: W, h: H, workers, over: over || undefined });
    const pages = [first];
    for (let i = 1; i < workers; i++) { const b = await launch(); browsers.push(b); pages.push(await openPage(b, url, W, H, !!over, words)); }
    const per = Math.ceil(N / workers);
    let doneFrames = 0, lastLog = 0;
    const segs = await Promise.all(pages.map(async ({ page }, wi) => {
      const f0 = wi * per, f1 = Math.min(N, f0 + per);
      if (f0 >= f1) return null;
      const seg = path.join(tmp, `seg${wi}.mp4`);
      const enc = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', '-r', String(FPS), '-an', seg];
      const args = over
        ? ['-ss', ((f0 / FPS)).toFixed(4), '-i', over, '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
           '-filter_complex', `[0:v]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},fps=${FPS},setpts=PTS-STARTPTS[b];[b][1:v]overlay=0:0:shortest=1[v]`,
           '-map', '[v]', '-frames:v', String(f1 - f0), ...enc]
        : ['-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', ...enc];
      const ff = ffmpeg(args);
      for (let f = f0; f < f1; f++) {
        const buf = await frame(page, f / FPS, W, H, !!over);
        if (!ff.p.stdin.write(buf)) await new Promise((r) => ff.p.stdin.once('drain', r));
        doneFrames++;
        if (Date.now() - lastLog > 3000) { lastLog = Date.now(); emit({ event: 'progress', frames: doneFrames, of: N }); }
      }
      ff.p.stdin.end();
      await ff.done;
      return seg;
    }));
    const list = path.join(tmp, 'list.txt');
    fs.writeFileSync(list, segs.filter(Boolean).map((s) => `file '${s}'`).join('\n'));
    await ffmpeg(['-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', '-movflags', '+faststart', out]).done;
    fs.rmSync(tmp, { recursive: true, force: true });
    const errs = pages.flatMap((p) => p.errors).slice(0, 5);
    emit({ event: 'done', out, seconds: +((Date.now() - t0) / 1000).toFixed(1), frames: N, errors: errs });
  } finally {
    await Promise.all(browsers.map((b) => b.close().catch(() => {})));
    srv.close();
  }
}

main().catch((e) => { emit({ event: 'error', message: String(e && e.message || e) }); process.exit(1); });
