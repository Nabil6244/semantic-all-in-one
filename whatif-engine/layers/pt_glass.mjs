// PT_GLASS: the frosted glass data cards of the review references ("Latency 1.2 ms", "Geekbench 23%"): rounded translucent gradient panels with a bright top edge,
// a small title, a big figure that counts up, and an optional delta pill. They sit over a 3D scene, one after another.
//   { "type": "pt_glass", "start": 0, "end": 6, "heading": "LATENCY",
//     "cards": [{ "title": "iPhone 18 Pro", "value": 1.2, "unit": "ms", "delta": "-98%", "tint": "teal", "x": 0.27, "y": 0.2, "w": 0.24 }, { "title": "iPhone 17 Pro", "value": 59.2, "unit": "ms", "tint": "green", "x": 0.73, "y": 0.2 }] }
// x, y are the card's centre as fractions of the frame; w is its width as a fraction of the frame width; the cards enter 0.18 s apart.
import { tm, clamp01, glideOut, overshoot } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

const TINT = { teal: ['rgba(120,220,235,0.92)', 'rgba(30,110,140,0.86)'], green: ['rgba(130,235,170,0.92)', 'rgba(26,120,86,0.86)'], blue: ['rgba(140,180,255,0.92)', 'rgba(34,66,170,0.86)'],
  amber: ['rgba(255,214,130,0.92)', 'rgba(170,96,20,0.86)'], pink: ['rgba(255,170,200,0.92)', 'rgba(160,36,96,0.86)'], slate: ['rgba(190,200,215,0.9)', 'rgba(48,58,76,0.88)'] };

export default {
  type: 'pt_glass',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.cards) || !def.cards.length) throw new Error('pt_glass: "cards" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, cards = d.cards.slice(0, 4), m = ptMotion(d, f.t, S, { inDur: 0.3, outDur: 0.3, rise: 0 });
    if (m.k <= 0.002) return;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    if (d.heading) T.text(String(d.heading).toUpperCase(), W / 2, H * 0.09, { font: ptFont(S, 30, 700, 'sans'), track: 5, align: 'center', color: 'rgba(255,255,255,0.8)', shadow: 0.5 });
    cards.forEach((c, i) => {
      const age = m.age - 0.18 * i, a = clamp01(age / 0.3);
      if (a <= 0) return;
      const sc = 0.88 + 0.12 * Math.min(1.06, overshoot(age / 0.5)), w = W * (c.w ?? 0.24), h = w * 0.56, cx = W * (c.x ?? (i + 0.5) / cards.length), cy = H * (c.y ?? 0.22) + (1 - a) * 18 * S;
      const [c0, c1] = TINT[c.tint] || TINT.teal;
      g.save(); g.globalAlpha *= a; g.translate(cx, cy); g.scale(sc, sc);
      g.shadowColor = 'rgba(0,0,0,0.45)'; g.shadowBlur = 36 * S; g.shadowOffsetY = 14 * S;
      const gr = g.createLinearGradient(-w / 2, -h / 2, w / 2, h / 2); gr.addColorStop(0, c0); gr.addColorStop(1, c1);
      g.fillStyle = gr; g.beginPath(); g.roundRect(-w / 2, -h / 2, w, h, h * 0.2); g.fill();
      g.shadowColor = 'transparent'; g.shadowBlur = 0;
      const hl = g.createLinearGradient(0, -h / 2, 0, 0); hl.addColorStop(0, 'rgba(255,255,255,0.38)'); hl.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = hl; g.beginPath(); g.roundRect(-w / 2 + 3 * S, -h / 2 + 3 * S, w - 6 * S, h * 0.5, h * 0.18); g.fill();
      g.strokeStyle = 'rgba(255,255,255,0.5)'; g.lineWidth = 2.5 * S; g.beginPath(); g.roundRect(-w / 2, -h / 2, w, h, h * 0.2); g.stroke();
      const k = glideOut((age - 0.2) / 1.1), v = Number(c.value), shown = Number.isFinite(v) ? (Number.isInteger(v) ? String(Math.round(v * k)) : (v * k).toFixed(1)) : String(c.value ?? '');
      if (c.title) T.text(String(c.title), -w / 2 + h * 0.16, -h / 2 + h * 0.3, { font: ptFont(S, Math.max(24, h * 0.17 / S), 800, 'sans'), color: 'rgba(255,255,255,0.92)', shadow: 0 });
      const big = ptFont(S, Math.max(40, h * 0.42 / S), 900), uw = T.measure(shown, big);
      T.text(shown, -w / 2 + h * 0.16, h * 0.22, { font: big, color: '#FFFFFF', shadow: 0.25 });
      if (c.unit) T.text(String(c.unit), -w / 2 + h * 0.16 + uw + 10 * S, h * 0.22, { font: ptFont(S, Math.max(26, h * 0.18 / S), 800, 'sans'), color: 'rgba(255,255,255,0.9)', shadow: 0 });
      if (c.delta) { const dw = T.measure(String(c.delta), ptFont(S, 24, 800, 'sans')) + 30 * S; g.fillStyle = 'rgba(0,0,0,0.28)'; g.beginPath(); g.roundRect(w / 2 - dw - h * 0.12, h / 2 - h * 0.12 - 40 * S, dw, 40 * S, 20 * S); g.fill();
        T.text(String(c.delta), w / 2 - dw / 2 - h * 0.12, h / 2 - h * 0.12 - 11 * S, { font: ptFont(S, 24, 800, 'sans'), align: 'center', color: '#FFFFFF', shadow: 0 }); }
      g.restore();
    });
    g.restore();
  },
};
