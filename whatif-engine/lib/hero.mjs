// HERO scenes: deliberately composed 3D scenes for the shots the reference builds by hand (a lander on the plain, a descent under a
// parachute). Procedural, deterministic and free: the same shot always gives the same frame, and its composition is data
// (shot.cam) -- craft size, horizon height, position, camera drift -- measured from the reference (V1 0:01.5: the lander 26 % of the
// frame wide and centred, horizon at 70 % of the frame height, warm orange sky, dark ground with scattered thin slabs of rock).
//   shot: { kind: "hero", scene: "venera_ground" | "venera_descent" | "cloud_airship" | "ship_engine" | "blackhole_*" (lib/blackhole.mjs), cam: { size, horizon, x, hover, fov, az, drift } }
import { blackholeScene, BLACKHOLE_SCENES } from './blackhole.mjs';
const rnd = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

export function skyMaterial(THREE, top, horizon) {
  return new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false,
    uniforms: { top: { value: new THREE.Color(top) }, hor: { value: new THREE.Color(horizon) } },
    vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: 'uniform vec3 top; uniform vec3 hor; varying vec3 vP; void main(){ float e = max(vP.y, 0.0); float m = pow(e, 0.55); float band = exp(-pow(vP.y * 7.0, 2.0)) * 0.12; gl_FragColor = vec4(mix(hor, top, m) + band, 1.0); }',
  });
}

function slabTexture(THREE) {
  const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d');
  g.fillStyle = '#6d5a48'; g.fillRect(0, 0, 64, 64);
  g.strokeStyle = 'rgba(40,28,20,0.5)'; g.lineWidth = 1;
  for (let i = 0; i <= 64; i += 8) { g.beginPath(); g.moveTo(i, 0); g.lineTo(i, 64); g.stroke(); g.beginPath(); g.moveTo(0, i); g.lineTo(64, i); g.stroke(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

/** The Venera lander as the reference draws it: a gridded sphere, a wide flat dish round it, a coil antenna on top, a ring base on struts,
 *  a bent soil-probe arm on one side. Units: the dish radius is 2.2. */
export function venera(THREE) {
  const g = new THREE.Group();
  const tan = new THREE.MeshStandardMaterial({ map: slabTexture(THREE), color: 0xd8b88c, roughness: 0.9, metalness: 0.05 });
  const bronze = new THREE.MeshStandardMaterial({ color: 0x7a5a3c, roughness: 0.7, metalness: 0.25 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x2b211b, roughness: 0.9 });
  const ball = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 32), tan); ball.position.y = 1.7; g.add(ball);
  const dish = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 1.95, 0.1, 64), bronze); dish.position.y = 2.15; g.add(dish);
  const rim = new THREE.Mesh(new THREE.TorusGeometry(2.17, 0.035, 8, 64), bronze); rim.rotation.x = Math.PI / 2; rim.position.y = 2.2; g.add(rim);
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.14, 0.45, 16), bronze); neck.position.y = 2.55; g.add(neck);
  const pts = []; for (let i = 0; i <= 120; i++) { const a = i / 120 * Math.PI * 2 * 5; pts.push(new THREE.Vector3(Math.cos(a) * 0.2, 2.75 + i / 120 * 0.95, Math.sin(a) * 0.2)); }
  g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 160, 0.022, 6, false), dark));
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.1, 0.3, 64), tan); ring.position.y = 0.2; g.add(ring);
  const lip = new THREE.Mesh(new THREE.CylinderGeometry(2.1, 1.9, 0.1, 64), bronze); lip.position.y = 0.0; g.add(lip);
  for (let i = 0; i < 8; i++) {
    const a = i / 8 * Math.PI * 2, r0 = 1.55, r1 = 0.55;
    const from = new THREE.Vector3(Math.cos(a) * r0, 0.34, Math.sin(a) * r0), to = new THREE.Vector3(Math.cos(a) * r1, 1.35, Math.sin(a) * r1);
    const len = from.distanceTo(to), s = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, len, 6), bronze);
    s.position.copy(from).add(to).multiplyScalar(0.5); s.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), to.clone().sub(from).normalize()); g.add(s);
  }
  const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 2.6, 8), bronze); arm.position.set(2.15, 1.55, 0.1); arm.rotation.z = -0.28; g.add(arm);
  const hook = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.5, 8), bronze); hook.position.set(2.45, 2.8, 0.1); hook.rotation.z = 1.2; g.add(hook);
  const pad = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.2, 0.18), dark); pad.position.set(2.02, 0.3, 0.1); g.add(pad);
  const eye = new THREE.Mesh(new THREE.SphereGeometry(0.2, 16, 12), dark); eye.position.set(0.95, 1.55, 0.35); g.add(eye);
  return g;
}

