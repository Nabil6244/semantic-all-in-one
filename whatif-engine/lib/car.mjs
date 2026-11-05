// CAR: a code-built concept car on an auto-show turntable (Car Concept style). No model download: the body is a side profile
// extruded with rounded edges, a glass greenhouse, light bars, big wheels. Two looks:
//   studio    -- painted clear-coat body in a dark studio, reflective floor, a lit ring around the turntable, bloom on the light bars
//   blueprint -- engineering view: see-through body drawn as cyan edges over a navy grid, battery pack and motors glowing inside
//   { id, start, end, kind: "product", object: "car", body: "suv" | "truck" | "sedan" | "coupe" | "muscle", paint: "#ff6a1a",
//     look: "studio" | "blueprint", cam: { az0, az1, el0, el1, dist0, dist1, ty }, spin_deg_s, accent: "#ff6a1a", bloom: 0.5 }
// Pure function of the time inside the shot; the same interface as buildProduct: { place(camera, k, t), render(renderer, camera) }.

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const lerp = (a, b, k) => a + (b - a) * k;
const ease = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
// near-constant camera speed (a cut already starts the move; no slow start from rest), a little easing at the ends
const camE = (k) => { const kk = clamp01(k); return 0.8 * kk + 0.2 * ease(kk); };

// side profiles (metres, front = +x, ground = 0). belt = beltline, hood = hood front height, nose = front face top,
// glass = [windshield base x, roof front x, roof rear x, rear glass base x], roof = roof height, tail = rear deck height
export const BODIES = {
  suv:    { L: 4.85, W: 2.02, clear: 0.34, wheelR: 0.43, wb: 2.95, nose: 0.86, hood: 1.04, belt: 1.13, tail: 1.10, roof: 1.74, glass: [0.80, -0.10, -1.95, -2.24] },
  truck:  { L: 5.60, W: 2.06, clear: 0.40, wheelR: 0.46, wb: 3.55, nose: 0.98, hood: 1.18, belt: 1.24, tail: 1.18, roof: 1.92, glass: [1.05, 0.25, -0.65, -0.75] },
  sedan:  { L: 4.95, W: 1.92, clear: 0.20, wheelR: 0.38, wb: 2.98, nose: 0.62, hood: 0.80, belt: 0.92, tail: 0.94, roof: 1.42, glass: [0.95, 0.10, -1.05, -1.95] },
  coupe:  { L: 4.60, W: 1.96, clear: 0.16, wheelR: 0.37, wb: 2.70, nose: 0.52, hood: 0.70, belt: 0.84, tail: 0.86, roof: 1.24, glass: [0.70, -0.20, -0.90, -1.95] },
  muscle: { L: 4.80, W: 1.98, clear: 0.18, wheelR: 0.39, wb: 2.85, nose: 0.70, hood: 0.86, belt: 0.94, tail: 0.92, roof: 1.32, glass: [0.55, -0.35, -1.10, -1.75] },
};

/** The body's side profile as a THREE.Shape, with wheel arches cut out of the lower edge. */
export function bodyShape(THREE, b) {
  const s = new THREE.Shape(), F = b.L / 2, R = -b.L / 2, ax = b.wb / 2, ar = b.wheelR + 0.09, cy = b.wheelR, lo = b.clear;
  s.moveTo(R + 0.06, lo);
  s.lineTo(-ax - ar, lo); s.lineTo(-ax - ar, cy); s.absarc(-ax, cy, ar, Math.PI, 0, true); s.lineTo(-ax + ar, lo);
  s.lineTo(ax - ar, lo); s.lineTo(ax - ar, cy); s.absarc(ax, cy, ar, Math.PI, 0, true); s.lineTo(ax + ar, lo);
  s.lineTo(F - 0.08, lo + 0.02);
  s.quadraticCurveTo(F + 0.03, lo + 0.12, F, b.nose);                      // front bumper up to the nose
  s.quadraticCurveTo(F - 0.04, b.hood + 0.02, F - 0.22, b.hood);           // the nose rolls over into the hood
  s.lineTo(b.glass[0], b.belt - 0.01);                                      // hood up to the windshield base
  s.lineTo(R + 0.24, b.tail);                                               // beltline back to the rear deck
  s.quadraticCurveTo(R + 0.02, b.tail - 0.02, R, b.tail - 0.22);           // rear deck rolls down
  s.quadraticCurveTo(R - 0.03, lo + 0.2, R + 0.06, lo);
  return s;
}

