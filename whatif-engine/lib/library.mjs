// The template library on disk (node only: tests, the catalog). The renderer never reads these files -- the planner puts each used
// template into its layer. validate() is the contract every template file must meet; whatif/templates.py checks the same rules.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, changeTimes, continuous, MOTIONS } from './tpl.mjs';
import { PRIM_NAMES } from './prims.mjs';
import { ICON_NAMES } from './icons.mjs';

export const TEMPLATE_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'templates');
export const STILL_GAP_S = 6.5;          // "something changes at least every ~6 s" (docs/whatif: V4 median gap 5.8 s)

export function loadLibrary(dir = TEMPLATE_DIR) {
  const out = new Map();
  for (const fam of fs.readdirSync(dir).sort()) {
    const fd = path.join(dir, fam);
    if (!fs.statSync(fd).isDirectory()) continue;
    for (const f of fs.readdirSync(fd).filter((x) => x.endsWith('.json')).sort()) {
      const t = JSON.parse(fs.readFileSync(path.join(fd, f), 'utf8'));
      t._file = path.join(fam, f);
      out.set(t.id, t);
    }
  }
  return out;
}

/** -> a list of problems (empty = fine). */
export function validate(t) {
  const p = [], where = t._file || t.id;
  for (const k of ['id', 'family', 'use', 'items']) if (t[k] == null) p.push(`${where}: "${k}" is missing`);
  if (t._file && path.basename(t._file, '.json') !== t.id) p.push(`${where}: the file name must be the id`);
  if (t._file && path.dirname(t._file) !== t.family) p.push(`${where}: the folder must be the family "${t.family}"`);
  const slots = t.slots || {};
  const used = new Set();
  JSON.stringify(t.items || []).replace(/\{([a-zA-Z_][\w]*)(?:\.[\w.]+)?\}/g, (m, k) => { used.add(k); return m; });
  for (const k of used) if (!(k in slots) && !['it', 'i', 'n', 'len'].includes(k)) p.push(`${where}: uses {${k}} but has no slot "${k}"`);
  for (const [k, s] of Object.entries(slots)) {
    if (s.default === undefined && !s.required) p.push(`${where}: slot "${k}" needs a default or "required": true`);
    if (s.from && !['label', 'sub', 'text', 'value_from', 'value_to', 'format'].includes(s.from)) p.push(`${where}: slot "${k}" comes from an unknown column "${s.from}"`);
  }
  for (const it of t.items || []) {
    if (!PRIM_NAMES.includes(it.p)) p.push(`${where}: unknown primitive "${it.p}"`);
    if (it.m && !MOTIONS.includes(it.m)) p.push(`${where}: unknown motion "${it.m}"`);
    if (it.p === 'icon' && typeof it.name === 'string' && !it.name.includes('{') && !ICON_NAMES.includes(it.name)) p.push(`${where}: unknown icon "${it.name}"`);
  }
  if (!p.length) {
    try {
      const len = t.hold ?? 6, items = build(t, {}, { len });
      for (const it of items) if (it.p === 'icon' && !ICON_NAMES.includes(it.name)) p.push(`${where}: unknown icon "${it.name}"`);
      // never a still screen: with no continuous motion, the longest gap between changes must stay under STILL_GAP_S
      if (t.plate !== false && !items.some(continuous)) {
        const ts = [0, ...changeTimes(items).filter((x) => x >= 0 && x <= len), len];
        for (let i = 1; i < ts.length; i++) if (ts[i] - ts[i - 1] > STILL_GAP_S) { p.push(`${where}: nothing changes between ${ts[i - 1]} s and ${ts[i]} s`); break; }
      }
    } catch (e) { p.push(`${where}: ${e.message}`); }
  }
  return p;
}