function ground(THREE, seed) {
  const g = new THREE.Group(), r = rnd(seed);
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(500, 500, 1, 1), new THREE.MeshStandardMaterial({ color: 0x3d2e24, roughness: 1 }));
  plane.rotation.x = -Math.PI / 2; g.add(plane);
  const mat = new THREE.MeshStandardMaterial({ color: 0x2a2019, roughness: 1 });
  const slab = new THREE.BoxGeometry(1, 0.06, 1);
  const inst = new THREE.InstancedMesh(slab, mat, 900), m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  for (let i = 0; i < 900; i++) {
    const dist = 2 + Math.pow(r(), 1.6) * 90, a = r() * Math.PI * 2, w = 0.2 + r() * 0.9 * (1 + dist * 0.03), d = 0.08 + r() * 0.3 * (1 + dist * 0.03);
    e.set((r() - 0.5) * 0.3, r() * Math.PI, (r() - 0.5) * 0.25); q.setFromEuler(e);
    m.compose(new THREE.Vector3(Math.cos(a) * dist, 0.03, Math.sin(a) * dist - 4), q, new THREE.Vector3(w, 1 + r() * 2, d)); inst.setMatrixAt(i, m);
  }
  g.add(inst);
  return g;
}

function shadowDisc(THREE) {
  const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
  const grd = x.createRadialGradient(64, 64, 4, 64, 64, 62); grd.addColorStop(0, 'rgba(0,0,0,0.7)'); grd.addColorStop(1, 'rgba(0,0,0,0)');
  x.fillStyle = grd; x.fillRect(0, 0, 128, 128);
  const t = new THREE.CanvasTexture(c);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; return m;
}

function parachute(THREE) {
  const g = new THREE.Group();
  const c = document.createElement('canvas'); c.width = 512; c.height = 8; const x = c.getContext('2d');
  for (let i = 0; i < 16; i++) { x.fillStyle = i % 2 ? '#e6d6bb' : '#c0532c'; x.fillRect(i * 32, 0, 32, 8); }
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.wrapS = THREE.RepeatWrapping;
  const dome = new THREE.Mesh(new THREE.SphereGeometry(3.4, 48, 16, 0, Math.PI * 2, 0, Math.PI * 0.5), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, side: THREE.DoubleSide }));
  dome.scale.y = 0.55; dome.position.y = 7.4; g.add(dome);
  const lines = new THREE.Group(), mat = new THREE.LineBasicMaterial({ color: 0xe9dcc4, transparent: true, opacity: 0.7 });
  for (let i = 0; i < 16; i++) {
    const a = i / 16 * Math.PI * 2;
    lines.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(Math.cos(a) * 3.4, 7.4, Math.sin(a) * 3.4), new THREE.Vector3(Math.cos(a) * 0.5, 3.2, Math.sin(a) * 0.5)]), mat));
  }
  g.add(lines);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.9, 32, 24), new THREE.MeshStandardMaterial({ color: 0xcdb590, roughness: 0.85 })); cap.position.y = 2.4; g.add(cap);
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(1.4, 1.5, 0.22, 48), new THREE.MeshStandardMaterial({ color: 0x6f5238, roughness: 0.7, metalness: 0.2 })); ring.position.y = 1.5; g.add(ring);
  return g;
}


/** An airship in profile: a long cream envelope with ribs, three tail fins and a gondola. Length 9 units along x. */
export function airship(THREE) {
  const g = new THREE.Group();
  const skin = new THREE.MeshStandardMaterial({ color: 0xefe6d2, roughness: 0.85 }), dark = new THREE.MeshStandardMaterial({ color: 0x6b5a48, roughness: 0.8 });
  const body = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), skin); body.scale.set(4.5, 1.35, 1.35); g.add(body);
  for (let i = -3; i <= 3; i++) {
    const x = i * 1.15, rr = 1.35 * Math.sqrt(Math.max(0.02, 1 - (x / 4.5) ** 2));
    const rib = new THREE.Mesh(new THREE.TorusGeometry(rr, 0.02, 6, 40), dark); rib.position.x = x; rib.rotation.y = Math.PI / 2; g.add(rib);
  }
  for (let k = 0; k < 3; k++) {
    const fin = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.05, 1.1), skin); fin.position.set(-4.1, 0, 0); fin.rotation.x = k * Math.PI / 3; g.add(fin);
  }
  const gond = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.45, 0.55), dark); gond.position.set(0.3, -1.65, 0); g.add(gond);
  for (const x of [-0.2, 0.8]) { const st = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.5, 6), dark); st.position.set(x, -1.35, 0); g.add(st); }
  return g;
}

