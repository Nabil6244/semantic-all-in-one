#!/usr/bin/env node
// Step-1 spike: script lines -> Edge voices -> timeline -> mouth envelope -> GPU Chromium frames -> mp4 with voice.
// Usage: node cartoon3d-engine/spike.mjs [--out path.mp4] [--w 1280 --h 720] [--stills 1,3.5,6]
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.dirname(HERE);
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const OUT = path.resolve(arg('out', path.join(HERE, 'out', 'spike.mp4'))), W = Number(arg('w', 1280)), H = Number(arg('h', 720)), FPS = 30;
const RATE = arg('rate', '-6%');
const HOST = arg('host', 'tutor');
const HUMAN_HOST = HOST === 'tutor' || HOST === 'nora';
const LINES = HUMAN_HOST ? [
  { text: "Hi friend! I'm so happy to see you!", gesture: 'wave', emotion: 'happy' },
  { text: 'Look! Up, up, up!', gesture: 'point', emotion: 'surprised' },
  { text: 'Your turn. Can you say up?', gesture: 'lean', emotion: 'happy', pause: 1.6 },
  { text: 'Yes! You did it! I love that!', gesture: 'heart', emotion: 'laugh' },
  { text: "Let's clap!", gesture: 'clap', emotion: 'happy' },
  { text: 'Yay!', gesture: 'cheer', emotion: 'laugh' },
] : [
  { text: 'Hi friend! Wave hello!', gesture: 'wave', emotion: 'happy' },
  { text: 'Look up there!', gesture: 'point', emotion: 'surprised' },
  { text: "Let's clap! Clap, clap!", gesture: 'clap', emotion: 'happy' },
  { text: 'Yay!', gesture: 'jump', emotion: 'happy' },
];
const VOICE = arg('voice', HUMAN_HOST ? 'en-US-JennyNeural' : 'en-US-AnaNeural');
const log = (o) => console.log(JSON.stringify(o));
const run = (cmd, a) => { const r = spawnSync(cmd, a, { encoding: 'utf8' }); if (r.status !== 0) throw new Error(`${cmd} failed: ${(r.stderr || '').slice(-400)}`); return r.stdout; };
const dur = (f) => Number(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).trim());

