// PT_BIGTYPE: a huge italic, wide display word across the frame ("120Hz") that settles from a slight scale-up, concept-trailer style.
//   { "type": "pt_bigtype", "text": "120Hz", "y": 0.22, "start": 6, "end": 9 }     (y: baseline-centre as a fraction of H)
import { C, tm, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont, ptFit, ptWith } from './pt_feature.mjs';

export default {
  type: 'pt_bigtype',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('pt_bigtype: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = ptMotion(d, f.t, S, { inDur: 0.8, rise: 0 });
    const text = String(d.text), px = ptFit(T, text, 300, W * 0.86, 900, 'display', 2);
    const cy = H * (Number.isFinite(d.y) ? d.y : 0.22), sc = 1.08 - 0.08 * quartOut(m.age / 1.4) - 0.015 * Math.max(0, m.age - 1.4) / 6;
    ptWith(g, f, m, () => {
      g.translate(W / 2, cy); g.scale(sc * 1.06, sc); g.transform(1, 0, -0.16, 1, 0, 0);   // wide + italic (sheared Montserrat Black)
      T.text(text, 0, px * S * 0.36, { font: ptFont(S, px, 900), track: px * 0.02, color: C.white, align: 'center', shadow: 0.3 });
    });
  },
};
