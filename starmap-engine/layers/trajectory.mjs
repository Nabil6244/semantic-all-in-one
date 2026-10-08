// TRAJECTORY: a flight path through space, from samples (real flight data) or generators (illustrated, see lib/paths.mjs).
// It is the source of truth for where a spacecraft is; drawing it is optional ("draw": false keeps it as data only).
//   { "type": "trajectory", "id": "apollo11_csm", "frame": "earth", "source": "illustrated",
//     "generate": [ {...}, ... ] | "samples": [ {...}, ... ],
//     "reveal": "craft" | "full" | { "t0": 10, "t1": 18 },     craft: drawn up to where the craft is now (a trail)
//     "draw_utc": ["1969-07-16T16:16:00Z", "1969-07-19T17:21:50Z"],   only this stretch of the path is drawn
//     "style": { "color": "#FBE040", "width": 6, "glow": 10, "dash": null | [18, 12], "future": "dashed" | "faint" | "hidden",
//                "arrow": false } }      dash: the drawn part too (a path that is planned, projected or hypothetical)
//   { "type": "trajectory", "of": "apollo11_csm", "draw_utc": [...], "start": 10, "end": 24 }   another view of the same
//     path (a different stretch, style or timing) without a second copy of the data
import { createTrajectory } from '../lib/paths.mjs';
import { progressAt, motionWhen } from '../lib/timing.mjs';
import { runs, YELLOW } from './ui.mjs';

function bind(inst, traj) {
  const range = (inst.def.draw_utc || []).map((u) => Date.parse(u));
  inst.traj = traj;
  inst.a = range[0] != null ? traj.indexAt(range[0]) : 0;
  inst.b = range[1] != null ? traj.indexAt(range[1]) : traj.samples.length - 1;
}

export default {
  type: 'trajectory',
  space: 'world',
  create(def, ctx) {
    if (!def.id && !def.of) throw new Error('a trajectory needs an id (spacecraft attach to it by id)');
    const inst = { def, ctx, traj: null, a: 0, b: 0 };
    if (!def.of) bind(inst, createTrajectory(ctx.world, def));
    return inst;
  },
  draw(inst, f) {
    if (!inst.traj) bind(inst, inst.ctx.layer(inst.def.of).traj);
    const { def, traj } = inst;
    if (def.draw === false) return;
    const st = def.style || {}, color = st.color || YELLOW;
    const now = traj.indexAt(def.motion ? motionWhen(def.motion, f.t, f.mu) : +f.date);   // a motion: the trail keeps up with its craft
    let cut;                                           // index the solid (travelled / revealed) part runs to
    if (def.reveal === 'full') cut = inst.b;
    else if (def.reveal && typeof def.reveal === 'object') cut = inst.a + (inst.b - inst.a) * progressAt(def.reveal, f.t, f.mu);
    else cut = Math.min(inst.b, Math.max(inst.a, now));
    const project = (pts) => pts.map((p) => { const q = f.toCam(traj.frame, p), s = f.project(q); return { x: s.x, y: s.y, ok: s.front && !f.hidden(q) }; });
    const per = st.points_per_sample ?? 3;
    if (cut > inst.a) {
      const done = project(traj.polyline(inst.a, cut, per));
      for (const r of runs(done)) f.u.line(r, { color, width: st.width ?? 6, glow: st.glow ?? 10, alpha: f.alpha, dash: st.dash || null });
      if (st.arrow) {
        const r = runs(done).pop();
        if (r && r.length > 1) { const [x1, y1] = r[r.length - 1], [x0, y0] = r[Math.max(0, r.length - 4)]; f.g.save(); f.g.globalAlpha = f.alpha; f.u.arrow(x1, y1, x1 - x0, y1 - y0, 20, color); f.g.restore(); }
      }
    }
    const future = st.future || 'dashed';
    if (future !== 'hidden' && cut < inst.b) {
      const rest = project(traj.polyline(cut, inst.b, per));
      for (const r of runs(rest)) f.u.line(r, { color: st.future_color || '#ffffff', width: (st.width ?? 6) * 0.55, dash: future === 'dashed' ? [16, 14] : null, alpha: f.alpha * (st.future_opacity ?? 0.55) });
    }
  },
};
