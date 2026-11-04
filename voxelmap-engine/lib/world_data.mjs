// World data in memory: the level-0 grid plus the story's detail tiles (raw elevation, land, region), and the height
// lookup built from them. The same code runs in Node (planning, clearance) and in the page (meshes, sets), so both agree
// on every ground height. Meshes are not built here; the page builds them on demand.

import { blockHeights, TILE_BLOCKS, LEVELS, tileKey } from './lod.mjs';

const N = TILE_BLOCKS * TILE_BLOCKS;

/** Split a tile file (int16 elevation, uint8 land, uint16 region) into typed arrays. */
export function parseTile(buf) {
  const u8 = new Uint8Array(buf);
  const elev = new Int16Array(u8.slice(0, N * 2).buffer), land = u8.slice(N * 2, N * 3), region = new Uint16Array(u8.slice(N * 3, N * 5).buffer);
  return { elev, land, region };
}

export function makeWorldData(meta, coarse, tiles = []) {
  const hgt = blockHeights(coarse.elev, coarse.land, meta.w * meta.h, 1);
  const data = { meta, coarse: { hgt, w: meta.w, h: meta.h, elev: coarse.elev, land: coarse.land, region: coarse.region }, tiles: new Map() };
  for (const t of tiles) addTile(data, t);
  return data;
}

export function addTile(data, t) {
  const L = LEVELS.find((x) => x.level === t.level);
  const raw = t.elev ? t : parseTile(t.buf);
  data.tiles.set(tileKey(t.level, t.tx, t.tz), { level: t.level, k: L.k, tx: t.tx, tz: t.tz, ...raw, hgt: blockHeights(raw.elev, raw.land, N, L.k) });
}
