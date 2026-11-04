// Ground sets generated from a recipe name and a seed: no hand-made models, no assets. A set is a square patch (n x n
// set units, FINE per world cell) placed on the terrain. The terrain itself is drawn by the renderer; props stand ON
// ctx.ground(x, z).y and obey it (no buildings on water or steep ground, paddies only on flat lowland near water ...).
//   box      { x, y, z, sx, sy, sz, c: [r,g,b], rot? }  x,z = CENTRE of the footprint (set units from the south-west corner);
//            y = ABSOLUTE bottom; rot = radians about the vertical axis around the centre (three.js rotation.y).
//   particles use the same convention (centre x/z, absolute base y).
//   emitter  { kind: 'smoke'|'fire'|'blast'|'rotor'|'flyer'|'chute'|'march', ... }
// Human scale: 1 set unit ~ 4 m, default set size n = 240 (~1 km). A person is 2 units tall (lib/figures.mjs); vehicles and
// buildings are sized to match. Sun is toward +x,+z, so contact shadows fall toward -x,-z. Pure and deterministic (seeded RNG only).
// buildSet(recipe, seed, n, ctx) reads optional ctx.factions (['us_marine', ...]), ctx.names (['Gen. Karch']) and ctx.signs
// (['WELCOME']) and returns { labels: [{x,y,z,text}], signs: [{x,y,z,w,h,rot,text}] } (sign face normal = (sin rot, cos rot)).

import { figure, formation, figureHeight, FACTIONS } from './figures.mjs';

export const FINE = 48;          // set units per world cell (1 unit ~ 58 m)
export const RECIPES = ['village', 'city', 'airfield', 'lz', 'battle', 'fortress', 'beach_landing', 'jungle', 'trail', 'delta', 'hall', 'office'];
export const INDOOR_RECIPES = ['hall', 'office'];

export const FLAT = { ground: () => ({ y: 0, water: 0, forest: false, color: [84, 138, 56] }) };

const MAX_BOXES = 20000;
const OLD_AREA = 144 * 144;   // sets used to be n = 144; counts of people scale with area from there
const C = {
  wall: [222, 214, 196], cream: [226, 206, 160], roof: [168, 66, 48], thatch: [176, 146, 88], concrete: [168, 168, 160],
  olive: [92, 98, 60], khaki: [150, 136, 96], steel: [130, 136, 140], dark: [38, 38, 40], white: [236, 236, 232],
  wood: [112, 80, 52], mud: [96, 70, 48], sand: [214, 196, 140], sandbag: [176, 158, 112], crater: [58, 46, 38],
  leaf: [48, 98, 42], skin: [196, 150, 118], rubber: [30, 30, 32], wire: [60, 56, 52], glass: [90, 130, 150],
  tan: [190, 168, 120], grey: [120, 124, 128], navy: [74, 84, 96], paddy: [96, 150, 70], water: [70, 120, 130],
};

function mulberry32(seed) {
  let a = (seed >>> 0) || 1;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const hashStr = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return h >>> 0; };
const clamp8 = (v) => Math.max(0, Math.min(255, Math.round(v)));
const mul = (c, k) => [clamp8(c[0] * k), clamp8(c[1] * k), clamp8(c[2] * k)];
const PI = Math.PI;

// ---------------------------------------------------------------------------------------------------------------------
// Environment: seeded RNG, layout rotation, ground-aware placement, occupancy
// ---------------------------------------------------------------------------------------------------------------------
function makeEnv(recipe, seed, n, ctx) {
  const r = mulberry32((seed >>> 0) * 2654435761 + hashStr(recipe));
  r(); r();
  const boxes = [], emitters = [];
  const occ = new Uint8Array(n * n);
  const E = { r, n, ctx, boxes, emitters, marches: [], A: r() * PI * 2, cu: n / 2, cv: n / 2, focus: [n / 2, n / 2], kA: (n * n) / OLD_AREA };
  E.ancient = isAncient(ctx);   // before firearms: no engines, guns or concrete anywhere in the set
  E.rr = (a, b) => a + r() * (b - a);
  E.ri = (a, b) => a + Math.floor(r() * (b - a + 1));
  E.pick = (arr) => arr[Math.floor(r() * arr.length)];
  E.chance = (p) => r() < p;
  E.vary = (c, k = 0.12) => mul(c, 1 - k + r() * 2 * k);
  E.G = (x, z) => ctx.ground(x, z);
  E.toW = (u, v) => { const c = Math.cos(E.A), s = Math.sin(E.A); return [E.cu + u * c + v * s, E.cv - u * s + v * c]; };

  const push = (b) => { if (boxes.length < MAX_BOXES + (E.reserve ? 300 : 0)) boxes.push(b); };
  E.full = () => boxes.length >= MAX_BOXES - 400;
  // centred box at world (cx, cz); y = bottom
  E.box = (cx, cz, y, sx, sy, sz, c, rot = 0) => {
    const b = { x: cx, y, z: cz, sx, sy, sz, c };
    if (rot) b.rot = rot;
    push(b);
  };
  // composite parts [dx, dy, dz, sx, sy, sz, c, rl?]; dx,dz rotated by th
  E.compose = (parts, cx, cz, y, th) => {
    const c = Math.cos(th), s = Math.sin(th);
    for (const p of parts) E.box(cx + p[0] * c + p[2] * s, cz - p[0] * s + p[2] * c, y + p[1], p[3], p[4], p[5], p[6], th + (p[7] || 0));
  };

  // occupancy (1 unit cells)
  const cellsOf = (x, z, rad, fn) => {
    const x0 = Math.max(0, Math.floor(x - rad)), x1 = Math.min(n - 1, Math.floor(x + rad));
    const z0 = Math.max(0, Math.floor(z - rad)), z1 = Math.min(n - 1, Math.floor(z + rad));
    for (let zz = z0; zz <= z1; zz++) for (let xx = x0; xx <= x1; xx++) { const dx = xx + 0.5 - x, dz = zz + 0.5 - z; if (dx * dx + dz * dz <= rad * rad) { if (fn(zz * n + xx)) return true; } }
    return false;
  };
  E.isFree = (x, z, rad) => !cellsOf(x, z, rad, (i) => occ[i] === 1);
  E.take = (x, z, rad) => { cellsOf(x, z, rad, (i) => { occ[i] = 1; return false; }); };

  // footprint test: 3x3 samples over a rotated rectangle
  E.fp = (cx, cz, w, d, th, o = {}) => {
    const mode = o.mode || 'land', slope = o.slope ?? 2;
    const c = Math.cos(th), s = Math.sin(th);
    let lo = 1e9, hi = -1e9;
    for (const a of [-0.5, 0, 0.5]) for (const b of [-0.5, 0, 0.5]) {
      const lx = a * w, lz = b * d, x = cx + lx * c + lz * s, z = cz - lx * s + lz * c;
      if (x < 1 || z < 1 || x > n - 1 || z > n - 1) return null;
      const g = ctx.ground(x, z);
      if (mode === 'land') { if (g.water !== 0 && !(o.shore && g.water === 2)) return null; }
      else if (g.water !== 1 && g.water !== 3) return null;
      if (g.y < lo) lo = g.y; if (g.y > hi) hi = g.y;
    }
    if (mode === 'land' && hi - lo > slope) return null;
    const rad = 0.5 * Math.hypot(w, d) * (o.free ?? 0.7);
    if (!o.noocc && !E.isFree(cx, cz, rad)) return null;
    return { y: lo, hi, lo, rad, gc: ctx.ground(cx, cz).color };
  };
  E.shadow = (cx, cz, w, d, th, h, f) => {
    E.box(cx - 0.4 * h, cz - 0.4 * h, f.lo + 0.03, w, 0.06, d, mul(f.gc, 0.55), th);
  };

  // place a definition {w,d,h,parts,...} at world x,z with total rotation th
  E.put = (def, x, z, th, o = {}) => {
    const kind = def.kind || 'bld';
    const f = E.fp(x, z, def.w, def.d, th, { slope: kind === 'veh' ? 1.2 : 2, mode: def.mode, ...o });
    if (!f) return null;
    E.take(x, z, f.rad);
    if (def.mode === 'water') { E.compose(def.parts, x, z, f.y + 0.05, th); return { x, z, y: f.y, th, h: def.h }; }
    const base = kind === 'veh' ? (f.lo + f.hi) / 2 : f.hi;
    if (kind !== 'veh' && f.hi - f.lo > 0.2) E.box(x, z, f.lo - 0.1, def.w * 0.96, f.hi - f.lo + 0.2, def.d * 0.96, mul(f.gc, 0.7), th);
    E.compose(def.parts, x, z, base, th);
    if (!def.noShadow) E.shadow(x, z, def.w, def.d, th, def.h, f);
    return { x, z, y: base, th, h: def.h };
  };
  E.putL = (def, u, v, hd, o) => { const [x, z] = E.toW(u, v); return E.put(def, x, z, E.A + hd, o); };

  // linear piece strip in world coords (road, trench ...); cut into short pieces that follow the terrain
  E.seg = (x1, z1, x2, z2, wd, h, c, o = {}) => {
    const L = Math.hypot(x2 - x1, z2 - z1); if (L < 0.01) return 0;
    const k = Math.max(1, Math.ceil(L / (o.step || 3))), th = Math.atan2(-(z2 - z1), x2 - x1);
    let placed = 0;
    for (let i = 0; i < k; i++) {
      const t = (i + 0.5) / k, cx = x1 + (x2 - x1) * t, cz = z1 + (z2 - z1) * t, pl = L / k + 0.06;
      const f = E.fp(cx, cz, pl, Math.max(wd, 1), th, { slope: o.slope ?? 2.5, noocc: true, mode: o.mode });
      if (!f) continue;
      E.box(cx, cz, (f.lo + f.hi) / 2 - 0.02 + (o.lift ?? 0), pl, h, wd, o.jit ? E.vary(c, o.jit) : c, th);
      placed++;
    }
    return placed;
  };
  E.segL = (u1, v1, u2, v2, wd, h, c, o) => { const a = E.toW(u1, v1), b = E.toW(u2, v2); return E.seg(a[0], a[1], b[0], b[1], wd, h, c, o); };

  // coarse maps (lazy): distance to open water, distance to land, relief
  let coarse = null;
  const cs = 3;
  E.coarse = () => {
    if (coarse) return coarse;
    const gw = Math.ceil(n / cs), wat = new Uint8Array(gw * gw), yy = new Float32Array(gw * gw), forest = new Uint8Array(gw * gw);
    let anyW = false;
    for (let j = 0; j < gw; j++) for (let i = 0; i < gw; i++) {
      const g = ctx.ground((i + 0.5) * cs, (j + 0.5) * cs), w = g.water === 1 || g.water === 3 ? 1 : 0;
      wat[j * gw + i] = w; yy[j * gw + i] = g.y; forest[j * gw + i] = g.forest ? 1 : 0; if (w) anyW = true;
    }
    const dt = (isSrc) => {
      const d = new Float32Array(gw * gw).fill(1e9);
      for (let i = 0; i < d.length; i++) if (isSrc(i)) d[i] = 0;
      const at = (i, j) => (i < 0 || j < 0 || i >= gw || j >= gw ? 1e9 : d[j * gw + i]);
      for (let j = 0; j < gw; j++) for (let i = 0; i < gw; i++) { const k = j * gw + i; d[k] = Math.min(d[k], at(i - 1, j) + cs, at(i, j - 1) + cs, at(i - 1, j - 1) + cs * 1.414, at(i + 1, j - 1) + cs * 1.414); }
      for (let j = gw - 1; j >= 0; j--) for (let i = gw - 1; i >= 0; i--) { const k = j * gw + i; d[k] = Math.min(d[k], at(i + 1, j) + cs, at(i, j + 1) + cs, at(i + 1, j + 1) + cs * 1.414, at(i - 1, j + 1) + cs * 1.414); }
      return d;
    };
    coarse = { gw, anyW, wat, y: yy, forest, dw: dt((i) => wat[i] === 1), dl: dt((i) => wat[i] === 0) };
    return coarse;
  };
  const look = (arr, x, z) => { const q = E.coarse(); const i = Math.max(0, Math.min(q.gw - 1, Math.floor(x / cs))), j = Math.max(0, Math.min(q.gw - 1, Math.floor(z / cs))); return arr[j * q.gw + i]; };
  E.hasWater = () => E.coarse().anyW;
  E.wd = (x, z) => (E.hasWater() ? look(E.coarse().dw, x, z) : Infinity);   // distance to open water
  E.ld = (x, z) => look(E.coarse().dl, x, z);                                 // distance to land
  E.relief = (x, z, rad = 4) => {
    let lo = 1e9, hi = -1e9;
    for (const [a, b] of [[0, 0], [rad, 0], [-rad, 0], [0, rad], [0, -rad], [rad, rad], [-rad, -rad], [rad, -rad], [-rad, rad]]) { const y = ctx.ground(x + a, z + b).y; if (y < lo) lo = y; if (y > hi) hi = y; }
    return hi - lo;
  };
  E.rel = (arr) => arr; // placeholder to keep API tidy
  return E;
}

// ---------------------------------------------------------------------------------------------------------------------
// Definitions: buildings, equipment, people, trees. Parts: [dx, dy, dz, sx, sy, sz, colour, rotLocal]
// Vehicle forward = local +x.
// ---------------------------------------------------------------------------------------------------------------------
const P = (dx, dy, dz, sx, sy, sz, c, rl = 0) => [dx, dy, dz, sx, sy, sz, c, rl];

