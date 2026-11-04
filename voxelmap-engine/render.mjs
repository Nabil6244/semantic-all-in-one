// Voxel map prototype renderer.
//   node render.mjs <story.csv> --stills 5,30,62 [--out dir] [--width 1280 --height 720]
//   node render.mjs <story.csv> --clip 0:20 [--fps 30] [--out dir]          (a preview piece, not the full video)
//   node render.mjs <story.csv> --plan                                       (timeline and warnings only, no browser)
// Optional --narration narration.json (from tools/narration_timing.py) to follow a real voiceover.
// A local server for the page, its modules, three.js and the world asset; a GPU Chromium; window.renderFrame(t) per frame;
// JPEGs piped to ffmpeg. stdout: one JSON object per line. Every run ends with a {"event":"perf"} line.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { parseStory } from './lib/beats_csv.mjs';
import { buildTimeline } from './lib/timeline.mjs';
import { cameraAt, placeCamera } from './lib/camera3d.mjs';
import { makeGeo } from './lib/geo.mjs';
import { wantedTiles, parentKey, sampleHeight, maxHeightNear, sampleLand, LEVELS, tileKey } from './lib/lod.mjs';
import { makeWorldData, addTile } from './lib/world_data.mjs';
import { dioramaWeight } from './lib/diorama.mjs';
const smoothstep = (a, b, v) => { const k = Math.max(0, Math.min(1, (v - a) / (b - a))); return k * k * (3 - 2 * k); };

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(HERE, '..');
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const TYPES = { '.mjs': 'text/javascript', '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf' };

function args(argv) {
  const a = { story: argv[0] };
  for (let i = 1; i < argv.length; i++) { const k = argv[i].replace(/^--/, ''); const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true; a[k] = v; }
  return a;
}
const loadPlaywright = () => createRequire(path.join(REPO, 'flow-engine', 'package.json'))('playwright');
const threeDir = () => [path.join(HERE, 'node_modules', 'three'), path.join(REPO, 'starmap-engine', 'node_modules', 'three')].find((d) => fs.existsSync(d));

