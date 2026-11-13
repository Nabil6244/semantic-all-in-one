#!/usr/bin/env node
// City Timelapse renderer. Story CSV -> plan (timeline, city growth, camera) -> frames in headless Chromium -> mp4.
//
//   node render.mjs samples/rome_timelapse.csv --plan                 # timeline + warnings, no browser
//   node render.mjs story.csv --stills 5,30,60                         # preview stills (out/<story>_t<sec>.jpg)
//   node render.mjs story.csv --clip 20:40                             # a short preview piece
//   node render.mjs story.csv --out out/rome.mp4 --audio out/mix.wav   # the full film
// Options: --w 1920 --h 1080 --fps 30 (preview default 1280x720), --world <id> (else the plan's world), --outdir <dir>.
// stdout: one JSON object per line ({event: ...}); the app reads these for progress.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { parseStory } from './lib/story.mjs';
import { buildTimeline } from './lib/timeline.mjs';
import { makeTerrain } from './lib/terrain.mjs';
import { makeLots, rankLots, makeTrees, roadRanks, needed, cityExtent, fallbackLanes, hash } from './lib/growth.mjs';
import { pathToXZ, footprint } from './lib/landmarks.mjs';
import { styleOf } from './lib/styles.mjs';
import { climateOf, CLIMATES, landClassAt, treeFactor } from './lib/climate.mjs';
import { styleForYear } from './lib/story.mjs';
import { shoreDistance, makeShips, makeFields, clearTreesForFields, planEvent, wallGates } from './lib/fx.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(HERE, '..');
process.stdout.on('error', () => process.exit(0));   // the reader (the app) is gone
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const TYPES = { '.mjs': 'text/javascript', '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.ttf': 'font/ttf', '.png': 'image/png', '.jpg': 'image/jpeg' };
const FONTS = {
  'CityNum.ttf': [path.join(REPO, 'starmap-engine', 'assets', 'fonts', 'Montserrat-VF.ttf'), path.join(REPO, 'pakmap-engine', 'assets', 'fonts', 'Montserrat-VF.ttf'), path.join(HERE, 'assets', 'fonts', 'Montserrat-VF.ttf')],
  'CitySerif.ttf': [path.join(REPO, 'gfx-core', 'fonts', 'CormorantGaramond-VF.ttf'), path.join(HERE, 'assets', 'fonts', 'CormorantGaramond-VF.ttf')],
};
const M_LAT = 110574, M_LON = 111320;

export function args(argv) {
  const a = { story: argv[0] };
  for (let i = 1; i < argv.length; i++) { const k = argv[i].replace(/^--/, ''); const v = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true; a[k] = v; }
  return a;
}
export const slug = (s) => String(s || '').toLowerCase().normalize('NFKD').replace(/[^\w]+/g, '_').replace(/^_|_$/g, '') || 'city';

