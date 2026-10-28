// PRODUCT BENCH: the review-lab set of the iPhone review reference: a dark workshop with a blue pegboard wall of tools, warm and teal bokeh lights, a grey
// table with props, and one to three phones lying landscape on cone stands with a chart, bars, a figure or a heat map on each screen. The room is out of
// focus, a slow push and a sideways drift move the camera. No picture is needed.
//   { id, start, end, kind: "product", object: "bench", phone: "iphone 18 pro", colors: ["Black", "White"],
//     screens: [{ type: "chart" | "bars" | "number" | "heat", title: "Frame rate", label: "iPhone 18 Pro Max", value: 59, values: [60, 52], color: "#4ad8ff" }, ...],
//     cam: { x: [-0.5, 0.5], dist: [6.4, 5.5], y: 0.5 }, palette: "blue" | "teal" | "amber", focus: 0.0016, bloom: 0.35, seed }
// A pure function of the time inside the shot; the same interface as buildProduct: { place(camera, k, t), render(renderer, camera) }.

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const lerp = (a, b, k) => a + (b - a) * k;
const ease = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const camE = (k, tr, shot) => { const kk = clamp01(k), lin = 0.75 * kk + 0.25 * ease(kk), t = shot && shot.travel != null ? shot.travel : tr; return 0.5 + (lin - 0.5) * t; };
const seeded = (seed) => { let s = (seed >>> 0) || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
const PAL = {
  blue: { wall: ['#0b1a33', '#102a52', '#07101f'], accent: '#ff9d3a', bokeh: ['#ff9d3a', '#4ad8ff', '#ff5e8a', '#ffd36a'], key: 0x6aa8ff, warm: 0xff9a4a, mat: '#12365e' },
  teal: { wall: ['#06232b', '#0c4350', '#04141a'], accent: '#ffb84a', bokeh: ['#ffb84a', '#3be0c8', '#ff7a5a', '#ffe08a'], key: 0x4ae0d0, warm: 0xffa24a, mat: '#0d4f55' },
  amber: { wall: ['#2a1608', '#4a280e', '#150a04'], accent: '#ffcf5a', bokeh: ['#ffcf5a', '#ff8a3a', '#ff5e5e', '#ffe9a6'], key: 0xffb86a, warm: 0xff8a3a, mat: '#4a3216' },
};

function wallTexture(THREE, pal, seed) {
  const c = document.createElement('canvas'); c.width = 2048; c.height = 1024; const g = c.getContext('2d'), r = seeded(seed);
  const gr = g.createLinearGradient(0, 0, 2048, 1024); gr.addColorStop(0, pal.wall[0]); gr.addColorStop(0.5, pal.wall[1]); gr.addColorStop(1, pal.wall[2]); g.fillStyle = gr; g.fillRect(0, 0, 2048, 1024);
  g.fillStyle = 'rgba(0,0,0,0.42)'; for (let y = 30; y < 1024; y += 44) for (let x = 30; x < 2048; x += 44) { g.beginPath(); g.arc(x, y, 6, 0, 7); g.fill(); }      // the pegboard holes
  const tools = [pal.accent, '#ff5e5e', '#e9eef5', '#4ad8ff', '#ffd36a'];
  for (let i = 0; i < 46; i++) {                                                          // hung tools: handles, heads, pliers, wrenches
    const x = 60 + r() * 1930, y = 90 + r() * 560, col = tools[i % tools.length], k = 0.5 + r() * 0.9;
    g.globalAlpha = 0.5; g.fillStyle = 'rgba(0,0,0,0.6)'; g.beginPath(); g.roundRect(x + 10, y + 12, 22 * k, 120 * k, 8); g.fill(); g.beginPath(); g.roundRect(x - 16 * k, y + 102 * k, 74 * k, 34 * k, 10); g.fill();   // its shadow on the board
    const tg = g.createLinearGradient(x, 0, x + 22 * k, 0); tg.addColorStop(0, 'rgba(255,255,255,0.7)'); tg.addColorStop(0.35, col); tg.addColorStop(1, 'rgba(0,0,0,0.55)');
    g.globalAlpha = 0.85; g.fillStyle = tg; g.beginPath(); g.roundRect(x, y, 22 * k, 120 * k, 8); g.fill(); g.fillStyle = col; g.beginPath(); g.roundRect(x - 26 * k, y + 90 * k, 74 * k, 34 * k, 10); g.fill();
    g.fillStyle = 'rgba(255,255,255,0.35)'; g.fillRect(x - 24 * k, y + 92 * k, 70 * k, 5 * k);
    if (i % 3 === 0) { g.fillStyle = col; g.beginPath(); g.arc(x + 11 * k, y - 18 * k, 26 * k, 0, 7); g.fill(); g.fillStyle = 'rgba(0,0,0,0.5)'; g.beginPath(); g.arc(x + 11 * k, y - 18 * k, 9 * k, 0, 7); g.fill(); }
    g.globalAlpha = 1;
  }
  for (const y of [420, 700]) { g.fillStyle = 'rgba(8,10,16,0.85)'; g.fillRect(0, y, 2048, 22); g.fillStyle = 'rgba(255,255,255,0.12)'; g.fillRect(0, y, 2048, 3); }   // shelves
  const neon = g.createLinearGradient(0, 0, 2048, 0); neon.addColorStop(0, 'rgba(74,216,255,0)'); neon.addColorStop(0.5, 'rgba(74,216,255,0.9)'); neon.addColorStop(1, 'rgba(74,216,255,0)'); g.fillStyle = neon; g.fillRect(0, 850, 2048, 8);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

function bokehTexture(THREE) {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d'), gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,255,255,0.9)'); gr.addColorStop(0.7, 'rgba(255,255,255,0.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

// what a phone screen shows, drawn landscape and rotated into the portrait texture the phone model wants
function drawScreen(g, spec, k, t, pal) {
  g.save(); g.fillStyle = '#05070c'; g.fillRect(0, 0, 540, 1170); g.translate(540, 0); g.rotate(Math.PI / 2);          // now 1170 x 540, upright
  const type = spec.type || 'chart', col = spec.color || '#4ad8ff', W = 1170, H = 540;
  g.fillStyle = 'rgba(255,255,255,0.88)'; g.font = '600 30px Inter, Arial, sans-serif'; g.textBaseline = 'alphabetic';
  if (spec.title) g.fillText(String(spec.title), 44, 62);
  if (type === 'chart') {
    const x0 = 70, y0 = 110, w = W - 130, h = H - 190;
    g.strokeStyle = 'rgba(255,255,255,0.12)'; g.lineWidth = 2; for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(x0, y0 + h * i / 4); g.lineTo(x0 + w, y0 + h * i / 4); g.stroke(); }
    const vals = spec.values && spec.values.length ? spec.values : [spec.value ?? 60], cols = [col, '#ff5e8a', '#ffd36a'];
    vals.forEach((v, si) => {
      const lvl = clamp01(v / (spec.max || Math.max(...vals) * 1.25)), n = 48, shown = Math.floor(n * clamp01(k * 1.3));
      g.strokeStyle = cols[si % 3]; g.lineWidth = 5; g.lineJoin = 'round'; g.beginPath();
      for (let i = 0; i <= shown; i++) { const x = x0 + w * i / n, wob = Math.sin(i * 0.8 + si * 2) * 0.05 + Math.sin(i * 2.3 + si) * 0.025, y = y0 + h * (1 - clamp01(lvl + wob)); if (i === 0) g.moveTo(x, y); else g.lineTo(x, y); }
      g.stroke();
      g.fillStyle = cols[si % 3]; g.font = '600 24px Inter, Arial'; g.fillText(`${spec.labels ? spec.labels[si] : ''} ${v}`, x0 + 6 + si * 300, H - 36);
    });
  } else if (type === 'bars') {
    const vals = spec.values && spec.values.length ? spec.values : [spec.value ?? 60], mx = spec.max || Math.max(...vals) * 1.15;
    vals.slice(0, 4).forEach((v, i) => {
      const y = 120 + i * 100, w = (W - 340) * clamp01(v / mx) * clamp01(k * 1.4 - i * 0.12);
      g.fillStyle = 'rgba(255,255,255,0.08)'; g.fillRect(70, y, W - 340, 54); const gr = g.createLinearGradient(70, 0, 70 + w, 0); gr.addColorStop(0, '#7a5cff'); gr.addColorStop(1, col); g.fillStyle = gr; g.fillRect(70, y, Math.max(2, w), 54);
      g.fillStyle = '#fff'; g.font = '700 38px Inter, Arial'; g.fillText(String(Math.round(v * clamp01(k * 1.4 - i * 0.12))), W - 250, y + 42);
      if (spec.labels) { g.font = '500 24px Inter, Arial'; g.fillStyle = 'rgba(255,255,255,0.7)'; g.fillText(String(spec.labels[i] || ''), 70, y - 10); }
    });
  } else if (type === 'number') {
    const gr = g.createLinearGradient(0, 0, W, H); gr.addColorStop(0, '#0c2b4a'); gr.addColorStop(1, '#14507a'); g.fillStyle = gr; g.fillRect(0, 0, W, H);
    g.fillStyle = 'rgba(255,255,255,0.85)'; g.font = '600 34px Inter, Arial'; if (spec.label) g.fillText(String(spec.label), 56, 76);
    g.fillStyle = '#fff'; g.font = '900 230px Inter, Arial Black, Arial'; const v = spec.value ?? 0, shown = Math.round(v * ease(k) * 10) / 10;
    g.fillText(String(Number.isInteger(v) ? Math.round(shown) : shown.toFixed(1)), 56, 340); g.font = '700 54px Inter, Arial'; g.fillStyle = col; g.fillText(String(spec.unit || ''), 60, 430);
  } else if (type === 'heat') {
    const stops = ['#0a0620', '#46107a', '#c81c3c', '#ff7814', '#ffd73c', '#fffadc'];
    const hot = (cx, cy, rad, v) => { const gr = g.createRadialGradient(cx, cy, 0, cx, cy, rad); const i = Math.min(5, Math.floor(clamp01(v) * 5)); gr.addColorStop(0, stops[i]); gr.addColorStop(0.5, stops[Math.max(0, i - 2)]); gr.addColorStop(1, 'rgba(10,6,32,0)'); g.fillStyle = gr; g.fillRect(0, 0, W, H); };
    g.fillStyle = '#0a0620'; g.fillRect(0, 0, W, H); const p = clamp01((spec.value ?? 0.7) * ease(k)); hot(300, 200, 520, p * 0.95); hot(820, 330, 420, p * 0.6);
    g.fillStyle = '#fff'; g.font = '700 38px Inter, Arial'; if (spec.title) g.fillText(String(spec.title), 44, 62);
  }
  g.restore();
}

export async function buildBench(THREE, shot, { renderer, W, H }) {
  const pal = PAL[shot.palette] || PAL.blue, seed = shot.seed ?? 13, R = seeded(seed);
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#05080f');
  const std = (c, rough = 0.7, metal = 0) => new THREE.MeshStandardMaterial({ color: c, roughness: rough, metalness: metal });
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(36, 15), new THREE.MeshBasicMaterial({ map: wallTexture(THREE, pal, seed), toneMapped: false, color: new THREE.Color(1, 1, 1).multiplyScalar(0.85) }));
  wall.position.set(0, 3.2, -8); scene.add(wall);
  const table = new THREE.Mesh(new THREE.BoxGeometry(16, 0.5, 7), new THREE.MeshPhysicalMaterial({ color: '#1a1d24', roughness: 0.38, clearcoat: 0.5, clearcoatRoughness: 0.3, metalness: 0.2 }));
  table.position.set(0, -0.25, -1.2); table.receiveShadow = true; scene.add(table);
  const matC = document.createElement('canvas'); matC.width = matC.height = 512; { const g = matC.getContext('2d'); g.fillStyle = pal.mat; g.fillRect(0, 0, 512, 512); g.strokeStyle = 'rgba(255,255,255,0.18)'; g.lineWidth = 2; for (let i = 0; i <= 512; i += 32) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 512); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(512, i); g.stroke(); } }
  const matT = new THREE.CanvasTexture(matC); matT.colorSpace = THREE.SRGBColorSpace; matT.wrapS = matT.wrapT = THREE.RepeatWrapping; matT.repeat.set(4, 2);
  const mat = new THREE.Mesh(new THREE.PlaneGeometry(8, 3.6), new THREE.MeshStandardMaterial({ map: matT, roughness: 0.8 })); mat.rotation.x = -Math.PI / 2; mat.position.set(0, 0.004, -0.3); mat.receiveShadow = true; scene.add(mat);
  // props on the table: gamepads, a small fan, a mug, cones, so the out-of-focus foreground and background read as a workshop
  const cast = (m) => { m.castShadow = true; m.receiveShadow = true; return m; };
  for (const [x, z, rot, col] of [[-3.6, -0.6, 0.5, '#23262e'], [3.5, -0.2, -0.4, '#2c3038'], [-2.7, 1.2, 0.1, '#1b1e25']]) {
    const pad = new THREE.Group(); pad.position.set(x, 0.12, z); pad.rotation.y = rot;
    pad.add(cast(new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.22, 0.6), std(col, 0.5, 0.2)))); for (const s of [-0.38, 0.38]) { const grip = new THREE.Mesh(new THREE.SphereGeometry(0.22, 18, 12), std(col, 0.5, 0.2)); grip.position.set(s, -0.04, 0.22); grip.scale.set(1, 0.9, 1.3); pad.add(cast(grip)); }
    const btn = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 8), new THREE.MeshBasicMaterial({ color: pal.accent })); btn.position.set(0.3, 0.12, -0.05); pad.add(btn); scene.add(pad);
  }
  const fan = new THREE.Group(); fan.position.set(3.2, 0.0, -2.0);
  fan.add(cast(new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.5, 0.12, 32), std('#9aa3ad', 0.4, 0.8)))); const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 1.1, 12), std('#9aa3ad', 0.4, 0.8)); stem.position.y = 0.6; fan.add(cast(stem));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.07, 14, 40), std('#c9d0d8', 0.35, 0.8)); ring.position.y = 1.3; fan.add(cast(ring)); scene.add(fan);
  // the bokeh lights: additive discs in the room behind, thrown out of focus by the depth of field
  const bt = bokehTexture(THREE);
  for (let i = 0; i < 34; i++) {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: bt, color: pal.bokeh[i % 4], transparent: true, opacity: 0.35 + R() * 0.5, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    sp.position.set((R() - 0.5) * 16, 0.3 + R() * 5, -4.5 - R() * 3.2); const s = 0.25 + R() * 0.9; sp.scale.set(s, s, 1); scene.add(sp);
  }
  // phones on cone stands
  const pmx = await import('./phone_models.mjs');
  const screens = (Array.isArray(shot.screens) && shot.screens.length ? shot.screens : [{ type: 'chart', values: [60, 55] }, { type: 'number', value: 12.4 }]).slice(0, 3), n = screens.length;
  const colors = Array.isArray(shot.colors) && shot.colors.length ? shot.colors : ['Black', 'White', 'Sky Blue'];
  const env = new THREE.Scene(); env.add(new THREE.Mesh(new THREE.SphereGeometry(30, 16, 12), new THREE.MeshBasicMaterial({ color: '#0a0d14', side: THREE.BackSide })));
  const pnl = (w, h, c, s, pos) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(c).multiplyScalar(s), side: THREE.DoubleSide })); m.position.set(...pos); m.lookAt(0, 1, 0); env.add(m); };
  pnl(14, 3, '#cfe3ff', 4, [0, 8, 3]); pnl(2, 10, '#ff9d3a', 3, [-9, 2, 2]); pnl(2, 10, '#4ad8ff', 3, [9, 2, 2]);
  const pm = new THREE.PMREMGenerator(renderer), envRT = pm.fromScene(env, 0.02); pm.dispose(); scene.environment = envRT.texture; scene.environmentIntensity = 0.9;
  const holder = new THREE.Group(); scene.add(holder);
  const tex = [];
  const SP = shot.spacing ?? 2.75;
  screens.forEach((sp, i) => {
    const c = document.createElement('canvas'); c.width = 540; c.height = 1170; const g = c.getContext('2d'); drawScreen(g, sp, 1, 0, pal);
    const map = new THREE.CanvasTexture(c); map.colorSpace = THREE.SRGBColorSpace; map.anisotropy = 8; tex.push({ c, g, map, sp });
    const spec = pmx.resolvePhone({ preset: shot.phone || 'iphone 18 pro', color: colors[i % colors.length], wordmark: shot.wordmark });
    const model = pmx.buildPhoneModel(THREE, spec, { envMap: envRT.texture, shot: { ...shot, object: 'phone' }, screenMap: map });
    model.traverse((o) => { if (o.isMesh) { o.castShadow = true; } });
    const x = (i - (n - 1) / 2) * SP, g2 = new THREE.Group(); g2.add(model); g2.rotation.z = Math.PI / 2; g2.rotation.x = 0; g2.rotation.y = 0;
    const tilt = new THREE.Group(); tilt.add(g2); tilt.rotation.x = -0.16; tilt.position.set(x, 1.32, 0); holder.add(tilt);
    const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.42, 0.8, 40), std('#6d737c', 0.45, 0.6)); stand.position.set(x, 0.4, -0.1); cast(stand); holder.add(stand);
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.46, 0.46, 0.06, 40), std('#2a2e36', 0.4, 0.5)); cap.position.set(x, 0.82, -0.1); cap.rotation.x = -0.16; holder.add(cap);
  });
  // light
  const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(-3, 6, 5); key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 10; key.shadow.bias = -0.0004;
  Object.assign(key.shadow.camera, { left: -8, right: 8, top: 6, bottom: -4, near: 0.5, far: 24 }); scene.add(key);
  const rimA = new THREE.PointLight(pal.key, 38, 16, 1.6); rimA.position.set(-5, 2.5, -2.5); scene.add(rimA);
  const rimB = new THREE.PointLight(pal.warm, 30, 16, 1.6); rimB.position.set(5, 2.2, -2.5); scene.add(rimB);
  scene.add(new THREE.HemisphereLight(0x8aa4d6, 0x120d0a, 0.45));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.VSMShadowMap;
  const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { BokehPass }, { OutputPass }] = await Promise.all([
    import('/three/addons/postprocessing/EffectComposer.js'), import('/three/addons/postprocessing/RenderPass.js'), import('/three/addons/postprocessing/UnrealBloomPass.js'),
    import('/three/addons/postprocessing/BokehPass.js'), import('/three/addons/postprocessing/OutputPass.js')]);
  let composer = null, dof = null, focusAt = 6;
  return {
    scene,
    place(camera, k, t) {
      const c = shot.cam || {}, e = camE(k, 0.9, shot), cx = c.x || [-0.6, 0.6], dist = c.dist || [10.2, 8.9];
      camera.fov = shot.fov ?? 28; camera.aspect = W / H; camera.near = 0.1; camera.far = 100; camera.updateProjectionMatrix();
      camera.position.set(lerp(cx[0], cx[1], e), c.y ?? 1.9, lerp(dist[0], dist[1], e)); camera.up.set(0, 1, 0); camera.lookAt(lerp(cx[0], cx[1], e) * 0.3, 1.05, 0); camera.updateMatrixWorld(true);
      focusAt = camera.position.distanceTo(new THREE.Vector3(0, 1.4, 0));
      for (const s of tex) { drawScreen(s.g, s.sp, clamp01((t - 0.2) / 2.2), t, pal); s.map.needsUpdate = true; }
      fan.rotation.y = 0.5 + 0.1 * Math.sin(t * 0.5);
    },
    render(rend, camera) {
      if (!composer) {
        composer = new EffectComposer(rend, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 })); composer.setPixelRatio(1); composer.setSize(W, H);
        composer.addPass(new RenderPass(scene, camera));
        if (shot.dof !== false) { dof = new BokehPass(scene, camera, { focus: focusAt, aperture: shot.focus ?? 0.0012, maxblur: shot.maxblur ?? 0.012 }); composer.addPass(dof); }
        composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), shot.bloom ?? 0.32, 0.6, 0.85)); composer.addPass(new OutputPass());
      }
      if (dof) dof.uniforms.focus.value = focusAt;
      composer.render();
    },
  };
}