const D = {
  stiltHut(E) {
    const roof = E.chance(0.5) ? C.thatch : mul(C.thatch, 0.8), wall = E.vary([160, 126, 84]);
    const w = E.rr(3, 3.8), d = E.rr(2.4, 3);
    const parts = [];
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) parts.push(P(sx * (w / 2 - 0.2), 0, sz * (d / 2 - 0.2), 0.2, 1, 0.2, C.wood));
    parts.push(P(0, 1, 0, w, 0.15, d, C.wood), P(0, 1.15, 0, w - 0.4, 1, d - 0.4, wall), P(0, 2.1, 0, w + 0.6, 0.3, d + 0.6, roof), P(0, 2.4, 0, w - 0.4, 0.3, d - 0.2, roof), P(0, 2.7, 0, w - 1.6, 0.25, d - 1.2, roof));
    parts.push(P(w / 2 + 0.3, 0.1, 0, 0.1, 0.9, 0.5, C.wood, 0), P(w / 2 - 0.05, 1.5, 0, 0.1, 0.45, 0.5, C.dark));
    return { w: w + 0.8, d: d + 0.8, h: 2.9, parts };
  },
  groundHut(E) {
    const roof = E.pick([C.thatch, C.thatch, C.roof, [150, 120, 74]]), wall = E.vary(E.pick([C.wall, [196, 170, 126], [168, 140, 100]]));
    const w = E.rr(2.6, 3.6), d = E.rr(2.4, 3.2);
    return { w: w + 0.6, d: d + 0.6, h: 2.2, parts: [P(0, 0, 0, w, 1.2, d, wall), P(0, 1.2, 0, w + 0.6, 0.3, d + 0.6, roof), P(0, 1.5, 0, w - 0.2, 0.3, d, roof), P(0, 1.8, 0, w - 1.2, 0.25, d - 1, roof), P(w / 2, 0, 0, 0.08, 0.9, 0.5, C.dark)] };
  },
  villa(E) {
    const w = 7, d = 6, hh = E.rr(3, 4), wall = E.pick([C.cream, C.wall, [232, 214, 150]]), roof = E.pick([C.roof, [150, 70, 52]]);
    const pw = w + 4, pd = d + 4, parts = [];
    parts.push(P(-1, 0, 0, w, hh, d, wall), P(-1, hh, 0, w + 0.6, 0.35, d + 0.6, roof), P(-1, hh + 0.35, 0, w - 0.6, 0.45, d - 0.6, roof), P(-1, hh + 0.8, 0, w - 2.2, 0.4, d - 2, roof));
    parts.push(P(-1 + w / 2 + 0.05, hh * 0.35, 0, 0.1, hh * 0.45, d - 1.4, C.dark));
    for (let i = -2; i <= 2; i++) parts.push(P(-1 + w / 2 + 0.7, 0, i * 1.1, 0.25, hh * 0.8, 0.25, C.white));
    parts.push(P(-1 + w / 2 + 0.7, hh * 0.8, 0, 0.9, 0.2, d - 0.4, C.white));
    // courtyard wall with a gate gap on the +x side
    parts.push(P(0, 0, pd / 2, pw, 0.9, 0.3, C.wall), P(0, 0, -pd / 2, pw, 0.9, 0.3, C.wall), P(-pw / 2, 0, 0, 0.3, 0.9, pd, C.wall));
    parts.push(P(pw / 2, 0, pd / 4 + 0.7, 0.3, 0.9, pd / 2 - 1.4, C.wall), P(pw / 2, 0, -pd / 4 - 0.7, 0.3, 0.9, pd / 2 - 1.4, C.wall));
    parts.push(P(pw / 2 - 1.6, 0, pd / 2 - 1.4, 0.3, 1.6, 0.3, C.wood), P(pw / 2 - 1.6, 1.6, pd / 2 - 1.4, 1.4, 0.7, 1.4, C.leaf));
    return { w: pw, d: pd, h: hh + 1.2, parts };
  },
  building(E, o = {}) {
    const w = o.w || E.rr(4, 7), d = o.d || E.rr(4, 7), floors = o.floors || 2, hh = floors * 2.0 + 0.4;
    const body = o.c || E.vary(E.pick([C.wall, [210, 196, 170], [190, 176, 150], [170, 160, 150], [214, 190, 140]]), 0.08);
    const parts = [P(0, 0, 0, w, hh, d, body)];
    for (let f = 0; f < floors; f++) parts.push(P(0, f * 2.0 + 1.2, 0, w + 0.06, 0.5, d + 0.06, mul(body, 0.55)));
    parts.push(P(0, hh, 0, w + 0.3, 0.3, d + 0.3, mul(body, 0.8)));
    if (o.roof !== false && floors < 4) parts.push(P(0, hh + 0.3, 0, w - 0.4, 0.5, d - 0.4, C.roof), P(0, hh + 0.8, 0, w - 1.8, 0.35, d - 1.8, C.roof));
    else if (E.chance(0.6)) parts.push(P(E.rr(-w / 4, w / 4), hh + 0.3, E.rr(-d / 4, d / 4), 1, 0.8, 1, C.steel));
    parts.push(P(w / 2 + 0.03, 0, 0, 0.1, 1.9, 1.1, C.dark));
    return { w, d, h: hh + 0.9, parts };
  },
  market(E) {
    const w = 11, d = 9, parts = [P(0, 0, 0, w, 0.08, d, [176, 160, 120])];
    const aw = [[196, 60, 50], [60, 120, 170], [210, 170, 50], [90, 150, 80], [220, 220, 210]];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) {
      const x = -3.4 + i * 3.4, z = -2.2 + j * 4.4, ac = E.pick(aw);
      parts.push(P(x, 0.08, z, 2.4, 0.7, 1.4, C.wood), P(x, 1.5, z, 2.8, 0.2, 2.2, ac), P(x - 1.2, 0.08, z - 1, 0.12, 1.4, 0.12, C.wood), P(x + 1.2, 0.08, z + 1, 0.12, 1.4, 0.12, C.wood), P(x, 0.78, z, 1.6, 0.3, 0.8, E.pick([ac, C.tan, C.leaf])));
    }
    return { w, d, h: 1.8, parts, noShadow: false };
  },
  hangar(E) {
    const w = 10, d = 9, c = E.pick([C.steel, C.concrete, [150, 150, 140]]);
    return { w, d, h: 3.6, parts: [P(0, 0, 0, w, 2, d, c), P(0, 2, 0, w - 0.6, 0.8, d - 1.2, mul(c, 0.9)), P(0, 2.8, 0, w - 1.8, 0.7, d - 3, mul(c, 0.8)), P(w / 2 + 0.03, 0, 0, 0.12, 1.8, d - 1.4, C.dark)] };
  },
  tower(E) {
    return { w: 3, d: 3, h: 7, parts: [P(0, 0, 0, 2.6, 0.8, 2.6, C.concrete), P(0, 0.8, 0, 1, 4, 1, C.wall), P(0, 4.8, 0, 2.6, 1.1, 2.6, C.glass), P(0, 5.9, 0, 3, 0.3, 3, C.concrete), P(0, 6.2, 0, 0.12, 1.1, 0.12, C.steel)] };
  },
  bunker(E) {
    return { w: 4.6, d: 3.8, h: 1.6, parts: [P(0, 0, 0, 3.4, 1.1, 2.6, C.concrete), P(0, 1.1, 0, 3.6, 0.25, 2.8, mul(C.concrete, 0.85)), P(1.72, 0.6, 0, 0.1, 0.3, 1.6, C.dark), P(-1.4, 0, 0, 1.2, 0.8, 3.6, C.mud), P(0.6, 0, -1.7, 2.8, 0.7, 0.7, C.mud), P(0.6, 0, 1.7, 2.8, 0.7, 0.7, C.mud)] };
  },
  revetment(E) {
    const c = E.pick([C.sandbag, C.sand, [150, 130, 96]]);
    return { w: 6, d: 5.4, h: 1.2, parts: [P(-2.6, 0, 0, 0.8, 1.1, 5.2, c), P(0, 0, -2.4, 5.4, 1.1, 0.8, c), P(0, 0, 2.4, 5.4, 1.1, 0.8, c)], noShadow: true };
  },
  fuelTank(E) {
    const s = E.rr(2.2, 3), h = E.rr(1.6, 2.4), c = E.pick([C.steel, C.white, C.grey]);
    return { w: s, d: s, h, parts: [P(0, 0, 0, s * 0.72, h, s * 0.72, c), P(0, 0, 0, s * 0.72, h, s * 0.72, c, PI / 4), P(0, h, 0, s * 0.5, 0.2, s * 0.5, mul(c, 0.8))] };
  },
  tent(E) {
    const c = E.pick([C.olive, C.khaki, [110, 112, 80]]);
    return { w: 3, d: 2.6, h: 1.4, parts: [P(0, 0, 0, 2.8, 0.7, 2.4, c), P(0, 0.7, 0, 2.2, 0.4, 2.4, c), P(0, 1.1, 0, 1.2, 0.3, 2.4, mul(c, 0.9))] };
  },
  watchtower(E) {
    return { w: 2.2, d: 2.2, h: 3.8, parts: [P(-0.8, 0, -0.8, 0.2, 2.6, 0.2, C.wood), P(0.8, 0, -0.8, 0.2, 2.6, 0.2, C.wood), P(-0.8, 0, 0.8, 0.2, 2.6, 0.2, C.wood), P(0.8, 0, 0.8, 0.2, 2.6, 0.2, C.wood), P(0, 2.6, 0, 2.0, 0.2, 2.0, C.wood), P(0, 2.8, 0, 1.6, 0.8, 1.6, C.olive), P(0, 3.6, 0, 2.2, 0.25, 2.2, C.thatch)] };
  },
  supply(E) {
    const parts = [], c = E.pick([C.olive, C.wood, C.khaki, [120, 100, 70]]), nx = E.ri(2, 3), nz = E.ri(2, 3);
    for (let i = 0; i < nx; i++) for (let j = 0; j < nz; j++) { const h = E.ri(1, 2); for (let k = 0; k < h; k++) parts.push(P(i * 0.85 - nx * 0.4, k * 0.6, j * 0.85 - nz * 0.4, 0.8, 0.58, 0.8, E.vary(c, 0.1))); }
    return { w: nx * 0.9, d: nz * 0.9, h: 1.2, parts };
  },
  sandbagRing(E, rad = 1.5) {
    const parts = [], k = 10;
    for (let i = 0; i < k; i++) { if (i === 0) continue; const a = (i / k) * PI * 2; parts.push(P(Math.cos(a) * rad, 0, Math.sin(a) * rad, 0.9, 0.5, 0.55, E.vary(C.sandbag, 0.08), -a + PI / 2 - PI / 2 + 0)); }
    parts.push(P(0, 0, 0, 0.5, 0.8, 0.3, C.olive));
    return { w: rad * 2 + 1, d: rad * 2 + 1, h: 0.8, parts, noShadow: true };
  },
  // ---- vehicles
  tank(E, col) {
    const c = col || C.olive, t = mul(c, 0.5);
    return { kind: 'veh', w: 2, d: 1.2, h: 0.9, parts: [P(0, 0.12, 0, 1.6, 0.4, 0.9, c), P(0, 0, 0.5, 1.8, 0.3, 0.22, C.rubber), P(0, 0, -0.5, 1.8, 0.3, 0.22, C.rubber), P(-0.05, 0.52, 0, 0.8, 0.3, 0.7, mul(c, 1.05)), P(0.85, 0.62, 0, 1, 0.09, 0.09, t), P(-0.1, 0.8, 0.15, 0.2, 0.1, 0.2, t)] };
  },
  apc(E, col) {
    const c = col || C.olive;
    return { kind: 'veh', w: 1.8, d: 1.1, h: 0.9, parts: [P(0, 0.12, 0, 1.5, 0.5, 0.85, c), P(0.5, 0.62, 0, 0.5, 0.12, 0.7, mul(c, 0.9)), P(0, 0, 0.45, 1.6, 0.28, 0.2, C.rubber), P(0, 0, -0.45, 1.6, 0.28, 0.2, C.rubber), P(-0.2, 0.62, 0, 0.5, 0.22, 0.5, mul(c, 1.1)), P(-0.2, 0.84, 0, 0.45, 0.06, 0.06, C.dark)] };
  },
  truck(E, col) {
    const c = col || E.pick([C.olive, C.khaki, [100, 96, 70]]);
    return { kind: 'veh', w: 2.6, d: 1.1, h: 1.2, parts: [P(0.85, 0.28, 0, 0.8, 0.8, 0.85, c), P(1.1, 0.7, 0, 0.1, 0.3, 0.7, C.glass), P(-0.4, 0.28, 0, 1.7, 0.2, 0.9, C.wood), P(-0.4, 0.48, 0, 1.7, 0.7, 0.9, mul(c, 0.75)), P(-0.4, 1.18, 0, 1.7, 0.08, 0.9, E.chance(0.5) ? C.tan : c), P(0.85, 0.05, 0.5, 0.45, 0.4, 0.14, C.rubber), P(0.85, 0.05, -0.5, 0.45, 0.4, 0.14, C.rubber), P(-0.85, 0.05, 0.5, 0.45, 0.4, 0.14, C.rubber), P(-0.85, 0.05, -0.5, 0.45, 0.4, 0.14, C.rubber)] };
  },
  jeep(E, col) {
    const c = col || C.olive;
    return { kind: 'veh', w: 1.5, d: 0.9, h: 0.8, parts: [P(0, 0.2, 0, 1.3, 0.35, 0.75, c), P(0.35, 0.55, 0, 0.1, 0.3, 0.7, C.glass), P(-0.2, 0.55, 0, 0.5, 0.18, 0.6, mul(c, 0.8)), P(0.45, 0.05, 0.4, 0.3, 0.3, 0.12, C.rubber), P(0.45, 0.05, -0.4, 0.3, 0.3, 0.12, C.rubber), P(-0.45, 0.05, 0.4, 0.3, 0.3, 0.12, C.rubber), P(-0.45, 0.05, -0.4, 0.3, 0.3, 0.12, C.rubber)] };
  },
  howitzer(E, col) {
    const c = col || C.olive;
    return { kind: 'veh', w: 2.6, d: 1.4, h: 0.9, parts: [P(0, 0, 0, 1, 0.3, 0.8, c), P(-0.1, 0.3, 0, 0.55, 0.4, 0.7, mul(c, 1.1)), P(1, 0.5, 0, 1.6, 0.12, 0.12, mul(c, 0.5), 0), P(1.6, 0.58, 0, 0.5, 0.1, 0.1, mul(c, 0.4)), P(-0.9, 0, 0.45, 1, 0.1, 0.12, C.dark, 0.3), P(-0.9, 0, -0.45, 1, 0.1, 0.12, C.dark, -0.3), P(0, 0, 0.55, 0.5, 0.45, 0.1, C.rubber), P(0, 0, -0.55, 0.5, 0.45, 0.1, C.rubber)] };
  },
  helicopter(E, col) {
    const c = col || C.olive;
    return { kind: 'veh', w: 3.4, d: 1.6, h: 1.4, rotorY: 1.25, rotorLen: 3.4, parts: [P(0.3, 0.35, 0, 1.5, 0.6, 0.7, c), P(0.95, 0.5, 0, 0.5, 0.35, 0.62, C.glass), P(-1.0, 0.55, 0, 1.5, 0.18, 0.18, mul(c, 0.9)), P(-1.7, 0.55, 0, 0.1, 0.55, 0.14, mul(c, 0.9)), P(0.1, 0.12, 0.38, 1.5, 0.07, 0.07, C.dark), P(0.1, 0.12, -0.38, 1.5, 0.07, 0.07, C.dark), P(0.1, 0.19, 0.38, 0.07, 0.17, 0.07, C.dark), P(0.1, 0.19, -0.38, 0.07, 0.17, 0.07, C.dark), P(0.3, 0.95, 0, 0.14, 0.3, 0.14, C.dark)] };
  },
  jet(E, col) {
    const c = col || E.pick([C.grey, [150, 154, 158], C.steel]);
    return { kind: 'veh', w: 3.8, d: 3, h: 0.8, parts: [P(0, 0.12, 0, 3.4, 0.4, 0.42, c), P(1.7, 0.18, 0, 0.8, 0.28, 0.32, mul(c, 0.8)), P(0.2, 0.3, 0, 1, 0.14, 0.34, C.glass), P(-0.3, 0.16, 0, 1, 0.08, 2.8, mul(c, 0.9), -0.0), P(-1.5, 0.3, 0, 0.6, 0.06, 1.2, mul(c, 0.9)), P(-1.5, 0.45, 0, 0.7, 0.45, 0.07, mul(c, 0.85)), P(-1.9, 0.12, 0, 0.3, 0.3, 0.3, C.dark)] };
  },
  cargoPlane(E, col) {
    const c = col || E.pick([C.concrete, C.olive, [180, 182, 176]]);
    return { kind: 'veh', w: 7, d: 8, h: 1.8, parts: [P(0, 0.3, 0, 6.4, 1.1, 1.1, c), P(3.1, 0.45, 0, 0.9, 0.7, 0.9, mul(c, 0.9)), P(-3, 1.1, 0, 1.4, 1.4, 0.12, mul(c, 0.9)), P(-3.1, 1.6, 0, 1.2, 0.1, 3, mul(c, 0.9)), P(0.2, 1.0, 0, 1.8, 0.14, 7.6, mul(c, 0.85)), P(0.6, 0.75, 2.2, 0.9, 0.35, 0.4, C.dark), P(0.6, 0.75, -2.2, 0.9, 0.35, 0.4, C.dark), P(0.6, 0.75, 3.6, 0.8, 0.3, 0.35, C.dark), P(0.6, 0.75, -3.6, 0.8, 0.3, 0.35, C.dark), P(1, 0.0, 0, 0.3, 0.3, 0.3, C.rubber), P(-1, 0.0, 0.7, 0.3, 0.3, 0.3, C.rubber), P(-1, 0.0, -0.7, 0.3, 0.3, 0.3, C.rubber)] };
  },
  landingCraft(E, col) {
    const c = col || C.olive;
    return { kind: 'veh', mode: 'water', w: 4.2, d: 1.8, h: 0.9, parts: [P(0, 0, 0, 3.6, 0.5, 1.5, c), P(1.9, 0, 0, 0.7, 0.4, 1.2, mul(c, 0.8)), P(2.3, 0.05, 0, 0.15, 0.45, 1.5, mul(c, 0.7)), P(-1.4, 0.5, 0, 0.8, 0.45, 1.3, mul(c, 1.1)), P(0.3, 0.5, 0.65, 2.6, 0.2, 0.08, c), P(0.3, 0.5, -0.65, 2.6, 0.2, 0.08, c)] };
  },
  patrolBoat(E, col) {
    const c = col || C.grey;
    return { kind: 'veh', mode: 'water', w: 3.2, d: 1.2, h: 1.1, parts: [P(0, 0, 0, 2.6, 0.4, 0.9, c), P(1.4, 0, 0, 0.8, 0.3, 0.5, c), P(-0.3, 0.4, 0, 1.1, 0.5, 0.7, C.white), P(-0.3, 0.9, 0, 0.9, 0.1, 0.6, C.dark), P(0.8, 0.4, 0, 0.3, 0.2, 0.3, C.dark), P(-0.4, 0.95, 0, 0.08, 0.5, 0.08, C.steel)] };
  },
  sampan(E) {
    const c = E.pick([C.wood, [120, 84, 52], [90, 70, 50]]);
    return { kind: 'veh', mode: 'water', w: 2.4, d: 0.8, h: 0.7, parts: [P(0, 0, 0, 2, 0.22, 0.6, c), P(1.1, 0.04, 0, 0.5, 0.22, 0.4, c), P(-1.1, 0.04, 0, 0.5, 0.22, 0.4, c), P(0.1, 0.22, 0, 1, 0.4, 0.55, C.thatch), P(-0.9, 0.22, 0, 0.06, 0.5, 0.06, C.wood)] };
  },
  ship(E) {
    const c = E.pick([C.navy, C.grey, [100, 108, 116]]);
    return { kind: 'veh', mode: 'water', w: 11, d: 3.4, h: 3.4, parts: [P(0, 0, 0, 9.6, 1.1, 2.6, c), P(5, 0, 0, 1.6, 1, 1.8, c), P(-0.4, 1.1, 0, 5.4, 0.7, 2.0, mul(c, 1.15)), P(-0.8, 1.8, 0, 2.2, 0.9, 1.5, mul(c, 1.25)), P(-0.8, 2.7, 0, 0.9, 0.5, 0.9, C.white), P(2.4, 1.1, 0, 1.2, 0.35, 0.35, C.dark), P(-1.6, 3.2, 0, 0.1, 0.9, 0.1, C.steel), P(-3.2, 1.1, 0, 1.0, 0.5, 1.0, C.dark)] };
  },
  bicycle(E) {
    const load = E.pick([[170, 150, 100], [120, 100, 70], [140, 128, 90]]);
    return { kind: 'veh', w: 1.5, d: 0.5, h: 1.2, noShadow: true, parts: [P(0.5, 0, 0, 0.08, 0.5, 0.5, C.rubber), P(-0.5, 0, 0, 0.08, 0.5, 0.5, C.rubber), P(0, 0.35, 0, 1.0, 0.07, 0.07, C.dark), P(-0.3, 0.45, 0, 0.9, 0.7, 0.4, load), P(-0.3, 1.1, 0, 0.5, 0.25, 0.3, load), P(0.55, 0.85, 0, 0.08, 0.08, 0.5, C.dark)] };
  },
  parachuteGround(E) {
    const c = E.pick([C.white, [230, 230, 220], [200, 190, 150], [150, 170, 110]]);
    return { kind: 'veh', w: 3.6, d: 3, h: 0.1, noShadow: true, parts: [P(0, 0, 0, 3.4, 0.07, 2.4, c, E.rr(-0.6, 0.6)), P(0.8, 0.02, 0.5, 2, 0.07, 1.8, mul(c, 0.9), E.rr(-1, 1))] };
  },
};


