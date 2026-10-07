// LINK: a line between two things in space, drawn on as it appears.
//   "light"   a thin glowing yellow line with pulses of light running from the first thing to the second ("light from
//             the Moon takes 1.3 seconds to reach Earth"), its label on a navy plate
//   "measure" a dashed white measuring line with end ticks and the distance on it
//   { "type": "link", "between": ["moon", "earth"], "style": "light", "label": "1.3 LIGHT-SECONDS" }
//   { "type": "link", "across": "milkyway", "style": "measure", "label": "100,000 LIGHT-YEARS" }   a scale bar of the body's
//   own width, straight across its middle ("below": 1.1 = a scale bar just under it); its label sits a quarter of the way
//   along, clear of the middle (a galaxy's centre has a landmark of its own)
// Ends are bodies, surface points or layers with a position (a craft), like the distance panel. "reveal": { t0, t1 }
// (default: the first second) draws it on; a link whose ends sit on the same dot is not drawn.
import { progressAt } from '../lib/timing.mjs';
import { frontPart, clipToFrame, planeNormal, plate } from '../lib/overlay.mjs';
import { YELLOW } from './ui.mjs';

const norm = (v) => { const l = Math.hypot(...v) || 1; return v.map((c) => c / l); };

export default {
  type: 'link',
  space: 'world',
  create(def) {
    if (!(Array.isArray(def.between) && def.between.length === 2) && !def.across) throw new Error('link: "between": [a, b] or "across": body is required');
    return { def };
  },
  ends(d, f) {
    if (!d.across) return [f.locate(d.between[0]), f.locate(d.between[1])];
    const c = f.locate(d.across), n = f.world.get(d.across);
    if (!c || !n) return [null, null];
    // across the body, in its own plane, as level on screen as that plane allows
    const e = f.camera.matrixWorld.elements, right = [e[0], e[1], e[2]], nrm = planeNormal(f, d.across, d.plane);
    const k = right[0] * nrm[0] + right[1] * nrm[1] + right[2] * nrm[2];
    const rh = norm(right.map((v, i) => v - nrm[i] * k)), r = rh.map((v) => v * n.radiusKm);
    // a scale bar just below the body (in its plane, on the screen-bottom side), so it never crosses what is on the body
    let q = norm([nrm[1] * rh[2] - nrm[2] * rh[1], nrm[2] * rh[0] - nrm[0] * rh[2], nrm[0] * rh[1] - nrm[1] * rh[0]]);
    if (q[0] * e[4] + q[1] * e[5] + q[2] * e[6] > 0) q = q.map((v) => -v);
    const o = c.map((v, i) => v + q[i] * n.radiusKm * (d.below ?? 0));
    return [o.map((v, i) => v - r[i]), o.map((v, i) => v + r[i])];
  },
  draw(inst, f) {
    const d = inst.def, [a, b] = this.ends(d, f);
    if (!a || !b) return;
    const seg = frontPart(f, a, b);
    if (!seg) return;
    const A = f.project(seg[0]), B = f.project(seg[1]);
    const k = progressAt(d.reveal || { t0: d.start ?? 0, t1: (d.start ?? 0) + 1 }, f.t, f.mu);
    const end = [A.x + (B.x - A.x) * k, A.y + (B.y - A.y) * k];
    const full = Math.hypot(B.x - A.x, B.y - A.y);
    if (full < 24 * f.u.S || k <= 0) return;
    const { u, g, W, H } = f, light = (d.style || 'light') === 'light';
    g.save(); g.globalAlpha = f.alpha;
    if (light) {
      u.line([[A.x, A.y], end], { color: d.color || YELLOW, width: 3, glow: 12, alpha: 0.9 });
      if (k >= 1) {                                    // pulses of light travelling from the first thing to the second
        const period = d.period_s || 1.6;
        for (const off of [0, 0.5]) {
          const s = (((f.t - (d.start ?? 0)) / period + off) % 1 + 1) % 1, x = A.x + (B.x - A.x) * s, y = A.y + (B.y - A.y) * s;
          const r = 13 * u.S, grd = g.createRadialGradient(x, y, 0, x, y, r);
          grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.35, 'rgba(251,224,64,0.9)'); grd.addColorStop(1, 'rgba(251,224,64,0)');
          g.fillStyle = grd; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
        }
      }
    } else {
      u.line([[A.x, A.y], end], { color: d.color || '#ffffff', width: 2.5, dash: [14, 10], alpha: 0.9, cap: 'butt' });
      const ux = (B.x - A.x) / full, uy = (B.y - A.y) / full, t = 12 * u.S;
      const ticks = k >= 1 ? [[A.x, A.y], end] : [[A.x, A.y]];
      for (const [x, y] of ticks) u.line([[x - uy * t, y + ux * t], [x + uy * t, y - ux * t]], { color: d.color || '#ffffff', width: 3, alpha: 0.95, cap: 'butt' });
    }
    if (d.label && k >= 0.6) {
      // on the middle of the part of the line that is on screen
      const vis = clipToFrame([A.x, A.y], end, W, H, 90 * u.S);
      if (vis) {
        const at = d.across ? 0.25 : 0.5, mx = vis[0][0] + (vis[1][0] - vis[0][0]) * at, my = vis[0][1] + (vis[1][1] - vis[0][1]) * at;
        g.globalAlpha = f.alpha * Math.min(1, (k - 0.6) / 0.3);
        plate(f, mx, my, d.label, { px: light ? 22 : 20, fg: light ? YELLOW : '#ffffff' });
      }
    }
    g.restore();
  },
};
