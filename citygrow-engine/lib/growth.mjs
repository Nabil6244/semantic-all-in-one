// How the city grows: house lots laid out along the streets, ranked by when they fill in, and the rule that says how
// many of them stand in a given year. Pure and deterministic (same world + story + seed = same city).
//
// A lot's rank is its place in the growth order (0 = the first house of the oldest core). In a year with population P
// the city has needed(P, year) houses, and lot k stands when k < needed. A shrinking city loses its outermost houses
// first and regrows them in the same order. Fires, sieges and quakes (event rows) clear an area for a while.

export function rng(seed) {
  let s = (seed >>> 0) || 1;
  return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
}
export const hash = (a, b = 0) => {
  let h = Math.imul((a | 0) ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul((b | 0) + 0x632be5ab, 0xc2b2ae35);
  h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12;
  return (h >>> 0) / 4294967296;
};
/** Smooth value noise in [0, 1] with a feature size of `scale` metres: growth comes in clumps, not salt and pepper. */
export function noise2(x, z, scale, seed = 0) {
  const fx = x / scale, fz = z / scale, i = Math.floor(fx), j = Math.floor(fz), u = fx - i, v = fz - j;
  const s = (k) => k * k * (3 - 2 * k);
  const a = hash(i * 7919 + seed, j), b = hash((i + 1) * 7919 + seed, j), c = hash(i * 7919 + seed, j + 1), d = hash((i + 1) * 7919 + seed, j + 1);
  return a + (b - a) * s(u) + (c - a) * s(v) + (a - b - c + d) * s(u) * s(v);
}

export const ROAD_HALF = { 1: 8, 2: 5.5, 3: 3 };   // street half-widths (m) by class (1 main, 2 secondary, 3 lane)
const MAX_LOTS = 130000;

/** Lanes for a world with no street data: a wobbly grid over dry, gentle land. */
export function fallbackLanes(terrain, seed = 1) {
  const out = [], step = 70, lim = terrain.half - 40;
  for (let dir = 0; dir < 2; dir++) {
    for (let a = -lim; a <= lim; a += step) {
      let run = [];
      for (let b = -lim; b <= lim; b += 20) {
        const wob = (noise2(a, b, 240, seed + dir) - 0.5) * 40;
        const [x, z] = dir ? [a + wob, b] : [b, a + wob];
        if (terrain.heightAt(x, z) > 0.8 && !terrain.waterAt?.(x, z)) run.push([x, z]);
        else { if (run.length > 2) out.push({ c: a % (step * 5) === 0 ? 2 : 3, p: run }); run = []; }
      }
      if (run.length > 2) out.push({ c: 3, p: run });
    }
  }
  return out;
}

/** House lots along the streets, up to `rows` deep on each side. Each lot: {x, z, rot, w, d, y, cls, road}. */
export function makeLots(roads, terrain, { seed = 7, rows = 3, max = MAX_LOTS } = {}) {
  const R = rng(seed), lots = [];
  const B = 16, grid = new Map();                       // circle-overlap test in 16 m buckets
  const key = (i, j) => i * 100003 + j;
  const fits = (x, z, rad) => {
    const i0 = Math.floor((x - rad - 12) / B), i1 = Math.floor((x + rad + 12) / B);
    const j0 = Math.floor((z - rad - 12) / B), j1 = Math.floor((z + rad + 12) / B);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const b = grid.get(key(i, j)); if (!b) continue;
      for (const o of b) { const dx = o.x - x, dz = o.z - z, rr = o.rad + rad; if (dx * dx + dz * dz < rr * rr) return false; }
    }
    return true;
  };
  const add = (lot) => { const k = key(Math.floor(lot.x / B), Math.floor(lot.z / B)); (grid.get(k) || grid.set(k, []).get(k)).push(lot); lots.push(lot); };
  // streets block houses: mark them first as long chains of circles
  roads.forEach((rd) => {
    const half = ROAD_HALF[rd.c] || 3;
    for (let k = 0; k + 1 < rd.p.length; k++) {
      const [ax, az] = rd.p[k], [bx, bz] = rd.p[k + 1], len = Math.hypot(bx - ax, bz - az), n = Math.max(1, Math.ceil(len / half));
      for (let s = 0; s <= n; s++) {
        const o = { x: ax + (bx - ax) * s / n, z: az + (bz - az) * s / n, rad: half, street: true };
        const kk = key(Math.floor(o.x / B), Math.floor(o.z / B)); (grid.get(kk) || grid.set(kk, []).get(kk)).push(o);
      }
    }
  });
  const order = roads.map((r, i) => i).sort((a, b) => roads[a].c - roads[b].c);   // main streets claim frontage first
  for (const ri of order) {
    const rd = roads[ri], half = ROAD_HALF[rd.c] || 3;
    for (let k = 0; k + 1 < rd.p.length; k++) {
      const [ax, az] = rd.p[k], [bx, bz] = rd.p[k + 1];
      const len = Math.hypot(bx - ax, bz - az); if (len < 4) continue;
      const tx = (bx - ax) / len, tz = (bz - az) / len, rot = Math.atan2(tz, tx);
      for (let s = 3; s < len - 3;) {
        const w = 7 + R() * 7, d = 7 + R() * 6;
        const cx = ax + tx * (s + w / 2), cz = az + tz * (s + w / 2);
        for (const side of [-1, 1]) {
          let off = half + 1.2;
          for (let row = 0; row < rows; row++) {
            const dd = row ? 7 + R() * 6 : d, ww = row ? 7 + R() * 7 : w;
            const o = off + dd / 2 + (row ? 1.5 : 0);
            const x = cx - tz * side * o, z = cz + tx * side * o, rad = Math.min(ww, dd) * 0.5;
            off = o + dd / 2;
            if (Math.abs(x) > terrain.half - 10 || Math.abs(z) > terrain.half - 10) break;
            const y = terrain.heightAt(x, z);
            if (y < 1.0 || terrain.slopeAt(x, z, Math.max(ww, dd)) > 0.32 || (terrain.waterAt && (terrain.waterAt(x, z) || terrain.waterAt(x + dd * 0.5 * (tz * side), z - dd * 0.5 * (tx * side))))) break;
            if (!fits(x, z, rad)) { if (row === 0) break; else continue; }
            add({ x, z, rot: rot + (R() - 0.5) * 0.08, w: ww, d: dd, y, cls: rd.c, road: ri, rad });
            if (lots.length >= max) return lots;
          }
        }
        s += w + 1 + R() * 2;
      }
    }
  }
  return lots;
}

