// Gate 3: replays host/stage3_shots.json (bone rotations about world axes) on the skinned GLB in the app's Three.js.
// Run: node cartoon3d-engine/authoring/host/stage3_check.mjs g2
import fs from 'node:fs'; import http from 'node:http'; import path from 'node:path'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, '..', '..', '..'), TAG = process.argv[2] || 'g1', SHOTFILE = process.argv[3] || 'stage3_shots.json', STAGE = process.argv[4] || 'stage3';
const DIR = path.join(HERE, '..', 'build', STAGE, TAG), OUT = path.join(DIR, 'three'); fs.mkdirSync(OUT, { recursive: true });
const three = path.join(ROOT, 'starmap-engine', 'node_modules', 'three');
const html = `<!doctype html><body style="margin:0;background:#e8e4e0"><script type="importmap">{"imports":{"three":"/three/three.module.min.js","three/addons/":"/three/addons/"}}</script><script type="module">
import * as THREE from 'three'; import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'; import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
try {
const W = 600, H = 712, r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setSize(W, H); document.body.appendChild(r.domElement);
const s = new THREE.Scene(); s.background = new THREE.Color('#e8e4e0');
s.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture; s.environmentIntensity = 0.4;
const add = (c, i, p, sh) => { const l = new THREE.DirectionalLight(c, i); l.position.set(p[0] * 2, 1.475 + p[1] * 2, -0.05 * -1 + p[2] * 2); l.target.position.set(0, 1.475, 0.05); s.add(l.target); s.add(l); if (sh) { l.castShadow = true; l.shadow.mapSize.set(2048, 2048); const c2 = l.shadow.camera; c2.left = -0.5; c2.right = 0.5; c2.top = 0.5; c2.bottom = -0.5; c2.near = 0.5; c2.far = 5; l.shadow.bias = -0.0006; l.shadow.normalBias = 0.004; l.shadow.radius = 6; } };
r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
add(0xfff1e2, 1.2, [-0.85, 0.65, 1.15], true); add(0xeef4ff, 0.42, [1.1, 0.05, 1.1]); add(0xffffff, 0.55, [0.65, 0.75, -0.95]); add(0xffdcc2, 0.08, [0, -0.7, 0.8]);
const g = await new GLTFLoader().loadAsync('/host.glb'); s.add(g.scene);
const meshes = []; let tris = 0; const tex = new Set();
g.scene.traverse((o) => { if (o.isMesh) { meshes.push(o); o.frustumCulled = false; o.castShadow = o.name !== 'cand_mouth'; o.receiveShadow = true; tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3; const m = o.material; ['map','normalMap','roughnessMap'].forEach((t) => { if (m[t]) tex.add(m.name + ':' + t); }); } });
const cam = new THREE.PerspectiveCamera(2 * Math.atan(18 / 85) * 180 / Math.PI, W / H, 0.05, 20);
window.view = (az, t, d = 1.58) => { const a = az * Math.PI / 180; const T = new THREE.Vector3(t[0], t[2], -t[1]); cam.position.set(T.x + d * Math.sin(a), T.y, T.z + d * Math.cos(a)); cam.lookAt(T); };
window.keys = (v) => { for (const m of meshes) { const d = m.morphTargetDictionary; if (!d) continue; m.morphTargetInfluences.fill(0); for (const [n, x] of Object.entries(v)) if (n in d) m.morphTargetInfluences[d[n]] = x; } };
const bones = {}; g.scene.traverse((o) => { if (o.isBone) bones[o.name] = { b: o, q: o.quaternion.clone() }; });
const depth = (o) => { let d = 0; while (o.parent) { d++; o = o.parent; } return d; };
const AX = { x: [1, 0, 0], y: [0, 0, -1], z: [0, 1, 0] };          // Blender world axes in Three's Y-up frame
window.pose = (rot) => { for (const v of Object.values(bones)) v.b.quaternion.copy(v.q); g.scene.updateMatrixWorld(true); const miss = [];
  const names = Object.keys(rot).map((n) => [n, bones[THREE.PropertyBinding.sanitizeNodeName(n)]]).filter(([n, v]) => v || !miss.push(n)).sort((a, b) => depth(a[1].b) - depth(b[1].b));
  for (const [n, v] of names) for (const [ax, deg] of rot[n]) { const pq = new THREE.Quaternion(); v.b.parent.getWorldQuaternion(pq);
    const R = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(...AX[ax]), deg * Math.PI / 180);
    v.b.quaternion.copy(pq.clone().invert().multiply(R).multiply(pq).multiply(v.b.quaternion)); v.b.updateMatrixWorld(true); }
  return miss; };
window.draw = () => { g.scene.updateMatrixWorld(true); r.render(s, cam); };
const names = new Set(); meshes.forEach((m) => Object.keys(m.morphTargetDictionary || {}).forEach((n) => names.add(n)));
window.info = { meshes: meshes.length, triangles: Math.round(tris), textures: [...tex], morphs: [...names] };
window.mem = () => ({ geometries: r.info.memory.geometries, textures: r.info.memory.textures, calls: r.info.render.calls, heap_mb: performance.memory ? +(performance.memory.usedJSHeapSize / 1e6).toFixed(1) : null });
window.__ready = true; } catch (e) { window.__error = String(e && e.stack || e); }
</script>`;
const safe = (b, q) => { const f = path.resolve(b, decodeURIComponent(q)); return f.startsWith(path.resolve(b) + path.sep) ? f : null; };
const srv = http.createServer((q, s) => { const p = new URL(q.url, 'http://x').pathname;
  if (p === '/') { s.writeHead(200, { 'Content-Type': 'text/html' }); return s.end(html); }
  const f = p === '/host.glb' ? path.join(DIR, 'host.glb') : p.startsWith('/three/addons/') ? safe(path.join(three, 'examples', 'jsm'), p.slice(14)) : p.startsWith('/three/') ? safe(path.join(three, 'build'), p.slice(7)) : null;
  if (!f || !fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'Content-Type': f.endsWith('.js') ? 'text/javascript' : 'application/octet-stream' }); fs.createReadStream(f).pipe(s); });
