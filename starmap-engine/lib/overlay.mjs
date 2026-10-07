// Drawing things that live in space on the 2D overlay: camera-depth tests, a segment cut at the camera plane, a screen line
// cut to the frame, and a point at an offset in a body's own axes. Shared by the line, ring, pointer and galaxy layers.
export const KM_PER_LY = 9.4607e12;

/** Camera-space z of a camera-relative point (negative = in front). */
export function viewZ(f, p) {
  const e = f.camera.matrixWorldInverse.elements;
  return e[2] * p[0] + e[6] * p[1] + e[10] * p[2] + e[14];
}

/** The part of segment a-b (camera-relative km) in front of the camera, or null when all of it is behind. */
export function frontPart(f, a, b) {
  const za = viewZ(f, a), zb = viewZ(f, b), near = -1e-6 * Math.max(Math.abs(za), Math.abs(zb), 1);
  if (za >= near && zb >= near) return null;
  const cut = (p, q, zp, zq) => { const s = (near - zp) / (zq - zp); return p.map((v, i) => v + (q[i] - v) * s); };
  if (za >= near) return [cut(a, b, za, zb), b];
  if (zb >= near) return [a, cut(b, a, zb, za)];
  return [a, b];
}

/** A screen segment cut to the frame (inset by pad px): [[x, y], [x, y]] or null (Liang-Barsky). */
export function clipToFrame(A, B, W, H, pad = 0) {
  let t0 = 0, t1 = 1;
  const dx = B[0] - A[0], dy = B[1] - A[1];
  const edges = [[-dx, A[0] - pad], [dx, W - pad - A[0]], [-dy, A[1] - pad], [dy, H - pad - A[1]]];
  for (const [p, q] of edges) {
    if (p === 0) { if (q < 0) return null; continue; }
    const r = q / p;
    if (p < 0) { if (r > t1) return null; if (r > t0) t0 = r; } else { if (r < t0) return null; if (r < t1) t1 = r; }
  }
  return [[A[0] + dx * t0, A[1] + dy * t0], [A[0] + dx * t1, A[1] + dy * t1]];
}

/** A point given in a body's own axes (x right, z towards the image bottom for a galaxy), in light-years -> camera-relative km. */
export function inBodyAxes(f, id, xLy, zLy, yLy = 0) {
  const B = f.world.orientation(id), v = [xLy, yLy, zLy].map((c) => c * KM_PER_LY);
  return f.toCam(id, [0, 1, 2].map((i) => B.x[i] * v[0] + B.y[i] * v[1] + B.z[i] * v[2]));
}

/** The plane a body's things lie in: a galaxy's disk, else the ecliptic (the planets' plane), as a unit normal. */
export const ECLIPTIC_NORTH = [0, 0.917482, 0.397777];      // engine axes (J2000 equatorial, y = celestial north)
export function planeNormal(f, id, plane) {
  if (Array.isArray(plane)) return plane;
  const n = f.world.get(id);
  if (plane === 'galactic' || (!plane && n && n.kind === 'galaxy')) return f.world.orientation(n && n.kind === 'galaxy' ? id : 'milkyway').y;
  return ECLIPTIC_NORTH;
}

/** A label chip on a navy plate (yellow or white text), centred on (cx, cy), placed clear of other chips. */
export function plate(f, cx, cy, text, { px = 20, fg = '#FBE040' } = {}) {
  const { u, g } = f, w = u.measure(text, px) + 26 * u.S, h = (px + 18) * u.S;
  const at = f.placeAny([cx - w / 2], cy - h / 2, w, h);
  u.shadow(10, 0.5); u.box(at.x, at.y, w, h, 8, 'rgba(8,19,32,0.92)'); u.noShadow();
  g.font = u.font(px); g.fillStyle = fg; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, at.x + w / 2, at.y + h / 2 + 1 * u.S); g.textAlign = 'left';
  return at;
}