/**
 * Growth order. cores: [{x, z, year, weight}] — the places a city starts from and the year each starts. A lot's score is
 * its distance to the nearest core (a core founded later counts as further away), lowered on main streets and varied
 * by clumpy noise; rank = position in ascending score.
 */
export function rankLots(lots, cores, { firstYear = 0, lastYear = 2000, seed = 7 } = {}) {
  const span = Math.max(50, lastYear - firstYear);
  const cs = cores.length ? cores : [{ x: 0, z: 0, year: firstYear, weight: 1 }];
  const score = lots.map((l) => {
    let best = Infinity;
    for (const c of cs) {
      const late = 1 + 2.5 * Math.max(0, (c.year ?? firstYear) - firstYear) / span;
      const d = Math.hypot(l.x - c.x, l.z - c.z) * late / (c.weight || 1);
      if (d < best) best = d;
    }
    const street = l.cls === 1 ? 0.82 : l.cls === 2 ? 0.92 : 1;
    return best * street * (0.7 + 0.6 * noise2(l.x, l.z, 380, seed)) + noise2(l.x, l.z, 60, seed + 3) * 120;
  });
  const idx = lots.map((_, i) => i).sort((a, b) => score[a] - score[b]);
  idx.forEach((li, r) => { lots[li].rank = r; });
  return lots;
}

/** How crowded a pre-modern city is: a very big one (Imperial Rome, Justinian's Constantinople) packs people into taller
 *  blocks instead of covering the whole map. 1 = an ordinary town. */
export function densityOf(pop, year) {
  return year < 1850 ? Math.min(3, Math.max(1, Math.sqrt(pop / 150000))) : 1;
}

/** People one lot stands for: old houses hold a household or two; modern lots are apartment blocks. */
export function peoplePerLot(year, pop = 0) {
  let base;
  if (year <= 1750) base = 7;
  else if (year >= 1990) base = 48;
  else { const k = (year - 1750) / 240; base = 7 + 41 * k * k; }
  return base * densityOf(pop, year);
}

