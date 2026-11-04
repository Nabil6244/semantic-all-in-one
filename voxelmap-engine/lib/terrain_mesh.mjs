// Block terrain: per-cell block heights and colours, and chunk meshes (top faces plus the side walls where a neighbour is
// lower). Pure typed-array code: the page turns the arrays into three.js geometry, the tests count faces. The same code
// builds every level of detail: `k` blocks per world cell (1 for the world, 4 and 16 for detail tiles, see lib/lod.mjs).
//
// Vertex layout per chunk:
//   pos  Int16 x3   (x, y, z) in blocks
//   col  Uint8 x4   rgb + (face id 0..4 | water << 3 | material << 5)   face 0 top, 1 +x, 2 -x, 3 +z, 4 -z;
//                   water 1 sea, 2 shore, 3 river; material (MAT) picks the block texture the page's shader draws
//   top  Int16 x1   the block-top height of the column a face belongs to (walls: their top edge), for side textures
//   reg  Uint16 x1  region index (territory tint lookup)
//   sh   Uint8 x1   light: corner occlusion x baked sun shadow (255 = fully lit)
// Sea cells of one depth band along a row are merged into one top quad.

import { blockHeights } from './lod.mjs';

const hash = (x, z) => { let h = (x * 374761393 + z * 668265263) >>> 0; h = ((h ^ (h >>> 13)) * 1274126177) >>> 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const SEA = [[46, 120, 170], [36, 96, 152], [28, 74, 132], [20, 54, 108]];
export const MAT = { grass: 0, forest: 1, sand: 2, stone: 3, snow: 4, sea: 5, river: 6 };
export const SUN = [0.6, 0.55, 0.45]; // direction toward the sun, shared with the page's light: ~36 deg high, east-south-east

/**
 * Heights, colours and light for every cell of a grid. opts: { k: blocks per world cell, latOf(z): latitude of a row,
 * gx, gz: the grid's offset in global blocks (keeps the colour noise continuous across tiles) }. land: 0 sea, 1 land, 2 river.
 */
export function buildCells(elev, land, w, h, opts = {}) {
  const k = opts.k ?? 1, latOf = opts.latOf ?? ((z) => 25 - z * (20 / h)), gx = opts.gx ?? 0, gz = opts.gz ?? 0;
  const hgt = blockHeights(elev, land, w * h, k), col = new Uint8Array(w * h * 3), water = new Uint8Array(w * h), mat = new Uint8Array(w * h);
  for (let z = 0; z < h; z++) for (let x = 0; x < w; x++) {
    const i = z * w + x, e = elev[i], j = hash(x + gx, z + gz);
    const isLand = (v) => v === 1;
    let c;
    if (land[i] === 2) { c = [62, 128, 168]; water[i] = 3; mat[i] = MAT.river; hgt[i] = Math.max(1, hgt[i] - 1); }
    else if (!land[i]) {
      c = SEA[Math.min(3, Math.round(-hgt[i] / k))] || SEA[3];
      const shore = (x > 0 && land[i - 1]) || (x < w - 1 && land[i + 1]) || (z > 0 && land[i - w]) || (z < h - 1 && land[i + w]);
      water[i] = shore ? 2 : 1; mat[i] = MAT.sea;
    } else {
      const coast = (x > 0 && !isLand(land[i - 1])) || (x < w - 1 && !isLand(land[i + 1])) || (z > 0 && !isLand(land[i - w])) || (z < h - 1 && !isLand(land[i + w]));
      const lat = latOf(z);
      // forest patches are a few world cells wide at every level, so the pattern matches across levels
      const fx = Math.floor((x + gx) / (8 * k)), fz = Math.floor((z + gz) / (8 * k));
      const forest = hash(fx, fz) * 0.6 + hash(Math.floor((x + gx) / k), Math.floor((z + gz) / k)) * 0.4 > 0.55;
      if (coast && e < 25 && land[i] === 1) { c = [214, 196, 140]; mat[i] = MAT.sand; }
      else if (e > 2700 || (e > 2200 && lat > 22)) { c = [236, 240, 244]; mat[i] = MAT.snow; }
      else if (e > 1500) { c = [118, 118, 112]; mat[i] = MAT.stone; }
      else if (forest) { c = [52, 104, 46]; mat[i] = MAT.forest; }
      else { c = [86, 140, 58]; mat[i] = MAT.grass; }
    }
    const jit = land[i] === 1 ? 0.92 + j * 0.16 : 1; // sea stays flat: its cells are merged into long quads
    col[i * 3] = Math.min(255, c[0] * jit); col[i * 3 + 1] = Math.min(255, c[1] * jit); col[i * 3 + 2] = Math.min(255, c[2] * jit);
  }
  return { hgt, col, water, mat, shadow: sunShadow(hgt, w, h), k };
}

/** Baked sun shadow per cell (0 = shadowed, 1 = lit): march toward the sun over the height field. */
export function sunShadow(hgt, w, h, steps = 28) {
  const out = new Float32Array(w * h).fill(1);
  const len = Math.hypot(SUN[0], SUN[2]), dx = SUN[0] / len, dz = SUN[2] / len, rise = SUN[1] / len; // world space, the same vector the page lights with
  for (let z = 0; z < h; z++) for (let x = 0; x < w; x++) {
    const h0 = hgt[z * w + x];
    if (h0 <= 0) continue;
    for (let s = 1; s <= steps; s++) {
      const sx = Math.round(x + dx * s), sz = Math.round(z + dz * s);
      if (sx < 0 || sz < 0 || sx >= w || sz >= h) break;
      if (hgt[sz * w + sx] > h0 + rise * s) { out[z * w + x] = 0; break; }
    }
  }
  return out;
}

/** One chunk's mesh arrays for cells [x0, x1) x [z0, z1). edgeFloor: how deep the walls at the grid's edge go (skirts). */
export function buildChunk(cells, region, w, h, x0, z0, x1, z1, edgeFloor = -4) {
  const { hgt, col, water, shadow } = cells, mat = cells.mat || new Uint8Array(w * h);
  const pos = [], cf = [], rg = [], sh = [], tp = [], idx = [];
  let v = 0;
  const quad = (p, rgb, face, r, light, top) => {
    for (let q = 0; q < 4; q++) { pos.push(p[q * 3], p[q * 3 + 1], p[q * 3 + 2]); cf.push(rgb[0], rgb[1], rgb[2], face); rg.push(r); sh.push(light[q]); tp.push(top); }
    idx.push(v, v + 2, v + 1, v, v + 3, v + 2); v += 4;
  };
  const H = (x, z) => (x < 0 || z < 0 || x >= w || z >= h ? edgeFloor : hgt[z * w + x]);
  // corner occlusion for a top-face corner: neighbours (dx,0), (0,dz) and (dx,dz) higher than the cell
  const ao = (x, z, y, dx, dz) => {
    const s1 = H(x + dx, z) > y, s2 = H(x, z + dz) > y, c = H(x + dx, z + dz) > y;
    return s1 && s2 ? 0 : 3 - (s1 + s2 + c);
  };
  const AOL = [0.55, 0.7, 0.85, 1];
  for (let z = z0; z < z1; z++) {
    for (let x = x0; x < x1; x++) {
      const i = z * w + x, y = hgt[i], r = region[i], rgb = [col[i * 3], col[i * 3 + 1], col[i * 3 + 2]];
      if (water[i] === 1 || water[i] === 2) {
        // merge a run of sea cells with the same depth band and kind
        let x2 = x + 1;
        while (x2 < x1 && hgt[z * w + x2] === y && water[z * w + x2] === water[i]) x2++;
        quad([x, y, z, x2, y, z, x2, y, z + 1, x, y, z + 1], rgb, (water[i] << 3) | (mat[i] << 5), 0, [255, 255, 255, 255], y);
        for (let xs = x; xs < x2; xs++) sides(xs, z, y, 0);
        x = x2 - 1;
        continue;
      }
      const lit = 0.62 + 0.38 * shadow[i];
      const L = [ao(x, z, y, -1, -1), ao(x, z, y, 1, -1), ao(x, z, y, 1, 1), ao(x, z, y, -1, 1)].map((a) => Math.round(255 * AOL[a] * lit));
      quad([x, y, z, x + 1, y, z, x + 1, y, z + 1, x, y, z + 1], rgb, (water[i] << 3) | (mat[i] << 5), r, L, y);
      sides(x, z, y, r);
    }
  }
  function sides(x, z, y, r) {
    const i = z * w + x, base = [col[i * 3], col[i * 3 + 1], col[i * 3 + 2]];
    // the wall shows soil under a grass/forest top, stone under rock and snow
    const wall = water[i] ? base : (base[1] > base[0] + 20 ? [118, 86, 58] : [120, 120, 124]);
    const lit = 0.62 + 0.38 * shadow[i], top = Math.round(255 * 0.92 * lit);
    const n = [[x + 1, z, 1], [x - 1, z, 2], [x, z + 1, 3], [x, z - 1, 4]];
    for (const [nx, nz, face] of n) {
      const ny = H(nx, nz);
      if (ny >= y) continue;
      // walls darken toward their foot: a cheap contact shadow that sells the block depth
      const foot = Math.round(255 * Math.max(0.42, 0.92 - 0.12 * (y - ny)) * lit), L = [top, top, foot, foot], code = face | (water[i] << 3) | (mat[i] << 5);
      if (face === 1) quad([x + 1, y, z + 1, x + 1, y, z, x + 1, ny, z, x + 1, ny, z + 1], wall, code, r, L, y);
      if (face === 2) quad([x, y, z, x, y, z + 1, x, ny, z + 1, x, ny, z], wall, code, r, L, y);
      if (face === 3) quad([x, y, z + 1, x + 1, y, z + 1, x + 1, ny, z + 1, x, ny, z + 1], wall, code, r, L, y);
      if (face === 4) quad([x + 1, y, z, x, y, z, x, ny, z, x + 1, ny, z], wall, code, r, L, y);
    }
  }
  return { pos: Int16Array.from(pos), col: Uint8Array.from(cf), reg: Uint16Array.from(rg), sh: Uint8Array.from(sh), top: Int16Array.from(tp), index: Uint32Array.from(idx), quads: v / 4 };
}

/** Ground height (block top) under a world point on a level-0 grid, for the camera and for placing sets. */
export function heightAt(cells, w, h, x, z) {
  const xi = Math.max(0, Math.min(w - 1, Math.floor(x))), zi = Math.max(0, Math.min(h - 1, Math.floor(z)));
  return Math.max(0, cells.hgt[zi * w + xi]);
}
