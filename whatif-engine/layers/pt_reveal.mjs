// PT_REVEAL: the name reveal -- a small kicker ("Introducing") and the product name large, in the empty half of the frame.
//   { "type": "pt_reveal", "kicker": "Introducing", "name": "Galaxy Concept", "side": "right", "start": 10, "end": 14 }
import { C, tm, clamp01 } from './tm_theme.mjs';
import { ptMotion, ptFont, ptFit, ptSide, ptWith } from './pt_feature.mjs';

export default {
  type: 'pt_reveal',
  space: 'screen',
  create: (def) => { if (!def.name) throw new Error('pt_reveal: "name" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = ptMotion(d, f.t, S);
    const side = ['left', 'right', 'center'].includes(d.side) ? d.side : 'right';
    const { x, align, maxW } = ptSide(side, W), name = String(d.name), px = ptFit(T, name, 150, maxW * 1.12, 800, 'display', -2);
    const kicker = d.kicker ?? 'Introducing', ny = H * 0.5 + px * S * 0.42;
    ptWith(g, f, m, () => {
      if (kicker) T.text(String(kicker), x, ny - px * S * 0.82 - 16 * S, { font: ptFont(S, 48, 600, 'sans'), color: '#E9ECF1', align, shadow: 0.35 });
      const k2 = clamp01((m.age - 0.3) / 0.7);
      g.save(); g.translate(0, (1 - k2) * 14 * S);
      T.text(name, x, ny, { font: ptFont(S, px, 800), track: -px * 0.02, color: C.white, align, shadow: 0.35, alpha: k2 });
      g.restore();
    });
  },
};
