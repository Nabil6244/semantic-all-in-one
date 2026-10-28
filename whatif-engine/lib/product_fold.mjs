// PRODUCT FOLD: a book-style foldable phone opening or closing on a hinge, for hinge and crease explainers: two metal halves with a glass inner screen, a
// hinge strip and a soft studio floor. The fold angle is a pure function of the time in the shot.
//   { id, start, end, kind: "product", object: "fold", tone: "#8fa3b5", angle: [180, 20] (degrees: 180 = flat open, 0 = closed), crease: true, wallpaper: "#4e9fc7",
//     cam: { az: [-0.6, 0.4], el: 0.28, dist: [5.2, 4.4] } }
// Same interface as buildProduct: { place(camera, k, t), render(renderer, camera) }.

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

function screenTexture(THREE, colour) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 1024; const g = c.getContext('2d'), col = new THREE.Color(colour);
  const rgb = (k, a = 1) => `rgba(${Math.round(255 * Math.min(1, col.r * k))},${Math.round(255 * Math.min(1, col.g * k))},${Math.round(255 * Math.min(1, col.b * k))},${a})`;
  const bg = g.createLinearGradient(0, 0, 1024, 1024); bg.addColorStop(0, rgb(0.5)); bg.addColorStop(1, rgb(1.0)); g.fillStyle = bg; g.fillRect(0, 0, 1024, 1024);
  for (let i = 0; i < 18; i++) { g.strokeStyle = i % 2 ? rgb(1.3, 0.35) : rgb(0.4, 0.35); g.lineWidth = 14; g.beginPath(); g.ellipse(512, 512, 40 + i * 28, 30 + i * 22, -0.4, 0, Math.PI * 2); g.stroke(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

function softSpot(THREE) {
  const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'), gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

export async function buildFold(THREE, shot, { renderer, W, H }) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#15171b');
  const tone = new THREE.Color(shot.tone || '#8fa3b5');
  const metal = new THREE.MeshPhysicalMaterial({ color: tone, metalness: 1, roughness: 0.28, envMapIntensity: 2.2 });
  const glass = new THREE.MeshPhysicalMaterial({ color: '#05070a', metalness: 0.1, roughness: 0.05, clearcoat: 1, envMapIntensity: 1.5 });
  const screen = new THREE.MeshBasicMaterial({ map: screenTexture(THREE, shot.wallpaper || '#4e9fc7'), toneMapped: false });
  // a studio reflection: a soft-box overhead and a cool strip
  const env = new THREE.Scene(); env.add(new THREE.Mesh(new THREE.SphereGeometry(20, 16, 12), new THREE.MeshBasicMaterial({ color: '#0a0b0e', side: THREE.BackSide })));
  const panel = (w, h, c, s, pos) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(c).multiplyScalar(s), side: THREE.DoubleSide })); m.position.set(...pos); m.lookAt(0, 0, 0); env.add(m); };
  panel(14, 2.4, '#ffffff', 5, [0, 7, 1]); panel(2, 12, '#bcd6ff', 3, [-8, 1, 2]); panel(1.4, 9, '#ffd9b0', 2, [8, 0.5, -3]);
  const pm = new THREE.PMREMGenerator(renderer), envRT = pm.fromScene(env, 0.02); pm.dispose(); scene.environment = envRT.texture;
  const half = (inner) => {
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.ExtrudeGeometry(rr(THREE, 0.96, 1.0, 0.1), { depth: 0.05, bevelEnabled: true, bevelSize: 0.01, bevelThickness: 0.01, curveSegments: 18 }), metal);
    body.geometry.translate(0, 0, -0.025); g.add(body);
    const sc = new THREE.Mesh(new THREE.ShapeGeometry(rr(THREE, 0.9, 0.94, 0.08), 18), screen);
    const uv = sc.geometry.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, (uv.getX(i) + 0.45) / 0.9, (uv.getY(i) + 0.47) / 0.94);
    sc.position.z = 0.0365; g.add(sc);
    const bezel = new THREE.Mesh(new THREE.ShapeGeometry(rr(THREE, 0.93, 0.97, 0.09), 18), glass); bezel.position.z = 0.0355; g.add(bezel);
    return g;
  };
  const fixed = new THREE.Group(), pivot = new THREE.Group(), top = half(), bottom = half();
  bottom.position.y = -0.5; fixed.add(bottom); top.position.y = 0.5; pivot.add(top); fixed.add(pivot); scene.add(fixed);
  // hinge strip + crease line on the screen
  const hinge = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.96, 24), metal); hinge.rotation.z = Math.PI / 2; hinge.position.z = -0.01; fixed.add(hinge);
  const crease = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.012), new THREE.MeshBasicMaterial({ color: '#000', transparent: true, opacity: 0.35 })); crease.position.z = 0.0375; fixed.add(crease);
  const spot = softSpot(THREE), shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.6), new THREE.MeshBasicMaterial({ color: '#000', alphaMap: spot, transparent: true, depthWrite: false, opacity: 0.8 }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = -1.02; scene.add(shadow);
  const key = new THREE.DirectionalLight(0xffffff, 1.6); key.position.set(-2, 4, 5); scene.add(key);
  const rim = new THREE.PointLight(0x9fd8ff, 6, 12, 1.6); rim.position.set(2.6, 1.4, -2); scene.add(rim);
  const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { OutputPass }] = await Promise.all([
    import('/three/addons/postprocessing/EffectComposer.js'), import('/three/addons/postprocessing/RenderPass.js'),
    import('/three/addons/postprocessing/UnrealBloomPass.js'), import('/three/addons/postprocessing/OutputPass.js')]);
  let composer = null;
  return {
    scene,
    place(camera, k, t) {
      const a = shot.angle || [180, 20], deg = lerp(a[0], a[1], linE(k)), fold = (180 - deg) * Math.PI / 180;   // 0 = flat open
      pivot.rotation.x = -fold; pivot.position.y = 0;
      // the hinge is at the pivot's bottom edge: the top half rotates about y = 0 of the pair (its own bottom edge)
      top.position.y = 0.5; pivot.position.set(0, 0, 0);
      fixed.position.y = lerp(0, 0.0, k); fixed.rotation.x = -0.5 * Math.min(1, fold / Math.PI) * 0.0;
      const c = shot.cam || {}, az = lerp((c.az || [-0.6, 0.4])[0], (c.az || [-0.6, 0.4])[1], camE(k, 0.6, shot)), el = c.el ?? 0.28, dist = lerp((c.dist || [3.9, 3.2])[0], (c.dist || [3.9, 3.2])[1], camE(k, 0.6, shot));
      camera.fov = 30; camera.aspect = W / H; camera.near = 0.1; camera.far = 80; camera.updateProjectionMatrix();
      camera.position.set(Math.sin(az) * Math.cos(el) * dist, 0.1 + Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist); camera.up.set(0, 1, 0); camera.lookAt(0, 0.1, 0);
      crease.material.opacity = shot.crease === false ? 0 : 0.15 + 0.5 * (1 - Math.min(1, fold / Math.PI));
    },
    render(rend, camera) {
      if (!composer) {
        composer = new EffectComposer(rend, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 })); composer.setPixelRatio(1); composer.setSize(W, H);
        composer.addPass(new RenderPass(scene, camera)); composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), shot.bloom ?? 0.2, 0.5, 0.9)); composer.addPass(new OutputPass());
      }
      composer.render();
    },
  };
}
