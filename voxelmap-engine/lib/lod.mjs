// Terrain levels of detail. Pure; shared by the page (which builds meshes), render.mjs (which plans which detail tiles a
// story needs, and the camera's terrain clearance) and the tests.
//
//   L0  the whole world, one block per cell (0.025 deg, ~2.8 km)                  always drawn
//   L1  tiles of 40x40 cells at 4 blocks per cell (~700 m), 160x160 blocks each   within L1_NEAR cells of the camera
//   L2  tiles of 10x10 cells at 16 blocks per cell (~175 m), 160x160 blocks each  within L2_NEAR cells of the camera
//
// Distances are measured from the camera to the nearest point of a tile, in cells. A tile fades in over a band
// (FADE_BAND x its distance) with a screen-door dither, and its parent level is cut away under it by the same dither,
// so a level change is a soft cross-fade and nothing is drawn twice. Tile edges carry walls down below sea level
// (skirts), so a level boundary never shows a crack.

import { VSCALE_M } from './geo.mjs';

export const LEVELS = [
  { level: 1, k: 4, tileCells: 40, zoom: 9, near: 50 },
  { level: 2, k: 16, tileCells: 10, zoom: 10, near: 12 },
];
export const TILE_BLOCKS = 160;
/** The world block size the level zooms above are set for (deg); a coarser world downloads coarser elevation. */
export const BASE_RES = 0.025;

/**
 * Terrarium zoom a detail level downloads for a world of `worldRes` degrees per cell: the level's zoom, one step
 * coarser per doubling of the world's block size over BASE_RES (finer pixels would be thrown away when sampled
 * down to that block size). Mirrored in tools/build_detail.py detail_zoom().
 */
export function detailZoom(level, worldRes) {
  const L = LEVELS.find((x) => x.level === level);
  const shift = Math.max(0, Math.floor(Math.log2((worldRes || BASE_RES) / BASE_RES) + 1e-9));
  return Math.max(1, L.zoom - shift);
}
export const FADE_BAND = 1.3;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (a, b, v) => { const k = clamp((v - a) / (b - a), 0, 1); return k * k * (3 - 2 * k); };

export const tileKey = (level, tx, tz) => `L${level}_${tx}_${tz}`;

/** Block heights for a grid at k blocks per cell (k = 1 for the world). Land >= 1 block; sea steps down by depth. */
export function blockHeights(elev, land, n, k = 1) {
  const out = new Int16Array(n), step = VSCALE_M / k;
  for (let i = 0; i < n; i++) {
    const e = elev[i];
    if (land[i]) out[i] = Math.max(1, 1 + Math.floor(Math.max(0, e) / step));
    else { const d = -Math.min(e, -1); out[i] = -k * (d < 200 ? 0 : d < 1000 ? 1 : d < 3000 ? 2 : 3); }
  }
  return out;
}

/** Distance (cells) from a camera position to the nearest point of a tile rectangle at ground level. */
export function tileDistance(cam, x0, z0, size) {
  const dx = Math.max(x0 - cam.x, 0, cam.x - (x0 + size)), dz = Math.max(z0 - cam.z, 0, cam.z - (z0 + size));
  return Math.hypot(dx, dz, Math.max(0, cam.y));
}

/** Tiles each level wants for a camera position, with their fade (0..1). worldW/H in cells. */
export function wantedTiles(cam, worldW, worldH, margin = 1) {
  const out = [];
  for (const L of LEVELS) {
    const reach = L.near * FADE_BAND * margin;
    if (cam.y > reach) continue;
    const r = Math.sqrt(Math.max(0, reach * reach - cam.y * cam.y));
    const tx0 = Math.max(0, Math.floor((cam.x - r) / L.tileCells)), tx1 = Math.min(Math.ceil(worldW / L.tileCells) - 1, Math.floor((cam.x + r) / L.tileCells));
    const tz0 = Math.max(0, Math.floor((cam.z - r) / L.tileCells)), tz1 = Math.min(Math.ceil(worldH / L.tileCells) - 1, Math.floor((cam.z + r) / L.tileCells));
    for (let tz = tz0; tz <= tz1; tz++) for (let tx = tx0; tx <= tx1; tx++) {
      const d = tileDistance(cam, tx * L.tileCells, tz * L.tileCells, L.tileCells);
      if (d > reach) continue;
      out.push({ level: L.level, tx, tz, key: tileKey(L.level, tx, tz), fade: 1 - smooth(L.near, L.near * FADE_BAND, d / margin), d });
    }
  }
  return out;
}

