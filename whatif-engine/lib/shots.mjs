// Shots: the video is a sequence of full-frame shots (hard cuts), each one of a few kinds; graphics layers run over them.
//   image   a still (Flow image, NASA photo) with a slow drift             { file, drift: { to: 1.04, fx, fy } }
//   video   a clip (Flow video, NASA film), cut to frames by cutter.mjs    { file, in_s, speed, loop }
//   plate   a dark diagram plate the diagram layers draw on                { tint: cool | warm | blue, title, sub }
//   craft   a 3D model (GLB) drifting in a star field                      { model, cam: { az0, az1, el, dist, roll } }
//   globe   a textured world with rim light                                { texture, cam, atmosphere, rotate_deg_s }
//   hero    a composed procedural 3D scene (lib/hero.mjs): a lander on the plain, a descent under a parachute, a ray-traced black hole { scene, cam }
//   black   black (a death, a silence)
// Every shot: { id, start, end, kind, credit?, exit?: "cut" | "push", grade?: {...} }. Pure functions of narration time t.
export const KINDS = ['image', 'video', 'plate', 'craft', 'globe', 'hero', 'product', 'black'];
export const HERO_SCENES = ['venera_ground', 'venera_descent', 'cloud_airship', 'ship_engine', 'blackhole_disc', 'blackhole_top', 'blackhole_ring', 'blackhole_lensing', 'blackhole_horizon',
  'ring_station', 'cylinder_interior', 'cylinder_exterior'];
const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };

export function validateShots(spec) {
  const problems = [], shots = spec.shots || [];
  if (!shots.length) problems.push('spec.shots is empty');
  let prev = 0;
  shots.forEach((s, i) => {
    if (!KINDS.includes(s.kind)) problems.push(`shot ${s.id || i}: unknown kind ${s.kind}`);
    if (!(s.end > s.start)) problems.push(`shot ${s.id || i}: end must be after start`);
    if (s.start < prev - 1e-6) problems.push(`shot ${s.id || i}: starts before the previous one ends`);
    if (['image', 'video'].includes(s.kind) && !s.file) problems.push(`shot ${s.id || i}: ${s.kind} needs a file`);
    if (s.kind === 'craft' && !s.model) problems.push(`shot ${s.id || i}: craft needs a model`);
    if (s.kind === 'globe' && !s.texture) problems.push(`shot ${s.id || i}: globe needs a texture`);
    if (s.kind === 'hero' && !HERO_SCENES.includes(s.scene)) problems.push(`shot ${s.id || i}: hero needs a scene (${HERO_SCENES.join(', ')})`);
    prev = s.end;
  });
  return problems;
}

/** Repair a spec's shots in place so the page never stops on them: -> notes. Unknown kinds and shots missing what they need become plates;
 *  a shot with no length is dropped; overlaps are trimmed; gaps are closed by the shot before; no shot at all -> one plate. */
export function sanitizeShots(spec) {
  const notes = [], out = [];
  for (const [i, s] of (spec.shots || []).entries()) {
    const id = s.id || `#${i}`;
    if (!Number.isFinite(s.start) || !Number.isFinite(s.end) || !(s.end > s.start)) { notes.push(`shot ${id}: no length; left out`); continue; }
    const why = !KINDS.includes(s.kind) ? `unknown kind ${s.kind}` : ['image', 'video'].includes(s.kind) && !s.file ? `${s.kind} without a file`
      : s.kind === 'craft' && !s.model ? 'craft without a model' : s.kind === 'globe' && !s.texture ? 'globe without a texture'
        : s.kind === 'hero' && !HERO_SCENES.includes(s.scene) ? `unknown hero scene ${s.scene}` : null;
    if (why) { notes.push(`shot ${id}: ${why}; drawn as a plate`); s.kind = 'plate'; }
    out.push(s);
  }
  out.sort((a, b) => a.start - b.start);
  for (let i = 1; i < out.length; i++) {
    if (out[i].start < out[i - 1].end) { out[i - 1].end = out[i].start; }
    else if (out[i].start > out[i - 1].end + 1e-6) out[i - 1].end = out[i].start;
  }
  const kept = out.filter((s) => s.end > s.start + 1e-6);
  if (!kept.length) { kept.push({ id: 'plate', start: 0, end: Math.max(1, spec.duration || 1), kind: 'plate' }); notes.push('no shot could be drawn; one plate for the whole video'); }
  if (kept[0].start > 0) kept[0].start = 0;
  if (spec.duration && kept[kept.length - 1].end < spec.duration) kept[kept.length - 1].end = spec.duration;
  spec.shots = kept;
  return notes;
}

export const shotAt = (shots, t) => {
  let lo = 0, hi = shots.length - 1, hit = null;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (t < shots[m].start) hi = m - 1; else if (t >= shots[m].end) lo = m + 1; else { hit = shots[m]; break; } }
  return hit || shots[shots.length - 1] || null;
};

/** The drift of a shot at t: scale 1 -> to over its length (linear, as the references: never fully still) and a pan towards (fx, fy). */
export function driftAt(s, t) {
  const d = s.drift || {}, k = clamp01((t - s.start) / Math.max(0.5, s.end - s.start));
  const to = d.to ?? 1.04, scale = (d.from ?? 1) + (to - (d.from ?? 1)) * k;
  // a shot that ends in a push into its subject (exit: "push") accelerates over its last 0.6 s
  const push = s.exit === 'push' ? smooth((t - (s.end - 0.6)) / 0.6) : 0;
  return { scale: scale * (1 + 0.32 * push), fx: d.fx ?? 0.5, fy: d.fy ?? 0.5, push };
}

/** Which video shots need frames cut, and from where (see cutter.mjs). */
export function videoShots(spec) {
  return (spec.shots || []).map((s, i) => ({ s, i })).filter(({ s }) => s.kind === 'video');
}
export function clipFrameIndex(s, t, fps) {
  const sp = s.speed || 1;
  return Math.max(0, Math.round((t - s.start) * sp * fps));
}
