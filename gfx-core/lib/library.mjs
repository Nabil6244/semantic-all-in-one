// The universal template library on disk (node: tests, tools, the Python planner's validator). A renderer never reads these files:
// the planner puts the template it uses into the layer.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, MOTIONS } from './tpl.mjs';
import { PRIM_NAMES } from './prims.mjs';
import { TEXT_STYLE_NAMES } from './textstyles.mjs';

export const TEMPLATE_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'templates');
export const COLUMNS = ['label', 'sub', 'text', 'value_from', 'value_to', 'format', 'rows', 'values', 'labels', 'geo', 'geo_area'];

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
  for (const k of ['id', 'family', 'use', 'items', 'niches']) if (t[k] == null) p.push(`${where}: "${k}" is missing`);
  if (t._file && path.basename(t._file, '.json') !== t.id) p.push(`${where}: the file name must be the id`);
  if (t._file && path.dirname(t._file) !== t.family) p.push(`${where}: the folder must be the family "${t.family}"`);
  const slots = t.slots || {};
  const used = new Set();
  JSON.stringify(t.items || []).replace(/\{([a-zA-Z_]\w*)(?:\.[\w.]+)?\}/g, (m, k) => { used.add(k); return m; });
  for (const k of used) if (!(k in slots) && !['it', 'i', 'n', 'len'].includes(k)) p.push(`${where}: uses {${k}} but has no slot "${k}"`);
  for (const [k, s] of Object.entries(slots)) {
    if (s.default === undefined && !s.required) p.push(`${where}: slot "${k}" needs a default or "required": true`);
    if (s.from && !COLUMNS.includes(s.from)) p.push(`${where}: slot "${k}" comes from an unknown column "${s.from}"`);
  }
  for (const it of t.items || []) {
    if (!PRIM_NAMES.includes(it.p)) p.push(`${where}: unknown primitive "${it.p}"`);
    if (it.m && !MOTIONS.includes(it.m)) p.push(`${where}: unknown motion "${it.m}"`);
    if (it.p === 'text' && it.style && !TEXT_STYLE_NAMES.includes(it.style)) p.push(`${where}: unknown text style "${it.style}"`);
  }
  if (!p.length) { try { build(t, {}, { len: t.hold ?? 6 }); } catch (e) { p.push(`${where}: ${e.message}`); } }
  return p;
}
