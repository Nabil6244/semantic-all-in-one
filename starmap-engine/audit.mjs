#!/usr/bin/env node
// node audit.mjs spec.json [--json]  -> what the viewer will see that reads as broken or boring (no rendering; see lib/audit.mjs)
import fs from 'node:fs';
import { auditSpec } from './lib/audit.mjs';

const spec = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const { issues, frames } = auditSpec(spec);
if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify({ issues, duration: spec.duration, map_s: frames.filter((f) => f.map).length / 6 }));
} else {
  for (const i of issues) console.log(`${i.kind.padEnd(8)} ${i.t0.toFixed(1).padStart(7)}-${i.t1.toFixed(1).padEnd(7)} ${(i.beat || '').padEnd(5)} ${i.detail}`);
  const tot = (k) => issues.filter((i) => i.kind === k).reduce((s, i) => s + i.t1 - i.t0, 0);
  console.log(`total: empty ${tot('empty').toFixed(0)} s, cut ${tot('cut').toFixed(0)} s, still ${tot('still').toFixed(0)} s, offframe ${tot('offframe').toFixed(0)} s, repeat ${tot('repeat').toFixed(0)} s of ${spec.duration.toFixed(0)} s`);
}
