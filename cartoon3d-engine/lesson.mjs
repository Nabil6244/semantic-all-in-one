#!/usr/bin/env node
// Kids Learn: lesson CSV -> Edge voice with word timings -> plan -> GPU Chromium frames -> mp4 (-14 LUFS).
// Usage: node cartoon3d-engine/lesson.mjs --csv lesson.csv [--out out.mp4] [--w 1280 --h 720] [--world playroom|park]
//        [--host tutor|toon|host3d] [--glb host.glb] [--look maya|sam] [--voice en-US-JennyNeural] [--rate -6%] [--stills 2,5] [--plan-only]
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { parseCsv, normalizeRows, buildLesson, TUTOR_X } from './lib/lesson.mjs';
import { visemeTrack } from './lib/visemes.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.dirname(HERE);
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const flag = (k) => process.argv.includes(`--${k}`);
const FPS = 30;
const log = (o) => console.log(JSON.stringify(o));
const run = (cmd, a) => { const r = spawnSync(cmd, a, { encoding: 'utf8' }); if (r.status !== 0) throw new Error(`${cmd} failed: ${(r.stderr || '').slice(-500)}`); return r.stdout; };
const dur = (f) => Number(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).trim());

function voices(beats, work, voice, rate) {
  const lines = beats.map((b) => ({ text: b.text, out: path.join(work, `${crypto.createHash('sha1').update(`${voice}|${rate}|${b.text}`).digest('hex').slice(0, 16)}.mp3`) }));
  const job = path.join(work, 'tts_job.json'); fs.writeFileSync(job, JSON.stringify({ voice, rate, lines }));
  run('python3', [path.join(HERE, 'tools', 'tts_words.py'), job]);
  return lines.map((l) => ({ file: l.out, dur: dur(l.out), words: JSON.parse(fs.readFileSync(l.out + '.words.json', 'utf8')) }));
}

