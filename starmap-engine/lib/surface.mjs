// Surface shapes on any body, as lon/lat outlines (degrees, body-fixed). Pure.
//   { "circle": { "lon": 23.47, "lat": 0.67, "radius_km": 60 } }       a landing zone, a crater, a blast radius
//   { "polygon": [[lon, lat], ...] }                                     a mare, a region, a country (one outer ring)
// Later: GeoJSON rings (lunar maria, Mars regions, countries) load into the same polygon form.
import { greatCircle } from './paths.mjs';

export function regionOutline(geometry, bodyRadiusKm, steps = 96) {
  if (geometry.circle) {
    const { lon, lat, radius_km: r } = geometry.circle;
    const arc = (r / bodyRadiusKm) * (180 / Math.PI);
    return Array.from({ length: steps }, (_, i) => greatCircle(lon, lat, (360 * i) / steps, arc));
  }
  if (Array.isArray(geometry.polygon)) {
    const ring = geometry.polygon.map(([lo, la]) => [lo, la]);
    const [a, b] = [ring[0], ring[ring.length - 1]];
    if (a[0] === b[0] && a[1] === b[1]) ring.pop();                    // drop a closing duplicate
    if (ring.length < 3) throw new Error('a region polygon needs at least three points');
    return ring;
  }
  throw new Error('region geometry needs "circle" or "polygon"');
}

/** The ring's centre (mean direction), for labels. */
export function regionCentre(ring) {
  const R = Math.PI / 180;
  let x = 0, y = 0, z = 0;
  for (const [lo, la] of ring) { x += Math.cos(la * R) * Math.cos(lo * R); y += Math.cos(la * R) * Math.sin(lo * R); z += Math.sin(la * R); }
  return [Math.atan2(y, x) / R, Math.atan2(z, Math.hypot(x, y)) / R];
}
