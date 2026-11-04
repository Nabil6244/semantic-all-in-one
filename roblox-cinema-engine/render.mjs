// Roblox Cinema renderer.
//   node render.mjs --csv samples/dday_1944.csv --out out/dday.mp4 [--words words.json] [--preview | --final]
//        [--stills 3,12.5,40] [--clip 20,30] [--plan-only] [--workers 3] [--fps 24]
// --plan-only writes <out>.plan.json (+ .cues.json) and stops.  --stills writes <out>.t<sec>.jpg for those moments.
// --preview = 1280x720 (default), --final = 1920x1080.  stdout: one JSON object per line (progress / perf / done / error).
import fs from 'node:fs';
import zlib from 'node:zlib';
import http from 'node:http';
import path from 'node:path';
import os from 'node:os';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { parseStory, storyFromText, validateStory } from './lib/csv.mjs';
import { direct, VOCAB } from './lib/director.mjs';
import { assembleScene } from './lib/assemble.mjs';
import { makeProj } from './lib/mapproj.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..');
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const TYPES = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf', '.png': 'image/png' };

function args() {
  const a = process.argv.slice(2), o = { fps: 24, res: 720 };
  for (let i = 0; i < a.length; i++) {
    const k = a[i];
    if (k === '--csv') o.csv = a[++i]; else if (k === '--text') o.text = a[++i]; else if (k === '--out') o.out = a[++i]; else if (k === '--words') o.words = a[++i];
    else if (k === '--stills') o.stills = a[++i].split(',').map(Number); else if (k === '--clip') o.clip = a[++i].split(',').map(Number);
    else if (k === '--preview') o.res = 720; else if (k === '--final') o.res = 1080; else if (k === '--plan-only') o.planOnly = true;
    else if (k === '--workers') o.workers = Number(a[++i]); else if (k === '--fps') o.fps = Number(a[++i]); else if (k === '--soft') o.soft = true;
    else if (k === '--range') o.range = a[++i].split(',').map(Number); else if (k === '--credit') o.credit = a[++i]; else if (k === '--crf') o.crf = Number(a[++i]);
    else if (k === '--no-music') o.noMusic = true; else if (k === '--preset') o.preset = a[++i]; else if (k === '--title') o.title = a[++i];
  }
  return o;
}

export function buildPlan(opts) {
  const text = fs.readFileSync(opts.csv || opts.text, 'utf8');
  const story = opts.csv ? parseStory(text) : storyFromText(text, opts.title || '');
  const errs = validateStory(story, VOCAB);
  const words = opts.words ? JSON.parse(fs.readFileSync(opts.words, 'utf8')) : null;
  const H = opts.res === 1080 ? 1080 : 720, Wd = H === 1080 ? 1920 : 1280;
  const plan = direct(story, { fps: opts.fps, width: Wd, height: H, words: words && (words.words || words) });
  return { story, plan, errs };
}

// ---- Natural Earth countries cropped and projected for each map scene --------------------------------------------------------
function loadCountries() {
  const f = path.join(ROOT, 'map_scene', 'data', 'countries.json.gz');
  if (!fs.existsSync(f)) return [];
  return JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString()).features;
}
export function mapGeo(plan, features) {
  const geo = {};
  for (const s of plan.scenes) {
    if (s.env !== 'map' || !s.map) continue;
    const P = makeProj(s.map.bbox), [lon0, lat0, lon1, lat1] = s.map.bbox, pad = 2;
    const countries = [];
    for (const f of features) {
      const polys = f.g.type === 'Polygon' ? [f.g.coordinates] : f.g.coordinates, out = [];
      for (const poly of polys) {
        const ring = poly[0]; let mnx = 1e9, mxx = -1e9, mny = 1e9, mxy = -1e9;
        for (const [x, y] of ring) { mnx = Math.min(mnx, x); mxx = Math.max(mxx, x); mny = Math.min(mny, y); mxy = Math.max(mxy, y); }
        if (mxx < lon0 - pad || mnx > lon1 + pad || mxy < lat0 - pad || mny > lat1 + pad) continue;
        const pts = []; let last = null;
        for (const [lo, la] of ring) {
          let [x, z] = P.toXZ(Math.max(lon0 - 12, Math.min(lon1 + 12, lo)), Math.max(lat0 - 12, Math.min(lat1 + 12, la)));
          if (!last || Math.hypot(x - last[0], z - last[1]) > 1.6) { pts.push([+x.toFixed(1), +z.toFixed(1)]); last = [x, z]; }
        }
        if (pts.length >= 4) out.push(pts);
      }
      if (out.length) countries.push({ name: f.n, polys: out });
    }
    const want = new Set([s.place && s.place.country, ...s.map.pins.map((p) => p.country)].filter(Boolean).map((x) => x.toLowerCase()));
    const focus = features.filter((f) => [f.n, ...(f.alt || [])].some((n) => want.has(String(n).toLowerCase()))).map((f) => f.n);
    geo[s.id] = { countries, focus };
  }
  return geo;
}

