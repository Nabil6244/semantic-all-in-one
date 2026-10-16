// TM_CURVE: one relationship as a clean curve on a plate (telemetry look) -- "THE FASTER YOU GO, THE LESS TIME THE TRIP TAKES
// FOR YOU", "THE ENERGY NEEDED TO GO FASTER". Axes with two words each, the curve drawing itself on, a dashed limit and a
// glowing node sliding along the curve to each position the narration gives.
//   { "type": "tm_curve", "shape": "decay" | "wall" | "rise" | "saturate" | "linear", "x_label": "SPEED →",
//     "y_label": "TIME FOR THE TRAVELLER", "limit_label": "SPEED OF LIGHT", "keys": [{ "t": 20, "x": 0.4 }, { "t": 23, "x": 1 }],
//     "marks": [{ "x": 0.77, "text": "77%" }], "start": 19, "end": 25 }
import { C, tm, glideOut, drift } from './tm_theme.mjs';

const SHAPES = {
  decay: (x) => Math.sqrt(Math.max(0, 1 - x * x)),                   // time for the traveller: 1/gamma
  wall: (x) => Math.min(1, 0.04 / Math.sqrt(Math.max(1e-4, 1 - x * x)) - 0.04 + 0.02),   // energy towards the limit
  rise: (x) => x * x,
  saturate: (x) => Math.tanh(x * 2.6) / Math.tanh(2.6),
  linear: (x) => x,
};

export default {
  type: 'tm_curve',
  space: 'screen',
  create: (def) => ({ def, fn: SHAPES[def.shape] || SHAPES.decay, keys: (def.keys || []).slice().sort((a, b) => a.t - b.t) }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), fn = inst.fn;
    const L = W * 0.33, R = W * 0.72, B = H * 0.8, Tp = H * 0.25;
    const P = (x, y) => [L + (R - L) * x * 0.97, B - (B - Tp) * y];
    const draw = glideOut((f.t - (d.start ?? 0) - 0.2) / 1.3);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    T.line(L, Tp, L, B, { color: C.label, width: 1.5, alpha: 0.8 });
    T.line(L, B, R, B, { color: C.label, width: 1.5, alpha: 0.8 });
    if (d.y_label) T.text(String(d.y_label).toUpperCase(), L - 10 * T.S, Tp - 18 * T.S, { font: T.sans(14, 800), track: 2, color: C.label, shadow: 0 });
    if (d.x_label) T.text(String(d.x_label).toUpperCase(), (L + R) / 2, B + 34 * T.S, { font: T.sans(14, 800), track: 2, align: 'center', color: C.label, shadow: 0 });
    const [lx] = P(1, 0);
    T.line(lx, Tp, lx, B, { color: C.label, width: 1.2, alpha: 0.6, dash: [5, 6] });
    if (d.limit_label) T.text(String(d.limit_label).toUpperCase(), lx, B + 34 * T.S, { font: T.sans(14, 800), track: 2, align: 'center', color: C.cyan, shadow: 0 });
    const pts = [];
    for (let i = 0; i <= 140 * draw; i++) pts.push(P(i / 140, fn(i / 140)));
    if (pts.length > 1) {
      g.save(); g.strokeStyle = C.cyan; g.lineWidth = 3 * T.S; g.shadowColor = C.cyan; g.shadowBlur = 10 * T.S; g.lineJoin = 'round';
      g.beginPath(); g.moveTo(...pts[0]); for (const p of pts) g.lineTo(...p); g.stroke(); g.restore();
    }
    for (const m of d.marks || []) {
      if (draw < m.x) continue;
      const [x, y] = P(m.x, fn(m.x));
      T.node(x, y, { color: C.white, r: 4, ring: false });
      T.text(String(m.text), x - 10 * T.S, y - 16 * T.S, { font: T.sans(24, 800), align: 'right' });
    }
    let x = null;
    for (let i = 0; i < inst.keys.length; i++) {
      const k = inst.keys[i];
      if (k.t > f.t) break;
      const from = i ? inst.keys[i - 1].x : 0;
      x = from + (k.x - from) * glideOut((f.t - k.t) / 1.5);
    }
    if (x != null) { const [px, py] = P(Math.min(1, x), fn(Math.min(1, x))); T.node(px, py, { color: C.cyan, r: 7 }); }
    g.restore();
  },
};