/** The greenhouse (cabin glass) profile, sitting on the beltline. */
export function glassShape(THREE, b) {
  const [w0, r0, r1, w1] = b.glass, s = new THREE.Shape(), base = b.belt - 0.02;
  s.moveTo(w0, base);
  s.quadraticCurveTo(lerp(w0, r0, 0.55), lerp(base, b.roof, 0.85), r0, b.roof);
  s.lineTo(r1, b.roof - 0.01);
  s.quadraticCurveTo(lerp(r1, w1, 0.35), b.roof - 0.02, w1, base);
  s.lineTo(w0, base);
  return s;
}

function radial(THREE, inner, outer, size = 256) {
  const c = document.createElement('canvas'); c.width = c.height = size; const g = c.getContext('2d'), gr = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gr.addColorStop(0, inner); gr.addColorStop(0.55, inner.replace(/[\d.]+\)$/, (m) => `${parseFloat(m) * 0.45})`)); gr.addColorStop(1, outer); g.fillStyle = gr; g.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(c);
}

function extrude(THREE, shape, depth, bevel) {
  const geo = new THREE.ExtrudeGeometry(shape, { depth: Math.max(0.01, depth - 2 * bevel), bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel * 0.55, bevelSegments: 8, curveSegments: 32 });
  geo.translate(0, 0, -Math.max(0.01, depth - 2 * bevel) / 2); geo.computeVertexNormals(); return geo;
}

function wheel(THREE, b, mats) {
  const g = new THREE.Group(), R = b.wheelR, wd = 0.34;
  const tyre = new THREE.Mesh(new THREE.CylinderGeometry(R, R, wd, 64, 1), mats.tyre); tyre.rotation.x = Math.PI / 2; g.add(tyre);
  const side = new THREE.Mesh(new THREE.TorusGeometry(R * 0.86, R * 0.14, 16, 64), mats.tyre); side.position.z = wd / 2 - 0.02; g.add(side);
  const rim = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.72, R * 0.72, 0.05, 64), mats.rimDark); rim.rotation.x = Math.PI / 2; rim.position.z = wd / 2 - 0.01; g.add(rim);
  for (let i = 0; i < 6; i++) {                                              // six turbine spokes
    const sp = new THREE.Mesh(new THREE.BoxGeometry(R * 0.66, R * 0.11, 0.05), mats.rim);
    sp.geometry.translate(R * 0.33, 0, 0); sp.rotation.z = i * Math.PI / 3 + 0.18; sp.position.z = wd / 2 + 0.02; g.add(sp);
  }
  const ring = new THREE.Mesh(new THREE.TorusGeometry(R * 0.71, 0.018, 8, 64), mats.rim); ring.position.z = wd / 2 + 0.03; g.add(ring);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.13, R * 0.13, 0.06, 32), mats.accent); cap.rotation.x = Math.PI / 2; cap.position.z = wd / 2 + 0.04; g.add(cap);
  return g;
}

