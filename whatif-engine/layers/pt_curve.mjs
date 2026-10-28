// PT_CURVE: a measured value over time or use on a frosted panel (the review's "crease depth" chart): the curve draws itself on, a glowing node
// rides along it, labelled marks pop in at their x, and a dashed level line can show where it settles.
//   { "type": "pt_curve", "title": "CREASE DEPTH", "note": "INTERNAL TEST, AS REPORTED", "x_label": "TIME SPENT FOLDED", "y_label": "DEPTH",
//     "points": [[0, 0], [0.1, 0.55], [0.3, 0.85], [1, 0.95]], "marks": [{ "x": 0.3, "text": "RAPID DEEPENING" }], "level": { "y": 0.95, "text": "STABILISES" },
//     "start": 12, "end": 20 }
// points: x and y from 0 to 1, sorted by x; any shape is a smooth monotone-ish line through them (Catmull-Rom).
import { C, tm, glideOut, quartOut, clamp01 } from './tm_theme.mjs';

function sample(pts, x) {
  if (!pts.length) return 0;
  if (x <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    if (x <= pts[i][0]) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], k = (x - x0) / Math.max(1e-6, x1 - x0), s = k * k * (3 - 2 * k);   // smoothstep between the points: no overshoot
      return y0 + (y1 - y0) * s;
    }
  }
  return pts[pts.length - 1][1];
}

export default {
  type: 'pt_curve',
  space: 'screen',
  create: (def) => {
    const pts = (def.points || []).map((p) => [clamp01(Number(p[0])), clamp01(Number(p[1]))]).filter((p) => p.every(Number.isFinite)).sort((a, b) => a[0] - b[0]);
    if (pts.length < 2) throw new Error('pt_curve: "points" needs at least two [x, y] pairs');
    return { def, pts };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, age = f.t - (d.start ?? 0);
    const px = W * 0.08, pw = W * 0.84, py = H * 0.16, ph = H * 0.7;
    g.save(); g.globalAlpha = f.alpha * quartOut(age / 0.4);
    T.card(px, py, pw, ph, { r: 22, fill: 'rgba(6,10,18,0.72)', border: 'rgba(255,255,255,0.14)', accent: C.cyan, accentW: 90 });
    T.text(String(d.title || '').toUpperCase(), px + 56 * S, py + 82 * S, { font: T.sans(40, 800), track: 3, color: C.white, shadow: 0 });
    if (d.note) T.text(String(d.note).toUpperCase(), px + 56 * S, py + 126 * S, { font: T.mono(24, 600), track: 2, color: '#9DA8B6', shadow: 0 });
    const L = px + 150 * S, R = px + pw - 90 * S, Bt = py + ph - 120 * S, Tp = py + 190 * S;
    const P = (x, y) => [L + (R - L) * x, Bt - (Bt - Tp) * y];
    T.line(L, Tp, L, Bt, { color: '#6F7A88', width: 2, alpha: 0.9 });
    T.line(L, Bt, R, Bt, { color: '#6F7A88', width: 2, alpha: 0.9 });
    if (d.y_label) T.text(String(d.y_label).toUpperCase(), L - 14 * S, Tp - 20 * S, { font: T.sans(26, 800), track: 2, color: '#9DA8B6', shadow: 0 });
    if (d.x_label) T.text(String(d.x_label).toUpperCase(), (L + R) / 2, Bt + 70 * S, { font: T.sans(26, 800), track: 2, align: 'center', color: '#9DA8B6', shadow: 0 });
    if (d.level && Number.isFinite(Number(d.level.y))) {
      const [lx, ly] = P(0, clamp01(Number(d.level.y)));
      T.line(lx, ly, R, ly, { color: C.amber, width: 2, alpha: 0.7 * glideOut((age - 1.6) / 0.6), dash: [8, 8] });
      if (d.level.text) T.text(String(d.level.text).toUpperCase(), R, ly - 14 * S, { font: T.mono(24, 700), track: 2, align: 'right', color: C.amber, shadow: 0, alpha: glideOut((age - 1.8) / 0.5) });
    }
    const draw = glideOut((age - 0.4) / 1.6), N = 160, pts = [];
    for (let i = 0; i <= N * draw; i++) { const x = i / N; pts.push(P(x, sample(inst.pts, x))); }
    if (pts.length > 1) {
      g.save(); g.strokeStyle = C.cyan; g.lineWidth = 6 * S; g.lineJoin = 'round'; g.lineCap = 'round'; g.shadowColor = C.cyan; g.shadowBlur = 18 * S;
      g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (const p of pts) g.lineTo(p[0], p[1]); g.stroke(); g.restore();
      const [nx, ny] = pts[pts.length - 1];
      T.node(nx, ny, { color: C.cyan, r: 9, ring: true });
    }
    for (const m of d.marks || []) {
      const x = clamp01(Number(m.x));
      if (!(draw >= x) || !Number.isFinite(x)) continue;
      const k = quartOut((age - 0.4 - 1.6 * x) / 0.4), [mx, my] = P(x, sample(inst.pts, x));
      g.save(); g.globalAlpha *= k;
      T.line(mx, my, mx, my - 70 * S, { color: '#EDE7DC', width: 2, alpha: 0.8 });
      T.node(mx, my, { color: C.white, r: 6, ring: false });
      T.text(String(m.text || '').toUpperCase(), mx, my - 86 * S, { font: T.sans(28, 800), track: 1.5, align: 'center', color: '#EDE7DC', shadow: 0 });
      g.restore();
    }
    g.restore();
  },
};
