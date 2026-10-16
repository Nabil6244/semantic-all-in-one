// The template catalog: one still of every template (and the black hole hero scenes), rendered locally by this engine -- no network,
// no generated media. node catalog.mjs <out dir> [id,id,...]   ->  <out>/<id>.jpg and <out>/catalog.jpg (a contact sheet)
// Each template runs on its own plate for its default hold; the still is taken at 75 % of it (when its builds have happened).
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { loadLibrary } from './lib/library.mjs';
import { BLACKHOLE_SCENES } from './lib/blackhole.mjs';
import { HABITAT_SCENES } from './lib/habitat.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || 'catalog');
const only = process.argv[3] ? new Set(process.argv[3].split(',')) : null;
fs.mkdirSync(out, { recursive: true });

const lib = [...loadLibrary().values()].filter((t) => !only || only.has(t.id));
const heroes = [...BLACKHOLE_SCENES, ...HABITAT_SCENES].filter((s) => !only || only.has(s));
const shots = [], layers = [], stills = [];
let t = 0;
for (const tp of lib) {
  const len = tp.hold ?? 6;
  shots.push({ id: tp.id, start: t, end: t + len, kind: 'plate', tint: tp.tint || 'cool' });
  layers.push({ type: 'tm_template', template: tp, slots: {}, start: t, end: t + len, fade_in: 0.05, fade_out: 0.05 });
  stills.push([tp.id, +(t + len * 0.75).toFixed(2)]);
  t += len;
}
for (const sc of heroes) {
  shots.push({ id: sc, start: t, end: t + 5, kind: 'hero', scene: sc, cam: { steps: 260 } });
  stills.push([sc, +(t + 2.5).toFixed(2)]);
  t += 5;
}
const spec = { width: 1280, height: 720, fps: 24, duration: t, look: {}, shots, layers, output: path.join(out, 'catalog.mp4') };
const specPath = path.join(out, 'catalog_spec.json');
fs.writeFileSync(specPath, JSON.stringify(spec));
const r = spawnSync(process.execPath, [path.join(HERE, 'render.mjs'), specPath], { env: { ...process.env, WHATIF_STILLS: stills.map((s) => s[1]).join(',') }, encoding: 'utf8', maxBuffer: 1 << 26 });
process.stdout.write(r.stdout.split('\n').filter((l) => /error|warning|done/.test(l)).join('\n') + '\n');
if (r.status !== 0) { process.stderr.write(r.stderr); process.exit(1); }
for (const [id, at] of stills) {
  const f = `${spec.output}.t${at}.jpg`;
  if (fs.existsSync(f)) fs.renameSync(f, path.join(out, `${id}.jpg`));
}
// contact sheet: 4 across, labelled by file order
const files = stills.map(([id]) => path.join(out, `${id}.jpg`)).filter((f) => fs.existsSync(f));
const cols = 4, rows = Math.ceil(files.length / cols);
const args = ['-y', '-loglevel', 'error'];
for (const f of files) args.push('-i', f);
const parts = files.map((_, i) => `[${i}]scale=480:-1[s${i}]`).join(';');
const layout = files.map((_, i) => `${(i % cols) * 480}_${Math.floor(i / cols) * 270}`).join('|');
args.push('-filter_complex', `${parts};${files.map((_, i) => `[s${i}]`).join('')}xstack=inputs=${files.length}:layout=${layout}:fill=black`, path.join(out, 'catalog.jpg'));
if (files.length > 1) spawnSync('ffmpeg', args, { stdio: 'inherit' });
console.log(JSON.stringify({ stills: files.length, rows, sheet: path.join(out, 'catalog.jpg') }));
