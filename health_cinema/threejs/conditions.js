// Condition scenes for Health Cinema: procedural 3D illustrations of what a narration describes (skin conditions, germs and cells, airways, bone, joints,
// vessels). Built fresh for every video: spec.procedural.seed (from the video and the scene) changes the arrangement, counts and timing, so no two videos
// show the same clip. Everything is a function of the frame (f.t and the 0..1 track f.proc.prog), so frames render in any order and a re-render is identical.
// Key positions come from spec.anchor_overrides (Blender coordinates, the same points the labels use), converted with tb(), so labels sit on what they name.
// These are conceptual illustrations, not anatomy: the pipeline labels them so.
export function build(THREE, scene, spec) {
  const P = spec.procedural; const K = P.kind; const C = P.condition || ''; const seed0 = (P.seed ?? 1) | 0;
  const rnd = (s) => () => { s |= 0; s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const r = rnd(seed0 * 7919 + 17);
  const tb = (p) => new THREE.Vector3(p[0], p[2], -p[1]);
  const pt = (name, dflt) => { const a = spec.anchor_overrides?.['c_' + name] ?? spec.anchor_overrides?.[name]; return a ? tb(a.center) : new THREE.Vector3(...dflt); };
  const std = (c, o = {}) => new THREE.MeshStandardMaterial({ color: new THREE.Color(...c), roughness: 0.5, metalness: 0, ...o });
  const glass = (c, op, o = {}) => std(c, { transparent: true, opacity: op, depthWrite: false, side: THREE.DoubleSide, roughness: 0.3, ...o });
  const glow = (c, op = 1) => new THREE.MeshBasicMaterial({ color: new THREE.Color(...c), transparent: true, opacity: op, depthWrite: false, blending: THREE.AdditiveBlending });
  const ease = (x) => { x = Math.min(1, Math.max(0, x)); return x * x * (3 - 2 * x); };
  const ramp = (p, a, b) => ease((p - a) / Math.max(1e-6, b - a));
  const group = new THREE.Group(); scene.add(group); const upd = []; const dm = new THREE.Object3D();
  const jitter = (k) => 1 + (r() - 0.5) * k;
  const inst = (geo, mat, n, order = 10) => { const m = new THREE.InstancedMesh(geo, mat, n); m.frustumCulled = false; m.renderOrder = order; group.add(m); return m; };
  const setI = (m, i, x, y, z, s, rx = 0, ry = 0, rz = 0, sy = null) => { dm.position.set(x, y, z); dm.rotation.set(rx, ry, rz); dm.scale.set(s, sy ?? s, s); dm.updateMatrix(); m.setMatrixAt(i, dm.matrix); };
  // a soft particle cloud far behind every scene, so the subject never floats on a flat backdrop
  const bgN = 70, bg = inst(new THREE.SphereGeometry(1, 12, 8), std(P.bg_color || [0.35, 0.5, 0.75], { transparent: true, opacity: 0.05, depthWrite: false, roughness: 0.9 }), bgN, 1);
  const bgD = Array.from({ length: bgN }, () => ({ x: (r() - 0.5) * 9, y: (r() - 0.5) * 5, z: -4 - r() * 5, s: 0.04 + r() * 0.16, ph: r() * 6.28 }));
  upd.push((f) => { bgD.forEach((c, i) => setI(bg, i, c.x + Math.sin(f.t * 0.11 + c.ph) * 0.3, c.y + Math.sin(f.t * 0.17 + c.ph) * 0.2, c.z, c.s)); bg.instanceMatrix.needsUpdate = true; });

  // ---------------------------------------------------------------- skin: a magnified block of skin (epidermis / dermis / fat) and what the condition does to it
  if (K === 'skin') {
    const W = 2.6, H = 1.3, top = 0.55, epi = 0.13, der = 0.62, fat = 0.55;      // x across, y down from the surface, z depth (cut face toward the camera)
    const block = new THREE.Group(); group.add(block);      // unrotated: the label points (Python) are in the same frame; the camera looks down at it
    const box = (h, y, c, op) => { const m = new THREE.Mesh(new THREE.BoxGeometry(W, h, H, 48, 4, 24), std(c, { transparent: op < 1, opacity: op, roughness: 0.6 })); m.position.y = y; m.renderOrder = 5; block.add(m); return m; };
    const mE = box(epi, top - epi / 2, [0.8, 0.58, 0.5], 1), mD = box(der, top - epi - der / 2, [0.76, 0.4, 0.4], 1), mF = box(fat, top - epi - der - fat / 2, [0.9, 0.74, 0.38], 1);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(W, epi + der + fat, H)), new THREE.LineBasicMaterial({ color: 0x8fd6ff, transparent: true, opacity: 0.5 })); edges.position.y = top - (epi + der + fat) / 2; block.add(edges);
    const yE = top - epi, yD = top - epi - der, zf = H / 2 + 0.002;
    // dermis furniture: a blood vessel, collagen strands, hair follicles, fat lobules on the cut face
    const ves = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, W * 0.99, 20), std([0.72, 0.1, 0.12], { roughness: 0.35 })); ves.rotation.z = Math.PI / 2; ves.position.set(0, yD + der * 0.3, zf - 0.08); block.add(ves);
    for (let i = 0; i < 40; i++) { const g = new THREE.CylinderGeometry(0.008, 0.008, 0.3 + r() * 0.6, 5); const s = new THREE.Mesh(g, std([0.97, 0.86, 0.8], { roughness: 0.8 })); s.rotation.z = Math.PI / 2 + (r() - 0.5) * 0.5; s.position.set((r() - 0.5) * W * 0.9, yD + der * (0.1 + r() * 0.8), zf - 0.01); block.add(s); }
    const fol = []; for (let i = 0; i < 3; i++) { const x = (i - 1) * 0.8 + (r() - 0.5) * 0.2; const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.035, epi + der * 0.7, 12), std([0.8, 0.55, 0.5], { roughness: 0.5 })); tube.position.set(x, top - (epi + der * 0.7) / 2, zf - 0.05); block.add(tube);
      const hair = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, epi + der * 0.7 + 0.5, 6), std([0.2, 0.13, 0.1])); hair.position.set(x, top - (epi + der * 0.7) / 2 + 0.25, zf - 0.05); hair.rotation.z = (r() - 0.5) * 0.25; block.add(hair); fol.push({ x, tube, hair }); }
    for (let i = 0; i < 26; i++) { const s = 0.06 + r() * 0.07; const m = new THREE.Mesh(new THREE.SphereGeometry(s, 14, 10), std([1, 0.9, 0.55], { roughness: 0.3 })); m.position.set((r() - 0.5) * W * 0.95, yD - fat * (0.15 + r() * 0.7), zf - s * 0.6); block.add(m); }
    const site = pt('lesion', [0, top, 0.1]); const sx = site.x;
    const redden = (m, base, k) => m.material.color.setRGB(base[0] + (0.95 - base[0]) * k, base[1] * (1 - 0.65 * k), base[2] * (1 - 0.65 * k));
    // germs used by several conditions
    const germN = 160, germ = inst(new THREE.CapsuleGeometry(0.018, 0.045, 4, 8), std(C === 'fungal' ? [0.85, 0.9, 0.6] : [0.45, 0.85, 0.25], { emissive: new THREE.Color(0.12, 0.3, 0.05), roughness: 0.4 }), germN, 12);
    const gs = Array.from({ length: germN }, () => ({ x: (r() - 0.5), y: r(), z: r(), at: r(), ph: r() * 6.28 })); block.add(germ);
    const wbcN = 22, wbc = inst(new THREE.IcosahedronGeometry(0.05, 2), std([0.95, 0.95, 1], { roughness: 0.6 }), wbcN, 12); block.add(wbc); const ws = Array.from({ length: wbcN }, () => ({ x: (r() - 0.5), y: r(), at: 0.3 + r() * 0.5, ph: r() * 6.28 }));
    const swell = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 24), glow([0.9, 0.12, 0.08], 0)); swell.renderOrder = 11; block.add(swell);
    let pus = null, plug = null, crack = null, blisters = [], scales = [], hyphae = null, gap = null;
    if (C === 'abscess') { pus = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 28), std([0.98, 0.92, 0.55], { roughness: 0.25, transparent: true, opacity: 0.95 })); pus.position.set(sx, yE - der * 0.3, zf - 0.25); block.add(pus);
      const wall = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 28), glass([0.9, 0.2, 0.15], 0.35)); pus.add(wall); wall.scale.setScalar(1.18); }
    if (C === 'acne') { const fo = fol.reduce((a, b) => (Math.abs(a.x - sx) < Math.abs(b.x - sx) ? a : b)); plug = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), std([0.95, 0.88, 0.62], { roughness: 0.35 })); plug.position.set(fo.x, top - epi * 0.8, zf - 0.05); block.add(plug); site.x = fo.x; }
    if (C === 'eczema' || C === 'psoriasis') { for (let i = 0; i < 18; i++) { const sc_ = new THREE.Mesh(new THREE.BoxGeometry(0.16 + r() * 0.2, C === 'psoriasis' ? 0.06 : 0.035, 0.16 + r() * 0.2), std(C === 'psoriasis' ? [0.86, 0.88, 0.92] : [0.82, 0.62, 0.55], { roughness: 0.95, metalness: C === 'psoriasis' ? 0.15 : 0 }));
        sc_.position.set(sx + (r() - 0.5) * 1.6, top + 0.015, (r() - 0.5) * H * 0.9); sc_.rotation.set((r() - 0.5) * 0.4, r() * 3, (r() - 0.5) * 0.4); sc_.userData.at = r(); block.add(sc_); scales.push(sc_); } }
    if (C === 'eczema') { const pts = []; for (let i = 0; i < 9; i++) { let x = sx + (r() - 0.5) * 1.4, z = (r() - 0.5) * H * 0.9; for (let k = 0; k < 4; k++) { const x2 = x + (r() - 0.5) * 0.35, z2 = z + (r() - 0.5) * 0.35; pts.push(x, top + 0.004, z, x2, top + 0.004, z2); x = x2; z = z2; } }
      crack = new THREE.Group(); block.add(crack); const cm = std([0.42, 0.08, 0.06], { roughness: 0.9 });      // cracks: dark strips cut into the surface, wide enough to read on screen
      for (let i = 0; i < pts.length; i += 6) { const p0 = new THREE.Vector3(pts[i], pts[i + 1], pts[i + 2]), p1 = new THREE.Vector3(pts[i + 3], pts[i + 4], pts[i + 5]); const m = new THREE.Mesh(new THREE.BoxGeometry(p0.distanceTo(p1), 0.012, 0.028), cm);
        m.position.copy(p0.clone().lerp(p1, 0.5)); m.rotation.y = -Math.atan2(p1.z - p0.z, p1.x - p0.x); m.userData.at = r(); crack.add(m); }
      for (let i = 0; i < 16; i++) { const b = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2), std([0.86, 0.3, 0.28], { roughness: 0.5 })); b.position.set(sx + (r() - 0.5) * 1.5, top, (r() - 0.5) * H * 0.85); b.userData = { s: 0.03 + r() * 0.04, at: r() }; block.add(b); blisters.push(b); } }
    if (C === 'burn') for (let i = 0; i < 7; i++) { const b = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 14, 0, Math.PI * 2, 0, Math.PI / 2), glass([0.98, 0.94, 0.8], 0.75, { side: THREE.FrontSide })); b.position.set(sx + (r() - 0.5) * 1.3, top, (r() - 0.5) * H * 0.8); b.userData = { s: 0.07 + r() * 0.1, at: r() * 0.5 }; block.add(b); blisters.push(b); }
    let ringP = null, base = null;
    if (C === 'fungal') { ringP = new THREE.Mesh(new THREE.TorusGeometry(1, 0.05, 10, 64), std([0.78, 0.22, 0.2], { roughness: 0.6 })); ringP.rotation.x = Math.PI / 2; ringP.position.set(sx, top + 0.01, 0); block.add(ringP); }      // the red ring ringworm is named for
    if (C === 'psoriasis' || C === 'eczema') { base = new THREE.Mesh(new THREE.CircleGeometry(1, 48), std([0.82, 0.3, 0.3], { roughness: 0.7 })); base.rotation.x = -Math.PI / 2; base.position.set(sx, top + 0.006, 0); block.add(base); }      // the inflamed patch under the scales
    if (C === 'fungal') { const segs = []; const grow = (x, y, z, dx, dy, depth) => { for (let i = 0; i < 5 && depth < 5; i++) { const x2 = x + dx * 0.12 + (r() - 0.5) * 0.06, y2 = Math.max(yE + 0.01, Math.min(top - 0.005, y + dy * 0.03 + (r() - 0.5) * 0.02)), z2 = z + (r() - 0.5) * 0.12;
          segs.push({ a: [x, y, z], b: [x2, y2, z2], d: depth + i / 5 }); x = x2; y = y2; z = z2; if (r() < 0.35) grow(x, y, z, dx * (r() < 0.5 ? -1 : 1), -1, depth + 1); } };
      for (let k = 0; k < 6; k++) grow(sx + (r() - 0.5) * 0.4, top - 0.02, (r() - 0.5) * 0.6, r() < 0.5 ? -1 : 1, -1, 0);
      hyphae = { segs, mesh: inst(new THREE.CylinderGeometry(0.016, 0.016, 1, 6), std([0.92, 0.95, 0.45], { emissive: new THREE.Color(0.3, 0.32, 0.05) }), segs.length, 13) }; block.add(hyphae.mesh); }
    if (C === 'wound') { gap = new THREE.Mesh(new THREE.BoxGeometry(0.22, epi + der * 0.75, H * 1.01), std([0.55, 0.05, 0.07], { roughness: 0.3 })); gap.position.set(sx, top - (epi + der * 0.75) / 2 + 0.005, 0); block.add(gap); }
    upd.push((f) => {
      const p = f.proc?.prog ?? 0, t = f.t;
      const infl = C === 'cellulitis' ? ramp(p, 0.1, 0.9) : C === 'abscess' ? ramp(p, 0.2, 0.8) * 0.8 : C === 'acne' ? ramp(p, 0.5, 1) * 0.7 : C === 'eczema' ? ramp(p, 0.2, 0.8) * 0.6 : C === 'psoriasis' ? ramp(p, 0.2, 0.8) * 0.45 : C === 'burn' ? ramp(p, 0.0, 0.5) : C === 'wound' ? 0.5 * (1 - ramp(p, 0.4, 1)) : 0;
      redden(mD, [0.76, 0.4, 0.4], infl * (C === 'cellulitis' ? 0.9 : 0.6)); redden(mE, [0.8, 0.58, 0.5], infl * 0.45);
      if (C === 'burn') { const dg = P.degree ?? 2; const ch = ramp(p, 0.35, 1); mE.material.color.setRGB(0.86 - (dg >= 2 ? 0.25 : 0.05) * ch - (dg >= 3 ? 0.45 : 0) * ch, 0.66 - 0.35 * ch - (dg >= 3 ? 0.2 : 0) * ch, 0.58 - 0.4 * ch - (dg >= 3 ? 0.15 : 0) * ch);
        if (dg >= 3) mD.material.color.setRGB(0.84 - 0.55 * ch, 0.52 - 0.4 * ch, 0.5 - 0.4 * ch);
        blisters.forEach((b) => { const g = dg === 2 ? ramp(p, 0.3 + b.userData.at, 0.65 + b.userData.at) : 0; b.visible = g > 0.01; b.scale.set(b.userData.s * g, b.userData.s * g * 0.8, b.userData.s * g); }); }
      const sw = C === 'cellulitis' ? 0.45 + 0.6 * infl : 0.35; swell.position.set(sx, yE - der * 0.35, zf - 0.35); swell.scale.set(Math.min(1.15, sw * 1.3), Math.min(0.26, sw * 0.32), Math.min(0.32, sw * 0.5)); swell.material.opacity = 0.28 * infl;
      mE.scale.y = C === 'psoriasis' ? 1 + 1.4 * ramp(p, 0.1, 0.8) : C === 'cellulitis' || C === 'abscess' ? 1 + 0.4 * infl : 1; mE.position.y = top - epi * mE.scale.y / 2 + (mE.scale.y - 1) * epi;
      // germs: spread outward from the site through the dermis (cellulitis), gather in the pocket (abscess), sit in the plug (acne)
      let ng = 0; const want = C === 'cellulitis' ? 1 : C === 'abscess' ? 0.6 : C === 'acne' ? 0.35 : C === 'wound' ? 0.25 * (1 - ramp(p, 0.3, 0.8)) : 0;
      gs.forEach((g, i) => { const on = want > 0 && g.at < want ? ramp(p, g.at * 0.6, g.at * 0.6 + 0.25) : 0; if (on < 0.02) return;
        let x, y, z; if (C === 'abscess') { const a = g.ph + t * 0.2, rr = 0.22 * Math.cbrt(g.z) * (0.4 + 0.6 * ramp(p, 0.1, 0.7)); x = pus.position.x + Math.cos(a) * rr; y = pus.position.y + (g.y - 0.5) * rr; z = pus.position.z + Math.sin(a) * rr * 0.6; }
        else if (C === 'acne') { x = site.x + (g.x) * 0.08; y = top - epi - g.y * der * 0.5; z = zf - 0.06 + g.z * 0.03; }
        else { const spread = 0.15 + 1.1 * ramp(p, 0.1, 1); x = sx + g.x * spread * 2; y = yE - g.y * der * 0.85; z = zf - 0.02 - g.z * 0.08; }
        setI(germ, ng++, x + Math.sin(t * 0.8 + g.ph) * 0.01, y, z, on, g.ph, t * 0.5 + g.ph, 0); });
      germ.count = ng; germ.instanceMatrix.needsUpdate = true;
      let nw = 0; ws.forEach((w) => { const on = (C === 'cellulitis' || C === 'abscess' || C === 'acne' || C === 'wound') ? ramp(p, w.at, w.at + 0.2) : 0; if (on < 0.02) return;
        const x = (C === 'abscess' ? pus.position.x : sx) + w.x * (C === 'abscess' ? 0.7 : 1.4) * on; setI(wbc, nw++, x, ves.position.y + 0.05 + w.y * 0.3 * on, zf - 0.04, on, t * 0.3 + w.ph, t * 0.2, 0); });
      wbc.count = nw; wbc.instanceMatrix.needsUpdate = true;
      if (pus) { const s = 0.06 + 0.24 * ramp(p, 0.15, 0.85); pus.scale.set(s * 1.3, s, s); mE.position.y += 0.06 * ramp(p, 0.5, 1); }
      if (plug) { const s = 0.03 + 0.08 * ramp(p, 0.05, 0.6); plug.scale.set(s, s * 1.4, s); swell.position.set(site.x, top - epi - 0.08, zf - 0.08); swell.scale.setScalar(0.12 + 0.2 * ramp(p, 0.5, 1)); swell.material.opacity = 0.5 * ramp(p, 0.5, 1); }
      if (crack) crack.children.forEach((m) => { const g = ramp(p, 0.1 + m.userData.at * 0.4, 0.3 + m.userData.at * 0.4); m.visible = g > 0.01; m.scale.set(g, 1, 1); });
      if (C === 'eczema') blisters.forEach((b) => { const g = ramp(p, 0.2 + b.userData.at * 0.5, 0.4 + b.userData.at * 0.5); b.visible = g > 0.01; b.scale.set(b.userData.s * g, b.userData.s * g * 0.7, b.userData.s * g); });
      if (ringP) { const g = ramp(p, 0.1, 0.9); ringP.visible = g > 0.01; ringP.scale.set(0.15 + 0.75 * g, 0.15 + 0.75 * g, 1 + 0.5 * g); }
      if (base) { const g = ramp(p, 0.1, 0.7); base.visible = g > 0.01; base.scale.setScalar(0.1 + 0.75 * g); base.position.y = mE.position.y + epi * mE.scale.y / 2 + 0.004; }
      scales.forEach((s) => { const g = ramp(p, 0.2 + s.userData.at * 0.5, 0.45 + s.userData.at * 0.5); s.visible = g > 0.01; s.scale.setScalar(g); s.position.y = mE.position.y + epi * mE.scale.y / 2 + 0.02; });      // scales sit on the epidermis as it thickens
      if (hyphae) { let n = 0; hyphae.segs.forEach((sg) => { const g = ramp(p, sg.d / 6, sg.d / 6 + 0.2); if (g < 0.02) return; const a = new THREE.Vector3(...sg.a), b = new THREE.Vector3(...sg.b); const mid = a.clone().lerp(b, 0.5 * g); const len = a.distanceTo(b) * g;
          dm.position.copy(a.clone().lerp(mid, 1)); dm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize()); dm.scale.set(1, len, 1); dm.position.copy(a.clone().add(b.clone().sub(a).multiplyScalar(g / 2))); dm.updateMatrix(); hyphae.mesh.setMatrixAt(n++, dm.matrix); });
        hyphae.mesh.count = n; hyphae.mesh.instanceMatrix.needsUpdate = true; mE.material.color.lerp(new THREE.Color(0.8, 0.78, 0.62), 0.3 * ramp(p, 0.3, 1)); }
      if (gap) { const c = 1 - ramp(p, 0.15, 0.95); gap.scale.x = Math.max(0.02, c); gap.material.color.setRGB(0.55 + 0.3 * (1 - c), 0.05 + 0.45 * (1 - c), 0.07 + 0.4 * (1 - c)); }
    });
  }

  // ---------------------------------------------------------------- cells and germs
  const cellMesh = (rad, col, op = 0.28) => { const g = new THREE.Group(); const mem = new THREE.Mesh(new THREE.SphereGeometry(rad, 64, 40), glass(col, op)); mem.renderOrder = 4; g.add(mem);
    const nuc = new THREE.Mesh(new THREE.SphereGeometry(rad * 0.34, 32, 22), std([0.45, 0.28, 0.65], { roughness: 0.5 })); nuc.position.set(-rad * 0.1, rad * 0.05, 0); g.add(nuc); g.userData = { mem, nuc }; return g; };
  const virusGeo = (() => { const g = new THREE.Group(); const core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.07, 2), std([0.85, 0.2, 0.3], { roughness: 0.4 })); g.add(core);
    const spikeG = new THREE.CylinderGeometry(0.006, 0.012, 0.035, 6); const spikeM = std([0.95, 0.55, 0.3]); const ico = new THREE.IcosahedronGeometry(0.07, 1).attributes.position;
    for (let i = 0; i < ico.count; i += 3) { const v = new THREE.Vector3(ico.getX(i), ico.getY(i), ico.getZ(i)).normalize(); const s = new THREE.Mesh(spikeG, spikeM); s.position.copy(v.clone().multiplyScalar(0.085)); s.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), v); g.add(s); } return g; });
  if (K === 'virus') {
    const cell = cellMesh(0.9, [0.55, 0.78, 0.95]); cell.position.copy(pt('cell', [0, -0.2, 0])); group.add(cell);
    const NV = 7 + Math.floor(r() * 4), vs = [];
    for (let i = 0; i < NV; i++) { const v = virusGeo(); group.add(v); const a = r() * 6.28, el = (r() - 0.2) * 1.2; const dir = new THREE.Vector3(Math.cos(a) * Math.cos(el), Math.sin(el) + 0.3, Math.sin(a) * Math.cos(el)).normalize(); vs.push({ v, dir, at: r() * 0.35, ph: r() * 6.28, enter: i < Math.ceil(NV * 0.6) }); }
    const NC = 40, copies = inst(new THREE.IcosahedronGeometry(0.035, 1), std([0.85, 0.2, 0.3], { roughness: 0.4 }), NC, 9); const cp = Array.from({ length: NC }, () => ({ d: new THREE.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).normalize(), rr: 0.15 + r() * 0.55, at: 0.55 + r() * 0.3 }));
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t; const c = cell.position;
      vs.forEach((o) => { const k = ramp(p, o.at, o.at + 0.35); const far = 2.2 - 1.25 * k - (o.enter ? 0.55 * ramp(p, o.at + 0.35, o.at + 0.55) : 0); o.v.position.copy(c).add(o.dir.clone().multiplyScalar(far)); o.v.position.y += Math.sin(t * 0.7 + o.ph) * 0.03 * (1 - k); o.v.rotation.set(t * 0.4 + o.ph, t * 0.3, 0); o.v.scale.setScalar(o.enter ? 1 - 0.6 * ramp(p, o.at + 0.45, o.at + 0.6) : 1); });
      let n = 0; cp.forEach((q) => { const g = ramp(p, q.at, q.at + 0.15); if (g < 0.02) return; const out = q.rr + 0.6 * ramp(p, 0.88, 1); setI(copies, n++, c.x + q.d.x * out, c.y + q.d.y * out, c.z + q.d.z * out, g, t + q.rr * 9, t * 0.7, 0); }); copies.count = n; copies.instanceMatrix.needsUpdate = true;
      cell.userData.nuc.material.color.setRGB(0.45 + 0.35 * ramp(p, 0.5, 0.9), 0.28 - 0.1 * ramp(p, 0.5, 0.9), 0.65 - 0.3 * ramp(p, 0.5, 0.9)); cell.rotation.y = t * 0.05; });
  }
  if (K === 'immune') {
    const NB = 26 + Math.floor(r() * 10), bact = inst(new THREE.CapsuleGeometry(0.05, 0.12, 6, 12), std([0.45, 0.85, 0.25], { emissive: new THREE.Color(0.1, 0.25, 0.04), roughness: 0.4 }), NB, 9);
    const bc = pt('bacteria', [0.3, 0, 0]); const bs = Array.from({ length: NB }, () => ({ o: new THREE.Vector3((r() - 0.5) * 0.9, (r() - 0.5) * 0.7, (r() - 0.5) * 0.6), ph: r() * 6.28, eat: r() }));
    const NW = 3 + Math.floor(r() * 2), wb = []; for (let i = 0; i < NW; i++) { const g = new THREE.Mesh(new THREE.IcosahedronGeometry(0.32, 4), std([0.92, 0.93, 1], { roughness: 0.65, transparent: true, opacity: 0.78 }));
      const pa = g.geometry.attributes.position; for (let k = 0; k < pa.count; k++) { const v = new THREE.Vector3(pa.getX(k), pa.getY(k), pa.getZ(k)); v.multiplyScalar(1 + (Math.sin(v.x * 30 + i) * Math.cos(v.y * 27) * 0.06)); pa.setXYZ(k, v.x, v.y, v.z); } g.geometry.computeVertexNormals();
      const nu = new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 14), std([0.55, 0.35, 0.75])); g.add(nu); g.renderOrder = 11; group.add(g); const a = (i / NW) * 6.28 + r(); wb.push({ g, from: new THREE.Vector3(Math.cos(a) * 2.2, Math.sin(a) * 1.2, -0.4), ph: r() * 6.28 }); }
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t;
      wb.forEach((w, i) => { const k = ramp(p, 0.05 + i * 0.05, 0.55 + i * 0.05); w.g.position.copy(w.from.clone().lerp(bc.clone().add(new THREE.Vector3(Math.cos(i * 2.1) * 0.25, Math.sin(i * 2.1) * 0.2, 0.1)), k)); w.g.rotation.set(t * 0.2 + w.ph, t * 0.15, 0); w.g.scale.setScalar(1 + 0.06 * Math.sin(t * 2 + w.ph)); });
      let n = 0; bs.forEach((b) => { const gone = ramp(p, 0.45 + b.eat * 0.4, 0.55 + b.eat * 0.4); if (gone > 0.98) return; const w = wb[Math.floor(b.eat * NW) % NW].g.position;
        const pos = bc.clone().add(b.o).lerp(w, gone * 0.9); setI(bact, n++, pos.x + Math.sin(t + b.ph) * 0.02, pos.y, pos.z, 1 - gone * 0.8, b.ph + t * 0.3, b.ph, 0); }); bact.count = n; bact.instanceMatrix.needsUpdate = true; });
  }
  if (K === 'insulin') {
    // a patch of cell membrane seen from the side, the blood above it: insulin binds receptors, channels open, glucose moves into the cell
    const mem = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.16, 1.6, 60, 1, 20), std([0.95, 0.75, 0.55], { roughness: 0.6 })); mem.position.y = -0.2; group.add(mem);
    const heads = inst(new THREE.SphereGeometry(0.035, 10, 8), std([0.98, 0.85, 0.65]), 400, 6); let n = 0; for (let x = -2; x <= 2; x += 0.1) for (let z = -0.75; z <= 0.75; z += 0.16) { setI(heads, n++, x, -0.11, z, 1); setI(heads, n++, x, -0.29, z, 1); } heads.count = n; heads.instanceMatrix.needsUpdate = true;
    const NR = 5, recs = []; for (let i = 0; i < NR; i++) { const x = -1.6 + i * 0.8 + (r() - 0.5) * 0.2; const g = new THREE.Group(); g.position.set(x, -0.2, (r() - 0.5) * 0.6); const st = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.42, 14), std([0.35, 0.6, 0.95])); g.add(st);
      const yk = new THREE.Mesh(new THREE.TorusGeometry(0.09, 0.03, 10, 20, Math.PI), std([0.35, 0.6, 0.95])); yk.position.y = 0.27; g.add(yk); const ch = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.2, 16, 1, true), glow([0.5, 1, 0.7], 0)); ch.position.x = 0.22; g.add(ch); group.add(g);
      const ins = new THREE.Mesh(new THREE.DodecahedronGeometry(0.06, 0), std([1, 0.75, 0.2], { emissive: new THREE.Color(0.35, 0.2, 0) })); group.add(ins); recs.push({ g, ch, ins, at: i / NR * 0.4, from: new THREE.Vector3(x + (r() - 0.5) * 1.2, 1.4 + r() * 0.4, (r() - 0.5) * 0.8) }); }
    const NG = 90, glu = inst(new THREE.CylinderGeometry(0.035, 0.035, 0.02, 6), std([0.4, 0.95, 0.85], { emissive: new THREE.Color(0.05, 0.25, 0.2) }), NG, 8); const gs = Array.from({ length: NG }, () => ({ x: (r() - 0.5) * 4, y: 0.2 + r() * 1.3, z: (r() - 0.5) * 1.4, rec: Math.floor(r() * NR), at: r(), ph: r() * 6.28 }));
    const resist = P.resistance ?? 0;      // 0 = a healthy response; 1 = insulin resistance (receptors bind but few channels open)
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t;
      recs.forEach((q, i) => { const k = ramp(p, q.at, q.at + 0.25); q.ins.position.copy(q.from.clone().lerp(q.g.position.clone().add(new THREE.Vector3(0, 0.33, 0)), k)); q.ins.rotation.set(t, t * 0.6, 0); q.ch.material.opacity = 0.6 * ramp(p, q.at + 0.25, q.at + 0.35) * (i / NR >= resist ? 1 : 0.15); });
      let n = 0; gs.forEach((g) => { const q = recs[g.rec]; const open = q.ch.material.opacity > 0.3; const k = open ? ramp(p, 0.4 + g.at * 0.5, 0.55 + g.at * 0.5) : 0; const gate = q.g.position.clone().add(new THREE.Vector3(0.22, 0, 0));
        const free = new THREE.Vector3(g.x + Math.sin(t * 0.3 + g.ph) * 0.15, g.y + Math.sin(t * 0.4 + g.ph) * 0.05, g.z); const pos = k < 0.5 ? free.lerp(gate, k * 2) : gate.clone().add(new THREE.Vector3(0, -(k - 0.5) * 2 * 0.9, 0));
        setI(glu, n++, pos.x, pos.y, pos.z, 1, Math.PI / 2, t * 0.5 + g.ph, 0); }); glu.count = n; glu.instanceMatrix.needsUpdate = true; });
  }
  if (K === 'neuron') {
    const a0 = pt('axon_start', [-2.2, 0.3, 0]), a1 = pt('synapse', [1.0, 0, 0]);
    const curve = new THREE.CatmullRomCurve3([a0, a0.clone().add(new THREE.Vector3(0.8, 0.25 + r() * 0.2, 0.1)), a1.clone().add(new THREE.Vector3(-0.9, -0.2, -0.1)), a1]);
    const axon = new THREE.Mesh(new THREE.TubeGeometry(curve, 120, 0.07, 14), std([0.95, 0.82, 0.55], { roughness: 0.45 })); group.add(axon);
    const soma = new THREE.Mesh(new THREE.IcosahedronGeometry(0.4, 4), std([0.95, 0.75, 0.5], { roughness: 0.5 })); soma.position.copy(a0).add(new THREE.Vector3(-0.3, 0, 0)); group.add(soma);
    for (let i = 0; i < 9; i++) { const a = r() * 6.28; const d = new THREE.Vector3(Math.cos(a), Math.sin(a), (r() - 0.5)).normalize(); const c2 = new THREE.CatmullRomCurve3([soma.position.clone(), soma.position.clone().add(d.clone().multiplyScalar(0.6)), soma.position.clone().add(d.clone().multiplyScalar(1.0)).add(new THREE.Vector3(r() - 0.5, r() - 0.5, 0).multiplyScalar(0.3))]);
      group.add(new THREE.Mesh(new THREE.TubeGeometry(c2, 20, 0.03, 8), std([0.95, 0.75, 0.5]))); }
    const knob = new THREE.Mesh(new THREE.SphereGeometry(0.22, 30, 20), std([0.95, 0.82, 0.55])); knob.position.copy(a1); group.add(knob);
    const post = new THREE.Mesh(new THREE.SphereGeometry(0.4, 30, 20, 0, Math.PI * 2, 0, Math.PI / 2), std([0.6, 0.75, 0.95], { side: THREE.DoubleSide })); post.rotation.z = Math.PI / 2; post.position.copy(a1).add(new THREE.Vector3(0.62, 0, 0)); group.add(post);
    const spark = new THREE.Mesh(new THREE.SphereGeometry(0.12, 20, 14), glow([0.6, 0.9, 1], 0.9)); group.add(spark);
    const NT = 70, nt = inst(new THREE.SphereGeometry(0.022, 8, 6), glow([1, 0.85, 0.4], 0.95), NT, 12); const ns = Array.from({ length: NT }, () => ({ y: (r() - 0.5) * 0.3, z: (r() - 0.5) * 0.3, sp: 0.5 + r(), ph: r() }));
    const rate = P.rate ?? 1.2;
    upd.push((f) => { const t = f.t, p = f.proc?.prog ?? 1; const u = ((t * rate * 0.5) % 1); spark.position.copy(curve.getPoint(Math.min(1, u * 1.1))); spark.material.opacity = 0.9 * (u < 0.92 ? 1 : 0); spark.scale.setScalar(1 + 0.3 * Math.sin(t * 9));
      const rel = ramp(u, 0.85, 1) + (u < 0.3 ? 1 - ramp(u, 0, 0.3) : 0); let n = 0; ns.forEach((q) => { const k = ((u + 1 - 0.88 + q.ph * 0.05) % 1) * q.sp; if (k > 0.5 || rel < 0.05) return; setI(nt, n++, a1.x + 0.18 + k * 0.6, a1.y + q.y * (0.4 + k), a1.z + q.z * (0.4 + k), p); }); nt.count = n; nt.instanceMatrix.needsUpdate = true; });
  }
  if (K === 'cancer') {
    const NC = 18, cells = []; const c0 = pt('tumour', [0, 0, 0]);
    for (let i = 0; i < NC; i++) { const ab = i >= 3; const g = new THREE.Mesh(new THREE.IcosahedronGeometry(0.26, 3), std(ab ? [0.85, 0.42, 0.62] : [0.95, 0.72, 0.68], { roughness: 0.5 }));
      if (ab) { const pa = g.geometry.attributes.position; for (let k = 0; k < pa.count; k++) { const v = new THREE.Vector3(pa.getX(k), pa.getY(k), pa.getZ(k)); v.multiplyScalar(1 + 0.18 * Math.sin(v.x * 18 + i) * Math.cos(v.z * 15 + i * 2)); pa.setXYZ(k, v.x, v.y, v.z); } g.geometry.computeVertexNormals(); }
      const n = new THREE.Mesh(new THREE.SphereGeometry(0.1 * (ab ? 1.4 : 1), 16, 12), std(ab ? [0.4, 0.1, 0.4] : [0.45, 0.28, 0.65])); g.add(n); group.add(g);
      const a = i * 2.399, rr = ab ? 0.12 + 0.11 * Math.sqrt(i) : 1.15 + r() * 0.2; const pos = i === 0 ? pt('normal', [1.3, 0.2, 0]) : new THREE.Vector3(Math.cos(a) * rr, Math.sin(a * 1.3) * rr * 0.7, Math.sin(a) * rr * 0.6).add(c0);
      cells.push({ g, at: ab ? (i - 3) / (NC - 3) : -1, pos, ph: r() * 6.28 }); }
    const vessel = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([c0.clone().add(new THREE.Vector3(-2.5, -1.2, -0.4)), c0.clone().add(new THREE.Vector3(-1.2, -0.6, -0.1)), c0.clone().add(new THREE.Vector3(-0.3, -0.15, 0))]), 60, 0.05, 10), std([0.75, 0.1, 0.12])); group.add(vessel);
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t; cells.forEach((c) => { const g = c.at < 0 ? 1 : ramp(p, c.at * 0.85, c.at * 0.85 + 0.12); c.g.visible = g > 0.01; c.g.position.copy(c.pos); c.g.scale.setScalar(g * (1 + 0.04 * Math.sin(t + c.ph))); c.g.rotation.y = t * 0.1 + c.ph; });
      vessel.scale.setScalar(Math.max(0.01, ramp(p, 0.55, 0.95))); group.rotation.y = Math.sin(t * 0.08) * 0.2; });
  }

  // ---------------------------------------------------------------- lungs: an airway (asthma) and air sacs (healthy, pneumonia, emphysema)
  if (K === 'airway') {
    const L = 4.4, R = 0.62; const wallG = new THREE.CylinderGeometry(R, R, L, 64, 40, true); wallG.rotateZ(Math.PI / 2); const base = wallG.attributes.position.array.slice();
    const wall = new THREE.Mesh(wallG, std([0.92, 0.6, 0.6], { side: THREE.DoubleSide, transparent: true, opacity: 0.55, roughness: 0.4 })); group.add(wall);
    const rings = []; for (let i = 0; i < 9; i++) { const ring = new THREE.Mesh(new THREE.TorusGeometry(R + 0.04, 0.035, 10, 40), std([0.95, 0.42, 0.42], { roughness: 0.6 })); ring.rotation.y = Math.PI / 2; ring.position.x = -L / 2 + 0.3 + i * (L - 0.6) / 8; group.add(ring); rings.push(ring); }
    const mucus = new THREE.Mesh(new THREE.CylinderGeometry(R, R, L * 0.7, 48, 1, true), std([0.92, 0.95, 0.75], { transparent: true, opacity: 0, side: THREE.DoubleSide, roughness: 0.2 })); mucus.rotation.z = Math.PI / 2; group.add(mucus);
    const NA = 120, air = inst(new THREE.SphereGeometry(0.03, 8, 6), glow([0.7, 0.9, 1], 0.9), NA, 9); const as_ = Array.from({ length: NA }, () => ({ x: r() * L, a: r() * 6.28, d: Math.sqrt(r()), sp: 0.6 + r() * 0.6 }));
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t; const squeeze = 0.55 * ramp(p, 0.15, 0.85); const pa = wallG.attributes.position;
      for (let i = 0; i < pa.count; i++) { const x = base[i * 3], y = base[i * 3 + 1], z = base[i * 3 + 2]; const k = 1 - squeeze * Math.exp(-(x * x) / 1.6) * (0.85 + 0.15 * Math.sin(Math.atan2(z, y) * 6)); pa.setXYZ(i, x, y * k, z * k); } pa.needsUpdate = true; wallG.computeVertexNormals();
      rings.forEach((rg) => { const k = 1 - squeeze * Math.exp(-(rg.position.x ** 2) / 1.6); rg.scale.set(k, k, 1); }); mucus.scale.set(1 - squeeze * 0.75, 1, 1 - squeeze * 0.75); mucus.material.opacity = 0.5 * ramp(p, 0.35, 0.9);
      let n = 0; as_.forEach((q) => { const xx = ((q.x + t * q.sp * (1 - 0.7 * squeeze)) % L) - L / 2; const lim = R * 0.85 * (1 - squeeze * Math.exp(-(xx * xx) / 1.6)); setI(air, n++, xx, Math.cos(q.a) * q.d * lim, Math.sin(q.a) * q.d * lim, 1); }); air.count = n; air.instanceMatrix.needsUpdate = true; });
  }
  if (K === 'alveoli') {
    const sacs = []; const root = pt('cluster', [0, 0, 0]); const br = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3([root.clone().add(new THREE.Vector3(0, 2.2, -0.2)), root.clone().add(new THREE.Vector3(0, 0.9, 0))]), 30, 0.12, 12), std([0.95, 0.6, 0.6])); group.add(br);
    for (let i = 0; i < 26; i++) { const a = i * 2.399, el = Math.acos(1 - 2 * (i + 0.5) / 26); const d = new THREE.Vector3(Math.sin(el) * Math.cos(a), Math.cos(el), Math.sin(el) * Math.sin(a)); const s = 0.26 + r() * 0.08;
      const m = new THREE.Mesh(new THREE.SphereGeometry(1, 28, 18), glass([0.98, 0.68, 0.68], 0.6)); m.position.copy(root).add(d.clone().multiplyScalar(0.78)); m.scale.setScalar(s); m.renderOrder = 6; group.add(m); sacs.push({ m, s, d, at: r() }); }
    const cap = new THREE.Group(); group.add(cap); for (let i = 0; i < 26; i++) { const a = r() * 6.28; const c = new THREE.CatmullRomCurve3(Array.from({ length: 6 }, (_, k) => { const b = a + k * 0.6; return root.clone().add(new THREE.Vector3(Math.cos(b) * 1.05, (r() - 0.5) * 1.6, Math.sin(b) * 1.05)); }));
      cap.add(new THREE.Mesh(new THREE.TubeGeometry(c, 40, 0.018, 6), std(i % 2 ? [0.75, 0.12, 0.16] : [0.3, 0.32, 0.75]))); }
    const NO = 90, ox = inst(new THREE.SphereGeometry(0.022, 8, 6), glow([0.6, 0.85, 1], 0.9), NO, 9); const os = Array.from({ length: NO }, () => ({ s: Math.floor(r() * 26), ph: r(), sp: 0.4 + r() * 0.4 }));
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t; const br_ = 0.5 + 0.5 * Math.sin(t * 1.4);
      sacs.forEach((q, i) => { let s = q.s * (1 + 0.06 * br_); let col = [0.98, 0.68, 0.68], op = 0.6;
        if (C === 'pneumonia') { const k = ramp(p, q.at * 0.6, q.at * 0.6 + 0.4); col = [0.98 - 0.1 * k, 0.68 + 0.2 * k, 0.68 - 0.25 * k]; op = 0.6 + 0.35 * k; s *= 1 - 0.04 * br_ * k; }
        if (C === 'emphysema' && i % 3 === 0) { const k = ramp(p, q.at * 0.5, q.at * 0.5 + 0.4); s *= 1 + 0.9 * k; op = 0.6 - 0.35 * k; }
        q.m.scale.setScalar(s); q.m.material.color.setRGB(...col); q.m.material.opacity = op; });
      let n = 0; os.forEach((o) => { const q = sacs[o.s]; const k = (t * o.sp + o.ph) % 1; const blocked = C === 'pneumonia' ? ramp(p, q.at * 0.6, q.at * 0.6 + 0.4) : 0; if (blocked > 0.6) return; const pos = root.clone().add(new THREE.Vector3(0, 2.0 * (1 - k), 0)).lerp(q.m.position, Math.min(1, k * 1.3)); setI(ox, n++, pos.x, pos.y, pos.z, 1); });
      ox.count = n; ox.instanceMatrix.needsUpdate = true; group.rotation.y = t * 0.06; });
  }

  // ---------------------------------------------------------------- bone (osteoporosis), joint (arthritis), vessel (aneurysm)
  if (K === 'bone') {      // osteoporosis: every strut of the spongy bone thins; about four in ten break, never all
    const NR = 260, rods = inst(new THREE.CylinderGeometry(1, 1, 1, 6), std([0.86, 0.8, 0.66], { roughness: 0.75 }), NR, 6); const nodes = Array.from({ length: 90 }, () => new THREE.Vector3((r() - 0.5) * 2.2, (r() - 0.5) * 2.2, (r() - 0.5) * 1.4));
    const links = []; nodes.forEach((a, i) => { const near = nodes.map((b, j) => [a.distanceTo(b), j]).filter(([d, j]) => j > i && d < 0.62).sort((x, y) => x[0] - y[0]).slice(0, 3); near.forEach(([, j]) => links.push({ a, b: nodes[j], w: 0.045 + r() * 0.03, at: r() })); });
    const shell = new THREE.Mesh(new THREE.CylinderGeometry(1.35, 1.35, 2.5, 48, 1, true), glass([0.95, 0.92, 0.85], 0.12)); group.add(shell);
    upd.push((f) => { const p = f.proc?.prog ?? 0; let n = 0; links.slice(0, NR).forEach((l) => { const thin = 1 - 0.55 * ramp(p, 0.1, 0.9); const lost = l.at < 0.4 ? ramp(p, 0.3 + l.at, 0.42 + l.at) : 0; if (lost > 0.95) return; const len = l.a.distanceTo(l.b) * (1 - 0.5 * lost);
        dm.position.copy(l.a.clone().lerp(l.b, 0.5)); dm.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), l.b.clone().sub(l.a).normalize()); dm.scale.set(l.w * thin, len, l.w * thin); dm.updateMatrix(); rods.setMatrixAt(n++, dm.matrix); }); rods.count = n; rods.instanceMatrix.needsUpdate = true; group.rotation.y = f.t * 0.08; });
  }
  if (K === 'joint') {
    const BONE = [0.72, 0.66, 0.55]; const top = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.55, 2.2, 40), std(BONE, { roughness: 0.65 })); top.position.y = 1.35; group.add(top);
    const cap1 = new THREE.Mesh(new THREE.SphereGeometry(0.85, 40, 24, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), std(BONE, { roughness: 0.65 })); cap1.position.y = 0.3; cap1.scale.y = 0.45; group.add(cap1);
    const bot = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.72, 2.2, 40), std(BONE, { roughness: 0.65 })); bot.position.y = -1.45; group.add(bot);
    const plat = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.85, 0.2, 40), std(BONE, { roughness: 0.65 })); plat.position.y = -0.3; group.add(plat);
    const cartT = new THREE.Mesh(new THREE.SphereGeometry(0.87, 40, 24, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), std([0.65, 0.85, 0.98], { transparent: true, opacity: 0.85, roughness: 0.25 })); cartT.position.y = 0.28; cartT.scale.y = 0.5; group.add(cartT);
    const cartB = new THREE.Mesh(new THREE.CylinderGeometry(0.92, 0.92, 0.12, 40), std([0.65, 0.85, 0.98], { transparent: true, opacity: 0.85, roughness: 0.25 })); cartB.position.y = -0.14; group.add(cartB);
    const spurs = []; for (let i = 0; i < 6; i++) { const s = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.22, 10), std([0.95, 0.9, 0.78])); const a = r() * 6.28; s.position.set(Math.cos(a) * 0.9, i % 2 ? -0.25 : 0.2, Math.sin(a) * 0.9); s.rotation.z = Math.cos(a) * 1.4; s.rotation.x = -Math.sin(a) * 1.4; s.userData.at = r(); group.add(s); spurs.push(s); }
    const glowJ = new THREE.Mesh(new THREE.SphereGeometry(1.1, 30, 20), glow([0.95, 0.25, 0.1], 0)); glowJ.scale.y = 0.4; glowJ.position.y = 0.05; group.add(glowJ);
    upd.push((f) => { const p = f.proc?.prog ?? 0, t = f.t; const wear = ramp(p, 0.1, 0.85); cartT.scale.set(1 - 0.08 * wear, 0.5 * (1 - 0.8 * wear), 1 - 0.08 * wear); cartB.scale.set(1, 1 - 0.85 * wear, 1); cartT.material.color.setRGB(0.65 + 0.25 * wear, 0.85 - 0.1 * wear, 0.98 - 0.3 * wear);
      const close = 0.12 * wear; top.position.y = 1.35 - close; cap1.position.y = 0.3 - close; cartT.position.y = 0.28 - close; spurs.forEach((s) => { s.scale.setScalar(ramp(p, 0.4 + s.userData.at * 0.4, 0.6 + s.userData.at * 0.4)); });
      glowJ.material.opacity = 0.35 * ramp(p, 0.5, 1) * (0.7 + 0.3 * Math.sin(t * 2)); group.rotation.y = t * 0.1; });
  }
  if (K === 'aneurysm') {
    const L = 5, R = 0.5, SEG = 100, ANG = 48; const g = new THREE.CylinderGeometry(R, R, L, ANG, SEG, true); g.rotateZ(Math.PI / 2); const base = g.attributes.position.array.slice();
    const wall = new THREE.Mesh(g, std([0.78, 0.2, 0.22], { side: THREE.DoubleSide, transparent: true, opacity: 0.62, roughness: 0.35 })); group.add(wall); const side = r() * 6.28;
    const NC = 160, cells = inst(new THREE.SphereGeometry(1, 14, 8), std([0.8, 0.06, 0.09], { roughness: 0.42 }), NC, 8); const cs = Array.from({ length: NC }, () => ({ x: r() * L, a: r() * 6.28, d: Math.sqrt(r()), sp: 0.7 + r() * 0.5, ph: r() * 6.28 }));
    const bulge = (x, ang, p) => 1 + 1.1 * p * Math.exp(-(x * x) / 0.5) * (0.35 + 0.65 * Math.max(0, Math.cos(ang - side)));
    upd.push((f) => { const p = ramp(f.proc?.prog ?? 0, 0.05, 0.95), t = f.t; const pa = g.attributes.position; const beat = 1 + 0.03 * Math.max(0, Math.sin(t * 6.7));
      for (let i = 0; i < pa.count; i++) { const x = base[i * 3], y = base[i * 3 + 1], z = base[i * 3 + 2]; const k = bulge(x, Math.atan2(z, y), p) * beat; pa.setXYZ(i, x, y * k, z * k); } pa.needsUpdate = true; g.computeVertexNormals();
      wall.material.color.setRGB(0.78 + 0.1 * p, 0.2 - 0.08 * p, 0.22 - 0.08 * p);
      let n = 0; cs.forEach((c) => { const x = ((c.x + t * c.sp * 0.9) % L) - L / 2; const lim = R * 0.85 * bulge(x, c.a, p) * (Math.abs(x) < 0.8 ? 1 : 1); const ang = c.a + (Math.abs(x) < 0.8 ? t * 0.8 * p : 0);
        setI(cells, n++, x, Math.cos(ang) * c.d * lim, Math.sin(ang) * c.d * lim, 0.06, t + c.ph, t * 0.6, 0, 0.025); }); cells.instanceMatrix.needsUpdate = true; });
  }
  scene.add(new THREE.HemisphereLight(0xc8d4f0, 0x2a1a1a, 0.55));
  return { update(f) { upd.forEach((u) => u(f)); } };
}
