// Footage beats: full-screen video clips (stock, NASA, Flow) and photographs between the map scenes -- one continuous
// documentary, the same idea as Hybrid Map (StarMap's own implementation). Pure: used by the page AND the Node renderer.
//
//   "footage": [ { "id": "launch", "start": 12, "end": 20, "file": "apollo11_launch.mp4",   video: .mp4 .mov .m4v .webm
//                  "in_s": 3.0, "speed": 1, "loop": false,                                  where in the clip to start
//                  "image": "launch.jpg", "ken_burns": { "from": [0.5, 0.5, 1], "to": [0.5, 0.45, 1.1] },   or a still
//                  "transition_in": "dissolve" | "cut", "transition_out": "dissolve" | "cut", "dissolve_s": 0.5,
//                  "credit": "NASA" } ]
//
// How the map survives footage (as in Hybrid Map):
//   * MAP TIME stops while footage is up: mu(t) = narration t minus the footage seconds before it. The universe clock, the
//     camera (moves and drift) and every layer animation run on map time, with their authored narration times converted
//     through mu -- so whatever was half done when the footage came is half done when the map returns, and carries on;
//     a camera move or a fast-forward that spans a beat pauses and resumes instead of jumping.
//   * a layer's START and END stay in narration time. A layer whose end falls under the footage (after the map is gone) is
//     held until the map returns plus return_grace_s, then leaves, so the viewer never loses a layer they did not see go; a
//     layer whose start falls under the footage appears when the map returns.
//   * transitions are dissolves centred on the beat boundary (so they do not eat the beat's own time); footage straight
//     after footage dissolves over the previous clip, never over the map.
const VIDEO = /\.(mp4|mov|m4v|webm|mkv)$/i, IMAGE = /\.(jpe?g|png|webp)$/i;
const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * (3 - 2 * k); };
export const DISSOLVE_S = 0.5, RETURN_GRACE_S = 0.8, MIN_BEAT_S = 2, SHORT_BEAT_S = 3.5;

