// Dry run of the What If page without a browser: node tools/check_spec.mjs <spec.json | folder of specs> [...]
// For each spec: the shot repairs the page would make, every layer made (lenient, as the page does) and drawn at its start, middle and end
// and at 40 moments across the video on a mock canvas. One JSON line per spec: { spec, repairs: [...], fatal: null | "message" }.
// "fatal" means the page itself would stop -- the stress test (whatif/stress.py) counts those; repairs never stop a render.
import fs from 'node:fs';
import { createRegistry, runLayers } from '../lib/layers.mjs';
import { registerBuiltins } from '../layers/index.mjs';
import { sanitizeShots, shotAt } from '../lib/shots.mjs';
import { mockCanvas } from '../lib/mockcanvas.mjs';

const fakeImage = { width: 1200, height: 800 };
// layers that draw into an offscreen canvas (tm_discmap's feathered disc) get a mock one
if (typeof globalThis.document === 'undefined') globalThis.document = { createElement: () => ({ width: 300, height: 150, getContext: () => mockCanvas().g }) };

export async function checkSpec(spec) {
  const repairs = [];
  const warn = (m) => { if (repairs.length < 60) repairs.push(m); };
  try {
    for (const m of sanitizeShots(spec)) warn(m);
    const W = spec.width || 1280, H = spec.height || 720, dur = spec.duration || (spec.shots.at(-1)?.end ?? 1);
    const reg = registerBuiltins(createRegistry());
    const layers = await reg.instantiate(spec.layers || [], { spec, W, H, loadImage: async () => fakeImage, warn }, { lenient: true, warn });
    const { g, bad } = mockCanvas(W, H);
    const times = new Set();
    for (let i = 0; i <= 40; i++) times.add(+(dur * i / 40).toFixed(3));
    for (const L of layers) for (const t of [L.def.start, (L.def.start + L.def.end) / 2, L.def.end - 0.05]) if (Number.isFinite(t)) times.add(+Math.max(0, Math.min(dur, t)).toFixed(3));
    for (const t of [...times].sort((a, b) => a - b)) {
      const frame = { t, W, H, g, spec, shot: shotAt(spec.shots, t), claims: [] };
      runLayers(layers, frame, 'draw', null, warn);
    }
    if (bad.length) warn(`${bad.length} drawing call(s) with a broken number (drawn as nothing), e.g. ${bad[0]}`);
    return { repairs, fatal: null };
  } catch (e) {
    return { repairs, fatal: String(e && e.stack || e).split('\n').slice(0, 3).join(' | ') };
  }
}

if (process.argv[1] && process.argv[1].endsWith('check_spec.mjs')) {
  const paths = [];
  for (const a of process.argv.slice(2)) {
    if (fs.existsSync(a) && fs.statSync(a).isDirectory()) for (const f of fs.readdirSync(a).filter((x) => x.endsWith('.json')).sort()) paths.push(`${a}/${f}`);
    else paths.push(a);
  }
  for (const p of paths) {
    let spec;
    try { spec = JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { process.stdout.write(JSON.stringify({ spec: p, repairs: [], fatal: `unreadable spec: ${e.message}` }) + '\n'); continue; }
    process.stdout.write(JSON.stringify({ spec: p, ...(await checkSpec(spec)) }) + '\n');
  }
}
