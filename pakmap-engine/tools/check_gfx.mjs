// Dry run of a spec's gfx-core graphics without a browser: node tools/check_gfx.mjs <spec.json>
// Every map_template event is built (slots, cues, times) and drawn at 8 moments across its window on a mock canvas, with a stand-in map projection
// and a stand-in picture. One JSON line on stdout: { events: { <id>: { repairs: [...], fatal: null | "message" } } }. "fatal" = this graphic cannot be
// drawn at all (the guard leaves it out); "repairs" = it draws but something was off (a broken number drawn as nothing, a slot default used).
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createGfx, drawGfx } from '../../gfx-core/lib/render.mjs';
import { mockCanvas } from '../../gfx-core/lib/mockcanvas.mjs';

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const W = spec.width || 1280, H = spec.height || 720, out = {};
const project = (lon, lat) => ({ x: W / 2 + (lon % 180) * (W / 360), y: H / 2 - (lat % 90) * (H / 180) });
const image = { width: 1200, height: 800 };
for (const e of spec.events || []) {
  if (e.type !== 'map_template') continue;
  const rec = { repairs: [], fatal: null };
  try {
    const len = e.t_out - e.t_in, warns = [];
    const inst = createGfx(e.template, e.slots || {}, { len, cues: e.cues || {}, warn: (m) => warns.push(m) });
    rec.repairs.push(...warns);
    const { g, bad } = mockCanvas(W, H);
    for (let i = 0; i <= 8; i++) drawGfx(inst, g, W, H, (len * i) / 8, { project, follow: e.follow ? [0.5, 0.5] : null, image: () => image });
    if (inst.items.some((it) => it._broken)) rec.repairs.push('a piece of the graphic could not be drawn and was left out');
    if (bad.length) rec.repairs.push(`${bad.length} drawing call(s) with a broken number (drawn as nothing), e.g. ${bad[0]}`);
  } catch (err) { rec.fatal = String((err && err.message) || err).slice(0, 300); }
  out[e.id] = rec;
}
process.stdout.write(JSON.stringify({ events: out }) + '\n');