/** The car as a group (studio or blueprint materials) plus the parts the blueprint look lights up. */
export function buildCarModel(THREE, shot, envMap) {
  const b = BODIES[shot.body] || BODIES.suv, look = shot.look === 'blueprint' ? 'blueprint' : 'studio';
  const paint = new THREE.Color(shot.paint || '#ff6a1a'), accent = new THREE.Color(shot.accent || shot.paint || '#ff6a1a');
  const bp = look === 'blueprint', cyan = new THREE.Color('#5fd6ff');
  const mats = bp ? {
    body: new THREE.MeshBasicMaterial({ color: cyan, transparent: true, opacity: 0.11, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }),
    glass: new THREE.MeshBasicMaterial({ color: cyan, transparent: true, opacity: 0.03, depthWrite: false }),
    tyre: new THREE.MeshBasicMaterial({ color: cyan, transparent: true, opacity: 0.06, depthWrite: false }),
    rim: new THREE.MeshBasicMaterial({ color: cyan, transparent: true, opacity: 0.25 }), rimDark: new THREE.MeshBasicMaterial({ color: cyan, transparent: true, opacity: 0.05, depthWrite: false }),
    accent: new THREE.MeshBasicMaterial({ color: accent }), lightF: new THREE.MeshBasicMaterial({ color: cyan }), lightR: new THREE.MeshBasicMaterial({ color: cyan }),
    trim: new THREE.MeshBasicMaterial({ color: cyan, transparent: true, opacity: 0.05, depthWrite: false }),
  } : {
    body: new THREE.MeshPhysicalMaterial({ color: paint, metalness: 0.55, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.04, envMap, envMapIntensity: 1.2 }),
    glass: new THREE.MeshPhysicalMaterial({ color: '#05070a', metalness: 0.3, roughness: 0.04, clearcoat: 1, envMap, envMapIntensity: 1.6 }),
    tyre: new THREE.MeshStandardMaterial({ color: '#0d0e10', roughness: 0.85, metalness: 0 }),
    rim: new THREE.MeshStandardMaterial({ color: '#c9ced6', roughness: 0.22, metalness: 1, envMap }),
    rimDark: new THREE.MeshStandardMaterial({ color: '#1a1c20', roughness: 0.4, metalness: 0.8, envMap }),
    accent: new THREE.MeshStandardMaterial({ color: accent, roughness: 0.3, metalness: 0.4, emissive: accent, emissiveIntensity: 0.3 }),
    lightF: new THREE.MeshBasicMaterial({ color: new THREE.Color('#eaf6ff').multiplyScalar(3.0) }),
    lightR: new THREE.MeshBasicMaterial({ color: new THREE.Color('#ff1f2e').multiplyScalar(2.6) }),
    trim: new THREE.MeshPhysicalMaterial({ color: '#0b0c0f', metalness: 0.4, roughness: 0.25, clearcoat: 1, envMap }),
  };
  const car = new THREE.Group(), edges = [];
  const add = (geo, mat, edge = true) => { const m = new THREE.Mesh(geo, mat); car.add(m); if (edge) edges.push(m); return m; };
  const bodyGeo = extrude(THREE, bodyShape(THREE, b), b.W, 0.16); add(bodyGeo, mats.body);
  const glassGeo = extrude(THREE, glassShape(THREE, b), b.W * 0.84, 0.12); add(glassGeo, mats.glass);
  // a dark lower cladding band and a thin roof blade in the paint (the two-tone concept look)
  const clad = new THREE.Mesh(new THREE.BoxGeometry(b.L * 0.92, 0.07, b.W * 1.005), mats.trim); clad.position.set(0, b.clear + 0.1, 0); car.add(clad);
  const [, r0, r1] = b.glass;
  const blade = new THREE.Mesh(new THREE.BoxGeometry(Math.abs(r0 - r1) * 0.96, 0.035, b.W * 0.74), mats.body); blade.position.set((r0 + r1) / 2, b.roof + 0.06, 0); car.add(blade);
  // light bars: a full-width front bar under the hood edge and a full-width tail bar
  const F = b.L / 2, Rr = -b.L / 2;
  const fbar = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, b.W * 0.9), mats.lightF); fbar.position.set(F + 0.005, b.nose - 0.02, 0); car.add(fbar);
  for (const z of [-1, 1]) { const c = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.14, 0.03), mats.lightF); c.position.set(F - 0.005, b.nose - 0.08, z * b.W * 0.43); car.add(c); }
  const rbar = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.035, b.W * 0.92), mats.lightR); rbar.position.set(Rr - 0.04, b.tail - 0.16, 0); car.add(rbar);
  // wheels
  const wheels = [];
  for (const x of [-b.wb / 2, b.wb / 2]) for (const z of [-1, 1]) {
    const w = wheel(THREE, b, mats); w.position.set(x, b.wheelR, z * (b.W / 2 - 0.15)); if (z < 0) w.rotation.y = Math.PI; car.add(w); wheels.push(w);
  }
  // the blueprint's insides: the battery pack in the floor and a motor on each axle
  const inside = new THREE.Group();
  if (bp) {
    const packL = b.wb * 0.86, pack = new THREE.Mesh(new THREE.BoxGeometry(packL, 0.14, b.W * 0.78), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.55 }));
    pack.position.set(0, b.clear + 0.12, 0); inside.add(pack);
    const cells = new THREE.Group();
    for (let i = 0; i < 12; i++) for (let j = 0; j < 4; j++) {
      const c = new THREE.Mesh(new THREE.BoxGeometry(packL / 12 * 0.84, 0.15, b.W * 0.78 / 4 * 0.84), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.85 }));
      c.position.set(-packL / 2 + packL / 12 * (i + 0.5), b.clear + 0.12, -b.W * 0.39 + b.W * 0.78 / 4 * (j + 0.5)); cells.add(c);
    }
    inside.add(cells);
    for (const x of [-b.wb / 2, b.wb / 2]) {
      const m = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.5, 32), new THREE.MeshBasicMaterial({ color: '#ffffff', transparent: true, opacity: 0.85 }));
      m.rotation.x = Math.PI / 2; m.position.set(x, b.wheelR, 0); inside.add(m);
      const axle = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, b.W - 0.3, 12), new THREE.MeshBasicMaterial({ color: cyan })); axle.rotation.x = Math.PI / 2; axle.position.set(x, b.wheelR, 0); inside.add(axle);
    }
    car.add(inside);
    car.traverse((o) => { if (o.isMesh && o.parent !== cells && o.parent !== inside) edges.push(o); });
    const seen = new Set();
    for (const m of edges) {
      if (seen.has(m)) continue; seen.add(m);
      const l = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 14), new THREE.LineBasicMaterial({ color: cyan, transparent: true, opacity: 0.9 }));
      m.updateMatrix(); l.matrix.copy(m.matrix); l.matrixAutoUpdate = false; m.parent.add(l);
    }
  }
  car.traverse((o) => { if (o.isMesh) { o.castShadow = !bp; o.receiveShadow = false; } });
  return { car, b, wheels, inside };
}

