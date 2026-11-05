#!/usr/bin/env node
// Kids Learn: lesson CSV -> Edge voice with word timings -> plan -> GPU Chromium frames -> mp4 (-14 LUFS).
// Usage: node cartoon3d-engine/lesson.mjs --csv lesson.csv [--out out.mp4] [--w 1280 --h 720] [--world playroom|park]
//        [--host tutor|toon|host3d] [--glb host.glb] [--work cache_dir] [--plan-file plan.json] [--voiceover your_recording.mp3] [--music auto|playroom|calm|sunny|off] [--sfx on|off] [--look maya|sam] [--voice en-US-JennyNeural] [--rate -6%] [--stills 2,5] [--plan-only]
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import { spawn, spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { parseCsv, normalizeRows, buildLesson, TUTOR_X } from './lib/lesson.mjs';
import { visemeTrack } from './lib/visemes.mjs';
import { alignLines, fillMissing } from './lib/align.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.dirname(HERE);
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const flag = (k) => process.argv.includes(`--${k}`);
const FPS = 30;
// The app passes its own Python (LESSON_PYTHON); on the command line python3 (python on Windows) is used.
const PY = process.env.LESSON_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const log = (o) => console.log(JSON.stringify(o));
const run = (cmd, a) => { const r = spawnSync(cmd, a, { encoding: 'utf8' }); if (r.status !== 0) throw new Error(`${cmd} failed: ${(r.stderr || '').slice(-500)}`); return r.stdout; };
const dur = (f) => Number(run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).trim());

function voices(beats, work, voice, rate, bpm) {
  const lines = beats.map((b) => ({ text: b.text, out: path.join(work, `${crypto.createHash('sha1').update(`${voice}|${rate}|${b.text}`).digest('hex').slice(0, 16)}.mp3`) }));
  const job = path.join(work, 'tts_job.json'); fs.writeFileSync(job, JSON.stringify({ voice, rate, lines }));
  run(PY, [path.join(HERE, 'tools', 'tts_words.py'), job]);
  return lines.map((l, i) => {
    const v = { file: l.out, dur: dur(l.out), words: JSON.parse(fs.readFileSync(l.out + '.words.json', 'utf8')) };
    return beats[i].type === 'chant' ? chantLine(v, beats[i].text, bpm, work) : v;
  });
}

// Chant rows: the kids_audio engine puts every spoken word on the beat (cached per line and tempo).
function chantLine(v, text, bpm, work) {
  const out = v.file.replace(/\.mp3$/, `.chant${bpm}.wav`), meta = out + '.json';
  if (!fs.existsSync(meta)) {
    const job = out + '.job.json'; fs.writeFileSync(job, JSON.stringify({ voice: v.file, words: v.words, text, bpm, out }));
    const r = spawnSync(PY, ['-m', 'kids_audio.chant', job], { encoding: 'utf8', cwd: ROOT });
    if (r.status !== 0) throw new Error(`kids_audio chant failed: ${(r.stderr || '').slice(-500)}`);
    fs.writeFileSync(meta, r.stdout.trim().split('\n').pop());
  }
  const c = JSON.parse(fs.readFileSync(meta, 'utf8'));
  return { file: c.file, dur: c.dur, words: c.words };
}

// The music bed this lesson uses (or null) and its tempo; chants follow the tempo even with music off.
function musicChoice(world) {
  const bedArg = arg('music', 'auto'), bed = bedArg === 'off' ? null : bedArg === 'auto' ? (world === 'park' ? 'sunny' : 'playroom') : bedArg;
  const r = spawnSync(PY, ['-c', 'import json; from kids_audio import library as L; print(json.dumps({k: v["bpm"] for k, v in L.build()["beds"].items()}))'], { encoding: 'utf8', cwd: ROOT });
  if (r.status !== 0) throw new Error(`kids_audio library failed: ${(r.stderr || '').slice(-500)}`);
  const bpms = JSON.parse(r.stdout.trim().split('\n').pop());
  if (bed && !bpms[bed]) throw new Error(`unknown --music "${bed}" (use ${Object.keys(bpms).join(', ')}, auto or off)`);
  return { bed, bpm: bpms[bed || 'playroom'] };
}

