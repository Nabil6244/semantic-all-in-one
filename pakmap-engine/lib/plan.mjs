// Node-side pre-flight for a render: validate the spec, resolve imagery, and walk
// the whole camera path once (cheap, no browser) to find out which imagery is
// used, how wide the narrowest frame gets, and where the shot is softer than the
// configured soft limit. Shared with the tests.
import { createCamera, frameWidthKm, metersPerPixel } from './camera.mjs';
import { validateEvents, validateWatermark, freezeWindows } from './events.mjs';
import { DEFAULT_IMAGERY, resolveProviders, selectLayers, softnessWarning, creditsFor } from './imagery.mjs';

export function planRender(spec, registry) {
  const { width, height, fps, duration } = spec;
  if (![width, height, fps, duration].every((v) => Number.isFinite(v) && v > 0)) throw new Error('spec needs positive width, height, fps and duration');
  const imagery = { ...DEFAULT_IMAGERY, ...(spec.imagery || {}) };
  const providers = resolveProviders(imagery, registry);
  const camera = createCamera({ camera: spec.camera, width, height, duration, freeze: freezeWindows(spec.events) });
  const total = Math.max(1, Math.round(duration * fps));
  const timeline = validateEvents(spec.events || [], duration);
  const wmErrors = validateWatermark(spec.watermark);
  if (wmErrors.length) throw new Error(wmErrors.join('; '));
  if (timeline.errors.length) throw new Error(`overlay timeline: ${timeline.errors.join('; ')}`);
  const used = new Set([providers[0].id]);
  let minKm = Infinity, minAt = 0;
  const soft = [];
  let open = null;
  for (let i = 0; i < total; i++) {
    const t = i / fps, c = camera.at(t);
    const mpp = metersPerPixel(c.lat, c.zoom), km = frameWidthKm(c.lat, c.zoom, width);
    if (km < minKm) { minKm = km; minAt = t; }
    selectLayers(providers, mpp, c.lat, imagery).forEach((l) => { if (l.opacity > 0) used.add(l.id); });
    const w = softnessWarning(providers, mpp, c.lat, km, imagery);
    if (w && !open) { open = { from: t, to: t, minFrameKm: km, provider: w.provider, upscale: w.upscale }; soft.push(open); }
    else if (w && open) { open.to = t; open.minFrameKm = Math.min(open.minFrameKm, km); open.upscale = Math.max(open.upscale, w.upscale); }
    else open = null;
  }
  const warnings = timeline.warnings.map((message) => ({ kind: 'timeline', message })).concat(soft.map((s) => ({
    kind: 'soft_imagery',
    message: `Frame is narrower than the ${imagery.soft_limit_frame_km} km soft limit from ${s.from.toFixed(1)}s to ${s.to.toFixed(1)}s (down to ${s.minFrameKm.toFixed(1)} km): ${s.provider} is stretched about ${s.upscale.toFixed(1)}x, so the picture will look soft.`,
    ...s,
  })));
  return { imagery, providers, camera, total, used, minFrameKm: minKm, minFrameAt: minAt, warnings, credits: creditsFor(providers, used) };
}
