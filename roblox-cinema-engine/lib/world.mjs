// World and environment generator. makeWorld(env, opts) returns a complete set as plain data — terrain (as a height
// function), water, roads, buildings, trees, fields, hedgerows, props, named anchors and colliders — deterministic from the
// seed. The browser builds meshes from it; Node uses the same object for camera-collision and ground-contact checks.
// Units: studs (a character is ~5 tall). x east, z south; the sea, when there is one, lies toward -z.

import { makeRng, fbm2, clamp, smooth, lerp } from './rng.mjs';

export const ENVIRONMENTS = ['city', 'town', 'village', 'farmland', 'forest', 'jungle', 'hills', 'mountains', 'valley', 'desert', 'beach', 'river',
  'island', 'airfield', 'military_base', 'factory', 'port', 'monument', 'battlefield', 'interior', 'sea', 'map'];

export const SIZE = 340; // half extent of a set's ground

// culture + era -> building styles and palette
const STYLE = {
  european: { house: 'stone_house', town: 'townhouse', big: 'church', roof: ['#7a3b2e', '#5b4a44', '#3f4650', '#8a5a3c'], wall: ['#d9cdb4', '#cbbd9e', '#bfb7a6', '#e2d8c2', '#b8a68a', '#a79a86'] },
  asian: { house: 'stilt_house', town: 'shophouse', big: 'temple', roof: ['#8a6a3a', '#6e5a32', '#a0522d', '#5c4a2e'], wall: ['#c9b48a', '#d8c9a3', '#b8a27a', '#e0d2b0'] },
  south_asian: { house: 'concrete_block', town: 'concrete_block', big: 'concrete_block', roof: ['#9a958a', '#8c8880'], wall: ['#e6d3a8', '#d9b48a', '#c8d0b4', '#e8c4a0', '#d6cfc0', '#b9c7c4'] },
  middle_east: { house: 'adobe', town: 'adobe_block', big: 'dome', roof: ['#c8b28a'], wall: ['#d9c39a', '#cdb48a', '#e2cfa8', '#c2a678'] },
  american: { house: 'clapboard', town: 'brick_block', big: 'courthouse', roof: ['#4a4a4f', '#5a3b30', '#3b4048'], wall: ['#e6e1d3', '#c9d3d9', '#d9c7a8', '#a85a45'] },
};

const dist2seg = (px, pz, ax, az, bx, bz) => {
  const dx = bx - ax, dz = bz - az, L = dx * dx + dz * dz || 1;
  const t = clamp(((px - ax) * dx + (pz - az) * dz) / L, 0, 1);
  return Math.hypot(px - (ax + t * dx), pz - (az + t * dz));
};
export const distToPolyline = (x, z, pts) => { let d = Infinity; for (let i = 1; i < pts.length; i++) d = Math.min(d, dist2seg(x, z, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])); return d; };

