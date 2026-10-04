// Polyline helpers for the line-draw engine (pure).

export function cumulative(points) {
  const d = [0];
  for (let i = 1; i < points.length; i++) d.push(d[i - 1] + Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]));
  return d;
}

/** The first `progress` (0..1) of the polyline's length, as a new point list plus the head direction. */
export function trimPolyline(points, progress) {
  if (points.length < 2 || progress <= 0) return { points: points.length ? [points[0]] : [], angle: 0 };
  if (progress >= 1) {
    const a = points[points.length - 2], b = points[points.length - 1];
    return { points: points.slice(), angle: Math.atan2(b[1] - a[1], b[0] - a[0]) };
  }
  const cum = cumulative(points), target = cum[cum.length - 1] * progress;
  const out = [points[0]];
  for (let i = 1; i < points.length; i++) {
    if (cum[i] < target) { out.push(points[i]); continue; }
    const seg = cum[i] - cum[i - 1] || 1, k = (target - cum[i - 1]) / seg;
    const a = points[i - 1], b = points[i];
    out.push([a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]);
    return { points: out, angle: Math.atan2(b[1] - a[1], b[0] - a[0]) };
  }
  return { points: out, angle: 0 };
}

/** Axis-aligned overlap test for chip rects {x,y,w,h}. */
export function overlaps(a, b, pad = 0) {
  return a.x < b.x + b.w + pad && a.x + a.w + pad > b.x && a.y < b.y + b.h + pad && a.y + a.h + pad > b.y;
}
