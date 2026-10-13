// Timed tile layers (spec.weather.rasters): a radar or satellite LOOP is a list of frames, each one picture (a tile provider),
// shown from `at` seconds into the layer and, with crossfade_s, blended into the next. Pure (no map, no canvas): the page sets
// MapLibre opacities from it, the overlay draws the frame's clock chip from it, and the tests check it.
import { clamp01 } from '../../pakmap-engine/lib/anim.mjs';

/** {index, mix}: the frame showing at narration time t (mix = how far the NEXT frame has faded in, 0..1). index -1 = none yet. */
export function frameAt(r, t) {
  const frames = r.frames || [];
  if (!frames.length) return { index: -1, mix: 0 };
  const lt = t - r.t_in;
  let i = -1;
  for (let k = 0; k < frames.length; k++) if (frames[k].at <= lt + 1e-9) i = k;
  if (i < 0) return { index: 0, mix: 0 };   // before the first frame's time: hold the first picture
  const next = frames[i + 1], xf = r.crossfade_s || 0;
  const mix = next && xf > 0 ? clamp01((lt - (next.at - xf)) / xf) : 0;
  return { index: i, mix };
}

/** Every tile provider the rasters use (served by the renderer like the base imagery). */
export function rasterProviders(spec) {
  return ((spec.weather && spec.weather.rasters) || []).flatMap((r) => (r.frames || []).map((f) => f.provider));
}

/** Problems with the rasters, each naming the layer. */
export function validateRasters(rasters, duration) {
  const errors = [], ids = new Set();
  (rasters || []).forEach((r, i) => {
    const at = `weather.rasters[${i}]${r.id ? ` (${r.id})` : ''}`;
    if (!r.id) errors.push(`${at}: needs an id`); else if (ids.has(r.id)) errors.push(`${at}: duplicate id`); ids.add(r.id);
    if (!(Number.isFinite(r.t_in) && Number.isFinite(r.t_out) && r.t_out > r.t_in)) errors.push(`${at}: needs numeric t_in < t_out`);
    else if (r.t_out > duration + 1e-9) errors.push(`${at}: ends after the video`);
    if (!Array.isArray(r.frames) || !r.frames.length) { errors.push(`${at}: needs at least one frame`); return; }
    r.frames.forEach((f, k) => {
      if (!f.provider || !f.provider.id || !f.provider.urlTemplate) errors.push(`${at}: frame ${k} needs a provider with id and urlTemplate`);
      if (!Number.isFinite(f.at) || (k && f.at < r.frames[k - 1].at)) errors.push(`${at}: frame ${k} needs an "at" time, in order`);
    });
  });
  return errors;
}
