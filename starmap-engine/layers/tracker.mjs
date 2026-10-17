// TRACKER: a tracking box locked on a craft while it moves -- corner brackets, its name, and live readouts counting as it
// flies (altitude above a body, speed, distance to its destination), all from its trajectory on every frame. Generic: any
// craft, any body; the readouts are only words and numbers. "approx": true marks them ≈ (an illustrated path: honest that
// the numbers come from a drawing of the flight, not telemetry).
//   { "type": "tracker", "craft": "apollo11.csm", "trajectory": "apollo11_csm", "label": "COLUMBIA",
//     "altitude_of": "earth", "to": "moon", "readouts": ["altitude", "speed", "distance"], "approx": true }
//   readouts: altitude (above altitude_of), speed, distance (to "to"), from (distance from "from"); [] = the name only
//   { "type": "tracker", "body": "io", "label": "IO" }   a planet or moon instead of a craft (no readouts)
//   "trail": true   a short fading trail behind it, long enough to read on screen (it fades towards its tail):
//     a craft's is its ACTUAL TRAJECTORY (solid, from its flight data);
//     a body's is its RECENT ORBITAL PATH RELATIVE TO ITS PARENT (dotted): where it was round its planet (or the Sun) over the
//     last hours or days, drawn about where the parent is now -- a picture of its motion, not its path through space
//   A body big on screen gets a thin ring round its disk instead of brackets.
import { formatDistance } from '../lib/units.mjs';
import { motionWhen } from '../lib/timing.mjs';
import { offsetOf } from '../lib/ephemeris.mjs';

const TRAIL_PX = 90;                         // a trail is long enough when it spans about this much of the screen
const SPANS_H = [0.25, 1, 3, 8, 24, 72, 240, 720, 2400, 8760, 26280, 87600];     // hours tried, shortest first

/** Points of the trail at a span (ms) ending at `when`: camera-relative km, oldest first. */
function trailPoints(d, f, traj, when, span, n = 16) {
  const out = [];
  if (traj) {
    for (let i = 0; i <= n; i++) out.push(f.toCam(traj.frame, traj.at(when - span * (1 - i / n)).position));
  } else {
    const node = f.world.get(d.body), eph = node?.offset?.ephemeris;
    if (!eph || !node.parent) return out;
    for (let i = 0; i <= n; i++) out.push(f.toCam(node.parent, offsetOf(eph, new Date(when - span * (1 - i / n)))));
  }
  return out;
}

const fmtSpeed = (kms) => (kms >= 1 ? `${kms.toFixed(kms >= 10 ? 1 : 2)} KM/S` : `${Math.round(kms * 3600)} KM/H`);
const fmtAlt = (km) => (km < 1 ? `${Math.max(0, Math.round(km * 1000))} M` : formatDistance(km));