// ---- before firearms (ctx.era === 'ancient', or ancient factions): what replaces engines, guns and concrete
Object.assign(D, {
  oxcart(E) {
    const w = E.pick([C.wood, [120, 90, 58]]), ox = E.pick([[120, 92, 64], [90, 70, 52], [160, 140, 110]]), load = E.pick([[176, 150, 100], C.thatch, [140, 120, 86]]);
    return { kind: 'veh', w: 3.4, d: 1.4, h: 1.4, parts: [P(1.15, 0.45, 0, 1.0, 0.55, 0.5, ox), P(1.75, 0.65, 0, 0.3, 0.3, 0.3, ox), P(1.15, 0, 0.18, 0.12, 0.45, 0.12, ox), P(1.15, 0, -0.18, 0.12, 0.45, 0.12, ox),
      P(0.45, 0.6, 0, 0.9, 0.08, 0.08, w), P(-0.5, 0.45, 0, 1.4, 0.15, 1.0, w), P(-0.5, 0.6, 0, 1.2, 0.5, 0.9, load), P(-0.5, 0, 0.56, 0.6, 0.6, 0.1, w), P(-0.5, 0, -0.56, 0.6, 0.6, 0.1, w)] };
  },
  catapult(E) {
    const w = E.pick([C.wood, [128, 96, 60]]), dk = mul(w, 0.7);
    return { kind: 'veh', w: 2.6, d: 1.6, h: 1.8, parts: [P(0, 0, 0.6, 2.4, 0.2, 0.2, w), P(0, 0, -0.6, 2.4, 0.2, 0.2, w), P(-0.9, 0.2, 0, 0.2, 0.2, 1.4, w), P(0.9, 0.2, 0, 0.2, 0.2, 1.4, w),
      P(0.1, 0.2, 0.6, 0.2, 1.1, 0.2, dk), P(0.1, 0.2, -0.6, 0.2, 1.1, 0.2, dk), P(0.1, 1.2, 0, 0.2, 0.2, 1.3, dk), P(-0.4, 0.4, 0, 1.6, 0.14, 0.14, w, 0), P(-1.15, 0.45, 0, 0.36, 0.2, 0.36, [90, 90, 90])] };
  },
  galley(E) {
    const h = E.pick([[120, 84, 52], [96, 70, 46]]), sail = E.pick([[226, 216, 190], [196, 70, 56], [220, 200, 150]]), parts = [P(0, 0, 0, 7.4, 0.7, 1.6, h), P(3.9, 0.2, 0, 0.8, 0.5, 0.8, mul(h, 0.8)), P(-3.7, 0.4, 0, 0.7, 0.9, 1.2, h), P(0, 0.7, 0, 0.12, 3.2, 0.12, C.wood), P(0, 1.6, 0, 0.12, 1.8, 2.6, sail)];
    for (let i = -3; i <= 3; i++) parts.push(P(i * 0.9, 0.3, 1.2, 0.08, 0.06, 1.0, C.wood, 0), P(i * 0.9, 0.3, -1.2, 0.08, 0.06, 1.0, C.wood, 0));
    return { kind: 'veh', mode: 'water', w: 8.6, d: 3.2, h: 3.6, parts };
  },
  horse(E, faction) {
    const coat = E.pick([[120, 84, 54], [80, 58, 40], [160, 140, 110], [60, 50, 44], [200, 190, 170]]), F = FACTIONS[faction] || FACTIONS.roman;
    return { kind: 'veh', w: 2.4, d: 0.8, h: 2.6, parts: [P(0, 0.9, 0, 1.5, 0.6, 0.55, coat), P(0.9, 1.3, 0, 0.35, 0.6, 0.3, coat), P(1.15, 1.7, 0, 0.5, 0.3, 0.28, coat),
      P(0.55, 0, 0.18, 0.14, 0.9, 0.14, coat), P(0.55, 0, -0.18, 0.14, 0.9, 0.14, coat), P(-0.55, 0, 0.18, 0.14, 0.9, 0.14, coat), P(-0.55, 0, -0.18, 0.14, 0.9, 0.14, coat), P(-0.85, 1.0, 0, 0.3, 0.6, 0.12, mul(coat, 0.7)),
      P(-0.05, 1.5, 0, 0.34, 0.66, 0.5, F.shirt), P(-0.05, 2.16, 0, 0.32, 0.32, 0.32, [214, 168, 124]), P(-0.05, 2.44, 0, 0.36, 0.16, 0.36, F.hatC), P(0.4, 1.9, -0.32, 0.08, 1.6, 0.08, [112, 84, 52])] };
  },
  elephant(E) {
    const g = [128, 124, 120];
    return { kind: 'veh', w: 3.6, d: 1.6, h: 3.4, parts: [P(0, 1.1, 0, 2.6, 1.5, 1.5, g), P(1.5, 1.6, 0, 0.8, 0.9, 1.0, g), P(1.95, 0.6, 0, 0.3, 1.2, 0.3, g), P(1.8, 1.8, 0.62, 0.4, 0.8, 0.12, mul(g, 0.9)), P(1.8, 1.8, -0.62, 0.4, 0.8, 0.12, mul(g, 0.9)),
      P(0.85, 0, 0.45, 0.4, 1.1, 0.4, g), P(0.85, 0, -0.45, 0.4, 1.1, 0.4, g), P(-0.85, 0, 0.45, 0.4, 1.1, 0.4, g), P(-0.85, 0, -0.45, 0.4, 1.1, 0.4, g), P(-0.1, 2.6, 0, 1.2, 0.6, 1.0, [150, 110, 60]), P(2.2, 1.0, 0.3, 0.6, 0.08, 0.08, [236, 232, 220]), P(2.2, 1.0, -0.3, 0.6, 0.08, 0.08, [236, 232, 220])] };
  },
  palisade(E, rad = 1.5) {
    const parts = [], k = Math.max(8, Math.round(rad * 8));
    for (let i = 0; i < k; i++) { const a = (i / k) * PI * 2; parts.push(P(Math.cos(a) * rad, 0, Math.sin(a) * rad, 0.22, E.rr(1.1, 1.5), 0.22, E.vary(C.wood, 0.1))); }
    return { w: rad * 2 + 1, d: rad * 2 + 1, h: 1.5, parts, noShadow: true };
  },
});
const MODERN = { tank: 'catapult', apc: 'catapult', howitzer: 'catapult', truck: 'oxcart', jeep: 'oxcart', bicycle: 'oxcart', helicopter: 'oxcart', jet: 'oxcart', cargoPlane: 'oxcart',
  parachuteGround: 'oxcart', landingCraft: 'galley', patrolBoat: 'galley', ship: 'galley', bunker: 'tent', revetment: 'palisade', sandbagRing: 'palisade', fuelTank: 'groundHut', hangar: 'groundHut', tower: 'watchtower' };
for (const [name, alt] of Object.entries(MODERN)) { const f = D[name]; D[name] = (E, ...a) => (E.ancient ? D[alt](E, ...(alt === 'palisade' ? a : [])) : f(E, ...a)); }
{ const f = D.tent; D.tent = (E) => { const d = f(E); if (!E.ancient) return d; const c = E.pick([[210, 196, 160], [180, 160, 120], [196, 180, 140]]); return { ...d, parts: d.parts.map((p) => [...p.slice(0, 6), c, p[7]]) }; }; }
{ const f = D.building; D.building = (E, o = {}) => (E.ancient ? f(E, { ...o, floors: Math.min(o.floors || 2, 3), roof: true, c: o.c || E.vary(E.pick([[222, 206, 170], [206, 178, 136], [230, 220, 196], [196, 160, 120]]), 0.06) }) : f(E, o)); }

// Human scale: a person is 2 units tall, so most things were redrawn bigger. scaleDef grows a whole definition about its centre.
function scaleDef(def, k) {
  const out = { ...def, w: def.w * k, d: def.d * k, h: def.h * k, parts: def.parts.map((p) => [p[0] * k, p[1] * k, p[2] * k, p[3] * k, p[4] * k, p[5] * k, p[6], p[7]]) };
  if (def.rotorY) { out.rotorY = def.rotorY * k; out.rotorLen = def.rotorLen * k; }
  return out;
}
const SCALE = { oxcart: 1.6, catapult: 1.7, galley: 1.3, horse: 1.15, elephant: 1.3, palisade: 1.4, stiltHut: 1.5, groundHut: 1.6, villa: 1.15, tent: 1.5, watchtower: 1.4, bunker: 1.5, revetment: 1.3, sandbagRing: 1.4, supply: 1.5, fuelTank: 1.4,
  market: 1.25, hangar: 1.5, tank: 1.8, apc: 1.8, truck: 1.7, jeep: 1.9, howitzer: 1.7, helicopter: 1.7, jet: 1.4, cargoPlane: 1.2, landingCraft: 1.6, patrolBoat: 1.5, sampan: 1.4, ship: 1.2, bicycle: 1.6 };
for (const [name, k] of Object.entries(SCALE)) { const f = D[name]; D[name] = (...a) => scaleDef(f(...a), k); }

// people ---------------------------------------------------------------------------------------------------------------
const toBoxParts = (parts) => parts.map((p) => [p.x, p.y, p.z, p.sx, p.sy, p.sz, p.c, p.rot || 0]);
const standOK = (E, x, z) => { if (x < 1 || z < 1 || x > E.n - 1 || z > E.n - 1) return null; const g = E.G(x, z); return g.water !== 0 || E.relief(x, z, 0.6) > 2 ? null : g; };
/** One humanoid at world x,z facing th (no occupancy test). Returns { x, y, z, top } or null off land / on steep ground. */
function person(E, x, z, th, kind, faction, o = {}) {
  const g = standOK(E, x, z); if (!g) return null;
  const parts = figure(kind, { faction, pose: o.pose, seed: Math.floor(E.r() * 1e9), phase: o.phase, rifle: o.rifle });
  E.compose(toBoxParts(parts), x, z, g.y, th);
  return { x, y: g.y, z, top: g.y + figureHeight(parts) };
}
const mixPose = (E, w) => { let q = E.r(), tot = 0; for (const k in w) tot += w[k]; q *= tot; for (const k in w) { q -= w[k]; if (q <= 0) return k; } return 'standing'; };
/** Scale a count tuned for n = 144 to this set's area. */
const KA = (E, a, b) => Math.max(1, Math.round(E.ri(a, b) * E.kA));
/** A formation of people centred on layout coords (cu, cv). o: { faction, th (layout angle), poses {name: weight}, officers (0..1),
 *  kind, spacing, radius, maxLine, abreast, out, face }. Returns the people placed. */
function group(E, cu, cv, type, count, o = {}) {
  if (count <= 0) return [];
  const [cx, cz] = E.toW(cu, cv);
  const pts = formation(type, count, { cx, cz, th: E.A + (o.th ?? 0), spacing: o.spacing, radius: o.radius, maxLine: o.maxLine, abreast: o.abreast, out: o.out, face: o.face }, E.r);
  const free = pts.map((p) => standOK(E, p.x, p.z) && E.isFree(p.x, p.z, 0.75));
  const placed = [];
  pts.forEach((p, i) => {
    if (!free[i] || E.boxes.length >= MAX_BOXES - 20) return;
    const kind = o.kind ?? (o.officers && E.chance(o.officers) ? 'officer' : 'soldier');
    const pl = person(E, p.x, p.z, p.th, kind, o.faction, { pose: o.poses ? mixPose(E, o.poses) : 'standing' });
    if (pl) placed.push(pl);
  });
  for (const p of placed) E.take(p.x, p.z, 0.5);
  return placed;
}
const MODERN_ARMY = new Set(['us_marine', 'us_army', 'arvn', 'pavn', 'viet_cong', 'french', 'pla']);
const soldierFactions = (E) => (Array.isArray(E.ctx.factions) ? E.ctx.factions : []).filter((f) => f && f !== 'civilian' && f !== 'sailor');
/** The set's i-th side; a civilian-only list never stands in for an army; before firearms a modern default becomes Roman. */
const fac = (E, i, def) => soldierFactions(E)[i] || (E.ancient && MODERN_ARMY.has(def) ? (E.ctx.sides?.[i] || 'roman') : def);
const SIDE_HINTS = [
  [/carthag|hannibal|cannae|zama|punic|trebia|trasimene|scipio/i, ['roman', 'carthaginian']],
  [/constantinople|ottoman|mehmed|byzant|1453/i, ['byzantine', 'ottoman']],
  [/gaul|alesia|vercinget|celt|brennus|allia/i, ['roman', 'gaul']],
  [/pyrrh|greek|macedon|hoplite|sparta|athen/i, ['roman', 'greek']],
  [/german|teutoburg|goth|vandal|visigoth|odoacer|adrianople|hun|barbarian|frank/i, ['roman', 'germanic']],
];
/** The two armies a battle before firearms most likely shows, from the beat's place and narration. */
export function sidesFromText(text) { for (const [re, sides] of SIDE_HINTS) if (re.test(text || '')) return sides; return null; }
/** Ancient when the story says so (ctx.era) or any faction asked for is from before firearms. */
export function isAncient(ctx) { return ctx?.era === 'ancient' || (Array.isArray(ctx?.factions) && ctx.factions.some((f) => FACTIONS[f]?.ancient)); }
/** The two sides of a battle: ctx.factions when given, else a plausible pair. */
function battleSides(E) {
  const f = soldierFactions(E).length ? soldierFactions(E) : (E.ctx.sides || []);
  const pairs = E.ancient ? [['roman', 'carthaginian'], ['roman', 'gaul'], ['roman', 'germanic']] : [['french', 'pavn'], ['us_army', 'pavn'], ['us_marine', 'viet_cong'], ['arvn', 'viet_cong']];
  const d = E.pick(pairs);
  return [f[0] || d[0], f[1] || (f[0] && f[0] === d[1] ? d[0] : d[1])];
}
/** Arc-length parameterised polyline of world points; extends straight beyond both ends. */
function polylineAt(pts) {
  const cum = [0]; for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const L = cum[cum.length - 1];
  const at = (t) => {
    let i = 0; if (t > 0) { i = cum.findIndex((c) => c >= t) - 1; if (i < 0) i = pts.length - 2; }
    i = Math.max(0, Math.min(pts.length - 2, i));
    const a = pts[i], b = pts[i + 1], seg = Math.max(1e-6, cum[i + 1] - cum[i]), f = (t - cum[i]) / seg;
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
  };
  return { at, L };
}
/** A walking column along a straight line through layout point (cu, cv) at layout angle `ang`, entering and leaving off the set
 *  edge. Queued on E.marches (added to the emitters last, within the particle budget). Returns true when a land path was found. */
function marchRoute(E, cu, cv, ang, count, faction, o = {}) {
  const [cx, cz] = E.toW(cu, cv), th = E.A + ang, dx = Math.cos(th), dz = -Math.sin(th);
  // the chord through the set, plus a run-up beyond each edge
  const edge = (sgn) => { let d = 0; while (d < E.n * 2 && cx + dx * (d * sgn) > -0.001 && cx + dx * (d * sgn) < E.n && cz + dz * (d * sgn) > -0.001 && cz + dz * (d * sgn) < E.n) d += 1; return d; };
  const back = edge(-1) + 10, fwd = edge(1) + 10;
  return marchPath(E, (t) => [cx + dx * t, cz + dz * t], -back, fwd, count, faction, o);
}
function marchPath(E, at, t0, t1, count, faction, o = {}) {
  const step = 1.5, path = [], cum = [];
  let ok = true, last = null, s = 0; const ins = [];
  for (let t = t0; t <= t1 + 1e-6; t += step) {
    const [x, z] = at(t), inside = x > 1 && z > 1 && x < E.n - 1 && z < E.n - 1;
    let g;
    try { g = E.G(inside ? x : Math.max(1, Math.min(E.n - 1, x)), inside ? z : Math.max(1, Math.min(E.n - 1, z))); } catch { g = { y: 0, water: 0 }; }
    if (inside && (g.water !== 0 || E.relief(x, z, 0.6) > 2)) { ok = false; break; }
    if (last) s += Math.hypot(x - last[0], z - last[2]);
    last = [x, g.y, z]; path.push(last); cum.push(s); ins.push(inside);
  }
  if (!ok) return false;
  // keep the part inside the set plus a short run-up beyond each edge (columns enter and leave off the edge)
  const i0 = ins.indexOf(true), i1 = ins.lastIndexOf(true);
  if (i0 < 0 || i1 - i0 < 6) return false;
  const a0 = Math.max(0, i0 - 7), a1 = Math.min(path.length - 1, i1 + 7), base = cum[a0];
  path.splice(a1 + 1); path.splice(0, a0); cum.splice(a1 + 1); cum.splice(0, a0); for (let i = 0; i < cum.length; i++) cum[i] -= base;
  if (path.length < 8) return false;
  const spacing = o.spacing ?? 2.2, L = cum[cum.length - 1];
  const n = Math.max(1, Math.min(o.max ?? 10, count, Math.floor((L - 16) / spacing)));
  const kinds = []; for (let i = 0; i < n; i++) kinds.push(i === 0 && o.officer ? 'officer' : 'soldier');
  E.marches.push({ kind: 'march', path, cum, step, L, count: n, spacing, speed: o.speed ?? E.rr(1.1, 1.6), s0: E.r() * L, faction, kinds, seed: Math.floor(E.r() * 1e9), ramp: 4 });
  return true;
}

// trees ----------------------------------------------------------------------------------------------------------------
function tree(E, x, z, kind, s = 1) {
  s *= 1.35;   // human scale: a person is 2 units, so trees stand taller too
  const g = E.G(x, z);
  if (g.water !== 0 && !(g.water === 2 && kind === 'palm')) return false;
  if (E.relief(x, z, 0.6) > 3) return false;
  const rad = kind === 'emerg' ? 1.3 * s : kind === 'shrub' ? 0.5 * s : 0.7 * s;
  if (!E.isFree(x, z, rad * 0.7)) return false;
  E.take(x, z, rad * 0.7);
  const y = g.y, r = E.r, leaf = E.vary(E.pick([C.leaf, [58, 112, 46], [42, 88, 40], [70, 120, 52]]), 0.12);
  const trunk = E.vary([96, 70, 44], 0.15);
  if (kind === 'palm') {
    const h = 2.6 * s, ph = r() * PI;
    E.box(x, z, y, 0.22 * s, h, 0.22 * s, trunk);
    for (let k = 0; k < 3; k++) E.box(x, z, y + h, 1.9 * s, 0.1, 0.34 * s, leaf, ph + (k * PI) / 3 * (k === 2 ? 1.5 : 1));
    E.box(x, z, y + h - 0.2, 0.4 * s, 0.35, 0.4 * s, [90, 66, 40]);
  } else if (kind === 'broad') {
    const h = 1.3 * s;
    E.box(x, z, y, 0.32 * s, h, 0.32 * s, trunk);
    E.box(x, z, y + h - 0.2, 2.5 * s, 0.9 * s, 2.5 * s, leaf, r() * PI);
    E.box(x, z, y + h + 0.6 * s, 1.7 * s, 0.8 * s, 1.7 * s, mul(leaf, 1.1), r() * PI);
  } else if (kind === 'emerg') {
    const h = 3.6 * s;
    E.box(x, z, y, 0.5 * s, h, 0.5 * s, trunk);
    E.box(x, z, y + h - 0.4, 3.6 * s, 1.2 * s, 3.6 * s, mul(leaf, 0.9), r() * PI);
    E.box(x, z, y + h + 0.7 * s, 2.4 * s, 1.0 * s, 2.4 * s, leaf, r() * PI);
    E.box(x, z, y + h + 1.5 * s, 1.2 * s, 0.7 * s, 1.2 * s, mul(leaf, 1.12), r() * PI);
  } else if (kind === 'bamboo') {
    const col = E.vary([112, 150, 70], 0.12);
    for (let i = 0; i < 5; i++) E.box(x + (r() - 0.5) * 0.9 * s, z + (r() - 0.5) * 0.9 * s, y, 0.12, (2.2 + r() * 1.4) * s, 0.12, col);
    E.box(x, z, y + 2.6 * s, 1.3 * s, 0.5 * s, 1.3 * s, mul(col, 0.9), r() * PI);
  } else if (kind === 'dead') {
    E.box(x, z, y, 0.28 * s, 1.5 * s, 0.28 * s, [52, 42, 36]);
    E.box(x, z, y + 1.0 * s, 0.9 * s, 0.1, 0.1, [52, 42, 36], r() * PI);
  } else { // shrub
    E.box(x, z, y, 1.1 * s, 0.5 * s, 1.1 * s, mul(leaf, 0.9), r() * PI);
    E.box(x, z, y + 0.45 * s, 0.7 * s, 0.4 * s, 0.7 * s, leaf, r() * PI);
  }
  return true;
}
// scatter trees over the whole set; denser where ctx says forest
function scatterTrees(E, attempts, mix, dens, o = {}) {
  const kinds = Object.keys(mix), tot = kinds.reduce((a, k) => a + mix[k], 0);
  for (let i = 0; i < attempts && !E.full(); i++) {
    const x = 1 + E.r() * (E.n - 2), z = 1 + E.r() * (E.n - 2);
    if (o.avoid && o.avoid(x, z)) continue;
    const g = E.G(x, z);
    if (!(g.forest ? E.r() < Math.min(1, dens * 2.2 + 0.25) : E.r() < dens)) continue;
    let q = E.r() * tot, kind = kinds[0];
    for (const k of kinds) { q -= mix[k]; if (q <= 0) { kind = k; break; } }
    tree(E, x, z, kind, (o.size ?? 1) * E.rr(0.7, 1.35));
  }
}

