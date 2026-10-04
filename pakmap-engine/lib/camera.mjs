// pakMap camera: ONE continuous top-down camera for the whole video.
//
//   base path   : piecewise  hold -> move -> hold -> move ...  (fly_to / push_in / pull_back)
//   idle drift  : always on, added on top, integrated so position never jumps
//   output      : { lon, lat, zoom } for any t -- pure and deterministic
//
// Browser-safe on purpose (no node imports): the renderer page and the tests
// run this exact file. Spec: docs/pakmap/pakmap-editing-spec.md section 5 / 16.5.

const TILE = 512; // MapLibre world size at zoom z is TILE * 2^z px
const RHO = 1.42; // van Wijk & Nuij fly-to curvature (same default as MapLibre's flyTo)
const DRIFT_STEP = 1 / 120;
const MAX_LAT = 85.0511;

export const clamp01 = (v) => Math.max(0, Math.min(1, v));
export const easings = {
  linear: (t) => t,
  in: (t) => t * t * t,
  out: (t) => 1 - Math.pow(1 - t, 3),
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
};

export function lonLatToWorld(lon, lat) {
  const s = Math.sin((Math.max(-MAX_LAT, Math.min(MAX_LAT, lat)) * Math.PI) / 180);
  return [(lon + 180) / 360, 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)];
}

export function worldToLonLat(x, y) {
  const n = Math.PI - 2 * Math.PI * y;
  return [x * 360 - 180, (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)))];
}

