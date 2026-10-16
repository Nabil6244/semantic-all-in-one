// TM_COMPARE: two things side by side (telemetry look), sliding in from opposite sides with a small overshoot.
//   mode "cards"      two value cards ("1.6 kg" VENUS'S AIR / "1.1 kg" OUR AIR)
//   mode "particles"  two identical boxes of air: one dense with dots, one nearly empty (each n dots drifting)
//   mode "bars"       two upright bars to scale (a log scale when one is over 50x the other, and it says so)
//   { "type": "tm_compare", "mode": "cards", "title": "ABOUT 50 KM UP, AT THE SAME PRESSURE",
//     "left": { "label": "VENUS'S AIR", "value": "1.6 kg", "sub": "PER CUBIC METRE", "color": "amber", "n": 400, "amount": 92 },
//     "right": { "label": "OUR AIR", "value": "1.1 kg", "sub": "PER CUBIC METRE", "color": "cyan", "n": 4, "amount": 1 },
//     "start": 30, "end": 35.5 }
import { C, tm, colour, overshoot, clamp01, drift } from './tm_theme.mjs';

function rnd(seed) { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

export default {
  type: 'tm_compare',
  space: 'screen',
  create: (def) => {
    if (!def.left || !def.right) throw new Error('tm_compare: "left" and "right" are required');
    // dots for the particle boxes: a fixed start and a velocity each (the same picture for the same frame)
    const dots = (n, seed) => { const r = rnd(seed); return Array.from({ length: Math.min(900, Math.max(0, n | 0)) }, () => [r(), r(), r() - 0.5, r() - 0.5]); };
    return { def, dl: dots(def.left.n ?? 300, 7), dr: dots(def.right.n ?? 6, 11) };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), mode = d.mode || 'cards';
    const age = f.t - (d.start ?? 0), k = overshoot(age / 0.45);
    const sides = [[d.left, -1, inst.dl], [d.right, 1, inst.dr]];
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.2, { font: T.sans(24, 800), track: 3, align: 'center', shadow: 0 });
    const big = Math.max(Number(d.left.amount) || 0, Number(d.right.amount) || 0), small = Math.max(1e-9, Math.min(Number(d.left.amount) || 0, Number(d.right.amount) || 0));
    const logScale = mode === 'bars' && big / small > 50;
    for (const [s, dir, dots] of sides) {
      const col = colour(s.color, dir < 0 ? C.amber : C.cyan);
      const cx = W / 2 + dir * W * 0.13 + dir * (1 - k) * W * 0.25, cy = H * 0.52;
      g.save(); g.globalAlpha *= clamp01(age / 0.25);
      if (mode === 'cards') {
        const w = 220 * T.S, h = 190 * T.S;
        T.card(cx - w / 2, cy - h / 2, w, h, { fill: 'rgba(10,13,18,0.7)', border: col });
        T.text(String(s.value ?? ''), cx, cy - 6 * T.S, { font: T.display(48), align: 'center', track: 1 });
        if (s.sub) T.text(String(s.sub).toUpperCase(), cx, cy + 28 * T.S, { font: T.mono(13, 600), align: 'center', color: C.label, track: 1.5, shadow: 0 });
      } else if (mode === 'particles') {
        const w = 300 * T.S, x0 = cx - w / 2, y0 = cy - w / 2;
        g.strokeStyle = 'rgba(200,215,235,0.55)'; g.lineWidth = 1.5 * T.S; g.strokeRect(x0, y0, w, w);
        g.fillStyle = col;
        const tt = f.t * 0.08;
        for (const [px, py, vx, vy] of dots) {
          const bx = Math.abs(((px + vx * tt) % 2 + 2) % 2 - 1), by = Math.abs(((py + vy * tt) % 2 + 2) % 2 - 1);   // bounce inside
          g.beginPath(); g.arc(x0 + 6 * T.S + bx * (w - 12 * T.S), y0 + 6 * T.S + by * (w - 12 * T.S), 3 * T.S, 0, Math.PI * 2); g.fill();
        }
        if (s.value) T.text(String(s.value), cx, y0 + w + 48 * T.S, { font: T.display(36), align: 'center', track: 1 });
      } else {
        const a = Number(s.amount) || 0, full = H * 0.42;
        const h = logScale ? full * Math.log10(1 + a) / Math.log10(1 + big) : full * a / (big || 1);
        const w = 120 * T.S, base = cy + full / 2;
        g.fillStyle = col; g.globalAlpha *= 0.9; g.fillRect(cx - w / 2, base - Math.max(2 * T.S, h * clamp01(age / 0.9)), w, Math.max(2 * T.S, h * clamp01(age / 0.9)));
        g.globalAlpha /= 0.9;
        if (s.value) T.text(String(s.value), cx, base - h - 20 * T.S, { font: T.display(36), align: 'center', track: 1 });
      }
      T.text(String(s.label || '').toUpperCase(), cx, H * 0.52 + (mode === 'cards' ? 136 : 230) * T.S, { font: T.sans(19, 800), track: 2.5, align: 'center', color: col, shadow: 0 });
      g.restore();
    }
    if (logScale) T.text('LOGARITHMIC SCALE', W / 2, H * 0.9, { font: T.mono(13, 600), track: 2, align: 'center', color: C.label, shadow: 0 });
    g.restore();
  },
};
