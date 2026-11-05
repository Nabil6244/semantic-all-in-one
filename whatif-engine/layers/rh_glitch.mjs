// RH_GLITCH: colour-split, torn strips and static over everything drawn before it. "bursts": [{ at, dur, amount }] limits it to moments
// (no bursts = the whole start..end). Layer it last. Draw order follows the spec, so put it after the other rh_ layers.
//   { "type": "rh_glitch", "start": 40, "end": 41, "bursts": [{ "at": 40.2, "dur": 0.15 }] }
import { drawGlitch, glitchOn, makeMk } from '../lib/rhkit.mjs';
export default {
  type: 'rh_glitch', space: 'screen',
  create: (def, ctx) => ({ def, mk: ctx && ctx.W ? makeMk(ctx.W, ctx.H) : null }),
  draw(inst, f) {
    const amt = glitchOn(inst.def, f.t) * (inst.def.amount ?? 1) * (f.alpha ?? 1);
    if (amt > 0.01) drawGlitch(f.g, f.W, f.H, f.t, amt, inst.mk);
  },
};
