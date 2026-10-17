// AUDIT: what the viewer will see, for a whole video, without rendering it. The same camera, clock, world and trajectories
// the page uses, projected with plain math a few times a second -- so a plan can be checked (and repaired) before a single
// frame is drawn. It looks for the things that make a map video read as broken or boring:
//   empty    the frame is nearly all black: what is on screen spans a small corner of it and no body is big enough to read
//   offframe a craft the beat is about is outside the frame (or hidden under a corner panel)
//   still    nothing visibly changes for many seconds: no point moves on screen, nothing appears or leaves
//   repeat   the same view, beat after beat, for a long stretch of narration
//   cut      a planet big enough to read is sliced by the frame edge (a third of it or more outside), not filling the frame
//   flat     no pattern interrupt (a cut, footage coming or going, a full-screen number, a title, a photo card) for a long
//            stretch: viewers drift away after about 45 s of the same rhythm
//   track_off a planet or moon the narration tracks is out of the frame (for review: never repaired by widening blindly)
// Each finding carries its time window and the beat it falls in (spec.starmap.beat_times when the compiler gave them).
import { buildWorld } from './world.mjs';
import { createCamera } from './camera.mjs';
import { trajectoryLookup } from './paths.mjs';
import { createClock } from './clock.mjs';
import { planFootage } from './footage.mjs';
import { motionWhen } from './timing.mjs';

const RAD = Math.PI / 180;
const OVERLAYS = new Set(['caption', 'stat_chip', 'title', 'photo_card', 'pointer', 'distance', 'link', 'rings', 'marker', 'region',
  'status_badge', 'time_jump', 'galaxy_guide']);
// the corner panels the overlays use (1920x1080 layout): a craft under one is as good as hidden
const PANELS = [[0, 0, 640, 110], [1360, 0, 1920, 150], [0, 900, 1920, 1080]];

const sub = (a, b) => a.map((x, i) => x - b[i]);
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((x) => x / l); };

