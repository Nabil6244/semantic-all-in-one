// The upstream-drift check reports, and never writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { checkUpstream } from '../tools/check_upstream.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENGINE = path.join(HERE, '..');
const PAK = path.join(ENGINE, '..', 'pakmap-engine');
const record = () => JSON.parse(fs.readFileSync(path.join(ENGINE, 'UPSTREAM.json'), 'utf8'));

function snapshot(dir) {
  const out = {};
  for (const e of fs.readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (!e.isFile()) continue;
    const f = path.join(e.parentPath ?? e.path, e.name);
    if (f.includes(`${path.sep}node_modules${path.sep}`)) continue;
    const st = fs.statSync(f);
    out[f] = `${st.size}:${st.mtimeMs}`;
  }
  return out;
}

test('every name Weather imports from pakmap-engine still exists', async () => {
  const r = await checkUpstream();
  assert.deepEqual(r.missing_exports, [], r.missing_exports.join('; '));
  assert.equal(r.broken, false);
  if (r.drift) console.log(`upstream drift (reported, not a failure): ${JSON.stringify({ copied: r.copied_changed, lib: r.lib_changed, added: r.lib_added })}`);
});

test('a changed upstream file is reported as drift, a missing export as broken', async () => {
  const rec = record();
  rec.copied['page.js'] = '0'.repeat(64);
  rec.pakmap_lib['draw.mjs'] = '0'.repeat(64);
  rec.uses_exports['style.mjs'] = [...rec.uses_exports['style.mjs'], 'NO_SUCH_EXPORT'];
  const r = await checkUpstream(rec);
  assert.ok(r.copied_changed.includes('page.js'));
  assert.ok(r.lib_changed.includes('draw.mjs'));
  assert.ok(r.missing_exports.includes('style.mjs: NO_SUCH_EXPORT'));
  assert.equal(r.drift, true);
  assert.equal(r.broken, true);
  assert.ok('page.js' in r.diffs && 'lib/draw.mjs' in r.diffs, 'each changed file gets its diff section');
});

test('the check changes no file in weather-engine or pakmap-engine', () => {
  const before = { ...snapshot(ENGINE), ...snapshot(PAK) };
  const r = spawnSync(process.execPath, [path.join(ENGINE, 'tools', 'check_upstream.mjs')], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const after = { ...snapshot(ENGINE), ...snapshot(PAK) };
  assert.deepEqual(after, before);
});
