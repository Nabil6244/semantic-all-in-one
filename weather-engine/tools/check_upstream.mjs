// Upstream-drift report for weather-engine: node tools/check_upstream.mjs [--json]
//
// Compares pakmap-engine as it is now with the fork record (UPSTREAM.json): the three copied files, every pakMap module
// the Weather page loads, and the exports Weather imports. READ ONLY: it never writes or changes a file, here or in
// pakmap-engine. Porting an upstream change into the copies is a separate, approved step that refreshes UPSTREAM.json.
//
// Exit code: 0 = no drift, or drift that is reported only (content changed); 2 = an export Weather imports is gone (the
// Weather renderer would fail to load: that is a breakage, not drift). The Python names in UPSTREAM.json python_uses are
// checked by test_weather_upstream.py.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENGINE = path.join(HERE, '..');
const PAK = path.join(ENGINE, '..', 'pakmap-engine');
const ROOT = path.join(ENGINE, '..');

const sha = (file) => crypto.createHash('sha256').update(fs.readFileSync(file).toString('latin1').replace(/\r\n/g, '\n'), 'latin1').digest('hex');

export async function checkUpstream(record = JSON.parse(fs.readFileSync(path.join(ENGINE, 'UPSTREAM.json'), 'utf8'))) {
  const report = { fork_commit: record.fork_commit, copied_changed: [], copied_missing: [], lib_changed: [], lib_added: [], lib_removed: [], missing_exports: [], diffs: {} };
  for (const [name, hash] of Object.entries(record.copied)) {
    const f = path.join(PAK, name);
    if (!fs.existsSync(f)) { report.copied_missing.push(name); continue; }
    if (sha(f) !== hash) report.copied_changed.push(name);
  }
  const now = fs.readdirSync(path.join(PAK, 'lib')).filter((n) => n.endsWith('.mjs')).sort();
  for (const name of now) {
    if (!(name in record.pakmap_lib)) report.lib_added.push(name);
    else if (sha(path.join(PAK, 'lib', name)) !== record.pakmap_lib[name]) report.lib_changed.push(name);
  }
  for (const name of Object.keys(record.pakmap_lib)) if (!now.includes(name)) report.lib_removed.push(name);
  for (const [mod, names] of Object.entries(record.uses_exports)) {
    const f = path.join(PAK, 'lib', mod);
    let m = null;
    try { m = await import(pathToFileURL(f).href); } catch (err) { report.missing_exports.push(`${mod}: cannot be loaded (${String(err.message || err).split('\n')[0]})`); continue; }
    for (const n of names) if (!(n in m)) report.missing_exports.push(`${mod}: ${n}`);
  }
  // what changed upstream since the fork, for each changed file (needs git; otherwise only the names are reported)
  for (const name of [...report.copied_changed, ...report.lib_changed.map((n) => `lib/${n}`)]) {
    const r = spawnSync('git', ['diff', '--no-color', record.fork_commit, '--', `pakmap-engine/${name}`], { cwd: ROOT, encoding: 'utf8' });
    report.diffs[name] = r.status === 0 ? r.stdout : '(git is not available here: compare by hand)';
  }
  report.drift = report.copied_changed.length + report.copied_missing.length + report.lib_changed.length + report.lib_added.length + report.lib_removed.length > 0;
  report.broken = report.missing_exports.length > 0 || report.copied_missing.length > 0;
  return report;
}

function print(r) {
  const out = [];
  out.push(`weather-engine upstream check (forked from pakmap-engine at ${r.fork_commit})`);
  if (!r.drift && !r.broken) { out.push('No drift: pakmap-engine matches the fork record.'); return out.join('\n'); }
  if (r.copied_changed.length) out.push(`Copied files changed upstream (review and port by hand if wanted): ${r.copied_changed.join(', ')}`);
  if (r.copied_missing.length) out.push(`Copied files gone upstream: ${r.copied_missing.join(', ')}`);
  if (r.lib_changed.length) out.push(`pakMap modules changed (Weather loads them as they are now): ${r.lib_changed.join(', ')}`);
  if (r.lib_added.length) out.push(`pakMap modules added: ${r.lib_added.join(', ')}`);
  if (r.lib_removed.length) out.push(`pakMap modules removed: ${r.lib_removed.join(', ')}`);
  if (r.missing_exports.length) out.push(`BROKEN — names Weather imports are gone: ${r.missing_exports.join('; ')}`);
  for (const [name, diff] of Object.entries(r.diffs)) out.push(`\n--- ${name} since ${r.fork_commit} ---\n${diff.trim() || '(no committed difference: the change is in the working tree)'}`);
  out.push('\nThis report changed nothing. To port: edit the weather-engine copies, then refresh UPSTREAM.json (both as an approved change).');
  return out.join('\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const r = await checkUpstream();
  if (process.argv.includes('--json')) process.stdout.write(JSON.stringify(r, null, 1) + '\n');
  else process.stdout.write(print(r) + '\n');
  process.exit(r.broken ? 2 : 0);
}
