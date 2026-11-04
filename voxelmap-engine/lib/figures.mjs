// Block humanoids and the formations they stand in. Pure and deterministic (no imports).
//   figure(kind, opts) -> part boxes { x, y, z, sx, sy, sz, c: [r,g,b], rot? } relative to the figure's FOOT CENTRE:
//     x,z = centre of the part, y = bottom of the part (feet at y = 0). The figure FACES LOCAL +x (like the vehicles); the
//     shoulders run along z. A standing figure is ~2.0 units tall (head top ~2.0, hats up to ~2.2).
//   formation(type, count, opts, rng) -> [{ x, z, th }] foot positions and facing. th uses the engine's rotation
//     convention: forward = (cos th, -sin th) in (x, z); it is the box rotation about the vertical axis.

const PI = Math.PI;
const clamp8 = (v) => Math.max(0, Math.min(255, Math.round(v)));
const mul = (c, k) => [clamp8(c[0] * k), clamp8(c[1] * k), clamp8(c[2] * k)];
function mulberry32(seed) {
  let a = (seed >>> 0) || 1;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

export const KINDS = ['soldier', 'officer', 'civilian', 'sailor', 'pilot'];
export const POSES = ['standing', 'walking', 'kneeling', 'aiming', 'prone'];

/** Skin tones, light to dark. */
export const SKINS = [[228, 188, 156], [214, 168, 124], [192, 142, 102], [150, 104, 72], [104, 70, 50]];

const DARK = [34, 34, 36], WHITE = [238, 238, 232], RIFLE = [40, 36, 32];
const CIV_SHIRTS = [[238, 238, 232], [74, 112, 162], [172, 62, 54], [212, 182, 72], [92, 142, 92], [126, 96, 70], [150, 150, 154], [228, 222, 200], [64, 74, 96]];
const CIV_PANTS = [[58, 58, 68], [92, 82, 66], [44, 48, 64], [120, 110, 90], [30, 30, 34]];

/** Faction palettes. hat: 'helmet' | 'cap' | 'pith' | 'conical' | 'beret' | 'sailor' | 'straw' | 'none'. */
export const FACTIONS = {
  us_marine: { shirt: [74, 90, 54], pants: [70, 84, 50], hat: 'helmet', hatC: [66, 80, 48], officer: [150, 136, 92], skins: [0, 0, 1, 2, 3, 4], pack: true },
  us_army: { shirt: [94, 100, 62], pants: [88, 94, 60], hat: 'helmet', hatC: [80, 88, 56], officer: [156, 142, 98], skins: [0, 0, 1, 2, 3, 4], pack: true },
  arvn: { shirt: [104, 110, 76], pants: [98, 102, 70], hat: 'helmet', hatC: [96, 104, 70], officer: [158, 146, 104], skins: [1, 1, 2, 1], pack: true },
  pavn: { shirt: [122, 124, 72], pants: [116, 118, 70], hat: 'pith', hatC: [156, 154, 104], officer: [140, 142, 84], skins: [1, 2, 1, 1], pack: true },
  viet_cong: { shirt: [30, 30, 34], pants: [26, 26, 30], hat: 'conical', hatC: [196, 172, 112], officer: [38, 38, 42], skins: [1, 2, 2, 1], pack: false },
  french: { shirt: [178, 160, 110], pants: [170, 152, 106], hat: 'beret', hatC: [76, 88, 66], officer: [196, 182, 134], skins: [0, 0, 0, 1, 3], pack: true },
  pla: { shirt: [84, 108, 66], pants: [70, 94, 72], hat: 'cap', hatC: [78, 102, 62], officer: [96, 120, 74], skins: [1, 1, 2], pack: true, star: true },
  civilian: { shirt: null, pants: null, hat: 'none', hatC: [200, 176, 116], officer: [60, 64, 90], skins: [1, 1, 2, 2, 0, 3], pack: false },
  sailor: { shirt: [34, 44, 82], pants: [34, 44, 82], hat: 'sailor', hatC: WHITE, officer: [236, 236, 232], skins: [0, 0, 1, 2, 3, 4], pack: false },
};
export const FACTION_NAMES = Object.keys(FACTIONS);

/** The faction a kind wears when none is asked for. */
export function defaultFaction(kind) {
  return kind === 'civilian' ? 'civilian' : kind === 'sailor' ? 'sailor' : 'us_army';
}

/** Height of the tallest part of a figure (feet at 0). */
export function figureHeight(parts) { let h = 0; for (const p of parts) h = Math.max(h, p.y + p.sy); return h; }

const B = (x, y, z, sx, sy, sz, c) => ({ x, y, z, sx, sy, sz, c });

/**
 * One figure. opts: { faction, pose: 'standing'|'walking'|'kneeling'|'aiming'|'prone', phase (walking, radians),
 * seed (colour/skin variety), skin (index into SKINS or [r,g,b]), hat (override), rifle (bool) }.
 */
export function figure(kind = 'soldier', opts = {}) {
  if (!KINDS.includes(kind)) kind = 'soldier';
  const fname = FACTIONS[opts.faction] ? opts.faction : defaultFaction(kind);
  const F = FACTIONS[fname], rng = mulberry32((((opts.seed ?? 0) | 0) * 2654435761) ^ 0x9e3779b9);
  const pose = POSES.includes(opts.pose) ? opts.pose : 'standing';
  const tone = 0.92 + rng() * 0.16;

  // colours
  let shirt, pants, hat = opts.hat ?? F.hat, hatC = F.hatC;
  if (fname === 'civilian') { shirt = CIV_SHIRTS[Math.floor(rng() * CIV_SHIRTS.length)]; pants = CIV_PANTS[Math.floor(rng() * CIV_PANTS.length)]; if (opts.hat === undefined) hat = rng() < 0.3 ? 'straw' : 'none'; }
  else { shirt = F.shirt; pants = F.pants; }
  if (kind === 'officer') { shirt = F.officer; pants = fname === 'civilian' ? F.officer : mul(F.pants, 1.12); if (opts.hat === undefined) { hat = fname === 'sailor' ? 'sailor' : 'cap'; hatC = mul(F.officer, 0.9); } }
  if (kind === 'pilot') { shirt = [92, 104, 74]; pants = shirt; if (opts.hat === undefined) { hat = 'helmet'; hatC = WHITE; } }
  if (kind === 'sailor' && !F.hat) hat = 'sailor';
  shirt = mul(shirt, tone); pants = mul(pants, tone);
  const sk = opts.skin ?? F.skins[Math.floor(rng() * F.skins.length)];
  const skin = Array.isArray(sk) ? sk : SKINS[Math.max(0, Math.min(SKINS.length - 1, sk | 0))];
  const armed = kind === 'soldier' || (kind === 'officer' && opts.rifle === true);
  const rifle = opts.rifle ?? (armed && (pose === 'aiming' || pose === 'kneeling' || pose === 'prone'));
  const parts = [];

  if (pose === 'prone') {
    parts.push(B(-0.75, 0, 0.14, 0.8, 0.2, 0.2, pants), B(-0.75, 0, -0.14, 0.8, 0.2, 0.2, pants));
    parts.push(B(-0.1, 0, 0, 0.7, 0.3, 0.52, shirt));
    parts.push(B(0.5, 0.02, 0, 0.36, 0.34, 0.36, skin));
    parts.push(B(0.5, 0.36, 0, 0.42, 0.14, 0.42, hatC));
    parts.push(B(0.62, 0, 0.3, 0.6, 0.16, 0.14, shirt), B(0.62, 0, -0.3, 0.6, 0.16, 0.14, shirt));
    if (rifle) parts.push(B(0.85, 0.16, 0.12, 1.0, 0.1, 0.1, RIFLE));
    return parts;
  }

  const kneel = pose === 'kneeling', walk = pose === 'walking', aim = pose === 'aiming' || (kneel && rifle);
  const drop = kneel ? 0.4 : 0;
  const hipY = 0.9 - drop;
  const sw = walk ? Math.sin(opts.phase ?? 0) : 0, sw2 = walk ? Math.sin((opts.phase ?? 0) + PI) : 0;
  const lift = (ph) => (walk ? 0.1 * Math.max(0, Math.cos(ph)) : 0);

  // legs
  if (kneel) {
    parts.push(B(0.3, 0, 0.15, 0.3, 0.5, 0.28, pants));                 // front leg, knee up
    parts.push(B(-0.25, 0, -0.15, 0.72, 0.2, 0.28, pants));             // back leg along the ground
  } else {
    parts.push(B(sw * 0.3, lift(opts.phase ?? 0), 0.15, 0.3, 0.9 - lift(opts.phase ?? 0), 0.28, pants));
    parts.push(B(sw2 * 0.3, lift((opts.phase ?? 0) + PI), -0.15, 0.3, 0.9 - lift((opts.phase ?? 0) + PI), 0.28, pants));
  }
  // torso, head
  parts.push(B(0, hipY, 0, 0.34, 0.72, 0.62, shirt));
  parts.push(B(0, hipY + 0.72, 0, 0.4, 0.4, 0.4, skin));
  const top = hipY + 1.12;
  // belt, sash or collar
  if (kind === 'officer') parts.push(B(0, hipY, 0, 0.37, 0.1, 0.65, DARK));
  else if (kind === 'sailor') parts.push(B(0.18, hipY + 0.5, 0, 0.04, 0.22, 0.4, WHITE));
  // arms
  if (aim) {
    parts.push(B(0.42, hipY + 0.5, 0.2, 0.7, 0.2, 0.2, shirt), B(0.42, hipY + 0.5, -0.2, 0.7, 0.2, 0.2, shirt));
    if (rifle) parts.push(B(0.6, hipY + 0.55, 0.0, 0.95, 0.1, 0.1, RIFLE));
  } else {
    parts.push(B(-sw * 0.25, hipY, 0.42, 0.24, 0.7, 0.22, shirt), B(-sw2 * 0.25, hipY, -0.42, 0.24, 0.7, 0.22, shirt));
    if (rifle) parts.push(B(0, hipY + 0.2, -0.38, 0.12, 0.12, 0.9, RIFLE));
  }
  if (F.pack && kind === 'soldier') parts.push(B(-0.26, hipY + 0.1, 0, 0.2, 0.5, 0.42, mul(shirt, 0.8)));
  // hats
  const hy = top - 0.12;
  if (hat === 'helmet') parts.push(B(0, hy, 0, 0.5, 0.22, 0.5, hatC));
  else if (hat === 'cap') { parts.push(B(0, hy + 0.04, 0, 0.46, 0.12, 0.46, hatC), B(0.27, hy + 0.04, 0, 0.18, 0.04, 0.38, mul(hatC, 0.7))); if (F.star && kind !== 'officer') parts.push(B(0.24, hy + 0.06, 0, 0.04, 0.08, 0.08, [200, 40, 36])); }
  else if (hat === 'pith') parts.push(B(0, hy + 0.02, 0, 0.58, 0.1, 0.58, hatC), B(0, hy + 0.12, 0, 0.38, 0.12, 0.38, hatC));
  else if (hat === 'conical') parts.push(B(0, hy + 0.02, 0, 0.7, 0.06, 0.7, hatC), B(0, hy + 0.08, 0, 0.42, 0.1, 0.42, hatC), B(0, hy + 0.18, 0, 0.16, 0.08, 0.16, hatC));
  else if (hat === 'beret') parts.push(B(0, hy + 0.04, 0.03, 0.5, 0.1, 0.46, hatC));
  else if (hat === 'sailor') parts.push(B(0, hy + 0.02, 0, 0.5, 0.14, 0.5, hatC));
  else if (hat === 'straw') parts.push(B(0, hy + 0.02, 0, 0.66, 0.05, 0.66, [204, 180, 118]), B(0, hy + 0.07, 0, 0.36, 0.1, 0.36, [204, 180, 118]));
  return parts;
}

// ---------------------------------------------------------------------------------------------------------------------
// Formations
// ---------------------------------------------------------------------------------------------------------------------
export const FORMATIONS = ['ranks', 'column', 'line', 'crowd', 'scatter', 'around'];

// dart throwing in an ellipse (rx forward, rz lateral): returns exactly `count` points at least `minD` apart
function darts(count, rx, rz, minD, rng) {
  const pts = [];
  let sx = rx, sz = rz, miss = 0;
  while (pts.length < count) {
    const a = rng() * PI * 2, d = Math.sqrt(rng()), x = Math.cos(a) * d * sx, z = Math.sin(a) * d * sz;
    let ok = true;
    for (const p of pts) { const dx = p[0] - x, dz = p[1] - z; if (dx * dx + dz * dz < minD * minD) { ok = false; break; } }
    if (ok) { pts.push([x, z]); miss = 0; } else if (++miss > 30) { sx *= 1.08; sz *= 1.08; miss = 0; }
  }
  return pts;
}

/**
 * Foot positions and facing for `count` figures. opts: { cx, cz (default 0), th (the formation's forward, default 0),
 * spacing, radius, maxLine, abreast, out (around: face outward), face: 'forward'|'center'|'random' }.
 * Local frame: x forward, z lateral. No two figures are ever closer than 0.6 units.
 */
export function formation(type, count, opts = {}, rng = mulberry32(opts.seed ?? 1)) {
  count = Math.max(0, Math.floor(count));
  const sp = Math.max(0.85, opts.spacing ?? 1.1), pts = []; // [lx, lz, thLocal]
  const jit = (a) => (rng() - 0.5) * 2 * a;
  if (type === 'ranks') {
    const cols = Math.max(1, Math.round(Math.sqrt(count * 1.8))), rows = Math.ceil(count / cols);
    for (let i = 0; i < count; i++) {
      const r = Math.floor(i / cols), c = i % cols, inRow = r === rows - 1 ? count - r * cols : cols;
      pts.push([-(r - (rows - 1) / 2) * sp * 1.25 + jit(0.04), (c - (inRow - 1) / 2) * sp + jit(0.04), 0]);
    }
  } else if (type === 'column') {
    const ab = Math.max(1, opts.abreast ?? 2);
    const rowsC = Math.ceil(count / ab);
    for (let i = 0; i < count; i++) { const r = Math.floor(i / ab), a = i % ab; pts.push([-(r - (rowsC - 1) / 2) * sp * 1.4 + jit(0.08), (a - (ab - 1) / 2) * sp * 1.1 + jit(0.05), 0]); }
  } else if (type === 'line') {
    const per = Math.max(2, opts.maxLine ?? 30);
    for (let i = 0; i < count; i++) {
      const r = Math.floor(i / per), c = i % per, inRow = Math.min(per, count - r * per);
      pts.push([-r * sp * 1.1 + jit(0.12), (c - (inRow - 1) / 2) * sp * 1.1 + (r % 2) * sp * 0.5 + jit(0.08), 0]);
    }
  } else if (type === 'crowd' || type === 'scatter') {
    const scat = type === 'scatter', minD = Math.max(0.65, opts.spacing ?? (scat ? 1.8 : 0.75));
    const R = Math.sqrt(count * minD * minD * 1.15 / PI) * (opts.radius ? 1 : 1) + (opts.radius ? 0 : 0.5);
    const rr = opts.radius ? Math.max(opts.radius, 0.5) : R;
    for (const p of darts(count, scat ? rr * 0.8 : rr, scat ? rr * 1.5 : rr, minD, rng)) pts.push([p[0], p[1], null]);
  } else if (type === 'around') {
    const out = !!opts.out;
    let R = opts.radius ?? Math.max(2.2, count * 0.9 / (PI * 2)), placed = 0;
    while (placed < count) {
      const cap = Math.max(1, Math.floor((PI * 2 * R) / 0.9)), k = Math.min(cap, count - placed), a0 = rng() * PI * 2;
      for (let i = 0; i < k; i++) {
        const a = a0 + (i / k) * PI * 2, lx = Math.cos(a) * R, lz = Math.sin(a) * R;
        pts.push([lx, lz, out ? Math.atan2(-lz, lx) : Math.atan2(lz, -lx)]);   // direction (cos t, -sin t) = outward or inward
      }
      placed += k; R += 0.95;
    }
  } else throw new Error('unknown formation ' + type);

  const th = opts.th ?? 0, c = Math.cos(th), s = Math.sin(th), cx = opts.cx ?? 0, cz = opts.cz ?? 0, face = opts.face;
  return pts.map((p) => {
    const lth = p[2] ?? (face === 'random' ? rng() * PI * 2 : face === 'center' ? Math.atan2(p[1], -p[0]) : jit(type === 'crowd' ? 0.8 : 0.9));
    return { x: cx + p[0] * c + p[1] * s, z: cz - p[0] * s + p[1] * c, th: th + lth };
  });
}
