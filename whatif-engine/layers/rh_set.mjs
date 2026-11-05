// RH_SET: a set. White-on-black looks: line-drawn; colour looks: a filled perspective room (lib/rhrooms.mjs; "lines": true keeps line art). Was: a line-drawn set (bedroom, hallway, house_section, yard, door, window, classroom) -- white lines on black.
//   { "type": "rh_set", "set": "bedroom", "start": 0, "end": 4, "cam": { "push": 0.06 } }
import { drawSet, applyCam, lineWidth, palOf } from '../lib/rhkit.mjs';
import { drawRoom } from '../lib/rhrooms.mjs';
export default {
  type: 'rh_set', space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const { g, W, H } = f;
    g.save(); g.globalAlpha = f.alpha ?? 1;
    applyCam(g, W, H, inst.def, f.t);
    const pal = palOf(f, inst.def);
    if (pal && !inst.def.lines) drawRoom(g, inst.def.set, W, H, f.t, pal);     // colour looks: a filled, shaded room like the colour references
    else drawSet(g, inst.def.set, W, H, lineWidth(H), f.t, pal);
    g.restore();
  },
};
