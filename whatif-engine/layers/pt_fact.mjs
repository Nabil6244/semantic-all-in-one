// PT_FACT: figures over real footage, readable without hiding the picture (Phase 3.2). A soft dark gradient rises from the bottom edge and the
// facts stand on it, left to right, each rising in on its spoken word and staying until the layer ends, so footage can change underneath while
// the figures stay. The newest fact gets an accent bar that sweeps under it.
//   { "type": "pt_fact", "start": 2, "end": 9, "kicker": "DATE" (optional),
//     "items": [{ "value": "5.4\"", "sub": "Outer Display", "at": 0.3 }, { "value": "7.6\"", "sub": "Inner Display", "at": 5.2 }] }
import { tm, clamp01, quartOut, overshoot } from './tm_theme.mjs';
import { ptMotion, ptFont, ptFit, cueAge } from './pt_feature.mjs';

export default {
  type: 'pt_fact',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.items) || !def.items.length) throw new Error('pt_fact: "items" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, items = d.items.slice(0, 4);
    const m = ptMotion(d, f.t, S, { inDur: 0.35, outDur: 0.35, rise: 0 });
    if (m.k <= 0.002) return;
    const accent = d.accent || '#7fc4ff';
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    const gr = g.createLinearGradient(0, H * 0.52, 0, H);                       // the scrim: nothing above half height is darkened
    gr.addColorStop(0, 'rgba(6,8,12,0)'); gr.addColorStop(0.55, 'rgba(6,8,12,0.58)'); gr.addColorStop(1, 'rgba(6,8,12,0.86)');
    g.fillStyle = gr; g.fillRect(0, H * 0.52, W, H * 0.48);
    const n = items.length, left = W * 0.07, colW = Math.min(W * 0.4, (W - left * 2) / n), base = H * 0.86;
    if (d.kicker) T.text(String(d.kicker).toUpperCase(), left, H * 0.665, { font: ptFont(S, 28, 700, 'sans'), track: 5, color: accent, shadow: 0 });
    let newest = -1, newestAge = 1e9;
    items.forEach((it, i) => { const a = cueAge(m.age, it, i, 0.9, 0.25); if (a >= 0 && a < newestAge) { newest = i; newestAge = a; } });
    items.forEach((it, i) => {
      const age = cueAge(m.age, it, i, 0.9, 0.25), k = quartOut(age / 0.5);
      if (k <= 0) return;
      const x = left + colW * i, v = String(it.value ?? ''), s = String(it.sub ?? ''), rise = (1 - k) * 40 * S;
      const pv = ptFit(T, v, 120, colW * 0.9, 800, 'display');
      const pop = 1 + 0.05 * (1 - clamp01(age / 0.7)) * (i === newest ? 1 : 0);
      g.save(); g.translate(x, base - pv * S * 0.2 + rise); g.scale(pop, pop);
      T.text(v, 0, 0, { font: ptFont(S, pv, 800, 'display'), color: '#FFFFFF', shadow: 0.5, alpha: k });
      g.restore();
      if (s) T.text(s, x, base + 46 * S + rise, { font: ptFont(S, ptFit(T, s, 38, colW * 0.9, 500, 'sans'), 500, 'sans'), color: 'rgba(255,255,255,0.82)', shadow: 0.4, alpha: k * clamp01((age - 0.12) / 0.3) });
      const bar = quartOut((age - 0.1) / 0.6) * Math.min(colW * 0.7, T.measure(v, ptFont(S, pv, 800, 'display')));
      if (bar > 1) { g.fillStyle = accent; g.globalAlpha *= (i === newest ? 1 : 0.55); g.fillRect(x, base + 14 * S + rise, bar, 5 * S); g.globalAlpha = (f.alpha ?? 1) * m.k; }
    });
    g.restore();
  },
};
