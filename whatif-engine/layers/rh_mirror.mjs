// RH_MIRROR: the reflection in a framed mirror. It copies the person's pose `lead` seconds EARLY (it moves first), smiles from smile_at,
// presses its face to the glass at press_at; "water": a running tap on this side only. set: bathroom | hall_mirror (or "rect": [x, y, w, h]).
//   { "type": "rh_mirror", "set": "bathroom", "pose": "stand", "lead": 0.5, "smile_at": 4.2, "press_at": 9, "water": true, "start": 3, "end": 8 }
import { applyCam, palOf } from '../lib/rhkit.mjs';
import { drawMirror } from '../lib/rhart.mjs';
export default {
  type: 'rh_mirror', space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const { g, W, H } = f;
    g.save(); g.globalAlpha = f.alpha ?? 1; applyCam(g, W, H, inst.def, f.t);
    drawMirror(g, W, H, f.t, inst.def, palOf(f, inst.def));
    g.restore();
  },
};
