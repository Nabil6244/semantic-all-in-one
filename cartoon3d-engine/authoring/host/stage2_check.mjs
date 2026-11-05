// Renders the Stage 2 bust GLB in the app's Three.js with the same cameras as the Blender portraits.
// Run: node cartoon3d-engine/authoring/host/stage2_check.mjs s1
import fs from 'node:fs'; import http from 'node:http'; import path from 'node:path'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, '..', '..', '..'), TAG = process.argv[2] || 's1';
const DIR = path.join(HERE, '..', 'build', 'stage2', TAG), OUT = path.join(DIR, 'three'); fs.mkdirSync(OUT, { recursive: true });
const three = path.join(ROOT, 'starmap-engine', 'node_modules', 'three');
const html = `<!doctype html><body style="margin:0;background:#e8e4e0"><script type="importmap">{"imports":{"three":"/three/three.module.min.js","three/addons/":"/three/addons/"}}</script><script type="module">
import * as THREE from 'three'; import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'; import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
try {
const W = 800, H = 950, r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setSize(W, H); document.body.appendChild(r.domElement);
const s = new THREE.Scene(); s.background = new THREE.Color('#e8e4e0');
s.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture; s.environmentIntensity = 0.4;
const add = (c, i, p, sh) => { const l = new THREE.DirectionalLight(c, i); l.position.set(p[0] * 2, 1.475 + p[1] * 2, -0.05 * -1 + p[2] * 2); l.target.position.set(0, 1.475, 0.05); s.add(l.target); s.add(l); if (sh) { l.castShadow = true; l.shadow.mapSize.set(2048, 2048); const c2 = l.shadow.camera; c2.left = -0.5; c2.right = 0.5; c2.top = 0.5; c2.bottom = -0.5; c2.near = 0.5; c2.far = 5; l.shadow.bias = -0.0006; l.shadow.normalBias = 0.004; l.shadow.radius = 6; } };
r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
add(0xfff1e2, 1.2, [-0.85, 0.65, 1.15], true); add(0xeef4ff, 0.42, [1.1, 0.05, 1.1]); add(0xffffff, 0.55, [0.65, 0.75, -0.95]); add(0xffdcc2, 0.08, [0, -0.7, 0.8]);
const g = await new GLTFLoader().loadAsync('/bust.glb'); s.add(g.scene);
const meshes = []; let tris = 0; const tex = new Set();
g.scene.traverse((o) => { if (o.isMesh) { meshes.push(o); o.frustumCulled = false; o.castShadow = o.name !== 'cand_mouth'; o.receiveShadow = true; tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3; const m = o.material; ['map','normalMap','roughnessMap'].forEach((t) => { if (m[t]) tex.add(m.name + ':' + t); }); } });
const cam = new THREE.PerspectiveCamera(2 * Math.atan(18 / 85) * 180 / Math.PI, W / H, 0.05, 20);
window.view = (az, t, d = 1.58) => { const a = az * Math.PI / 180; const T = new THREE.Vector3(t[0], t[2], -t[1]); cam.position.set(T.x + d * Math.sin(a), T.y, T.z + d * Math.cos(a)); cam.lookAt(T); };
window.keys = (v) => { for (const m of meshes) { const d = m.morphTargetDictionary; if (!d) continue; m.morphTargetInfluences.fill(0); for (const [n, x] of Object.entries(v)) if (n in d) m.morphTargetInfluences[d[n]] = x; } };
window.draw = () => { g.scene.updateMatrixWorld(true); r.render(s, cam); };
const names = new Set(); meshes.forEach((m) => Object.keys(m.morphTargetDictionary || {}).forEach((n) => names.add(n)));
window.info = { meshes: meshes.length, triangles: Math.round(tris), textures: [...tex], morphs: [...names] };
window.__ready = true; } catch (e) { window.__error = String(e && e.stack || e); }
</script>`;
const safe = (b, q) => { const f = path.resolve(b, decodeURIComponent(q)); return f.startsWith(path.resolve(b) + path.sep) ? f : null; };
const srv = http.createServer((q, s) => { const p = new URL(q.url, 'http://x').pathname;
  if (p === '/') { s.writeHead(200, { 'Content-Type': 'text/html' }); return s.end(html); }
  const f = p === '/bust.glb' ? path.join(DIR, 'bust.glb') : p.startsWith('/three/addons/') ? safe(path.join(three, 'examples', 'jsm'), p.slice(14)) : p.startsWith('/three/') ? safe(path.join(three, 'build'), p.slice(7)) : null;
  if (!f || !fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'Content-Type': f.endsWith('.js') ? 'text/javascript' : 'application/octet-stream' }); fs.createReadStream(f).pipe(s); });
await new Promise((r) => srv.listen(0, '127.0.0.1', r));
const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
const br = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] }); const errors = [];
try {
  const pg = await br.newPage({ viewport: { width: 800, height: 950 } });
  pg.on('pageerror', (e) => errors.push(String(e))); pg.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const t0 = Date.now(); await pg.goto(`http://127.0.0.1:${srv.address().port}/`);
  await pg.waitForFunction(() => window.__ready || window.__error, null, { timeout: 120000 });
  const load_ms = Date.now() - t0; const e = await pg.evaluate(() => window.__error || null); if (e) throw new Error(e);
  const T = [0, -0.05, 1.475], TS = [0.1, 0.035, 1.43], B = (w) => ({ eyeBlinkLeft: w, eyeBlinkRight: w, eyeBlinkArcLeft: 4 * w * (1 - w), eyeBlinkArcRight: 4 * w * (1 - w) });
  const shots = [['front_neutral', 0, T, {}], ['q_neutral', 35, T, {}], ['side_neutral', 90, TS, {}], ['front_smile', 0, T, { smile: 1 }], ['q_smile', 35, T, { smile: 1 }],
    ['blink_half', 0, T, B(0.5)], ['blink', 0, T, B(1)], ['jaw', 0, T, { jawOpen: 1 }], ['aa', 0, T, { viseme_aa: 1 }], ['O', 0, T, { viseme_O: 1 }], ['SS', 0, T, { viseme_SS: 1 }], ['laugh', 0, T, { laugh: 1 }]];
  for (const [n, az, t, k] of shots) { await pg.evaluate(([az, t, k]) => { view(az, t); keys(k); draw(); }, [az, t, k]); fs.writeFileSync(path.join(OUT, n + '.png'), await pg.screenshot()); }
  const ms = await pg.evaluate(() => { keys({ smile: 0.5, viseme_aa: 0.5 }); const gl = document.querySelector('canvas').getContext('webgl2'); const px = new Uint8Array(4); const a = performance.now(); for (let i = 0; i < 60; i++) { draw(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); } return (performance.now() - a) / 60; });
  const info = await pg.evaluate(() => window.info);
  const rep = { ...info, morphs: info.morphs.length, load_ms, draw_ms: +ms.toFixed(2), errors }; fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(rep, null, 1)); console.log(JSON.stringify(rep));
} finally { await br.close(); srv.close(); }
