// HABITAT hero scenes (V5 "The City in Space Where the Ground Is Above Your Head"): spinning space settlements drawn procedurally --
// no textures to download, no generated pictures, the same frame every time.
//   ring_station        a wheel station (torus, spokes, hub) turning slowly against the stars, a blue planet below (V5 0:40, 7:40)
//   cylinder_interior   standing inside an O'Neill cylinder: land strips and window strips curve up and over your head, clouds float
//                       halfway to the axis, the far end glows (V5 0:00, 9:50 -- the title shot)
//   cylinder_exterior   the pair of counter-turning cylinders seen from outside, land and window stripes along them (V5 7:20 'MODEL 4')
//   shot.cam: { dist, el, az, fov, orbit (deg over the shot), push (0..1), spin (deg/s), x, seed }
export const HABITAT_SCENES = ['ring_station', 'cylinder_interior', 'cylinder_exterior'];
const rnd = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

function canvasTex(THREE, w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

/** The inside of a cylinder as one texture: around the circumference three land strips (fields, roads, a few towns) and three windows. */
function insideTexture(THREE, seed) {
  const r = rnd(seed);
  return canvasTex(THREE, 3072, 1024, (g, W, H) => {
    const strip = W / 6;
    for (let k = 0; k < 6; k++) {
      const x0 = k * strip;
      if (k % 2) {       // a window: sunlight through glass, pale blue sky
        const grd = g.createLinearGradient(x0, 0, x0 + strip, 0);
        grd.addColorStop(0, '#9FC3E6'); grd.addColorStop(0.5, '#CFE4F5'); grd.addColorStop(1, '#9FC3E6');
        g.fillStyle = grd; g.fillRect(x0, 0, strip, H);
        g.fillStyle = 'rgba(80,100,120,0.35)';
        for (let y = 0; y < H; y += 64) g.fillRect(x0, y, strip, 3);          // the window's frame ribs
        continue;
      }
      g.fillStyle = '#5E7F3A'; g.fillRect(x0, 0, strip, H);
      for (let i = 0; i < 260; i++) {        // fields
        const fx = x0 + r() * strip, fy = r() * H, fw = 20 + r() * 90, fh = 14 + r() * 60;
        const c = ['#6F8F45', '#86A350', '#A6A65A', '#4F6E33', '#93904C', '#7A9A4A'][Math.floor(r() * 6)];
        g.fillStyle = c; g.fillRect(Math.min(fx, x0 + strip - fw), fy, fw, fh);
      }
      g.strokeStyle = 'rgba(210,200,170,0.6)'; g.lineWidth = 3;               // roads along the cylinder and a few across
      g.beginPath(); g.moveTo(x0 + strip * 0.5, 0); g.lineTo(x0 + strip * 0.5, H); g.stroke();
      for (let y = 40; y < H; y += 120 + r() * 120) { g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 + strip, y + (r() - 0.5) * 30); g.stroke(); }
      for (let i = 0; i < 18; i++) {         // towns: small light blocks
        const tx = x0 + 20 + r() * (strip - 40), ty = r() * H;
        for (let j = 0; j < 12; j++) { g.fillStyle = ['#D8D2C4', '#C9C1B0', '#E6E0D2'][j % 3]; g.fillRect(tx + (r() - 0.5) * 50, ty + (r() - 0.5) * 50, 6 + r() * 8, 6 + r() * 8); }
      }
    }
  });
}

function cloudSprite(THREE) {
  return canvasTex(THREE, 128, 128, (g) => {
    for (let i = 0; i < 9; i++) {
      const x = 30 + Math.random() * 68, y = 44 + Math.random() * 40, rr = 18 + Math.random() * 22;
      const grd = g.createRadialGradient(x, y, 0, x, y, rr); grd.addColorStop(0, 'rgba(255,255,255,0.95)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = grd; g.beginPath(); g.arc(x, y, rr, 0, Math.PI * 2); g.fill();
    }
  });
}

function hullTexture(THREE, seed, { windows = false } = {}) {
  const r = rnd(seed);
  return canvasTex(THREE, 1024, 512, (g, W, H) => {
    g.fillStyle = '#8D939B'; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 900; i++) { g.fillStyle = `rgba(${r() < 0.5 ? '40,44,50' : '220,224,230'},${0.08 + r() * 0.12})`; g.fillRect(r() * W, r() * H, 8 + r() * 40, 4 + r() * 20); }
    g.strokeStyle = 'rgba(30,34,40,0.5)'; g.lineWidth = 2;
    for (let x = 0; x < W; x += 32) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
    if (windows) for (let k = 1; k < 6; k += 2) { g.fillStyle = 'rgba(20,40,70,0.85)'; g.fillRect((k * W) / 6, 0, W / 6, H); }
  });
}

