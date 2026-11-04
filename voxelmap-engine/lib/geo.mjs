// lon/lat <-> block-world coordinates. One world unit = one terrain cell (meta.res degrees); x grows east, z grows south,
// y is block height. Pure; shared by the page, the timeline and the tests.

export const VSCALE_M = 420; // metres per block step on land (about 6.6x vertical exaggeration at 0.025 deg cells)

export function makeGeo(meta) {
  const [lon0, lat0, lon1, lat1] = meta.bbox;
  const res = meta.res;
  const kmPerCell = res * 111.32;
  return {
    w: meta.w, h: meta.h, res, kmPerCell, bbox: meta.bbox,
    toWorld: (lon, lat) => ({ x: (lon - lon0) / res, z: (lat1 - lat) / res }),
    toLonLat: (x, z) => ({ lon: lon0 + x * res, lat: lat1 - z * res }),
    inside: (lon, lat) => lon >= lon0 && lon <= lon1 && lat >= lat0 && lat <= lat1,
  };
}

/** Elevation (m) -> block top height. Land is always >= 1, sea floor steps down by depth, never below -4. */
export function blockHeight(elevM) {
  if (elevM > 0) return 1 + Math.floor(elevM / VSCALE_M);
  const d = -elevM;
  return d < 200 ? 0 : d < 1000 ? -1 : d < 3000 ? -2 : -3;
}

/** Great-circle distance in km. */
export function distanceKm(a, b) {
  const R = 6371, r = Math.PI / 180;
  const dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)));
}