// features -------------------------------------------------------------------------------------------------------------
function crater(E, x, z, rad) {
  const g = E.G(x, z); if (g.water !== 0 || E.relief(x, z, rad) > 2.5) return false;
  E.take(x, z, rad * 0.6);
  E.box(x, z, g.y + 0.02, rad * 1.4, 0.05, rad * 1.4, E.vary(C.crater, 0.1), E.r() * PI);
  E.box(x, z, g.y + 0.05, rad * 0.8, 0.05, rad * 0.8, mul(C.crater, 0.6), E.r() * PI);
  for (let i = 0; i < 6; i++) { const a = (i / 6) * PI * 2 + E.r() * 0.4, rx = x + Math.cos(a) * rad * 0.85, rz = z + Math.sin(a) * rad * 0.85; const gg = E.G(rx, rz); if (gg.water === 0 && E.relief(rx, rz, 0.6) <= 3) E.box(rx, rz, gg.y, rad * 0.5, 0.22, rad * 0.35, E.vary(C.mud, 0.1), -a); }
  return true;
}
function zigzagTrench(E, u0, u1, v, amp, step, o = {}) {
  // trench polyline along local u at depth v with zigzag; floor dark, parapet both sides
  const pts = []; let flip = 1;
  for (let u = u0; u <= u1 + 0.01; u += step) { pts.push([u, v + flip * amp]); flip = -flip; }
  for (let i = 0; i + 1 < pts.length; i++) {
    const [a, b] = [pts[i], pts[i + 1]], dx = b[0] - a[0], dv = b[1] - a[1], L = Math.hypot(dx, dv), nx = -dv / L, nv = dx / L;
    E.segL(a[0], a[1], b[0], b[1], 0.9, 0.06, [40, 30, 24], { lift: 0.04 });
    E.segL(a[0] + nx * 0.8, a[1] + nv * 0.8, b[0] + nx * 0.8, b[1] + nv * 0.8, 0.6, 0.4, E.pick([C.khaki, C.sandbag]), { jit: 0.08 });
    E.segL(a[0] - nx * 0.8, a[1] - nv * 0.8, b[0] - nx * 0.8, b[1] - nv * 0.8, 0.6, 0.32, C.mud, { jit: 0.08 });
    for (const q of [a, b]) { const [wx, wz] = E.toW(q[0], q[1]); E.take(wx, wz, 0.9); }
  }
  return pts;
}
function wireLine(E, u0, u1, v, o = {}) {
  const jag = o.jag ?? 0.5;
  let prev = null;
  for (let u = u0; u <= u1 + 0.01; u += 2.4) {
    const vv = v + (E.r() - 0.5) * jag * 2, [x, z] = E.toW(u, vv), g = E.G(x, z);
    if (g.water === 0 && E.relief(x, z, 0.6) <= 3) { E.box(x, z, g.y, 0.1, 0.7, 0.1, C.wire); E.box(x, z, g.y + 0.4, 0.14, 0.07, 0.4, C.wire, E.r() * PI); }
    if (prev) E.segL(prev[0], prev[1], u, vv, 0.06, 0.07, C.wire, { lift: 0.4, step: 2.6 });
    prev = [u, vv];
  }
}
function ringTrench(E, cu, cv, rad, sides = 10) {
  for (let i = 0; i < sides; i++) {
    const a1 = (i / sides) * PI * 2, a2 = ((i + 1) / sides) * PI * 2;
    E.segL(cu + Math.cos(a1) * rad, cv + Math.sin(a1) * rad, cu + Math.cos(a2) * rad, cv + Math.sin(a2) * rad, 0.8, 0.07, [40, 30, 24], { lift: 0.04 });
    E.segL(cu + Math.cos(a1) * (rad + 0.7), cv + Math.sin(a1) * (rad + 0.7), cu + Math.cos(a2) * (rad + 0.7), cv + Math.sin(a2) * (rad + 0.7), 0.6, 0.38, C.sandbag, { jit: 0.1 });
  }
}
function paddyPlot(E, x, z, w, d, th) {
  const f = E.fp(x, z, w, d, th, { slope: 1.2, free: 0.8 });
  if (!f) return false;
  E.take(x, z, f.rad);
  const wet = E.chance(0.5);
  const col = wet ? E.vary([88, 138, 120], 0.1) : E.vary(E.pick([[110, 160, 70], [140, 170, 70], [92, 142, 62]]), 0.1);
  E.box(x, z, f.hi - 0.03, w - 0.5, 0.06, d - 0.5, col, th);
  const c = Math.cos(th), s = Math.sin(th), dk = [118, 100, 66];
  for (const [dx, dz, sx, sz] of [[0, d / 2, w, 0.35], [0, -d / 2, w, 0.35], [w / 2, 0, 0.35, d], [-w / 2, 0, 0.35, d]]) E.box(x + dx * c + dz * s, z - dx * s + dz * c, f.hi - 0.02, sx, 0.2, sz, E.vary(dk, 0.08), th);
  if (!wet) for (let i = -1; i <= 1; i++) E.box(x + i * 1.2 * s, z + i * 1.2 * c, f.hi, w - 1.2, 0.18, 0.5, mul(col, 0.8), th);
  return true;
}
function pathLine(E, pts, wd, c, o = {}) {
  for (let i = 0; i + 1 < pts.length; i++) E.seg(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], wd, o.h ?? 0.08, c, { jit: 0.08, lift: o.lift ?? 0.02, slope: o.slope ?? 3, step: o.step ?? 2.6 });
}
function smoke(E, x, z, rate = 0.8, extra = {}) { const g = E.G(x, z); E.emitters.push({ kind: 'smoke', x, y: g.y + 0.6, z, rate, ...extra }); }

// a helicopter: parked (static boxes + spinning rotor) or landing loop (animated)
function heliStatic(E, x, z, th, col) {
  const def = D.helicopter(E, col), p = E.put(def, x, z, th);
  if (p) E.emitters.push({ kind: 'rotor', x: p.x, y: p.y + def.rotorY, z: p.z, len: def.rotorLen, speed: E.rr(14, 22), rot0: E.r() * PI });
  return p;
}
function heliLanding(E, x, z, th, col, alt, period, phase) {
  const def = D.helicopter(E, col), f = E.fp(x, z, def.w, def.d, th, { slope: 1.2 });
  if (!f) return false;
  E.take(x, z, f.rad);
  E.emitters.push({ kind: 'flyer', mode: 'land', x, z, y: (f.lo + f.hi) / 2, th, parts: def.parts, rotorY: def.rotorY, rotorLen: def.rotorLen, alt, period, phase, speed: E.rr(18, 24), drift: E.rr(-4, 4) });
  return true;
}