function serve(config, worldDir) {
  const body = JSON.stringify(config), three = threeDir();
  const server = http.createServer((req, res) => {
    const p = new URL(req.url, 'http://x').pathname;
    let file = null;
    if (p === '/config.json') { res.writeHead(200, { 'Content-Type': 'application/json' }); return res.end(body); }
    if (p === '/' || p === '/index.html') file = path.join(HERE, 'page.html');
    else if (p === '/page.js') file = path.join(HERE, 'page.js');
    else if (/^\/lib\/[\w-]+\.mjs$/.test(p)) file = path.join(HERE, p);
    else if (/^\/world\/[\w.-]+$/.test(p)) file = path.join(worldDir, path.basename(p));
    else if (/^\/world\/L[12]\/\d+_\d+\.bin$/.test(p)) file = path.join(worldDir, p.slice(7));
    else if (/^\/globe\/[\w.-]+$/.test(p)) file = path.join(HERE, 'worlds', '_globe', path.basename(p));
    else if (p === '/three/three.module.min.js' && three) file = path.join(three, 'build', 'three.module.min.js');
    else if (/^\/fonts\/[\w.-]+\.ttf$/.test(p)) file = [path.join(HERE, 'assets', 'fonts', path.basename(p)), path.join(REPO, 'whatif-engine', 'assets', 'fonts', path.basename(p))].find((f) => fs.existsSync(f));
    if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((r) => server.listen(0, '127.0.0.1', () => r(server)));
}

// ---- world data in Node: the level-0 grid plus whichever detail tiles are on disk ----
const readArr = (file, T) => { const b = fs.readFileSync(file); return new T(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength)); };
function loadWorld(worldDir, needs = null) {
  const meta = JSON.parse(fs.readFileSync(path.join(worldDir, 'meta.json'), 'utf8'));
  const data = makeWorldData(meta, { elev: readArr(path.join(worldDir, 'height.i16'), Int16Array), land: readArr(path.join(worldDir, 'land.u8'), Uint8Array), region: readArr(path.join(worldDir, 'region.u16'), Uint16Array) });
  const onDisk = [];
  for (const t of needs || []) {
    const f = path.join(worldDir, `L${t.level}`, `${t.tx}_${t.tz}.bin`);
    if (!fs.existsSync(f)) continue;
    addTile(data, { ...t, buf: fs.readFileSync(f) }); onDisk.push(t);
  }
  return { meta, data, onDisk };
}

/** The detail tiles a story's camera will want (sampled every 0.2 s, with a margin), plus fine ground under every set. */
function planTiles(tl, data, meta) {
  const geo = makeGeo(meta), need = new Map();
  const add = (level, tx, tz) => { need.set(tileKey(level, tx, tz), { level, tx, tz }); const p = parentKey(level, tx, tz); if (p) { const [, a, b] = p.split('_'); need.set(p, { level: 1, tx: +a, tz: +b }); } };
  for (let t = 0; t <= tl.duration; t += 0.2) {
    const pl = placeCamera(cameraAt(tl.camera, t), geo, (x, z) => sampleHeight(data, x, z));
    for (const w of wantedTiles(pl.pos, meta.w, meta.h, 1.08)) add(w.level, w.tx, w.tz);
  }
  for (const b of tl.beats.filter((x) => x.site)) {
    const p = geo.toWorld(b.lon, b.lat), L = LEVELS[1];
    for (let dz = -1; dz <= 1; dz++) for (let dx = -1; dx <= 1; dx++) add(2, Math.floor(p.x / L.tileCells) + dx, Math.floor(p.z / L.tileCells) + dz);
  }
  return [...need.values()].sort((a, b) => a.level - b.level || a.tz - b.tz || a.tx - b.tx);
}

const boxBlur = (s, B, passes = 2) => {
  for (let pass = 0; pass < passes; pass++) {
    const o = new Float32Array(s.length);
    for (let i = 0; i < s.length; i++) { let sum = 0, c = 0; for (let j = Math.max(0, i - B); j <= Math.min(s.length - 1, i + B); j++) { sum += s[j]; c++; } o[i] = sum / c; }
    s = o;
  }
  return s;
};
const tableAt = (tab, t) => { const f = Math.max(0, Math.min(t / tab.dt, tab.values.length - 1)), i = Math.floor(f), j = Math.min(i + 1, tab.values.length - 1); return tab.values[i] + (tab.values[j] - tab.values[i]) * (f - i); };

/** The ground height the camera aims at, over time (10 Hz): the terrain around the target averaged over a patch that grows
 *  with altitude, then eased over a second. Block heights come in whole steps (and change when a finer level takes over),
 *  so aiming at the raw height under the target made the frame jump a block at a time. */
function groundTable(tl, data, meta) {
  const geo = makeGeo(meta), dt = 0.1, n = Math.ceil(tl.duration / dt) + 1, raw = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const c = cameraAt(tl.camera, i * dt), p = geo.toWorld(c.lon, c.lat), r = Math.max(0.3, (c.alt / geo.kmPerCell) * 0.12);
    let sum = 0, m = 0;
    for (let dz = -2; dz <= 2; dz++) for (let dx = -2; dx <= 2; dx++) { sum += sampleHeight(data, p.x + dx * r / 2, p.z + dz * r / 2); m++; }
    raw[i] = sum / m;
  }
  return { dt, values: Array.from(boxBlur(raw, 5), (v) => +v.toFixed(4)) };
}

/** Minimum camera height over time (10 Hz), from the finest terrain along the camera's line of sight, smoothed so the
 *  camera rises over a ridge ahead of time instead of being pushed up in a jolt. Every frame uses the same table. */
