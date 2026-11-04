// Territory states: which regions carry which faction tint, from simple rules over the world's regions (provinces).
// A state = { key, date, legend: [{label, color}], rules: [{iso: [..], lat_min?, lat_max?, color, strength?}] }.
// Rules are applied in order; a later rule wins. Pure: the page turns the result into a TINT_SIZE-entry tint texture.

export const TINT_SIZE = 2048; // regions a world may have (provinces in its bounding box)
export const hexRgb = (h) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

/** -> Uint8Array(TINT_SIZE*4): rgb + strength (0..255) per region index. Region 0 (sea / none) is never tinted. */
export function tintTable(regions, state) {
  const out = new Uint8Array(TINT_SIZE * 4);
  if (!state) return out;
  for (const r of regions) {
    if (r.i <= 0 || r.i >= TINT_SIZE) continue;
    for (const rule of state.rules || []) {
      if (rule.polygon) continue; // drawn front lines are painted by the page's mask, not per province
      if (rule.iso && !rule.iso.includes(r.iso)) continue;
      if (rule.lat_min != null && r.lat < rule.lat_min) continue;
      if (rule.lat_max != null && r.lat >= rule.lat_max) continue;
      if (rule.names && !rule.names.includes(r.name)) continue;
      const [cr, cg, cb] = hexRgb(rule.color);
      out.set([cr, cg, cb, Math.round(255 * (rule.strength ?? 0.72))], r.i * 4);
    }
  }
  return out;
}

/** Blend two tint tables (k 0..1) for a soft change between months. */
export function blendTables(a, b, k) {
  const out = new Uint8Array(a.length);
  for (let i = 0; i < a.length; i += 4) {
    // a region that gains or loses a tint keeps its colour and fades the strength
    const sa = a[i + 3], sb = b[i + 3];
    for (let c = 0; c < 3; c++) out[i + c] = sa === 0 ? b[i + c] : sb === 0 ? a[i + c] : Math.round(a[i + c] + (b[i + c] - a[i + c]) * k);
    out[i + 3] = Math.round(sa + (sb - sa) * k);
  }
  return out;
}

/** Regions past TINT_SIZE cannot be tinted individually; report them so a world build can be checked. */
export function untintable(regions) { return regions.filter((r) => r.i >= TINT_SIZE).length; }