function mixVoice(lesson, vo, work) {
  const wav = path.join(work, 'voice.wav'), inputs = vo.flatMap((v) => ['-i', v.file]);
  const fc = vo.map((_, i) => `[${i}:a]aresample=48000,adelay=${Math.round(lesson.lines[i].t0 * 1000)}:all=1[a${i}]`).join(';') + ';' + vo.map((_, i) => `[a${i}]`).join('') + `amix=inputs=${vo.length}:normalize=0,apad,atrim=0:${lesson.duration.toFixed(3)}[o]`;
  run('ffmpeg', ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', fc, '-map', '[o]', '-ac', '1', '-ar', '48000', wav]);
  return wav;
}

// Mouth opening per video frame from voice loudness: fast open, slower close, quiet gated to 0.
function envelope(wav, total) {
  const raw = spawnSync('ffmpeg', ['-loglevel', 'error', '-i', wav, '-f', 'f32le', '-ac', '1', '-ar', '16000', '-'], { maxBuffer: 1 << 29 }).stdout;
  const s = new Float32Array(raw.buffer, raw.byteOffset, Math.floor(raw.length / 4)), per = 16000 / FPS, n = Math.ceil(total * FPS), rms = [];
  for (let i = 0; i < n; i++) { let a = 0, c = 0; for (let k = Math.floor(i * per); k < Math.min(s.length, (i + 1) * per); k++) { a += s[k] * s[k]; c++; } rms.push(c ? Math.sqrt(a / c) : 0); }
  const sorted = rms.filter((x) => x > 1e-4).sort((a, b) => a - b), ref = sorted[Math.floor(sorted.length * 0.95)] || 1, out = []; let v = 0;
  for (const r of rms) { let x = Math.min(1, r / ref); x = x < 0.12 ? 0 : (x - 0.12) / 0.88; v = x > v ? v + (x - v) * 0.75 : v + (x - v) * 0.35; out.push(+v.toFixed(3)); }
  return out;
}


// Loudness: measure the voice track, lift it straight to -14 LUFS, and let a soft limiter catch the peaks at -1.5 dBTP.
// (loudnorm's linear mode backs off the gain when peaks would clip, which left speech near -15.5 LUFS.)
function loudnorm(wav) {
  const chain = (g) => `volume=${g.toFixed(2)}dB,alimiter=limit=0.84:attack=3:release=60:level=false`;
  const measure = (af) => { const r = spawnSync('ffmpeg', ['-hide_banner', '-i', wav, '-af', `${af}${af ? ',' : ''}ebur128`, '-f', 'null', '-'], { encoding: 'utf8' }); const m = (r.stderr || '').match(/I:\s+(-?[\d.]+) LUFS/g); return m ? Number(m[m.length - 1].match(/-?[\d.]+/)[0]) : null; };
  const i0 = measure(''); if (i0 === null || !Number.isFinite(i0)) return 'loudnorm=I=-14:TP=-1.5:LRA=11';
  // The limiter eats some loudness; measure after it and top the gain up (two quick audio-only passes).
  let g = -14 - i0;
  for (let k = 0; k < 2; k++) { const i = measure(chain(g)); if (i === null) break; if (Math.abs(-14 - i) < 0.2) break; g += -14 - i; }
  return chain(Math.max(-20, Math.min(24, g)));
}

// The approved host from authoring (accepted at Gate 5). Override with --glb.
const HOST_GLB = path.join(HERE, 'authoring', 'build', 'revisions', 'f1_gate5', 'f1', 'host.glb');

function server(planJson, glb) {
  const three = path.join(ROOT, 'starmap-engine', 'node_modules', 'three'), TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.ttf': 'font/ttf', '.json': 'application/json' };
  const safe = (base, rel) => { const f = path.resolve(base, decodeURIComponent(rel)); return f.startsWith(path.resolve(base) + path.sep) ? f : null; };
  const srv = http.createServer((req, res) => {
    const p = new URL(req.url, 'http://x').pathname; let file = null;
    if (p === '/host.glb' && glb) { res.writeHead(200, { 'Content-Type': 'model/gltf-binary' }); return fs.createReadStream(glb).pipe(res); }
    if (p === '/plan.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(planJson); }
    if (p === '/' || p === '/index.html') file = path.join(HERE, 'web', 'lesson.html');
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
  const csv = arg('csv'); if (!csv) throw new Error('--csv is required');
  const OUT = path.resolve(arg('out', path.join(HERE, 'out', path.basename(csv, '.csv') + '.mp4'))), W = Number(arg('w', 1280)), H = Number(arg('h', 720));
  const work = path.join(path.dirname(OUT), '.voice_cache'); fs.mkdirSync(work, { recursive: true });
  const { beats, problems } = normalizeRows(parseCsv(fs.readFileSync(csv, 'utf8')));
  for (const p of problems) log({ event: 'warning', message: p });
  if (!beats.length) throw new Error('the lesson CSV has no usable rows');
  const vo = voices(beats, work, arg('voice', 'en-US-JennyNeural'), arg('rate', '-6%'));
  const lesson = buildLesson(beats, vo);
  const wav = mixVoice(lesson, vo, work), env = envelope(wav, lesson.duration);
  const plan = { width: W, height: H, fps: FPS, envFps: FPS, envelope: env, ...lesson, tutorX: TUTOR_X, host: arg('host', 'tutor'), look: arg('look', 'maya'), world: arg('world', 'playroom') };
  const glb = plan.host === 'host3d' ? path.resolve(arg('glb', HOST_GLB)) : null;
  if (glb && !fs.existsSync(glb)) throw new Error(`host GLB not found: ${glb}`);
  if (glb) plan.visemeTrack = visemeTrack(lesson.lines.flatMap((l) => l.words), env, FPS, lesson.duration, FPS);
  fs.writeFileSync(OUT + '.plan.json', JSON.stringify({ ...plan, envelope: `${env.length} values`, visemeTrack: plan.visemeTrack ? `${plan.visemeTrack.frames.length} frames x ${plan.visemeTrack.names.length}` : undefined }, null, 1));
  log({ event: 'plan', duration: lesson.duration, lines: lesson.lines.length, props: lesson.props.length, cards: lesson.cards.length });
  if (flag('plan-only')) return;
  const srv = await server(JSON.stringify(plan), glb), origin = `http://127.0.0.1:${srv.address().port}`;
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
    if (stills) { for (const t of stills.split(',').map(Number)) { await page.evaluate((x) => window.renderFrame(x), t); fs.writeFileSync(`${OUT}.t${t}.jpg`, await shot()); } log({ event: 'done', stills, errors }); return; }
    const silent = OUT + '.video.mp4';
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
      '-vf', 'format=yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', String(FPS), silent], { stdio: ['pipe', 'ignore', 'pipe'] });
    let ferr = ''; ff.stderr.on('data', (d) => { ferr += d; }); const closed = new Promise((r) => ff.on('close', r));
    const n = Math.ceil(lesson.duration * FPS), t0 = Date.now();
    for (let i = 0; i < n; i++) {
      await page.evaluate((t) => window.renderFrame(t), i / FPS);
      if (!ff.stdin.write(await shot())) await new Promise((r) => ff.stdin.once('drain', r));
      if (i % 150 === 0) log({ event: 'progress', frame: i, total: n, ms_per_frame: Math.round((Date.now() - t0) / (i + 1)) });
    }
    ff.stdin.end(); if ((await closed) !== 0) throw new Error(`ffmpeg: ${ferr.slice(-300)}`);
    run('ffmpeg', ['-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', `${loudnorm(wav)},aresample=48000`, '-shortest', '-movflags', '+faststart', OUT]);
    fs.rmSync(silent, { force: true });
    log({ event: 'done', output: OUT, frames: n, wall_s: (Date.now() - t0) / 1000, errors });
  } finally { await browser.close(); srv.close(); }
}
main().catch((e) => { log({ event: 'error', message: String((e && e.stack) || e) }); process.exit(1); });