/** Everything that does not need a browser: world, lots, trees, streets, timeline. */
export function planCity(storyText, { worldsDir = path.join(HERE, 'worlds'), worldId = null, terrainStep = 2 } = {}) {
  const story = parseStory(storyText);
  const id = worldId || story.plan.world || slug(story.plan.city);
  const dir = path.join(worldsDir, id);
  if (!fs.existsSync(path.join(dir, 'meta.json'))) {
    const c = story.plan.center;
    const hint = c ? `python3 tools/build_city.py --id ${id} --center ${c.lon},${c.lat} --size ${story.plan.size || 8}` : 'add a plan row with focus "lon,lat"';
    const e = new Error(`world "${id}" is not built yet (${hint})`); e.code = 'NO_WORLD'; e.worldId = id; throw e;
  }
  const meta = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json'), 'utf8'));
  const buf = fs.readFileSync(path.join(dir, 'height.f32'));
  const heights = new Float32Array(buf.buffer, buf.byteOffset, buf.byteLength / 4);
  const wb = fs.readFileSync(path.join(dir, 'water.u8')), water = new Uint8Array(wb.buffer, wb.byteOffset, wb.byteLength);
  const lf = path.join(dir, 'water_level.f32');
  const level = fs.existsSync(lf) ? (() => { const b = fs.readFileSync(lf); return new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4); })() : null;
  const T = makeTerrain(heights, meta.w, meta.h, meta.cell, { step: terrainStep, water, level });
  const [lon0, lat0] = meta.center, kx = M_LON * Math.cos((lat0 * Math.PI) / 180);
  const toXZ = (lon, lat) => ({ x: (lon - lon0) * kx, z: -(lat - lat0) * M_LAT });
  let roads = fs.existsSync(path.join(dir, 'roads.json')) ? JSON.parse(fs.readFileSync(path.join(dir, 'roads.json'), 'utf8')) : [];
  const warnings = [...story.warnings];
  if (!roads.length) { roads = fallbackLanes(T, story.plan.seed || 1); warnings.push('no street data for this world: the city lays out its own lanes'); }
  const seed = Number(story.plan.seed) || 7;
  // look "real" (plan extra {"look":"real"}): each lot is a real OpenStreetMap building (tools/build_real.py), with its own height
  const realLook = String(story.plan.look || '').toLowerCase() === 'real', bf = path.join(dir, 'buildings.json');
  let lots;
  if (realLook && fs.existsSync(bf)) {
    lots = JSON.parse(fs.readFileSync(bf, 'utf8')).map(([x, z, rot, w, d, h]) => ({ x, z, rot, w, d, h, y: T.heightAt(x, z), cls: 2 }))
      .filter((l) => l.y > -0.3 && !T.waterAt?.(l.x, l.z));
    warnings.push(`real look: ${lots.length.toLocaleString('en-US')} real buildings`);
  } else {
    if (realLook) warnings.push(`look "real" needs real buildings: run python3 tools/build_real.py --id ${id}; using generated houses`);
    lots = makeLots(roads, T, { seed, infill: story.plan.infill !== false });
  }
  const firstYear = story.eras[0].year, lastYear = story.eras[story.eras.length - 1].year;
  let cores = story.districts.map((d) => ({ ...toXZ(d.lon, d.lat), year: d.year ?? firstYear, weight: d.weight }));
  if (!cores.length) {
    const f = story.eras.find((e) => e.focus)?.focus;
    cores = [{ ...(f ? toXZ(f.lon, f.lat) : { x: 0, z: 0 }), year: firstYear, weight: 1 }];
    warnings.push('no district rows: the city grows from one centre');
  }
  rankLots(lots, cores, { firstYear, lastYear, seed });
  const climate = climateOf(story.plan, meta);
  // land use (built with the world): trees follow parks, farmland and woods; ground colour follows it in the page
  const lcf = path.join(dir, 'landuse_cls.u8');
  const landCls = fs.existsSync(lcf) ? new Uint8Array(fs.readFileSync(lcf)) : null;
  const hasLanduse = !!landCls && landCls.length === 1024 * 1024;
  const cd = CLIMATES[climate].treeDensity;
  const trees = makeTrees(T, lots, { seed: seed + 4, density: cd, densityAt: hasLanduse ? (x, z) => treeFactor(landClassAt(landCls, T.half, x, z), cd) : null });
  // farm fields round the growing city (fewer in dry land), and the trees on them go when they are first ploughed
  const fields = realLook ? [] : makeFields(T, lots, { seed: seed + 6, density: climate === 'arid' ? 0.25 : 1 });
  clearTreesForFields(trees, fields);
  const shore = shoreDistance(T);
  const ships = story.plan.ships === false ? [] : makeShips(T, shore, { seed: seed + 8 });
  const rr = roadRanks(roads, lots);
  roads.forEach((r, i) => { r.rank = rr[i]; });
  const landmarks = story.landmarks.map((l) => ({ ...l, ...(l.lon != null ? toXZ(l.lon, l.lat) : { x: 0, z: 0 }), points: l.extra.path ? pathToXZ(l.extra.path, toXZ) : null }));
  for (const l of landmarks) if (l.kind === 'wall' && l.points) l.gates = wallGates(l.points, roads);
  for (const l of landmarks) if (Math.abs(l.x) > T.half || Math.abs(l.z) > T.half) warnings.push(`line ${l.line}: landmark "${l.id}" is outside the world`);
  // houses and trees give way to a landmark from the year it stands (until it is gone)
  const covered = (items) => {
    const B = 40, grid = new Map();
    items.forEach((it, i) => { const k = Math.floor(it.x / B) * 100003 + Math.floor(it.z / B); (grid.get(k) || grid.set(k, []).get(k)).push(i); it.block = Infinity; it.unblock = Infinity; });
    for (const l of landmarks) {
      const from = l.year ?? -1e9, to = l.until ?? Infinity;
      for (const c of footprint(l)) {
        for (let i = Math.floor((c.x - c.r) / B); i <= Math.floor((c.x + c.r) / B); i++) for (let j = Math.floor((c.z - c.r) / B); j <= Math.floor((c.z + c.r) / B); j++) {
          for (const idx of grid.get(i * 100003 + j) || []) { const it = items[idx]; if (Math.hypot(it.x - c.x, it.z - c.z) < c.r && from < it.block) { it.block = from; it.unblock = to; } }
        }
      }
    }
  };
  covered(lots); covered(trees);
  const landmarkXZ = Object.fromEntries(landmarks.map((l) => [l.id, { x: l.x, z: l.z }]));
  const extentCache = new Map();
  const city = {
    toXZ, landmarkXZ,
    extent: (year, pop, style) => { const k = `${year}|${pop}|${style}`; if (!extentCache.has(k)) extentCache.set(k, cityExtent(lots, needed(pop, year, lots.length, styleOf(style).pph))); return extentCache.get(k); },
  };
  const tl = buildTimeline(story, city);
  const events = story.events.map((e) => {
    const ev = { ...toXZ(e.lon, e.lat), kind: e.kind, r: e.radius, year: e.year, regrow: e.regrow ?? 25, down: e.down ?? 2 };
    return { ...ev, ...planEvent(T, shore, ev, { seed }) };
  });
  // a siege camp clears its own ground: the trees there are felled for the camp and grow back after
  for (const e of events) if (e.kind === 'siege') {
    const r = Math.max(160, e.r * 0.8);
    for (const t of trees) if (Math.hypot(t.x - e.x, t.z - e.z) < r && !Number.isFinite(t.block)) { t.block = e.year - 1; t.unblock = e.year + 3; }
  }
  for (const e of tl.captions) if (e.text.split(/\s+/).length > 28) warnings.push(`caption too long to read comfortably: "${e.text.slice(0, 40)}…"`);
  for (const h of tl.holds) {
    const n = needed(h.pop, h.year, lots.length, styleOf(h.style).pph);
    if (n >= lots.length * 0.999) warnings.push(`era ${h.year}: population fills every lot in the area (${lots.length.toLocaleString('en-US')}); a bigger --size world would show more`);
  }
  return { story, meta, climate, hasLanduse, realLook, worldDir: dir, worldId: id, T, lots, trees, fields, ships, roads, landmarks, events, tl, warnings };
}