/** opts: {seed, culture, era, time, weather, damaged, variant} */
export function makeWorld(env, opts = {}) {
  const seed = `${env}:${opts.seed ?? 0}`, rng = makeRng(seed), noise = fbm2(seed, 4), fine = fbm2(`${seed}:f`, 3);
  const culture = STYLE[opts.culture] ? opts.culture : 'european', st = STYLE[culture], era = opts.era || 'ww2';
  const W = { env, seed: opts.seed ?? 0, culture, era, size: SIZE, water: null, roads: [], buildings: [], trees: [], fields: [], hedges: [], props: [], anchors: {}, colliders: [], craters: [], interior: null, ground: 'grass' };
  let amp = 2.2, shoreZ = null, river = null, plateau = null, flatten = [];

  // ---- terrain shape per environment --------------------------------------------------------------------------------------
  if (env === 'beach' || env === 'port' || env === 'island') {
    shoreZ = (x) => -60 + noise(x / 90, 3.1) * 10;
    W.water = { level: 0, kind: 'sea' };
  }
  if (env === 'sea') { W.water = { level: 0, kind: 'sea', open: true }; }
  if (env === 'river' || env === 'jungle' || (env === 'village' && opts.variant === 'river')) {
    const bend = rng.range(-30, 30);
    river = { width: env === 'river' ? 30 : 18, path: Array.from({ length: 13 }, (_, i) => { const z = -SIZE + i * (2 * SIZE / 12); return [bend + Math.sin(z / 110 + rng() * 0.5) * 38, z]; }) };
    if (env === 'jungle') river.path = river.path.map(([x, z]) => [x + 110, z]);
    W.water = { level: 0, kind: 'river', river };
  }
  if (env === 'hills' || env === 'mountains' || env === 'valley') amp = env === 'mountains' ? 46 : env === 'valley' ? 26 : 16;
  if (env === 'desert') amp = 7;
  if (env === 'interior' || env === 'map') amp = 0;
  if (env === 'city' || env === 'airfield' || env === 'factory' || env === 'military_base') amp = 0.8;

  const heightAt = (x, z) => {
    if (env === 'interior' || env === 'map') return 0;
    if (env === 'sea') return -18;
    let h = noise(x / 120, z / 120) * amp + fine(x / 22, z / 22) * 0.35;
    if (env === 'valley') h = Math.abs(x) / 180 * amp + noise(x / 90, z / 90) * 5 - 6;
    if (env === 'mountains') h = Math.max(0, noise(x / 150, z / 150) * 0.5 + 0.5) ** 1.6 * amp * 1.6 + Math.max(0, -z - 80) * 0.18;
    if (env === 'desert') h = (Math.sin(x / 34 + noise(x / 60, z / 60) * 2) * 0.5 + 0.5) * amp + noise(x / 200, z / 200) * 4;
    if (shoreZ) {
      const s = shoreZ(x), d = z - s; // d < 0: sea
      if (d < 0) h = Math.max(-14, d * 0.12) - 0.4;
      else if (env === 'beach') {
        const beachW = 70;
        h = d < beachW ? d * 0.035 : beachW * 0.035 + (smooth((d - beachW) / 30) * 15) + Math.max(0, d - beachW - 30) * 0.02 + noise(x / 60, z / 60) * 1.2 * smooth((d - beachW) / 30);
        if (opts.variant === 'flat') h = d * 0.03 + smooth((d - beachW) / 60) * 3;
      } else if (env === 'island') h = Math.min(d * 0.08, 6 + noise(x / 50, z / 50) * 4);
      else h = Math.min(1.6, d * 0.15) + (d > 20 ? 0 : 0); // port: low quay
    }
    if (river) {
      const d = distToPolyline(x, z, river.path), w = river.width;
      if (d < w * 1.8) h = lerp(h, d < w ? -3.2 * (1 - (d / w) ** 2) - 0.4 : h * smooth((d - w) / (w * 0.8)), d < w ? 1 : 1);
    }
    for (const f of flatten) { const d = Math.hypot((x - f.x) / f.rx, (z - f.z) / f.rz); if (d < 1.4) h = lerp(f.h, h, smooth((d - 1) / 0.4)); }
    for (const c of W.craters) { const d = Math.hypot(x - c.x, z - c.z) / c.r; if (d < 1.25) h += d < 1 ? -c.depth * (1 - d * d) : c.depth * 0.35 * Math.sin((d - 1) / 0.25 * Math.PI); }
    return h;
  };
  W.heightAt = heightAt;
  W.isWater = (x, z) => !!W.water && heightAt(x, z) < (W.water.level ?? 0) - 0.05;
  const slopeAt = (x, z) => Math.hypot(heightAt(x + 1, z) - heightAt(x - 1, z), heightAt(x, z + 1) - heightAt(x, z - 1)) / 2;
  W.slopeAt = slopeAt;

  // ---- placement helpers ---------------------------------------------------------------------------------------------------
  const blocked = (x, z, r) => W.buildings.some((b) => Math.abs(x - b.x) < b.w / 2 + r && Math.abs(z - b.z) < b.d / 2 + r)
    || W.roads.some((rd) => distToPolyline(x, z, rd.points) < rd.width / 2 + r) || (W.water && heightAt(x, z) < 0.3);
  const addBuilding = (b) => {
    if (W.isWater(b.x, b.z) || slopeAt(b.x, b.z) > 0.6) return false;
    if (W.buildings.some((o) => Math.abs(b.x - o.x) < (b.w + o.w) / 2 + 1.5 && Math.abs(b.z - o.z) < (b.d + o.d) / 2 + 1.5)) return false;
    const y = Math.min(...[[-1, -1], [1, -1], [-1, 1], [1, 1], [0, 0]].map(([a, c]) => heightAt(b.x + a * b.w / 2, b.z + c * b.d / 2)));
    b.y = y; b.rot = b.rot || 0;
    W.buildings.push(b);
    W.colliders.push({ x0: b.x - b.w / 2 - 1, x1: b.x + b.w / 2 + 1, z0: b.z - b.d / 2 - 1, z1: b.z + b.d / 2 + 1, y1: y + b.h + (b.roofH || 0) + 1 });
    return true;
  };
  const house = (x, z, rot, kind = st.house, big = false) => {
    const w = big ? rng.range(18, 26) : rng.range(10, 16), d = big ? rng.range(14, 20) : rng.range(9, 13);
    const floors = kind === 'townhouse' ? rng.int(3, 5) : kind === 'concrete_block' ? rng.int(2, 4) : kind === 'shophouse' || kind === 'brick_block' || kind === 'adobe_block' ? rng.int(2, 3) : kind === 'stilt_house' ? 1 : rng.int(1, 2);
    const flat = ['adobe', 'adobe_block', 'brick_block', 'concrete_block'].includes(kind);
    return addBuilding({ kind, x, z, w, d, h: floors * 5.2 + (kind === 'stilt_house' ? 3 : 0), floors, rot, wall: rng.pick(st.wall), roof: rng.pick(st.roof), roofH: flat ? 0 : rng.range(4, 7), roofType: flat ? 'flat' : kind === 'townhouse' ? 'mansard' : 'gable',
      damaged: !!opts.damaged && rng.chance(0.45), shutters: culture === 'european' && rng.chance(0.6), awning: kind === 'townhouse' || kind === 'shophouse' ? rng.chance(0.5) : false, seed: rng.int(0, 1e6) });
  };
  const tree = (x, z, kind, s = 1) => { if (!blocked(x, z, 2.5)) W.trees.push({ x, z, y: heightAt(x, z), kind, scale: s * rng.range(0.8, 1.25), rot: rng() * 6.28 }); };
  const scatterTrees = (n, kinds, region = SIZE, avoid = null) => { for (let i = 0; i < n; i++) { const x = rng.range(-region, region), z = rng.range(-region, region); if (avoid && avoid(x, z)) continue; tree(x, z, rng.pick(kinds)); } };
  const road = (points, width = 10, kind = 'dirt') => W.roads.push({ points, width, kind });
  const prop = (kind, x, z, rot = 0, extra = {}) => W.props.push({ kind, x, z, y: heightAt(x, z), rot, ...extra });
  const hedgeRow = (pts) => W.hedges.push({ points: pts.map(([x, z]) => [x, z, heightAt(x, z)]) });
  const fieldPatch = (x, z, w, d, rot, color) => W.fields.push({ x, z, w, d, rot, color, y: heightAt(x, z) });

  const treeKinds = env === 'jungle' ? ['palm', 'broadleaf', 'broadleaf', 'fern', 'palm'] : culture === 'asian' || culture === 'south_asian' ? ['palm', 'broadleaf', 'bush'] : culture === 'middle_east' ? ['palm', 'bush'] : ['oak', 'oak', 'pine', 'poplar', 'bush'];

  // ---- environment recipes -----------------------------------------------------------------------------------------------
  switch (env) {
    case 'city': case 'monument': {
      W.ground = 'paved';
      road([[-SIZE, 0], [SIZE, 0]], 22, 'boulevard'); road([[0, -SIZE], [0, SIZE]], 16, 'street');
      for (const z of [-120, 120]) road([[-SIZE, z], [SIZE, z]], 12, 'street');
      for (const x of [-140, 140]) road([[x, -SIZE], [x, SIZE]], 12, 'street');
      if (env === 'monument' || opts.variant === 'monument') { flatten.push({ x: 0, z: 0, rx: 30, rz: 30, h: 0 }); prop('arch', 0, -60, 0, { scale: 1.2 }); W.anchors.monument = [0, -60]; }
      for (let gx = -280; gx <= 280; gx += 26) for (const side of [-1, 1]) for (const zz of [18, 52, 86, 150, 190]) {
        const x = gx + rng.range(-3, 3), z = side * zz;
        if (Math.abs(x) < 14 || Math.abs(Math.abs(x) - 140) < 12 || (env === 'monument' && Math.hypot(x, z + 60) < 40)) continue;
        house(x, z, side > 0 ? Math.PI : 0, st.town, rng.chance(0.08));
      }
      for (let x = -300; x <= 300; x += 22) for (const s of [-1, 1]) { if (Math.abs(x) > 12) { prop('lamp', x, s * 12.5); tree(x + 11, s * 9.5, culture === 'european' ? 'plane' : treeKinds[0], 0.9); } }
      for (let i = 0; i < 6; i++) prop('kiosk', rng.range(-200, 200), rng.pick([-14, 14]));
      W.anchors = { ...W.anchors, center: [0, 0], street: [-60, 0], square: [0, 0], crowd: [0, 8], far: [-220, 0] };
      break;
    }
    case 'town': case 'village': {
      const big = env === 'town';
      road([[-SIZE, 4], [-40, 0], [40, -2], [SIZE, 6]], big ? 13 : 9, big ? 'cobble' : 'dirt');
      road([[0, -SIZE * 0.7], [2, -20], [0, 20], [-6, SIZE]], 8, 'dirt');
      flatten.push({ x: 0, z: 0, rx: 36, rz: 30, h: heightAt(0, 0) });
      house(0, -46, 0, st.big, true); W.anchors.church = [0, -46];
      const n = big ? 34 : 18;
      for (let i = 0; i < n * 3 && W.buildings.length < n; i++) {
        const along = rng.range(-1, 1) * (big ? 220 : 150), side = rng.pick([-1, 1]);
        const x = along, z = side * rng.range(16, big ? 60 : 34) + (Math.abs(along) < 40 ? side * 18 : 0);
        house(x, z, side > 0 ? Math.PI : 0, big && rng.chance(0.6) ? st.town : st.house);
      }
      for (let i = 0; i < 10; i++) prop(rng.pick(['cart', 'crates', 'barrel', 'fence', 'well', 'hay']), rng.range(-90, 90), rng.range(-30, 30) + rng.pick([-18, 18]), rng() * 6);
      prop('well', 8, 10);
      // fields and hedgerows around (bocage)
      for (let i = 0; i < 26; i++) {
        const x = rng.range(-SIZE, SIZE), z = rng.range(-SIZE, SIZE);
        if (Math.hypot(x, z) < (big ? 170 : 120)) continue;
        fieldPatch(x, z, rng.range(50, 90), rng.range(40, 80), rng.range(-0.2, 0.2), rng.pick(['#7f9a4a', '#a3a04f', '#6f8d42', '#b9a35a', '#8aa152']));
      }
      for (let i = 0; i < 14; i++) { const x = rng.range(-SIZE, SIZE), z = rng.range(-SIZE, SIZE); if (Math.hypot(x, z) > 130) hedgeRow([[x, z], [x + rng.range(-80, 80), z + rng.range(30, 90)]]); }
      scatterTrees(big ? 160 : 220, treeKinds, SIZE, (x, z) => Math.hypot(x, z) < 50);
      W.anchors = { ...W.anchors, center: [0, 0], square: [0, 6], street: [-70, 2], edge: [-150, 6], field: [160, 120] };
      break;
    }
    case 'farmland': case 'hills': case 'valley': case 'mountains': case 'forest': {
      const dense = env === 'forest' ? 900 : env === 'mountains' ? 260 : 300;
      road([[-SIZE, -20], [-100, 10], [60, -10], [SIZE, 30]], 9, 'dirt');
      if (env === 'farmland') {
        for (let gx = -SIZE + 40; gx < SIZE; gx += 85) for (let gz = -SIZE + 40; gz < SIZE; gz += 75) {
          if (Math.abs(gz) < 30) continue;
          fieldPatch(gx + rng.range(-8, 8), gz + rng.range(-8, 8), rng.range(60, 80), rng.range(52, 66), rng.range(-0.12, 0.12), rng.pick(['#7f9a4a', '#a3a04f', '#6f8d42', '#b9a35a', '#8aa152', '#95a85e']));
          hedgeRow([[gx - 42, gz - 37], [gx + 42, gz - 37]]); if (rng.chance(0.7)) hedgeRow([[gx - 42, gz - 37], [gx - 42, gz + 37]]);
        }
        house(50, 50, 0.1, st.house); house(80, 62, 1.6, 'barn'); house(-120, -60, 0.4, st.house);
        for (let i = 0; i < 6; i++) prop('hay', rng.range(-200, 200), rng.range(40, 200));
      }
      scatterTrees(dense, env === 'mountains' ? ['pine', 'pine', 'rock'] : env === 'forest' ? ['pine', 'oak', 'oak', 'birch', 'bush'] : treeKinds, SIZE, (x, z) => Math.abs(z + Math.sin(x / 80) * 20) < 16);
      W.anchors = { center: [0, 0], road: [-40, 0], edge: [-160, 0], ridge: [0, -150] };
      break;
    }
    case 'jungle': {
      W.ground = 'jungle';
      road([[-SIZE, 40], [-80, 0], [40, 30], [SIZE, 0]], 5, 'trail');
      scatterTrees(1400, ['palm', 'broadleaf', 'broadleaf', 'fern', 'fern', 'bush'], SIZE, (x, z) => Math.hypot(x + 20, z - 10) < 34);
      for (let i = 0; i < 4; i++) house(rng.range(-60, 60), rng.range(-60, -30), rng() * 6, 'stilt_house');
      W.anchors = { center: [0, 20], trail: [-60, 6], clearing: [-20, 10], river: [river.path[6][0] - 26, river.path[6][1]] };
      break;
    }
    case 'desert': {
      W.ground = 'sand';
      road([[-SIZE, 0], [SIZE, 10]], 12, 'sand_road');
      for (let i = 0; i < 12; i++) house(rng.range(-80, 80), rng.range(-90, -30), rng() * 0.3, 'adobe');
      scatterTrees(50, ['palm', 'bush', 'rock'], SIZE, (x, z) => Math.abs(z) < 14);
      W.anchors = { center: [0, 0], road: [-80, 2], town: [0, -60] };
      break;
    }
    case 'beach': {
      W.ground = 'grass';
      const s0 = shoreZ(0);
      // tide-line obstacles, a sea wall, bunkers on the bluff, wire, then fields beyond
      for (let x = -260; x <= 260; x += rng.range(7, 11)) for (const k of [0, 1]) prop(rng.chance(0.7) ? 'hedgehog' : 'stake', x + rng.range(-2, 2), shoreZ(x) + 10 + k * 13 + rng.range(-2, 2), rng() * 6);
      for (let x = -250; x <= 250; x += 4) if (rng.chance(0.55)) prop('wire', x, shoreZ(x) + 64, 0);
      for (const bx of [-180, -60, 70, 190]) { const bz = shoreZ(bx) + 104; prop('bunker', bx, bz, Math.PI); W.colliders.push({ x0: bx - 9, x1: bx + 9, z0: bz - 7, z1: bz + 7, y1: heightAt(bx, bz) + 7 }); }
      for (let x = -300; x <= 300; x += 3) if (rng.chance(0.18)) tree(x, shoreZ(x) + 130 + rng.range(0, 60), rng.pick(['bush', 'oak']));
      for (let i = 0; i < 8; i++) fieldPatch(rng.range(-280, 280), shoreZ(0) + rng.range(200, 300), 70, 50, rng.range(-0.1, 0.1), rng.pick(['#7f9a4a', '#a3a04f', '#8aa152']));
      road([[-SIZE, s0 + 150], [SIZE, s0 + 160]], 7, 'dirt');
      if (opts.damaged !== false) for (let i = 0; i < 14; i++) W.craters.push({ x: rng.range(-220, 220), z: s0 + rng.range(14, 70), r: rng.range(3, 6), depth: rng.range(0.8, 1.6) });
      W.anchors = { center: [0, s0 + 30], waterline: [0, s0 - 4], surf: [0, s0 - 18], obstacles: [0, s0 + 16], shingle: [0, s0 + 52], bluff: [0, s0 + 100], offshore: [0, s0 - 110], far_sea: [0, s0 - 260] };
      break;
    }
    case 'port': {
      W.ground = 'paved';
      const q = shoreZ(0);
      for (const px of [-180, -60, 60, 180]) { prop('pier', px, q - 30, 0, { len: 60 }); }
      for (let i = 0; i < 10; i++) house(rng.range(-260, 260), q + rng.range(40, 90), 0, 'warehouse');
      for (const cx of [-120, 0, 120]) prop('crane', cx, q + 14, Math.PI);
      for (let i = 0; i < 30; i++) prop(rng.pick(['crates', 'barrel', 'crates']), rng.range(-250, 250), q + rng.range(8, 30), rng() * 6);
      W.anchors = { center: [0, q + 20], quay: [0, q + 10], water: [0, q - 50], warehouses: [0, q + 60], offshore: [0, q - 150] };
      break;
    }
    case 'island': { scatterTrees(260, culture === 'asian' || culture === 'american' ? ['palm', 'palm', 'bush', 'broadleaf'] : treeKinds, SIZE, (x, z) => heightAt(x, z) < 1); W.anchors = { center: [0, 40], beach: [0, shoreZ(0) + 6], offshore: [0, shoreZ(0) - 120] }; break; }
    case 'river': {
      scatterTrees(420, treeKinds, SIZE);
      const m = river.path[6];
      W.anchors = { center: [m[0], m[1]], bank_near: [m[0] + river.width + 10, m[1]], bank_far: [m[0] - river.width - 10, m[1]], water: [m[0], m[1]] };
      if (opts.variant === 'bridge') prop('bridge', m[0], m[1], Math.PI / 2, { len: river.width * 2.6 });
      for (let i = 0; i < 6; i++) house(m[0] + rng.range(50, 160), m[1] + rng.range(-120, 120), rng() * 6, st.house);
      break;
    }
    case 'airfield': {
      W.ground = 'grass';
      road([[-300, 0], [300, 0]], 34, 'runway'); road([[-200, 40], [200, 40]], 14, 'taxiway');
      for (const hx of [-150, -60, 30]) addBuilding({ kind: 'hangar', x: hx, z: 95, w: 60, d: 40, h: 16, rot: 0, wall: '#7d8579', roof: '#5c6359', roofH: 8, roofType: 'arch' });
      addBuilding({ kind: 'tower', x: 130, z: 80, w: 12, d: 12, h: 20, rot: 0, wall: '#d9d2c0', roof: '#4a4f55', roofH: 0, roofType: 'flat' });
      prop('windsock', 180, 60); for (let i = 0; i < 20; i++) prop(rng.pick(['barrel', 'crates']), rng.range(-200, 200), rng.range(60, 80));
      scatterTrees(200, treeKinds, SIZE, (x, z) => Math.abs(z) < 140);
      W.anchors = { center: [0, 0], runway_start: [-240, 0], runway_end: [240, 0], apron: [-60, 55], hangars: [-60, 95] };
      break;
    }
    case 'military_base': case 'factory': {
      W.ground = env === 'factory' ? 'paved' : 'dirt';
      road([[-SIZE, 0], [SIZE, 0]], 12, 'dirt'); road([[0, -200], [0, 200]], 10, 'dirt');
      if (env === 'factory') {
        for (const [x, z] of [[-90, -60], [10, -60], [110, -60], [-90, 60], [60, 60]]) addBuilding({ kind: 'shed', x, z, w: 70, d: 44, h: 14, rot: 0, wall: rng.pick(['#9a6a52', '#8a7a6a', '#a77b5b']), roof: '#4a4a4a', roofH: 6, roofType: 'sawtooth' });
        for (const x of [-120, -20, 80]) prop('chimney', x, -90, 0, { smoke: true });
        road([[-SIZE, 110], [SIZE, 110]], 6, 'rail');
      } else {
        for (let r = 0; r < 4; r++) for (let c = 0; c < 8; c++) prop('tent', -150 + c * 22, -40 - r * 22, 0);
        for (let c = 0; c < 6; c++) addBuilding({ kind: 'quonset', x: 40 + c * 28, z: -50, w: 18, d: 36, h: 9, rot: 0, wall: '#6f7468', roof: '#6f7468', roofH: 0, roofType: 'arch' });
        prop('tower_watch', 180, 60); prop('tower_watch', -190, 60);
        for (let i = 0; i < 40; i++) prop(rng.pick(['crates', 'crates', 'barrel', 'sandbags']), rng.range(-180, 180), rng.range(25, 70), rng() * 6);
        prop('flagpole', 0, -16);
        for (let x = -230; x <= 230; x += 12) prop('fence', x, 110, 0);
      }
      scatterTrees(220, treeKinds, SIZE, (x, z) => Math.abs(x) < 240 && Math.abs(z) < 130);
      W.anchors = { center: [0, 0], parade: [0, 14], tents: [-80, -60], depot: [0, 45], road: [-120, 0], gate: [0, 108] };
      break;
    }
    case 'battlefield': {
      W.ground = 'mud';
      for (let i = 0; i < 40; i++) W.craters.push({ x: rng.range(-220, 220), z: rng.range(-200, 200), r: rng.range(4, 9), depth: rng.range(1, 2.4) });
      for (const z of [-60, 70]) prop('trench', 0, z, 0, { len: 420 });
      for (let i = 0; i < 8; i++) house(rng.range(-200, 200), rng.range(-200, -100), rng() * 6, st.house);
      W.buildings.forEach((b) => { b.damaged = true; });
      for (let i = 0; i < 6; i++) prop('wreck', rng.range(-150, 150), rng.range(-40, 40), rng() * 6);
      scatterTrees(80, ['dead', 'dead', 'bush'], SIZE);
      W.anchors = { center: [0, 0], line_a: [0, 70], line_b: [0, -60], nomans: [0, 5] };
      break;
    }
    case 'interior': {
      W.ground = 'floor';
      W.interior = { w: 44, d: 30, h: 14, wall: opts.variant === 'bunker' ? '#7c7a72' : '#c9bfa8', floor: '#6b4a32', window: true, rainOutside: opts.weather === 'rain' || opts.weather === 'storm' };
      W.props.push({ kind: 'table_map', x: 0, z: 0, y: 0, rot: 0 }, { kind: 'wall_map', x: 0, z: -14.6, y: 0, rot: 0 }, { kind: 'lamp_hang', x: -8, z: 0, y: 0 }, { kind: 'lamp_hang', x: 8, z: 0, y: 0 },
        { kind: 'bookcase', x: 20, z: -13, y: 0, rot: 0 }, { kind: 'clock', x: -14, z: -14.6, y: 0 }, { kind: 'chair', x: -10, z: 6, y: 0, rot: Math.PI }, { kind: 'chair', x: 10, z: 6, y: 0, rot: Math.PI }, { kind: 'chair', x: 0, z: -7, y: 0, rot: 0 }, { kind: 'phone', x: 6, z: -1, y: 3.1 });
      const I = W.interior;
      W.colliders.push({ inside: true, x0: -I.w / 2 + 1.5, x1: I.w / 2 - 1.5, z0: -I.d / 2 + 1.5, z1: I.d / 2 - 1.5, y0: 1, y1: I.h - 1 });
      W.anchors = { center: [0, 0], table: [0, 0], head: [0, -6], window: [-21, 0], door: [21, 8] };
      break;
    }
    case 'sea': { W.anchors = { center: [0, 0], fleet: [0, -40], near: [0, 40] }; break; }
    default: W.anchors = { center: [0, 0] };
  }
  if (!W.anchors.center) W.anchors.center = [0, 0];
  W.anchorY = (name) => { const a = W.anchors[name] || W.anchors.center; return [a[0], heightAt(a[0], a[1]), a[1]]; };
  /** surface type at a point (for footstep sounds, dust colour and wading) */
  W.surfaceAt = (x, z) => {
    if (W.isWater(x, z)) return heightAt(x, z) > -1.6 ? 'shallow' : 'water';
    if (W.roads.some((r) => distToPolyline(x, z, r.points) < r.width / 2)) return 'road';
    if (env === 'beach' && shoreZ && z - shoreZ(x) < 72) return 'sand';
    return W.ground;
  };
  W.shoreZ = shoreZ;
  return W;
}

/** Ground height the camera may not go below at (x,z): terrain or water (+ building tops when over one). */
export function clearanceAt(W, x, z) {
  let h = Math.max(W.heightAt(x, z), W.water ? W.water.level : -Infinity);
  for (const c of W.colliders) if (!c.inside && x > c.x0 && x < c.x1 && z > c.z0 && z < c.z1) h = Math.max(h, c.y1);
  return h;
}
