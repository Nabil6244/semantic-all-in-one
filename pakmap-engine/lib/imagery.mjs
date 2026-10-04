// pakMap imagery: a replaceable provider interface + SCALE-based selection.
//
//   camera scale (metres per screen pixel) -> which imagery layers show -> render
//
// There is deliberately no "country = this source / close-up = that source"
// rule anywhere. A provider only declares what it IS (its finest native
// resolution); the selection works out which layers a given scale needs. A
// better free source can therefore be registered later without touching the
// camera, the timeline, the CSV or the renderer.
//
// Browser-safe (no node imports): shared by the renderer page and the tests.

export const EQUATOR_M_PER_PX_Z0 = 156543.03392; // 256 px tiles at zoom 0 (GIBS "GoogleMapsCompatible")

const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best';
export const GIBS_ACK =
  "We acknowledge the use of imagery provided by services from NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information System (ESDIS).";

/** Provider records. Pure data: swap or add entries, nothing else changes. */
export const PROVIDERS = {
  nasa_bluemarble_bathymetry: {
    id: 'nasa_bluemarble_bathymetry',
    title: 'NASA Blue Marble with Bathymetry',
    urlTemplate: `${GIBS}/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`,
    format: 'jpeg',
    tileSize: 256,
    maxNativeZoom: 8,
    blackIsNodata: false,
    historical: false,
    attribution: GIBS_ACK,
    licenceStatus: 'verify exact terms for this GIBS layer before distribution',
  },
  nasa_landsat_weld_2000: {
    id: 'nasa_landsat_weld_2000',
    title: 'NASA Landsat WELD annual composite (year 2000)',
    urlTemplate: `${GIBS}/Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual/default/2000-12-01/GoogleMapsCompatible_Level12/{z}/{y}/{x}.jpeg`,
    format: 'jpeg',
    tileSize: 256,
    maxNativeZoom: 12,
    blackIsNodata: true, // composite has black holes (offshore, gaps): treated as transparent
    historical: true,
    vintage: '1998-2000 era',
    attribution: GIBS_ACK,
    honesty: 'Historical Landsat imagery (about the year 2000), not current satellite imagery.',
    licenceStatus: 'verify exact terms for this GIBS layer before distribution',
  },
};

export const DEFAULT_IMAGERY = {
  // coarse -> fine. The first is the base (always visible); each later one fades in
  // only once the one before it would have to be stretched too far.
  providers: ['nasa_bluemarble_bathymetry', 'nasa_landsat_weld_2000'],
  max_upsample: 2.0, // how many times a layer may be stretched before the next finer one starts to appear
  crossfade_octaves: 0.75, // fade length, in zoom levels
  soft_limit_frame_km: 25, // draft constant from the Phase 0 look test; configurable, never a hard stop
  grade: { saturation: -0.1, contrast: 0.06, brightness_min: 0.0, brightness_max: 0.94, hue_rotate: 0 },
  ocean_lift: null, // optional colour (e.g. '#0a2b3b') blended with 'lighten' to lift near-black sea; off by default because it also tints dark land and the space behind the globe
};

export function resolveProviders(config = DEFAULT_IMAGERY, registry = PROVIDERS) {
  const ids = config.providers || DEFAULT_IMAGERY.providers;
  if (!ids.length) throw new Error('imagery.providers must name at least one provider');
  const list = ids.map((id) => {
    const p = typeof id === 'string' ? registry[id] : id; // a full provider object is accepted too
    if (!p) throw new Error(`unknown imagery provider: ${id}`);
    return { ...p, nativeMPerPx: EQUATOR_M_PER_PX_Z0 / Math.pow(2, p.maxNativeZoom) };
  });
  for (let i = 1; i < list.length; i++) {
    if (list[i].nativeMPerPx >= list[i - 1].nativeMPerPx) {
      throw new Error(`imagery.providers must go from coarse to fine: ${list[i].id} (${list[i].nativeMPerPx.toFixed(1)} m/px) is not finer than ${list[i - 1].id}`);
    }
  }
  return list;
}

/**
 * Which layers should be visible, and how strongly, for a camera whose screen
 * pixels each cover `mPerPx` metres on the ground at the equator-equivalent
 * scale (pass the latitude-corrected value from camera.metersPerPixel; imagery
 * resolution shrinks with cos(latitude) too, so use `nativeAtLat`).
 */
export function selectLayers(list, mPerPx, lat, config = DEFAULT_IMAGERY) {
  const cosLat = Math.max(0.05, Math.cos((lat * Math.PI) / 180));
  const maxUp = config.max_upsample ?? DEFAULT_IMAGERY.max_upsample;
  const fade = Math.max(0.01, config.crossfade_octaves ?? DEFAULT_IMAGERY.crossfade_octaves);
  const out = list.map((p, i) => ({ id: p.id, opacity: i === 0 ? 1 : 0 }));
  for (let i = 1; i < list.length; i++) {
    const prevNative = list[i - 1].nativeMPerPx * cosLat;
    // How far the coarser layer is stretched on screen: native m/px over the shot's m/px.
    // Zoomed in far enough that it exceeds max_upsample, the finer layer fades in.
    const overStretch = Math.log2(prevNative / (maxUp * mPerPx)); // octaves past the tolerance (<=0 = fine)
    out[i].opacity = Math.max(0, Math.min(1, overStretch / fade));
  }
  return out;
}

/** Warnings worth showing to the author (not errors): frame narrower than the soft limit while
 *  the finest provider is already carrying the shot. */
export function softnessWarning(list, mPerPx, lat, frameKm, config = DEFAULT_IMAGERY) {
  const limit = config.soft_limit_frame_km ?? DEFAULT_IMAGERY.soft_limit_frame_km;
  const finest = list[list.length - 1];
  const cosLat = Math.max(0.05, Math.cos((lat * Math.PI) / 180));
  const upscale = (finest.nativeMPerPx * cosLat) / mPerPx; // >1 = even the finest layer is being stretched
  return frameKm < limit && upscale > 1 ? { frameKm, limit, provider: finest.id, upscale } : null;
}

/** Credits that must travel with the output (video description / end card). */
export function creditsFor(list, usedIds) {
  const used = list.filter((p) => !usedIds || usedIds.has(p.id));
  const lines = [...new Set(used.map((p) => p.attribution).filter(Boolean))];
  const notes = used.filter((p) => p.honesty).map((p) => p.honesty);
  return { attribution: lines, notes, licence_status: used.map((p) => ({ provider: p.id, status: p.licenceStatus || 'unknown' })) };
}
