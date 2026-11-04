// The block globe: the whole Earth as axis-aligned voxels on a 3D grid (a stepped sphere, like the reference's opening
// and ending), coloured from worlds/_globe (real elevation, Natural Earth land, a coarse surface class), with block
// clouds that drift around it. Pure: the page turns the arrays into instanced cubes; the tests check counts and colours.
//
// Units: one voxel = 1; the sphere's sea level has radius R voxels, so a voxel is 6371 / R km.

export const R = 140;
export const KM_PER_VOXEL = 6371 / R;
const hash = (a, b, c = 0) => { let h = (a * 374761393 + b * 668265263 + c * 2147483647) >>> 0; h = ((h ^ (h >>> 13)) * 1274126177) >>> 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const SURF = { 1: [96, 150, 62], 2: [44, 98, 42], 3: [218, 196, 138], 4: [120, 118, 110], 5: [238, 242, 246] };

/** Unit direction of a lon/lat (y up, +z at lon 0 lat 0 facing the camera's default). */
export function dirOf(lon, lat) {
  const a = (lon * Math.PI) / 180, b = (lat * Math.PI) / 180;
  return { x: Math.cos(b) * Math.sin(a), y: Math.sin(b), z: Math.cos(b) * Math.cos(a) };
}

/** -> { pos: Int16Array (x,y,z per voxel), col: Uint8Array (rgb per voxel), count }. */
export function buildGlobe(meta, height, land, surf) {
  const { w, h, res } = meta;
  const cells = new Map();
  const step = Math.min(res, (180 / Math.PI) / (R * 1.6)); // sample finer than a voxel so the shell has no holes
  const at = (lon, lat) => {
    const x = Math.min(w - 1, Math.max(0, Math.floor((lon + 180) / res))), y = Math.min(h - 1, Math.max(0, Math.floor((90 - lat) / res)));
    return y * w + x;
  };
  for (let lat = -90 + step / 2; lat < 90; lat += step) {
    const lonStep = step / Math.max(0.05, Math.cos((lat * Math.PI) / 180));
    for (let lon = -180; lon < 180; lon += lonStep) {
      const i = at(lon, lat), e = height[i], isLand = land[i] === 1;
      // land rises a block above the sea, mountains a few more (exaggerated, as the reference's globe)
      const top = isLand ? 1 + Math.min(4, Math.floor(Math.max(0, e) / 1100)) : 0;
      const d = dirOf(lon, lat);
      for (let r = -1; r <= top; r++) {
        const x = Math.round(d.x * (R + r)), y = Math.round(d.y * (R + r)), z = Math.round(d.z * (R + r));
        const key = (x + 512) * 1048576 + (y + 512) * 1024 + (z + 512);
        if (cells.has(key) && r < cells.get(key).r) continue;
        let c;
        if (!isLand) { const deep = Math.min(1, -e / 5000); c = [46 - deep * 24, 118 - deep * 56, 172 - deep * 50]; if (Math.abs(lat) > 76) c = [226, 234, 242]; }
        else c = SURF[surf[i]] || SURF[1];
        const j = 0.9 + hash(x, y, z) * 0.18;
        cells.set(key, { x, y, z, r, c: c.map((v) => Math.min(255, v * j)) });
      }
    }
  }
  const list = [...cells.values()];
  const pos = new Int16Array(list.length * 3), col = new Uint8Array(list.length * 3);
  list.forEach((v, k) => { pos.set([v.x, v.y, v.z], k * 3); col.set(v.c, k * 3); });
  return { pos, col, count: list.length };
}

/** Block clouds: puffy clusters a few voxels above the surface, as offsets from their centres. Deterministic. */
export function buildClouds(n = 46, seed = 7) {
  const out = [];
  for (let k = 0; k < n; k++) {
    const lon = hash(k, seed) * 360 - 180, lat = (hash(k, seed, 1) * 2 - 1) * 62, d = dirOf(lon, lat), size = 3 + Math.floor(hash(k, seed, 2) * 5);
    const c = { x: d.x * (R + 7), y: d.y * (R + 7), z: d.z * (R + 7) };
    for (let i = -size; i <= size; i++) for (let j = -size; j <= size; j++) for (let m = 0; m <= 1; m++) {
      if (i * i + j * j > size * size * (0.7 + hash(i + 50, j + 50, k) * 0.5)) continue;
      // a flat slab lying on the sphere: spread along two tangent axes
      const t1 = Math.abs(d.y) < 0.9 ? norm(cross(d, { x: 0, y: 1, z: 0 })) : { x: 1, y: 0, z: 0 }, t2 = cross(d, t1);
      out.push({ x: Math.round(c.x + t1.x * i + t2.x * j + d.x * m), y: Math.round(c.y + t1.y * i + t2.y * j + d.y * m), z: Math.round(c.z + t1.z * i + t2.z * j + d.z * m) });
    }
  }
  return out;
}
const cross = (a, b) => ({ x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x });
const norm = (a) => { const l = Math.hypot(a.x, a.y, a.z) || 1; return { x: a.x / l, y: a.y / l, z: a.z / l }; };

/** Camera on the globe for a camera state (lon, lat, alt km, heading): above the point, looking at the planet's centre. */
export function placeGlobeCamera(c) {
  const d = dirOf(c.lon, c.lat), dist = R + c.alt / KM_PER_VOXEL;
  const north = norm({ x: -Math.sin((c.lat * Math.PI) / 180) * Math.sin((c.lon * Math.PI) / 180), y: Math.cos((c.lat * Math.PI) / 180), z: -Math.sin((c.lat * Math.PI) / 180) * Math.cos((c.lon * Math.PI) / 180) });
  const east = cross(north, d), hd = ((c.heading ?? 0) * Math.PI) / 180;
  const up = { x: north.x * Math.cos(hd) + east.x * Math.sin(hd), y: north.y * Math.cos(hd) + east.y * Math.sin(hd), z: north.z * Math.cos(hd) + east.z * Math.sin(hd) };
  return { pos: { x: d.x * dist, y: d.y * dist, z: d.z * dist }, up, near: Math.max(0.5, (dist - R) * 0.2), far: dist + R * 2 };
}

/** How much of a frame the globe takes (1 = globe only, 0 = the flat world only), from the camera's altitude in km. */
export function globeWeight(altKm, lo = 2600, hi = 3800) {
  const k = Math.max(0, Math.min(1, (altKm - lo) / (hi - lo)));
  return k * k * (3 - 2 * k);
}
