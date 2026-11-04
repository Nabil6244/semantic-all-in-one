// Human-scale dioramas: under every ground scene a patch of terrain rebuilt at ~4 m per block from the real elevation,
// coastlines and rivers (the reference's ground scenes are human scale: a block is about a person's width). The camera's
// last stage of a descent lands in it; the coarser terrain under it is cut away by the same dither as the detail levels.
// Pure: the page meshes `cells` with buildChunk; scene recipes stand on `ground()`.

import { sampleElevation, sampleLand, sampleHeight } from './lod.mjs';
import { sunShadow } from './terrain_mesh.mjs';
import { MAT } from './terrain_mesh.mjs';

export const DIO = 640;        // diorama blocks per world cell (~4.3 m each at 0.025 deg cells)
export const SET_N = 240;      // the scene recipe's own square, in blocks (~1 km)
export const MARGIN = 40;      // terrain around it, in blocks, so the edges sit in the haze
export const V_STEP_M = 2.5;   // metres of real elevation per block step (a mild 1.7x vertical exaggeration)

const hash = (x, z) => { let h = (x * 374761393 + z * 668265263) >>> 0; h = ((h ^ (h >>> 13)) * 1274126177) >>> 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
function vnoise(x, z, s) { // smooth value noise, scale s blocks
  const X = x / s, Z = z / s, x0 = Math.floor(X), z0 = Math.floor(Z), u = X - x0, v = Z - z0, f = (t) => t * t * (3 - 2 * t);
  const a = hash(x0, z0), b = hash(x0 + 1, z0), c = hash(x0, z0 + 1), d = hash(x0 + 1, z0 + 1);
  return (a * (1 - f(u)) + b * f(u)) * (1 - f(v)) + (c * (1 - f(u)) + d * f(u)) * f(v);
}

/** Build the diorama for a scene centred on world point (cx, cz) (cells). opts (for the coarser outer ring): units =
 *  blocks per cell across the ground, n/margin = size in those blocks, eRef/meshY = share the inner diorama's heights. */
export function buildDiorama(data, cx, cz, seed = 1, opts = {}) {
  const U = opts.units ?? DIO, n = opts.n ?? SET_N, M = opts.margin ?? MARGIN, N = n + 2 * M, x0 = cx - N / 2 / U, z0 = cz - N / 2 / U;
  const elev = new Float32Array(N * N), land = new Uint8Array(N * N);
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const x = x0 + (i + 0.5) / U, z = z0 + (j + 0.5) / U;
    elev[j * N + i] = sampleElevation(data, x, z); land[j * N + i] = sampleLand(data, x, z);
  }
  // heights count up from the low land of the patch (its 5th percentile), so a coast sits one block above the sea and
  // inland relief is unchanged; the outer ring shares the inner diorama's reference
  let eRef = opts.eRef;
  if (eRef == null) {
    const ls = []; for (let k = 0; k < N * N; k += 7) if (land[k] === 1) ls.push(elev[k]);
    ls.sort((x, y) => x - y);
    eRef = ls.length ? ls[Math.floor(ls.length * 0.05)] : elev[(N >> 1) * N + (N >> 1)];
  }
  const hgt = new Int16Array(N * N), col = new Uint8Array(N * N * 3), water = new Uint8Array(N * N), mat = new Uint8Array(N * N);
  for (let k = 0; k < N * N; k++) hgt[k] = land[k] ? Math.max(1, 1 + Math.floor(Math.max(0, elev[k] - eRef) / V_STEP_M)) : 0;
  // shores slope: land near water rises one block per two blocks inland (the source data is too coarse for a beach)
  {
    const dist = new Int16Array(N * N).fill(99), q = [];
    for (let k = 0; k < N * N; k++) if (land[k] !== 1) { dist[k] = 0; q.push(k); }
    for (let h = 0; h < q.length; h++) {
      const k = q[h], i = k % N, j = (k / N) | 0, d = dist[k] + 1;
      if (d > 12) continue;
      for (const kk of [i > 0 ? k - 1 : -1, i < N - 1 ? k + 1 : -1, j > 0 ? k - N : -1, j < N - 1 ? k + N : -1]) if (kk >= 0 && dist[kk] > d) { dist[kk] = d; q.push(kk); }
    }
    for (let k = 0; k < N * N; k++) if (land[k] === 1 && dist[k] <= 12) hgt[k] = Math.min(hgt[k], 1 + (dist[k] >> 1));
  }
  const gx = Math.round(cx * U), gz = Math.round(cz * U), sx = seed % 997, ns = U / DIO; // noise scales follow the block size
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const k = j * N + i, jit = 0.92 + hash(i + gx, j + gz) * 0.16;
    let c;
    const nb = (di, dj) => { const ii = Math.min(N - 1, Math.max(0, i + di)), jj = Math.min(N - 1, Math.max(0, j + dj)); return ii === i && jj === j ? k : jj * N + ii; };
    const nearWater = [nb(1, 0), nb(-1, 0), nb(0, 1), nb(0, -1), nb(2, 0), nb(-2, 0), nb(0, 2), nb(0, -2)].some((q) => land[q] !== 1);
    if (land[k] === 0) {
      const d = -Math.min(elev[k], -1);
      c = d < 6 ? [62, 140, 178] : d < 30 ? [46, 118, 168] : [32, 92, 148];
      water[k] = nearWater && [nb(1, 0), nb(-1, 0), nb(0, 1), nb(0, -1)].some((q) => land[q] === 1) ? 2 : 1; mat[k] = MAT.sea;
    } else if (land[k] === 2) {
      // a river: one block below the banks around it, flat water
      let bank = hgt[k];
      for (const q of [nb(1, 0), nb(-1, 0), nb(0, 1), nb(0, -1)]) if (land[q] === 1) bank = Math.min(bank, hgt[q]);
      hgt[k] = Math.max(1, bank - 1); c = [62, 128, 168]; water[k] = 3; mat[k] = MAT.river;
    } else {
      const slope = Math.max(Math.abs(hgt[nb(1, 0)] - hgt[nb(-1, 0)]), Math.abs(hgt[nb(0, 1)] - hgt[nb(0, -1)]));
      const forest = vnoise(i + gx + sx, j + gz, 46 * ns) * 0.7 + vnoise(i + gx, j + gz + sx, 11 * ns) * 0.3 > 0.56;
      if (nearWater && elev[k] < 12) { c = [214, 196, 140]; mat[k] = MAT.sand; }
      else if (slope >= 4 || elev[k] > 2700) { c = elev[k] > 2700 ? [236, 240, 244] : [118, 118, 112]; mat[k] = elev[k] > 2700 ? MAT.snow : MAT.stone; }
      else if (forest) { c = [52, 104, 46]; mat[k] = MAT.forest; }
      else { c = [86, 140, 58]; mat[k] = MAT.grass; }
    }
    const jj = land[k] === 1 ? jit : 1;
    col[k * 3] = Math.min(255, c[0] * jj); col[k * 3 + 1] = Math.min(255, c[1] * jj); col[k * 3 + 2] = Math.min(255, c[2] * jj);
  }
  const cells = { hgt, col, water, mat, shadow: sunShadow(hgt, N, N, 40), k: DIO };
  const hc = hgt[(N >> 1) * N + (N >> 1)];
  // the world height the diorama's centre block sits at: the detail level's ground there, so the hand-over does not jump
  const baseY = sampleHeight(data, cx, cz), meshY = opts.meshY ?? baseY - hc / DIO; // heights are in DIO steps at every size
  let minH = 1e9; for (let k = 0; k < N * N; k++) minH = Math.min(minH, hgt[k]);
  const idx = (fx, fz) => { const i = Math.min(N - 1, Math.max(0, Math.floor(fx + M))), j = Math.min(N - 1, Math.max(0, Math.floor(fz + M))); return j * N + i; };
  return {
    N, n, M, x0, z0, meshY, eRef, units: U, cells, edgeFloor: minH - 24,
    rect: [x0, z0, x0 + N / U, z0 + N / U],
    /** set coordinates (0..n) -> the ground a scene recipe stands on */
    ground: (fx, fz) => { const k = idx(fx, fz); return { y: hgt[k], water: water[k], forest: mat[k] === MAT.forest, color: [col[k * 3], col[k * 3 + 1], col[k * 3 + 2]] }; },
    /** world point -> world height of the diorama's surface there (null outside it) */
    heightAt: (x, z) => {
      const fi = (x - x0) * U, fj = (z - z0) * U;
      if (fi < 0 || fj < 0 || fi >= N || fj >= N) return null;
      return meshY + Math.max(0, hgt[Math.floor(fj) * N + Math.floor(fi)]) / DIO;
    },
    toWorld: (fx, fy, fz) => ({ x: x0 + (fx + M) / U, y: meshY + fy / DIO, z: z0 + (fz + M) / U }),
  };
}

/** How much the diorama has taken over (0 above 3 km, 1 below 1.5 km), from the camera altitude in km. */
export function dioramaWeight(altKm, lo = 1.5, hi = 3) {
  const k = Math.max(0, Math.min(1, (hi - altKm) / (hi - lo)));
  return k * k * (3 - 2 * k);
}
