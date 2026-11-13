// Landmark models, built in code from simple shapes (our own low-poly art, no files). One parameterised model covers
// many cities: a dome church is Hagia Sophia in Istanbul and a cathedral elsewhere; a wall follows any path.
// Units: metres, origin at the landmark's centre on the ground, x east, z south. build(THREE, spec, groundY) -> Group.

export const KINDS = ['dome_church', 'mosque', 'cathedral', 'temple', 'forum', 'amphitheatre', 'hippodrome', 'castle',
  'palace', 'station', 'wall', 'harbour', 'aqueduct', 'bridge', 'lighthouse', 'tower', 'skyscraper', 'column', 'church', 'market'];

export const PALETTE = {
  stone: 0xd8ccb2, marble: 0xefe9dc, sand: 0xcdb48a, brick: 0xa9643f, terracotta: 0xb4553b, lead: 0x8e999f,
  gold: 0xd5a948, slate: 0x5d6670, wood: 0x7a5a3c, glass: 0x8fb3c9, concrete: 0xb9b6ae, green: 0x5f8f72, plaza: 0xc9bea5,
};

export function buildLandmark(THREE, spec, groundY) {
  const g = new THREE.Group();
  const mats = new Map();
  const mat = (c) => { if (!mats.has(c)) mats.set(c, new THREE.MeshLambertMaterial({ color: c, flatShading: true })); return mats.get(c); };
  // banners take the era's own colour (the page sets it); one material per landmark
  const bannerMat = new THREE.MeshLambertMaterial({ color: 0xb3202a, flatShading: true, side: THREE.DoubleSide });
  mats.set('banner', bannerMat);
  const S = spec.extra?.size ?? spec.size ?? null;
  const add = (geo, color, x = 0, y = 0, z = 0, ry = 0, parent = g) => {
    const m = new THREE.Mesh(geo, mat(color)); m.position.set(x, y, z); m.rotation.y = ry; m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
  };
  const box = (w, h, d, color, x = 0, y = 0, z = 0, ry = 0, p) => add(new THREE.BoxGeometry(w, h, d), color, x, y + h / 2, z, ry, p);
  const cyl = (r, h, color, x = 0, y = 0, z = 0, seg = 10, rTop = r, p) => add(new THREE.CylinderGeometry(rTop, r, h, seg), color, x, y + h / 2, z, 0, p);
  const dome = (r, color, x = 0, y = 0, z = 0, seg = 12, p) => add(new THREE.SphereGeometry(r, seg, 6, 0, Math.PI * 2, 0, Math.PI / 2), color, x, y, z, 0, p);
  const cone = (r, h, color, x = 0, y = 0, z = 0, seg = 8, p) => add(new THREE.ConeGeometry(r, h, seg), color, x, y + h / 2, z, 0, p);
  const gable = (w, h, d, color, x = 0, y = 0, z = 0, ry = 0, p) => {   // roof prism along x
    const s = new THREE.Shape(); s.moveTo(-d / 2, 0); s.lineTo(d / 2, 0); s.lineTo(0, h); s.closePath();
    const geo = new THREE.ExtrudeGeometry(s, { depth: w, bevelEnabled: false }); geo.translate(0, 0, -w / 2); geo.rotateY(Math.PI / 2);
    return add(geo, color, x, y, z, ry, p);
  };
  const DARK = 0x3a3430;   // window and arch openings
  // a row of arched openings on a facade: along local x at z = zf (face pointing to sign(zf)), or along z when alongZ
  const windows = (count, span, y, h, w, zf, alongZ = false, cx = 0) => {
    for (let i = 0; i < count; i++) {
      const o = cx + -span / 2 + (i + 0.5) * span / count, depth = 0.8, out = Math.sign(zf) * depth * 0.4;
      if (alongZ) { box(depth, h, w, DARK, zf + out, y, o); cyl(w / 2, depth, DARK, zf + out, y + h - 0.01, o, 8).rotation.z = Math.PI / 2; }
      else { box(w, h, depth, DARK, o, y, zf + out); cyl(w / 2, depth, DARK, o, y + h - 0.01, zf + out, 8).rotation.x = Math.PI / 2; }
    }
  };
  const banner = (x, y, z, size = 4) => { cyl(0.25, size * 1.6, PALETTE.wood, x, y, z, 4); add(new THREE.BoxGeometry(size * 1.1, size * 0.7, 0.15), bannerMat, x + size * 0.55, y + size * 1.25, z); };
  const colour = (k, d) => PALETTE[spec.extra?.[k]] ?? (typeof spec.extra?.[k] === 'string' && spec.extra[k].startsWith('#') ? parseInt(spec.extra[k].slice(1), 16) : d);
  const wallC = colour('color', PALETTE.stone), roofC = colour('roof', PALETTE.terracotta), domeC = colour('dome', PALETTE.lead);

  switch (spec.kind) {
    case 'dome_church': case 'mosque': {
      const L = S || 72, H = L * 0.32, D = L * 0.9, mosque = spec.kind === 'mosque';
      box(L, H, D, wallC);
      // two tiers of arched windows on every side, stone bands between them
      for (const zf of [-D / 2, D / 2]) { windows(9, L * 0.8, H * 0.18, H * 0.26, L * 0.04, zf); windows(7, L * 0.7, H * 0.58, H * 0.22, L * 0.045, zf); }
      for (const xf of [-L / 2, L / 2]) windows(7, D * 0.75, H * 0.22, H * 0.28, L * 0.045, xf, true);
      box(L * 1.01, H * 0.04, D * 1.01, PALETTE.stone, 0, H * 0.48, 0);
      // the great dome on a drum ringed with windows, stepped half-domes east and west, small exedra domes
      cyl(L * 0.29, L * 0.09, wallC, 0, H, 0, 20);
      for (let i = 0; i < 20; i++) { const a = (i / 20) * Math.PI * 2; box(L * 0.03, L * 0.05, L * 0.03, DARK, Math.cos(a) * L * 0.292, H + L * 0.02, Math.sin(a) * L * 0.292); }
      dome(L * 0.27, domeC, 0, H + L * 0.09, 0, 20);
      cyl(L * 0.012, L * 0.06, PALETTE.gold, 0, H + L * 0.35, 0, 6);
      for (const sx of [-1, 1]) {
        dome(L * 0.2, domeC, sx * L * 0.27, H * 0.95, 0, 14);
        for (const sz of [-1, 1]) dome(L * 0.09, domeC, sx * L * 0.36, H * 0.92, sz * L * 0.17, 10);
      }
      // corner piers and side buttresses
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) box(L * 0.12, H * 1.12, L * 0.12, wallC, sx * L * 0.44, 0, sz * L * 0.4);
      for (const sz of [-1, 1]) for (const sx of [-0.18, 0.18]) box(L * 0.06, H * 1.05, L * 0.08, wallC, sx * L, 0, sz * (D / 2 + L * 0.03));
      // narthex and its roof on the west
      box(L * 0.16, H * 0.62, D * 0.92, wallC, -L * 0.58, 0, 0); gable(D * 0.92, L * 0.05, L * 0.17, domeC, -L * 0.58, H * 0.62, 0, Math.PI / 2);
      windows(6, D * 0.7, H * 0.15, H * 0.25, L * 0.04, -L * 0.66, true);
      if (mosque) {   // a courtyard with a domed arcade in front
        box(L * 0.75, 0.5, D * 0.92, PALETTE.plaza, -L * 1.04, 0, 0);
        for (let i = 0; i < 5; i++) for (const sz of [-1, 1]) { box(L * 0.14, H * 0.3, L * 0.12, wallC, -L * 0.72 - i * L * 0.15, 0, sz * D * 0.42); dome(L * 0.055, domeC, -L * 0.72 - i * L * 0.15, H * 0.3, sz * D * 0.42, 8); }
        for (let i = 0; i < 3; i++) { box(L * 0.12, H * 0.3, L * 0.12, wallC, -L * 1.37, 0, (i - 1) * D * 0.3); dome(L * 0.055, domeC, -L * 1.37, H * 0.3, (i - 1) * D * 0.3, 8); }
      } else {   // the atrium: a walled court before the doors
        for (const sz of [-1, 1]) box(L * 0.6, H * 0.3, L * 0.06, wallC, -L * 0.96, 0, sz * D * 0.43);
        box(L * 0.06, H * 0.3, D * 0.9, wallC, -L * 1.26, 0, 0);
        box(L * 0.6, 0.4, D * 0.8, PALETTE.plaza, -L * 0.96, 0, 0);
      }
      const n = spec.kind === 'mosque' ? (spec.extra?.minarets ?? 4) : (spec.extra?.minarets ?? 0);
      const corners = [[1, 1], [-1, -1], [1, -1], [-1, 1], [0, 1.2], [0, -1.2]];
      for (let i = 0; i < n; i++) {
        const [cx, cz] = corners[i % corners.length], mx = cx * L * 0.58, mz = cz * L * 0.55;
        cyl(L * 0.035, L * 0.85, PALETTE.marble, mx, 0, mz, 8);
        cyl(L * 0.05, L * 0.03, PALETTE.marble, mx, L * 0.6, mz, 8);
        cone(L * 0.037, L * 0.16, domeC, mx, L * 0.85, mz, 8);
      }
      break;
    }
    case 'church': {
      const L = S || 34; box(L, L * 0.38, L * 0.45, wallC); gable(L, L * 0.2, L * 0.47, roofC, 0, L * 0.38, 0);
      box(L * 0.2, L * 0.75, L * 0.2, wallC, -L * 0.55, 0, 0); cone(L * 0.15, L * 0.35, roofC, -L * 0.55, L * 0.75, 0, 4);
      break;
    }
    case 'cathedral': {
      const L = S || 90, W = L * 0.32;
      box(L, L * 0.3, W, wallC); gable(L, L * 0.16, W * 1.04, roofC, 0, L * 0.3, 0);
      box(W * 0.9, L * 0.28, L * 0.62, wallC, L * 0.12, 0, 0); gable(L * 0.62, L * 0.15, W * 0.92, roofC, L * 0.12, L * 0.28, 0, Math.PI / 2);
      for (const sz of [-1, 1]) { box(W * 0.36, L * 0.62, W * 0.36, wallC, -L * 0.5, 0, sz * W * 0.32); cone(W * 0.24, L * 0.3, PALETTE.slate, -L * 0.5, L * 0.62, sz * W * 0.32, 4); }
      cyl(W * 0.42, L * 0.3, PALETTE.marble, L * 0.47, 0, 0, 10);
      break;
    }
    case 'temple': {
      const L = S || 50, W = L * 0.45, h = L * 0.22;
      box(L * 1.08, L * 0.04, W * 1.18, PALETTE.marble);
      const nx = 8, nz = 4;
      for (let i = 0; i < nx; i++) for (const sz of [-1, 1]) cyl(L * 0.025, h, PALETTE.marble, -L / 2 + (i + 0.5) * L / nx, L * 0.04, sz * W * 0.48, 8);
      for (let j = 1; j < nz - 1; j++) for (const sx of [-1, 1]) cyl(L * 0.025, h, PALETTE.marble, sx * (L / 2 - L / nx / 2), L * 0.04, -W / 2 + (j + 0.5) * W / nz, 8);
      box(L * 0.7, h, W * 0.6, wallC, 0, L * 0.04, 0);
      box(L * 1.02, L * 0.035, W * 1.06, PALETTE.marble, 0, L * 0.04 + h, 0);
      gable(L * 1.02, L * 0.09, W * 1.06, roofC, 0, L * 0.075 + h, 0);
      break;
    }
    case 'forum': case 'market': {
      const L = S || 120, W = L * 0.6;
      box(L, 0.6, W, PALETTE.plaza);
      for (const sz of [-1, 1]) { box(L, L * 0.06, W * 0.08, wallC, 0, 0.6, sz * W * 0.46); gable(L, L * 0.03, W * 0.09, roofC, 0, 0.6 + L * 0.06, sz * W * 0.46); }
      if (spec.kind === 'forum') { box(L * 0.18, L * 0.12, W * 0.3, PALETTE.marble, L * 0.38, 0.6, 0); gable(L * 0.18, L * 0.05, W * 0.31, roofC, L * 0.38, 0.6 + L * 0.12, 0); }
      else for (let i = 0; i < 8; i++) box(L * 0.08, 3, W * 0.12, PALETTE.wood, -L * 0.35 + i * L * 0.1, 0.6, 0);
      break;
    }
    case 'amphitheatre': {
      const R = S ? S / 2 : 85, ring = new THREE.Group(); g.add(ring);
      const shape = (r1, r2, h) => {
        const s = new THREE.Shape(); s.absellipse(0, 0, r1, r1 * 0.82, 0, Math.PI * 2, false, 0);
        const hole = new THREE.Path(); hole.absellipse(0, 0, r2, r2 * 0.82, 0, Math.PI * 2, true, 0); s.holes.push(hole);
        const geo = new THREE.ExtrudeGeometry(s, { depth: h, bevelEnabled: false, curveSegments: 28 }); geo.rotateX(-Math.PI / 2); return geo;
      };
      add(shape(R, R * 0.55, R * 0.3), wallC); add(shape(R * 0.9, R * 0.55, R * 0.36), PALETTE.sand);
      add(new THREE.CylinderGeometry(R * 0.55, R * 0.55, 0.5, 28), PALETTE.sand, 0, 0.25, 0).scale.z = 0.82;
      // three storeys of arches round the outside
      const N = Math.round(R * 0.5);
      for (let lv = 0; lv < 3; lv++) for (let i = 0; i < N; i++) {
        const a = (i / N) * Math.PI * 2, x = Math.cos(a) * R * 1.005, z = Math.sin(a) * R * 0.82 * 1.005;
        box(R * 0.045, R * 0.06, 0.8, DARK, x, R * (0.03 + lv * 0.09), z, -a + Math.PI / 2);
      }
      break;
    }
    case 'hippodrome': {   // open sand track, long stands on both sides, a curved end, the starting gates, the spine
      const L = S || 440, W = L * 0.27, sh = L * 0.03, sw = W * 0.2, straight = L - W / 2;
      box(straight, 0.6, W, PALETTE.sand, -W / 4, 0, 0);
      for (const sz of [-1, 1]) {
        box(straight, sh, sw, wallC, -W / 4, 0, sz * (W / 2 - sw / 2));
        // the stands step down to the track in three tiers, an arcade runs along the outside
        for (let k = 0; k < 3; k++) box(straight * 0.98, sh * (0.75 - k * 0.22), sw * 0.26, k % 2 ? PALETTE.marble : PALETTE.stone, -W / 4, sh * 0.1, sz * (W / 2 - sw * (1.05 + k * 0.28)));
        windows(Math.round(straight / 9), straight * 0.95, sh * 0.15, sh * 0.5, 3.2, sz * W / 2, false, -W / 4);
      }
      box(L * 0.06, sh * 1.5, sw * 0.9, wallC, -W / 4, 0, -(W / 2 + sw * 0.3));   // the emperor's box
      for (const ox of [-0.32, -0.2, 0.1, 0.22]) cone(W * 0.02, L * 0.05, PALETTE.marble, ox * L, 2.2, 0, 4);
      const s = new THREE.Shape(); s.absarc(0, 0, W / 2, -Math.PI / 2, Math.PI / 2, false); s.lineTo(0, W / 2 - sw);
      s.absarc(0, 0, W / 2 - sw, Math.PI / 2, -Math.PI / 2, true); s.closePath();
      const geo = new THREE.ExtrudeGeometry(s, { depth: sh, bevelEnabled: false, curveSegments: 14 }); geo.rotateX(-Math.PI / 2);
      add(geo, wallC, straight / 2 - W / 4, 0, 0);
      add(new THREE.CylinderGeometry(W / 2 - sw, W / 2 - sw, 0.6, 14, 1, false, 0, Math.PI), PALETTE.sand, straight / 2 - W / 4, 0.3, 0);
      box(sw * 0.8, sh * 1.2, W, wallC, -straight / 2 - W / 4, 0, 0);
      box(straight * 0.62, 1.6, W * 0.06, PALETTE.marble, -W / 4, 0.6, 0);
      cyl(W * 0.025, L * 0.07, PALETTE.marble, -L * 0.12, 2.2, 0, 4, W * 0.008);
      cyl(W * 0.025, L * 0.06, PALETTE.stone, L * 0.05, 2.2, 0, 6, W * 0.01);
      break;
    }
    case 'castle': {
      const L = S || 70, h = L * 0.22;
      for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { cyl(L * 0.09, h * 1.4, wallC, sx * L / 2, 0, sz * L / 2, 10); cone(L * 0.1, L * 0.12, roofC, sx * L / 2, h * 1.4, sz * L / 2, 10); }
      for (const [w, d, x, z] of [[L, L * 0.06, 0, -L / 2], [L, L * 0.06, 0, L / 2], [L * 0.06, L, -L / 2, 0], [L * 0.06, L, L / 2, 0]]) box(w, h, d, wallC, x, 0, z);
      box(L * 0.32, h * 2, L * 0.32, wallC, L * 0.1, 0, -L * 0.08); gable(L * 0.32, L * 0.1, L * 0.33, roofC, L * 0.1, h * 2, -L * 0.08);
      banner(L * 0.1, h * 2 + L * 0.1, -L * 0.08, L * 0.06);
      break;
    }
    case 'palace': {
      const L = S || 120, h = L * 0.1;
      for (const [w, d, x, z] of [[L, L * 0.16, 0, -L * 0.42], [L, L * 0.16, 0, L * 0.42], [L * 0.16, L * 0.68, -L * 0.42, 0], [L * 0.16, L * 0.68, L * 0.42, 0]]) {
        box(w, h, d, wallC, x, 0, z); gable(Math.max(w, d), L * 0.05, Math.min(w, d) * 1.02, roofC, x, h, z, w > d ? 0 : Math.PI / 2);
      }
      box(L * 0.84, 0.4, L * 0.68, PALETTE.green); dome(L * 0.08, domeC, 0, h * 0.2, -L * 0.42, 10);
      for (const zf of [-L * 0.5, L * 0.5]) windows(10, L * 0.9, h * 0.25, h * 0.45, 2.6, zf);
      // a lower second court and terraces running down from the main one
      for (const [w, d, x, z] of [[L * 0.7, L * 0.1, L * 0.9, -L * 0.3], [L * 0.7, L * 0.1, L * 0.9, L * 0.3], [L * 0.1, L * 0.7, L * 1.25, 0]]) {
        box(w, h * 0.7, d, wallC, x, 0, z); gable(Math.max(w, d), L * 0.035, Math.min(w, d) * 1.02, roofC, x, h * 0.7, z, w > d ? 0 : Math.PI / 2);
      }
      box(L * 0.6, 0.4, L * 0.5, PALETTE.plaza, L * 0.88, 0, 0);
      for (let i = 0; i < 6; i++) cyl(L * 0.012, h * 0.6, PALETTE.marble, L * 0.62 + i * L * 0.1, 0.4, -L * 0.22, 6);
      for (let i = 0; i < 8; i++) { const a = i * 2.4; cone(L * 0.03, L * 0.07, PALETTE.green, Math.cos(a) * L * 0.22, 0.4, Math.sin(a) * L * 0.2, 6); }
      break;
    }
    case 'station': {   // a long station hall with a clock tower, platform canopies and the tracks running on past it
      const L = S || 110, D = L * 0.16, h = L * 0.09;
      box(L, h, D, wallC, 0, 0, 0); gable(L, L * 0.04, D * 1.05, roofC, 0, h, 0);
      box(D * 0.7, h * 2.2, D * 0.7, wallC, 0, 0, 0); cone(D * 0.5, L * 0.06, roofC, 0, h * 2.2, 0, 4);
      for (const k of [1, 2]) {
        const z = -(D / 2 + k * L * 0.07);
        box(L * 0.9, 0.6, L * 0.035, PALETTE.concrete, 0, 0, z + L * 0.02);
        for (let i = -3; i <= 3; i++) box(0.5, L * 0.04, 0.5, PALETTE.slate, (i * L * 0.9) / 7, 0.6, z + L * 0.02);
        box(L * 0.9, 0.4, L * 0.04, PALETTE.slate, 0, L * 0.04 + 0.6, z + L * 0.02);
      }
      for (const z of [-(D / 2 + L * 0.1), -(D / 2 + L * 0.17)]) box(L * 2.6, 0.35, 3.2, 0x6b5f55, 0, 0, z);
      break;
    }
    case 'lighthouse': { const H = S || 60; cyl(H * 0.12, H, PALETTE.marble, 0, 0, 0, 10, H * 0.07); cyl(H * 0.08, H * 0.1, PALETTE.gold, 0, H, 0, 8); break; }
    case 'column': { const H = S || 35; box(H * 0.2, H * 0.1, H * 0.2, PALETTE.marble); cyl(H * 0.06, H, PALETTE.marble, 0, H * 0.1, 0, 10); break; }
    case 'tower': { const H = S || 60; cyl(H * 0.14, H, wallC, 0, 0, 0, 12); cone(H * 0.16, H * 0.3, roofC, 0, H, 0, 12); break; }
    case 'skyscraper': {
      const H = spec.extra?.height ?? S ?? 180;   // metres: use the real height (Burj Khalifa 828, Shanghai Tower 632)
      if (H >= 250) {   // a supertall: stepped, tapering shaft and a spire, not a box
        const col = colour('color', PALETTE.glass), steps = 7;
        let w = spec.extra?.width ?? H * 0.075, y = 0;
        for (let i = 0; i < steps; i++) { const h = (H * 0.76) / steps; box(w, h, w, col, 0, y, 0); y += h; w *= 0.8; }
        cyl(w * 0.9, H - y, PALETTE.concrete, 0, y, 0, 8, w * 0.1);
        break;
      }
      const W = spec.extra?.width ?? H * 0.22;
      box(W, H, W, colour('color', PALETTE.glass)); box(W * 0.7, H * 0.08, W * 0.7, PALETTE.concrete, 0, H, 0);
      break;
    }
    case 'wall': case 'harbour': case 'aqueduct': case 'bridge': {
      const pts = spec.points || [];
      const h = spec.extra?.height ?? (spec.kind === 'wall' ? 14 : spec.kind === 'aqueduct' ? 22 : spec.kind === 'bridge' ? 9 : 4);
      const thick = spec.extra?.thickness ?? (spec.kind === 'wall' ? 6 : spec.kind === 'harbour' ? 14 : spec.kind === 'bridge' ? 12 : 5);
      const wall = spec.kind === 'wall', towerEvery = spec.extra?.towers ?? (wall ? 55 : 0);
      const bandC = colour('band', PALETTE.brick), gates = (spec.gates || []).map(([x, z]) => ({ x, z, done: false }));
      // a wall tower: square, taller, banded like the wall, crenellated, every other one flies the era's banner
      let nTower = 0;
      const tower = (x, gy, z, ang) => {
        const tw = thick * 2.3, th = h * 1.45;
        box(tw, th, tw, wallC, x, gy - 1, z, ang);
        for (const f of [0.33, 0.66]) box(tw * 1.02, th * 0.06, tw * 1.02, bandC, x, gy - 1 + th * f, z, ang);
        for (const [u, v] of [[-1, -1], [1, -1], [-1, 1], [1, 1], [0, -1], [0, 1], [-1, 0], [1, 0]]) {
          const c = Math.cos(ang), sn = Math.sin(ang), ox = (u * c + v * sn) * tw * 0.42, oz = (-u * sn + v * c) * tw * 0.42;
          box(tw * 0.18, 1.6, tw * 0.18, wallC, x + ox, gy - 1 + th, z + oz, ang);
        }
        if (nTower++ % 2 === 0) banner(x, gy - 1 + th, z, Math.max(3, thick * 0.6));
      };
      let acc = 0;
      for (let i = 0; i + 1 < pts.length; i++) {
        const [ax, az] = pts[i], [bx, bz] = pts[i + 1], len = Math.hypot(bx - ax, bz - az); if (len < 0.5) continue;
        const n = Math.max(1, Math.ceil(len / 24)), ang = -Math.atan2(bz - az, bx - ax), ux = (bx - ax) / len, uz = (bz - az) / len;
        for (let k = 0; k < n; k++) {
          const s0 = k / n, s1 = (k + 1) / n, x = ax + (bx - ax) * (s0 + s1) / 2, z = az + (bz - az) * (s0 + s1) / 2;
          const gy = spec.kind === 'bridge' || spec.kind === 'harbour' ? Math.max(0, groundY(x, z)) : groundY(x, z);
          const seg = len / n + 0.6;
          if (spec.kind === 'aqueduct' || spec.kind === 'bridge') {
            box(seg, thick * 0.35, thick, wallC, x, gy + h - thick * 0.35, z, ang);
            box(thick * 0.7, h, thick * 0.9, wallC, x, Math.min(gy, 0) - 2, z, ang);
            if (spec.kind === 'aqueduct') windows(1, seg, Math.min(gy, 0), h * 0.55, seg * 0.55, 0.01, false, 0);
          } else if (wall) {
            const gate = gates.find((q) => Math.hypot(q.x - x, q.z - z) < seg * 0.75);
            if (gate) {   // a gatehouse where a street passes through: two towers and the arch between them
              if (!gate.done) {
                gate.done = true;
                for (const sg of [-1, 1]) tower(x + ux * sg * thick * 2.2, gy, z + uz * sg * thick * 2.2, ang);
                box(thick * 2.4, h * 0.4, thick * 1.1, wallC, x, gy - 1 + h * 0.75, z, ang);
                acc = 0;
              }
              continue;
            }
            box(seg, h, thick, wallC, x, gy - 1, z, ang);
            // striped courses of brick in the stone, battlements along the top
            for (const f of [0.3, 0.55, 0.8]) box(seg, h * 0.06, thick * 1.03, bandC, x, gy - 1 + h * f, z, ang);
            for (let m = 0; m < Math.floor(seg / 3.2); m++) {
              const o = -seg / 2 + (m + 0.5) * (seg / Math.floor(seg / 3.2));
              for (const sd of [-1, 1]) box(1.6, 1.5, 0.9, wallC, x + ux * o - uz * sd * thick * 0.42, gy - 1 + h, z + uz * o + ux * sd * thick * 0.42, ang);
            }
          } else box(seg, h + 2, thick, wallC, x, gy - 2, z, ang);
          acc += len / n;
          if (towerEvery && acc >= towerEvery) { acc = 0; tower(x, gy, z, ang); }
        }
      }
      mergeChildren(THREE, g);
      g.userData.banner = bannerMat;
      return g;   // path pieces carry their own heights
    }
    default: box(S || 20, (S || 20) * 0.8, S || 20, wallC);
  }
  mergeChildren(THREE, g);
  g.userData.banner = bannerMat;
  // a foundation under the footprint reaches down into any slope, so the building sits at its centre's height
  const bb = new THREE.Box3().setFromObject(g);
  const fx = bb.max.x - bb.min.x, fz = bb.max.z - bb.min.z;
  const plinth = new THREE.Mesh(new THREE.BoxGeometry(fx * 1.04, 60, fz * 1.04), mat(PALETTE.stone));
  plinth.position.set((bb.max.x + bb.min.x) / 2, -29.7, (bb.max.z + bb.min.z) / 2); plinth.receiveShadow = true; plinth.userData.plinth = true; g.add(plinth);
  g.userData.local = bb;   // the model's own box (before it is turned and placed), for the scaffolding
  const rot = ((spec.extra?.rot ?? 0) * Math.PI) / 180;
  g.rotation.y = rot;
  // stand on the highest ground under the footprint (5 x 5 samples); the plinth fills the slope below
  let top = -Infinity;
  for (let i = 0; i <= 4; i++) for (let j = 0; j <= 4; j++) {
    const lx = bb.min.x + (fx * i) / 4, lz = bb.min.z + (fz * j) / 4;
    top = Math.max(top, groundY(spec.x + Math.cos(rot) * lx + Math.sin(rot) * lz, spec.z - Math.sin(rot) * lx + Math.cos(rot) * lz));
  }
  g.position.set(spec.x, Math.max(0.3, top), spec.z);
  return g;
}

