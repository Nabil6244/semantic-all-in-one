// PT_BENCH: a large, readable benchmark comparison (product-film look): a frosted panel, a bold title, then one bar per row with the
// name above the bar and a big figure at its end. Built for a phone or chip rumour where two numbers are the story.
//   { "type": "pt_bench", "title": "GEEKBENCH 6.5 MULTI-CORE", "note": "INTERNAL TEST, AS REPORTED",
//     "rows": [{ "label": "EXYNOS 2700", "value": 13000, "text": "~13,000", "highlight": true },
//              { "label": "SNAPDRAGON 8 ELITE EXTREME GEN 6", "value": 11000, "text": "~11,000" }],
//     "delta": { "text": "+20%", "sub": "AS REPORTED" }, "max": 14000, "start": 20, "end": 30 }
import { C, tm, colour, glideOut, quartOut } from './tm_theme.mjs';

export default {
  type: 'pt_bench',
  space: 'screen',
  create: (def) => { if (!def.rows?.length) throw new Error('pt_bench: "rows" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, rows = d.rows.slice(0, 4);
    const max = d.max || Math.max(...rows.map((r) => Number(r.value) || 0)) * 1.1 || 1;
    const age = f.t - (d.start ?? 0), kPanel = quartOut(age / 0.4);
    const px = W * 0.08, pw = W * 0.84, py = H * 0.25, ph = H * 0.63;
    g.save(); g.globalAlpha = f.alpha * kPanel;
    T.card(px, py, pw, ph, { r: 22, fill: 'rgba(6,10,18,0.72)', border: 'rgba(255,255,255,0.14)', accent: C.cyan, accentW: 90 });
    T.text(String(d.title || '').toUpperCase(), px + 56 * S, py + 82 * S, { font: T.sans(40, 800), track: 3, color: C.white, shadow: 0 });
    if (d.note) T.text(String(d.note).toUpperCase(), px + 56 * S, py + 126 * S, { font: T.mono(24, 600), track: 2, color: '#9DA8B6', shadow: 0 });
    const top = py + 190 * S, rowH = (ph - 230 * S) / rows.length, bx = px + 56 * S, bw = pw - 112 * S - 250 * S, bh = Math.min(58 * S, rowH * 0.34);
    rows.forEach((r, i) => {
      const k = glideOut((age - 0.35 - 0.3 * i) / 1.0), y = top + rowH * i, w = bw * Math.max(0, Number(r.value) || 0) / max * k;
      const col = r.highlight ? C.cyan : colour(r.color, '#C9B79A');
      T.text(String(r.label).toUpperCase(), bx, y + 34 * S, { font: T.sans(32, 800), track: 1.5, color: r.highlight ? C.cyan : '#EDE7DC', shadow: 0, alpha: Math.min(1, k * 3) });
      g.save(); g.fillStyle = 'rgba(255,255,255,0.07)'; g.beginPath(); g.roundRect(bx, y + 52 * S, bw, bh, 8 * S); g.fill();
      g.fillStyle = col; g.shadowColor = r.highlight ? C.cyan : 'transparent'; g.shadowBlur = r.highlight ? 22 * S : 0;
      g.beginPath(); g.roundRect(bx, y + 52 * S, Math.max(0.1, w), bh, 8 * S); g.fill(); g.restore();
      if (k > 0.5) T.text(String(r.text ?? r.value), bx + bw + 40 * S, y + 52 * S + bh * 0.82, { font: T.display(72), color: r.highlight ? C.white : '#EDE7DC', glow: r.highlight ? 'rgba(80,200,255,0.5)' : null, shadow: 0, alpha: (k - 0.5) / 0.5 });
    });
    if (d.delta) {
      const kd = quartOut((age - 1.6) / 0.5);
      if (kd > 0) { g.save(); g.globalAlpha *= kd; T.text(String(d.delta.text), px + pw - 56 * S, py + 100 * S, { font: T.display(104), align: 'right', color: C.amber, glow: 'rgba(255,170,60,0.45)', shadow: 0 });
        if (d.delta.sub) T.text(String(d.delta.sub).toUpperCase(), px + pw - 56 * S, py + 142 * S, { font: T.mono(22, 600), track: 2, align: 'right', color: '#9DA8B6', shadow: 0 }); g.restore(); }
    }
    g.restore();
  },
};
