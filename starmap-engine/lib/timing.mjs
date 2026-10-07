// Narration-time visibility, shared by every layer. A layer is on screen from `start` to `end` (seconds of narration,
// never frame numbers), fading in over `fade_in` and out over `fade_out`. Everything is a pure function of t, so a layer
// that is interrupted (a footage beat covers the screen) shows exactly the right state when the map comes back.
//
//   { "start": 4, "end": 12, "fade_in": 0.6, "fade_out": 0.6 }      no start = from the beginning, no end = to the end
const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * (3 - 2 * k); };

export const DEFAULT_FADE = 0.5;

/** 0..1: how visible a timed thing is at narration time t. */
export function opacityAt(def, t) {
  const start = def.start ?? -Infinity, end = def.end ?? Infinity;
  if (t < start || t > end) return 0;
  const fi = def.fade_in ?? DEFAULT_FADE, fo = def.fade_out ?? DEFAULT_FADE;
  const a = Number.isFinite(start) && fi > 0 ? smooth((t - start) / fi) : 1;
  const b = Number.isFinite(end) && fo > 0 ? smooth((end - t) / fo) : 1;
  return Math.min(a, b);
}

/** 0..1 progress of a timed reveal { t0, t1 } (eased), for paths drawn on and numbers counting up. Animations run on MAP
 *  time: pass the footage plan's mu and a reveal that a footage beat interrupts pauses and resumes (mu = identity without
 *  footage). */
export function progressAt(r, t, mu = (x) => x) {
  if (!r) return 1;
  const a = mu(r.t0), b = mu(r.t1), m = mu(t);
  if (m <= a) return 0;
  if (m >= b) return 1;
  return smooth((m - a) / (b - a));
}

/** Piecewise-linear keys [{t, v}] -> value at t (held before the first key and after the last). */
export function keyed(keys, t) {
  if (!keys || !keys.length) return null;
  if (t <= keys[0].t) return keys[0].v;
  for (let i = 1; i < keys.length; i++) {
    const a = keys[i - 1], b = keys[i];
    if (t <= b.t) return b.t > a.t ? a.v + (b.v - a.v) * ((t - a.t) / (b.t - a.t)) : b.v;
  }
  return keys[keys.length - 1].v;
}