function clearanceTable(tl, data, meta, ground) {
  const geo = makeGeo(meta), dt = 0.1, n = Math.ceil(tl.duration / dt) + 1, raw = new Float32Array(n);
  const sitePts = tl.beats.filter((b) => b.site).map((b) => geo.toWorld(b.lon, b.lat));
  for (let i = 0; i < n; i++) {
    const g = tableAt(ground, i * dt), pl = placeCamera(cameraAt(tl.camera, i * dt), geo, () => g);
    let m = 0;
    for (let k = 0; k <= 4; k++) {
      const px = pl.pos.x + (pl.target.x - pl.pos.x) * k / 4, pz = pl.pos.z + (pl.target.z - pl.pos.z) * k / 4;
      m = Math.max(m, maxHeightNear(data, px, pz, Math.max(0.25, pl.distance * 0.08)));
    }
    // terrain only: the margin that grows with altitude is added per frame by the page, so a fast descent is never held up
    // by the larger margin of a second ago (that pinned the camera high and washed the frame out)
    // where a diorama is taking over, the coarse terrain (exaggerated 6.6x in height) no longer holds the camera up; fading
    // it out here, before the time smoothing below, lets the camera ease down onto the diorama instead of snapping
    const c = cameraAt(tl.camera, i * dt), tw = geo.toWorld(c.lon, c.lat);
    let k = 0;
    for (const s of sitePts) k = Math.max(k, dioramaWeight(c.alt) * (1 - smoothstep(0.45, 1.4, Math.hypot(s.x - tw.x, s.z - tw.z))));
    raw[i] = m * (1 - k);
  }
  // look 1.5 s ahead and behind (a moving maximum), then ease it with a 1 s box blur twice
  const R = 15, mx = new Float32Array(n);
  for (let i = 0; i < n; i++) { let v = 0; for (let j = Math.max(0, i - R); j <= Math.min(n - 1, i + R); j++) v = Math.max(v, raw[j]); mx[i] = v; }
  const s = boxBlur(mx, 5);
  for (let i = 0; i < n; i++) s[i] = Math.max(s[i], raw[i]);
  return { dt, values: Array.from(s, (v) => +v.toFixed(4)) };
}

/** A ground scene needs land under it: a ground beat whose point is in the sea (or a river) moves to the nearest land
 *  within ~15 km, and a beach landing to the nearest shoreline (land next to water). Reported as a note, never silent. */