/** Bake a group's direct mesh children into one mesh per material: a landmark of hundreds of pieces costs a few draws. */
export function mergeChildren(THREE, g) {
  const groups = new Map();
  for (const ch of [...g.children]) {
    if (!ch.isMesh || ch.userData.plinth) continue;
    ch.updateMatrix();
    const geo = (ch.geometry.index ? ch.geometry.toNonIndexed() : ch.geometry.clone());
    for (const k of Object.keys(geo.attributes)) if (k !== 'position' && k !== 'normal') geo.deleteAttribute(k);
    geo.applyMatrix4(ch.matrix);
    (groups.get(ch.material) || groups.set(ch.material, []).get(ch.material)).push(geo);
    g.remove(ch); ch.geometry.dispose();
  }
  for (const [m, list] of groups) {
    let n = 0; for (const q of list) n += q.attributes.position.count;
    const P = new Float32Array(n * 3), N = new Float32Array(n * 3); let o = 0;
    for (const q of list) { P.set(q.attributes.position.array, o); if (q.attributes.normal) N.set(q.attributes.normal.array, o); o += q.attributes.position.array.length; q.dispose(); }
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(P, 3)); geo.setAttribute('normal', new THREE.BufferAttribute(N, 3));
    const mesh = new THREE.Mesh(geo, m); mesh.castShadow = true; mesh.receiveShadow = true; g.add(mesh);
  }
  return g;
}