// ---------------------------------------------------------------------------------------------------------------------
// Recipes
// ---------------------------------------------------------------------------------------------------------------------
const BUILD = {
  village(E) {
    const { r, n } = E, R = n * 0.34, wet = E.hasWater();
    const stiltBias = wet ? 0.9 : E.rr(0.15, 0.5), count = E.ri(14, 30);
    const cu = E.rr(-R * 0.3, R * 0.3), cv = E.rr(-R * 0.3, R * 0.3), houses = [];
    // houses cluster; with water, they hug the water edge
    for (let i = 0; i < 900 && houses.length < count; i++) {
      const a = r() * PI * 2, d = 4 + Math.sqrt(r()) * R * 0.85, u = cu + Math.cos(a) * d, v = cv + Math.sin(a) * d;
      const [x, z] = E.toW(u, v), wd = E.wd(x, z);
      if (wet && wd > 20 && !E.chance(0.12)) continue;
      if (wet && wd < 2.5) continue;
      const stilt = wet ? (wd < 12 ? E.chance(stiltBias) : E.chance(0.15)) : E.chance(stiltBias);
      const def = stilt ? D.stiltHut(E) : D.groundHut(E);
      const p = E.put(def, x, z, E.A + E.pick([0, PI / 2, PI, -PI / 2]) + E.rr(-0.25, 0.25));
      if (p) houses.push(p);
    }
    // a communal building and a granary or two
    for (let i = 0; i < 2; i++) { const [x, z] = E.toW(cu + E.rr(-6, 6), cv + E.rr(-6, 6)); E.put(D.building(E, { floors: 1, w: 6, d: 4 }), x, z, E.A); }
    // rice paddies on flat lowland near water
    const pw = E.rr(7, 10), pd = E.rr(5, 7), pstep = E.chance(0.5) ? 1.15 : 1.3;
    for (let u = -R; u <= R && !E.full(); u += pw * pstep) for (let v = -R; v <= R; v += pd * pstep) {
      const [x, z] = E.toW(u + E.rr(-1, 1), v + E.rr(-1, 1));
      const near = wet ? E.wd(x, z) < 34 : true;
      if (!near || E.relief(x, z, 4) >= 3 || !E.isFree(x, z, 3)) continue;
      paddyPlot(E, x, z, pw, pd, E.A + (E.chance(0.1) ? 0.12 : 0));
    }
    // palms, bamboo, shrubs
    for (let i = 0; i < 400 && !E.full(); i++) {
      const h = houses.length ? E.pick(houses) : { x: n / 2, z: n / 2 };
      const x = h.x + E.rr(-9, 9), z = h.z + E.rr(-9, 9);
      tree(E, x, z, E.chance(0.55) ? 'palm' : E.chance(0.4) ? 'bamboo' : 'broad', E.rr(0.8, 1.3));
      if (i > 120) break;
    }
    scatterTrees(E, 700, { palm: 3, broad: 3, bamboo: 1, shrub: 2 }, E.rr(0.1, 0.22));
    if (wet) for (let i = 0; i < 300 && E.emitters.length < 3 + 0; i++) { /* boats below */ break; }
    if (wet) { let b = 0; for (let i = 0; i < 400 && b < E.ri(4, 10); i++) { const x = r() * n, z = r() * n; if (E.ld(x, z) < 12 && E.ld(x, z) > 1 && E.put(D.sampan(E), x, z, r() * PI * 2)) b++; } }
    for (let i = 0; i < Math.min(3, houses.length); i++) smoke(E, houses[i].x, houses[i].z, 0.5, { c: [150, 146, 140], big: 0.6 });
    // villagers about the houses; a patrol column when the story names a faction
    E.focus = E.toW(cu, cv);
    for (let i = 0; i < 3; i++) group(E, cu + E.rr(-R * 0.4, R * 0.4), cv + E.rr(-R * 0.4, R * 0.4), 'crowd', KA(E, 4, 9), { faction: 'civilian', kind: 'civilian', face: 'random' });
    if (E.ctx.factions && E.ctx.factions[0]) marchRoute(E, cu, cv + E.rr(-6, 6), E.rr(-0.3, 0.3), KA(E, 5, 8), E.ctx.factions[0], { officer: true });
  },

  city(E) {
    const { r, n } = E, R = n * 0.36, bs = E.rr(12, 16), st = 3.2, cell = bs + st;
    const cu = E.rr(-3, 3), cv = E.rr(-3, 3), road = E.pick([[112, 108, 100], [100, 100, 98], [124, 116, 104]]);
    const nb = Math.floor(R * 2 / cell);
    const bx = (i) => -R + (i + 0.5) * cell + cu, bz = (j) => -R + (j + 0.5) * cell + cv;
    // streets
    for (let i = 0; i <= nb; i++) { const u = -R + i * cell + cu - cell / 2 + (cell - bs) / 2 - st / 2 + st / 2; E.segL(u, -R - cell / 2, u, R + cell / 2, st, 0.08, road, { lift: 0.0, step: 3.5, slope: 3 }); E.segL(u + cell / 2, -R, u + cell / 2, R, 0.1, 0.1, [200, 190, 150], { lift: 0.06, step: 6, noocc: true }); }
    for (let j = 0; j <= nb; j++) { const v = -R + j * cell + cv - cell / 2 + (cell - bs) / 2 - st / 2 + st / 2; E.segL(-R - cell / 2, v, R + cell / 2, v, st, 0.08, road, { lift: 0.0, step: 3.5, slope: 3 }); }
    const marketAt = [E.ri(1, nb - 1), E.ri(1, nb - 1)], parkAt = [E.ri(0, nb), E.ri(0, nb)], villaZone = E.rr(0.55, 0.8);
    for (let i = 0; i < nb && !E.full(); i++) for (let j = 0; j < nb; j++) {
      const u = bx(i), v = bz(j), dist = Math.hypot(u - cu, v - cv) / R;
      if (i === marketAt[0] && j === marketAt[1]) { E.putL(D.market(E), u, v, 0, {}); continue; }
      if (i === parkAt[0] && j === parkAt[1]) { for (let k = 0; k < 14; k++) { const [x, z] = E.toW(u + E.rr(-bs / 2, bs / 2), v + E.rr(-bs / 2, bs / 2)); tree(E, x, z, E.pick(['broad', 'palm', 'broad']), E.rr(0.9, 1.4)); } continue; }
      if (dist > villaZone && E.chance(0.6)) { E.putL(D.villa(E), u, v, E.pick([0, PI / 2, PI, -PI / 2]), {}); continue; }
      // 2x2 lots
      const ls = bs / 2 - 0.4;
      for (const [a, b] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
        if (E.chance(0.1)) { const [x, z] = E.toW(u + a * ls / 2, v + b * ls / 2); tree(E, x, z, 'broad', 1.1); continue; }
        const tall = E.chance(Math.max(0.05, 0.6 - dist)), floors = tall ? E.ri(3, 7) : E.ri(1, 3);
        E.putL(D.building(E, { w: E.rr(ls * 0.65, ls * 0.97), d: E.rr(ls * 0.65, ls * 0.97), floors, roof: !tall }), u + a * ls / 2 + a * 0.1, v + b * ls / 2 + b * 0.1, E.pick([0, 0, PI / 2]) * 0, {});
      }
    }
    // vehicles on streets, trees along them
    for (let k = 0; k < E.ri(10, 22); k++) {
      const i = E.ri(0, nb), along = E.rr(-R, R), horiz = E.chance(0.5), line = -R + i * cell + (horiz ? cv : cu) - cell / 2 + (cell - bs) / 2;
      const def = E.pick([D.jeep, D.truck, D.jeep, D.apc])(E), hd = horiz ? 0 : PI / 2;
      horiz ? E.putL(def, along, line + E.pick([-0.6, 0.6]), E.chance(0.5) ? hd : hd + PI, { noocc: false }) : E.putL(def, line + E.pick([-0.6, 0.6]), along, E.chance(0.5) ? hd : hd + PI, {});
    }
    scatterTrees(E, 160, { broad: 3, palm: 2, shrub: 1 }, 0.35, { size: 0.9 });
    // crowds at the market and on the streets, a parade block and a marching column
    E.focus = E.toW(bx(marketAt[0]), bz(marketAt[1]));
    group(E, bx(marketAt[0]), bz(marketAt[1]), 'crowd', KA(E, 20, 34), { faction: 'civilian', kind: 'civilian', face: 'random' });
    for (let k = 0; k < 6; k++) group(E, E.rr(-R, R), -R + E.ri(0, nb) * cell + cv - cell / 2 + (cell - bs) / 2, 'crowd', KA(E, 4, 9), { faction: 'civilian', kind: 'civilian', face: 'random', radius: 2.5 });
    group(E, bx(parkAt[0]), bz(parkAt[1]), 'ranks', KA(E, 24, 40), { faction: fac(E, 0, 'arvn'), officers: 0.05, th: 0 });
    marchRoute(E, cu, -R + E.ri(1, Math.max(1, nb - 1)) * cell + cv, 0, KA(E, 6, 10), fac(E, 0, 'arvn'), { officer: true });
  },

  airfield(E) {
    const { r, n } = E;
    // runway along the flattest axis
    let best = [];
    for (let k = 0; k < 12; k++) {
      const a = (k / 12) * PI, c = Math.cos(a), s = Math.sin(a); let lo = 1e9, hi = -1e9;
      for (let t = -45; t <= 45; t += 6) { const g = E.G(n / 2 + c * t, n / 2 - s * t); if (g.water !== 0) { hi = 1e9; } if (g.y < lo) lo = g.y; if (g.y > hi) hi = g.y; }
      best.push({ a, relief: hi - lo });
    }
    const min = Math.min(...best.map((b) => b.relief)), cand = best.filter((b) => b.relief <= min + 0.5);
    E.A = E.pick(cand).a + E.rr(-0.04, 0.04);
    const len = E.rr(84, 100), rw = E.rr(5, 7);
    // runway
    E.segL(-len / 2, 0, len / 2, 0, rw, 0.1, [96, 98, 100], { step: 6, slope: 3, lift: 0.0 });
    for (let u = -len / 2 + 6; u < len / 2 - 5; u += 6) E.segL(u, 0, u + 2.8, 0, 0.3, 0.06, C.white, { lift: 0.09, noocc: true, step: 3 });
    for (let k = -2; k <= 2; k++) { E.segL(-len / 2 + 1, k * 0.8, -len / 2 + 3.2, k * 0.8, 0.3, 0.06, C.white, { lift: 0.09 }); E.segL(len / 2 - 3.2, k * 0.8, len / 2 - 1, k * 0.8, 0.3, 0.06, C.white, { lift: 0.09 }); }
    // taxiway + apron
    const side = E.pick([-1, 1]), off = rw / 2 + E.rr(9, 12) , tw = 3.2;
    E.segL(-len / 2 + 4, side * off, len / 2 - 4, side * off, tw, 0.09, [112, 114, 114], { step: 6, slope: 3 });
    for (let u = -len / 2 + 14; u < len / 2 - 12; u += 22) E.segL(u, side * (rw / 2 + 1), u, side * (off - tw / 2), 2.6, 0.09, [112, 114, 114], { step: 3, slope: 3 });
    const apronV = side * (off + 6.5);
    E.segL(-len * 0.34, apronV, len * 0.34, apronV, 9, 0.09, [118, 118, 114], { step: 6, slope: 3 });
    // hangars / revetments behind the apron
    const nh = E.ri(3, 6), hv = side * (off + 15);
    for (let i = 0; i < nh; i++) {
      const u = -len * 0.34 + (i + 0.5) * (len * 0.68 / nh);
      E.chance(0.6) ? E.putL(D.hangar(E), u, hv, side > 0 ? -PI / 2 : PI / 2, {}) : E.putL(D.revetment(E), u, hv - side * 1, side > 0 ? PI / 2 : -PI / 2 * 1, {});
    }
    // parked aircraft on the apron
    const npj = E.ri(4, 9);
    for (let i = 0; i < npj; i++) { const u = -len * 0.34 + (i + 0.5) * (len * 0.68 / npj), v = apronV + E.rr(-1, 1); E.chance(0.25) ? E.putL(D.cargoPlane(E), u, v, side > 0 ? PI / 2 : -PI / 2, {}) : E.putL(D.jet(E), u, v, side > 0 ? PI / 2 : -PI / 2, {}); }
    // revetted jets on the other side
    for (let i = 0; i < E.ri(2, 5); i++) { const u = E.rr(-len * 0.4, len * 0.4), v = -side * (rw / 2 + E.rr(8, 12)); E.putL(D.revetment(E), u, v, side > 0 ? -PI / 2 : PI / 2, {}); E.putL(D.jet(E), u - side * 0.1, v + 0.1, side > 0 ? -PI / 2 : PI / 2, { noocc: true }); }
    // tower, fuel, tents, helicopters, vehicles
    E.putL(D.tower(E), E.rr(-10, 10), side * (off + 28), E.rr(-0.3, 0.3), {});
    for (let i = 0; i < E.ri(2, 5); i++) E.putL(D.fuelTank(E), -len * 0.3 + i * 4, side * (off + 24), 0, {});
    for (let i = 0; i < E.ri(3, 7); i++) E.putL(D.tent(E), E.rr(len * 0.1, len * 0.4), side * (off + E.rr(22, 32)), E.rr(-0.2, 0.2), {});
    for (let i = 0; i < E.ri(1, 4); i++) { const [x, z] = E.toW(E.rr(-len * 0.3, len * 0.3), -side * E.rr(rw / 2 + 16, rw / 2 + 24)); heliStatic(E, x, z, E.A + E.rr(0, PI * 2)); }
    for (let i = 0; i < E.ri(5, 10); i++) E.putL(E.pick([D.jeep, D.truck, D.jeep])(E), E.rr(-len * 0.4, len * 0.4), side * (off + E.rr(3, 5)) + (E.chance(0.5) ? 0 : 10), E.chance(0.5) ? 0 : PI, {});
    // jet flyby
    const th = E.A, [x0, z0] = E.toW(-len * 0.5 - 6, E.rr(-1, 1));
    E.emitters.push({ kind: 'flyer', mode: 'flyby', x: x0, z: z0, y: (E.G(x0, z0).y || 0) + 3, th: E.A, dx: Math.cos(E.A), dz: -Math.sin(E.A), speed: 9, period: E.rr(12, 18), phase: E.rr(0, 12), parts: D.jet(E).parts });
    // ground crew and pilots on the apron, officers in a line by the tower
    E.focus = E.toW(0, apronV);
    group(E, -len * 0.2, apronV - side * 3, 'scatter', KA(E, 4, 8), { faction: fac(E, 0, 'us_army'), radius: 6, spacing: 2 });
    group(E, len * 0.1, apronV - side * 3, 'line', KA(E, 3, 6), { faction: fac(E, 0, 'us_army'), kind: 'pilot', th: side * PI / 2, spacing: 1.5 });
    group(E, E.rr(-10, 10), side * (off + 20), 'ranks', KA(E, 10, 18), { faction: fac(E, 0, 'us_army'), officers: 0.08, th: side > 0 ? PI / 2 : -PI / 2 });
    scatterTrees(E, 200, { shrub: 3, palm: 1, broad: 1 }, 0.12, { avoid: (x, z) => false });
  },

  lz(E) {
    const { r, n } = E, R = n * 0.34;
    const rad = E.rr(15, 21), cu = E.rr(-8, 8), cv = E.rr(-8, 8), inClear = (x, z) => { const a = E.toW(cu, cv); return Math.hypot((x - a[0]), (z - a[1])) < rad; };
    // keep the clearing free so props stay out of it
    // grass tufts in the clearing
    for (let i = 0; i < 90; i++) { const a = r() * PI * 2, d = Math.sqrt(r()) * rad, [x, z] = E.toW(cu + Math.cos(a) * d, cv + Math.sin(a) * d), g = E.G(x, z); if (g.water === 0 && E.relief(x, z, 0.6) <= 3) E.box(x, z, g.y, 0.2, E.rr(0.2, 0.6), 0.2, E.vary(r() < 0.5 ? [178, 170, 90] : [140, 160, 70], 0.1), r() * PI); }
    // helicopters: landing loops + parked
    const nh = E.ri(3, 5);
    for (let i = 0; i < nh; i++) {
      const a = (i / nh) * PI * 2 + E.rr(-0.3, 0.3), d = rad * E.rr(0.45, 0.7), [x, z] = E.toW(cu + Math.cos(a) * d, cv + Math.sin(a) * d);
      if (i < nh - 1) heliLanding(E, x, z, E.A + E.rr(0, PI * 2), E.chance(0.5) ? C.olive : [86, 94, 70], E.rr(10, 16), E.rr(11, 15), E.rr(0, 14));
      else heliStatic(E, x, z, E.A + E.rr(0, PI * 2));
    }
    // marker smoke
    const [mx, mz] = E.toW(cu + E.rr(-4, 4), cv + E.rr(-4, 4));
    const smk = E.pick([[230, 200, 40], [200, 50, 50], [130, 60, 160], [80, 180, 90]]);
    E.take(mx, mz, 0.8); smoke(E, mx, mz, 0.9, { c: smk, big: 1.1, tall: 1.2 });
    // troops in two groups, a few at the perimeter
    const f0 = fac(E, 0, 'us_army'), f1 = fac(E, 1, f0), skirm = { standing: 1, kneeling: 2, aiming: 2, prone: 1.5 };
    group(E, cu - rad * 0.2, cv, 'scatter', KA(E, 10, 18), { faction: f0, radius: 4.5, poses: skirm, officers: 0.06 });
    group(E, cu + rad * 0.4, cv + rad * 0.3, 'scatter', KA(E, 6, 12), { faction: f1, radius: 3.5, poses: skirm });
    group(E, cu + 1, cv - 1, 'around', KA(E, 6, 10), { faction: f0, radius: 3.2, poses: { standing: 1, kneeling: 1 } });   // waiting round the marker smoke
    E.focus = E.toW(cu, cv);
    for (let i = 0; i < E.ri(3, 6); i++) E.putL(D.supply(E), cu + rad * E.rr(0.6, 0.85) * Math.cos(i), cv + rad * E.rr(0.6, 0.85) * Math.sin(i), E.rr(0, PI), {});
    for (let i = 0; i < E.ri(1, 3); i++) E.putL(D.jeep(E), cu + E.rr(-rad * 0.5, rad * 0.5), cv + E.rr(-rad * 0.5, rad * 0.5), E.rr(0, PI * 2), {});
    // fallen logs at the edge
    for (let i = 0; i < 6; i++) { const a = r() * PI * 2, [x, z] = E.toW(cu + Math.cos(a) * rad * 0.95, cv + Math.sin(a) * rad * 0.95), g = E.G(x, z); if (g.water === 0 && E.relief(x, z, 0.6) <= 3) E.box(x, z, g.y, 2.2, 0.3, 0.3, [80, 58, 38], r() * PI); }
    // jungle around the clearing
    scatterTrees(E, 3000, { broad: 4, emerg: 1.2, palm: 1.2, bamboo: 1.2, shrub: 2.5 }, E.rr(0.55, 0.8), { avoid: (x, z) => inClear(x, z) });
  },

  battle(E) {
    if (E.ancient) return ancientBattle(E);
    const { r, n } = E, R = n * 0.36, gap = E.rr(14, 22), ax = E.rr(-6, 6), aggressor = E.pick([[86, 96, 60], [100, 92, 62]]), defender = E.pick([[116, 106, 78], [96, 82, 58]]);
    const sides = battleSides(E);
    // no man's land craters
    for (let i = 0; i < E.ri(22, 40); i++) { const [x, z] = E.toW(E.rr(-R, R), E.rr(-gap * 0.8, gap * 0.8)); crater(E, x, z, E.rr(1.1, 2.6)); }
    // two trench systems
    const sideDefs = [{ v: -gap, col: defender, dir: -1, fac: sides[0] }, { v: gap, col: aggressor, dir: 1, fac: sides[1] }];
    for (const s of sideDefs) {
      zigzagTrench(E, -R, R, s.v, E.rr(0.8, 1.6), E.rr(2.6, 4));
      zigzagTrench(E, -R * 0.8, R * 0.8, s.v + s.dir * E.rr(6, 9), E.rr(0.5, 1.2), E.rr(3, 4.5));
      for (let u = -R + 4; u < R - 2; u += 3.3) E.segL(u, s.v + s.dir * 3.6, u + 1.6, s.v + s.dir * 7, 0.6, 0.38, C.mud, { jit: 0.1 });
      wireLine(E, -R, R, s.v - s.dir * E.rr(5, 7));
      if (E.chance(0.6)) wireLine(E, -R, R, s.v - s.dir * E.rr(8.5, 10.5), { jag: 0.9 });
      for (let i = 0; i < E.ri(3, 6); i++) E.putL(D.bunker(E), E.rr(-R * 0.8, R * 0.8), s.v + s.dir * E.rr(2.5, 4), s.dir > 0 ? PI : 0, {});
      for (let i = 0; i < E.ri(4, 9); i++) E.putL(D.sandbagRing(E, E.rr(1.1, 1.6)), E.rr(-R * 0.9, R * 0.9), s.v + s.dir * E.rr(1.5, 5), 0, {});
      // a firing line in front of the trench, a second rank behind it, a few officers; both face the enemy
      const face = -s.dir * PI / 2, per = Math.floor(R * 1.7 / 1.2);
      group(E, 0, s.v + s.dir * 2.2, 'line', KA(E, 26, 45), { faction: s.fac, th: face, maxLine: per, poses: { standing: 2, aiming: 3, kneeling: 2, prone: 0.6 }, officers: 0.04, spacing: 1.1 });
      group(E, E.rr(-R * 0.4, R * 0.4), s.v + s.dir * 11, 'ranks', KA(E, 10, 20), { faction: s.fac, th: face, officers: 0.05 });
      marchRoute(E, E.rr(-R * 0.3, R * 0.3), s.v + s.dir * E.rr(15, 24), s.dir > 0 ? 0 : PI, KA(E, 6, 10), s.fac, { officer: true });   // reinforcements along the rear
      for (let i = 0; i < E.ri(1, 3); i++) E.putL(D.howitzer(E, s.col), E.rr(-R * 0.7, R * 0.7), s.v + s.dir * E.rr(13, 20), s.dir > 0 ? -PI / 2 : PI / 2, {});
      for (let i = 0; i < E.ri(2, 5); i++) E.putL(D.tank(E, mul(s.col, 1.05)), E.rr(-R * 0.8, R * 0.8), s.v + s.dir * E.rr(9, 14), s.dir > 0 ? -PI / 2 : PI / 2, {});
      for (let i = 0; i < E.ri(1, 3); i++) E.putL(D.truck(E), E.rr(-R * 0.8, R * 0.8), s.v + s.dir * E.rr(18, 26), E.rr(0, PI * 2), {});
    }
    // burning wrecks, smoke and blasts: always visible and changing
    for (let i = 0; i < E.ri(3, 5); i++) { const [x, z] = E.toW(E.rr(-R, R), E.rr(-gap, gap)); smoke(E, x, z, E.rr(0.5, 1.2), { big: E.rr(0.9, 1.6) }); if (i < 3) { const g = E.G(x, z); E.emitters.push({ kind: 'fire', x, y: g.y + 0.1, z }); } }
    for (let i = 0; i < E.ri(3, 5); i++) { const [x, z] = E.toW(E.rr(-R, R), E.rr(-gap, gap)); E.emitters.push({ kind: 'blast', x, y: E.G(x, z).y + 0.3, z, period: E.rr(3, 6), phase: E.rr(0, 6) }); }
    E.focus = E.toW(0, 0);
    scatterTrees(E, 100, { dead: 3, shrub: 3, broad: 1 }, 0.1, { size: 0.9 });
  },

  fortress(E) {
    const { r, n } = E, R = n * 0.34;
    // strongpoints on the high spots
    const spots = [];
    for (let i = 0; i < 400; i++) { const x = E.rr(n * 0.2, n * 0.8), z = E.rr(n * 0.2, n * 0.8), g = E.G(x, z); if (g.water === 0) spots.push({ x, z, y: g.y + r() * 0.8 }); }
    spots.sort((a, b) => b.y - a.y);
    const chosen = [], want = E.ri(3, 6);
    for (const s of spots) { if (chosen.length >= want) break; if (chosen.every((c) => Math.hypot(c.x - s.x, c.z - s.z) > 22)) chosen.push(s); }
    for (const s of chosen) {
      const rad = E.rr(6, 9), u = (s.x - E.cu), v = (s.z - E.cv);
      // convert world centre back to local layout coords
      const c = Math.cos(E.A), sn = Math.sin(E.A), lu = u * c - v * sn, lv = u * sn + v * c;
      ringTrench(E, lu, lv, rad, 12); ringTrench(E, lu, lv, rad * 0.55, 8);
      wireLine(E, lu - rad - 3, lu + rad + 3, lv - rad - 3.5, { jag: 0.5 }); wireLine(E, lu - rad - 3, lu + rad + 3, lv + rad + 3.5, { jag: 0.5 });
      E.putL(D.bunker(E), lu, lv, E.rr(0, PI * 2), { noocc: true });
      for (let k = 0; k < 4; k++) { const a = k * PI / 2 + E.rr(-0.4, 0.4); E.putL(D.sandbagRing(E, 1.2), lu + Math.cos(a) * rad * 0.8, lv + Math.sin(a) * rad * 0.8, 0, {}); }
      E.putL(D.watchtower(E), lu + rad * 0.3, lv - rad * 0.3, 0, {});
      group(E, lu, lv, 'scatter', KA(E, 6, 12), { faction: fac(E, 0, 'french'), radius: rad * 0.55, poses: { standing: 2, aiming: 2, kneeling: 1 }, officers: 0.08, spacing: 1.5 });
      for (let k = 0; k < E.ri(1, 3); k++) E.putL(D.howitzer(E), lu + E.rr(-rad, rad), lv + rad + E.rr(2, 5), E.rr(0, PI * 2), {});
    }
    if (chosen.length) E.focus = [chosen[0].x, chosen[0].z];
    // attackers dug in on the hills round the strongpoints
    { const hills = []; for (const s of spots) { if (hills.length >= 2) break; if (chosen.every((c) => Math.hypot(c.x - s.x, c.z - s.z) > 30) && hills.every((h) => Math.hypot(h.x - s.x, h.z - s.z) > 30)) hills.push(s); }
      for (const h of hills) { const lu = (h.x - E.cu) * Math.cos(E.A) - (h.z - E.cv) * Math.sin(E.A), lv = (h.x - E.cu) * Math.sin(E.A) + (h.z - E.cv) * Math.cos(E.A); group(E, lu, lv, 'scatter', KA(E, 14, 24), { faction: fac(E, 1, 'pavn'), radius: 9, poses: { standing: 1, kneeling: 2, aiming: 2, prone: 2 }, spacing: 2 }); } }
    // airstrip along the flattest straight
    const a0 = E.A, len = E.rr(46, 60);
    let bestA = a0, bestR = 1e9;
    for (let k = 0; k < 8; k++) { const a = a0 + (k / 8) * PI; let lo = 1e9, hi = -1e9; for (let t = -len / 2; t <= len / 2; t += 6) { const g = E.G(n / 2 + Math.cos(a) * t - 0, n / 2 - Math.sin(a) * t); if (g.water !== 0) hi = 1e9; lo = Math.min(lo, g.y); hi = Math.max(hi, g.y); } if (hi - lo < bestR) { bestR = hi - lo; bestA = a; } }
    const keepA = E.A; E.A = bestA; const sv = E.rr(-14, 14);
    E.segL(-len / 2, sv, len / 2, sv, 4, 0.1, [118, 100, 70], { step: 5, slope: 3 });
    for (let i = 0; i < E.ri(1, 3); i++) E.putL(D.revetment(E), E.rr(-len * 0.3, len * 0.3), sv + 6, PI / 2, {});
    for (let i = 0; i < E.ri(1, 3); i++) E.putL(D.jeep(E), E.rr(-len * 0.4, len * 0.4), sv + 3, 0, {});
    if (E.chance(0.7)) E.putL(D.cargoPlane(E), E.rr(-len * 0.2, len * 0.2), sv - 7, PI / 2, {});
    E.A = keepA;
    // artillery park
    const [ax, az] = E.toW(E.rr(-R, R), E.rr(-R, R));
    for (let i = 0; i < E.ri(3, 6); i++) E.put(D.howitzer(E), ax + (i % 3) * 5 + E.rr(-1, 1), az + Math.floor(i / 3) * 4.5, E.A + E.rr(-0.4, 0.4));
    // parachutes: lying on the ground and a few still drifting down
    for (let i = 0; i < E.ri(14, 30); i++) { const x = E.rr(4, n - 4), z = E.rr(4, n - 4); E.put(D.parachuteGround(E), x, z, E.rr(0, PI * 2), {}); }
    for (let i = 0; i < 5; i++) { const x = E.rr(10, n - 10), z = E.rr(10, n - 10); E.emitters.push({ kind: 'chute', x, z, y: E.G(x, z).y, alt: E.rr(14, 22), period: E.rr(14, 22), phase: E.rr(0, 20), c: E.pick([[236, 236, 230], [200, 190, 150], [150, 170, 110]]) }); }
    for (let i = 0; i < E.ri(2, 4); i++) { const x = E.rr(10, n - 10), z = E.rr(10, n - 10); smoke(E, x, z, 0.8, { big: 1.2 }); }
    for (let i = 0; i < 2; i++) { const x = E.rr(10, n - 10), z = E.rr(10, n - 10); E.emitters.push({ kind: 'blast', x, y: E.G(x, z).y + 0.3, z, period: E.rr(4, 7), phase: E.rr(0, 7) }); }
    scatterTrees(E, 500, { shrub: 3, broad: 2, dead: 1.5, palm: 0.5 }, 0.18);
    for (let i = 0; i < 30; i++) { const x = E.rr(4, n - 4), z = E.rr(4, n - 4); crater(E, x, z, E.rr(1, 2.2)); }
  },

  beach_landing(E) {
    const { r, n } = E, wet = E.hasWater();
    // landing craft at the shore, ships offshore
    if (wet) {
      let placed = 0;
      for (let i = 0; i < 700 && placed < E.ri(6, 12); i++) { const x = E.rr(2, n - 2), z = E.rr(2, n - 2), d = E.ld(x, z); if (d > 1.5 && d < 16 && E.put(D.landingCraft(E), x, z, r() * PI * 2)) placed++; }
      placed = 0;
      for (let i = 0; i < 400 && placed < E.ri(2, 5); i++) { const x = E.rr(2, n - 2), z = E.rr(2, n - 2), d = E.ld(x, z); if (d > 22 && E.put(r() < 0.75 ? D.ship(E) : D.patrolBoat(E), x, z, r() * PI * 2)) placed++; }
    }
    // beach: land close to water (or anywhere on a dry set)
    const near = (x, z) => (wet ? E.wd(x, z) : 6);
    let tanks = 0, tTarget = E.ri(3, 7), troopsN = 0, sup = 0;
    for (let i = 0; i < 3000 && (tanks < tTarget || sup < 8); i++) {
      const x = E.rr(3, n - 3), z = E.rr(3, n - 3), d = near(x, z), g = E.G(x, z);
      if (g.water !== 0) continue;
      if (d < 22 && tanks < tTarget && E.put(D[E.chance(0.7) ? 'tank' : 'apc'](E), x, z, E.rr(0, PI * 2))) tanks++;
      else if (d < 36 && d > 4 && sup < 12 && E.put(D.supply(E), x, z, E.rr(0, PI))) sup++;
    }
    // hedgehog obstacles at the waterline
    for (let i = 0; i < 400; i++) { const x = E.rr(3, n - 3), z = E.rr(3, n - 3), d = near(x, z), g = E.G(x, z); if (g.water === 0 && E.relief(x, z, 0.6) <= 3 && d < 6 && E.chance(0.2) && E.isFree(x, z, 0.7)) { E.take(x, z, 0.7); E.compose([P(0, 0, 0, 1.0, 0.1, 0.1, C.dark, 0.6), P(0, 0, 0, 1.0, 0.1, 0.1, C.dark, -0.6), P(0, 0.1, 0, 0.1, 0.9, 0.1, C.dark)], x, z, g.y + 0.1, r() * PI); } }
    // landing troops wading in lines, a crowd of locals a little inland
    { const f0 = fac(E, 0, 'us_marine'), f1 = fac(E, 1, 'civilian'), shore = [], inland = [];
      for (let i = 0; i < 1500; i++) { const x = E.rr(5, n - 5), z = E.rr(5, n - 5), d = near(x, z), g = E.G(x, z); if (g.water !== 0) continue; if (d >= 1.5 && d < 9 && shore.length < 12) shore.push([x, z]); else if (d > 14 && d < 30 && inland.length < 6) inland.push([x, z]); }
      const toL = (x, z) => [(x - E.cu) * Math.cos(E.A) - (z - E.cv) * Math.sin(E.A), (x - E.cu) * Math.sin(E.A) + (z - E.cv) * Math.cos(E.A)];
      const nLines = Math.min(shore.length, E.ri(3, 5)), per = Math.max(8, Math.round(KA(E, 60, 110) / Math.max(1, nLines)));
      for (let i = 0; i < nLines; i++) { const [lu, lv] = toL(shore[i][0], shore[i][1]); group(E, lu, lv, i % 2 ? 'line' : 'ranks', per, { faction: f0, th: E.rr(0, PI * 2) - E.A * 0, poses: { standing: 3, aiming: 2, kneeling: 1, prone: 0.4 }, officers: 0.05 }); }
      for (let i = 0; i < Math.min(inland.length, 3); i++) { const [lu, lv] = toL(inland[i][0], inland[i][1]); group(E, lu, lv, 'crowd', KA(E, 14, 26), { faction: f1, kind: f1 === 'civilian' ? 'civilian' : 'soldier', face: 'random' }); }
      if (shore.length) E.focus = shore[0]; }
    for (let i = 0; i < E.ri(2, 4); i++) { const x = E.rr(6, n - 6), z = E.rr(6, n - 6); if (near(x, z) < 30) smoke(E, x, z, 0.8, { big: 1.2 }); }
    for (let i = 0; i < 3; i++) { const x = E.rr(6, n - 6), z = E.rr(6, n - 6); if (near(x, z) < 30) E.emitters.push({ kind: 'blast', x, y: E.G(x, z).y + 0.3, z, period: E.rr(3, 6), phase: E.rr(0, 6) }); }
    for (let i = 0; i < 20; i++) { const x = E.rr(3, n - 3), z = E.rr(3, n - 3); if (near(x, z) < 28) crater(E, x, z, E.rr(1, 2)); }
    scatterTrees(E, 700, { palm: 4, broad: 2, shrub: 2 }, 0.25, { avoid: (x, z) => near(x, z) < 8 });
  },

  jungle(E) {
    const { r, n } = E, dens = E.rr(0.65, 0.95);
    // a winding trail first, so trees keep off it
    const tr = [], tilt = r() * PI * 2, amp = E.rr(4, 10), ph = r() * 6;
    for (let t = -n * 0.45; t <= n * 0.45; t += 5) tr.push(E.toW(t, Math.sin(t * 0.09 + ph) * amp));
    pathLine(E, tr, 1.4, E.vary([128, 98, 66], 0.1), {});
    const nearTrail = (x, z) => tr.some((p) => Math.abs(p[0] - x) < 2.2 && Math.abs(p[1] - z) < 2.2);
    scatterTrees(E, 2600, { broad: 4, emerg: 1.3, palm: 1.4, bamboo: 1.2, shrub: 3, dead: 0.2 }, dens, { avoid: nearTrail, size: E.rr(0.95, 1.2) });
    for (let i = 0; i < E.ri(8, 18); i++) { const x = E.rr(4, n - 4), z = E.rr(4, n - 4), g = E.G(x, z); if (g.water === 0 && E.relief(x, z, 0.6) <= 3 && !nearTrail(x, z)) E.box(x, z, g.y, E.rr(2, 3.4), 0.3, 0.32, [80, 58, 38], r() * PI); }
    for (let i = 0; i < E.ri(1, 3); i++) { const x = E.rr(10, n - 10), z = E.rr(10, n - 10); smoke(E, x, z, 0.5, { c: [150, 150, 150], big: 0.8 }); }
    // a patrol walking the trail
    if (tr.length > 6) { const pl = polylineAt(tr); marchPath(E, pl.at, -pl.L * 0.5, pl.L * 1.5, KA(E, 6, 9), fac(E, 0, 'viet_cong'), { officer: true }); }
  },

  trail(E) {
    const { r, n } = E, R = n * 0.4;
    // winding trail, two forks
    const amp = E.rr(5, 12), ph = r() * 6, fr = E.rr(0.05, 0.1), path = [], forkAt = E.rr(-R * 0.3, R * 0.3);
    for (let t = -R; t <= R; t += 4) path.push([t, Math.sin(t * fr + ph) * amp]);
    const wpts = path.map((p) => E.toW(p[0], p[1]));
    pathLine(E, wpts, E.rr(2.2, 3), E.vary([134, 104, 72], 0.08), {});
    const fork = path.filter((p) => p[0] > forkAt).map((p) => E.toW(p[0], p[1] + (p[0] - forkAt) * 0.45));
    pathLine(E, fork, 1.4, E.vary([128, 98, 66], 0.1), {});
    const nearTrail = (x, z) => wpts.some((p) => Math.abs(p[0] - x) < 2.6 && Math.abs(p[1] - z) < 2.6);
    // convoy
    const tilt = (i) => { const a = path[Math.max(0, Math.min(path.length - 1, i))], b = path[Math.max(0, Math.min(path.length - 1, i + 1))]; return Math.atan2(-(b[1] - a[1]), b[0] - a[0]); };
    let nt = 0;
    for (let k = 3; k < path.length - 3 && nt < E.ri(4, 8); k += E.ri(3, 5)) { const [x, z] = wpts[k], th = tilt(k) + E.A * 0; if (E.put(D.truck(E), x, z, th, { noocc: true })) nt++; }
    for (let k = 2; k < path.length - 2; k += E.ri(1, 3)) { if (E.chance(0.5)) { const [x, z] = wpts[k]; E.put(D.bicycle(E), x + E.rr(-0.5, 0.5), z + E.rr(-0.5, 0.5), tilt(k) + (E.chance(0.5) ? 0 : PI), { noocc: true }); } }
    for (let i = 0; i < E.ri(10, 20); i++) { const k = E.ri(0, wpts.length - 1), x = wpts[k][0] + E.rr(-9, 9), z = wpts[k][1] + E.rr(-9, 9); crater(E, x, z, E.rr(1.4, 3)); }
    for (let i = 0; i < E.ri(3, 6); i++) { const k = E.ri(2, wpts.length - 3); E.put(D.supply(E), wpts[k][0] + E.rr(3, 5), wpts[k][1] + E.rr(3, 5), E.rr(0, PI)); }
    scatterTrees(E, 2000, { broad: 4, emerg: 1.2, palm: 1, bamboo: 1.4, shrub: 2.5 }, E.rr(0.5, 0.85), { avoid: nearTrail });
    for (let i = 0; i < 2; i++) { const k = E.ri(3, wpts.length - 4); smoke(E, wpts[k][0] + 5, wpts[k][1] + 4, 0.6, { big: 1 }); }
    // porters and soldiers walking the trail
    if (wpts.length > 6) {
      const pl = polylineAt(wpts);
      for (let k = 0; k < 2; k++) marchPath(E, pl.at, -pl.L * 0.5, pl.L * 1.5, KA(E, 5, 8), fac(E, k, k ? 'civilian' : 'pavn'), { officer: k === 0, spacing: 2.6 });
    }
    E.focus = wpts[Math.floor(wpts.length / 2)];
  },

  delta(E) {
    const { r, n } = E, R = n * 0.4, wet = E.hasWater();
    // a small village on whatever dry land is closest to water
    const cu = E.rr(-R * 0.4, R * 0.4), cv = E.rr(-R * 0.4, R * 0.4), houses = [];
    for (let i = 0; i < 400 && houses.length < E.ri(8, 16); i++) {
      const a = r() * PI * 2, d = 3 + Math.sqrt(r()) * 12, [x, z] = E.toW(cu + Math.cos(a) * d, cv + Math.sin(a) * d);
      if (wet && E.wd(x, z) > 18) continue;
      const p = E.put(r() < 0.6 ? D.stiltHut(E) : D.groundHut(E), x, z, E.A + E.pick([0, PI / 2, PI, -PI / 2]) + E.rr(-0.2, 0.2));
      if (p) houses.push(p);
    }
    // paddy grid with shared dikes
    const pw = E.rr(8, 12), pd = E.rr(6, 9);
    for (let u = -R; u <= R && !E.full(); u += pw + 0.2) for (let v = -R; v <= R; v += pd + 0.2) {
      const [x, z] = E.toW(u, v);
      if (wet && E.wd(x, z) > 45) continue;
      if (E.relief(x, z, 4) >= 3) continue;
      paddyPlot(E, x, z, pw, pd, E.A);
    }
    // sampans
    if (wet) { let b = 0, t = E.ri(6, 14); for (let i = 0; i < 700 && b < t; i++) { const x = E.rr(2, n - 2), z = E.rr(2, n - 2); if (E.put(D.sampan(E), x, z, r() * PI * 2)) b++; } }
    // dike-side palms and clumps
    scatterTrees(E, 500, { palm: 4, bamboo: 1.5, shrub: 2, broad: 1 }, 0.22);
    for (let i = 0; i < Math.min(2, houses.length); i++) smoke(E, houses[i].x, houses[i].z, 0.5, { c: [150, 146, 140], big: 0.6 });
    // farmers working the paddies
    E.focus = E.toW(cu, cv);
    for (let i = 0; i < 4; i++) group(E, E.rr(-R * 0.7, R * 0.7), E.rr(-R * 0.7, R * 0.7), 'scatter', KA(E, 3, 7), { faction: 'civilian', kind: 'civilian', radius: 4, spacing: 2.2, face: 'random' });
  },
};

