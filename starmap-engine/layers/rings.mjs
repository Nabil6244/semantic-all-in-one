// RINGS: scale rings around a body, in its plane (the ecliptic for the Sun, the disk for a galaxy), each with a label --
// "1 LIGHT-HOUR", "1 LIGHT-DAY", "1 LIGHT-YEAR" around the Sun, so a flight outwards passes through them. A ring shows
// while it is a sensible size on screen and fades as the camera nears it (flying through it, it sweeps past the frame).
//   { "type": "rings", "around": "sun", "rings": [{ "radius": { "au": 7.2 }, "label": "1 LIGHT-HOUR" }], "plane": "ecliptic" }
import { toKm } from '../lib/units.mjs';
import { viewZ, planeNormal, plate } from '../lib/overlay.mjs';
import { runs } from './ui.mjs';

const N = 160;
const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const ramp = (v, a, b) => Math.min(1, Math.max(0, (v - a) / (b - a)));

export default {
  type: 'rings',
  space: 'world',
  create(def) {
    if (!def.around || !Array.isArray(def.rings) || !def.rings.length) throw new Error('rings: "around" and "rings" are required');
    return { def, rings: def.rings.map((r) => ({ km: toKm(r.radius), label: r.label || '' })) };
  },
  draw(inst, f) {
    const d = inst.def, c = f.locate(d.around);
    if (!c) return;
    const nrm = planeNormal(f, d.around, d.plane), e1 = norm(cross(nrm, Math.abs(nrm[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1])), e2 = cross(nrm, e1);
    const dist = Math.hypot(...c), { u, g, W, H } = f;
    g.save();
    for (const r of inst.rings) {
      const px = (r.km / Math.max(dist, 1e-9)) * f.focalPx;
      const a = f.alpha * ramp(px, 40 * u.S, 110 * u.S) * (1 - ramp(r.km / dist, 0.75, 1.15)) * (1 - ramp(px, 4 * W, 9 * W));
      if (a <= 0.01) continue;
      const pts = [];
      for (let i = 0; i <= N; i++) {
        const th = (i / N) * Math.PI * 2, cs = Math.cos(th), sn = Math.sin(th);
        pts.push(c.map((v, j) => v + (e1[j] * cs + e2[j] * sn) * r.km));
      }
      let best = null;
      const proj = pts.map((q) => { const z = viewZ(f, q); const s = z < 0 ? f.project(q) : { x: 0, y: 0 }; return { x: s.x, y: s.y, ok: z < 0 }; });
      for (const run of runs(proj)) u.line(run, { color: d.color || '#9fc4ff', width: 2, dash: [10, 8], alpha: a * 0.8, cap: 'butt' });
      for (const A of proj) {
        // the label sits where the ring is lowest on screen while still inside the frame
        if (A.ok && A.x > 120 * u.S && A.x < W - 120 * u.S && A.y > 120 * u.S && A.y < H - 150 * u.S && (!best || A.y > best.y)) best = A;
      }
      if (best && r.label) { g.globalAlpha = a; plate(f, best.x, best.y, r.label, { px: 18, fg: '#ffffff' }); g.globalAlpha = 1; }
    }
    g.restore();
  },
};