/** spec -> the footage plan: { beats, problems, warnings, mu, coverage, mapAlpha, clipTime, adjustLayer, mapClock, mapCamera }. */
export function planFootage(spec = {}) {
  const problems = [], warnings = [];
  const raw = (spec.footage || []).map((b, i) => ({ ...b, i, id: b.id || `footage${i + 1}` }));
  const beats = raw.slice().sort((a, b) => a.start - b.start).map((b) => {
    const file = b.file || b.image;
    const kind = b.image ? 'image' : VIDEO.test(file || '') ? 'video' : IMAGE.test(file || '') ? 'image' : null;
    if (!file) problems.push(`footage ${b.id}: no clip or image`);
    else if (!kind) problems.push(`footage ${b.id}: unsupported file type "${file}" (video: mp4 mov m4v webm mkv; image: jpg png webp)`);
    if (!(Number.isFinite(b.start) && Number.isFinite(b.end) && b.end > b.start)) problems.push(`footage ${b.id}: needs start < end (narration seconds)`);
    else if (b.end - b.start < MIN_BEAT_S) problems.push(`footage ${b.id}: ${(b.end - b.start).toFixed(1)} s is too short (minimum ${MIN_BEAT_S} s)`);
    else if (b.end - b.start < SHORT_BEAT_S) warnings.push(`footage ${b.id}: only ${(b.end - b.start).toFixed(1)} s on screen`);
    for (const k of ['transition_in', 'transition_out']) if (b[k] && !['dissolve', 'cut'].includes(b[k])) problems.push(`footage ${b.id}: ${k} must be "dissolve" or "cut"`);
    const d = b.dissolve_s ?? spec.dissolve_s ?? DISSOLVE_S;
    return { ...b, file, kind, speed: b.speed || 1, in_s: b.in_s || 0, dIn: b.transition_in === 'cut' ? 0 : d, dOut: b.transition_out === 'cut' ? 0 : d };
  });
  for (let k = 1; k < beats.length; k++) {
    const a = beats[k - 1], b = beats[k];
    if (b.start < a.end - 1e-6) problems.push(`footage ${a.id} and ${b.id} overlap (${b.start} < ${a.end})`);
    if (Math.abs(b.start - a.end) < 1e-6) { a.nextAdjacent = b; b.prevAdjacent = a; }
  }
  for (const b of beats) {
    if (b.dIn > b.end - b.start || b.dOut > b.end - b.start) problems.push(`footage ${b.id}: the dissolve is longer than the beat`);
    // the stretch of narration this beat's pictures are needed for (its own dissolves; under the next clip's dissolve-in)
    b.t0 = b.start - b.dIn / 2;
    b.t1 = b.nextAdjacent ? b.end + b.nextAdjacent.dIn / 2 : b.end + b.dOut / 2;
  }
  // the map is frozen while any footage is up: merged [start, end] spans
  const spans = [];
  for (const b of beats) {
    const last = spans[spans.length - 1];
    if (last && b.start <= last.end + 1e-6) { last.end = Math.max(last.end, b.end); last.dOut = b.dOut; }
    else spans.push({ start: b.start, end: b.end, dIn: b.dIn, dOut: b.dOut });
  }
  const mu = (t) => { let m = t; for (const s of spans) m -= Math.max(0, Math.min(t, s.end) - s.start); return m; };

  /** How opaque a beat's pictures are at t (0..1). */
  const beatAlpha = (b, t) => {
    if (t < b.t0 || t > b.t1) return 0;
    const fin = b.dIn > 0 ? smooth((t - b.t0) / b.dIn) : (t >= b.start ? 1 : 0);
    if (b.nextAdjacent) return fin;                              // the next clip dissolves in over this one
    const fout = b.dOut > 0 ? smooth((b.t1 - t) / b.dOut) : (t < b.end ? 1 : 0);
    return Math.min(fin, fout);
  };
  /** The footage to draw at t, bottom to top: [{ beat, alpha }]. */
  const coverage = (t) => beats.map((b) => ({ beat: b, alpha: beatAlpha(b, t) })).filter((x) => x.alpha > 0);
  /** How much of the map shows through at t. */
  const mapAlpha = (t) => coverage(t).reduce((m, x) => m * (1 - x.alpha), 1);
  /** Seconds into the source clip for narration t (before looping/clamping, which depend on the clip's length). */
  const clipTime = (b, t) => b.in_s + (t - b.start) * b.speed;

  /** A layer's narration-time start/end, moved off the footage (see the header). Over-footage layers are untouched. */
  const adjustLayer = (def, grace = spec.return_grace_s ?? RETURN_GRACE_S) => {
    if (def.over_footage || !spans.length) return def;
    const out = { ...def };
    for (const s of spans) {
      const gone = s.start + s.dIn / 2;                         // the map is fully hidden from here
      if (out.end != null && out.end > gone && out.end <= s.end) out.end = s.end + s.dOut / 2 + grace;
      if (out.start != null && out.start > s.start && out.start < s.end) { out.start = s.end; out.fade_in = Math.max(out.fade_in ?? 0, s.dOut); }
    }
    return out;
  };
  /** Narration-time keys (clock, camera) -> map-time keys. */
  const mapClock = (clock = {}) => (clock.keys ? { ...clock, keys: clock.keys.map((k) => ({ ...k, t: mu(k.t) })) } : clock);
  // a camera move keeps its own length in map time: one that runs into footage pauses and finishes after the map returns
  // (shortened only if it would then run into the next move)
  const mapCamera = (cam = {}) => {
    const moves = (cam.moves || []).slice().sort((a, b) => a.t - b.t).map((m) => ({ ...m, t: mu(m.t), dur: m.dur ?? 4 }));
    for (let k = 0; k + 1 < moves.length; k++) if (moves[k].t + moves[k].dur > moves[k + 1].t) moves[k].dur = Math.max(0, moves[k + 1].t - moves[k].t);
    return { ...cam, moves };
  };
  // keys or moves authored under the footage are almost always a mistake: their effect happens at the map's return
  for (const s of spans) {
    for (const k of spec.clock?.keys || []) if (k.t > s.start && k.t < s.end) warnings.push(`clock key at ${k.t} s is under footage: the universe gets there when the map returns at ${s.end} s`);
    for (const m of spec.camera?.moves || []) if (m.t > s.start && m.t < s.end) warnings.push(`camera move at ${m.t} s starts under footage: it starts when the map returns at ${s.end} s`);
  }
  const cm = mapCamera(spec.camera), authored = (spec.camera?.moves || []).slice().sort((a, b) => a.t - b.t);
  cm.moves.forEach((m, k) => { if (m.dur < (authored[k].dur ?? 4) - 1e-6) warnings.push(`camera move at ${authored[k].t} s is cut short by footage (it pauses under the footage and the next move starts before it ends)`); });
  return { beats, spans, problems, warnings, mu, coverage, mapAlpha, clipTime, adjustLayer, mapClock, mapCamera };
}

/** What to cut from a video clip for a beat: frames at `rate` per clip-second from `fromS`, for `durS` clip-seconds
 *  (the beat plus its dissolves). The Node renderer extracts them; the page asks for frame k. */
export function extractPlan(b, fps) {
  const fromS = Math.max(0, b.in_s + (b.t0 - b.start) * b.speed);
  return { fromS, durS: (b.t1 - b.t0) * b.speed + 2 / fps, rate: fps / b.speed };
}

/** The extracted frame index for narration t (the server holds the last frame if the clip is shorter). */
export function clipFrameIndex(b, t, fps) {
  const { fromS, rate } = extractPlan(b, fps);
  return Math.max(0, Math.round((b.in_s + (t - b.start) * b.speed - fromS) * rate));
}

/** Ken Burns for a still: the crop at narration t (centre x, y as 0..1 of the image, zoom >= 1 over a cover fit). */
export function kenBurnsAt(b, t) {
  const kb = b.ken_burns || {}, from = kb.from || [0.5, 0.5, 1.0], to = kb.to || [0.5, 0.5, 1.08];
  const k = Math.min(1, Math.max(0, (t - b.t0) / Math.max(1e-6, b.t1 - b.t0)));     // a steady drift, no easing
  return from.map((v, i) => v + (to[i] - v) * k);
}
