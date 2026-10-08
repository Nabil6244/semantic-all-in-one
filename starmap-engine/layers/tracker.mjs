// TRACKER: a tracking box locked on a craft while it moves -- corner brackets, its name, and live readouts counting as it
// flies (altitude above a body, speed, distance to its destination), all from its trajectory on every frame. Generic: any
// craft, any body; the readouts are only words and numbers. "approx": true marks them ≈ (an illustrated path: honest that
// the numbers come from a drawing of the flight, not telemetry).
//   { "type": "tracker", "craft": "apollo11.csm", "trajectory": "apollo11_csm", "label": "COLUMBIA",
//     "altitude_of": "earth", "to": "moon", "readouts": ["altitude", "speed", "distance"], "approx": true }
//   readouts: altitude (above altitude_of), speed, distance (to "to"), from (distance from "from"); [] = the name only
import { formatDistance } from '../lib/units.mjs';
import { motionWhen } from '../lib/timing.mjs';

const fmtSpeed = (kms) => (kms >= 1 ? `${kms.toFixed(kms >= 10 ? 1 : 2)} KM/S` : `${Math.round(kms * 3600)} KM/H`);
const fmtAlt = (km) => (km < 1 ? `${Math.max(0, Math.round(km * 1000))} M` : formatDistance(km));

export default {
  type: 'tracker',
  space: 'world',
  create(def, ctx) {
    if (!def.craft || !def.trajectory) throw new Error('tracker: "craft" (a spacecraft layer id) and "trajectory" are required');
    return { def, ctx };
  },
  draw(inst, f) {
    const d = inst.def, rel = f.locate(d.craft);
    if (!rel) return;
    const s = f.project(rel);
    if (!s.front || f.hidden(rel)) return;
    const { u, g, W, H } = f;
    if (s.x < -40 || s.x > W + 40 || s.y < -40 || s.y > H + 40) return;
    const traj = inst.ctx.layer(d.trajectory).traj;
    const when = d.motion ? motionWhen(d.motion, f.t, f.mu) : +f.date;
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
    // the brackets: four corners around the craft, a slow breath so the eye finds it
    const r = Math.max(22, 18 + 4 * Math.sin(f.t * 3)) * u.S, k = 9 * u.S, col = d.color || '#FBE040';
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
