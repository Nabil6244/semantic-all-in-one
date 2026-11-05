// RH_CROWD: rows of seated figures (kind "classroom" or "cinema"), one marked. mark = [row, col] (row 0 = front), label, eyes_red, turn (time every head turns).
//   { "type": "rh_crowd", "kind": "classroom", "rows": 4, "cols": 9, "mark": [2, 4], "label": "NORMAL", "start": 0, "end": 3 }
import { applyCam, palOf } from '../lib/rhkit.mjs';
import { drawCrowd } from '../lib/rhart.mjs';
import { tm } from './tm_theme.mjs';
export default {
  type: 'rh_crowd', space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), fam = T.sans(1, 800).split('px ')[1];
    g.save(); g.globalAlpha = f.alpha ?? 1; applyCam(g, W, H, d, f.t);
    drawCrowd(g, W, H, f.t, d, fam, palOf(f, inst.def));
    g.restore();
  },
};
