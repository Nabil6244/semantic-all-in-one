// DISTANCE: a live distance panel (bottom right). The camera's distance from what it looks at, or between two things --
// bodies ("earth"), surface points ("moon@23.47,0.67") or other layers with a position (a spacecraft id).
//   { "type": "distance" }                                                   CAMERA DISTANCE
//   { "type": "distance", "between": ["earth", "csm"], "label": "FROM EARTH" }
import { formatDistance } from '../lib/units.mjs';

export default {
  type: 'distance',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def;
    let km = f.cam.distance, label = d.label || 'CAMERA DISTANCE';
    if (d.between) {
      const a = f.locate(d.between[0]), b = f.locate(d.between[1]);
      if (!a || !b) return;
      km = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
      if (d.minus_radii) for (const id of d.between) { const n = f.world.get(id); if (n) km -= n.radiusKm; }
    }
    f.g.save(); f.g.globalAlpha = f.alpha;
    f.u.panel(f.W - 52 * f.u.S, f.H - 56 * f.u.S - 104 * f.u.S, formatDistance(Math.max(0, km)), label);
    f.g.restore();
  },
};
