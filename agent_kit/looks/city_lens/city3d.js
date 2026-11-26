// 3D BLOCK CITY: a dark ground with a grid of grey extruded buildings (seeded, same every frame), seen from a moving
// camera. For "1958 Sweet Auburn" / "the Stitch" / "downtown from above" shots: a red elevated freeway cutting through,
// a green park lid over a trench, buildings vanishing (demolished for parking) or rising (a comeback).
//   const C3 = await makeCity(canvas, { seed: 4, blocks: 14, towers: [[0, 0, 9]] });   // towers: [x, z, height] landmarks
//   C3.render({
//     cam: { yaw: -30, pitch: 48, dist: 26, x: 0, z: 0 },     // orbit around (x, z); move these over t
//     rise: 1,                                                 // 0..1 buildings grow from the ground
//     gone: (x, z) => x > 2 && x < 5 ? k : 0,                  // 0..1 per building: 1 = removed (demolished)
//     corridor: { pts: [[-14, 3], [14, -1]], width: 1.6, color: 0xd9352e, k, height: 0.6 },  // a band drawn along a line (or an array of them; clear:false keeps buildings)
//     ring: { pts: [[-6,-5],[6,-5],[6,5],[-6,5]], k, color: 0xf2a33a },                       // a glowing loop on the ground
//   });
//   C3.screen(x, z, y=0) -> [px, py] for labels/pins (put them in the svg above the canvas).
// Units: one block = 1 unit; the city spans -blocks..blocks on x and z.
import * as THREE from '/agent_kit/lib/three.module.js';

export async function makeCity(canvas, { seed = 1, blocks = 14, towers = [], ground = 0x1b1f27, building = 0xc9ccd1,
  fog = 0x1b1f27, density = 0.8 } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(canvas.width, canvas.height, false); renderer.setClearColor(ground);
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(fog, blocks * 1.6, blocks * 4.2);
  const camera = new THREE.PerspectiveCamera(34, canvas.width / canvas.height, 0.1, 400);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x30343c, 1.25));
  const sun = new THREE.DirectionalLight(0xffffff, 1.5); sun.position.set(-20, 40, 18); scene.add(sun);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(blocks * 8, blocks * 8), new THREE.MeshStandardMaterial({ color: ground, roughness: 1 }));
  floor.rotation.x = -Math.PI / 2; scene.add(floor);
  // street grid lines
  const grid = new THREE.GridHelper(blocks * 2, blocks * 2, 0x3a4150, 0x2a303b); grid.position.y = 0.002; scene.add(grid);

  let s = seed * 7919 + 13;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const mat = new THREE.MeshStandardMaterial({ color: building, roughness: 0.85 });
  const box = new THREE.BoxGeometry(1, 1, 1); box.translate(0, 0.5, 0);
  const list = [];
  for (let x = -blocks; x < blocks; x++) for (let z = -blocks; z < blocks; z++) {
    if (rnd() > density) continue;
    const n = 1 + Math.floor(rnd() * 3);                           // 1-3 buildings per block
    for (let i = 0; i < n; i++) {
      const w = 0.25 + rnd() * 0.45, d = 0.25 + rnd() * 0.45, cx = x + 0.15 + rnd() * (0.7 - w) + w / 2, cz = z + 0.15 + rnd() * (0.7 - d) + d / 2;
      const r = Math.hypot(cx, cz) / blocks, h = 0.15 + rnd() * (0.4 + 2.6 * Math.max(0, 1 - r * 1.6) ** 2);
      const m = new THREE.Mesh(box, mat); m.position.set(cx, 0, cz); m.scale.set(w, h, d); scene.add(m);
      list.push({ m, h, x: cx, z: cz });
    }
  }
  towers.forEach(([x, z, h]) => { const m = new THREE.Mesh(box, mat); m.position.set(x, 0, z); m.scale.set(0.8, h, 0.8); scene.add(m); list.push({ m, h, x, z }); });

  const extra = new THREE.Group(); scene.add(extra);
  const band = (pts, width, color, y, k, opacity = 1) => {          // a flat band along a polyline, drawn on to k
    const total = pts.slice(1).reduce((a, p, i) => a + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);
    let left = total * Math.min(1, Math.max(0, k));
    for (let i = 1; i < pts.length && left > 0; i++) {
      const [x0, z0] = pts[i - 1], [x1, z1] = pts[i], L = Math.hypot(x1 - x0, z1 - z0), l = Math.min(L, left); left -= l;
      const g = new THREE.BoxGeometry(l, Math.max(0.02, y), width);
      const mm = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color, roughness: 0.6, transparent: opacity < 1, opacity, emissive: color, emissiveIntensity: 0.25 }));
      const a = Math.atan2(z1 - z0, x1 - x0);
      mm.position.set(x0 + Math.cos(a) * l / 2, Math.max(0.02, y) / 2, z0 + Math.sin(a) * l / 2); mm.rotation.y = -a;
      extra.add(mm);
    }
  };
  const near = (pts, x, z, w) => {                                   // distance from (x, z) to a polyline < w
    for (let i = 1; i < pts.length; i++) {
      const [ax, az] = pts[i - 1], [bx, bz] = pts[i], dx = bx - ax, dz = bz - az;
      const u = Math.max(0, Math.min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz || 1)));
      if (Math.hypot(x - ax - u * dx, z - az - u * dz) < w) return true;
    }
    return false;
  };

  function render({ cam = {}, rise = 1, gone = null, corridor = null, ring = null } = {}) {
    extra.children.forEach((c) => { c.geometry.dispose(); c.material.dispose(); }); extra.clear();
    const kr = Math.min(1, Math.max(0, rise)), cors = corridor ? [].concat(corridor) : [];
    list.forEach((b) => {
      let g = gone ? Math.min(1, Math.max(0, gone(b.x, b.z))) : 0;
      cors.forEach((c) => { if (c.clear !== false && near(c.pts, b.x, b.z, (c.width || 1.4) * 0.6)) g = Math.max(g, Math.min(1, (c.k ?? 1) * 1.4)); });
      const h = b.h * (1 - (1 - kr) ** 3) * (1 - g);
      b.m.visible = h > 0.01; b.m.scale.y = Math.max(0.01, h);
    });
    cors.forEach((c) => band(c.pts, c.width || 1.4, c.color ?? 0xd9352e, c.height ?? 0.5, c.k ?? 1));
    if (ring) { const p = [...ring.pts, ring.pts[0]]; band(p, ring.width || 0.22, ring.color ?? 0xf2a33a, 0.05, ring.k ?? 1); }
    const { yaw = -30, pitch = 50, dist = 26, x = 0, z = 0 } = cam, r = Math.PI / 180;
    camera.position.set(x + dist * Math.cos(pitch * r) * Math.sin(yaw * r), dist * Math.sin(pitch * r), z + dist * Math.cos(pitch * r) * Math.cos(yaw * r));
    camera.lookAt(x, 0, z); camera.updateMatrixWorld();
    renderer.render(scene, camera);
  }
  function screen(x, z, y = 0) {
    const v = new THREE.Vector3(x, y, z).project(camera);
    return [(v.x + 1) / 2 * canvas.width, (1 - v.y) / 2 * canvas.height];
  }
  return { render, screen };
}
