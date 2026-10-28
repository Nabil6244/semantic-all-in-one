// PRODUCT X-RAY: the inside of a phone as a glowing technical render (the review's teardown and CT shots): a glass shell, the battery, the board,
// the camera stack, the speaker and the port drawn as dark parts with bright edges, a scan line sweeping up the phone, an optional explode (the parts
// separate along the depth axis, back to front) and labelled dimension lines such as "3.05 mm".
//   { id, start, end, kind: "product", object: "xray", tone: "#3ac8ff", explode: [0, 1], scan: true, dims: [{ from: [-0.4, 0.9], to: [0.4, 0.9], text: "77.6 mm" }],
//     cam: { az: [-0.5, 0.35], el: 0.25, dist: [4.6, 3.9] }, bloom: 0.9 }
// A pure function of the time inside the shot; the same interface as buildProduct: { place(camera, k, t), render(renderer, camera) }.

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const lerp = (a, b, k) => a + (b - a) * k;
const ease = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
// camera travel inside one shot: near-constant speed (a hard cut already starts the next shot, so no slow start from rest) and a shorter move
// (the reference trailers move about a tenth as far per frame as a full smoothstep). shot.travel 0..1 scales the move (default `tr`); 1 = as authored.
const camE = (k, tr = 0.5, shot = null) => { const kk = clamp01(k), lin = 0.75 * kk + 0.25 * ease(kk), t = shot && shot.travel != null ? shot.travel : tr; return 0.5 + (lin - 0.5) * t; };
const linE = (k) => { const kk = clamp01(k); return 0.75 * kk + 0.25 * ease(kk); };

function rr(THREE, w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r); s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

function label(THREE, text, colour = '#ffffff') {
  const c = document.createElement('canvas'); c.width = 512; c.height = 128; const g = c.getContext('2d');
  g.font = '700 64px TMSans, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = colour; g.shadowColor = 'rgba(0,0,0,0.8)'; g.shadowBlur = 8;
  g.fillText(String(text), 256, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthTest: false, toneMapped: false }));
  sp.scale.set(0.8, 0.2, 1); sp.renderOrder = 20; return sp;
}

