// templates/index.json: id -> family (used by the preview page). Run after adding a template.
import fs from 'node:fs';
import path from 'node:path';
import { loadLibrary, TEMPLATE_DIR } from '../lib/library.mjs';
const idx = {}; for (const t of loadLibrary().values()) idx[t.id] = t.family;
fs.writeFileSync(path.join(TEMPLATE_DIR, 'index.json'), JSON.stringify(idx, null, 1) + '\n');
console.log(Object.keys(idx).length, 'templates');