/** Metres per screen pixel at a latitude/zoom (MapLibre zoom, 512 px world tile). */
export function metersPerPixel(lat, zoom) {
  return (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (TILE * Math.pow(2, zoom));
}

export function frameWidthKm(lat, zoom, widthPx) {
  return (metersPerPixel(lat, zoom) * widthPx) / 1000;
}

const sinh = (n) => (Math.exp(n) - Math.exp(-n)) / 2;
const cosh = (n) => (Math.exp(n) + Math.exp(-n)) / 2;
const tanh = (n) => { const a = Math.exp(n), b = Math.exp(-n); return a === Infinity ? 1 : b === Infinity ? -1 : (a - b) / (a + b); };

/** Smooth simultaneous pan + zoom between two states (a single curved path,
 *  not pan-then-zoom). Returns fn(k in 0..1) -> {x, y, zoom} in world units. */
function flyPath(a, b, viewPx) {
  const dx = b.x - a.x, dy = b.y - a.y;
  const scale = Math.pow(2, b.zoom - a.zoom);
  const u1 = Math.hypot(dx, dy) * TILE * Math.pow(2, a.zoom); // px at start zoom
  const w0 = viewPx, w1 = w0 / scale, rho2 = RHO * RHO;
  let u, w, S;
  if (u1 < 1e-9) {
    if (Math.abs(a.zoom - b.zoom) < 1e-12) return () => ({ x: a.x, y: a.y, zoom: a.zoom });
    const k = w1 < w0 ? -1 : 1;
    S = Math.abs(Math.log(w1 / w0)) / RHO;
    u = () => 0;
    w = (s) => Math.exp(k * RHO * s);
  } else {
    const r = (i) => {
      const bb = (w1 * w1 - w0 * w0 + (i ? -1 : 1) * rho2 * rho2 * u1 * u1) / (2 * (i ? w1 : w0) * rho2 * u1);
      return Math.log(Math.sqrt(bb * bb + 1) - bb);
    };
    const r0 = r(0);
    w = (s) => cosh(r0) / cosh(r0 + RHO * s);
    u = (s) => (w0 * ((cosh(r0) * tanh(r0 + RHO * s) - sinh(r0)) / rho2)) / u1;
    S = (r(1) - r0) / RHO;
  }
  return (k) => {
    const s = k * S;
    const f = k >= 1 ? 1 : u(s);
    return { x: a.x + dx * f, y: a.y + dy * f, zoom: a.zoom + Math.log2(1 / w(s)) };
  };
}

const MOVE_TYPES = ['fly_to', 'push_in', 'pull_back'];
// All three start gently: a move that starts at full speed reads as a snap, not a camera move.
const DEFAULT_EASING = { fly_to: 'inOut', push_in: 'inOut', pull_back: 'inOut' };

export class TimelineError extends Error {}

export function validateCamera(camera, duration, freeze = []) {
  const errs = [];
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  if (!camera || !camera.start || !num(camera.start.lon) || !num(camera.start.lat) || !num(camera.start.zoom)) {
    errs.push('camera.start needs numeric lon, lat, zoom');
  }
  let prevEnd = 0;
  (camera?.moves || []).forEach((m, i) => {
    if (!MOVE_TYPES.includes(m.type)) errs.push(`moves[${i}].type must be one of ${MOVE_TYPES.join(', ')}`);
    if (!num(m.t) || !num(m.dur) || m.dur <= 0) errs.push(`moves[${i}] needs numeric t and dur > 0`);
    if (!m.to || !num(m.to.zoom)) errs.push(`moves[${i}].to needs a numeric zoom`);
    if (m.type === 'fly_to' && (!m.to || !num(m.to.lon) || !num(m.to.lat))) errs.push(`moves[${i}] fly_to needs to.lon and to.lat`);
    if (m.easing && !easings[m.easing]) errs.push(`moves[${i}].easing unknown: ${m.easing}`);
    if (num(m.t) && m.t < prevEnd - 1e-9) errs.push(`moves[${i}] starts at ${m.t}s before the previous move ends (${prevEnd}s); moves must not overlap`);
    if (num(m.t) && num(m.dur)) prevEnd = m.t + m.dur;
    if (num(duration) && num(m.t) && num(m.dur) && m.t + m.dur > duration + 1e-9) errs.push(`moves[${i}] ends after the video (${m.t + m.dur}s > ${duration}s)`);
    for (const [a, b] of freeze) if (num(m.t) && num(m.dur) && m.t < b - 1e-9 && m.t + m.dur > a + 1e-9) errs.push(`moves[${i}] (${m.t}s-${m.t + m.dur}s) runs under full-screen media (${a}s-${b}s): the map holds still there, so move the camera before or after it`);
  });
  const d = camera?.drift;
  if (d && (!num(d.pct_per_s) || d.pct_per_s < 0)) errs.push('drift.pct_per_s must be a number >= 0');
  return errs;
}

export function createCamera({ camera, width, height, duration, freeze = [] }) {
  const errs = validateCamera(camera, duration, freeze);
  if (errs.length) throw new TimelineError(errs.join('; '));
  const viewPx = Math.max(width, height);

  // ---- base path ---------------------------------------------------------
  const [sx, sy] = lonLatToWorld(camera.start.lon, camera.start.lat);
  let cur = { x: sx, y: sy, zoom: camera.start.zoom };
  const segs = [];
  for (const m of [...(camera.moves || [])].sort((p, q) => p.t - q.t)) {
    let to;
    if (m.type === 'fly_to') {
      // shortest way round the globe: keep the target longitude within 180 degrees of the current one
      const curLon = cur.x * 360 - 180;
      let lon = m.to.lon;
      while (lon - curLon > 180) lon -= 360;
      while (lon - curLon < -180) lon += 360;
      const [tx, ty] = lonLatToWorld(lon, m.to.lat);
      to = { x: tx, y: ty, zoom: m.to.zoom };
    } else if (Number.isFinite(m.to.lon) && Number.isFinite(m.to.lat)) {
      const curLon = cur.x * 360 - 180;
      let lon = m.to.lon;
      while (lon - curLon > 180) lon -= 360;
      while (lon - curLon < -180) lon += 360;
      const [tx, ty] = lonLatToWorld(lon, m.to.lat);
      to = { x: tx, y: ty, zoom: m.to.zoom };
    } else {
      to = { x: cur.x, y: cur.y, zoom: m.to.zoom };
    }
    const ease = easings[m.easing || DEFAULT_EASING[m.type]];
    segs.push({ t0: m.t, t1: m.t + m.dur, from: cur, to, ease, path: m.type === 'fly_to' ? flyPath(cur, to, viewPx) : null });
    cur = to;
  }

  function base(t) {
    let state = { x: sx, y: sy, zoom: camera.start.zoom };
    for (const s of segs) {
      if (t < s.t0) return state;
      if (t < s.t1) {
        const k = s.ease((t - s.t0) / (s.t1 - s.t0));
        if (s.path) return s.path(k);
        return { x: s.from.x + (s.to.x - s.from.x) * k, y: s.from.y + (s.to.y - s.from.y) * k, zoom: s.from.zoom + (s.to.zoom - s.from.zoom) * k };
      }
      state = s.to;
    }
    return state;
  }

  // ---- idle drift ----------------------------------------------------------
  // The drift is integrated (so it is always continuous), but it must never drag
  // the camera away from where a move is aimed: drift picked up before a move is
  // CARRIED into it and fades out over the move, so every move still lands on its
  // target (plus only the little drift of the current shot). Position and speed
  // stay continuous at both ends of every move.
  const drift = camera.drift || { pct_per_s: 0 };
  const h0 = ((drift.heading_deg ?? 90) * Math.PI) / 180;
  const turn = ((drift.turn_deg_per_s ?? 0) * Math.PI) / 180;
  const steps = Math.ceil((duration + 1) / DRIFT_STEP) + 1;
  const cumX = new Float64Array(steps), cumY = new Float64Array(steps);
  for (let i = 1; i < steps; i++) {
    const t = (i - 1) * DRIFT_STEP;
    const z = base(t).zoom;
    const v = (drift.pct_per_s / 100) * (width / (TILE * Math.pow(2, z))); // world units / s
    const th = h0 + turn * t;
    const still = freeze.some(([a, b]) => t >= a && t < b); // under full-screen media the map does not drift either
    cumX[i] = cumX[i - 1] + (still ? 0 : Math.sin(th) * v * DRIFT_STEP);
    cumY[i] = cumY[i - 1] - (still ? 0 : Math.cos(th) * v * DRIFT_STEP);
  }
  function cum(t) {
    const f = Math.max(0, t) / DRIFT_STEP, i = Math.min(steps - 2, Math.floor(f)), r = f - i;
    return [cumX[i] + (cumX[i + 1] - cumX[i]) * r, cumY[i] + (cumY[i + 1] - cumY[i]) * r];
  }
  function offset(t) {
    let i = -1;
    for (let j = 0; j < segs.length; j++) if (t >= segs[j].t0) i = j;
    const [cx, cy] = cum(t);
    if (i < 0) return [cx, cy];
    const [sx0, sy0] = cum(segs[i].t0);
    const [px, py] = i > 0 ? cum(segs[i - 1].t0) : [0, 0];
    const s = segs[i];
    const k = s.ease(clamp01((t - s.t0) / (s.t1 - s.t0)));
    return [cx - sx0 + (sx0 - px) * (1 - k), cy - sy0 + (sy0 - py) * (1 - k)];
  }

  function at(t) {
    const b = base(t), [ox, oy] = offset(t);
    const y = Math.max(0.0001, Math.min(0.9999, b.y + oy));
    const [lon, lat] = worldToLonLat(b.x + ox, y);
    return { lon, lat, zoom: b.zoom };
  }
  return { at, base, segments: segs };
}
