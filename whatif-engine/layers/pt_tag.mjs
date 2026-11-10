// PT_TAG: the section tag the reference channels keep bottom-left on every shot: the chapter's name with its number ("Camera Specs  2/9").
//   { "type": "pt_tag", "text": "Camera Specs", "index": 2, "total": 9, "start": 90, "end": 190, "ink": "dark" | "light" }
import { tm, clamp01 } from './tm_theme.mjs';
import { ptFont } from './pt_feature.mjs';

export default {
  type: 'pt_tag',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('pt_tag: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, a = d.start ?? 0, b = d.end ?? a + 5, t = f.t;
    if (t < a || t >= b) return;
    const k = clamp01((t - a) / 0.4), dark = d.ink !== 'light', label = String(d.text), fs = 30;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * k; T.set(ptFont(S, fs, 700, 'sans'));
    const tw = g.measureText(label).width, cnt = d.total ? `${d.index}/${d.total}` : '', cw = cnt ? g.measureText(cnt).width + 26 * S : 0;
    const pw = tw + cw + 52 * S, ph = 56 * S, x = 34 * S, y = H - ph - 30 * S;
    g.fillStyle = dark ? 'rgba(18,22,30,0.82)' : 'rgba(255,255,255,0.86)'; g.beginPath(); g.roundRect(x, y, pw, ph, ph / 2); g.fill();
    g.restore();
    T.text(label, x + 26 * S, y + ph * 0.66, { font: ptFont(S, fs, 700, 'sans'), color: dark ? '#FFFFFF' : '#161A21', shadow: 0, alpha: k });
    if (cnt) T.text(cnt, x + 26 * S + tw + 18 * S, y + ph * 0.66, { font: ptFont(S, fs - 6, 600, 'sans'), color: dark ? 'rgba(255,255,255,0.55)' : 'rgba(22,26,33,0.5)', shadow: 0, alpha: k });
  },
};