// A recorded voice-over: word times (local faster-whisper, cached per file), each CSV line matched to where it was said,
// and the recording itself as the voice track. The free Edge voice is not used.
function voiceoverLesson(file, beats, work) {
  if (!fs.existsSync(file)) throw new Error(`voice-over not found: ${file}`);
  const wj = path.join(work, 'voiceover_words.json');
  const r = spawnSync(PY, [path.join(HERE, 'tools', 'voice_words.py'), path.resolve(file), wj], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error(`timing the voice-over failed: ${(r.stderr || '').slice(-400)}`);
  const spoken = JSON.parse(fs.readFileSync(wj, 'utf8')), duration = dur(file);
  const found = alignLines(beats.map((b) => b.text), spoken.words), timed = fillMissing(found, duration, beats.map((b) => b.text));
  found.forEach((x, i) => { if (!x) log({ event: 'warning', message: `line ${i + 1} ("${beats[i].text.slice(0, 40)}") was not found in the voice-over; it is placed between its neighbours` }); });
  log({ event: 'voiceover', words: spoken.words.length, lines: beats.length, lines_found: found.filter(Boolean).length, seconds: +duration.toFixed(2) });
  const lesson = buildLesson(beats, [], { timed, voiceDuration: duration });
  const wav = path.join(work, 'voice.wav');
  run('ffmpeg', ['-y', '-loglevel', 'error', '-i', path.resolve(file), '-af', `aresample=48000,apad,atrim=0:${lesson.duration.toFixed(3)}`, '-ac', '1', '-ar', '48000', wav]);
  return { lesson, wav };
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
const HOST_GLB = path.join(HERE, 'assets', 'host', 'host.glb');

// Music and sound effects come from the reusable kids_audio engine (repo root). Lesson events -> named effects;
// effects closer than 0.12 s to the previous one are dropped so nothing piles up.
function audioEvents(plan) {
  const ev = [], add = (t, name, gain_db = 0) => ev.push({ t: +Math.max(0, t).toFixed(3), name, gain_db });
  for (const p of plan.props) add(p.t0 + 0.02, p.n ? `ding_${Math.min(10, p.n)}` : 'pop', p.n ? -2 : 0);
  for (const c of plan.cards) add(c.t0, 'sparkle', -5);
  for (const b of plan.badges) add(b.t0, 'chime', -3);
  for (const l of plan.lines) if (l.type === 'cheer') add(l.t0 - 0.45, 'success', -2);      // in the gap before she cheers, not over her first word
  const NUM = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10 };
  for (const l of plan.lines) if (l.type === 'chant') for (const w of l.words) { const n = NUM[w.text.toLowerCase().replace(/[^a-z]/g, '')]; if (n) add(w.t0, `ding_${n}`, -4); }
  ev.sort((a, b) => a.t - b.t);
  return ev.filter((e, i) => !ev.slice(0, i).some((x) => Math.abs(x.t - e.t) < 0.12));
}

function audioMix(plan, wav, work) {
  const sfxOn = arg('sfx', 'on') !== 'off', bed = plan.music;
  if (!bed && !sfxOn) return null;                                    // voice only: the old path, unchanged
  const voiceP = path.join(work, 'voice_processed.wav'), out = path.join(work, 'mix.wav'), job = path.join(work, 'mix_job.json');
  run('ffmpeg', ['-y', '-loglevel', 'error', '-i', wav, '-af', `${loudnorm(wav)},aresample=48000`, '-ac', '2', voiceP]);   // same voice processing as before
  fs.writeFileSync(job, JSON.stringify({ voice: voiceP, out, duration: plan.duration, voice_lufs: -14, music: bed ? { bed } : null, sfx: sfxOn ? audioEvents(plan) : [], duck_regions: plan.lines.filter((l) => l.type === 'chant').map((l) => ({ t0: l.t0 - 0.2, t1: l.t1, duck_db: -4 })) }));
  const r = spawnSync(PY, ['-m', 'kids_audio.mixer', job], { encoding: 'utf8', cwd: ROOT });
  if (r.status !== 0) throw new Error(`kids_audio mixer failed: ${(r.stderr || '').slice(-500)}`);
  const rep = JSON.parse(r.stdout.trim().split('\n').pop());
  log({ event: 'audio', ...rep });
  return out;
}

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
  const work = path.resolve(arg('work', path.join(path.dirname(OUT), '.voice_cache'))); fs.mkdirSync(work, { recursive: true });
  const PLAN = path.resolve(arg('plan-file', OUT + '.plan.json'));
  const { beats, problems } = normalizeRows(parseCsv(fs.readFileSync(csv, 'utf8')));
  for (const p of problems) log({ event: 'warning', message: p });
  if (!beats.length) throw new Error('the lesson CSV has no usable rows');
  const music = musicChoice(arg('world', 'playroom'));
  let lesson, wav;
  if (arg('voiceover')) ({ lesson, wav } = voiceoverLesson(arg('voiceover'), beats, work));
  else {
    const vo = voices(beats, work, arg('voice', 'en-US-JennyNeural'), arg('rate', '-6%'), music.bpm);
    lesson = buildLesson(beats, vo, { beat: 60 / music.bpm }); wav = mixVoice(lesson, vo, work);
  }
  const env = envelope(wav, lesson.duration);
  const plan = { width: W, height: H, fps: FPS, envFps: FPS, envelope: env, ...lesson, tutorX: TUTOR_X, host: arg('host', 'tutor'), look: arg('look', 'maya'), world: arg('world', 'playroom'), music: music.bed, bpm: music.bpm };
  const glb = plan.host === 'host3d' ? path.resolve(arg('glb', HOST_GLB)) : null;
  if (glb && !fs.existsSync(glb)) throw new Error(`host GLB not found: ${glb}`);
  if (glb) plan.visemeTrack = visemeTrack(lesson.lines.flatMap((l) => l.words), env, FPS, lesson.duration, FPS);
  fs.writeFileSync(PLAN, JSON.stringify({ ...plan, envelope: `${env.length} values`, visemeTrack: plan.visemeTrack ? `${plan.visemeTrack.frames.length} frames x ${plan.visemeTrack.names.length}` : undefined }, null, 1));
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
      if (i % 30 === 0) log({ event: 'progress', frame: i, total: n, ms_per_frame: Math.round((Date.now() - t0) / (i + 1)) });
    }
    ff.stdin.end(); if ((await closed) !== 0) throw new Error(`ffmpeg: ${ferr.slice(-300)}`);
    const mixed = audioMix(plan, wav, work);
    if (mixed) run('ffmpeg', ['-y', '-loglevel', 'error', '-i', silent, '-i', mixed, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', OUT]);
    else run('ffmpeg', ['-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', `${loudnorm(wav)},aresample=48000`, '-shortest', '-movflags', '+faststart', OUT]);
    fs.rmSync(silent, { force: true });
    log({ event: 'done', output: OUT, frames: n, wall_s: (Date.now() - t0) / 1000, errors });
  } finally { await browser.close(); srv.close(); }
}
main().catch((e) => { log({ event: 'error', message: String((e && e.stack) || e) }); process.exit(1); });
