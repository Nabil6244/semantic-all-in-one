// Gate 5 lip-sync test: an Edge voice line + word timings -> Meta visemes, blinks, light head motion, rendered frame by frame in the app's Three.js.
// Run from the repo root: node cartoon3d-engine/authoring/host/stage5_clip.mjs f1   (needs build/stage5/clip/line.mp3 and line.mp3.words.json)
import fs from 'node:fs'; import http from 'node:http'; import path from 'node:path'; import { execFileSync } from 'node:child_process'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, '..', '..', '..'), TAG = process.argv[2] || 'f1';
const B = path.join(HERE, '..', 'build', 'stage5'), GLB = path.join(B, TAG, 'host.glb'), CLIP = path.join(B, 'clip'), FR = path.join(CLIP, 'frames_' + TAG);
fs.rmSync(FR, { recursive: true, force: true }); fs.mkdirSync(FR, { recursive: true });
const three = path.join(ROOT, 'starmap-engine', 'node_modules', 'three'), W = 960, H = 540, FPS = 30;

// ---- words -> visemes (spelling rules; Edge gives word times, not phonemes)
const RULES = [[/^th/, 'TH'], [/^(sh|ch|tch)/, 'CH'], [/^ck/, 'kk'], [/^ng/, 'nn'], [/^(ee|ea|ie)/, 'E'], [/^(oo|ue|ew)/, 'U'], [/^ou$/, 'U'], [/^(ou|ow)/, 'aa'], [/^y(?=[aeiou])/, null], [/^c(?=[eiy])/, 'SS'], [/^c/, 'kk'], [/^(ai|ay|ei)/, 'E'], [/^[a]/, 'aa'], [/^e/, 'E'], [/^[iy]/, 'I'],
  [/^o/, 'O'], [/^u/, 'U'], [/^[bpm]/, 'PP'], [/^[fv]/, 'FF'], [/^[szc]/, 'SS'], [/^x/, 'kk'], [/^[tdl]/, 'DD'], [/^n/, 'nn'], [/^[kgq]/, 'kk'], [/^r/, 'RR'], [/^w/, 'U'], [/^j/, 'CH'], [/^[h']/, null]];
const VOW = new Set(['aa', 'E', 'I', 'O', 'U']);
// common preschool words that spelling gets wrong (Meta viseme names, without the prefix)
const DICT = { the: 'DD aa', a: 'aa', to: 'DD U', do: 'DD U', you: 'U', your: 'U RR', one: 'U aa nn', two: 'DD U', said: 'SS E DD', says: 'SS E SS', what: 'U aa DD', where: 'U E RR',
  are: 'aa RR', is: 'I SS', was: 'U aa SS', friend: 'FF RR E nn DD', friends: 'FF RR E nn DD SS', hello: 'E DD O', hi: 'aa I', great: 'kk RR E DD', good: 'kk U DD', look: 'DD U kk',
  "let's": 'DD E DD SS', some: 'SS aa PP', something: 'SS aa PP TH I nn', come: 'kk aa PP', love: 'DD aa FF', all: 'O DD', ball: 'PP O DD', now: 'nn aa U', know: 'nn O', eye: 'aa I', eyes: 'aa I SS',
  find: 'FF aa I nn DD', night: 'nn aa I DD', light: 'DD aa I DD', right: 'RR aa I DD', blue: 'PP DD U', who: 'U', why: 'U aa I', my: 'PP aa I', by: 'PP aa I', bye: 'PP aa I', yes: 'I E SS', yellow: 'I E DD O', red: 'RR E DD', green: 'kk RR I nn' };
function visemes(word) {
  const key = word.toLowerCase().replace(/[^a-z']/g, ''); if (DICT[key]) return DICT[key].split(' ');
  let w = key; if (w.length > 2 && w.endsWith('e') && !/[aeiou]e$/.test(w)) w = w.slice(0, -1);
  const out = []; while (w.length) { const r = RULES.find(([re]) => re.test(w)); if (!r) { w = w.slice(1); continue; } const m = w.match(r[0])[0]; w = w.slice(m.length);
    if (r[1] && !(out.length && (out.at(-1) === r[1] || (VOW.has(r[1]) && VOW.has(out.at(-1)))))) out.push(r[1]); }
  return out;
}
const words = JSON.parse(fs.readFileSync(path.join(CLIP, 'line.mp3.words.json'), 'utf8'));
const items = []; for (const wd of words) { const v = visemes(wd.text); const wt = v.map((x) => (VOW.has(x) ? 2 : 1)); const tot = wt.reduce((a, b) => a + b, 0) || 1; let t = wd.t0;
  v.forEach((x, i) => { const d = (wd.t1 - wd.t0) * wt[i] / tot; items.push({ v: x, c: t + d / 2, hw: d * 0.6 + 0.04, peak: x === 'PP' ? 1 : VOW.has(x) ? 1.15 : 0.85 }); t += d; }); }
const dur = Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path.join(CLIP, 'line.mp3')]).toString()) + 0.6;
const speaking = (t) => words.some((w) => t >= w.t0 - 0.05 && t <= w.t1 + 0.05);
const BLINKS = [1.45, 4.85, 6.6, 9.0], tri = (x, c, h) => Math.max(0, 1 - Math.abs(x - c) / h);
// voice loudness at 100 Hz, normalised to the 95th percentile
const pcm = execFileSync('ffmpeg', ['-v', 'error', '-i', path.join(CLIP, 'line.mp3'), '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], { maxBuffer: 1 << 26 });
const S = new Float32Array(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.length)), ER = 100, env = [];
for (let i = 0; i * 160 < S.length; i++) { let a = 0; for (let j = i * 160; j < Math.min(S.length, i * 160 + 160); j++) a += S[j] * S[j]; env.push(Math.sqrt(a / 160)); }
const p95 = [...env].sort((a, b) => a - b)[Math.floor(env.length * 0.95)] || 1;
const loud = (t) => { const i = t * ER, a = Math.floor(i), f = i - a; return Math.min(1, ((env[a] || 0) * (1 - f) + (env[a + 1] || 0) * f) / p95); };
const sstep = (e0, e1, x) => { const u = Math.min(1, Math.max(0, (x - e0) / (e1 - e0))); return u * u * (3 - 2 * u); };
const bump = (x, c, h) => (Math.abs(x - c) < h ? 0.5 * (1 + Math.cos(Math.PI * (x - c) / h)) : 0);
const LEAD = 0.04, HZ = 120;                       // the mouth shapes a sound slightly before it is heard
function rawMouth(t, tuned) {
  const k = {}; const tt = tuned ? t + LEAD : t;
  for (const it of items) { const a = it.peak * (tuned ? bump(tt, it.c, it.hw * 1.15) : tri(tt, it.c, it.hw)); const n = 'viseme_' + it.v; if (a > (k[n] || 0)) k[n] = a; }
  if (tuned) { const L = loud(tt), g = sstep(0.04, 0.22, L) * (0.6 + 0.55 * L);       // open with the real voice, shut in the gaps
    for (const n in k) if (n !== 'viseme_PP') k[n] *= g; }
  const sum = Object.values(k).reduce((a, b) => a + b, 0); if (sum > 1.3) for (const n in k) k[n] *= 1.3 / sum;
  return k;
}
const VNAMES = [...new Set(items.map((i) => 'viseme_' + i.v))], NS = Math.ceil(dur * HZ), TRACK = {};
for (const n of VNAMES) TRACK[n] = new Float32Array(NS);
for (let i = 0, y = Object.fromEntries(VNAMES.map((n) => [n, 0])); i < NS; i++) { const k = rawMouth(i / HZ, true);
  for (const n of VNAMES) { const x = k[n] || 0, a = 1 - Math.exp(-1 / (HZ * (x > y[n] ? 0.025 : 0.06))); y[n] += (x - y[n]) * a; TRACK[n][i] = y[n]; } }
const mouthAt = (t) => { const i = Math.min(NS - 1, Math.round(t * HZ)); return Object.fromEntries(VNAMES.map((n) => [n, TRACK[n][i]])); };
// how well the mouth follows the voice: openness vs loudness, and shut in silence
const OPEN = { aa: 1, O: 0.8, E: 0.55, I: 0.45, U: 0.35, TH: 0.5, DD: 0.4, kk: 0.45, nn: 0.35, RR: 0.3, CH: 0.35, SS: 0.3, FF: 0.2, PP: 0 };
const openness = (k) => Object.entries(k).reduce((a, [n, x]) => a + x * (OPEN[n.slice(7)] || 0), 0);
function score(get) { const A = [], Bv = []; let sil = 0, shut = 0;
  for (let t = 0; t < dur - 0.6; t += 1 / FPS) { const o = openness(get(t)), L = loud(t); A.push(o); Bv.push(L); if (L < 0.03 && !speaking(t)) { sil++; if (o < 0.08) shut++; } }
  const m = (v) => v.reduce((a, b) => a + b, 0) / v.length, ma = m(A), mb = m(Bv); let c = 0, va = 0, vb = 0;
  A.forEach((a, i) => { c += (a - ma) * (Bv[i] - mb); va += (a - ma) ** 2; vb += (Bv[i] - mb) ** 2; });
  return { follow_voice: +(c / Math.sqrt(va * vb)).toFixed(3), shut_in_silence: +(shut / Math.max(1, sil)).toFixed(3) }; }
const SCORE = { before: score((t) => rawMouth(t, false)), after: score(mouthAt) };
function frameState(t) {
  const k = mouthAt(t);
  k.smile = speaking(t) ? 0.2 : 0.32;      // warm, lips together in pauses
  const q = words.find((w) => /ball/i.test(w.text) && w.t0 < 3.5); if (q) k.browInnerUp = 0.45 * tri(t, (q.t0 + q.t1) / 2, 0.9);       // the question lifts her brows
  const b2 = words.find((w) => w.text === 'Ball'); if (b2) k.surprise = 0.3 * tri(t, (b2.t0 + b2.t1) / 2, 0.5);
  const bw = Math.max(...BLINKS.map((c) => tri(t, c, 0.09))); Object.assign(k, { eyeBlinkLeft: bw, eyeBlinkRight: bw, eyeBlinkArcLeft: 4 * bw * (1 - bw), eyeBlinkArcRight: 4 * bw * (1 - bw) });
  const nod = words.reduce((a, w) => a + 1.6 * tri(t, w.t0 + 0.08, 0.18), 0);
  const pose = { neck03: [['z', 1.2 * Math.sin(t * 0.8)]], head: [['z', 2.2 * Math.sin(t * 0.55 + 0.6)], ['x', nod + 0.8 * Math.sin(t * 0.9)], ['y', 1.0 * Math.sin(t * 0.4)]] };
  return { k, pose };
}

const html = `<!doctype html><body style="margin:0;background:#e8e4e0"><script type="importmap">{"imports":{"three":"/three/three.module.min.js","three/addons/":"/three/addons/"}}</script><script type="module">
import * as THREE from 'three'; import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'; import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
try {
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setSize(${W}, ${H}); document.body.appendChild(r.domElement);
const s = new THREE.Scene(); s.background = new THREE.Color('#e8e4e0');
s.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture; s.environmentIntensity = 0.4;
r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
const add = (c, i, p, sh) => { const l = new THREE.DirectionalLight(c, i); l.position.set(p[0] * 2, 1.475 + p[1] * 2, 0.05 + p[2] * 2); l.target.position.set(0, 1.475, 0.05); s.add(l.target); s.add(l); if (sh) { l.castShadow = true; l.shadow.mapSize.set(2048, 2048); const c2 = l.shadow.camera; c2.left = -0.5; c2.right = 0.5; c2.top = 0.5; c2.bottom = -0.5; c2.near = 0.5; c2.far = 5; l.shadow.bias = -0.0006; l.shadow.normalBias = 0.004; l.shadow.radius = 6; } };
add(0xfff1e2, 1.2, [-0.85, 0.65, 1.15], true); add(0xeef4ff, 0.42, [1.1, 0.05, 1.1]); add(0xffffff, 0.55, [0.65, 0.75, -0.95]); add(0xffdcc2, 0.08, [0, -0.7, 0.8]);
const g = await new GLTFLoader().loadAsync('/host.glb'); s.add(g.scene);
const meshes = []; g.scene.traverse((o) => { if (o.isMesh) { meshes.push(o); o.frustumCulled = false; o.castShadow = o.name !== 'cand_mouth'; o.receiveShadow = true; } });
const cam = new THREE.PerspectiveCamera(2 * Math.atan(18 / 85) * 180 / Math.PI, ${W} / ${H}, 0.05, 20); cam.position.set(0, 1.46, 0.05 + 1.62); cam.lookAt(0, 1.46, 0.05);
const bones = {}; g.scene.traverse((o) => { if (o.isBone) bones[o.name] = { b: o, q: o.quaternion.clone() }; });
const AX = { x: [1, 0, 0], y: [0, 0, -1], z: [0, 1, 0] };
window.frame = (k, rot) => { for (const v of Object.values(bones)) v.b.quaternion.copy(v.q); g.scene.updateMatrixWorld(true);
  for (const [n, list] of Object.entries(rot)) { const v = bones[THREE.PropertyBinding.sanitizeNodeName(n)]; if (!v) continue;
    for (const [ax, deg] of list) { const pq = new THREE.Quaternion(); v.b.parent.getWorldQuaternion(pq); const R = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...AX[ax]), deg * Math.PI / 180);
      v.b.quaternion.copy(pq.clone().invert().multiply(R).multiply(pq).multiply(v.b.quaternion)); v.b.updateMatrixWorld(true); } }
  for (const m of meshes) { const d = m.morphTargetDictionary; if (!d) continue; m.morphTargetInfluences.fill(0); for (const [n, x] of Object.entries(k)) if (n in d) m.morphTargetInfluences[d[n]] = x; }
  g.scene.updateMatrixWorld(true); r.render(s, cam); };
window.__ready = true; } catch (e) { window.__error = String(e && e.stack || e); }
</script>`;
const safe = (b, q) => { const f = path.resolve(b, decodeURIComponent(q)); return f.startsWith(path.resolve(b) + path.sep) ? f : null; };
const srv = http.createServer((q, s) => { const p = new URL(q.url, 'http://x').pathname;
  if (p === '/') { s.writeHead(200, { 'Content-Type': 'text/html' }); return s.end(html); }
  const f = p === '/host.glb' ? GLB : p.startsWith('/three/addons/') ? safe(path.join(three, 'examples', 'jsm'), p.slice(14)) : p.startsWith('/three/') ? safe(path.join(three, 'build'), p.slice(7)) : null;
  if (!f || !fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'Content-Type': f.endsWith('.js') ? 'text/javascript' : 'application/octet-stream' }); fs.createReadStream(f).pipe(s); });
await new Promise((r) => srv.listen(0, '127.0.0.1', r));
const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
const br = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] });
try {
  const pg = await br.newPage({ viewport: { width: W, height: H } }); await pg.goto(`http://127.0.0.1:${srv.address().port}/`);
  await pg.waitForFunction(() => window.__ready || window.__error, null, { timeout: 120000 }); const e = await pg.evaluate(() => window.__error || null); if (e) throw new Error(e);
  const n = Math.ceil(dur * FPS), t0 = Date.now();
  for (let i = 0; i < n; i++) { const { k, pose } = frameState(i / FPS); await pg.evaluate(([k, pose]) => frame(k, pose), [k, pose]); fs.writeFileSync(path.join(FR, String(i).padStart(4, '0') + '.png'), await pg.screenshot()); }
  const out = path.join(CLIP, `lipsync_${TAG}.mp4`);
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-framerate', String(FPS), '-i', path.join(FR, '%04d.png'), '-i', path.join(CLIP, 'line.mp3'), '-af', 'apad', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-c:a', 'aac', '-b:a', '160k', '-shortest', out]);
  console.log(JSON.stringify({ frames: n, seconds: +dur.toFixed(2), render_s: +((Date.now() - t0) / 1000).toFixed(1), out, visemes: items.length, score: SCORE, sample: words.slice(0, 4).map((w) => [w.text, visemes(w.text).join(' ')]) }));
} finally { await br.close(); srv.close(); }
