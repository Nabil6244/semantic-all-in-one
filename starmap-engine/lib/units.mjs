// Units across every scale StarMap draws: a surface (km), the Earth-Moon system, the solar system (AU), the stars and
// galaxies (light-years). Internally every distance is kilometres in a 64-bit float.

export const KM_PER_AU = 149_597_870.7;
export const KM_PER_LY = 9_460_730_472_580.8;
export const KM_PER_PC = 30_856_775_814_913.67;

const group = (n) => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const sig = (n, d = 2) => (n >= 100 ? group(n) : n >= 10 ? n.toFixed(1).replace(/\.0$/, '') : n.toFixed(d).replace(/\.?0+$/, ''));

/** The distance in the unit a documentary would say it in: "384,400 KM", "54.6 MILLION KM", "5.2 AU", "26,000 LIGHT-YEARS". */
export function formatDistance(km) {
  const a = Math.abs(km);
  if (a < 1e6) return `${group(a)} KM`;
  if (a < 1.5 * KM_PER_AU) return `${sig(a / 1e6, 1)} MILLION KM`;   // planet distances are said in millions of km
  if (a < 0.05 * KM_PER_LY) return `${sig(a / KM_PER_AU, 1)} AU`;
  if (a < 1e6 * KM_PER_LY) return `${sig(a / KM_PER_LY, 1)} LIGHT-YEARS`;
  return `${sig(a / KM_PER_LY / 1e6, 1)} MILLION LIGHT-YEARS`;
}

/** A value with its unit in a spec ({"km": 1}, {"au": 5.2}, {"ly": 26000}, or a plain number = km) -> km. */
export function toKm(v) {
  if (typeof v === 'number') return v;
  if (v == null) return 0;
  if (v.km != null) return v.km;
  if (v.au != null) return v.au * KM_PER_AU;
  if (v.ly != null) return v.ly * KM_PER_LY;
  if (v.pc != null) return v.pc * KM_PER_PC;
  throw new Error(`unknown distance ${JSON.stringify(v)}`);
}