export async function buildCar(THREE, shot, { renderer, W, H }) {
  const bp = shot.look === 'blueprint', accent = new THREE.Color(shot.accent || shot.paint || '#ff6a1a');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(bp ? '#04101f' : '#06070a');
  // ---- the studio's light, reflected in the paint (a dark room with long softboxes overhead and at the sides) --------------------
  const envScene = new THREE.Scene(); envScene.background = new THREE.Color('#020203');
  const box = (w, h, x, y, z, ry, rx, k) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color('#ffffff').multiplyScalar(k), side: THREE.DoubleSide })); m.position.set(x, y, z); m.rotation.set(rx, ry, 0); envScene.add(m); };
  box(14, 2.2, 0, 7, 0, 0, Math.PI / 2, 2.2);            // the long overhead strip that draws a line down the hood and roof
  box(10, 3, 0, 3, -9, 0, 0, 1.4); box(10, 3, 0, 3, 9, Math.PI, 0, 1.0);
  box(3, 5, -10, 3, 0, Math.PI / 2, 0, 0.9); box(3, 5, 10, 3, 0, -Math.PI / 2, 0, 0.9);
  const pm = new THREE.PMREMGenerator(renderer); const envRT = pm.fromScene(envScene, 0.02); pm.dispose();
  scene.environment = envRT.texture; scene.environmentIntensity = bp ? 0 : 1;
  // ---- the car --------------------------------------------------------------------------------------------------------------------
  const { car, b } = buildCarModel(THREE, shot, envRT.texture);
  const turn = new THREE.Group(); turn.add(car); scene.add(turn);
  // ---- floor, turntable, contact shadow ----------------------------------------------------------------------------------------
  if (bp) {
    const grid = new THREE.GridHelper(40, 80, '#1d6a92', '#0e3350'); grid.material.transparent = true; grid.material.opacity = 0.75; scene.add(grid);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(9, 4), new THREE.MeshBasicMaterial({ map: radial(THREE, 'rgba(60,170,230,0.22)', 'rgba(0,0,0,0)'), transparent: true, depthWrite: false }));
    ground.rotation.x = -Math.PI / 2; ground.position.y = 0.002; scene.add(ground);
  } else {
    const floor = new THREE.Mesh(new THREE.CircleGeometry(30, 96), new THREE.MeshPhysicalMaterial({ color: '#050608', roughness: 0.9, metalness: 0.0, envMapIntensity: 0.06 }));
    floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(b.L * 0.66, 128), new THREE.MeshPhysicalMaterial({ color: '#0c0d11', roughness: 0.55, metalness: 0.0, clearcoat: 0.25, clearcoatRoughness: 0.5, envMapIntensity: 0.12 }));
    disc.rotation.x = -Math.PI / 2; disc.position.y = 0.004; disc.receiveShadow = true; scene.add(disc);
    const ring = new THREE.Mesh(new THREE.RingGeometry(b.L * 0.66, b.L * 0.66 + 0.05, 160), new THREE.MeshBasicMaterial({ color: accent.clone().multiplyScalar(1.9) }));
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.008; scene.add(ring);
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(b.L * 1.25, b.W * 1.6), new THREE.MeshBasicMaterial({ map: radial(THREE, 'rgba(0,0,0,0.92)', 'rgba(0,0,0,0)'), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.01; turn.add(shadow);
    // a soft pool of light on the floor around the car
    const pool = new THREE.Mesh(new THREE.PlaneGeometry(18, 18), new THREE.MeshBasicMaterial({ map: radial(THREE, 'rgba(120,130,150,0.07)', 'rgba(0,0,0,0)'), transparent: true, depthWrite: false }));
    pool.rotation.x = -Math.PI / 2; pool.position.y = 0.006; scene.add(pool);
    // ---- lights ---------------------------------------------------------------------------------------------------------------
    const key = new THREE.SpotLight('#fff4e6', 70, 30, 0.5, 0.8, 1.6); key.position.set(2, 9, 4); key.target.position.set(0, 0.6, 0);
    key.castShadow = true; key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0003; key.shadow.radius = 8; scene.add(key, key.target);
    const rim = new THREE.DirectionalLight('#9fd0ff', 1.1); rim.position.set(-6, 3, -6); scene.add(rim);
    const kick = new THREE.DirectionalLight(accent, 0.6); kick.position.set(6, 1, -4); scene.add(kick);
    scene.add(new THREE.HemisphereLight('#6d7c94', '#0a0b0e', 0.35));
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  }
  // ---- post: bloom on the light bars and the ring ------------------------------------------------------------------------------
  let composer = null;
  try {
    const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { OutputPass }] = await Promise.all([
      import('/three/addons/postprocessing/EffectComposer.js'), import('/three/addons/postprocessing/RenderPass.js'),
      import('/three/addons/postprocessing/UnrealBloomPass.js'), import('/three/addons/postprocessing/OutputPass.js')]);
    composer = { EffectComposer, RenderPass, UnrealBloomPass, OutputPass, c: null };
  } catch (err) { console.warn(`car: bloom not used (${err && err.message})`); }

  const c = shot.cam || {};
  const ty = c.ty ?? b.roof * 0.45;
  return {
    scene,
    place(camera, k, t) {
      const e = camE(k);
      const az = lerp(c.az0 ?? 35, c.az1 ?? 60, e) * Math.PI / 180, el = lerp(c.el0 ?? 8, c.el1 ?? (c.el0 ?? 8), e) * Math.PI / 180;
      const dist = lerp(c.dist0 ?? 9.5, c.dist1 ?? 8.6, e);
      camera.fov = c.fov ?? 30; camera.updateProjectionMatrix(); camera.up.set(0, 1, 0);
      camera.position.set(Math.sin(az) * Math.cos(el) * dist, ty + Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist);
      camera.lookAt(c.tx ?? 0, ty, 0);
      if (shot.frame_x) camera.setViewOffset(W, H, -shot.frame_x * W, 0, W, H); else camera.clearViewOffset();
      turn.rotation.y = ((shot.spin_deg_s ?? 0) * t) * Math.PI / 180;
    },
    render(renderer, camera) {
      if (composer && !composer.c) {
        const { EffectComposer, RenderPass, UnrealBloomPass, OutputPass } = composer;
        const ec = new EffectComposer(renderer); ec.setSize(W, H);
        ec.addPass(new RenderPass(scene, camera));
        ec.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), shot.bloom ?? (bp ? 0.55 : 0.35), 0.4, bp ? 0.25 : 1.6));
        ec.addPass(new OutputPass()); composer.c = ec;
      }
      if (composer && composer.c) { composer.c.passes[0].camera = camera; composer.c.render(); } else renderer.render(scene, camera);
    },
  };
}
