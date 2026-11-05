// RH_PROP: one object filling the frame -- paper (test sheet + pencil), report, note, clock, phone, eye, cctv (overlay), door_feet.
//   { "type": "rh_prop", "kind": "paper", "start": 0, "end": 3, "title": "CHEMISTRY - UNIT 4 TEST", "lines": ["1. ..."], "cam": {...} }
import { applyCam, palOf } from '../lib/rhkit.mjs';
import { drawProp, PROP_KINDS } from '../lib/rhart.mjs';
import { tm } from './tm_theme.mjs';
export default {
  type: 'rh_prop', space: 'screen',
  create: (def) => { if (!PROP_KINDS.includes(def.kind)) throw new Error(`rh_prop: kind must be one of ${PROP_KINDS.join(', ')}`); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), fam = T.sans(1, 700).split('px ')[1];
    g.save(); g.globalAlpha = f.alpha ?? 1; if (d.kind !== 'cctv') applyCam(g, W, H, d, f.t);
    drawProp(g, d.kind, W, H, f.t, f.t - (d.start ?? 0), d, fam, palOf(f, d));
    g.restore();
  },
};
