// Health Cinema 3D render worker: ONE browser for many clips. Reads jobs as JSON lines on stdin ({"id", "frames", "glb", "out", "w", "h"}), renders each
// job's frames exactly like render.mjs (same page, same files, same PNG frames), and answers one JSON line per job ({"event": "done" | "error", "id", ...}).
// The browser starts once (render.mjs starts one per clip); every job still gets a fresh page, so no WebGL state carries over between clips.
// Usage: node render_worker.mjs   (the parent closes stdin to stop it)
import fs from 'node:fs'; import path from 'node:path'; import http from 'node:http'; import readline from 'node:readline'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.join(HERE, '..', '..');
const THREE = path.join(ROOT, 'starmap-engine', 'node_modules', 'three');
const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
const TYPES = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm' };
const STATIC = { '/index.html': 'page.html', '/page.js': 'page.js', '/procedural.js': 'procedural.js', '/conditions.js': 'conditions.js', '/atmosphere.js': 'atmosphere.js', '/bodymap.js': 'bodymap.js' };
let job = null;      // the job being rendered: its frames.json and model are what /frames.json and /chest.glb serve
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]); let f = null;
  if (STATIC[u]) f = path.join(HERE, STATIC[u]);
  else if (u === '/chest.glb' && job) f = path.resolve(job.glb); else if (u === '/frames.json' && job) f = path.resolve(job.frames);
  else if (u === '/three/three.module.min.js') f = path.join(THREE, 'build', 'three.module.min.js');
  else if (u === '/three/three.core.min.js') f = path.join(THREE, 'build', 'three.core.min.js');
  else if (u.startsWith('/three/addons/')) f = path.join(THREE, 'examples', 'jsm', u.slice(14));
  if (!f || !fs.existsSync(f)) { res.statusCode = 404; return res.end(); }
  res.setHeader('content-type', TYPES[path.extname(f)] || 'application/octet-stream'); res.setHeader('cache-control', 'no-store'); fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const args = process.env.WHATIF_GL === 'software' ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'];
const channel = process.env.HC_BROWSER_CHANNEL || undefined;
const browser = await chromium.launch({ headless: true, args, ...(channel ? { channel } : {}) });
emit({ event: 'ready' });
const rl = readline.createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  let page = null;
  try {
    job = JSON.parse(line); const t0 = Date.now();
    const frames = JSON.parse(fs.readFileSync(job.frames, 'utf8')).frames.length;
    page = await browser.newPage({ viewport: { width: +job.w, height: +job.h }, deviceScaleFactor: 1 });
    let pageErr = null; page.on('pageerror', (e) => { pageErr = String(e); });
    await page.goto(`http://127.0.0.1:${server.address().port}/index.html?w=${job.w}&h=${job.h}`);
    await page.waitForFunction('window.__ready === true || window.__error', null, { timeout: 60000 });
    const err = await page.evaluate('window.__error'); if (err) throw new Error(err);
    const t1 = Date.now(); fs.mkdirSync(job.out, { recursive: true });
    for (let i = 0; i < frames; i++) {
      const url = await page.evaluate((k) => window.renderFrame(k), i);
      fs.writeFileSync(path.join(job.out, `f${String(i).padStart(5, '0')}.png`), Buffer.from(url.split(',')[1], 'base64'));
    }
    if (pageErr) throw new Error(pageErr);
    emit({ event: 'done', id: job.id, frames, init_s: (t1 - t0) / 1000, frames_s: (Date.now() - t1) / 1000 });
  } catch (e) {
    emit({ event: 'error', id: job && job.id, message: String(e && e.stack || e).slice(0, 2000) });
  } finally {
    if (page) await page.close().catch(() => {});
    job = null;
  }
}
await browser.close(); server.close();