export function sceneCues(plan) {
  const cues = [];
  for (const s of plan.scenes) { try { const A = assembleScene(JSON.parse(JSON.stringify(s))); for (const c of A.cues) cues.push({ ...c, scene: s.id }); } catch (e) { emit({ event: 'warning', message: `cues for ${s.id}: ${e.message}` }); } }
  return cues.sort((a, b) => a.t - b.t);
}

function threeRoot() {
  for (const d of [path.join(HERE, 'node_modules', 'three'), path.join(ROOT, 'starmap-engine', 'node_modules', 'three')]) if (fs.existsSync(d)) return d;
  throw new Error('three.js not found (expected starmap-engine/node_modules/three)');
}
function loadPlaywright() {
  for (const d of [path.join(ROOT, 'flow-engine')]) { try { return createRequire(path.join(d, 'package.json'))('playwright'); } catch { /* next */ } }
  throw new Error('Playwright not found (expected in flow-engine/node_modules)');
}

function startServer(planJson, geoJson) {
  const three = threeRoot();
  const safe = (base, rel) => { const f = path.resolve(base, decodeURIComponent(rel)); return f.startsWith(path.resolve(base) + path.sep) ? f : null; };
  const server = http.createServer((req, res) => {
    const u = new URL(req.url, 'http://x'), p = u.pathname;
    let file = null;
    if (p === '/plan.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(planJson); }
    if (p === '/geo.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(geoJson); }
    if (p === '/' || p === '/index.html') file = path.join(HERE, 'web', 'page.html');
    else if (p.startsWith('/web/')) file = safe(path.join(HERE, 'web'), p.slice(5));
    else if (p.startsWith('/lib/')) file = safe(path.join(HERE, 'lib'), p.slice(5));
    else if (p.startsWith('/fonts/')) file = safe(path.join(HERE, 'assets', 'fonts'), p.slice(7));
    else if (p.startsWith('/three/addons/')) file = safe(path.join(three, 'examples', 'jsm'), p.slice(14));
    else if (p.startsWith('/three/')) file = safe(path.join(three, 'build'), p.slice(7));
    if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

const FRAME_TIMEOUT = 90000;
const withTimeout = (p, ms, what) => { let t; return Promise.race([p, new Promise((_, rej) => { t = setTimeout(() => rej(new Error(`${what} took over ${ms / 1000} s`)), ms); })]).finally(() => clearTimeout(t)); };

async function openPage(chromium, origin, W, H, soft, pageErrors) {
  const launch = { headless: true, args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--hide-scrollbars']
    : ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--hide-scrollbars'] };
  const browser = await chromium.launch(launch);
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  page.on('pageerror', (e) => pageErrors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') pageErrors.push(m.text()); });
  await page.goto(`${origin}/index.html?w=${W}&h=${H}`);
  await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 120000 });
  const err = await page.evaluate(() => window.__error || null);
  if (err) throw new Error(`page setup failed: ${err}`);
  return { browser, page };
}

async function main() {
  const o = args();
  if (!o.csv && !o.text) throw new Error('--csv or --text is required');
  const out = path.resolve(o.out || path.join(HERE, 'out', 'roblox_cinema.mp4'));
  fs.mkdirSync(path.dirname(out), { recursive: true });
  const { story, plan, errs } = buildPlan(o);
  if (errs.length) emit({ event: 'warning', message: `story problems: ${errs.slice(0, 8).join(' | ')}` });
  for (const w of plan.warnings) emit({ event: 'warning', message: w });
  const TITLES = { lost_frontier: 'Lost Frontier', interloper: 'Interloper', echoes_of_time_v2: 'Echoes of Time v2', ascending_the_vale: 'Ascending the Vale', long_note_four: 'Long Note Four', despair_and_triumph: 'Despair and Triumph', stormfront: 'Stormfront', dark_fog: 'Dark Fog' };
  const tracks = (plan.audio.music.tracks || []).filter((x) => TITLES[x]);
  plan.hud.credit = o.credit || (!o.noMusic && tracks.length ? `Music: ${tracks.map((x) => `\u201C${TITLES[x]}\u201D`).join(' and ')} by Kevin MacLeod (incompetech.com), CC BY 4.0` : null);
  const features = loadCountries(), geo = mapGeo(plan, features), cues = sceneCues(plan);
  fs.writeFileSync(out + '.plan.json', JSON.stringify(plan, null, 1));
  fs.writeFileSync(out + '.cues.json', JSON.stringify({ duration: plan.duration, ambience: plan.audio.ambience, music: plan.audio.music, cues: [...plan.audio.cues, ...cues] }, null, 1));
  emit({ event: 'plan', scenes: plan.scenes.length, duration: plan.duration, voiceTimed: plan.voiceTimed, warnings: plan.warnings.length, cues: cues.length });
  if (o.planOnly) { emit({ event: 'done', plan: out + '.plan.json' }); return; }

  const { width: W, height: H, fps } = plan, total = Math.ceil(plan.duration * fps);
  const server = await startServer(JSON.stringify(plan), JSON.stringify(geo));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { chromium } = loadPlaywright(), pageErrors = [];
  let { browser, page } = await openPage(chromium, origin, W, H, o.soft || process.env.RCE_GL === 'software', pageErrors);
  try {
    const gpu = await page.evaluate(() => { const c = document.createElement('canvas'), g = c.getContext('webgl2'); const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER); });
    emit({ event: 'gpu', renderer: gpu });
    const shot = () => page.screenshot({ type: 'jpeg', quality: 94 });
    if (o.stills) {
      for (const t of o.stills) { const st = await page.evaluate((tt) => window.renderFrame(tt), t); fs.writeFileSync(`${out}.t${t}.jpg`, await shot()); emit({ event: 'still', t, ...st }); }
      emit({ event: 'perf', ...(await page.evaluate(() => window.__perf())) });
      if (pageErrors.length) emit({ event: 'warning', message: `page: ${pageErrors.slice(0, 5).join(' | ')}` });
      emit({ event: 'done', stills: o.stills }); return;
    }
    const range = o.range ? o.range.map(Number) : o.clip ? [Math.floor(o.clip[0] * fps), Math.ceil(o.clip[1] * fps)] : [0, total];
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', o.preset || 'medium', '-crf', String(o.crf ?? 18),
      '-vf', 'format=rgb24,scale=out_range=tv:out_color_matrix=bt709:flags=accurate_rnd+full_chroma_int,format=yuv420p',
      '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', String(fps), '-movflags', '+faststart', out], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ferr = ''; ff.stderr.on('data', (d) => { ferr += d; });
    const closed = new Promise((r) => ff.on('close', r));
    const t0 = Date.now(), frameMs = [], shotMs = [], samples = [];
    for (let i = range[0]; i < range[1]; i++) {
      const a = Date.now();
      const st = await withTimeout(page.evaluate((t) => window.renderFrame(t), i / fps), FRAME_TIMEOUT, `frame ${i}`);
      const b = Date.now();
      const buf = await withTimeout(shot(), FRAME_TIMEOUT, `screenshot ${i}`);
      shotMs.push(Date.now() - b); frameMs.push(b - a);
      if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
      if ((i - range[0]) % 48 === 0) { const mem = await page.evaluate(() => window.__perf().heap); samples.push({ frame: i, heapMB: mem, rssMB: Math.round(process.memoryUsage().rss / 1e6) }); }
      if ((i - range[0]) % 24 === 0) emit({ event: 'progress', frame: i - range[0] + 1, total: range[1] - range[0], ms_per_frame: Math.round((Date.now() - t0) / (i - range[0] + 1)), scene: st.scene });
    }
    ff.stdin.end();
    if ((await closed) !== 0) throw new Error(`ffmpeg failed: ${ferr.slice(-400)}`);
    const sum = (a) => a.reduce((s, x) => s + x, 0), sorted = [...frameMs].sort((x, y) => x - y);
    const pf = await page.evaluate(() => window.__perf());
    emit({ event: 'perf', frames: frameMs.length, wall_s: (Date.now() - t0) / 1000, mean_render_ms: +(sum(frameMs) / frameMs.length).toFixed(1), p95_render_ms: sorted[Math.floor(sorted.length * 0.95)], max_render_ms: sorted[sorted.length - 1],
      mean_screenshot_ms: +(sum(shotMs) / shotMs.length).toFixed(1), max_draw_calls: pf.maxDraw, max_triangles: pf.maxTris, max_live_particles: pf.maxLive, builds: pf.builds, memory: samples, gpu_memory: pf.memory });
    if (pageErrors.length) emit({ event: 'warning', message: `page: ${[...new Set(pageErrors)].slice(0, 6).join(' | ')}` });
    emit({ event: 'done', output: out, frames: frameMs.length });
  } finally { try { await browser.close(); } catch { /* gone */ } server.close(); }
}
if (process.argv[1] === fileURLToPath(import.meta.url)) main().catch((e) => { emit({ event: 'error', message: String((e && e.stack) || e) }); process.exit(1); });
