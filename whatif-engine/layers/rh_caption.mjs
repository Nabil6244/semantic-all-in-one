// RH_CAPTION: one short phrase in small white capitals, bottom centre, with a soft cut-in (no slide).
//   { "type": "rh_caption", "text": "and see a deer standing in your yard", "start": 3, "end": 6 }
import { clamp01 } from '../lib/rhkit.mjs';
import { tm } from './tm_theme.mjs';
export default {
  type: 'rh_caption', space: 'screen',
  create: (def) => { if (!String(def.text || '').trim()) throw new Error('rh_caption: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), text = String(d.text).trim().toUpperCase(), age = f.t - (d.start ?? 0);
    let px = H * (d.size ?? 0.04);
    const fam = T.sans(1, 700).split('px ')[1];
    g.save(); g.font = `700 ${Math.round(px)}px ${fam}`; g.letterSpacing = `${(px * 0.12).toFixed(1)}px`;
    const w = g.measureText(text).width, maxW = W * 0.82;
    if (w > maxW) { px *= maxW / w; g.font = `700 ${Math.round(px)}px ${fam}`; g.letterSpacing = `${(px * 0.12).toFixed(1)}px`; }
    g.globalAlpha = (f.alpha ?? 1) * clamp01(age / 0.12);
    const tw = g.measureText(text).width; g.fillStyle = 'rgba(0,0,0,0.88)'; g.fillRect(W / 2 - tw / 2 - px * 0.7, H * (d.y ?? 0.92) - px * 0.85, tw + px * 1.4, px * 1.7);   // a dark plate: the line stays readable over a white shape
    g.fillStyle = '#F2F2F2'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.shadowColor = 'rgba(0,0,0,0.9)'; g.shadowBlur = px * 0.3;
    g.fillText(text, W / 2, H * (d.y ?? 0.92));
    g.restore();
  },
};