function snapGroundBeats(story) {
  const worldDir = path.join(HERE, 'worlds', story.world || '');
  if (!fs.existsSync(path.join(worldDir, 'meta.json'))) return;
  const needsFile = fs.readdirSync(worldDir).filter((f) => f.startsWith('needs_')).map((f) => path.join(worldDir, f));
  const needs = needsFile.flatMap((f) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')).tiles; } catch { return []; } });
  const { meta, data } = loadWorld(worldDir, needs), geo = makeGeo(meta);
  const landAt = (lon, lat) => { const p = geo.toWorld(lon, lat); return sampleLand(data, p.x, p.z); };
  const shore = (lon, lat) => { const d = 0.004; return [[d, 0], [-d, 0], [0, d], [0, -d]].some(([a, b]) => landAt(lon + a, lat + b) !== 1); };
  for (const b of story.beats) {
    if (b.rung !== 'ground' || !b.site) continue;
    const want = (lon, lat) => landAt(lon, lat) === 1 && (b.site !== 'beach_landing' || shore(lon, lat));
    if (want(b.lon, b.lat)) continue;
    let found = null;
    for (let r = 1; r <= 70 && !found; r++) for (let k = 0; k < 8 * r && !found; k++) {
      const a = (k / (8 * r)) * Math.PI * 2, lon = b.lon + Math.cos(a) * r * 0.002, lat = b.lat + Math.sin(a) * r * 0.002;
      if (want(lon, lat)) found = [lon, lat];
    }
    if (found) { emit({ event: 'note', message: `beat ${b.id}: moved ${(Math.hypot(found[0] - b.lon, found[1] - b.lat) * 111).toFixed(1)} km to ${b.site === 'beach_landing' ? 'the shore' : 'land'} (${found[0].toFixed(3)}, ${found[1].toFixed(3)})` }); b.lon = +found[0].toFixed(4); b.lat = +found[1].toFixed(4); }
    else emit({ event: 'warning', message: `beat ${b.id}: no land within 15 km of its point; the scene will be mostly water` });
  }
}

/** --check: everything that would make a wrong or failing video, before any rendering or download. */
async function checkStory(story, tl, storyPath) {
  const { RECIPES, MUSEUM_ITEMS } = await import('./lib/props.mjs');
  const { FACTION_NAMES } = await import('./lib/figures.mjs');
  const { LIGHTS } = await import('./lib/timeline.mjs');
  const errors = [], warnings = [...tl.warnings];
  const worldDir = path.join(HERE, 'worlds', story.world || '');
  if (!story.world || !fs.existsSync(path.join(worldDir, 'meta.json'))) { errors.push(`world "${story.world}" is not built (tools/build_world.py)`); return { errors, warnings }; }
  const { meta, data } = loadWorld(worldDir), [lo0, la0, lo1, la1] = meta.bbox;
  const inside = (lon, lat) => lon >= lo0 && lon <= lo1 && lat >= la0 && lat <= la1;
  const keys = new Set(story.territories.map((x) => x.key));
  let prev = '';
  story.beats.forEach((b) => {
    const at = `beat ${b.id}`;
    if (b.rung !== 'globe' && !inside(b.lon, b.lat)) errors.push(`${at}: ${b.lon},${b.lat} is outside the world ${meta.bbox.join(',')}`);
    if (b.site && !RECIPES.includes(b.site)) errors.push(`${at}: site "${b.site}" is not a recipe (${RECIPES.join(', ')})`);
    if (b.site && b.rung !== 'ground') warnings.push(`${at}: a site only shows on a ground beat`);
    if (b.territory && !keys.has(b.territory)) errors.push(`${at}: territory "${b.territory}" has no territory row`);
    if (b.light && !LIGHTS.includes(b.light)) errors.push(`${at}: light "${b.light}" (use ${LIGHTS.join(', ')})`);
    for (const f of b.factions || []) if (!FACTION_NAMES.includes(f)) errors.push(`${at}: faction "${f}" (use ${FACTION_NAMES.join(', ')})`);
    for (const e of b.effects || []) { if (!['blasts', 'smoke', 'fires', 'planes'].includes(e.kind)) errors.push(`${at}: effect kind "${e.kind}"`); if (!e.at || !inside(e.at[0], e.at[1])) errors.push(`${at}: effect needs "at" inside the world`); }
    if (b.museum && !MUSEUM_ITEMS.includes(b.museum.item)) errors.push(`${at}: museum item "${b.museum.item}" (use ${MUSEUM_ITEMS.join(', ')})`);
    if (b.date < prev) warnings.push(`${at}: date ${b.date} goes back from ${prev}`);
    prev = b.date;
    if (!b.sentences.length) errors.push(`${at}: no narration`);
  });
  for (const l of story.labels) if (!inside(l.lon, l.lat)) warnings.push(`label "${l.name}" is outside the world`);
  // detail tiles the camera would want, and how many elevation tiles that would download
  const tiles = planTiles(tl, data, meta), missing = tiles.filter((t) => !fs.existsSync(path.join(worldDir, `L${t.level}`, `${t.tx}_${t.tz}.bin`)));
  const zoomOf = { 1: 9, 2: 10 }, cellsOf = { 1: 40, 2: 10 }, kOf = { 1: 4, 2: 16 }, need = new Set();
  const txy = (lon, lat, z) => { const n = 2 ** z, r = (lat * Math.PI) / 180; return [((lon + 180) / 360) * n, ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n]; };
  for (const t of missing) {
    const res = meta.res / kOf[t.level], pad = 16 * res, lon = lo0 + t.tx * cellsOf[t.level] * meta.res, lat = la1 - t.tz * cellsOf[t.level] * meta.res, span = cellsOf[t.level] * meta.res, z = zoomOf[t.level];
    const [x0, y0] = txy(lon - pad, lat + pad, z), [x1, y1] = txy(lon + span + pad, lat - span - pad, z);
    for (let y = Math.floor(y0); y <= Math.floor(y1); y++) for (let x = Math.floor(x0); x <= Math.floor(x1); x++) if (!fs.existsSync(path.join(HERE, 'cache', 'terrarium', String(z), String(x), `${y}.png`))) need.add(`${z}/${x}/${y}`);
  }
  if (story.beats.some((b) => b.rung === 'globe') && !fs.existsSync(path.join(HERE, 'worlds', '_globe', 'meta.json'))) warnings.push('globe beats need tools/build_globe.py once (~5 MB)');
  return { errors, warnings, duration_s: tl.duration, beats: story.beats.length, chapters: story.chapters.length, shots: tl.shots.map((x) => x.shot),
    detail_tiles: { planned: tiles.length, to_build: missing.length, downloads: need.size, download_mb_est: +(need.size * 0.065).toFixed(1) } };
}

const pct = (xs, q) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(q * s.length))] : 0; };

