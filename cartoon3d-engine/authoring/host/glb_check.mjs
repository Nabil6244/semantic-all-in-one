// Loads build/host_test.glb in the app's own Three.js and headless browser, drives morphs and bones, saves stills and a report.
// Run: node cartoon3d-engine/authoring/host/glb_check.mjs
import fs from 'node:fs'; import http from 'node:http'; import path from 'node:path'; import { createRequire } from 'node:module'; import { fileURLToPath } from 'node:url';
const HERE = path.dirname(fileURLToPath(import.meta.url)), BUILD = path.join(HERE, '..', 'build'), ROOT = path.resolve(HERE, '..', '..', '..');
const three = path.join(ROOT, 'starmap-engine', 'node_modules', 'three'), OUT = path.join(BUILD, 'face', 'glb'); fs.mkdirSync(OUT, { recursive: true });
const html = `<!doctype html><body style="margin:0;background:#e8e4e0"><script type="importmap">{"imports":{"three":"/three/three.module.min.js","three/addons/":"/three/addons/"}}</script><script type="module">
import * as THREE from 'three'; import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'; import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
try {
const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setSize(700, 840); document.body.appendChild(r.domElement);
const s = new THREE.Scene(); s.background = new THREE.Color('#e8e4e0'); s.environment = new THREE.PMREMGenerator(r).fromScene(new RoomEnvironment(), 0.04).texture; s.environmentIntensity = 0.45;
const k = new THREE.DirectionalLight(0xfff1e2, 1.6); k.position.set(-1, 2.2, 2); s.add(k); const f = new THREE.DirectionalLight(0xeef4ff, 0.5); f.position.set(1.4, 1.2, 1.6); s.add(f);
const g = await new GLTFLoader().loadAsync('/host.glb'); s.add(g.scene);
const meshes = [], mats = new Set(); let skinned = 0, tris = 0, bones = null; const tex = new Set();
g.scene.traverse((o) => { if (o.isMesh) { meshes.push(o); if (o.isSkinnedMesh) { skinned++; bones = o.skeleton.bones.length; } tris += (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3; (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { mats.add(m.name); ['map','normalMap','roughnessMap'].forEach((t) => { if (m[t]) tex.add(m.name + ':' + t); }); }); o.frustumCulled = false; } });
const cam = new THREE.PerspectiveCamera(13.5, 700/840, 0.1, 20);
const head = g.scene.getObjectByName('head'); const hp = new THREE.Vector3(); head.getWorldPosition(hp);
window.setView = (az, z = 1.5, dy = 0.075) => { const t = new THREE.Vector3(0, hp.y + dy, 0.04); const a = az * Math.PI / 180; cam.position.set(z * Math.sin(a), t.y, t.z + z * Math.cos(a)); cam.lookAt(t); };
window.setKeys = (v) => { for (const m of meshes) { const d = m.morphTargetDictionary; if (!d) continue; m.morphTargetInfluences.fill(0); for (const [n, x] of Object.entries(v)) if (n in d) m.morphTargetInfluences[d[n]] = x; } };
const rest = new Map(); g.scene.traverse((o) => { if (o.isBone) rest.set(o, o.quaternion.clone()); });
window.resetBones = () => { for (const [b, q] of rest) b.quaternion.copy(q); };
window.bend = (names, axis, deg) => { for (const n of names) { const b = g.scene.getObjectByName(n); if (b) b.rotateOnAxis(new THREE.Vector3(...axis), deg * Math.PI / 180); } };
window.draw = () => { g.scene.updateMatrixWorld(true); r.render(s, cam); };
window.delta = (name) => { let peak = 0; for (const m of meshes) { const d = m.morphTargetDictionary; if (!d || !(name in d)) continue; const a = m.geometry.morphAttributes.position?.[d[name]]; if (!a) continue; for (let i = 0; i < a.count; i++) peak = Math.max(peak, Math.hypot(a.getX(i), a.getY(i), a.getZ(i))); } return peak; };
const names = new Set(); meshes.forEach((m) => Object.keys(m.morphTargetDictionary || {}).forEach((n) => names.add(n)));
window.info = { meshes: meshes.length, skinned, bones, triangles: Math.round(tris), materials: [...mats], textures: [...tex], morphs: names.size, relative: g.parser.json.meshes.length, morphByMesh: Object.fromEntries(meshes.filter((m) => m.morphTargetDictionary).map((m) => [m.name, Object.keys(m.morphTargetDictionary).length])) };
window.__ready = true; } catch (e) { window.__error = String(e && e.stack || e); }
</script>`;
const safe = (b, r) => { const f = path.resolve(b, decodeURIComponent(r)); return f.startsWith(path.resolve(b) + path.sep) ? f : null; };
const srv = http.createServer((q, s) => { const p = new URL(q.url, 'http://x').pathname;
  if (p === '/') { s.writeHead(200, { 'Content-Type': 'text/html' }); return s.end(html); }
  const f = p === '/host.glb' ? path.join(BUILD, 'host_test.glb') : p.startsWith('/three/addons/') ? safe(path.join(three, 'examples', 'jsm'), p.slice(14)) : p.startsWith('/three/') ? safe(path.join(three, 'build'), p.slice(7)) : null;
  if (!f || !fs.existsSync(f)) { s.writeHead(404); return s.end(); }
  s.writeHead(200, { 'Content-Type': f.endsWith('.js') ? 'text/javascript' : 'application/octet-stream' }); fs.createReadStream(f).pipe(s); });
await new Promise((r) => srv.listen(0, '127.0.0.1', r));
const { chromium } = createRequire(path.join(ROOT, 'flow-engine', 'package.json'))('playwright');
const br = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] });
const errors = [];
try {
  const pg = await br.newPage({ viewport: { width: 700, height: 840 } });
  pg.on('pageerror', (e) => errors.push(String(e))); pg.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await pg.goto(`http://127.0.0.1:${srv.address().port}/`);
  await pg.waitForFunction(() => window.__ready || window.__error, null, { timeout: 120000 });
  const e = await pg.evaluate(() => window.__error || null); if (e) throw new Error(e);
  const shots = [['neutral', 0, {}], ['smile', 0, { exprSmile: 1 }], ['smile45', 0, { mouthSmileLeft: .45, mouthSmileRight: .45 }], ['laugh', 15, { exprLaugh: 1 }], ['talk', 15, { exprTalk: 1 }], ['surprise', 0, { exprSurprise: 1 }], ['blink', 0, { eyeBlinkLeft: 1, eyeBlinkRight: 1 }], ['smile_blink', 35, { exprSmile: 1, eyeBlinkLeft: 1, eyeBlinkRight: 1 }]];
  for (const [n, az, k] of shots) { await pg.evaluate(([az, k]) => { setView(az); setKeys(k); resetBones(); draw(); }, [az, k]); fs.writeFileSync(path.join(OUT, n + '.png'), await pg.screenshot()); }
  const info = await pg.evaluate(() => ({ ...window.info, peaks_m: Object.fromEntries(['exprSmile', 'viseme_aa', 'eyeBlinkLeft', 'jawOpen'].map((n) => [n, +delta(n).toFixed(4)])) }));
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ ...info, errors }, null, 1));
  console.log(JSON.stringify({ ...info, errors }));
} finally { await br.close(); srv.close(); }
