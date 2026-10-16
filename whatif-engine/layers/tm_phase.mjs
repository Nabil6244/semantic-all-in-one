// TM_PHASE: a phase diagram on a plate -- solid / liquid / gas regions as faint curves on temperature and pressure axes, a
// marked point for "EARTH'S AIR" and one that moves for a world's surface, a highlighted region ("NOT QUITE A GAS · NOT QUITE A LIQUID").
//   { "type": "tm_phase", "title": "CARBON DIOXIDE: WHAT IT IS AT EACH TEMPERATURE AND PRESSURE", "points": [{ "label": "EARTH'S AIR", "x": 0.22, "y": 0.08, "color": "cyan" },
//     { "label": "VENUS'S SURFACE · 464 °C, 92 BAR", "x": 0.82, "y": 0.55, "color": "red", "t": 6 }], "region": { "x0": 0.7, "y0": 0.45, "x1": 1, "y1": 1, "label": "NOT QUITE A GAS · NOT QUITE A LIQUID", "t": 5 } }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

export default {
  type: 'tm_phase',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), L = W * 0.25, R = W * 0.76, B = H * 0.8, Tp = H * 0.26;
    const P = (x, y) => [L + (R - L) * x, B - (B - Tp) * y];
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (d.title) T.text(String(d.title).toUpperCase(), L, H * 0.14, { font: T.sans(18, 800), track: 2.5, shadow: 0 });
    T.line(L, Tp, L, B, { color: C.label, width: 1.5 }); T.line(L, B, R, B, { color: C.label, width: 1.5 });
    T.text('PRESSURE', L - 14 * T.S, Tp - 14 * T.S, { font: T.mono(12, 600), color: C.label, shadow: 0 }); T.text('TEMPERATURE', R, B + 34 * T.S, { font: T.mono(12, 600), color: C.label, align: 'right', shadow: 0 });
    const draw = glideOut((f.t - (d.start ?? 0)) / 1.0);
    const curve = (fn, n0, n1) => { g.beginPath(); for (let i = 0; i <= 60 * draw; i++) { const u = n0 + (n1 - n0) * i / 60, [x, y] = P(u, fn(u)); i ? g.lineTo(x, y) : g.moveTo(x, y); } g.stroke(); };
    g.strokeStyle = 'rgba(255,255,255,0.7)'; g.lineWidth = 2 * T.S;
    curve((u) => 0.78 * u ** 1.4, 0.0, 0.58); curve((u) => 0.36 * Math.exp(2.6 * (u - 0.58)) , 0.58, 0.9);
    for (const [n, x, y] of [['SOLID', 0.06, 0.55], ['LIQUID', 0.34, 0.62], ['GAS', 0.5, 0.12]]) T.text(n, ...P(x, y), { font: T.mono(13, 600), color: C.label, shadow: 0 });
    const r = d.region;
    if (r && f.t >= (r.t ?? 0)) {
      const [x0, y0] = P(r.x0, r.y1), [x1, y1] = P(r.x1, r.y0), a = clamp01((f.t - r.t) / 0.5);
      g.save(); g.globalAlpha *= a; g.fillStyle = 'rgba(255,42,75,0.16)'; g.strokeStyle = 'rgba(255,42,75,0.55)'; g.lineWidth = 2 * T.S; g.fillRect(x0, y0, x1 - x0, y1 - y0); g.strokeRect(x0, y0, x1 - x0, y1 - y0);
      if (r.label) T.text(String(r.label).toUpperCase(), x0 + 12 * T.S, y0 + 28 * T.S, { font: T.mono(13, 600), color: C.red, shadow: 0 }); g.restore();
    }
    for (const p of d.points || []) {
      if (p.t != null && f.t < p.t) continue;
      const [x, y] = P(p.x, p.y), col = colour(p.color, C.cyan), a = clamp01((f.t - (p.t ?? d.start ?? 0)) / 0.4);
      g.save(); g.globalAlpha *= a; T.node(x, y, { color: col, r: 6 }); T.text(String(p.label).toUpperCase(), x + 14 * T.S, y + 5 * T.S, { font: T.mono(13, 700), color: col, shadow: 0 }); g.restore();
    }
    g.restore();
  },
};