export function habitatScene(THREE, shot, { stars } = {}) {
  const cam = shot.cam || {}, scene = new THREE.Scene();
  const sun = new THREE.DirectionalLight(0xfff4e0, 2.6); sun.position.set(-8, 6, 10); scene.add(sun);
  scene.add(new THREE.HemisphereLight(0x9fb6d8, 0x1a1d24, 0.55));
  if (shot.scene === 'cylinder_interior') {
    const R = 10, L = 80;
    scene.background = new THREE.Color(0xbfd8ee);
    scene.fog = new THREE.Fog(0xcfe2f2, 18, 75);
    const tex = insideTexture(THREE, cam.seed ?? 3); tex.wrapS = THREE.RepeatWrapping; tex.wrapT = THREE.RepeatWrapping; tex.repeat.set(1, 3);
    const tube = new THREE.Mesh(new THREE.CylinderGeometry(R, R, L, 192, 1, true), new THREE.MeshStandardMaterial({ map: tex, side: THREE.BackSide, roughness: 1 }));
    tube.rotation.x = Math.PI / 2; scene.add(tube);
    scene.add(new THREE.AmbientLight(0xffffff, 1.1));
    const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: canvasTex(THREE, 256, 256, (g) => { const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128); grd.addColorStop(0, 'rgba(255,255,240,1)'); grd.addColorStop(0.3, 'rgba(255,250,225,0.8)'); grd.addColorStop(1, 'rgba(255,250,225,0)'); g.fillStyle = grd; g.fillRect(0, 0, 256, 256); }), depthWrite: false, fog: false }));
    glow.scale.set(14, 14, 1); glow.position.set(0, 0, -L / 2 + 2); scene.add(glow);
    const cloudMap = cloudSprite(THREE), r = rnd(cam.seed ?? 11), clouds = new THREE.Group();
    for (let i = 0; i < 70; i++) {
      const a = r() * Math.PI * 2, rad = R * (0.55 + r() * 0.2), z = (r() - 0.5) * L * 0.9;
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: cloudMap, transparent: true, opacity: 0.85, depthWrite: false }));
      const s = 2.2 + r() * 2.6; sp.scale.set(s, s * 0.6, 1); sp.position.set(Math.cos(a) * rad, Math.sin(a) * rad, z); clouds.add(sp);
    }
    scene.add(clouds);
    return { scene, place(camera, k, W, H) {
      const t = k * (shot.end - shot.start), fov = cam.fov ?? 72;
      camera.fov = fov; camera.aspect = W / H; camera.updateProjectionMatrix();
      const h = cam.height ?? 0.9;                                  // 0.9 R from the axis: standing near the ground, the land rising overhead
      const roll = ((cam.roll ?? 0) + (cam.spin ?? 0.6) * t) * Math.PI / 180;
      camera.position.set(Math.sin(roll) * R * h, -Math.cos(roll) * R * h, (cam.z ?? 25) - (cam.speed ?? 0.25) * t);
      camera.up.set(-Math.sin(roll), Math.cos(roll), 0);
      const look = (cam.look ?? 0.15) * R;
      camera.lookAt(Math.sin(roll) * (R * h - look), -Math.cos(roll) * (R * h - look), camera.position.z - 30);
      clouds.rotation.z = t * 0.004;
    } };
  }
  scene.background = new THREE.Color(0x020306);
  if (stars) scene.add(stars(cam.seed ?? 21));
  if (shot.scene === 'ring_station') {
    const station = new THREE.Group(), R = 6;
    const metal = new THREE.MeshStandardMaterial({ map: hullTexture(THREE, 5, { windows: true }), roughness: 0.55, metalness: 0.6 });
    station.add(new THREE.Mesh(new THREE.TorusGeometry(R, 0.75, 32, 160), metal));
    const steel = new THREE.MeshStandardMaterial({ color: 0xb8bec6, roughness: 0.4, metalness: 0.8 });
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2, spoke = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, R, 12), steel);
      spoke.position.set(Math.cos(a) * R / 2, Math.sin(a) * R / 2, 0); spoke.rotation.z = a - Math.PI / 2; station.add(spoke);
    }
    station.add(new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 1.6, 32), steel).rotateX(Math.PI / 2));
    const mirror = new THREE.Mesh(new THREE.TorusGeometry(R * 1.02, 0.08, 8, 160), new THREE.MeshStandardMaterial({ color: 0xdfe6ee, roughness: 0.15, metalness: 1 }));
    mirror.position.z = 1.2; station.add(mirror);
    scene.add(station);
    const planet = new THREE.Mesh(new THREE.SphereGeometry(40, 64, 48), new THREE.MeshStandardMaterial({ color: 0x2f6bdf, roughness: 0.9 }));
    planet.position.set(0, -78, -70); scene.add(planet);
    const halo = new THREE.Mesh(new THREE.SphereGeometry(41.2, 64, 48), new THREE.MeshBasicMaterial({ color: 0x7fb6ff, transparent: true, opacity: 0.18, side: THREE.BackSide }));
    halo.position.copy(planet.position); scene.add(halo);
    return { scene, place(camera, k, W, H) {
      const t = k * (shot.end - shot.start), fov = cam.fov ?? 38, dist = (cam.dist ?? 22) * (1 - (cam.push ?? 0.05) * k);
      camera.fov = fov; camera.aspect = W / H; camera.updateProjectionMatrix();
      station.rotation.z = (cam.spin ?? 6) * t * Math.PI / 180;    // 1 turn a minute = 6 degrees a second (V5 '1 TURN A MINUTE')
      const az = ((cam.az ?? 25) + (cam.orbit ?? 8) * k) * Math.PI / 180, el = (cam.el ?? 28) * Math.PI / 180;
      camera.position.set(Math.sin(az) * Math.cos(el) * dist, Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist); camera.lookAt(0, 0, 0);
      camera.setViewOffset(W, H, (0.5 - (cam.x ?? 0.5)) * W, 0, W, H);
    } };
  }
  // cylinder_exterior: the counter-turning pair
  const pair = new THREE.Group(), cyl = [];
  for (const side of [-1, 1]) {
    const m = new THREE.MeshStandardMaterial({ map: hullTexture(THREE, side > 0 ? 7 : 9, { windows: true }), roughness: 0.5, metalness: 0.55 });
    const c = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 7, 96, 1, false), m); c.position.x = side * 2.6; pair.add(c); cyl.push([c, side]);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.2, 0.05, 8, 96), new THREE.MeshStandardMaterial({ color: 0xc9a36a, metalness: 0.7, roughness: 0.4 }));
    ring.rotation.x = Math.PI / 2; ring.position.set(side * 2.6, -3.3, 0); pair.add(ring);
  }
  scene.add(pair);
  return { scene, place(camera, k, W, H) {
    const t = k * (shot.end - shot.start), fov = cam.fov ?? 36, dist = (cam.dist ?? 17) * (1 - (cam.push ?? 0.05) * k);
    camera.fov = fov; camera.aspect = W / H; camera.updateProjectionMatrix();
    for (const [c, side] of cyl) c.rotation.y = side * (cam.spin ?? 6) * t * Math.PI / 180;      // turning opposite ways (V5 'TURNING OPPOSITE WAYS')
    const az = ((cam.az ?? 20) + (cam.orbit ?? 10) * k) * Math.PI / 180, el = (cam.el ?? 22) * Math.PI / 180;
    camera.position.set(Math.sin(az) * Math.cos(el) * dist, Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist); camera.lookAt(0, 0, 0);
    camera.setViewOffset(W, H, (0.5 - (cam.x ?? 0.5)) * W, 0, W, H);
  } };
}