/** A finer tile only shows where its parent level is present: an L2 tile needs its L1 parent tile active. */
export function parentKey(level, tx, tz) {
  if (level !== 2) return null;
  const r = LEVELS[0].tileCells / LEVELS[1].tileCells;
  return tileKey(1, Math.floor(tx / r), Math.floor(tz / r));
}

/**
 * Ground height (world units = cells) at a world point from the finest data available. `data` = { coarse: {hgt, w, h},
 * tiles: Map(key -> {level, k, tx, tz, hgt}) }. Pure; the same answer in Node and in the page.
 */
export function sampleHeight(data, x, z) {
  for (let li = LEVELS.length - 1; li >= 0; li--) {
    const L = LEVELS[li];
    const tx = Math.floor(x / L.tileCells), tz = Math.floor(z / L.tileCells), t = data.tiles.get(tileKey(L.level, tx, tz));
    if (!t) continue;
    const bx = clamp(Math.floor((x - tx * L.tileCells) * L.k), 0, TILE_BLOCKS - 1), bz = clamp(Math.floor((z - tz * L.tileCells) * L.k), 0, TILE_BLOCKS - 1);
    return Math.max(0, t.hgt[bz * TILE_BLOCKS + bx]) / L.k;
  }
  const c = data.coarse, xi = clamp(Math.floor(x), 0, c.w - 1), zi = clamp(Math.floor(z), 0, c.h - 1);
  return Math.max(0, c.hgt[zi * c.w + xi]);
}

/** Highest ground within `r` cells of a point (9 samples), for clearance. */
export function maxHeightNear(data, x, z, r) {
  let m = 0;
  for (let dz = -1; dz <= 1; dz++) for (let dx = -1; dx <= 1; dx++) m = Math.max(m, sampleHeight(data, x + dx * r, z + dz * r));
  return m;
}

/** Elevation in metres at a world point, bilinear over the finest raw data available (for human-scale dioramas, which
 *  need smooth real relief rather than block steps). */
export function sampleElevation(data, x, z) {
  for (let li = LEVELS.length - 1; li >= 0; li--) {
    const L = LEVELS[li], tx = Math.floor(x / L.tileCells), tz = Math.floor(z / L.tileCells), t = data.tiles.get(tileKey(L.level, tx, tz));
    if (!t) continue;
    return bilinear(t.elev, TILE_BLOCKS, TILE_BLOCKS, (x - tx * L.tileCells) * L.k - 0.5, (z - tz * L.tileCells) * L.k - 0.5);
  }
  const c = data.coarse;
  return bilinear(c.elev, c.w, c.h, x - 0.5, z - 0.5);
}
/** Land flag (0 sea, 1 land, 2 river) at a world point from the finest data available. */
export function sampleLand(data, x, z) {
  for (let li = LEVELS.length - 1; li >= 0; li--) {
    const L = LEVELS[li], tx = Math.floor(x / L.tileCells), tz = Math.floor(z / L.tileCells), t = data.tiles.get(tileKey(L.level, tx, tz));
    if (!t) continue;
    const bx = clamp(Math.floor((x - tx * L.tileCells) * L.k), 0, TILE_BLOCKS - 1), bz = clamp(Math.floor((z - tz * L.tileCells) * L.k), 0, TILE_BLOCKS - 1);
    return t.land[bz * TILE_BLOCKS + bx];
  }
  const c = data.coarse, xi = clamp(Math.floor(x), 0, c.w - 1), zi = clamp(Math.floor(z), 0, c.h - 1);
  return c.land ? c.land[zi * c.w + xi] : 1;
}
function bilinear(a, w, h, fx, fz) {
  const x0 = clamp(Math.floor(fx), 0, w - 1), z0 = clamp(Math.floor(fz), 0, h - 1), x1 = Math.min(w - 1, x0 + 1), z1 = Math.min(h - 1, z0 + 1);
  const u = clamp(fx - x0, 0, 1), v = clamp(fz - z0, 0, 1);
  return (a[z0 * w + x0] * (1 - u) + a[z0 * w + x1] * u) * (1 - v) + (a[z1 * w + x0] * (1 - u) + a[z1 * w + x1] * u) * v;
}