/** spec -> { issues: [{ kind, t0, t1, beat, detail }], frames: per-sample measurements (for tests and the report) }. */
export function auditSpec(spec, { step = 1 / 6, thresholds = {} } = {}) {
  const T = { empty_span: 0.28, empty_px: 0.06, empty_s: 3, still_px_s: 6, still_s: 5, offframe_s: 1.5, repeat_s: 45, cut_s: 1.5, flat_s: 45,
    // Cinema: a shot is on screen a few seconds between cuts, so a map that moves less than this for 2.5 s already reads as still
    ...(spec.cinema && spec.cinema.motion !== false ? { still_px_s: 10, still_s: 2.5 } : {}), ...thresholds };
  const W = spec.width || 1920, H = spec.height || 1080, fov = spec.fov_deg || 40, aspect = W / H;
  const sx = W / 1920, sy = H / 1080;
  const tanHalf = Math.tan((fov / 2) * RAD), focal = (H / 2) / tanHalf;
  const fp = planFootage(spec);
  const clock = createClock(fp.mapClock(spec.clock));
  const world = buildWorld(spec.world, { date: clock.utc(fp.mu(0)) });
  const look = trajectoryLookup(world, spec.layers || []);
  const camSpec = fp.mapCamera(spec.camera);
  const cam = createCamera(world, { fov_deg: fov, aspect, ...camSpec }, { trajectory: look, dateAt: (t) => clock.utc(t) });
  const sunId = [...world.nodes.values()].find((n) => n.kind === 'star')?.id;
  const layers = spec.layers || [];
  const crafts = layers.filter((L) => L.type === 'tracker' && !L.body);
  const tracked = layers.filter((L) => L.type === 'tracker' && L.body);
  const drawn = layers.filter((L) => L.type === 'trajectory' && L.of && L.draw !== false);
  const beatTimes = spec.starmap?.beat_times || [];
  const beatAt = (t) => (beatTimes.find((b) => t >= b.start && t < b.end) || {}).id || '';

  // Cinema's full-frame plates and hero scenes hide the map while they are up
  const covers = (spec.layers || []).filter((L) => L.type === 'cinema_plate' || L.type === 'cinema_hero' || L.type === 'cinema_craft');
  const covered = (t) => covers.some((L) => t >= L.start && t < L.end);
  const frames = [];
  for (let t = 0; t <= spec.duration; t += step) {
    if (fp.mapAlpha(t) < 0.5 || covered(t)) { frames.push({ t, map: false }); continue; }
    const m = fp.mu(t), date = clock.utc(m);
    world.setTime(date);
    const c = cam(m), fwd = norm(sub(c.target, c.position)), right = norm(cross(fwd, c.up)), up = cross(right, fwd);
    // world point (anchor-relative km) -> screen px; null behind the camera
    const proj = (anchor, local) => {
      const v = world.vec(c.anchor, anchor), p = [v[0] + local[0] - c.position[0], v[1] + local[1] - c.position[1], v[2] + local[2] - c.position[2]];
      const z = dot(p, fwd);
      if (z <= 0) return null;
      return { x: W / 2 + (dot(p, right) / z) * focal, y: H / 2 - (dot(p, up) / z) * focal, z };
    };
    // a hero close-up (the camera within a km of a craft): the craft's model fills the frame; its turning is the motion
    const hero = c.distance < 1;
    const camFromSunLy = sunId ? Math.hypot(...world.vec(sunId, c.anchor).map((v, i) => v + c.position[i])) / 9.4607e12 : 0;
    const pts = [];            // content on screen: [x, y, weight]
    let biggest = 0, cut = '';
    for (const n of world.nodes.values()) {
      if (n.kind !== 'body' && n.kind !== 'star' && n.kind !== 'galaxy') continue;
      const s = proj(n.id, [0, 0, 0]);
      if (!s) continue;
      const px = (n.radiusKm / s.z) * focal;
      if (n.kind === 'galaxy' && camFromSunLy < 500) continue;   // inside it: no disk on screen
      // a neighbour star only shows once the camera is out past show_from_ly (the page fades it in from there)
      if (n.show_from_ly && camFromSunLy < n.show_from_ly) continue;
      pts.push([s.x, s.y, px]);
      if (s.x > -px && s.x < W + px && s.y > -px && s.y < H + px) biggest = Math.max(biggest, Math.min(px, H));
      if (px > 0.04 * H && px < 0.45 * H && s.x > 0 && s.x < W && s.y > 0 && s.y < H) {
        const over = Math.max(px - s.x, s.x + px - W, px - s.y, s.y + px - H) / (2 * px);
        if (over > 0.3) cut = n.id;
      }
      if (n.parent && n.show_orbit && world.get(n.parent)) {
        // its orbit ring shows while the camera is neither too close nor too far (as the page fades it)
        const r = Math.hypot(...world.vec(n.parent, n.id)), ratio = c.distance / r;
        if (ratio > 0.3 && ratio < 60) {
          const B = world.orientation(n.parent), a0 = norm(world.vec(n.parent, n.id)), a1 = norm(cross(B.y, a0));
          for (let k = 0; k < 8; k++) {
            const ang = (k / 8) * 2 * Math.PI, local = [0, 1, 2].map((i) => (a0[i] * Math.cos(ang) + a1[i] * Math.sin(ang)) * r);
            const q = proj(n.parent, local);
            if (q) pts.push([q.x, q.y, 0]);
          }
        }
      }
    }
    const craftsOn = [];
    for (const L of crafts) {
      if (t < L.start || t > L.end) continue;
      const tr = look(L.trajectory);
      if (!tr) continue;
      const when = L.motion ? motionWhen(L.motion, t, fp.mu) : +date;
      const q = proj(tr.frame, tr.at(when).position);
      craftsOn.push({ id: L.craft, s: q });
      if (q) pts.push([q.x, q.y, 0]);
    }
    for (const L of drawn) {
      if (t < (L.start ?? 0) || t > (L.end ?? spec.duration)) continue;
      const tr = look(L.of);
      if (!tr) continue;
      const a = L.draw_utc ? Date.parse(L.draw_utc[0]) : tr.t0, b = L.draw_utc ? Date.parse(L.draw_utc[1]) : tr.t1;
      const hideFuture = (L.style || {}).future === 'hidden';
      const end = hideFuture ? Math.min(b, +date) : b;
      for (let k = 0; k <= 10 && end > a; k++) { const q = proj(tr.frame, tr.at(a + ((end - a) * k) / 10).position); if (q) pts.push([q.x, q.y, 0]); }
    }
    // how much of the frame the content spans (clipped to the frame)
    const inside = pts.filter(([x, y]) => x >= 0 && x <= W && y >= 0 && y <= H);
    let span = 0;
    // out past the galaxies: the engine's cloud of thousands of galaxies fills the frame
    if (camFromSunLy > 2e8 || hero) span = 1;
    if (hero) biggest = Math.max(biggest, 0.4 * H);
    else if (inside.length) {
      const xs = inside.map((p) => p[0]), ys = inside.map((p) => p[1]);
      span = Math.max((Math.max(...xs) - Math.min(...xs)) / W, (Math.max(...ys) - Math.min(...ys)) / H);
    }
    // a craft just outside the frame, or under a corner panel (a craft far off in another part of space is simply not in this
    // shot -- the beat shows the place, not a framing mistake)
    const lost = tracked.filter((L) => t >= L.start && t <= L.end && world.get(L.body)).filter((L) => {
      const q = proj(L.body, [0, 0, 0]);
      return !q || q.x < 0 || q.x > W || q.y < 0 || q.y > H;
    }).map((L) => L.body);
    const near = (s) => s && s.x > -1.5 * W && s.x < 2.5 * W && s.y > -1.5 * H && s.y < 2.5 * H;
    const off = craftsOn.filter(({ s }) => near(s) && (s.x < 0 || s.x > W || s.y < 0 || s.y > H
      || PANELS.some(([x0, y0, x1, y1]) => s.x >= x0 * sx && s.x <= x1 * sx && s.y >= y0 * sy && s.y <= y1 * sy))).map((o) => o.id);
    frames.push({ t, map: true, span, biggest: biggest / H, bigPx: biggest, lost, look: fwd, cut, pts: inside.map(([x, y]) => [x, y]), off, crafts: craftsOn.length,
      shot: shotKey(camSpec, m) });
  }

  // ---- findings -----------------------------------------------------------------------------------------------------------
  const issues = [];
  const runs = (pred, min, kind, detail) => {
    let a = null;
    const flush = (end) => { if (a != null && end - a >= min) issues.push({ kind, t0: +a.toFixed(2), t1: +end.toFixed(2), beat: beatAt(a), detail: detail(a, end) }); a = null; };
    for (const f of frames) { if (pred(f)) { if (a == null) a = f.t; } else flush(f.t); }
    flush(spec.duration);
  };
  runs((f) => f.map && f.span < T.empty_span && f.biggest < T.empty_px, T.empty_s, 'empty',
    (a, b) => `the content spans ${Math.round(100 * avg(frames, a, b, 'span'))}% of the frame and nothing is big enough to read`);
  runs((f) => f.map && f.lost && f.lost.length > 0, T.offframe_s, 'track_off', (a) => `${frameAt(frames, a).lost.join(', ')} is named as moving but out of the frame (review)`);
  runs((f) => f.map && f.cut, T.cut_s, 'cut', (a) => `${frameAt(frames, a).cut} is cut by the frame edge`);
  runs((f) => f.map && f.off.length > 0, T.offframe_s, 'offframe', (a, b) => `${frameAt(frames, a).off.join(', ')} is out of frame or under a panel`);
  // still: the content's on-screen motion (median px/s between samples) is below a few pixels a second, and no layer comes or goes
  for (let i = 1; i < frames.length; i++) {
    const f = frames[i], g = frames[i - 1];
    if (!f.map || !g.map) { f.motion = null; continue; }
    const n = Math.min(f.pts.length, g.pts.length);
    const d = [];
    for (let k = 0; k < n && f.pts.length === g.pts.length; k++) d.push(Math.hypot(f.pts[k][0] - g.pts[k][0], f.pts[k][1] - g.pts[k][1]));
    d.sort((x, y) => x - y);
    f.motion = d.length ? d[d.length >> 1] / step : (f.pts.length !== g.pts.length ? 99 : 0);
    // a planet on screen changes too when it grows (a push-in) or the view turns round it (its surface slides by)
    const turn = Math.acos(Math.max(-1, Math.min(1, dot(f.look, g.look))));
    f.motion = Math.max(f.motion, Math.abs(f.bigPx - g.bigPx) / step, (turn * Math.min(f.bigPx, g.bigPx)) / step);
  }
  let a = null;
  const flushStill = (end) => { if (a != null && end - a >= T.still_s) issues.push({ kind: 'still', t0: +a.toFixed(2), t1: +end.toFixed(2), beat: beatAt(a), detail: `nothing moves or changes on screen for ${(end - a).toFixed(1)} s` }); a = null; };
  // overlays coming and going do not make a picture alive: only the picture itself moving does
  for (const f of frames) {
    const changing = !f.map || f.motion == null || f.motion >= T.still_px_s;
    if (!changing) { if (a == null) a = f.t; } else flushStill(f.t);
  }
  flushStill(spec.duration);
  // repeat: one camera view (target, frame size) held through several beats
  let r0 = null, key = null, beats = new Set();
  const flushRepeat = (end) => { if (r0 != null && end - r0 >= T.repeat_s && beats.size >= 2) issues.push({ kind: 'repeat', t0: +r0.toFixed(2), t1: +end.toFixed(2), beat: beatAt(r0), detail: `the same view (${key}) for ${Math.round(end - r0)} s across ${beats.size} beats` }); };
  for (const f of frames) {
    if (!f.map) continue;
    if (f.shot !== key) { flushRepeat(f.t); r0 = f.t; key = f.shot; beats = new Set(); }
    beats.add(beatAt(f.t));
  }
  flushRepeat(spec.duration);
  // flat: the moments that reset attention, in narration time; a gap longer than flat_s between two of them
  const camCuts = (spec.camera.moves || []).filter((m) => !m.dur).map((m) => m.t);
  const resets = [0, spec.duration, ...camCuts, ...(spec.footage || []).flatMap((f) => [f.start, f.end]),
    ...layers.filter((L) => ['big_number', 'title', 'photo_card', 'time_jump'].includes(L.type)).map((L) => L.start ?? L.at)]
    .filter((x) => x != null).sort((a, b) => a - b);
  for (let i = 1; i < resets.length; i++) {
    const a = resets[i - 1], b = resets[i];
    if (b - a > T.flat_s) issues.push({ kind: 'flat', t0: +a.toFixed(2), t1: +b.toFixed(2), beat: beatAt(a + (b - a) / 2),
      detail: `${Math.round(b - a)} s with no cut, footage, big number or card` });
  }
  issues.sort((x, y) => x.t0 - y.t0);
  return { issues, frames };
}

const avg = (frames, a, b, k) => { const xs = frames.filter((f) => f.map && f.t >= a && f.t < b).map((f) => f[k]); return xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0; };
const frameAt = (frames, t) => frames.find((f) => f.t >= t && f.map) || {};

/** A coarse name for the view the camera is on (or gliding to) at map time m: its target and its size to one decade. */
function shotKey(cam, m) {
  const moves = (cam.moves || []).filter((x) => x.t <= m);
  const s = moves.length ? moves[moves.length - 1].to : cam.start;
  if (!s) return '';
  if (s.path) return `path ${s.path.trajectory} ${s.path.from_utc?.slice(0, 4)}-${s.path.to_utc?.slice(0, 4)} el${Math.round(s.el_deg ?? 25)}`;
  if (s.follow) return `follow ${s.follow.trajectory}`;
  const d = s.distance ? Object.entries(s.distance)[0] : null;
  return `${s.target} ${d ? `${d[0]}~1e${Math.round(Math.log10(d[1]))}` : s.fill ? `fill~${s.fill.toFixed(1)}` : s.fit ? `fit~${(+s.fit).toFixed(1)}` : ''} az${Math.round(s.az_deg || 0)} el${Math.round(s.el_deg ?? 0)}`;
}
