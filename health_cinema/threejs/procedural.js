// Procedural medical illustrations for Health Cinema: blood flow, artery plaque, blood clot, a cell (optionally filling with fat droplets).
// Deterministic (seeded, every position is a function of the scene time and the spec tracks), so a re-render is identical and frames can be rendered in any order.
// These are conceptual illustrations, not anatomy: the pipeline labels them as such. Units are metres-ish; the vessel runs along the X axis (three.js Y is up).
export function build(THREE, scene, spec) {
  const P = spec.procedural; const rnd = (seed) => () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const V = P.variant || 0; const kind = P.kind; const R = P.radius ?? 0.5, L = P.length ?? 8; const group = new THREE.Group(); scene.add(group);
  const std = (c, o = {}) => new THREE.MeshStandardMaterial({ color: new THREE.Color(...c), roughness: 0.5, metalness: 0, ...o });
  const upd = [];
  const tubeMat = (c, op) => std(c, { transparent: true, opacity: op, side: THREE.DoubleSide, depthWrite: false, roughness: 0.35 });
  if (kind === 'blood_flow' || kind === 'plaque' || kind === 'clot') {
    const SEG = 120, ANG = 56; const geo = new THREE.CylinderGeometry(R, R, L, ANG, SEG, true); geo.rotateZ(Math.PI / 2);   // along X
    const base = geo.attributes.position.array.slice(); const WALL = [[0.62, 0.16, 0.18], [0.5, 0.13, 0.22], [0.66, 0.24, 0.14], [0.45, 0.16, 0.16]][V % 4]; const wall = new THREE.Mesh(geo, tubeMat(WALL, 0.3)); wall.renderOrder = 5; group.add(wall);
    const bell = (x, s) => Math.exp(-(x * x) / (2 * s * s));
    // plaque: the wall thickens around x = 0, mostly on one side, narrowing the lumen; a separate yellow lipid layer follows the same displacement
    const lump = (x, ang, prog) => { const bumps = 0.75 + 0.25 * Math.sin(ang * 3 + x * 2.2); const side = 0.5 + 0.5 * Math.cos(ang - 0.35 - V * 1.7);  /* the upper wall: seen in profile as a bulge into the channel */ return prog * (P.thickness ?? 1.05) * R * bell(x - 0.25 * (V % 3 - 1), 0.55 + 0.12 * (V % 2)) * (0.04 + 0.96 * side * side) * bumps; };
    let plaqueMesh = null, pGeo = null;
    if (kind === 'plaque') {
      pGeo = new THREE.CylinderGeometry(R, R, L, ANG, SEG, true); pGeo.rotateZ(Math.PI / 2); pGeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(pGeo.attributes.position.count * 3), 3)); plaqueMesh = new THREE.Mesh(pGeo, std([1, 1, 1], { side: THREE.BackSide, roughness: 0.6, vertexColors: true })); plaqueMesh.renderOrder = 6; group.add(plaqueMesh);
    }
    const N = (P.cells ?? 220) + (V % 3) * 45, cells = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 20, 12), std([0.78, 0.06, 0.09], { roughness: 0.42 }), N); cells.renderOrder = 8; cells.frustumCulled = false; group.add(cells);
    const r = rnd(7 + V * 131), cs = Array.from({ length: N }, () => ({ x0: r() * L, u: r(), th: r() * 6.283, sp: 0.55 + r() * 0.5, ph: r() * 6.283, tum: 0.6 + r() * 1.6, s: 0.052 + r() * 0.018 }));
    // clot: platelets + fibrin strands accumulate on the wall at x = 0 and finally block the vessel
    const M = 900, plate = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 10, 8), std([0.86, 0.52, 0.36], { roughness: 0.55 }), M); plate.renderOrder = 7; plate.count = 0; plate.frustumCulled = false; if (kind === 'clot') group.add(plate);
    const rc = rnd(21 + V * 17), pl = Array.from({ length: M }, (_, i) => { const a = rc() * 6.283, d = Math.cbrt(rc()), s = 0.026 + rc() * 0.018; return { a, d, s, x: (rc() - 0.5) * 1.5 }; });
    const fib = []; for (let i = 0; i < 90; i++) { const a = rc() * 6.283, b = rc() * 6.283; fib.push([(rc() - 0.5) * 1.4, Math.cos(a) * R * 0.8 * rc(), Math.sin(a) * R * 0.8 * rc(), (rc() - 0.5) * 1.4, Math.cos(b) * R * 0.8 * rc(), Math.sin(b) * R * 0.8 * rc()]); }
    const fibGeo = new THREE.BufferGeometry(); fibGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(fib.flatMap((s) => s)), 3)); const fibMesh = new THREE.LineSegments(fibGeo, new THREE.LineBasicMaterial({ color: 0xf2e6b0, transparent: true, opacity: 0 })); fibMesh.renderOrder = 7; if (kind === 'clot') group.add(fibMesh);
    const dummy = new THREE.Object3D(), pa = geo.attributes.position, ppa = pGeo ? pGeo.attributes.position : null; let lastProg = -1;
    upd.push((f) => {
      const t = f.t, prog = f.proc?.plaque ?? 0, clot = f.proc?.clot ?? 0, speed = (P.speed ?? 0.9) * (f.proc?.flow ?? 1);
      if (kind === 'plaque' && Math.abs(prog - lastProg) > 1e-4) {   // reshape the inner (lipid) layer; the outer wall stays put
        for (let i = 0; i < ppa.count; i++) { const x = base[i * 3], y = base[i * 3 + 1], z = base[i * 3 + 2]; const ang = Math.atan2(z, y); const d = lump(x, ang, prog); const k = (R - d) / R; ppa.setXYZ(i, x, y * k, z * k); const m = Math.max(0, Math.min(1, (d - 0.01 * R) / (0.06 * R))); const col = pGeo.attributes.color; col.setXYZ(i, 0.62 + 0.36 * m, 0.16 + 0.58 * m, 0.17 + 0.05 * m); }
        pGeo.attributes.color.needsUpdate = true;
        ppa.needsUpdate = true; pGeo.computeVertexNormals(); lastProg = prog;
      }
      const local = (x, th) => (kind === 'plaque' ? R - lump(x, th, prog) : R);
      cs.forEach((c, i) => {
        let adv = c.x0 + (V % 2 ? -1 : 1) * c.sp * speed * t * 1.4;                         // metres along the vessel
        let x = ((adv % L) + L) % L - L / 2; const tum = c.ph + c.tum * t; let alive = 1;
        if (kind === 'clot') { const front = -0.9 * clot; if (x > front - 1.2 && x < 0.5 && clot > 0.05) x = Math.min(x, front - 0.05 - 0.12 * (i % 9) / 9); if (x > 0.6) alive = 1 - 0.92 * clot; }
        const rmax = Math.min(R, local(x, c.th)) * 0.86; const rr = Math.sqrt(c.u) * rmax;
        const y = Math.cos(c.th) * rr, z = Math.sin(c.th) * rr; const sc = c.s * (kind === 'plaque' ? 1 : 1) * alive;
        dummy.position.set(x, y, z); dummy.rotation.set(tum, tum * 0.7, tum * 0.4); dummy.scale.set(sc, sc * 0.4, sc); dummy.updateMatrix(); cells.setMatrixAt(i, dummy.matrix);
      }); cells.instanceMatrix.needsUpdate = true;
      if (kind === 'clot') {
        const n = Math.floor(M * clot); plate.count = n;
        for (let i = 0; i < n; i++) { const p = pl[i]; const ang = p.a, rad = R * 0.92 * (0.15 + 0.85 * p.d) * (0.35 + 0.65 * clot); dummy.position.set(-0.1 + p.x * (0.4 + clot), Math.cos(ang) * rad, Math.sin(ang) * rad); dummy.scale.setScalar(p.s * (0.6 + 0.6 * clot)); dummy.rotation.set(0, 0, 0); dummy.updateMatrix(); plate.setMatrixAt(i, dummy.matrix); }
        plate.instanceMatrix.needsUpdate = true; fibMesh.material.opacity = Math.min(1, clot * 1.4) * 0.8;
      }
    });
  }
  if (kind === 'cell') {
    const cell = new THREE.Group(); group.add(cell); const mem = new THREE.Mesh(new THREE.SphereGeometry(1, 64, 40), tubeMat([0.55, 0.75, 0.95], 0.2)); mem.scale.set(1.15, 0.95, 1.0); mem.renderOrder = 4; cell.add(mem);
    const nuc = new THREE.Mesh(new THREE.SphereGeometry(0.36, 40, 28), std([0.42, 0.28, 0.62], { roughness: 0.55 })); nuc.position.set(-0.12, 0.05, 0.0); cell.add(nuc);
    const nl = new THREE.Mesh(new THREE.SphereGeometry(0.1, 24, 16), std([0.25, 0.14, 0.4])); nl.position.set(-0.05, 0.1, 0.28); cell.add(nl);
    const r = rnd(3 + V * 13); const mito = [];
    for (let i = 0; i < 9; i++) { const m = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.16, 8, 16), std([0.95, 0.55, 0.25], { roughness: 0.45 })); const a = r() * 6.283, b = (r() - 0.5) * 2.2, d = 0.55 + r() * 0.25;
      m.position.set(Math.cos(a) * d * 0.9, Math.sin(b) * d * 0.55, Math.sin(a) * d * 0.8); m.rotation.set(r() * 3, r() * 3, r() * 3); cell.add(m); mito.push(m); }
    const D = 46, drops = [], dr = rnd(11 + V * 7);
    for (let i = 0; i < D; i++) { const a = dr() * 6.283, b = Math.acos(2 * dr() - 1), d = 0.35 + dr() * 0.55; const m = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 14), std([0.98, 0.9, 0.35], { roughness: 0.25, transparent: true, opacity: 0.92 }));
      m.position.set(Math.sin(b) * Math.cos(a) * d * 1.05, Math.cos(b) * d * 0.8, Math.sin(b) * Math.sin(a) * d * 0.9); m.userData = { s: 0.025 + dr() * 0.06, at: dr() }; cell.add(m); drops.push(m); }
    upd.push((f) => { const t = f.t, lip = f.proc?.lipid ?? 0; cell.rotation.y = 0.12 * t; mito.forEach((m, i) => { m.position.y += Math.sin(t * 1.3 + i) * 0.0004; });
      drops.forEach((m) => { const g = Math.min(1, Math.max(0, (lip - m.userData.at * 0.6) / 0.4)); m.visible = g > 0.01; m.scale.setScalar(m.userData.s * (0.2 + 1.9 * g)); });
      nuc.scale.setScalar(1 - 0.18 * lip); });
  }
  // depth behind the subject: out-of-focus vessels and cells drifting far away (so the scene is never a lone object on a flat background)
  const rb = rnd(99 + V * 31), bgG = new THREE.Group(); scene.add(bgG); const farN = 90, dm = new THREE.Object3D(); let far = null, farD = [];
  if (kind !== 'cell') for (let i = 0; i < 5; i++) { const rad = 0.7 + rb() * 0.9; const m = new THREE.Mesh(new THREE.CylinderGeometry(rad, rad, 18, 24, 1, true), std([0.2, 0.035, 0.06], { transparent: true, opacity: 0.4, side: THREE.DoubleSide, depthWrite: false, roughness: 0.8 }));
    m.rotation.z = Math.PI / 2 + (rb() - 0.5) * 0.5; m.position.set((rb() - 0.5) * 4, (rb() - 0.5) * 3.4, -3.2 - rb() * 4.5); m.renderOrder = 1; bgG.add(m); }
  far = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 14, 10), std(kind === 'cell' ? [0.3, 0.65, 0.85] : [0.42, 0.06, 0.1], { transparent: true, opacity: kind === 'cell' ? 0.15 : 0.42, roughness: 0.85, depthWrite: false }), farN); far.renderOrder = 2; far.frustumCulled = false; bgG.add(far);
  for (let i = 0; i < farN; i++) farD.push({ x: (rb() - 0.5) * 9, y: (rb() - 0.5) * 5, z: -2.5 - rb() * 5.5, s: kind === 'cell' ? 0.1 + rb() * 0.28 : 0.1 + rb() * 0.22, sp: 0.04 + rb() * 0.08, ph: rb() * 6.28 });
  upd.push((f) => { farD.forEach((c, i) => { const x = (((c.x + 4.5 + c.sp * f.t * (V % 2 ? -1 : 1)) % 9) + 9) % 9 - 4.5; dm.position.set(x, c.y + Math.sin(f.t * 0.3 + c.ph) * 0.12, c.z); dm.rotation.set(f.t * 0.2 + c.ph, f.t * 0.15, 0); dm.scale.set(c.s, c.s * (kind === 'cell' ? 1 : 0.4), c.s); dm.updateMatrix(); far.setMatrixAt(i, dm.matrix); }); far.instanceMatrix.needsUpdate = true; });
  scene.add(new THREE.HemisphereLight(0xaab8dd, 0x331a1a, 0.6));
  return { update(f) { upd.forEach((u) => u(f)); } };
}