function cloudSea(THREE, seed) {
  const r = rnd(seed), puff = new THREE.IcosahedronGeometry(1, 2);
  const mat = new THREE.MeshStandardMaterial({ color: 0xf3e6cb, roughness: 1 }), inst = new THREE.InstancedMesh(puff, mat, 1400), m = new THREE.Matrix4();
  for (let i = 0; i < 1400; i++) {
    const dist = 3 + Math.pow(r(), 1.3) * 150, a = r() * Math.PI * 2, s = 2 + r() * 5 * (1 + dist * 0.025);
    m.compose(new THREE.Vector3(Math.cos(a) * dist, -2.2 + r() * 0.8, Math.sin(a) * dist - 10), new THREE.Quaternion(), new THREE.Vector3(s, s * 0.45, s));
    inst.setMatrixAt(i, m);
  }
  return inst;
}

/** The constant-thrust ship of V3: a black nose, a white-hot drive and its glow, a long truss, a ring and four gold tanks. Axis along x. */
export function driveShip(THREE) {
  const g = new THREE.Group();
  const gold = new THREE.MeshStandardMaterial({ color: 0xc9a24a, roughness: 0.4, metalness: 0.85 }), steel = new THREE.MeshStandardMaterial({ color: 0xc8ccd2, roughness: 0.35, metalness: 0.9 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1a1b1f, roughness: 0.6, metalness: 0.4 }), hot = new THREE.MeshBasicMaterial({ color: 0xfff6e0 });
  const nose = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 24), dark); nose.scale.set(0.9, 1.1, 1.1); nose.position.x = -4.2; g.add(nose);
  const nozzle = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.75, 0.9, 32), hot); nozzle.rotation.z = Math.PI / 2; nozzle.position.x = -3.1; g.add(nozzle);
  const truss = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 6.2, 12), dark); truss.rotation.z = Math.PI / 2; truss.position.x = 0.2; g.add(truss);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1.05, 0.13, 12, 48), steel); ring.rotation.y = Math.PI / 2; ring.position.x = 2.3; g.add(ring);
  for (let i = 0; i < 4; i++) {
    const a = i / 4 * Math.PI * 2 + Math.PI / 4, tank = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 1.7, 24), gold);
    tank.rotation.z = Math.PI / 2; tank.position.set(2.7, Math.cos(a) * 0.82, Math.sin(a) * 0.82); g.add(tank);
  }
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.45, 1.3, 24), steel); cone.rotation.z = -Math.PI / 2; cone.position.x = 4.1; g.add(cone);
  const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d');
  const grd = x.createRadialGradient(64, 64, 0, 64, 64, 64); grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.25, 'rgba(200,230,255,0.7)'); grd.addColorStop(1, 'rgba(120,180,255,0)');
  x.fillStyle = grd; x.fillRect(0, 0, 128, 128);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), blending: THREE.AdditiveBlending, depthWrite: false })); glow.scale.set(4.2, 4.2, 1); glow.position.x = -3.6; g.add(glow);
  return g;
}