export default {
  type: 'tracker',
  space: 'world',
  create(def, ctx) {
    if (!def.body && (!def.craft || !def.trajectory)) throw new Error('tracker: "craft" (a spacecraft layer id) and "trajectory", or a "body", are required');
    return { def, ctx };
  },
  draw(inst, f) {
    const d = inst.def;
    if (f.cam && f.cam.distance < 1) return;          // a hero close-up (camera within a km): the craft itself fills the frame
    const rel = f.locate(d.body || d.craft);
    if (!rel) return;
    const s = f.project(rel);
    if (!s.front || (!d.body && f.hidden(rel))) return;
    const { u, g, W, H } = f;
    if (s.x < -40 || s.x > W + 40 || s.y < -40 || s.y > H + 40) return;
    const traj = d.body ? null : inst.ctx.layer(d.trajectory).traj;
    const when = d.motion ? motionWhen(d.motion, f.t, f.mu) : +f.date;
    const col = d.color || '#FBE040';
    if (d.trail) {
      // the span is chosen once (the first frame it shows), so the trail never changes length under the viewer: the shortest
      // that reads on screen, never more than a third of a body's orbit (the arc, not a full circle)
      if (inst.span == null) {
        const node = d.body ? f.world.get(d.body) : null, cap = node?.period_days ? node.period_days * 86400e3 / 3 : Infinity;
        inst.span = 0;
        for (const h of SPANS_H) {
          const span = Math.min(h * 3600e3, cap), pts = trailPoints(d, f, traj, when, span, 6).map((p) => f.project(p));
          let len = 0;
          for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
          inst.span = span;
          if (len >= TRAIL_PX || span >= cap) break;
        }
      }
      const pts = trailPoints(d, f, traj, when, inst.span).map((p) => f.project(p));
      g.save(); g.lineCap = 'round'; g.strokeStyle = col; g.lineWidth = 3 * u.S;
      if (d.body) g.setLineDash([2 * u.S, 7 * u.S]);       // an orbit trail is dotted: not the body's path through space
      for (let i = 1; i < pts.length; i++) {
        if (!pts[i].front || !pts[i - 1].front) continue;
        g.globalAlpha = f.alpha * 0.85 * (i / pts.length) ** 1.6;   // fading towards its tail
        g.beginPath(); g.moveTo(pts[i - 1].x, pts[i - 1].y); g.lineTo(pts[i].x, pts[i].y); g.stroke();
      }
      g.restore();
    }
    if (d.body) {
      // a planet or moon: a ring round it when its disk is big, else the brackets; its name beside
      const info = (f.bodies || []).find((b) => b.id === d.body), px = info ? info.px : 0;
      g.save(); g.globalAlpha = f.alpha; u.shadow(6, 0.7); g.strokeStyle = col; g.lineWidth = 2.5 * u.S;
      if (px > 30 * u.S) { g.beginPath(); g.arc(s.x, s.y, px + 10 * u.S, 0, Math.PI * 2); g.stroke(); }
      const r = px > 30 * u.S ? px + 10 * u.S : Math.max(18, 14 + 4 * Math.sin(f.t * 3)) * u.S, k = 9 * u.S;
      if (px <= 30 * u.S) {
        for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
          g.beginPath(); g.moveTo(s.x + sx * r, s.y + sy * (r - k)); g.lineTo(s.x + sx * r, s.y + sy * r); g.lineTo(s.x + sx * (r - k), s.y + sy * r); g.stroke();
        }
      }
      u.noShadow();
      const bw = u.measure(d.label || '', 18) + 24 * u.S, bh = 30 * u.S, right = s.x < W * 0.68;
      const at = f.placeAny([right ? s.x + r * 0.75 + 14 * u.S : s.x - r * 0.75 - 14 * u.S - bw], s.y - r * 0.75 - bh, bw, bh);
      u.box(at.x, at.y, bw, bh, 7, 'rgba(8,19,32,0.88)');
      g.textAlign = 'left'; g.textBaseline = 'middle'; g.font = u.font(18); g.fillStyle = col;
      g.fillText(d.label || '', at.x + 12 * u.S, at.y + bh / 2);
      g.restore();
      return;
    }
    // readouts from the trajectory itself (frame coordinates), never from the screen
    const p = traj.at(when).position, q = traj.at(when + 1000).position;
    const lines = [];
    const ap = d.approx ? '≈ ' : '';
    for (const r of d.readouts || ['altitude', 'speed']) {
      if (r === 'altitude' && d.altitude_of) {
        const b = f.world.get(d.altitude_of), c = f.world.vec(traj.frame, d.altitude_of);
        lines.push(`ALT ${ap}${fmtAlt(Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]) - (b ? b.radiusKm : 0))}`);
      } else if (r === 'speed' && !d.motion) {
        lines.push(`SPEED ${ap}${fmtSpeed(Math.hypot(q[0] - p[0], q[1] - p[1], q[2] - p[2]))}`);
      } else if (r === 'distance' && d.to) {
        const c = f.world.vec(traj.frame, d.to);
        lines.push(`TO ${(d.to_label || d.to).toUpperCase()} ${ap}${formatDistance(Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]))}`);
      } else if (r === 'from' && d.from) {
        const c = f.world.vec(traj.frame, d.from);
        lines.push(`FROM ${(d.from_label || d.from).toUpperCase()} ${ap}${formatDistance(Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]))}`);
      }
    }
    if (d.style === 'node') {
      // What If's marker (Cinema): a small glowing node on the craft, a short leader up and out, the name and a mono line under it
      const side = s.x < W * 0.68 ? 1 : -1, lx = s.x + side * 46 * u.S, ly = s.y - 40 * u.S;
      g.save(); g.globalAlpha = f.alpha;
      g.strokeStyle = 'rgba(255,255,255,0.9)'; g.lineWidth = 1.6 * u.S;
      g.beginPath(); g.arc(s.x, s.y, 7 * u.S, 0, Math.PI * 2); g.stroke();
      g.fillStyle = '#FFFFFF'; g.beginPath(); g.arc(s.x, s.y, 2.2 * u.S, 0, Math.PI * 2); g.fill();
      g.beginPath(); g.moveTo(s.x + side * 6 * u.S, s.y - 5 * u.S); g.lineTo(lx, ly); g.stroke();
      g.textAlign = side > 0 ? 'left' : 'right'; g.textBaseline = 'alphabetic';
      u.shadow(8, 0.7); g.font = u.font(20); g.fillStyle = '#FFFFFF'; g.fillText(String(d.label || '').split(' · ')[0], lx + side * 6 * u.S, ly);
      if (lines.length) { g.font = '600 ' + Math.round(14 * u.S) + 'px WIMono, Menlo, monospace'; g.fillStyle = 'rgba(200,210,222,0.85)'; g.fillText(lines[0], lx + side * 6 * u.S, ly + 20 * u.S); }
      u.noShadow(); g.restore();
      return;
    }
    // the brackets: four corners around the craft, a slow breath so the eye finds it
    const r = Math.max(22, 18 + 4 * Math.sin(f.t * 3)) * u.S, k = 9 * u.S;
    g.save(); g.globalAlpha = f.alpha;
    u.shadow(6, 0.7); g.strokeStyle = col; g.lineWidth = 2.5 * u.S;
    for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
      g.beginPath(); g.moveTo(s.x + sx * r, s.y + sy * (r - k)); g.lineTo(s.x + sx * r, s.y + sy * r); g.lineTo(s.x + sx * (r - k), s.y + sy * r); g.stroke();
    }
    u.noShadow();
    // the info block beside it: name, then the readouts; a short leader line from the bracket
    const right = s.x < W * 0.68, bw = Math.max(u.measure(d.label || '', 20) + 26 * u.S, ...lines.map((l) => u.measure(l, 15) + 22 * u.S));
    const bh = (32 + lines.length * 22 + 8) * u.S, gap = 26 * u.S;
    const bx = right ? s.x + r + gap : s.x - r - gap - bw;
    const at = f.placeAny([bx], s.y - r - bh * 0.35, bw, bh);
    g.strokeStyle = col; g.lineWidth = 1.5 * u.S; g.globalAlpha = f.alpha * 0.8;
    g.beginPath(); g.moveTo(s.x + (right ? r : -r), s.y - r * 0.5); g.lineTo(right ? at.x : at.x + bw, at.y + 16 * u.S); g.stroke();
    g.globalAlpha = f.alpha;
    u.shadow(12, 0.5); u.box(at.x, at.y, bw, bh, 8, 'rgba(8,19,32,0.88)'); u.noShadow();
    g.textAlign = 'left'; g.textBaseline = 'middle';
    g.font = u.font(20); g.fillStyle = col; g.fillText(d.label || '', at.x + 13 * u.S, at.y + 18 * u.S);
    g.font = u.font(15, 700); g.fillStyle = '#ffffff';
    lines.forEach((l, i) => g.fillText(l, at.x + 13 * u.S, at.y + (42 + i * 22) * u.S));
    g.restore();
    void H;
  },
};
