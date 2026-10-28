// PT_CAPTION: one short spec line centred near the bottom, concept-trailer style ("New Design", "6.9\" 120Hz Display",
// "200MP Primary Camera"): white geometric sans, crisp dark drop shadow + faint dark halo so it reads over bright sets.
//   { "type": "pt_caption", "text": "200MP Primary Camera", "start": 4, "end": 8, "y": 0.86, "size": 0.11 }
// y = vertical centre of the line as a fraction of H; size = font px as a fraction of H (shrinks to fit 80 % of W).
// Fade-in with a slight rise over 0.6 s, fade-out over 0.5 s. Pure function of t.
import { tm, clamp01, DISPLAY } from './tm_theme.mjs';
import { ptMotion } from './pt_feature.mjs';

export default {
  type: 'pt_caption',
  space: 'screen',
  create: (def) => { if (def.text == null || String(def.text).trim() === '') throw new Error('pt_caption: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S;
    const m = ptMotion(d, f.t, S, { inDur: 0.6, outDur: 0.5, rise: 0 });
    if (m.k <= 0.002) return;
    const text = String(d.text).trim(), maxW = W * 0.8;
    let px = H * (Number(d.size) > 0 ? Number(d.size) : 0.11);             // device px
    const font = (p) => `600 ${Math.round(p)}px ${DISPLAY}, sans-serif`;
    g.save();
    g.font = font(px);
    const w0 = g.measureText(text).width;
    if (w0 > maxW) { px *= maxW / w0; g.font = font(px); }
    const y = H * clamp01(d.y ?? 0.86) + (1 - m.kin) * H * 0.018;           // slight rise on entry
    g.globalAlpha = (f.alpha ?? 1) * m.k;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillStyle = '#FFFFFF';
    // faint outer halo
    g.shadowColor = 'rgba(0,0,0,0.38)'; g.shadowBlur = px * 0.32; g.shadowOffsetX = 0; g.shadowOffsetY = 0;
    g.fillText(text, W / 2, y);
    // crisp dark drop shadow, down-right
    g.shadowColor = 'rgba(0,0,0,0.78)'; g.shadowBlur = px * 0.05; g.shadowOffsetX = px * 0.035; g.shadowOffsetY = px * 0.045;
    g.fillText(text, W / 2, y);
    g.shadowColor = 'transparent'; g.shadowBlur = 0; g.shadowOffsetX = 0; g.shadowOffsetY = 0;
    g.fillText(text, W / 2, y);
    g.restore();
  },
};
