// Hybrid Map engine options. Pure functions (no browser) so they can be unit tested. Everything here is switched on by the
// spec/event flags below; a PakMap spec carries none of them, so PakMap output is untouched.
//
//   spec.hybrid.pause_overlays   while full-screen media is up, the clocks of the map layers stop (their entrance animations
//                                freeze mid-progress and resume on return); a layer's planned END stays in narration time
//   media_full.cover_ui          the footage is drawn over the cards, stat chips, captions and HUD (they dissolve with the map)
//   media_full.xfade_prev        this clip dissolves in over the previous clip (which stays opaque until then): no map flash
//   media_full.kenburns          a slow push-in on the clip over its time on screen
//   media_full.fit = 'slow'      a clip shorter than its slot plays slower (not below half speed) so it covers the slot; beyond that it plays
//                                forwards then backwards: it never jumps back to its first frame (a hard repeat)

/** Union of the time windows covered by full-screen media, sorted and merged. */
export function footageWindows(events) {
  const spans = (events || []).filter((e) => e.type === 'media_full').map((e) => [e.t_in, e.t_out]).sort((a, b) => a[0] - b[0]);
  const out = [];
  for (const [a, b] of spans) {
    if (out.length && a <= out[out.length - 1][1] + 1e-9) out[out.length - 1][1] = Math.max(out[out.length - 1][1], b);
    else out.push([a, b]);
  }
  return out;
}

/** Seconds of [a, b] that fall inside the windows. */
export function pausedSpan(windows, a, b) {
  let s = 0;
  for (const [x, y] of windows) s += Math.max(0, Math.min(b, y) - Math.max(a, x));
  return s;
}

/** The event as the map layers should see it at time t: its start moved later by the time spent under footage since it began,
 *  so every animation measured from t_in is frozen under footage. t_out is left alone (the planned lifecycle is narration time).
 *  With no windows (PakMap) the same object comes back. */
export function shiftedEvent(e, t, windows) {
  if (!windows || !windows.length || e.type === 'media_full') return e;
  const p = pausedSpan(windows, e.t_in, Math.min(t, e.t_out));
  return p > 0 ? { ...e, t_in: e.t_in + p } : e;
}

/** How opaque a full-screen clip is at t: linear dissolve in, linear dissolve out; a clip that the next one dissolves over stays opaque. */
export function footageAlpha(e, t, events, dissolve) {
  const d = e.dissolve_s ?? dissolve;
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  const aIn = clamp01((t - e.t_in) / d);
  const handedOver = (events || []).some((o) => o !== e && o.type === 'media_full' && o.xfade_prev === true && o.t_in >= e.t_in && o.t_in <= e.t_out + 1e-9);
  const aOut = handedOver ? 1 : clamp01((e.t_out - t) / d);
  return Math.min(aIn, aOut);
}

/** Scale for the slow push-in. 1 when the clip has no kenburns flag. */
export function kenBurnsScale(e, t) {
  if (!e.kenburns) return 1;
  const span = Math.max(1e-6, e.t_out - e.t_in);
  const k = Math.max(0, Math.min(1, (t - e.t_in) / span));
  return 1 + (e.kenburns_zoom ?? 0.06) * k;
}

/** The event to animate: kenburns "auto" means a still gets the push-in and a video does not (decided from the file actually fetched). */
export function resolveKenBurns(e, info) {
  return e.kenburns === 'auto' ? { ...e, kenburns: !!info && info.kind === 'image' } : e;
}

export const MIN_RATE = 0.5;

/** Playback rate for a clip with `avail` seconds of material in a slot of `slot` seconds: 1 when it is long enough, else slower, never below MIN_RATE. */
export function fitRate(avail, slot) {
  if (!(slot > 0) || avail >= slot) return 1;
  return Math.max(MIN_RATE, Math.max(0.001, avail) / slot);
}

/** Frame of a fitted clip: rate-adjusted, and ping-pong (forwards, backwards, forwards ...) when even the slowest rate runs out of frames. */
export function fitFrame(t, tIn, fps, count, rate) {
  if (count <= 1) return 0;
  const k = Math.max(0, Math.floor((t - tIn) * fps * rate + 1e-9));
  const period = 2 * (count - 1), m = k % period;
  return m < count ? m : period - m;
}