/** How many lots stand at population `pop` in `year` (capped by the lots there are). `pph` (a house style's own people per
 *  lot, e.g. low-rise South Asian family houses) replaces the period's default. */
export function needed(pop, year, total, pph = null) {
  const per = pph ? pph * densityOf(pop, year) : peoplePerLot(year, pop);
  return Math.min(total, Math.max(0, pop / per));
}

/** 0..1: how far lot of `rank` has risen when `need` lots stand (a soft edge, so growth reads as a wave). */
export function riseOf(rank, need, total) {
  const ramp = Math.max(25, total * 0.012);
  return Math.max(0, Math.min(1, (need - rank) / ramp));
}

/** 0..1 multiplier from destruction events at (x, z) in `year`: 0 while cleared, regrowing outward afterwards. */
export function eventFactor(events, x, z, year) {
  let f = 1;
  for (const e of events) {
    if (year < e.year) continue;
    const d = Math.hypot(x - e.x, z - e.z); if (d > e.r) continue;
    const back = e.year + (e.regrow ?? 20);
    if (year <= e.year + (e.down ?? 2)) { f = 0; continue; }
    // regrowth runs from the edge of the cleared area inward
    const k = (year - e.year - (e.down ?? 2)) / Math.max(1, back - e.year - (e.down ?? 2));
    const need = 1 - d / e.r;
    f = Math.min(f, Math.max(0, Math.min(1, (k - need) * 4)));
  }
  return f;
}

/** Where the standing city is in a year: its centre of mass and a radius holding ~85% of its houses. */
export function cityExtent(lots, need) {
  let sx = 0, sz = 0, n = 0;
  for (const l of lots) if (l.rank < need) { sx += l.x; sz += l.z; n++; }
  if (!n) return { x: 0, z: 0, r: 300, n: 0 };
  const cx = sx / n, cz = sz / n, ds = [];
  for (const l of lots) if (l.rank < need) ds.push(Math.hypot(l.x - cx, l.z - cz));
  ds.sort((a, b) => a - b);
  return { x: cx, z: cz, r: Math.max(220, ds[Math.floor(ds.length * 0.85)] || 0), n };
}

/** Trees on open land, each remembering the rank of the nearest lot, so it is cleared when the city reaches it. */
export function makeTrees(terrain, lots, { seed = 11, spacing = 19, max = 90000, density = 1 } = {}) {
  const R = rng(seed), out = [], B = 24, near = new Map();
  for (const l of lots) { const k = Math.floor(l.x / B) * 100003 + Math.floor(l.z / B); (near.get(k) || near.set(k, []).get(k)).push(l); }
  const lim = terrain.half - 5;
  for (let z = -lim; z < lim; z += spacing) {
    for (let x = -lim; x < lim; x += spacing) {
      const px = x + (R() - 0.5) * spacing, pz = z + (R() - 0.5) * spacing;
      const dens = noise2(px, pz, 300, seed);
      if (R() > (0.05 + dens * dens * 1.3) * density) continue;
      const y = terrain.heightAt(px, pz);
      if (y < 1.5 || terrain.slopeAt(px, pz, 8) > 0.7 || terrain.waterAt?.(px, pz)) continue;
      let rank = Infinity;
      const i = Math.floor(px / B), j = Math.floor(pz / B);
      for (let a = i - 1; a <= i + 1; a++) for (let b = j - 1; b <= j + 1; b++) {
        for (const l of near.get(a * 100003 + b) || []) if (l.rank < rank && Math.hypot(l.x - px, l.z - pz) < 22) rank = l.rank;
      }
      out.push({ x: px, z: pz, y, kind: dens > 0.62 ? 0 : R() < 0.25 ? 2 : R() < 0.5 ? 1 : 0, s: 0.75 + R() * 0.6, rank });
      if (out.length >= max) return out;
    }
  }
  return out;
}

/** Each street segment takes the rank of the first house along it: a street appears when its first house does. */
export function roadRanks(roads, lots) {
  const first = new Map();
  for (const l of lots) if (!first.has(l.road) || first.get(l.road) > l.rank) first.set(l.road, l.rank);
  return roads.map((_, i) => first.get(i) ?? Infinity);
}