export const LOT_STRIDE = 12;   // x z rot w d y rank styleHash block unblock realHeight infill
function packLots(lots) {
  const a = new Float32Array(lots.length * LOT_STRIDE), big = (v) => (Number.isFinite(v) ? v : 1e9);
  lots.forEach((l, i) => { a.set([l.x, l.z, l.rot, l.w, l.d, l.y, l.rank, hash(i, 77), big(l.block), big(l.unblock), l.h || 0, l.infill ? 1 : 0], i * LOT_STRIDE); });
  return a;
}
function packTrees(trees) {
  const a = new Float32Array(trees.length * 8), big = (v) => (Number.isFinite(v) ? v : 1e9);
  trees.forEach((t, i) => { a.set([t.x, t.z, t.y, t.kind, t.s, big(t.rank), big(t.block), big(t.unblock)], i * 8); });
  return a;
}

function serve(config, files) {
  const body = JSON.stringify(config);
  const three = [path.join(HERE, 'node_modules', 'three', 'build'), path.join(REPO, 'starmap-engine', 'node_modules', 'three', 'build'), path.join(REPO, 'voxelmap-engine', 'node_modules', 'three', 'build')].find((d) => fs.existsSync(d));
  const server = http.createServer((req, res) => {
    const p = new URL(req.url, 'http://x').pathname;
    let file = null, data = null;
    if (p === '/config.json') data = body;
    else if (p === '/' || p === '/index.html') file = path.join(HERE, 'page.html');
    else if (p === '/page.js') file = path.join(HERE, 'page.js');
    else if (/^\/lib\/[\w-]+\.mjs$/.test(p)) file = path.join(HERE, p);
    else if (p === '/three/three.module.min.js') file = path.join(three, 'three.module.min.js');
    else if (/^\/three\/three\.core(\.min)?\.js$/.test(p)) file = path.join(three, path.basename(p));
    else if (/^\/fonts\/City(Num|Serif)\.ttf$/.test(p)) file = FONTS[path.basename(p)].find((f) => fs.existsSync(f));
    else if (files[p]) { if (Buffer.isBuffer(files[p]) || ArrayBuffer.isView(files[p])) data = Buffer.from(files[p].buffer ?? files[p], files[p].byteOffset ?? 0, files[p].byteLength); else file = files[p]; }
    if (data != null) { res.writeHead(200, { 'Content-Type': p.endsWith('.json') ? 'application/json' : 'application/octet-stream' }); return res.end(data); }
    if (!file || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise((r) => server.listen(0, '127.0.0.1', () => r(server)));
}

const loadPlaywright = () => createRequire(path.join(REPO, 'flow-engine', 'package.json'))('playwright');

async function main() {
  const a = args(process.argv.slice(2));
  if (!a.story) { console.error('usage: node render.mjs story.csv [--plan] [--stills 5,30] [--clip 20:40] [--out file.mp4] [--audio mix.wav]'); process.exit(2); }
  const preview = Boolean(a.stills || a.clip);
  const W = Number(a.w) || (preview ? 1280 : 1920), H = Number(a.h) || (preview ? 720 : 1080), fps = Number(a.fps) || 30;
  const t0 = Date.now();
  let plan;
  try { plan = planCity(fs.readFileSync(a.story, 'utf8'), { worldId: a.world || null }); }
  catch (e) { emit({ event: 'error', code: e.code || 'PLAN', world: e.worldId, message: e.message }); process.exit(1); }
  const { tl, lots, trees, fields, ships, roads, landmarks, events, warnings, meta, worldDir } = plan;
  for (const w of warnings) emit({ event: 'warning', message: w });
  emit({ event: 'plan', world: plan.worldId, landuse: plan.hasLanduse, duration: +tl.duration.toFixed(2), eras: tl.holds.length, lots: lots.length, infill: lots.filter((l) => l.infill).length, trees: trees.length, fields: fields.length, ships: ships.length, roads: roads.length, landmarks: landmarks.length, plan_ms: Date.now() - t0 });
  const name = path.basename(a.story).replace(/\.csv$/i, '');
  const outDir = a.outdir ? path.resolve(a.outdir) : path.join(HERE, 'out'); fs.mkdirSync(outDir, { recursive: true });
  if (a.plan) {
    const rows = tl.holds.map((h) => ({ year: h.year, from: +h.tr0.toFixed(1), hold: [+h.h0.toFixed(1), +h.h1.toFixed(1)], pop: h.pop, houses: Math.round(needed(h.pop, h.year, lots.length, styleOf(h.style).pph)), style: h.style }));
    fs.writeFileSync(path.join(outDir, a.outdir ? 'timeline.json' : `${name}_timeline.json`), JSON.stringify({ ...tl, rows, world: plan.worldId, credits: meta.credits }, null, 1));
    rows.forEach((r) => emit({ event: 'era', ...r }));
    return;
  }
  // ground picture for the real look: "satellite" (ground_sat.jpg) or "landuse" (landuse.png), whichever the story asks for and the world has
  const wantGround = String(plan.story.plan.ground || (plan.realLook ? 'landuse' : '')).toLowerCase();
  const groundFile = { satellite: 'ground_sat.jpg', landuse: 'landuse.png' }[wantGround];
  const groundKind = plan.realLook && groundFile && fs.existsSync(path.join(worldDir, groundFile)) ? wantGround : null;
  const config = { W, H, fps, tl, world: { w: meta.w, h: meta.h, cell: meta.cell, borderWater: meta.border_water ?? 1, hasLevel: fs.existsSync(path.join(worldDir, 'water_level.f32')), hasLanduse: plan.hasLanduse }, terrainStep: 2, climate: CLIMATES[plan.climate], look: plan.realLook ? 'real' : 'low', ground: groundKind, roads, landmarks, events, fields, ships, lotStride: LOT_STRIDE, sun: plan.story.plan.sun, tiltShift: plan.story.plan.tilt_shift ?? (plan.realLook ? 0.25 : 1) };
  const server = await serve(config, { '/world/height.f32': path.join(worldDir, 'height.f32'), ...(plan.hasLanduse ? { '/world/landuse_cls.u8': path.join(worldDir, 'landuse_cls.u8') } : {}), '/world/water.u8': path.join(worldDir, 'water.u8'), '/world/water_level.f32': path.join(worldDir, 'water_level.f32'), ...(groundKind ? { '/world/ground.img': path.join(worldDir, groundFile) } : {}), '/data/lots.bin': packLots(lots), '/data/trees.bin': packTrees(trees) });
  const { chromium } = loadPlaywright();
  const soft = process.env.CITY_GL === 'software';
  const browser = await chromium.launch({ headless: true, args: soft ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] : ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=metal', '--hide-scrollbars'] });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    page.on('pageerror', (e) => errors.push(String(e))); page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto(`http://127.0.0.1:${server.address().port}/index.html`);
    try { await page.waitForFunction(() => window.__ready === true || window.__error, null, { timeout: 240000 }); }
    catch (e) { throw new Error(`page did not start: ${errors.slice(0, 5).join(' | ') || e.message} (stage: ${await page.evaluate(() => window.__stage || '?').catch(() => '?')})`); }
    const err = await page.evaluate(() => window.__error || null);
    if (err) throw new Error(`page setup failed: ${err}`);
    emit({ event: 'ready', ...(await page.evaluate(() => window.stats())), setup_ms: Date.now() - t0 });
    const frame = async (t) => Buffer.from(await page.evaluate((tt) => window.renderFrame(tt), t), 'base64');
    if (a.stills) {
      for (const s of String(a.stills).split(',').map(Number).filter(Number.isFinite)) {
        const f0 = Date.now(), file = path.join(outDir, `${name}_t${s}.jpg`);
        fs.writeFileSync(file, await frame(s));
        emit({ event: 'still', t: s, file, ms: Date.now() - f0 });
      }
      return;
    }
    const [c0, c1] = a.clip ? String(a.clip).split(':').map(Number) : [0, tl.duration];
    const n = Math.max(1, Math.round((Math.min(c1, tl.duration) - c0) * fps));
    const file = a.out ? path.resolve(a.out) : path.join(outDir, a.clip ? `${name}_clip_${c0}-${c1}.mp4` : `${name}.mp4`);
    const silent = a.audio ? file.replace(/\.mp4$/, '_video.mp4') : file;
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', silent], { stdio: ['pipe', 'inherit', 'inherit'] });
    const done = new Promise((r, j) => ff.on('close', (c) => (c ? j(new Error(`ffmpeg failed (${c})`)) : r())));
    const ms = [];
    for (let i = 0; i < n; i++) {
      const f0 = Date.now(), jpg = await frame(c0 + i / fps); ms.push(Date.now() - f0);
      if (!ff.stdin.write(jpg)) await new Promise((r) => ff.stdin.once('drain', r));
      if (i % 15 === 0 || i === n - 1) emit({ event: 'progress', frame: i + 1, frames: n, pct: +(((i + 1) / n) * 100).toFixed(1) });
    }
    ff.stdin.end(); await done;
    if (a.audio) {
      await new Promise((r, j) => spawn('ffmpeg', ['-y', '-loglevel', 'error', '-i', silent, '-ss', String(c0), '-t', String(n / fps), '-i', a.audio, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', file], { stdio: 'inherit' })
        .on('close', (c) => (c ? j(new Error('mux failed')) : r())));
      fs.rmSync(silent, { force: true });
    }
    ms.sort((x, y) => x - y);
    emit({ event: 'done', file, frames: n, seconds: +(n / fps).toFixed(2), wall_s: +((Date.now() - t0) / 1000).toFixed(1),
      frame_ms: { avg: Math.round(ms.reduce((s, x) => s + x, 0) / ms.length), p95: ms[Math.floor(ms.length * 0.95)], max: ms[ms.length - 1] } });
  } finally {
    await browser.close(); server.close();
    if (errors.length) emit({ event: 'page_errors', errors: errors.slice(0, 5) });
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => { emit({ event: 'error', message: String(e.message || e) }); process.exit(1); });
}
