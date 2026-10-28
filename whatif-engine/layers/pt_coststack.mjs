// PT_COSTSTACK: a "what the phone costs to build" stack beside a flat phone: coloured segments stack up one after the other, each labelled with its part and
// price, and the total lands on top.
//   { "type": "pt_coststack", "start": 0, "end": 6, "title": "BILL OF MATERIALS", "total": "$466", "unit": "$",
//     "rows": [{ "label": "Display", "value": 90 }, { "label": "Camera", "value": 120 }, { "label": "Processor", "value": 160 }, { "label": "Memory", "value": 96 }] }
import { tm, clamp01, glideOut, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

const PAL = ['#2f6df6', '#e8a21a', '#1fb86a', '#d6455d', '#8a5cf6', '#14a8c4'];

export default {
  type: 'pt_coststack',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.rows) || def.rows.length < 2) throw new Error('pt_coststack: at least two "rows" are required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, rows = d.rows.slice(0, 6), sum = rows.reduce((a, r) => a + (Number(r.value) || 0), 0) || 1;
    const m = ptMotion(d, f.t, S, { inDur: 0.3, outDur: 0.3, rise: 0 });
    if (m.k <= 0.002) return;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    g.fillStyle = '#F2F1EE'; g.fillRect(0, 0, W, H);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.11, { font: ptFont(S, 32, 700, 'sans'), track: 4, align: 'center', color: '#8A8F98', shadow: 0 });
    const ph = H * 0.62, pw = ph * 0.49, px = W * 0.22, py = H * 0.2;          // flat phone, left
    g.shadowColor = 'rgba(0,0,0,0.2)'; g.shadowBlur = 24 * S; g.shadowOffsetY = 10 * S; g.fillStyle = '#2b2b2e'; g.beginPath(); g.roundRect(px, py, pw, ph, pw * 0.14); g.fill(); g.shadowColor = 'transparent';
    g.fillStyle = 'rgba(0,0,0,0.6)'; for (let c = 0; c < 3; c++) { g.beginPath(); g.arc(px + pw * 0.26, py + ph * 0.075 + c * pw * 0.2, pw * 0.085, 0, 7); g.fill(); }
    const sx = W * 0.5, sw = W * 0.12, sh = H * 0.6, sy = H * 0.2;                // the stack, right of the phone, built from the bottom up
    let acc = 0, lastEnd = 0;
    rows.forEach((r, i) => {
      const v = Math.max(0, Number(r.value) || 0), h = sh * v / sum, a = glideOut((m.age - 0.3 - 0.55 * i) / 0.6), y = sy + sh - sh * acc / sum - h;
      acc += v; lastEnd = 0.3 + 0.55 * i + 0.6;
      if (a <= 0) return;
      const col = r.color || PAL[i % PAL.length], hh = h * a;
      g.fillStyle = col; g.beginPath(); g.roundRect(sx, y + h - hh, sw, Math.max(1, hh - 3 * S), 6 * S); g.fill();
      T.text(String(r.label), sx + sw + 28 * S, y + h / 2 - 2 * S, { font: ptFont(S, 32, 800), color: '#1d2127', shadow: 0, alpha: a, base: 'middle' });
      T.text(`${d.unit ?? '$'}${(v * a).toFixed(0)}`, sx + sw + 28 * S, y + h / 2 + 34 * S, { font: ptFont(S, 28, 600, 'sans'), color: '#6b7380', shadow: 0, alpha: a, base: 'middle' });
    });
    const kt = quartOut((m.age - lastEnd) / 0.5);
    if (kt > 0 && d.total) T.text(String(d.total), sx + sw / 2, sy - 22 * S, { font: ptFont(S, 76, 900), align: 'center', color: '#1d2127', shadow: 0, alpha: kt });
    g.restore();
    void clamp01;
  },
};