await new Promise((r) => srv.listen(0, '127.0.0.1', r));
const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
const br = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] }); const errors = [];
try {
  const pg = await br.newPage({ viewport: { width: 600, height: 712 } });
  pg.on('pageerror', (e) => errors.push(String(e))); pg.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const t0 = Date.now(); await pg.goto(`http://127.0.0.1:${srv.address().port}/`);
  await pg.waitForFunction(() => window.__ready || window.__error, null, { timeout: 120000 });
  const load_ms = Date.now() - t0; const e = await pg.evaluate(() => window.__error || null); if (e) throw new Error(e);
  const SHOTS = JSON.parse(fs.readFileSync(path.join(HERE, SHOTFILE), 'utf8')); const missing = new Set();
  for (const sh of SHOTS) { const m = await pg.evaluate(([sh]) => { const m = pose(sh.pose || {}); view(sh.az, sh.target, sh.dist); keys(sh.keys || {}); draw(); return m; }, [sh]); m.forEach((x) => missing.add(x)); fs.writeFileSync(path.join(OUT, sh.name + '.png'), await pg.screenshot()); }
  errors.push(...[...missing].map((m) => 'missing bone ' + m));
  const ms = await pg.evaluate(() => { keys({ smile: 0.5, viseme_aa: 0.5 }); const gl = document.querySelector('canvas').getContext('webgl2'); const px = new Uint8Array(4); const a = performance.now(); for (let i = 0; i < 60; i++) { draw(); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); } return (performance.now() - a) / 60; });
  const info = await pg.evaluate(() => window.info);
  const mem = await pg.evaluate(() => window.mem());
  const rep = { ...info, ...mem, morphs: info.morphs.length, load_ms, draw_ms: +ms.toFixed(2), errors }; fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(rep, null, 1)); console.log(JSON.stringify(rep));
} finally { await br.close(); srv.close(); }