// named people and banners near the set's focal point -------------------------------------------------------------------
const strs = (v) => (Array.isArray(v) ? v.filter((t) => typeof t === 'string' && t.trim()).map((t) => t.trim()) : []);
function placeNames(E, names) {
  const labels = [], fx = E.focus[0], fz = E.focus[1], f0 = fac(E, 0, 'us_army');
  names.forEach((text, i) => {
    for (let d = 3 + i * 1.5; d < 48; d += 1.2) for (let k = 0; k < 12; k++) {
      const a = i * 0.9 + (k / 12) * PI * 2, x = fx + Math.cos(a) * d, z = fz + Math.sin(a) * d;
      if (!standOK(E, x, z) || !E.isFree(x, z, 0.75) || labels.some((l) => Math.hypot(l.x - x, l.z - z) < 2.5)) continue;
      const pl = person(E, x, z, E.rr(0, PI * 2), 'officer', f0, { pose: 'standing' });
      if (!pl) continue;
      E.take(x, z, 0.8); labels.push({ x, y: pl.top + 1, z, text }); return;
    }
  });
  return labels;
}
function placeSigns(E, texts) {
  const signs = [], fx = E.focus[0], fz = E.focus[1];
  texts.forEach((text, i) => {
    const w = Math.max(3, Math.min(14, 0.7 * text.length + 1.2)), h = 1.3, th = E.rr(-0.3, 0.3);
    for (let d = 7 + i * 3; d < 55; d += 1.5) for (let k = 0; k < 12; k++) {
      const a = i * 1.7 + (k / 12) * PI * 2, x = fx + Math.cos(a) * d, z = fz + Math.sin(a) * d, f = E.fp(x, z, w, 1.2, th, { slope: 2 });
      if (!f || signs.some((q) => Math.hypot(q.x - x, q.z - z) < w)) continue;
      E.take(x, z, f.rad);
      const rise = f.hi - f.lo, by = rise + 2.2;
      E.compose([P(-w / 2 + 0.15, 0, 0, 0.25, by + h + 0.2, 0.25, C.wood), P(w / 2 - 0.15, 0, 0, 0.25, by + h + 0.2, 0.25, C.wood), P(0, by, 0, w, h, 0.15, [240, 238, 230]), P(0, by - 0.08, 0, w + 0.1, 0.08, 0.2, C.dark), P(0, by + h, 0, w + 0.1, 0.08, 0.2, C.dark)], x, z, f.lo, th);
      signs.push({ x, y: f.lo + by + h / 2, z, w, h, rot: th, text }); return;
    }
  });
  return signs;
}

/** Build a set. Unknown recipes become 'village' (a set never stops a render). `ctx` also carries optional story data:
 *  factions (['us_marine', 'pavn']), names (['Gen. Karch']), signs (['WELCOME']). */

