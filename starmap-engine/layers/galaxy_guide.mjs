// GALAXY_GUIDE: a galaxy seen from outside gets its landmarks -- "YOU ARE HERE" on the Sun, the galactic centre, the
// spiral arms -- from its catalogue entry ("features": [{ "label", "at_ly": [x, z] } | { "label", "at": "sun" }], x to the
// right of the face-on picture and z towards its bottom, in light-years). Automatic: it shows only while the camera is far
// enough out to see the disk whole and near enough that the galaxy is more than a dot.
//   { "type": "galaxy_guide" }
import { inBodyAxes } from '../lib/overlay.mjs';
import { drawPointer } from './pointer.mjs';

const ramp = (v, a, b) => Math.min(1, Math.max(0, (v - a) / (b - a)));

export default {
  type: 'galaxy_guide',
  space: 'world',
  create: (def, ctx) => ({ def, galaxies: [...ctx.world.nodes.values()].filter((n) => n.kind === 'galaxy' && Array.isArray(n.features)) }),
  draw(inst, f) {
    for (const n of inst.galaxies) {
      const c = f.locate(n.id);
      if (!c) continue;
      const k = Math.hypot(...c) / n.radiusKm, a = f.alpha * ramp(k, 1.4, 2.2) * (1 - ramp(k, 7, 11));
      if (a <= 0.01) continue;
      f.g.save(); f.g.globalAlpha = a;
      for (const ft of n.features) {
        const p = ft.at ? f.locate(ft.at) : inBodyAxes(f, n.id, ft.at_ly[0], ft.at_ly[1]);
        drawPointer(f, p, ft.label, ft.sub || '', ft.at ? {} : { color: '#ffffff' });
      }
      f.g.restore();
    }
  },
};
