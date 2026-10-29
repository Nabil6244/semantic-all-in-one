// Body-map extras for Health Cinema: a magnified skin-tissue block (epidermis / dermis / fat, a lesion with bacteria) floating in front of the real skin position, and an illustrative
// route that bacteria take from the lesion toward the heart. Both are conceptual illustrations placed on real anatomical anchors (spec.procedural.at / .path, three.js coordinates).
// Deterministic: everything is a function of the frame's named tracks (f.proc.skin, .infection, .spread, .route) so frames can render in any order.
export function build(THREE, scene, spec) {
  const P = spec.procedural; const group = new THREE.Group(); scene.add(group);
  const rnd = (seed) => () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const r = rnd(P.seed || 5);
  const std = (c, o = {}) => new THREE.MeshStandardMaterial({ color: new THREE.Color(...c), roughness: 0.55, metalness: 0, ...o });
  const upd = [];
  // ---- skin block ---------------------------------------------------------------------------------------------------------------------------------
  const at = P.at || [0, -50, 0];      // organ-only scenes have no skin block: it stays hidden (skin track 0) far away from the body
  const W = P.block?.[0] ?? 0.16, D = P.block?.[1] ?? 0.1, H = P.block?.[2] ?? 0.07;   // across the arm, depth into the tissue (y), along the arm
  const block = new THREE.Group(); const OFF = P.offset ?? [0, 0, 0]; block.position.set(at[0] + OFF[0], at[1] + OFF[1], at[2] + (P.lift ?? 0.07)); block.rotation.set(0.5, 0.0, 0.0); group.add(block);
  // block spans x:-W/2..W/2 (across), y:0..-D (top surface down), z:-H/2..H/2 (the cut face looks toward +z / the camera)
  const layers = [{ name: 'epidermis', f: 0.07, c: [0.8, 0.6, 0.54], o: 0.92 }, { name: 'dermis', f: 0.40, c: [0.74, 0.42, 0.4], o: 0.97 }, { name: 'fat', f: 0.53, c: [0.82, 0.68, 0.36], o: 0.97 }];
  let y = 0; const mats = {};
  layers.forEach((L) => { const h = D * L.f; const m = new THREE.Mesh(new THREE.BoxGeometry(W, h, H), std(L.c, { transparent: true, opacity: L.o, roughness: 0.62 })); m.position.y = y - h / 2; y -= h; m.renderOrder = 20; block.add(m); mats[L.name] = m; L.mesh = m; });
  // edges: a soft hologram outline so the block reads as an illustration, not an object
  const eg = new THREE.EdgesGeometry(new THREE.BoxGeometry(W, D, H)); const edges = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x7fd0ff, transparent: true, opacity: 0.7 })); edges.position.y = -D / 2; edges.renderOrder = 30; block.add(edges);
  // dermis details: collagen strands along x, a small vessel along x
  const dTop = -D * layers[0].f, dBot = -D * (layers[0].f + layers[1].f);
  const strands = new THREE.Group(); block.add(strands);
  for (let i = 0; i < 26; i++) { const g = new THREE.CylinderGeometry(0.0009, 0.0009, W * (0.4 + r() * 0.5), 5); g.rotateZ(Math.PI / 2); const s = new THREE.Mesh(g, std([0.96, 0.82, 0.78], { roughness: 0.8 })); s.position.set((r() - 0.5) * W * 0.4, dBot + (dTop - dBot) * (0.1 + r() * 0.8), H / 2 - 0.002 - r() * (H - 0.004)); s.renderOrder = 21; strands.add(s); }
  const vessel = new THREE.Mesh((() => { const g = new THREE.CylinderGeometry(0.0055, 0.0055, W * 0.98, 20, 1, true); g.rotateZ(Math.PI / 2); return g; })(), std([0.62, 0.08, 0.1], { transparent: true, opacity: 0.8, side: THREE.DoubleSide, roughness: 0.3 }));
  vessel.position.set(0, dBot + (dTop - dBot) * 0.28, H * 0.12); vessel.renderOrder = 22; block.add(vessel);
  const inner = new THREE.Mesh((() => { const g = new THREE.CylinderGeometry(0.0038, 0.0038, W * 0.99, 14); g.rotateZ(Math.PI / 2); return g; })(), new THREE.MeshBasicMaterial({ color: new THREE.Color(0.8, 0.08, 0.1), transparent: true, opacity: 0.9 })); inner.position.copy(vessel.position); inner.renderOrder = 22; block.add(inner);
  // fat lobules
  const fatTop = dBot, fatBot = -D;
  for (let i = 0; i < 22; i++) { const s = 0.006 + r() * 0.009; const m = new THREE.Mesh(new THREE.SphereGeometry(s, 14, 10), std([1.0, 0.9, 0.55], { transparent: true, opacity: 0.55, roughness: 0.25 })); m.position.set((r() - 0.5) * W * 0.92, fatTop + (fatBot - fatTop) * (0.18 + r() * 0.7), (r() - 0.5) * H * 0.9); m.renderOrder = 21; block.add(m); }
  // lesion: a reddened, swollen zone in the dermis under the top surface, a cluster of bacteria and immune cells
  const lesion = new THREE.Mesh(new THREE.SphereGeometry(1, 36, 22), new THREE.MeshBasicMaterial({ color: new THREE.Color(0.95, 0.12, 0.08), transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending })); lesion.position.set(0.0, dTop - 0.012, H * 0.2); lesion.scale.set(W * 0.34, D * 0.2, H * 0.4); lesion.renderOrder = 25; block.add(lesion);
  const NB = 120, bact = new THREE.InstancedMesh(new THREE.CapsuleGeometry(0.0026, 0.0068, 4, 8), std([0.55, 0.85, 0.2], { emissive: new THREE.Color(0.2, 0.45, 0.05), roughness: 0.4 }), NB); bact.renderOrder = 26; bact.frustumCulled = false; block.add(bact);
  const bs = Array.from({ length: NB }, (_, i) => ({ a: r() * 6.283, d: Math.cbrt(r()), z: r() - 0.5, at: r(), ph: r() * 6.283, tilt: r() * 3 }));
  const NI = 26, imm = new THREE.InstancedMesh(new THREE.SphereGeometry(0.0038, 12, 8), std([0.96, 0.96, 1.0], { roughness: 0.3 }), NI); imm.renderOrder = 26; imm.frustumCulled = false; block.add(imm);
  const is = Array.from({ length: NI }, () => ({ a: r() * 6.283, d: 0.5 + r() * 0.6, ph: r() * 6.283, at: 0.25 + r() * 0.6 }));
  const dm = new THREE.Object3D();
  // the magnifier lines from the skin spot to the block's top corners
  const cone = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: 0x7fd0ff, transparent: true, opacity: 0 })); cone.renderOrder = 30; group.add(cone);
  const spot = new THREE.Mesh(new THREE.RingGeometry(0.012, 0.016, 48), new THREE.MeshBasicMaterial({ color: 0xff5a4a, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, depthTest: false })); spot.position.set(at[0], at[1], at[2] + 0.002); spot.renderOrder = 30; group.add(spot);
  // ---- route: lesion -> vessel -> heart (illustrative) --------------------------------------------------------------------------------------------
  let routeObj = null;
  if (P.path && P.path.length > 1) {
    const curve = new THREE.CatmullRomCurve3(P.path.map((p) => new THREE.Vector3(...p)), false, 'centripetal'); const rt = new THREE.Group(); group.add(rt);
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 160, 0.0075, 12, false), new THREE.MeshBasicMaterial({ color: new THREE.Color(1.0, 0.36, 0.12), transparent: true, opacity: 0, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending })); tube.renderOrder = 40; rt.add(tube);
    const NP = 170, parts = new THREE.InstancedMesh(new THREE.SphereGeometry(0.0046, 10, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(0.95, 0.55, 0.2), transparent: true, opacity: 0.95, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }), NP); parts.renderOrder = 41; parts.frustumCulled = false; rt.add(parts);
    const ps = Array.from({ length: NP }, () => ({ u: r(), sp: 0.2 + r() * 0.5, off: [(r() - 0.5) * 0.006, (r() - 0.5) * 0.006, (r() - 0.5) * 0.006], s: 0.5 + r() }));
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.012, 20, 14), new THREE.MeshBasicMaterial({ color: new THREE.Color(1.0, 0.55, 0.2), transparent: true, opacity: 0, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending })); head.renderOrder = 42; rt.add(head);
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.03, 0.034, 64), new THREE.MeshBasicMaterial({ color: 0xff7a40, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false, depthTest: false })); ring.position.copy(curve.getPoint(1)); ring.renderOrder = 42; rt.add(ring);
    routeObj = { curve, tube, parts, ps, head, ring };
  }
  const ease = (x) => { x = Math.min(1, Math.max(0, x)); return x * x * (3 - 2 * x); };
  upd.push((f) => {
    const t = f.t, sk = f.proc?.skin ?? 0, inf = f.proc?.infection ?? 0, sp = f.proc?.spread ?? 0, rt = f.proc?.route ?? 0, entry = f.proc?.entry ?? 0;
    group.visible = true; block.visible = sk > 0.01; edges.material.opacity = 0.7 * ease(sk);
    block.scale.setScalar(0.55 + 0.45 * ease(sk)); block.position.y = at[1] + OFF[1] + 0.03 * (1 - ease(sk));
    Object.values(mats).forEach((m) => { m.material.opacity = (m === mats.epidermis ? 0.92 : 0.97) * ease(sk); });
    mats.dermis.material.color.setRGB(0.74 + 0.15 * inf, 0.42 - 0.25 * inf, 0.4 - 0.25 * inf);
    mats.epidermis.material.color.setRGB(0.8 + 0.1 * inf, 0.6 - 0.22 * inf, 0.54 - 0.26 * inf); mats.epidermis.scale.set(1, 1 + 0.9 * inf, 1);
    lesion.material.opacity = 0.5 * ease(inf) * ease(sk); const sw = 1 + 0.25 * inf; lesion.scale.set(W * 0.34 * sw, D * 0.2 * sw, H * 0.4 * sw);
    let nb = 0; bs.forEach((b, i) => { const g = ease((inf - b.at * 0.8) / 0.25) * ease(sk); const a = b.a + t * 0.3 * (b.at - 0.5), rr = b.d * W * 0.16 * (0.4 + 0.6 * ease(inf));
      const into = ease(entry);   // late: bacteria drift into the small vessel (the bloodstream entry)
      let px = Math.cos(a) * rr, py = dTop - 0.012 + Math.sin(a * 1.7 + b.ph) * D * 0.05, pz = H * 0.2 + b.z * H * 0.34;
      px = px * (1 - into) + (b.z * W * 0.9) * into; py = py * (1 - into) + vessel.position.y * into; pz = pz * (1 - into) + vessel.position.z * into;
      dm.position.set(px, py, pz); dm.rotation.set(b.tilt, t * 0.8 + b.ph, b.tilt * 0.5); dm.scale.setScalar(g); dm.updateMatrix(); bact.setMatrixAt(i, dm.matrix); nb += g; });
    bact.instanceMatrix.needsUpdate = true;
    is.forEach((c, i) => { const g = ease((inf - c.at) / 0.25) * ease(sk) * (1 - ease(entry)); const a = c.a + t * 0.5; dm.position.set(Math.cos(a) * c.d * W * 0.2, dTop - 0.012 + Math.sin(a * 1.3 + c.ph) * D * 0.06, H * 0.2 + Math.sin(a) * H * 0.2); dm.rotation.set(0, 0, 0); dm.scale.setScalar(g); dm.updateMatrix(); imm.setMatrixAt(i, dm.matrix); });
    imm.instanceMatrix.needsUpdate = true;
    inner.material.color.setRGB(0.8 - 0.1 * entry, 0.08 + 0.3 * entry, 0.1);
    const corners = [[-W / 2, 0, H / 2], [W / 2, 0, H / 2]].map((c) => block.localToWorld(new THREE.Vector3(...c))); const s0 = new THREE.Vector3(at[0], at[1], at[2] + 0.002);
    cone.geometry.setFromPoints(corners.flatMap((c) => [s0, c])); cone.material.opacity = 0.55 * ease(sk) * (1 - 0.6 * ease(rt)); spot.material.opacity = 0.9 * ease(Math.max(sk, inf)) * (1 - ease(rt)); spot.scale.setScalar(1 + 0.12 * Math.sin(t * 5));
    if (routeObj) {
      const { curve, tube, parts, ps, head, ring } = routeObj; tube.material.opacity = 0.6 * ease(rt); const u = ease(sp);
      for (let i = 0; i < ps.length; i++) { const p = ps[i], uu = ((p.u + t * p.sp * 0.22) % 1) * u; const pt = curve.getPoint(Math.min(0.999, uu)); dm.position.set(pt.x + p.off[0], pt.y + p.off[1], pt.z + p.off[2]); dm.scale.setScalar(rt > 0.02 && u > 0.01 ? p.s : 0); dm.rotation.set(0, 0, 0); dm.updateMatrix(); parts.setMatrixAt(i, dm.matrix); }
      parts.instanceMatrix.needsUpdate = true; head.position.copy(curve.getPoint(Math.min(0.999, u))); head.material.opacity = 0.8 * ease(rt) * (u > 0.01 ? 1 : 0) * (1 - 0.5 * ease((u - 0.92) / 0.08)); head.scale.setScalar(1 + 0.2 * Math.sin(t * 7));
      const arrive = ease((u - 0.9) / 0.1); ring.material.opacity = arrive * (0.5 + 0.5 * Math.sin(t * 4)); ring.scale.setScalar(1 + 0.5 * ((t * 0.8) % 1)); ring.lookAt(ring.position.x, ring.position.y, ring.position.z + 1);
    }
  });
  scene.add(new THREE.HemisphereLight(0xbcd0ff, 0x2a1a1a, 0.5));
  return { update(f) { upd.forEach((u) => u(f)); } };
}
