// Region geometry helpers (pure): true-scale moves for "same size as" comparisons,
// areas, point-in-polygon, bounding boxes.

const KM_PER_DEG = 111.132;

export function ringCentroid(ring) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [x0, y0] = ring[j], [x1, y1] = ring[i], f = x0 * y1 - x1 * y0;
    a += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f;
  }
  return Math.abs(a) < 1e-12 ? ring[0].slice() : [cx / (3 * a), cy / (3 * a)];
}

/** Area-weighted centre of a MultiPolygon (coordinates: polygons -> rings -> [lon, lat]). */
export function multiCentroid(polys) {
  let tw = 0, tx = 0, ty = 0;
  for (const p of polys) {
    const w = Math.abs(ringAreaDeg(p[0])) || 1e-9, [x, y] = ringCentroid(p[0]);
    tw += w; tx += x * w; ty += y * w;
  }
  return [tx / tw, ty / tw];
}

function ringAreaDeg(ring) {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
  return a / 2;
}

/** Ring area in km2 (spherical polygon, good for countries). */
export function ringAreaKm2(ring) {
  const R = 6371.0088, rad = Math.PI / 180;
  let s = 0;
  for (let i = 0; i < ring.length; i++) {
    const [lon1, lat1] = ring[i], [lon2, lat2] = ring[(i + 1) % ring.length];
    s += (lon2 - lon1) * rad * (2 + Math.sin(lat1 * rad) + Math.sin(lat2 * rad));
  }
  return Math.abs((s * R * R) / 2);
}

export function multiAreaKm2(polys) {
  return polys.reduce((acc, p) => acc + ringAreaKm2(p[0]) - p.slice(1).reduce((h, r) => h + ringAreaKm2(r), 0), 0);
}

/**
 * Move a MultiPolygon so its centre lands on `to`, keeping its true size: offsets are turned
 * into kilometres at the source and back into degrees at the destination, so a country moved
 * north or south is NOT stretched the way a plain lon/lat shift would stretch it on a Mercator map.
 */
export function moveShapeTrueScale(polys, to, from = multiCentroid(polys)) {
  const [lon0, lat0] = from;
  return polys.map((poly) => poly.map((ring) => ring.map(([lon, lat]) => {
    const dyKm = (lat - lat0) * KM_PER_DEG;
    const dxKm = (lon - lon0) * KM_PER_DEG * Math.cos((((lat + lat0) / 2) * Math.PI) / 180);
    const lat2 = to.lat + dyKm / KM_PER_DEG;
    const lon2 = to.lon + dxKm / (KM_PER_DEG * Math.cos((((lat2 + to.lat) / 2) * Math.PI) / 180));
    return [lon2, lat2];
  })));
}

export function bboxOfPolys(polys) {
  let w = 180, s = 90, e = -180, n = -90;
  for (const p of polys) for (const [x, y] of p[0]) { if (x < w) w = x; if (x > e) e = x; if (y < s) s = y; if (y > n) n = y; }
  return [w, s, e, n];
}

function inRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Point in a MultiPolygon, honouring holes. `boxes` (optional, from polyBoxes) skips far-away polygons fast. */
export function pointInPolys(x, y, polys, boxes = null) {
  for (let k = 0; k < polys.length; k++) {
    if (boxes) { const b = boxes[k]; if (x < b[0] || x > b[2] || y < b[1] || y > b[3]) continue; }
    const p = polys[k];
    if (!inRing(x, y, p[0])) continue;
    let hole = false;
    for (let h = 1; h < p.length && !hole; h++) if (inRing(x, y, p[h])) hole = true;
    if (!hole) return true;
  }
  return false;
}
export const polyBoxes = (polys) => polys.map((p) => bboxOfPolys([p]));

/** Drop far-flung islets and overseas territories: keep polygons with at least `share` of the biggest one's area. */
export function mainPolys(polys, share = 0.05) {
  const areas = polys.map((p) => ringAreaKm2(p[0])), top = Math.max(...areas);
  return polys.filter((_, i) => areas[i] >= top * share);
}