/** -> { scene, place(camera, t01, W, H, shot) } for a hero scene. */
export function buildHero(THREE, shot, { stars } = {}) {
  if (BLACKHOLE_SCENES.includes(shot.scene)) return blackholeScene(THREE, shot);
  const scene = new THREE.Scene(), cam = shot.cam || {};
  scene.background = new THREE.Color(0xe0a868);
  scene.fog = new THREE.Fog(cam.fog ?? 0xc8955a, cam.fog_near ?? 25, cam.fog_far ?? 170);
  const sun = new THREE.DirectionalLight(0xffd9a6, 2.2); sun.position.set(-6, 5, 7); scene.add(sun);
  scene.add(new THREE.HemisphereLight(0xe8a860, 0x2a1c14, 1.0));
  const sky = new THREE.Mesh(new THREE.SphereGeometry(400, 32, 16), skyMaterial(THREE, cam.sky_top ?? 0xc07a3a, cam.sky_horizon ?? 0xedb97a)); scene.add(sky);
  if (shot.scene === 'ship_engine') {
    scene.background = new THREE.Color(0x020306); scene.fog = null; scene.remove(sky);
    if (stars) scene.add(stars(cam.seed ?? 9));
    const ship = driveShip(THREE); scene.add(ship); sun.color.set(0xfff3e0); sun.intensity = 2.6; sun.position.set(4, 3, 6);
    return { scene, place(camera, k, W, H) {
      const t = k * (shot.end - shot.start), fov = cam.fov ?? 32, size = cam.size ?? 0.5, aspect = W / H;
      camera.fov = fov; camera.aspect = aspect; camera.updateProjectionMatrix();
      const D = 9.5 / (size * 2 * Math.tan(fov * Math.PI / 360) * aspect), az = ((cam.az ?? -28) + 10 * k) * Math.PI / 180, el = (cam.el ?? 14) * Math.PI / 180;
      ship.rotation.x = t * 0.02;
      camera.position.set(Math.sin(az) * Math.cos(el) * D, Math.sin(el) * D, Math.cos(az) * Math.cos(el) * D); camera.lookAt(0, 0, 0);
      camera.setViewOffset(W, H, (0.5 - (cam.x ?? 0.5)) * W, 0, W, H);
    } };
  }
  if (shot.scene === 'cloud_airship') {
    sky.material = skyMaterial(THREE, cam.sky_top ?? 0xd88a3c, cam.sky_horizon ?? 0xf2d9a8); scene.fog.color.set(0xf0d6a4); scene.fog.near = 30; scene.fog.far = 190;
    scene.add(cloudSea(THREE, cam.seed ?? 5));
    const ship = airship(THREE); scene.add(ship);
    return { scene, place(camera, k, W, H) {
      const t = k * (shot.end - shot.start), fov = cam.fov ?? 30, size = cam.size ?? 0.34, aspect = W / H, horizon = cam.horizon ?? 0.62;
      camera.fov = fov; camera.aspect = aspect; camera.updateProjectionMatrix();
      ship.position.set(Math.sin(t * 0.2) * 0.2, 1.4 + Math.sin(t * 0.7) * 0.08, 0); ship.rotation.y = cam.turn ?? 0.12; ship.rotation.z = Math.sin(t * 0.5) * 0.01;
      const D = 9.0 / (size * 2 * Math.tan(fov * Math.PI / 360) * aspect), up = Math.atan((horizon - 0.5) * 2 * Math.tan(fov * Math.PI / 360)), drift = 1 - 0.04 * k;
      camera.position.set((cam.az ?? 0) * 0.02 * D, 1.6, D * drift); camera.lookAt(0, 1.6 + Math.tan(up) * D * drift, 0);
      camera.setViewOffset(W, H, (0.5 - (cam.x ?? 0.42)) * W, 0, W, H);
    } };
  }
  if (shot.scene === 'venera_descent') {
    const p = parachute(THREE); scene.add(p);
    return { scene, place(camera, k, W, H) {
      const t = k * (shot.end - shot.start), fov = cam.fov ?? 34, size = cam.size ?? 0.36, aspect = W / H;
      camera.fov = fov; camera.aspect = aspect; camera.updateProjectionMatrix();
      p.position.y = Math.sin(t * 0.9) * 0.12; p.rotation.z = Math.sin(t * 0.55) * 0.03;
      const D = 7.0 / (size * 2 * Math.tan(fov * Math.PI / 360) * aspect);
      camera.position.set(Math.sin((cam.az ?? 0) * 0.017 + t * 0.01) * D * 0.15, 4.2 + (cam.y ?? 0), D); camera.lookAt(0, 4.6 + (cam.look ?? 0), 0);
    } };
  }
  const land = venera(THREE), hov = new THREE.Group(); hov.add(land); scene.add(hov);
  const gnd = ground(THREE, cam.seed ?? 7); scene.add(gnd);
  const sh = shadowDisc(THREE); sh.scale.setScalar(6); sh.position.y = 0.02; scene.add(sh);
  return { scene, place(camera, k, W, H) {
    const t = k * (shot.end - shot.start), fov = cam.fov ?? 30, size = cam.size ?? 0.26, aspect = W / H, horizon = cam.horizon ?? 0.7;
    camera.fov = fov; camera.aspect = aspect; camera.updateProjectionMatrix();
    const hover = (cam.hover ?? 1.3) + Math.sin(t * 0.8) * 0.05;     // it floats a little above the plain, as in the reference
    hov.position.y = hover; sh.position.y = 0.02; sh.scale.setScalar(5.4 + hover * 0.8); sh.material.opacity = Math.max(0.25, 0.8 - hover * 0.18);
    land.rotation.y = (cam.turn ?? -0.35) + Math.sin(t * 0.25) * 0.05;
    const D = 4.4 / (size * 2 * Math.tan(fov * Math.PI / 360) * aspect), camH = cam.cam_h ?? (hover + 2.0);
    const up = Math.atan((horizon - 0.5) * 2 * Math.tan(fov * Math.PI / 360));          // pitch that puts the horizon at `horizon` of the frame height
    const drift = 1 - 0.04 * k;
    camera.position.set((cam.az ?? 0) * 0.02 * D, camH, D * drift);
    camera.lookAt(0, camH + Math.tan(up) * D * drift, 0);
    const xc = cam.x ?? 0.5; camera.setViewOffset(W, H, (0.5 - xc) * W, 0, W, H);
  } };
}
