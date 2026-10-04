// Deterministic point sets for dot-density and cluster layers (pure).
import { rng } from './anim.mjs';

/** n points inside bbox [west, south, east, north], pulled toward weighted hotspots. */
export function generatePoints({ bbox, n, seed = 1, hotspots = [], uniform = 0.25 }) {
  const r = rng(seed), [w, s, e, nn] = bbox, out = [];
  const total = hotspots.reduce((a, h) => a + (h.weight ?? 1), 0);
  const gauss = () => { const u = Math.max(1e-9, r()), v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  for (let i = 0; i < n; i++) {
    if (!hotspots.length || r() < uniform) { out.push([w + r() * (e - w), s + r() * (nn - s)]); continue; }
    let pick = r() * total, h = hotspots[0];
    for (const c of hotspots) { pick -= c.weight ?? 1; if (pick <= 0) { h = c; break; } }
    const sp = h.spread ?? 1;
    const lon = Math.min(e, Math.max(w, h.lon + gauss() * sp)), lat = Math.min(nn, Math.max(s, h.lat + gauss() * sp * 0.8));
    out.push([lon, lat]);
  }
  return out;
}

/** Parse "lat,lon" or "lon,lat" CSV text (header row allowed) into [lon, lat] pairs. */
export function parsePointsCsv(text, order = 'lat,lon') {
  const rows = String(text).split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const out = [];
  for (const row of rows) {
    const [a, b] = row.split(/[;,\t]/).map((v) => Number(v));
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue; // header or junk row
    out.push(order === 'lat,lon' ? [b, a] : [a, b]);
  }
  return out;
}

/**
 * Dot positions from populated places (an approximation of where people live):
 * each place gets population/1e6 * perMillion dots (at least `minPerPlace`), scattered around it
 * with a spread that grows with city size. Deterministic. `accept(lon, lat)` can drop dots
 * (for example those that fall outside the chosen country).
 */
export function placesToDots(places, { perMillion = 60, minPerPlace = 1, maxDots = 6000, seed = 1, accept = null } = {}) {
  const r = rng(seed), out = [];
  const gauss = () => { const u = Math.max(1e-9, r()), v = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
  const sorted = [...places].sort((a, b) => b[2] - a[2]);
  for (const [lon, lat, pop] of sorted) {
    const n = Math.max(minPerPlace, Math.round((pop / 1e6) * perMillion));
    const spreadKm = Math.max(3, 4 + 9 * Math.log10(Math.max(pop, 1e4) / 1e4)); // ~4 km for a village, ~35 km for a big city
    const dLat = spreadKm / 111.132, dLon = spreadKm / (111.132 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
    for (let i = 0; i < n && out.length < maxDots; i++) {
      const p = [lon + gauss() * dLon, lat + gauss() * dLat];
      if (!accept || accept(p[0], p[1])) out.push(p);
    }
    if (out.length >= maxDots) break;
  }
  return out;
}
