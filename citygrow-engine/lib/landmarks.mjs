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
  const colour = (k, d) => PALETTE[spec.extra?.[k]] ?? (typeof spec.extra?.[k] === 'string' && spec.extra[k].startsWith('#') ? parseInt(spec.extra[k].slice(1), 16) : d);
  const wallC = colour('color', PALETTE.stone), roofC = colour('roof', PALETTE.terracotta), domeC = colour('dome', PALETTE.lead);

  switch (spec.kind) {
    case 'dome_church': case 'mosque': {
      const L = S || 72, H = L * 0.32;
      box(L, H, L * 0.9, wallC);
      // stepped half-domes and the great dome on a drum
      cyl(L * 0.27, L * 0.08, wallC, 0, H, 0, 16);
      dome(L * 0.27, domeC, 0, H + L * 0.08, 0, 16);
      dome(L * 0.2, domeC, L * 0.27, H * 0.95, 0, 12); dome(L * 0.2, domeC, -L * 0.27, H * 0.95, 0, 12);
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) box(L * 0.12, H * 1.08, L * 0.12, wallC, sx * L * 0.44, 0, sz * L * 0.4);
      box(L * 0.3, H * 0.7, L * 0.7, wallC, -L * 0.62, 0, 0);
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
      break;
    }
    case 'hippodrome': {   // open sand track, long stands on both sides, a curved end, the starting gates, the spine
      const L = S || 440, W = L * 0.27, sh = L * 0.03, sw = W * 0.2, straight = L - W / 2;
      box(straight, 0.6, W, PALETTE.sand, -W / 4, 0, 0);
      for (const sz of [-1, 1]) box(straight, sh, sw, wallC, -W / 4, 0, sz * (W / 2 - sw / 2));
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
      break;
    }
    case 'palace': {
      const L = S || 120, h = L * 0.1;
      for (const [w, d, x, z] of [[L, L * 0.16, 0, -L * 0.42], [L, L * 0.16, 0, L * 0.42], [L * 0.16, L * 0.68, -L * 0.42, 0], [L * 0.16, L * 0.68, L * 0.42, 0]]) {
        box(w, h, d, wallC, x, 0, z); gable(Math.max(w, d), L * 0.05, Math.min(w, d) * 1.02, roofC, x, h, z, w > d ? 0 : Math.PI / 2);
      }
      box(L * 0.84, 0.4, L * 0.68, PALETTE.green); dome(L * 0.08, domeC, 0, h * 0.2, -L * 0.42, 10);
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
      const towerEvery = spec.extra?.towers ?? (spec.kind === 'wall' ? 70 : 0);
      let acc = 0;
      for (let i = 0; i + 1 < pts.length; i++) {
        const [ax, az] = pts[i], [bx, bz] = pts[i + 1], len = Math.hypot(bx - ax, bz - az); if (len < 0.5) continue;
        const n = Math.max(1, Math.ceil(len / 24)), ang = -Math.atan2(bz - az, bx - ax);
        for (let k = 0; k < n; k++) {
          const s0 = k / n, s1 = (k + 1) / n, x = ax + (bx - ax) * (s0 + s1) / 2, z = az + (bz - az) * (s0 + s1) / 2;
          const gy = spec.kind === 'bridge' || spec.kind === 'harbour' ? Math.max(0, groundY(x, z)) : groundY(x, z);
          const seg = len / n + 0.6;
          if (spec.kind === 'aqueduct' || spec.kind === 'bridge') {
            box(seg, thick * 0.35, thick, wallC, x, gy + h - thick * 0.35, z, ang);
            box(thick * 0.7, h, thick * 0.9, wallC, x, Math.min(gy, 0) - 2, z, ang);
          } else box(seg, h + (spec.kind === 'harbour' ? 2 : 0), thick, wallC, x, gy - (spec.kind === 'harbour' ? 2 : 1), z, ang);
          acc += len / n;
          if (towerEvery && acc >= towerEvery) { acc = 0; box(thick * 2.2, h * 1.45, thick * 2.2, wallC, x, gy - 1, z, ang); }
        }
      }
      return g;   // path pieces carry their own heights
    }
    default: box(S || 20, (S || 20) * 0.8, S || 20, wallC);
  }
  // a foundation under the footprint reaches down into any slope, so the building sits at its centre's height
  const bb = new THREE.Box3().setFromObject(g);
  const fx = bb.max.x - bb.min.x, fz = bb.max.z - bb.min.z;
  const plinth = new THREE.Mesh(new THREE.BoxGeometry(fx * 1.04, 60, fz * 1.04), mat(PALETTE.stone));
  plinth.position.set((bb.max.x + bb.min.x) / 2, -29.7, (bb.max.z + bb.min.z) / 2); plinth.receiveShadow = true; g.add(plinth);
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
