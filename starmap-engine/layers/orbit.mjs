// ORBIT: a circular orbit drawn around any body, in its real plane. Either an explicit plane, or the osculating circle of a
// trajectory at a moment ("the orbit the craft is on at 17:30"), so the ring and the craft always agree.
//   { "type": "orbit", "body": "moon", "altitude_km": 110, "plane": { "through": [23.47, 0.67], "heading_deg": 270, "epoch": "..." } }
//   { "type": "orbit", "body": "moon", "trajectory": "apollo11_csm", "at_utc": "1969-07-19T20:00:00Z" }
//   "style": { "color": "#ffffff", "width": 3, "dash": null, "behind": "hide" | "faint" }, "arrows": 3, "min_px": 8
import { orbitPlane, orbitPoint, orbitRadius } from '../lib/paths.mjs';

const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

export default {
  type: 'orbit',
  space: 'world',
  create(def, ctx) {
    if (!ctx.world.get(def.body)) throw new Error(`orbit: unknown body ${def.body}`);
    if (!def.trajectory && !def.plane) throw new Error('orbit: give a "plane" or a "trajectory" + "at_utc"');
    return { def, ctx, ring: null };
  },
  ring(inst, f) {
    if (inst.ring) return inst.ring;
    const d = inst.def;
    if (d.trajectory) {
      // the osculating circle: the craft's position and direction at at_utc, relative to the body (inertial)
      const traj = inst.ctx.layer(d.trajectory).traj, when = Date.parse(d.at_utc);
      const was = f.world.date; f.world.setTime(new Date(when));
      const st = traj.at(when), off = f.world.vec(traj.frame, d.body);
      f.world.setTime(was);
      const pos = st.position.map((c, i) => c - off[i]), u = norm(pos);
      const k = st.direction[0] * u[0] + st.direction[1] * u[1] + st.direction[2] * u[2];
      const v = norm(st.direction.map((c, i) => c - u[i] * k));
      inst.ring = { P: { u, v, n: cross(u, v) }, r: Math.hypot(...pos) };
    } else {
      inst.ring = { P: orbitPlane(f.world, d.body, d.plane), r: orbitRadius(f.world, d.body, d) };
    }
    return inst.ring;
  },
  draw(inst, f) {
    const d = inst.def, st = d.style || {}, { P, r } = this.ring(inst, f);
    const centre = f.toCam(d.body, [0, 0, 0]), dist = Math.hypot(...centre);
    if ((r / dist) * f.focalPx < (d.min_px ?? 8)) return;
    const N = d.segments || 240, dir = d.direction ?? 1;
    const pts = [];
    for (let i = 0; i <= N; i++) {
      const q = orbitPoint(P, r, (360 * i) / N).map((c, k) => c + centre[k]), s = f.project(q);
      pts.push({ x: s.x, y: s.y, front: s.front, hid: f.hidden(q) });
    }
    const color = st.color || '#ffffff', width = st.width ?? 3;
    const split = (want) => { const out = []; let cur = []; for (const p of pts) { if (p.front && p.hid === want) cur.push([p.x, p.y]); else if (cur.length) { out.push(cur); cur = []; } } if (cur.length) out.push(cur); return out.filter((x) => x.length > 1); };
    for (const run of split(false)) f.u.line(run, { color, width, dash: st.dash || null, alpha: f.alpha * (st.opacity ?? 0.85), glow: 6 });
    if (st.behind === 'faint') for (const run of split(true)) f.u.line(run, { color, width: width * 0.7, dash: [10, 12], alpha: f.alpha * 0.25 });
    const arrows = d.arrows ?? 3;
    for (let k = 0; k < arrows; k++) {
      const i = Math.floor(((k + 0.5) / arrows) * N), a = pts[i], b = pts[Math.min(N, i + dir)], c = pts[Math.max(0, i - dir)];
      if (!a.front || a.hid || !b.front || !c.front) continue;
      f.g.save(); f.g.globalAlpha = f.alpha * (st.opacity ?? 0.85); f.u.arrow(a.x, a.y, b.x - c.x, b.y - c.y, 16, color); f.g.restore();
    }
  },
};