// ---------------------------------------------------------------------------------------------------------------------
// Landmarks: real places as block models (lib/landmarks.mjs names them). Each returns a definition centred on (0, 0), built
// up from y = 0; buildSet places it at the set's centre before the recipe so streets and crowds fill in around it.
// ---------------------------------------------------------------------------------------------------------------------
const STONE = [214, 204, 180], MARBLE = [236, 232, 222], TRAVERTINE = [206, 186, 150];
function ringParts(parts, rx, rz, y, h, k, sz, c, gapEvery = 0) {
  for (let i = 0; i < k; i++) {
    if (gapEvery && i % gapEvery === 1) continue;
    const a = (i / k) * PI * 2, x = Math.cos(a) * rx, z = Math.sin(a) * rz;
    const seg = (2 * PI * Math.sqrt((rx * rx + rz * rz) / 2)) / k + 0.05;
    parts.push(P(x, y, z, sz, h, seg, c, -a));
  }
}
function columnsRow(parts, x0, x1, z, n, y, h, c, along = 'x') {
  for (let i = 0; i < n; i++) { const t = n === 1 ? 0.5 : i / (n - 1), u = x0 + (x1 - x0) * t; parts.push(along === 'x' ? P(u, y, z, 0.9, h, 0.9, c) : P(z, y, u, 0.9, h, 0.9, c)); }
}
function pediment(parts, x, y, w, d, c, along = 'z') {   // stepped triangle roof over a portico
  for (let k = 0; k < 4; k++) parts.push(along === 'z' ? P(x, y + k * 0.5, 0, d, 0.5, w - k * (w / 4.5), c) : P(0, y + k * 0.5, x, w - k * (w / 4.5), 0.5, d, c));
}
const LM = {
  colosseum(E) {
    const parts = [], rx = 26, rz = 21, k = 64, tier = 3.2;
    for (let t = 0; t < 4; t++) {   // three arcaded tiers and a solid attic; arches = gaps between piers
      const y = t * tier, h = t === 3 ? 2.2 : tier - 0.5, c = E.vary(TRAVERTINE, 0.04);
      if (t < 3) { for (let i = 0; i < k; i++) { const a = (i / k) * PI * 2; parts.push(P(Math.cos(a) * rx, y, Math.sin(a) * rz, 1.4, h, 1.0, c, -a)); } ringParts(parts, rx, rz, y + h, 0.5, k, 1.5, mul(c, 0.92)); }
      else ringParts(parts, rx, rz, y, h, k, 1.4, c);
    }
    for (let s = 0; s < 6; s++) ringParts(parts, rx - 2 - s * 1.6, rz - 2 - s * 1.6, 0, 9 - s * 1.4, 56, 1.7, s % 2 ? [176, 160, 132] : [190, 174, 146]);   // seating steps
    parts.push(P(0, 0, 0, (rx - 12) * 2, 0.2, (rz - 12) * 2, C.sand));   // arena
    return { w: rx * 2 + 2, d: rz * 2 + 2, h: 13, parts, landmark: true };
  },
  temple(E) {
    const parts = [], w = 14, d = 24, ph = 2.4, ch = 7, c = MARBLE;
    parts.push(P(0, 0, 0, d, ph, w, mul(c, 0.9)));
    for (let s = 0; s < 4; s++) parts.push(P(d / 2 + 0.6 + s * 0.6, 0, 0, 1.2, ph - s * 0.6, w * 0.7, mul(c, 0.95)));   // front steps
    columnsRow(parts, -d / 2 + 1, d / 2 - 1, w / 2 - 1, 10, ph, ch, c); columnsRow(parts, -d / 2 + 1, d / 2 - 1, -w / 2 + 1, 10, ph, ch, c);
    columnsRow(parts, -w / 2 + 3, w / 2 - 3, d / 2 - 1, 4, ph, ch, c, 'z'); columnsRow(parts, -w / 2 + 3, w / 2 - 3, -d / 2 + 1, 4, ph, ch, c, 'z');
    parts.push(P(-1.5, ph, 0, d - 7, ch, w - 5, [210, 196, 170]));   // cella
    parts.push(P(0, ph + ch, 0, d + 0.4, 1.2, w + 0.4, c));
    for (let k = 0; k < 4; k++) parts.push(P(0, ph + ch + 1.2 + k * 0.55, 0, d + 0.2, 0.55, w - k * 3.1, C.roof));
    return { w: d + 5, d: w + 1, h: ph + ch + 3.5, parts, landmark: true };
  },
  pantheon(E) {
    const parts = [], R = 11, c = [214, 200, 170];
    ringParts(parts, R, R, 0, 9, 40, 1.6, c);
    for (let k = 0; k < 6; k++) { const r = R - 0.5 - k * 1.7; ringParts(parts, r, r, 9 + k * 1.1, 1.1, 36, 2.2, [176, 176, 172]); }
    parts.push(P(0, 9 + 6 * 1.1, 0, 2.5, 0.4, 2.5, [176, 176, 172]));
    const px = R + 4;   // portico: three rows of eight columns and a pediment
    for (let r = 0; r < 3; r++) columnsRow(parts, -7, 7, px + r * 2.2 - 2.2, 8, 0, 8, MARBLE, 'z');
    parts.push(P(px - 0.6, 8, 0, 7.6, 1.0, 16, MARBLE)); pediment(parts, px - 0.6, 9, 16, 7.4, C.roof);
    return { w: (R + px) + 6, d: R * 2 + 2, h: 16, parts, landmark: true };
  },
  palace(E, o = {}) {
    const parts = [], L = 70, D = 16, fl = 3, H = fl * 3.4, wall = o.c || E.pick([[118, 160, 128], [226, 206, 160], [214, 196, 170], [230, 220, 200]]), trim = MARBLE;
    parts.push(P(0, 0, 0, D, H, L, wall), P(0, H, 0, D + 0.6, 0.7, L + 0.6, trim), P(0, H + 0.7, 0, D - 2, 1.4, L - 2, [110, 120, 110]));
    for (const sd of [1, -1]) {   // a dressed front on both long sides: the camera may come from either
      for (let f = 0; f < fl; f++) for (let i = 0; i < 22; i++) parts.push(P(sd * (D / 2 + 0.05), f * 3.4 + 1.1, -L / 2 + 2 + i * ((L - 4) / 21), 0.1, 1.6, 1.0, [80, 100, 120]));   // windows
      for (let i = 0; i < 26; i++) parts.push(P(sd * (D / 2 + 0.5), 0, -L / 2 + 1.4 + i * ((L - 2.8) / 25), 0.6, H, 0.6, trim));   // pilasters
      parts.push(P(sd * (D / 2 + 3), 0, 0, 6, H + 1, 14, wall)); columnsRow(parts, -6, 6, sd * (D / 2 + 5.6), 6, 0, H, trim, 'z'); pediment(parts, sd * (D / 2 + 3), H + 1, 14, 6.2, trim);
    }
    for (const z of [-L / 2 - 6, L / 2 + 6]) parts.push(P(0, 0, z, D + 12, H, 12, wall), P(0, H, z, D + 12.6, 0.7, 12.6, trim));   // wings
    for (let i = 0; i < 12; i++) parts.push(P(-D / 2 - 0.3, H + 0.7, -L / 2 + 3 + i * 5.8, 0.5, 1.2, 0.5, trim));   // roof statues
    return { w: D + 26, d: L + 26, h: H + 4, parts, landmark: true };
  },
  domed(E, o = {}) {
    const parts = [], B = 30, H = 10, c = o.c || [200, 150, 120], dome = [150, 156, 160];
    parts.push(P(0, 0, 0, B, H, B, c), P(0, H, 0, B + 0.6, 0.8, B + 0.6, mul(c, 0.9)));
    for (const [x, z] of [[B / 2 - 3, 0], [-B / 2 + 3, 0]]) for (let k = 0; k < 3; k++) parts.push(P(x, H + 0.8 + k * 1.1, z, 7 - k * 2, 1.1, 12 - k * 3, dome));   // semi-domes
    for (let k = 0; k < 7; k++) { const r = 11 - k * 1.55; ringParts(parts, r, r, H + 0.8 + k * 1.3, 1.3, 32, 2.0, k === 0 ? mul(c, 0.95) : dome); }
    parts.push(P(0, H + 0.8 + 7 * 1.3, 0, 2, 1.4, 2, [200, 170, 70]));
    if (o.minarets !== false) for (const [x, z] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) { const mx = x * (B / 2 + 3), mz = z * (B / 2 + 3); parts.push(P(mx, 0, mz, 1.6, 22, 1.6, MARBLE), P(mx, 15, mz, 2.4, 0.6, 2.4, MARBLE), P(mx, 22, mz, 1.0, 3, 1.0, dome)); }
    return { w: B + 9, d: B + 9, h: 26, parts, landmark: true };
  },
  cathedral(E) {
    const parts = [], L = 44, W = 14, H = 13, c = E.pick([[196, 186, 160], [176, 170, 156], [210, 200, 176]]), roof = [96, 110, 116];
    parts.push(P(-2, 0, 0, L, H, W, c));
    for (let k = 0; k < 5; k++) parts.push(P(-2, H + k * 1.2, 0, L, 1.2, W - k * 2.8, roof));   // pitched roof
    parts.push(P(2, 0, 0, 12, H * 0.9, W + 16, c)); for (let k = 0; k < 4; k++) parts.push(P(2, H * 0.9 + k * 1.2, 0, 12 - k * 2.8, 1.2, W + 16, roof));   // transept
    for (const z of [W / 2 - 2.5, -W / 2 + 2.5]) { parts.push(P(L / 2 - 2, 0, z, 6, 26, 6, c)); for (let k = 0; k < 4; k++) parts.push(P(L / 2 - 2, 26 + k * 2, z, 4.4 - k, 2, 4.4 - k, roof)); }   // towers and spires
    for (let i = 0; i < 9; i++) for (const z of [W / 2 + 1.2, -W / 2 - 1.2]) parts.push(P(-L / 2 + 4 + i * 4.4, 0, z, 1.2, H * 0.8, 1.6, mul(c, 0.9)));   // buttresses
    parts.push(P(L / 2 + 1.05, H * 0.55, 0, 0.1, 3.6, 3.6, [150, 60, 110]));   // rose window
    return { w: L + 6, d: W + 18, h: 34, parts, landmark: true };
  },
  castle(E) {
    const parts = [], S = 34, wh = 6, c = E.pick([[150, 146, 138], [176, 166, 146]]);
    for (const [x, z, sx, sz] of [[S / 2, 0, 1.6, S], [-S / 2, 0, 1.6, S], [0, S / 2, S, 1.6], [0, -S / 2, S, 1.6]]) {
      parts.push(P(x, 0, z, sx, wh, sz, c));
      const n = 12; for (let i = 0; i < n; i++) { const t = -0.5 + (i + 0.5) / n; parts.push(P(x + (sx > 2 ? t * sx : 0), wh, z + (sz > 2 ? t * sz : 0), sx > 2 ? 1.2 : 1.8, 0.9, sz > 2 ? 1.2 : 1.8, c)); }
    }
    for (const [x, z] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) parts.push(P(x * S / 2, 0, z * S / 2, 4.6, wh + 3.5, 4.6, mul(c, 1.04)), P(x * S / 2, wh + 3.5, z * S / 2, 5.2, 0.9, 5.2, c));
    parts.push(P(-3, 0, 0, 11, 15, 11, mul(c, 1.06)), P(-3, 15, 0, 12, 1, 12, c), P(S / 2 + 0.2, 0, 0, 0.4, 3.6, 3.4, C.wood));
    return { w: S + 6, d: S + 6, h: 16, parts, landmark: true };
  },
  wall(E) {
    const parts = [], L = 150, c = [168, 160, 142];
    parts.push(P(0, 0, 0, 2.2, 3.4, L, c));
    for (let i = 0; i < 40; i++) parts.push(P(0, 3.4, -L / 2 + 1.8 + i * (L - 3.6) / 39, 2.4, 0.7, 1.2, c));
    parts.push(P(-3.5, 0, 0, 9, 4.2, 9, mul(c, 1.05)), P(-3.5, 4.2, 0, 9.4, 0.5, 9.4, c), P(1.6, 0, 0, 1, 2.6, 2.4, C.wood));   // milecastle and gate
    parts.push(P(-9, 0.02, 0, 3, 0.4, L, [110, 92, 70]));   // the ditch line
    return { w: 14, d: L, h: 5, parts, landmark: true };
  },
  arch(E) {
    const parts = [], W = 13, D = 5, H = 11, c = MARBLE;
    parts.push(P(0, 0, W / 2 - 1.8, D, 7, 3.6, c), P(0, 0, -W / 2 + 1.8, D, 7, 3.6, c), P(0, 7, 0, D, 2.4, W, c), P(0, 9.4, 0, D + 0.4, 1.6, W + 0.4, mul(c, 0.94)));
    for (const z of [W / 2 - 0.4, W / 2 - 3.2, -W / 2 + 0.4, -W / 2 + 3.2]) parts.push(P(D / 2 + 0.4, 0, z, 0.8, 7, 0.8, mul(c, 0.96)));
    parts.push(P(0, H, 0, 2, 1.2, 4, [176, 150, 80]));
    return { w: D + 4, d: W + 4, h: H + 1.5, parts, landmark: true };
  },
  pyramid(E) {
    const parts = [], B = 46, steps = 18, c = [216, 190, 134];
    for (let k = 0; k < steps; k++) { const s = B * (1 - k / steps); parts.push(P(0, k * 1.35, 0, s, 1.35, s, E.vary(c, 0.03))); }
    return { w: B + 2, d: B + 2, h: steps * 1.35, parts, landmark: true };
  },
  column(E) {
    const parts = [P(0, 0, 0, 5, 3, 5, MARBLE)];
    for (let k = 0; k < 12; k++) parts.push(P(0, 3 + k * 1.6, 0, 2.2, 1.6, 2.2, k % 2 ? [226, 220, 206] : MARBLE));
    parts.push(P(0, 22.2, 0, 3, 0.8, 3, MARBLE), P(0, 23, 0, 0.9, 2.2, 0.9, [176, 150, 80]));
    return { w: 7, d: 7, h: 25.5, parts, landmark: true };
  },
};
LM.mosque = (E) => LM.domed(E, { c: [226, 220, 206], minarets: true });
/** The flattest spot near the set's centre for a footprint w x d (layout offsets tried outward); the centre when none is flat. */
function flatSpot(E, w, d) {
  const steps = [0, 0.08, -0.08, 0.16, -0.16, 0.24, -0.24];
  for (const a of steps) for (const b of steps) { const [x, z] = E.toW(a * E.n, b * E.n), f = E.fp(x, z, w, d, E.A, { slope: 2.5, noocc: true }); if (f) return [a * E.n, b * E.n]; }
  return [0, 0];
}
/** Place a landmark at the set's centre, levelled on a plinth whatever the slope, and make it the set's focus. */
function placeLandmark(E, name) {
  const def = (LM[name] || LM.temple)(E), hd = name === 'wall' ? 0 : E.pick([0, PI / 2, PI, -PI / 2]) * 0;
  const [lu, lv] = flatSpot(E, def.w * 0.9, def.d * 0.9), [x, z] = E.toW(lu, lv), f = E.fp(x, z, def.w * 0.9, def.d * 0.9, E.A + hd, { slope: 1e9, noocc: true });
  if (!f) return false;
  E.compose([[0, -(f.hi - f.lo) - 0.2, 0, def.w * 0.9, f.hi - f.lo + 0.3, def.d * 0.9, [190, 180, 160], 0], ...def.parts], x, z, f.hi, E.A + hd);   // plinth, then the model
  E.take(x, z, Math.hypot(def.w, def.d) * 0.48);
  E.landmarkAt = [x, z];
  return true;
}

// ---------------------------------------------------------------------------------------------------------------------
// Indoor scenes: a room seen from above with low cut-away walls (a doll's house), people sitting and standing in it.
// ---------------------------------------------------------------------------------------------------------------------
function room(E, W, D, floorA, floorB, wallC, o = {}) {
  [E.ru, E.rv] = flatSpot(E, W + 4, D + 4);
  const [cx, cz] = E.toW(E.ru, E.rv), f = E.fp(cx, cz, W + 4, D + 4, E.A, { slope: 1e9, noocc: true });
  const y0 = f ? f.hi + 0.4 : E.G(cx, cz).y + 0.4, parts = [];
  parts.push([0, -(f ? f.hi - f.lo : 0) - 0.4, 0, W + 4, (f ? f.hi - f.lo : 0) + 0.4, D + 4, mul(wallC, 0.8), 0]);   // the building's footing
  for (let i = 0; i < W / 2; i++) for (let j = 0; j < D / 2; j++) parts.push([-W / 2 + 1 + i * 2, 0, -D / 2 + 1 + j * 2, 2, 0.12, 2, (i + j) % 2 ? floorA : floorB, 0]);   // tiled floor
  const wh = o.wallH ?? 2.6;
  for (const [x, z, sx, sz] of [[0, D / 2 + 0.5, W + 2, 1], [0, -D / 2 - 0.5, W + 2, 1], [W / 2 + 0.5, 0, 1, D], [-W / 2 - 0.5, 0, 1, D]]) parts.push([x, 0, z, sx, wh, sz, wallC, 0]);
  for (let i = 0; i < Math.floor(W / 4); i++) for (const z of [D / 2 + 0.5, -D / 2 - 0.5]) parts.push([-W / 2 + 2 + i * 4, 0, z, 0.9, wh + 0.4, 1.3, mul(wallC, 1.08), 0]);   // pilasters
  for (let i = 0; i < Math.floor(W / 4) - 1; i++) parts.push([-W / 2 + 4 + i * 4, wh * 0.35, D / 2 + 0.02, 1.6, wh * 0.55, 0.1, o.windows || [120, 150, 180], 0]);   // windows / paintings on the far wall
  E.compose(parts, cx, cz, y0, E.A);
  E.take(cx, cz, Math.hypot(W, D) * 0.5 + 1);
  E.focus = [cx, cz];
  return y0;
}
/** People inside a room (layout coords relative to the room centre), at floor height y0. */
function indoorPerson(E, u, v, th, kind, faction, pose, y0) {
  const [x, z] = E.toW(u + (E.ru || 0), v + (E.rv || 0)), parts = figure(kind, { faction, pose, seed: Math.floor(E.r() * 1e9) });
  E.compose(toBoxParts(parts), x, z, y0 + 0.12, E.A + th);
}
function furniture(E, u, v, th, parts, y0) { const [x, z] = E.toW(u + (E.ru || 0), v + (E.rv || 0)); E.compose(parts, x, z, y0 + 0.12, E.A + th); }
const INDOOR = {
  hall(E) {
    if (E.ancient) {   // a senate: stone floor, tiers of benches down both long sides full of senators, the consuls' chairs at the end
      const W = 40, D = 28, y0 = room(E, W, D, [214, 206, 188], [190, 180, 160], [206, 196, 172], { windows: [170, 150, 120] });
      for (const side of [-1, 1]) for (let t = 0; t < 3; t++) {
        const v = side * (D / 2 - 2 - t * 2.4);
        furniture(E, 0, v, 0, [[0, 0, 0, W - 8, 0.5 + t * 0.4, 1.6, [176, 160, 132], 0]], y0);
        for (let i = 0; i < 14; i++) indoorPerson(E, -W / 2 + 6 + i * ((W - 12) / 13) + E.rr(-0.3, 0.3), v - side * 0.2, side > 0 ? PI / 2 : -PI / 2, 'civilian', 'senator', 'sitting', y0 + 0.5 + t * 0.4);
      }
      furniture(E, -W / 2 + 3, 0, 0, [[0, 0, 0, 3, 0.8, 6, [150, 120, 80], 0], [0, 0.8, -1.2, 1, 1.2, 1, [196, 170, 80], 0], [0, 0.8, 1.2, 1, 1.2, 1, [196, 170, 80], 0]], y0);
      indoorPerson(E, -W / 2 + 3, -1.2, 0, 'civilian', 'senator', 'sitting', y0 + 0.8); indoorPerson(E, -W / 2 + 3, 1.2, 0, 'civilian', 'senator', 'sitting', y0 + 0.8);
      for (let i = 0; i < 3; i++) indoorPerson(E, -2 + i * 2, E.rr(-2, 2), PI, 'civilian', 'senator', 'standing', y0);   // a speaker and two listeners on the floor
    } else {           // a treaty hall: a long table under the windows, delegates seated both sides, witnesses standing along the walls
      const W = 44, D = 30, y0 = room(E, W, D, [150, 40, 40], [130, 32, 34], [226, 214, 186], { windows: [196, 176, 110] });
      furniture(E, 0, 0, 0, [[0, 0, 0, 24, 0.9, 3, [70, 110, 70], 0], [0, 0.9, 0, 24.2, 0.08, 3.2, [60, 96, 60], 0]], y0);
      for (let i = 0; i < 10; i++) for (const side of [-1, 1]) {
        const u = -10.8 + i * 2.4, v = side * 2.2;
        furniture(E, u, v + side * 0.3, 0, [[0, 0, 0, 0.8, 0.5, 0.8, [110, 70, 44], 0], [side > 0 ? 0 : 0, 0.5, side * 0.35, 0.8, 0.9, 0.12, [110, 70, 44], 0]], y0);
        indoorPerson(E, u, v, side > 0 ? PI / 2 : -PI / 2, 'officer', 'civilian', 'sitting', y0 + 0.08);
      }
      for (let i = 0; i < 26; i++) { const along = E.chance(0.5); indoorPerson(E, along ? E.rr(-W / 2 + 2, W / 2 - 2) : E.pick([-1, 1]) * (W / 2 - 2), along ? E.pick([-1, 1]) * (D / 2 - 2) : E.rr(-D / 2 + 3, D / 2 - 3), E.rr(0, PI * 2), E.chance(0.6) ? 'officer' : 'civilian', 'civilian', 'standing', y0); }
      furniture(E, W / 2 - 4, 0, 0, [[0, 0, 0, 6, 0.04, 2.4, [200, 40, 40], 0]], y0);   // carpet to the door
      for (const v of [-4, 4]) furniture(E, -W / 2 + 1.6, v, 0, [[0, 0, 0, 0.15, 4, 0.15, [200, 180, 80], 0], [0, 2.6, 0.6, 0.06, 1.2, 1.2, E.pick([[40, 70, 160], [190, 40, 40], [240, 240, 240]]), 0]], y0);
    }
    scatterTrees(E, 120, { broad: 3, shrub: 2 }, 0.2, { size: 1 });
  },
  office(E) {   // a head of state's office: desk, chair, the leader seated, aides standing, bookshelves, a flag and a rug
    const W = 26, D = 20, y0 = room(E, W, D, [120, 84, 56], [104, 72, 48], [150, 50, 50], { windows: [150, 170, 190] });
    furniture(E, 0, 0, 0, [[0, 0, 0, 12, 0.05, 9, [170, 40, 44], 0]], y0);   // rug
    furniture(E, -4, 0, 0, [[0, 0, 0, 2.4, 0.9, 5, [80, 50, 30], 0], [0, 0.9, 0, 2.6, 0.08, 5.2, [60, 36, 22], 0], [0.2, 0.98, -1.2, 0.7, 0.04, 0.9, [236, 236, 230], 0], [0.1, 0.98, 1.4, 0.3, 0.4, 0.3, [40, 40, 40], 0]], y0);
    furniture(E, -6.2, 0, 0, [[0, 0, 0, 1, 0.5, 1, [60, 40, 30], 0], [-0.45, 0.5, 0, 0.1, 1.2, 1, [60, 40, 30], 0]], y0);
    indoorPerson(E, -6.0, 0, 0, E.ancient ? 'civilian' : 'officer', E.ancient ? 'senator' : 'civilian', 'sitting', y0 + 0.08);
    for (let i = 0; i < E.ri(2, 4); i++) indoorPerson(E, E.rr(-1, 3), E.rr(-3.5, 3.5), PI + E.rr(-0.4, 0.4), E.ancient ? 'civilian' : E.chance(0.5) ? 'officer' : 'soldier', E.ancient ? 'senator' : 'civilian', 'standing', y0);
    for (let i = 0; i < 5; i++) { const parts = [[0, 0, 0, 0.8, 3, 2.6, [96, 64, 40], 0]]; for (let s = 0; s < 4; s++) for (let b = 0; b < 4; b++) parts.push([0.42, 0.3 + s * 0.7, -0.9 + b * 0.6, 0.06, 0.5, 0.45, E.pick([[150, 40, 40], [40, 70, 120], [60, 110, 60], [190, 160, 90]]), 0]); furniture(E, -W / 2 + 0.6, -D / 2 + 3 + i * 3.4, 0, parts, y0); }
    furniture(E, -W / 2 + 1.2, D / 2 - 2, 0, [[0, 0, 0, 0.15, 3.6, 0.15, [200, 180, 80], 0], [0, 2.4, 0.6, 0.06, 1.2, 1.2, E.pick([[40, 70, 160], [190, 40, 40], [40, 120, 60]]), 0]], y0);
    furniture(E, 6, 0, 0, [[0, 0, 0, 2, 0.6, 5, [110, 90, 70], 0], [0.8, 0.6, 0, 0.4, 0.6, 5, [110, 90, 70], 0]], y0);   // sofa
    scatterTrees(E, 120, { broad: 3, shrub: 2 }, 0.2, { size: 1 });
  },
};