function voice(work) {
  const lines = [];
  let t = 0.5;
  LINES.forEach((L, i) => {
    const f = path.join(work, `line${i}.mp3`);
    if (!fs.existsSync(f)) run('edge-tts', ['--voice', VOICE, `--rate=${RATE}`, '--text', L.text, '--write-media', f]);
    const d = dur(f), lead = 0.12, speak = Math.max(0.3, d - 0.3);
    // Word times: spread over the spoken part by letter count (good enough for caption highlight).
    const words = L.text.split(/\s+/), lens = words.map((w) => w.replace(/[^\w']/g, '').length + 1), tot = lens.reduce((a, b) => a + b, 0);
    let wt = t + lead; const W2 = words.map((w, k) => { const w0 = wt; wt += speak * lens[k] / tot; return { text: w, t0: +w0.toFixed(3), t1: +wt.toFixed(3) }; });
    lines.push({ ...L, file: f, t0: +t.toFixed(3), t1: +(t + d).toFixed(3), words: W2 });
    t += d + 0.3 + (L.pause || 0);
  });
  const total = t + 0.6, wav = path.join(work, 'voice.wav');
  const inputs = lines.flatMap((l) => ['-i', l.file]);
  const fc = lines.map((l, i) => `[${i}:a]aresample=48000,adelay=${Math.round(l.t0 * 1000)}:all=1[a${i}]`).join(';') + ';' + lines.map((_, i) => `[a${i}]`).join('') + `amix=inputs=${lines.length}:normalize=0,apad,atrim=0:${total.toFixed(3)}[o]`;
  run('ffmpeg', ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', fc, '-map', '[o]', '-ac', '1', '-ar', '48000', wav]);
  return { lines, total, wav };
}

// Mouth envelope: RMS per video frame, normalised to the loud end, fast open / slower close, small values gated to 0.
function envelope(wav, total) {
  const raw = spawnSync('ffmpeg', ['-loglevel', 'error', '-i', wav, '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'], { maxBuffer: 1 << 28 }).stdout;
  const s = new Float32Array(raw.buffer, raw.byteOffset, Math.floor(raw.length / 4)), per = 16000 / FPS, n = Math.ceil(total * FPS), rms = [];
  for (let i = 0; i < n; i++) { let a = 0, c = 0; for (let k = Math.floor(i * per); k < Math.min(s.length, (i + 1) * per); k++) { a += s[k] * s[k]; c++; } rms.push(c ? Math.sqrt(a / c) : 0); }
  const sorted = [...rms].filter((x) => x > 1e-4).sort((a, b) => a - b), ref = sorted[Math.floor(sorted.length * 0.95)] || 1;
  const out = []; let v = 0;
  for (const r of rms) { let x = Math.min(1, r / ref); x = x < 0.12 ? 0 : (x - 0.12) / 0.88; v = x > v ? v + (x - v) * 0.75 : v + (x - v) * 0.35; out.push(+v.toFixed(3)); }
  return out;
}

function threeRoot() { return path.join(ROOT, 'starmap-engine', 'node_modules', 'three'); }
function server(planJson) {
  const three = threeRoot(), TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.ttf': 'font/ttf', '.json': 'application/json' };
  const safe = (base, rel) => { const f = path.resolve(base, decodeURIComponent(rel)); return f.startsWith(path.resolve(base) + path.sep) ? f : null; };
  const srv = http.createServer((req, res) => {
    const p = new URL(req.url, 'http://x').pathname; let file = null;
    if (p === '/plan.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(planJson); }
    if (p === '/' || p === '/index.html') file = path.join(HERE, 'web', 'spike.html');
    else if (p.startsWith('/web/')) file = safe(path.join(HERE, 'web'), p.slice(5));
    else if (p.startsWith('/fonts/')) file = safe(path.join(ROOT, 'roblox-cinema-engine', 'assets', 'fonts'), p.slice(7));
    else if (p.startsWith('/three/addons/')) file = safe(path.join(three, 'examples', 'jsm'), p.slice(14));
    else if (p.startsWith('/three/')) file = safe(path.join(three, 'build'), p.slice(7));
    if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((r) => srv.listen(0, '127.0.0.1', () => r(srv)));
}

async function main() {
  const work = OUT + '.' + HOST + '.work'; fs.mkdirSync(work, { recursive: true });
  let { lines, total, wav } = voice(work);
  const maxDur = Number(arg('duration', 0));
  if (maxDur > 0 && total > maxDur) {
    total = maxDur;
    lines = lines.filter((l) => l.t0 < maxDur);
    const trimmed = wav + '.trim.wav';
    run('ffmpeg', ['-y', '-loglevel', 'error', '-i', wav, '-t', String(maxDur), '-c', 'copy', trimmed]);
    fs.renameSync(trimmed, wav);
  }
  const env = envelope(wav, total);
  const gestures = lines.map((l) => ({ t: Math.max(0, l.t0 - 0.15), gesture: l.gesture, emotion: l.emotion }));
  const plan = {
    width: W, height: H, fps: FPS, duration: total, envFps: FPS, envelope: env, lines, gestures, palette: 'sunny',
    host: HOST, look: arg('look', HOST === 'nora' ? 'nora' : 'maya'),
    world: arg('world', HUMAN_HOST ? 'playroom' : 'park'),
  };
  fs.writeFileSync(OUT + '.plan.json', JSON.stringify({ ...plan, envelope: `${env.length} values` }, null, 1));
  log({ event: 'plan', duration: +total.toFixed(2), lines: lines.length });
  const srv = await server(JSON.stringify(plan)), origin = `http://127.0.0.1:${srv.address().port}`;
  const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
  const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--hide-scrollbars'] });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    page.on('pageerror', (e) => errors.push(String(e))); page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(`${origin}/index.html?w=${W}&h=${H}`);
    await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 60000 });
    const err = await page.evaluate(() => window.__error || null); if (err) throw new Error(err);
    const shot = () => page.screenshot({ type: 'jpeg', quality: 94 });
    const stills = arg('stills');
    if (stills) {
      for (const t of stills.split(',').map(Number)) { await page.evaluate((x) => window.renderFrame(x), t); fs.writeFileSync(`${OUT}.t${t}.jpg`, await shot()); }
      log({ event: 'done', stills, errors }); return;
    }
    const silent = OUT + '.video.mp4';
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
      '-vf', 'format=yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', String(FPS), silent], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ferr = ''; ff.stderr.on('data', (d) => { ferr += d; }); const closed = new Promise((r) => ff.on('close', r));
    const n = Math.ceil(total * FPS), t0 = Date.now();
    for (let i = 0; i < n; i++) {
      await page.evaluate((t) => window.renderFrame(t), i / FPS);
      if (!ff.stdin.write(await shot())) await new Promise((r) => ff.stdin.once('drain', r));
      if (i % 60 === 0) log({ event: 'progress', frame: i, total: n, ms_per_frame: Math.round((Date.now() - t0) / (i + 1)) });
    }
    ff.stdin.end(); if ((await closed) !== 0) throw new Error(`ffmpeg: ${ferr.slice(-300)}`);
    run('ffmpeg', ['-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', 'loudnorm=I=-14:TP=-1.5:LRA=7', '-shortest', '-movflags', '+faststart', OUT]);
    fs.rmSync(silent, { force: true });
    log({ event: 'done', output: OUT, frames: n, wall_s: (Date.now() - t0) / 1000, errors });
  } finally { await browser.close(); srv.close(); }
}
main().catch((e) => { log({ event: 'error', message: String((e && e.stack) || e) }); process.exit(1); });
