// Where a render may be cut into separately drawn pieces (segments), so pieces can be drawn at the same time and a piece
// whose inputs did not change can be reused from the last render. Pure functions (no browser).
//
// Every frame is a function of its time, with two exceptions in draw.mjs, both remembered the first time a layer is drawn:
// a map-anchored card (pip without `at`, filmstrip) keeps the geo point under its first position, and a marker with an
// automatic label side keeps the side it first picked. A cut between frames s-1 and s is safe when no such layer is on
// screen on both sides of it: then whichever renderer draws the layer draws all of it, from its first frame, exactly as one
// render does. Cuts at safe frames are all this module gives out, so the joined pieces are the frames one render makes.

const EPS = 1e-9;

/** True for the layers whose look depends on the first frame they were drawn in. */
export function remembersFirstFrame(e) {
  if (e.type === 'pip') return !e.at;
  if (e.type === 'filmstrip') return true;
  if (e.type === 'marker') return e.dot !== false && !(e.side && e.side !== 'auto');
  return false;
}

/** First frame i with i/fps >= t (the frame test activeAt uses: t >= t_in). */
export function firstFrameAt(t, fps) {
  let i = Math.max(0, Math.ceil(t * fps - 1e-6));
  while (i > 0 && (i - 1) / fps >= t) i--;
  while (i / fps < t) i++;
  return i;
}

/** [first, end) frames on which the event is live (t_in <= i/fps < t_out). */
export function liveFrames(e, fps) {
  return [firstFrameAt(e.t_in, fps), firstFrameAt(e.t_out, fps)];
}

/** Sorted frame numbers s (0 < s < total) where a cut between s-1 and s is safe. */
export function safeCuts(events, total, fps) {
  const blocked = new Uint8Array(total + 1);
  for (const e of events || []) {
    if (!remembersFirstFrame(e)) continue;
    const [a, b] = liveFrames(e, fps);
    for (let s = Math.max(1, a + 1); s < Math.min(total, b); s++) blocked[s] = 1;   // live on frame s-1 and on frame s
  }
  const out = [];
  for (let s = 1; s < total; s++) if (!blocked[s]) out.push(s);
  return out;
}

const VIDEO_EXT = /\.(mp4|mov|m4v|webm|mkv|avi)$/i;

/**
 * Per-frame drawing cost: 0.1 for a frame that is only one full-screen video clip (the renderer sends the clip frame
 * straight to the encoder, lib/footage_pass.mjs), 1 for every other frame. An estimate, used only to share the work out.
 */
export function frameCosts(spec, total) {
  const fps = spec.fps, cost = new Float32Array(total).fill(1);
  if (!spec.hybrid) return cost;
  const fulls = (spec.events || []).filter((e) => e.type === 'media_full');
  for (const e of fulls) {
    if (e.cover_ui !== true || !VIDEO_EXT.test(String(e.media || ''))) continue;
    const d = e.dissolve_s ?? 0.5;
    const [a, b] = liveFrames({ t_in: e.t_in + d, t_out: e.t_out - d }, fps);
    for (let i = Math.max(0, a); i < Math.min(total, b); i++) cost[i] = 0.1;
  }
  return cost;
}

/**
 * The video cut into segments of about `targetS` seconds, every cut at a safe frame. Depends only on the timings of the
 * layers that remember their first frame, so changing a picture or a clip leaves the segments (and so the reusable ones)
 * where they were. A last piece shorter than `minS` joins the one before it.
 */
export function planSegments(events, total, fps, { targetS = 30, minS = 10 } = {}) {
  const cuts = safeCuts(events, total, fps), target = Math.round(targetS * fps), min = Math.round(minS * fps);
  const edges = [0];
  for (const s of cuts) {
    if (s - edges[edges.length - 1] >= target && total - s >= min) edges.push(s);
  }
  edges.push(total);
  return edges.slice(1).map((b, k) => ({ from: edges[k], to: b }));
}

/** The events a segment's frames can depend on: live at some frame of [from, to), plus every full-screen clip (their
 *  windows pause the other layers' clocks and set the dissolves). Used for the segment's reuse key. */
export function segmentEvents(events, seg, fps) {
  const t0 = seg.from / fps - EPS, t1 = (seg.to - 1) / fps + EPS;
  return (events || []).filter((e) => e.type === 'media_full' || (e.t_in <= t1 && e.t_out > t0));
}
