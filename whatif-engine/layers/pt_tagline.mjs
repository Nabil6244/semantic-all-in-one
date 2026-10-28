// PT_TAGLINE: one medium white line in the concept-trailer look ("Slimmer. Stronger"), in the empty half of the frame.
//   { "type": "pt_tagline", "text": "Slimmer. Stronger", "side": "left", "start": 2, "end": 5 }
import { C, tm } from './tm_theme.mjs';
import { ptMotion, ptFont, ptFit, ptSide, ptWith } from './pt_feature.mjs';

export default {
  type: 'pt_tagline',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('pt_tagline: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = ptMotion(d, f.t, S);
    const side = ['left', 'right', 'center'].includes(d.side) ? d.side : 'left';
    const { x, align, maxW } = ptSide(side, W), text = String(d.text), px = ptFit(T, text, 96, maxW, 800, 'display', -1.5);
    ptWith(g, f, m, () => T.text(text, x, H * 0.5 + px * S * 0.35, { font: ptFont(S, px, 800), track: -px * 0.015, color: C.white, align, shadow: 0.35 }));
  },
};
