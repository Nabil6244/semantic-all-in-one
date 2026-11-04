// Map projection for the tabletop map: equirectangular around the map's centre, x scaled by cos(latitude), so distances
// look right at the latitudes shown. MAP_W studs across the bbox's width.

export const MAP_W = 1000;

export function makeProj(bbox) {
  const [lon0, lat0, lon1, lat1] = bbox, cl = Math.cos(((lat0 + lat1) / 2) * Math.PI / 180);
  const cx = (lon0 + lon1) / 2, cy = (lat0 + lat1) / 2, k = MAP_W / ((lon1 - lon0) * cl || 1);
  return {
    bbox, k,
    toXZ: (lon, lat) => [(lon - cx) * cl * k, -(lat - cy) * k],
    toLonLat: (x, z) => [x / (cl * k) + cx, -z / k + cy],
    depth: (lat1 - lat0) * k,
  };
}

/** A bbox around points with a margin, widened to 16:9-ish so the map fills the frame. */
export function bboxAround(points, marginDeg = 1.2, minSpanDeg = 3) {
  const lons = points.map((p) => p[0]), lats = points.map((p) => p[1]);
  let lon0 = Math.min(...lons) - marginDeg, lon1 = Math.max(...lons) + marginDeg, lat0 = Math.min(...lats) - marginDeg, lat1 = Math.max(...lats) + marginDeg;
  const cl = Math.cos(((lat0 + lat1) / 2) * Math.PI / 180);
  const spanX = Math.max(minSpanDeg, (lon1 - lon0)), spanY = Math.max(minSpanDeg * 0.56 / cl, lat1 - lat0);
  const cx = (lon0 + lon1) / 2, cy = (lat0 + lat1) / 2;
  const wy = Math.max(spanY, spanX * cl * 0.62), wx = Math.max(spanX, wy / cl / 0.62);
  return [cx - wx / 2, cy - wy / 2, cx + wx / 2, cy + wy / 2];
}
