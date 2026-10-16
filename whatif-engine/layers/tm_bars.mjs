// TM_BARS: a horizontal bar chart on a plate (telemetry look) -- "TEN LANDINGS, 1970-1985 · TIME ON THE SURFACE". Names on the
// left, bars growing in one after another, the value after each bar; the row the story is about in cyan, the rest sand.
//   { "type": "tm_bars", "rows": [{ "label": "VENERA 13", "value": 127, "text": "127 MIN", "highlight": true }, ...],
//     "max": 140, "start": 40, "end": 46 }
import { C, tm, colour, glideOut, drift } from './tm_theme.mjs';

export default {
  type: 'tm_bars',
  space: 'screen',
  create: (def) => { if (!def.rows?.length) throw new Error('tm_bars: "rows" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), rows = d.rows.slice(0, 12);
    const max = d.max || Math.max(...rows.map((r) => Number(r.value) || 0)) * 1.08 || 1;
    const n = rows.length, top = H * 0.24, bottom = H * 0.82, pitch = Math.min(64 * T.S, (bottom - top) / n);
    const xl = W * 0.3, xr = W * 0.76, bh = Math.min(26 * T.S, pitch * 0.5);
    const y0 = (top + bottom) / 2 - (pitch * n) / 2;
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    rows.forEach((r, i) => {
      const k = glideOut((f.t - (d.start ?? 0) - 0.12 * i) / 0.9);
      const y = y0 + pitch * (i + 0.5), w = (xr - xl) * Math.max(0, Number(r.value) || 0) / max * k;
      const col = r.highlight ? C.cyan : colour(r.color, '#D9C3A5');
      T.text(String(r.label).toUpperCase(), xl - 22 * T.S, y + 7 * T.S, { font: T.sans(19, 800), track: 1.5, align: 'right', color: r.highlight ? C.cyan : '#E8E2D8', shadow: 0 });
      g.save(); g.globalAlpha *= r.highlight ? 1 : 0.85; g.fillStyle = col; g.fillRect(xl, y - bh / 2, w, bh);
      if (r.highlight) { g.shadowColor = C.cyan; g.shadowBlur = 16 * T.S; g.fillRect(xl, y - bh / 2, w, bh); }
      g.restore();
      if (k > 0.6) T.text(String(r.text ?? r.value).toUpperCase(), xl + w + 14 * T.S, y + 7 * T.S, { font: T.mono(18, 700), color: r.highlight ? C.cyan : '#E8E2D8', alpha: (k - 0.6) / 0.4, shadow: 0 });
    });
    T.line(xl, y0, xl, y0 + pitch * n, { color: C.label, width: 1.2, alpha: 0.5 });
    g.restore();
  },
};
