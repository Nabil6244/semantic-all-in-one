// PT_SIDES: two figures either side of one phone (docs/product_trailer/REVIEW_REFERENCE_5.md, gap 17): a big figure with a small line under
// it on the left, another on the right ("$1299 / S26 Ultra Launch Price", "$1499 / S27 Ultra Leaked Price"; "LPDDR5X / Not LPDDR6").
// The phone is the shot (3D hero) or a flat phone on the paper; the figures sit in the empty thirds, never over it. Each figure rises in on its
// word ("at", s after start, from product_trailer/wordcue.py), else the left one first and the right one a moment later.
//   { "type": "pt_sides", "ink": "dark", "start": 2, "end": 7,
//     "items": [{ "value": "$1,299", "sub": "S26 Ultra Launch Price", "side": "left", "at": 0.4 }, { "value": "$1,499", "sub": "S27 Ultra Leaked Price", "side": "right", "at": 2.1 }] }
import { tm, clamp01, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont, ptFit, cueAge } from './pt_feature.mjs';

export default {
  type: 'pt_sides',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.items) || !def.items.length) throw new Error('pt_sides: "items" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, items = d.items.slice(0, 2);
    const m = ptMotion(d, f.t, S, { inDur: 0.2, outDur: 0.3, rise: 0 });
    if (m.k <= 0.002) return;
    const dark = d.ink === 'dark', ink = dark ? '#16191e' : '#FFFFFF', soft = dark ? '#5d636d' : 'rgba(255,255,255,0.78)';
    const subs = ((f.spec && f.spec.layers) || []).some((L) => L && L.type === 'pt_subtitle');
    const y = H * (subs ? 0.44 : 0.48), maxW = W * 0.27;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    items.forEach((it, i) => {
      const side = it.side || (i === 0 ? 'left' : 'right'), age = cueAge(m.age, it, i, 0.5, 0.2), k = quartOut(age / 0.5);
      if (k <= 0) return;
      const cx = side === 'left' ? W * 0.19 : W * 0.81, rise = (1 - k) * 34 * S, v = String(it.value ?? ''), s = String(it.sub ?? '');
      const pv = ptFit(T, v, 118, maxW, 800, 'sans');
      T.text(v, cx, y + rise, { font: ptFont(S, pv, 800, 'sans'), align: 'center', color: ink, shadow: dark ? 0 : 0.35, alpha: k });
      if (s) {
        const ps = ptFit(T, s, 34, maxW, 500, 'sans');
        T.text(s, cx, y + rise + (ps + 26) * S, { font: ptFont(S, ps, 500, 'sans'), align: 'center', color: soft, shadow: 0, alpha: k * clamp01((age - 0.15) / 0.35) });
      }
    });
    g.restore();
  },
};
