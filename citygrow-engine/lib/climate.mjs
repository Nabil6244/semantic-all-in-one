// Which look the land has: desert cities (Dubai, Riyadh, Doha...) must not be drawn as green meadows.
// The story can say it ("climate":"arid" or "temperate" in the plan row's extra); without that it follows the city centre.

export const CLIMATES = {
  temperate: { grassA: 0x7f9f52, grassB: 0x9aae5e, dry: 0xb6ad78, rock: 0x9b9583, sand: 0xd8c99a, trees: [0x4f7a3a, 0x5d8a40, 0x3f6b35, 0x6c9447, 0x587d3c], treeDensity: 1 },
  // dry land: sand and tan, bare rock, a few grey-olive trees (date palms, ghaf, acacia) instead of woods
  arid: { grassA: 0xd6bb83, grassB: 0xe0c98f, dry: 0xcaa874, rock: 0xa8977c, sand: 0xe6d6a8, trees: [0x6f7f45, 0x7d8a4e, 0x5f7040, 0x8a9455, 0x6b7a47], treeDensity: 0.12 },
};

const ALIASES = { arid: 'arid', desert: 'arid', dry: 'arid', temperate: 'temperate', green: 'temperate', lush: 'temperate' };

/** [lon, lat] boxes whose cities stand in desert: the Arabian Peninsula and the Gulf coast, Sahara belt, Thar/Sindh coast excluded on purpose. */
const ARID_BOXES = [[36, 14, 60.5, 31], [-17, 18, 25, 31.5]];

export function climateOf(plan = {}, meta = {}) {
  const said = ALIASES[String(plan.climate || '').toLowerCase().trim()];
  if (said) return said;
  const c = plan.center || meta.center;
  // the story gives { lon, lat }; the world's meta.json gives [lon, lat]
  const lonLat = Array.isArray(c) ? [c[0], c[1]] : c && typeof c === 'object' ? [c.lon, c.lat] : null;
  if (lonLat) {
    const [lon, lat] = [Number(lonLat[0]), Number(lonLat[1])];
    if (Number.isFinite(lon) && Number.isFinite(lat) && ARID_BOXES.some(([w, s, e, n]) => lon >= w && lon <= e && lat >= s && lat <= n)) return 'arid';
  }
  return 'temperate';
}

/** The land-use class raster (tools/build_real.py): 1024 x 1024 bytes over the whole world, north edge first. */
export const LAND = { n: 1024, none: 0, built: 1, green: 2, dry: 3, wet: 4 };

export function landClassAt(cls, half, x, z) {
  if (!cls) return 0;
  const i = Math.floor(((x + half) / (2 * half)) * LAND.n), j = Math.floor(((z + half) / (2 * half)) * LAND.n);
  if (i < 0 || j < 0 || i >= LAND.n || j >= LAND.n) return 0;
  return cls[j * LAND.n + i];
}

/** How many trees a land-use class gets next to the climate's own density: woods and parks fill up, desert and bare ground stay empty. */
export function treeFactor(cls, climateDensity) {
  switch (cls) {
    case LAND.green: return Math.max(1, climateDensity * 3);
    case LAND.built: return Math.max(0.3, climateDensity * 0.8);
    case LAND.dry: return 0.04;
    case LAND.wet: return 0.15;
    default: return climateDensity;   // not mapped: the climate decides
  }
}
