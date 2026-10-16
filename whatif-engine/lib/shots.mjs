// Shots: the video is a sequence of full-frame shots (hard cuts), each one of a few kinds; graphics layers run over them.
//   image   a still (Flow image, NASA photo) with a slow drift             { file, drift: { to: 1.04, fx, fy } }
//   video   a clip (Flow video, NASA film), cut to frames by cutter.mjs    { file, in_s, speed, loop }
//   plate   a dark diagram plate the diagram layers draw on                { tint: cool | warm | blue, title, sub }
//   craft   a 3D model (GLB) drifting in a star field                      { model, cam: { az0, az1, el, dist, roll } }
//   globe   a textured world with rim light                                { texture, cam, atmosphere, rotate_deg_s }
//   hero    a composed procedural 3D scene (lib/hero.mjs): a lander on the plain, a descent under a parachute, a ray-traced black hole { scene, cam }
//   black   black (a death, a silence)
// Every shot: { id, start, end, kind, credit?, exit?: "cut" | "push", grade?: {...} }. Pure functions of narration time t.
export const KINDS = ['image', 'video', 'plate', 'craft', 'globe', 'hero', 'black'];
export const HERO_SCENES = ['venera_ground', 'venera_descent', 'cloud_airship', 'ship_engine', 'blackhole_disc', 'blackhole_top', 'blackhole_ring', 'blackhole_lensing', 'blackhole_horizon'];
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