/** A battle before firearms: two armies in close order facing each other across a narrow gap, front ranks clashing with levelled
 *  spears, reserves in blocks behind, cavalry on the wings, standards, catapults and a camp at the rear, war elephants for Carthage,
 *  dust and burning carts instead of shell blasts. The camera's focus is the clash. */
function ancientBattle(E) {
  const { n } = E, R = n * 0.3, gap = E.rr(5, 8), sides = battleSides(E);
  E.focus = E.toW(0, 0);
  // trampled ground in the middle
  for (let i = 0; i < E.ri(30, 50); i++) { const [x, z] = E.toW(E.rr(-R, R), E.rr(-gap * 1.6, gap * 1.6)); crater(E, x, z, E.rr(0.6, 1.4)); }
  [{ v: -gap, dir: -1, fac: sides[0] }, { v: gap, dir: 1, fac: sides[1] }].forEach((s, k) => {
    const face = -s.dir * PI / 2, per = Math.floor(R * 1.6 / 1.0);
    // the clash: front ranks with levelled spears, a second line close behind
    group(E, 0, s.v + s.dir * 1.2, 'line', KA(E, 40, 60), { faction: s.fac, th: face, maxLine: per, poses: { aiming: 4, standing: 1, walking: 1 }, spacing: 1.0 });
    group(E, 0, s.v + s.dir * 4.2, 'line', KA(E, 30, 46), { faction: s.fac, th: face, maxLine: per, poses: { standing: 3, walking: 1 }, officers: 0.04, spacing: 1.0 });
    // reserve blocks (maniples / warbands) in a chequer behind the line
    for (let b = -2; b <= 2; b++) group(E, b * R * 0.36 + (k ? 3 : -3), s.v + s.dir * E.rr(11, 15), 'ranks', KA(E, 14, 22), { faction: s.fac, th: face, officers: 0.06, spacing: 1.0 });
    // fallen
    group(E, E.rr(-R * 0.5, R * 0.5), s.v * 0.3, 'scatter', KA(E, 4, 8), { faction: s.fac, th: face, poses: { prone: 1 } });
    // cavalry on both wings, standards, siege engines and a camp behind
    for (const side of [-1, 1]) for (let i = 0; i < E.ri(4, 7); i++) E.putL(D.horse(E, s.fac), side * (R * 0.95 + E.rr(-4, 6)), s.v + s.dir * E.rr(2, 12), face + E.rr(-0.3, 0.3), {});
    for (let i = 0; i < 4; i++) E.putL({ w: 0.6, d: 0.6, h: 4.2, parts: [P(0, 0, 0, 0.12, 3.6, 0.12, C.wood), P(0, 3.4, 0, 0.1, 0.6, 0.7, FACTIONS[s.fac]?.shieldC || C.olive), P(0, 4.0, 0, 0.3, 0.3, 0.3, [200, 170, 70])] }, (i - 1.5) * R * 0.4, s.v + s.dir * 8, 0, {});
    for (let i = 0; i < E.ri(1, 3); i++) E.putL(D.catapult(E), E.rr(-R * 0.6, R * 0.6), s.v + s.dir * E.rr(20, 26), face, {});
    if (s.fac === 'carthaginian') for (let i = 0; i < E.ri(3, 5); i++) E.putL(D.elephant(E), E.rr(-R * 0.7, R * 0.7), s.v + s.dir * E.rr(5, 9), face, {});
    for (let i = 0; i < E.ri(4, 8); i++) E.putL(D.tent(E), E.rr(-R, R), s.v + s.dir * E.rr(30, 40), E.rr(0, PI), {});
    marchRoute(E, E.rr(-R * 0.3, R * 0.3), s.v + s.dir * E.rr(17, 22), s.dir > 0 ? 0 : PI, KA(E, 6, 10), s.fac, { officer: true });
  });
  // dust and burning carts: always moving, no gunpowder
  for (let i = 0; i < E.ri(3, 5); i++) { const [x, z] = E.toW(E.rr(-R, R), E.rr(-gap * 2, gap * 2)); smoke(E, x, z, E.rr(0.4, 0.9), { big: E.rr(0.8, 1.3) }); if (i < 2) { const g = E.G(x, z); E.emitters.push({ kind: 'fire', x, y: g.y + 0.1, z }); } }
  scatterTrees(E, 100, { broad: 2, shrub: 3 }, 0.1, { size: 0.9 });
}

export function buildSet(recipe, seed = 1, n = 240, ctx = FLAT) {
  const name = BUILD[recipe] || INDOOR[recipe] ? recipe : 'village';
  ctx = ctx || FLAT;
  const E = makeEnv(name, seed, n, ctx);
  // a real place first (its ground is reserved), then the recipe fills in around it; rooms have no landmark
  const lm = !INDOOR.hasOwnProperty(name) && ctx.landmark && LM[ctx.landmark] ? placeLandmark(E, ctx.landmark) : false;
  (BUILD[name] || INDOOR[name])(E);
  if (lm) E.focus = E.landmarkAt;
  // a set is never empty (guards a fully-blocked ctx): scatter low scrub as filler
  if (E.boxes.length < 100) scatterTrees(E, 4000, { shrub: 3, broad: 1 }, 1);
  if (E.boxes.length < 100) for (let i = 0; i < 100 - E.boxes.length + 20; i++) { const x = E.rr(1, n - 1), z = E.rr(1, n - 1); E.box(x, z, E.G(x, z).y, 0.6, 0.4, 0.6, C.leaf); }
  E.reserve = true;
  const labels = placeNames(E, strs(ctx.names)), signs = placeSigns(E, strs(ctx.signs));
  // walking columns last, so they never push another emitter out of the 600-particle budget; trimmed to fit what is left
  let used = E.emitters.reduce((a, em) => a + maxOf(em), 0);
  for (const m of E.marches) { const room = Math.floor((600 - used) / PART_MAX); if (room < 3) break; m.count = Math.min(m.count, room); m.kinds.length = m.count; used += maxOf(m); E.emitters.push(m); }
  return { recipe: name, n, boxes: E.boxes, emitters: E.emitters, labels, signs, focus: E.focus, landmark: lm ? ctx.landmark : null };
}

// ---------------------------------------------------------------------------------------------------------------------
// Particles: a pure function of t
// ---------------------------------------------------------------------------------------------------------------------
const ease = (k) => k * k * (3 - 2 * k);
function rotOff(dx, dz, th) { const c = Math.cos(th), s = Math.sin(th); return [dx * c + dz * s, -dx * s + dz * c]; }
function partsOut(out, parts, x, y, z, th, a = 1) {
  for (const p of parts) { const [ox, oz] = rotOff(p[0], p[2], th); out.push({ x: x + ox, y: y + p[1], z: z + oz, sx: p[3], sy: p[4], sz: p[5], rot: th + (p[7] || 0), c: p[6], a }); }
}

/** The most particles an emitter can ever give in one frame. */
const MAX_PER = { smoke: 18, fire: 10, blast: 16, rotor: 2, chute: 4 };
const PART_MAX = 12;   // most boxes in one figure
const maxOf = (em) => (em.kind === 'march' ? em.count * PART_MAX : MAX_PER[em.kind] ?? ((em.parts ? em.parts.length : 0) + 8));
const included = new WeakMap();
/** Emitters that fit the 600-particle budget, chosen once per set by their worst case, so an emitter never drops in or
 *  out of the frame because another one happens to be busy (that made particles vanish for a single frame). */
function budgeted(set) {
  let list = included.get(set);
  if (!list) { let n = 0; list = set.emitters.map((em) => { n += maxOf(em); return n <= 600; }); included.set(set, list); }
  return list;
}

/** Animated particles of a set at time t. Cubes {x,y,z,s,c,a} or shaped {x,y,z,sx,sy,sz,rot,c,a} (centres). `a` fades a
 *  particle out (the renderer shrinks it to nothing at a = 0); `g` grows or collapses a shaped particle (default 1). */
export function particlesAt(set, t) {
  const out = [], keep = budgeted(set);
  set.emitters.forEach((em, ei) => {
    if (!keep[ei]) return;
    if (em.kind === 'smoke') {
      const col = em.c, big = em.big ?? 1, tall = em.tall ?? 1;
      for (let i = 0; i < 18; i++) {
        const life = 6, age = ((t * (em.rate ?? 1) + (i * life) / 18 + ei * 0.7) % life), k = age / life;
        const c = col ? [col[0] - k * 20, col[1] - k * 20, col[2] - k * 20] : [120 - k * 30, 118 - k * 30, 114 - k * 28];
        out.push({ x: em.x + Math.sin(i * 2.1 + ei) * k * 2 * big + k * 1.5, y: em.y + k * 9 * tall, z: em.z + Math.cos(i * 1.7) * k * 1.5 * big + k * 1.2, s: (0.6 + k * 2.2) * big, c, a: 0.85 * (1 - k) * Math.min(1, k / 0.06) });
      }
    } else if (em.kind === 'fire') {
      for (let i = 0; i < 10; i++) {
        const f = 0.5 + 0.5 * Math.sin(t * 9 + i * 1.3 + ei);
        out.push({ x: em.x + (i % 3) * 0.6 - 0.6, y: em.y + f * 0.8 + (i % 2) * 0.4, z: em.z + Math.floor(i / 3) * 0.5 - 0.5, s: 0.5 + f * 0.4, c: [255, 120 + f * 100, 30], a: 1 });
      }
    } else if (em.kind === 'blast') {
      const age = (t + em.phase) % em.period;
      if (age < 1.4) for (let i = 0; i < 16; i++) {
        const k = age / 1.4, a = i * 0.45, d = 1 + (i % 4) * 0.6;
        // grows from nothing over the first tenth of a second and shrinks to nothing at the end
        out.push({ x: em.x + Math.cos(a) * k * 3 * d, y: em.y + Math.abs(Math.sin(a * 1.7)) * k * 3.4 * d + k * 1.2, z: em.z + Math.sin(a) * k * 3 * d, s: (0.8 + k) * (i % 3 ? 1 : 1.4), c: i % 3 ? [255, 200 - k * 140, 60 - k * 40] : [70, 62, 56], a: (1 - k) * Math.min(1, age / 0.1) });
      }
    } else if (em.kind === 'rotor') {
      const rot = em.rot0 + t * em.speed;
      out.push({ x: em.x, y: em.y, z: em.z, sx: em.len, sy: 0.05, sz: 0.2, rot, c: [36, 36, 36], a: 0.85 });
      out.push({ x: em.x, y: em.y, z: em.z, sx: em.len, sy: 0.05, sz: 0.2, rot: rot + PI / 2, c: [36, 36, 36], a: 0.85 });
    } else if (em.kind === 'flyer' && em.mode === 'land') {
      const p = (((t + em.phase) % em.period) + em.period) % em.period / em.period;
      let k;      // 0 on ground, 1 at altitude
      if (p < 0.5) k = 1 - ease(p / 0.5); else if (p < 0.75) k = 0; else k = ease((p - 0.75) / 0.25);
      const y = em.y + 0.05 + k * em.alt, x = em.x + k * em.drift, spin = em.speed * (k > 0.02 ? 1 : 0.6);
      partsOut(out, em.parts, x, y, em.z, em.th);
      const rot = t * spin + ei;
      for (const q of [0, PI / 2]) out.push({ x, y: y + em.rotorY, z: em.z, sx: em.rotorLen, sy: 0.05, sz: 0.2, rot: rot + q, c: [36, 36, 36], a: 0.85 });
      if (k < 0.35) for (let i = 0; i < 6; i++) { const a = i * 1.05 + t * 2, d = 1 + (1 - k * 2.8) * 2.5; out.push({ x: em.x + Math.cos(a) * d, y: em.y + 0.2 + (i % 2) * 0.3, z: em.z + Math.sin(a) * d, s: 0.5 + (i % 3) * 0.2, c: [170, 150, 118], a: 0.5 * (1 - k * 2.8) }); }
    } else if (em.kind === 'flyer' && em.mode === 'flyby') {
      // the pass starts and ends far outside the set, so the loop's restart is never on screen
      const L = 520, period = Math.max(em.period, L / em.speed), p = (((t + em.phase) % period) + period) % period, d = p * em.speed - 180;
      partsOut(out, em.parts, em.x + em.dx * d, em.y + 2 + Math.min(p, 6) * 0.4, em.z + em.dz * d, em.th);
    } else if (em.kind === 'march') {
      const pathAt = (s) => {
        const k = Math.max(0, Math.min(em.path.length - 1.0001, s / em.step)), i = Math.floor(k), f = k - i, a = em.path[i], b = em.path[i + 1];
        return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
      };
      for (let i = 0; i < em.count; i++) {
        const s = (((em.s0 + t * em.speed - i * em.spacing) % em.L) + em.L) % em.L;
        // full size once clear of the run-up, nothing at either end of the path (which lies beyond the set edge)
        const g = ease(Math.max(0, Math.min(1, s / em.ramp, (em.L - s) / em.ramp)));
        if (g <= 0.001) continue;
        const p = pathAt(s), p0 = pathAt(Math.max(0, s - 1.5)), p1 = pathAt(Math.min(em.L, s + 1.5)), th = Math.atan2(-(p1[2] - p0[2]), p1[0] - p0[0]);
        const phase = s * (PI * 2 / 1.8) + i * 1.7, bob = 0.05 * Math.abs(Math.sin(phase));
        for (const q of figure(em.kinds[i], { faction: em.faction, pose: 'walking', phase, seed: em.seed + i * 7919 })) {
          const [ox, oz] = rotOff(q.x, q.z, th);
          out.push({ x: p[0] + ox, y: p[1] + bob + q.y, z: p[2] + oz, sx: q.sx, sy: q.sy, sz: q.sz, rot: th, c: q.c, a: 1, g });
        }
      }
    } else if (em.kind === 'chute') {
      const p = (((t + em.phase) % em.period) + em.period) % em.period / em.period, y = em.y + (1 - p) * em.alt, sway = Math.sin(t * 0.9 + ei) * 0.8;
      const x = em.x + sway, z = em.z + Math.cos(t * 0.7 + ei) * 0.6;
      // opens high up, collapses on landing: never pops back from the ground to the sky
      const g = Math.min(1, p / 0.06, (1 - p) / 0.08);
      out.push({ x, y: y + 1.5, z, sx: 2.4, sy: 0.3, sz: 2.4, rot: t * 0.2 + ei, c: em.c, a: 1, g });
      out.push({ x, y: y + 1.9, z, sx: 1.4, sy: 0.3, sz: 1.4, rot: t * 0.2 + ei, c: em.c, a: 1, g });
      out.push({ x, y: y + 0.75, z, sx: 0.06, sy: 1.4, sz: 0.06, rot: 0, c: [60, 56, 50], a: 1, g });
      out.push({ x, y, z, sx: 0.25, sy: 0.4, sz: 0.2, rot: 0, c: [92, 98, 60], a: 1, g });
    }
  });
  return out.length > 600 ? out.slice(0, 600) : out;
}

/** One piece of equipment on its own (for the museum inset): -> { parts: [P...], w, d, h } in set units, or null.
 *  Uses the same builders as the scene recipes, so the inset shows the model the scenes use. */
export const MUSEUM_ITEMS = ['tank', 'apc', 'truck', 'jeep', 'howitzer', 'helicopter', 'jet', 'cargoPlane', 'landingCraft', 'patrolBoat', 'sampan', 'ship', 'bicycle'];
export function equipmentModel(kind, seed = 1) {
  const fn = D[kind];
  if (typeof fn !== 'function') return null;
  const E = makeEnv('village', seed, 32, FLAT);
  const def = fn(E, [92, 98, 60]);
  return def && def.parts ? { parts: def.parts.map((p) => ({ x: p[0], y: p[1], z: p[2], sx: p[3], sy: p[4], sz: p[5], c: p[6], rot: p[7] || 0 })), w: def.w, d: def.d, h: def.h } : null;
}