export async function buildXray(THREE, shot, { renderer, W, H }) {
  const tone = new THREE.Color(shot.tone || '#3ac8ff'), warm = new THREE.Color('#ffb45a');
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#03060a');
  const grid = new THREE.GridHelper(14, 56, 0x16324a, 0x0b1a28); grid.position.y = -1.25; scene.add(grid);
  const holder = new THREE.Group(); scene.add(holder);
  const lines = [], parts = [];
  const edgeMat = (c, o = 0.9) => new THREE.LineBasicMaterial({ color: c, transparent: true, opacity: o, toneMapped: false });
  // the glass shell: a faint body and a bright outline
  const shell = new THREE.Mesh(new THREE.ExtrudeGeometry(rr(THREE, 0.96, 2.0, 0.14), { depth: 0.09, bevelEnabled: true, bevelSize: 0.012, bevelThickness: 0.012, curveSegments: 20 }),
    new THREE.MeshPhysicalMaterial({ color: tone.clone().multiplyScalar(0.5), transparent: true, opacity: 0.1, roughness: 0.1, metalness: 0.2, side: THREE.DoubleSide, depthWrite: false }));
  shell.geometry.translate(0, 0, -0.045); holder.add(shell);
  const shellEdge = new THREE.LineSegments(new THREE.EdgesGeometry(shell.geometry, 25), edgeMat(tone, 0.85)); holder.add(shellEdge); lines.push(shellEdge);
  // parts: [name, w, h, d, x, y, z, colour, explode distance]
  const defs = [
    ['battery', 0.78, 1.0, 0.045, 0, -0.38, -0.015, warm, 0.35], ['board', 0.78, 0.55, 0.03, 0, 0.62, 0.02, tone, 0.12],
    ['camera_a', 0.2, 0.2, 0.06, -0.22, 0.78, -0.035, tone, 0.55], ['camera_b', 0.2, 0.2, 0.06, -0.22, 0.52, -0.035, tone, 0.55], ['camera_c', 0.13, 0.25, 0.05, 0.1, 0.65, -0.03, tone, 0.5],
    ['chip', 0.22, 0.22, 0.028, 0.22, 0.62, 0.05, new THREE.Color('#ffffff'), 0.2], ['speaker', 0.4, 0.07, 0.04, 0, -0.93, 0.0, tone, 0.25], ['port', 0.14, 0.04, 0.03, 0, -0.97, -0.02, tone, 0.3],
    ['frame_l', 0.04, 1.8, 0.06, -0.45, 0, 0.0, tone, 0.1], ['frame_r', 0.04, 1.8, 0.06, 0.45, 0, 0.0, tone, 0.1],
  ];
  for (const [name, w, h, d, x, y, z, col, ex] of defs) {
    const g = name.startsWith('camera_a') || name.startsWith('camera_b') ? new THREE.CylinderGeometry(w / 2, w / 2, d, 40) : new THREE.BoxGeometry(w, h, d);
    if (g.type === 'CylinderGeometry') g.rotateX(Math.PI / 2);
    const mesh = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: '#0a1118', roughness: 0.5, metalness: 0.7, emissive: col, emissiveIntensity: 0.08 }));
    const edge = new THREE.LineSegments(new THREE.EdgesGeometry(g, 20), edgeMat(col, 0.95));
    const grp = new THREE.Group(); grp.add(mesh, edge); grp.position.set(x, y, z); grp.userData = { z0: z, ex, mesh, edge, y };
    holder.add(grp); parts.push(grp); lines.push(edge);
  }
  for (const d of shot.dims || []) {   // dimension lines: a line with two ticks and a label
    const [x0, y0] = d.from, [x1, y1] = d.to, g = new THREE.Group();
    const pts = [new THREE.Vector3(x0, y0, 0.12), new THREE.Vector3(x1, y1, 0.12)];
    const tick = (p, dx, dy) => [p.clone().add(new THREE.Vector3(-dx, -dy, 0)), p.clone().add(new THREE.Vector3(dx, dy, 0))];
    const ang = Math.atan2(y1 - y0, x1 - x0), nx = -Math.sin(ang) * 0.05, ny = Math.cos(ang) * 0.05;
    const seg = [...pts, ...tick(pts[0], nx, ny), ...tick(pts[1], nx, ny)];
    g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(seg), edgeMat(0xffffff, 0.95)));
    const tx = label(THREE, d.text); tx.position.set((x0 + x1) / 2, (y0 + y1) / 2 + 0.12, 0.14); g.add(tx);
    g.userData.delay = d.delay ?? 0.5; holder.add(g); parts.push(g);
  }
  // the scan line: a bright plane sweeping up
  const scanMat = new THREE.MeshBasicMaterial({ color: tone, transparent: true, opacity: 0.0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  const scan = new THREE.Mesh(new THREE.PlaneGeometry(1.4, 0.03), scanMat); scan.position.z = 0.1; holder.add(scan);
  const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { OutputPass }] = await Promise.all([
    import('/three/addons/postprocessing/EffectComposer.js'), import('/three/addons/postprocessing/RenderPass.js'),
    import('/three/addons/postprocessing/UnrealBloomPass.js'), import('/three/addons/postprocessing/OutputPass.js')]);
  scene.add(new THREE.AmbientLight(0x88aaff, 0.5)); const key = new THREE.DirectionalLight(0xffffff, 1.2); key.position.set(-2, 3, 4); scene.add(key);
  let composer = null;
  return {
    scene,
    place(camera, k, t) {
      const c = shot.cam || {}, az = lerp((c.az || [-0.5, 0.35])[0], (c.az || [-0.5, 0.35])[1], camE(k, 0.6, shot)), el = c.el ?? 0.25, dist = lerp((c.dist || [4.6, 3.9])[0], (c.dist || [4.6, 3.9])[1], camE(k, 0.6, shot));
      camera.fov = 30; camera.aspect = W / H; camera.near = 0.1; camera.far = 80; camera.updateProjectionMatrix();
      camera.position.set(Math.sin(az) * Math.cos(el) * dist, Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist); camera.up.set(0, 1, 0); camera.lookAt(0, -0.05, 0);
      holder.rotation.set(0, 0, 0);
      const ex = shot.explode || [0, 0], e = lerp(ex[0], ex[1], linE(k));
      const sy = lerp(-1.1, 1.1, (k * 1.4) % 1);
      for (const p of parts) {
        if (p.userData.mesh) {
          p.position.z = p.userData.z0 + p.userData.ex * e;
          const near = shot.scan === false ? 0 : Math.max(0, 1 - Math.abs(p.userData.y - sy) * 2.2);
          p.userData.edge.material.opacity = 0.55 + 0.45 * near + 0.1 * Math.sin(t * 3);
        } else p.visible = k * (shot.end - shot.start || 4) > (p.userData.delay ?? 0.5);
      }
      scan.position.y = sy; scanMat.opacity = shot.scan === false ? 0 : 0.55;
    },
    render(rend, camera) {
      if (!composer) {
        composer = new EffectComposer(rend, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 })); composer.setPixelRatio(1); composer.setSize(W, H);
        composer.addPass(new RenderPass(scene, camera)); composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), shot.bloom ?? 0.9, 0.6, 0.2)); composer.addPass(new OutputPass());
      }
      composer.render();
    },
  };
}