async function main() {
  const a = args(process.argv.slice(2));
  if (!a.story) throw new Error('usage: node render.mjs <story.csv> --stills t,t | --clip a:b | --plan');
  const story = parseStory(fs.readFileSync(a.story, 'utf8'));
  const narration = a.narration ? JSON.parse(fs.readFileSync(a.narration, 'utf8')).sentences : null;
  snapGroundBeats(story);
  const tl = buildTimeline(story, narration);
  for (const w of tl.warnings) emit({ event: 'warning', message: w });
  for (const n of tl.notes || []) emit({ event: 'note', message: n });
  emit({ event: 'plan', duration: tl.duration, beats: tl.beats.length, chapters: tl.chapters.length, sentences: tl.captions.length });
  if (a.plan) { fs.mkdirSync(a.out || '.', { recursive: true }); fs.writeFileSync(path.join(a.out || '.', 'timeline.json'), JSON.stringify(tl, null, 1)); return; }
  if (a.check) { const r = await checkStory(story, tl, a.story); emit({ event: 'check', ...r }); process.exitCode = r.errors.length ? 1 : 0; return; }

  const W = Number(a.width || story.width), H = Number(a.height || story.height), fps = Number(a.fps || story.fps);
  const outDir = path.resolve(a.out || path.join(HERE, 'out')); fs.mkdirSync(outDir, { recursive: true });
  const worldDir = path.join(HERE, 'worlds', story.world);
  if (!fs.existsSync(path.join(worldDir, 'meta.json'))) throw new Error(`world "${story.world}" is not built: run tools/build_world.py`);
  const needsFile = path.join(worldDir, `needs_${path.basename(a.story, '.csv')}.json`);
  if (a.prepare) {
    const { meta, data } = loadWorld(worldDir);
    const tiles = planTiles(tl, data, meta);
    fs.writeFileSync(needsFile, JSON.stringify({ story: a.story, tiles }, null, 1));
    const built = tiles.filter((t) => fs.existsSync(path.join(worldDir, `L${t.level}`, `${t.tx}_${t.tz}.bin`))).length;
    emit({ event: 'tiles_planned', L1: tiles.filter((t) => t.level === 1).length, L2: tiles.filter((t) => t.level === 2).length, already_built: built, file: needsFile });
    if (a.dry) return;
    const py = fs.existsSync(path.join(REPO, '.venv', 'bin', 'python')) ? path.join(REPO, '.venv', 'bin', 'python') : 'python3';
    await new Promise((res, rej) => { const p = spawn(py, [path.join(HERE, 'tools', 'build_detail.py'), '--world', story.world, '--needs', needsFile], { stdio: ['ignore', 'pipe', 'inherit'] });
      let last = ''; p.stdout.on('data', (d) => { last = String(d).trim().split('\n').pop(); }); p.on('close', (c) => (c ? rej(new Error(`build_detail failed (${c})`)) : (emit(JSON.parse(last)), res()))); });
    return;
  }
  const needs = fs.existsSync(needsFile) ? JSON.parse(fs.readFileSync(needsFile, 'utf8')).tiles : [];
  if (!needs.length) emit({ event: 'warning', message: 'no detail tiles planned for this story: run --prepare first (rendering with the world level only)' });
  const { data, onDisk, meta } = loadWorld(worldDir, needs);
  if (onDisk.length < needs.length) emit({ event: 'warning', message: `${needs.length - onDisk.length} planned detail tiles are not built; those areas use a coarser level` });
  const aimGround = groundTable(tl, data, meta);
  const clearance = clearanceTable(tl, data, meta, aimGround);
  const server = await serve({ W, H, fps, timeline: tl, story, tiles: onDisk, clearance, aimGround, blur: a.blur !== 'off' }, worldDir);
  const { chromium } = loadPlaywright();
  const soft = process.env.VOXEL_GL === 'software';
  const browser = await chromium.launch({ headless: true, args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] : ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=metal', '--hide-scrollbars'] });
  const errors = [];
  const wall0 = Date.now();
  try {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    page.on('pageerror', (e) => errors.push(String(e))); page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(`http://127.0.0.1:${server.address().port}/index.html`);
    page.on('console', (m) => { if (process.env.VOXEL_DEBUG) emit({ event: 'console', text: m.text() }); });
    try { await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: Number(process.env.VOXEL_START_MS) || 180000 }); }
    catch (e) { throw new Error(`page did not start: ${errors.slice(0, 5).join(' | ') || e.message} (stage: ${await page.evaluate(() => window.__stage || '?').catch(() => '?')})`); }
    const err = await page.evaluate(() => window.__error || null);
    if (err) throw new Error(`page setup failed: ${err}`);
    const setup = await page.evaluate(() => window.stats());
    emit({ event: 'ready', gpu: setup.gpu, quads: setup.quads, init_ms: setup.initMs, setup_wall_ms: Date.now() - wall0 });

    const frameWall = [];
    if (a.bench) {
      // per altitude band: 8 moments spread through the story where the camera is in that band, each rendered once
      const bands = { high: [300, 1e9], mid: [20, 300], low: [0, 20] }, report = {};
      const all = []; for (let t = 1; t < tl.duration; t += 0.5) all.push({ t, alt: cameraAt(tl.camera, t).alt });
      for (const [name, [lo, hi]] of Object.entries(bands)) {
        const pool = all.filter((x) => x.alt >= lo && x.alt < hi), pick = [];
        for (let i = 0; i < 8 && pool.length; i++) pick.push(pool[Math.floor((i + 0.5) * pool.length / 8)]);
        const ms = [], lods = [];
        for (const p of pick) {
          const f0 = Date.now(); const b64 = await page.evaluate((tt) => window.renderFrame(tt), p.t); ms.push(Date.now() - f0);
          lods.push(await page.evaluate(() => window.stats().last));
          if (pick.indexOf(p) === 0) fs.writeFileSync(path.join(outDir, `bench_${name}_${p.t}.jpg`), Buffer.from(b64, 'base64'));
        }
        const avg = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0);
        report[name] = { frames: ms.length, alt_km: pick.map((p) => +p.alt.toFixed(1)), wall_ms_avg: Math.round(avg(ms)), wall_ms_max: Math.max(0, ...ms),
          L1_tiles_avg: +avg(lods.map((l) => l.L1)).toFixed(1), L2_tiles_avg: +avg(lods.map((l) => l.L2)).toFixed(1), subframes_avg: +avg(lods.map((l) => l.S)).toFixed(1) };
      }
      emit({ event: 'bench', size: `${W}x${H}`, bands: report });
    } else if (a.stills) {
      for (const t of String(a.stills).split(',').map(Number)) {
        const f0 = Date.now();
        const b64 = await page.evaluate((tt) => window.renderFrame(tt), t);
        frameWall.push(Date.now() - f0);
        const file = path.join(outDir, `still_${String(t).replace('.', '_')}.jpg`);
        fs.writeFileSync(file, Buffer.from(b64, 'base64'));
        emit({ event: 'still', t, file });
      }
    } else if (a.clip) {
      const [c0, c1] = String(a.clip).split(':').map(Number), file = path.join(outDir, `preview_${c0}_${c1}.mp4`);
      const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-vf', 'scale=in_range=full:out_range=tv:out_color_matrix=bt709', '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', '-r', String(fps), '-movflags', '+faststart', file], { stdio: ['pipe', 'ignore', 'inherit'] });
      const n = Math.round((c1 - c0) * fps);
      for (let i = 0; i < n; i++) {
        const f0 = Date.now();
        const b64 = await page.evaluate((tt) => window.renderFrame(tt), c0 + i / fps);
        frameWall.push(Date.now() - f0);
        if (!ff.stdin.write(Buffer.from(b64, 'base64'))) await new Promise((r) => ff.stdin.once('drain', r));
        if (i % fps === 0) emit({ event: 'progress', frame: i, total: n });
      }
      ff.stdin.end(); await new Promise((r) => ff.on('close', r));
      if (a.audio) {
        // mux the mixed soundtrack, cut to the clip's window, so audio and video share one clock
        const muxed = file.replace(/\.mp4$/, '_av.mp4');
        await new Promise((r, j) => spawn('ffmpeg', ['-y', '-loglevel', 'error', '-i', file, '-ss', String(c0), '-t', String(c1 - c0), '-i', a.audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', muxed], { stdio: 'inherit' }).on('close', (c) => (c ? j(new Error('mux failed')) : r())));
        emit({ event: 'clip_av', file: muxed });
      }
      emit({ event: 'clip', file });
    }
    const st = await page.evaluate(() => window.stats());
    const gpuMs = st.frameMs.slice(1), wall = frameWall.slice(1);
    const avg = (xs) => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0);
    const perFrame = avg(wall) || avg(frameWall);
    // memory: the page's own counters plus the resident size of every Chromium process of this render
    let chromeMB = null;
    try {
      // Playwright's Chromium processes are this render's children: sum the resident size of every descendant of this process
      const ps = (await import('node:child_process')).execSync('ps -A -o pid=,ppid=,rss=').toString().trim().split('\n').map((l) => l.trim().split(/\s+/).map(Number));
      const kids = new Set([process.pid]); let grew = true;
      while (grew) { grew = false; for (const [p, pp] of ps) if (kids.has(pp) && !kids.has(p)) { kids.add(p); grew = true; } }
      kids.delete(process.pid);
      chromeMB = Math.round(ps.filter(([p]) => kids.has(p)).reduce((s, [, , r]) => s + r, 0) / 1024);
    } catch { /* not reported */ }
    const sub = st.subframes || [];
    emit({ event: 'perf', gpu: st.gpu, size: `${W}x${H}`, frames: frameWall.length, page_ms_avg: Math.round(avg(gpuMs)), page_ms_p95: Math.round(pct(gpuMs, 0.95)),
      wall_ms_avg: Math.round(perFrame), wall_ms_p95: Math.round(pct(wall, 0.95)), wall_ms_max: Math.max(0, ...frameWall), est_full_minutes_at_30fps: +((tl.duration * 30 * perFrame) / 60000).toFixed(1),
      subframes_avg: sub.length ? +(sub.reduce((s, x) => s + x, 0) / sub.length).toFixed(2) : null, tile_meshes_built: st.tileBuilds, tile_build_ms_total: Math.round(st.tileBuildMs),
      max_active_tiles: st.maxActive, world_tiles_loaded: st.worldTiles, gpu_terrain_mb: st.gpuTerrainMB, js_heap_mb: st.jsHeapMB, chromium_rss_mb: chromeMB, init_ms: st.initMs, load_ms: st.loadMs, errors: errors.slice(0, 5) });
  } finally { await browser.close(); server.close(); }
}

main().catch((e) => { emit({ event: 'error', message: String(e && e.message || e) }); process.exit(1); });