/** Wooden scaffolding round a building's own box: poles every ~7 m on the outline, a deck every ~6 m (one mesh). */
export function buildScaffold(THREE, bb, material) {
  const g = new THREE.Group(), pad = 2.5, x0 = bb.min.x - pad, x1 = bb.max.x + pad, z0 = bb.min.z - pad, z1 = bb.max.z + pad, top = bb.max.y + 2;
  const pole = (x, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(0.5, top, 0.5), material); m.position.set(x, top / 2, z); g.add(m); };
  for (const [ax, az, bx, bz] of [[x0, z0, x1, z0], [x1, z0, x1, z1], [x1, z1, x0, z1], [x0, z1, x0, z0]]) {
    const L = Math.hypot(bx - ax, bz - az), n = Math.max(1, Math.round(L / 7));
    for (let i = 0; i < n; i++) pole(ax + (bx - ax) * i / n, az + (bz - az) * i / n);
    for (let y = 6; y < top; y += 6) { const m = new THREE.Mesh(new THREE.BoxGeometry(Math.abs(bx - ax) + 0.5, 0.35, Math.abs(bz - az) + 0.5), material); m.position.set((ax + bx) / 2, y, (az + bz) / 2); g.add(m); }
  }
  mergeChildren(THREE, g);
  return g;
}

