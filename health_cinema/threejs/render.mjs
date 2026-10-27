// Health Cinema Three.js backend (benchmark). Own folder: nothing in whatif-engine is touched. Reuses the repo's pinned three.js
// (starmap-engine/node_modules) and Playwright (flow-engine/node_modules). Usage: node render.mjs frames.json chest.glb OUT_DIR W H [first last]
import fs from 'node:fs'; import path from 'node:path'; import http from 'node:http'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)); const ROOT = path.join(HERE, '..', '..');
const [framesPath, glbPath, outDir, W, H, first, last] = process.argv.slice(2);
const frames = JSON.parse(fs.readFileSync(framesPath, 'utf8'));
const THREE = path.join(ROOT, 'starmap-engine', 'node_modules', 'three');
const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
const TYPES = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.glb': 'model/gltf-binary', '.wasm': 'application/wasm' };
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split('?')[0]); let f = null;
  if (u === '/index.html') f = path.join(HERE, 'page.html'); else if (u === '/page.js') f = path.join(HERE, 'page.js');
  else if (u === '/chest.glb') f = path.resolve(glbPath); else if (u === '/frames.json') f = path.resolve(framesPath);
  else if (u === '/three/three.module.min.js') f = path.join(THREE, 'build', 'three.module.min.js');
  else if (u === '/three/three.core.min.js') f = path.join(THREE, 'build', 'three.core.min.js');
  else if (u.startsWith('/three/addons/')) f = path.join(THREE, 'examples', 'jsm', u.slice(14));
  if (!f || !fs.existsSync(f)) { res.statusCode = 404; return res.end(); }
  res.setHeader('content-type', TYPES[path.extname(f)] || 'application/octet-stream'); fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const emit = (o) => process.stdout.write(JSON.stringify(o) + '\n');
const args = process.env.WHATIF_GL === 'software' ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] : ['--enable-gpu', '--ignore-gpu-blocklist', '--enable-unsafe-swiftshader'];
const channel = process.env.HC_BROWSER_CHANNEL || undefined;   // 'chrome' when Playwright's own Chromium is not installed
const browser = await chromium.launch({ headless: true, args, ...(channel ? { channel } : {}) });
const page = await browser.newPage({ viewport: { width: +W, height: +H }, deviceScaleFactor: 1 });
page.on('console', (m) => { if (m.type() === 'error') emit({ event: 'console_error', text: m.text() }); });
page.on('pageerror', (e) => emit({ event: 'page_error', text: String(e) }));
await page.goto(`http://127.0.0.1:${server.address().port}/index.html?w=${W}&h=${H}`);
await page.waitForFunction('window.__ready === true || window.__error', null, { timeout: 60000 });
const err = await page.evaluate('window.__error'); if (err) { emit({ event: 'error', message: err }); process.exit(2); }
emit({ event: 'gpu', renderer: await page.evaluate('window.__gl') });
fs.mkdirSync(outDir, { recursive: true });
const a = +(first || 0), b = +(last || frames.frames.length); const times = []; const t0 = Date.now();
for (let i = a; i < b; i++) {
  const t1 = Date.now(); const url = await page.evaluate((k) => window.renderFrame(k), i);
  fs.writeFileSync(path.join(outDir, `f${String(i).padStart(5, '0')}.png`), Buffer.from(url.split(',')[1], 'base64')); times.push(Date.now() - t1);
}
emit({ event: 'done', frames: b - a, total_s: (Date.now() - t0) / 1000, avg_ms: times.reduce((x, y) => x + y, 0) / times.length, first_ms: times[0] });
await browser.close(); server.close();