/** Ground a landmark covers, as circles {x, z, r} in metres (the city clears houses and trees there once it stands). */
const SHAPE = { hippodrome: [1, 0.3], dome_church: [1.35, 1.05], mosque: [1.4, 1.3], cathedral: [1.15, 0.75], temple: [1.15, 0.6],
  forum: [1, 0.65], market: [1, 0.65], station: [1.3, 0.5], palace: [1.05, 0.9], castle: [1.25, 1.25], amphitheatre: [1, 0.85], church: [1.3, 0.6] };
const DEFAULT_SIZE = { dome_church: 72, mosque: 72, church: 34, cathedral: 90, temple: 50, forum: 120, market: 120, amphitheatre: 170,
  hippodrome: 440, station: 110, castle: 70, palace: 120, lighthouse: 20, column: 8, tower: 18, skyscraper: 45 };
export function footprint(spec) {
  if (spec.points) {
    const r = ((spec.extra?.thickness ?? 6) / 2) + 5, out = [];
    for (let i = 0; i + 1 < spec.points.length; i++) {
      const [ax, az] = spec.points[i], [bx, bz] = spec.points[i + 1], n = Math.max(1, Math.ceil(Math.hypot(bx - ax, bz - az) / (r * 1.2)));
      for (let k = 0; k <= n; k++) out.push({ x: ax + (bx - ax) * k / n, z: az + (bz - az) * k / n, r });
    }
    return out;
  }
  const size = spec.extra?.size ?? DEFAULT_SIZE[spec.kind] ?? 40, [fl, fw] = SHAPE[spec.kind] || [1, 1];
  const L = size * fl, Wd = size * fw, rot = ((spec.extra?.rot ?? 0) * Math.PI) / 180;
  const n = Math.max(1, Math.round(L / Wd)), r = Wd / 2 + 6, out = [];
  // the model's long axis is local x; rotation.y turns local x to (cos, -sin) in x/z
  for (let k = 0; k < n; k++) { const o = (k + 0.5) / n * L - L / 2; out.push({ x: spec.x + Math.cos(rot) * o, z: spec.z - Math.sin(rot) * o, r }); }
  return out;
}

/** The points a path landmark is built along must be in metres before build(): [[lon, lat]] -> [[x, z]]. */
export function pathToXZ(path, toXZ) {
  return (path || []).map(([lon, lat]) => { const p = toXZ(lon, lat); return [p.x, p.z]; });
}
