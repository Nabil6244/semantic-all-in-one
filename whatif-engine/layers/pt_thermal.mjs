// PT_THERMAL: the heat-camera shot of a stress test: two or three phone outlines on black, drawn in a thermal palette (black, violet, red, orange, yellow,
// white) with the hot spot growing from the chip, a big temperature under each, and a colour scale at the side.
//   { "type": "pt_thermal", "start": 0, "end": 5, "title": "30 MIN GAMING", "unit": "°C", "min": 25, "max": 50,
//     "phones": [{ "label": "Galaxy S26 Ultra", "temp": 41.2 }, { "label": "Galaxy S27 Ultra", "temp": 46.8, "highlight": true }] }
import { tm, clamp01, glideOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

const STOPS = [[0, [8, 6, 24]], [0.25, [70, 14, 120]], [0.5, [200, 28, 60]], [0.72, [255, 120, 20]], [0.9, [255, 215, 60]], [1, [255, 250, 220]]];
export const heatRGB = (h) => { const x = clamp01(h); for (let i = 1; i < STOPS.length; i++) if (x <= STOPS[i][0]) { const [a, ca] = STOPS[i - 1], [b, cb] = STOPS[i], k = (x - a) / (b - a); return ca.map((v, j) => Math.round(v + (cb[j] - v) * k)); } return STOPS[STOPS.length - 1][1]; };
const css = (h, a = 1) => { const c = heatRGB(h); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; };

export default {
  type: 'pt_thermal',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.phones) || !def.phones.length) throw new Error('pt_thermal: "phones" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, ph = d.phones.slice(0, 3), n = ph.length;
    const m = ptMotion(d, f.t, S, { inDur: 0.4, outDur: 0.3, rise: 0 });
    if (m.k <= 0.002) return;
    const lo = d.min ?? 25, hi = d.max ?? 50, unit = d.unit ?? '°C';
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    g.fillStyle = '#05060c'; g.fillRect(0, 0, W, H);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.11, { font: ptFont(S, 32, 700, 'sans'), track: 4, align: 'center', color: '#8d93a6', shadow: 0 });
    const pw = Math.min(H * 0.3, W * 0.2), pH = pw * 2.05, gap = pw * 0.9, x0 = W * 0.47 - (n * pw + (n - 1) * gap) / 2, y0 = H * 0.5 - pH / 2 - H * 0.02;
    ph.forEach((p, i) => {
      const x = x0 + i * (pw + gap), k = glideOut((m.age - 0.2 - 0.15 * i) / 2.2), tn = clamp01(((Number(p.temp) || lo) - lo) / (hi - lo)), peak = tn * k, wob = 0.03 * Math.sin(f.t * 2 + i * 2);
      g.save(); g.beginPath(); g.roundRect(x, y0, pw, pH, pw * 0.14); g.clip();
      g.fillStyle = css(0.04 + 0.12 * peak); g.fillRect(x, y0, pw, pH);
      const hot = (cx, cy, r, v) => { const gr = g.createRadialGradient(x + pw * cx, y0 + pH * cy, 0, x + pw * cx, y0 + pH * cy, pw * r); gr.addColorStop(0, css(v, 1)); gr.addColorStop(0.45, css(v * 0.62, 0.85)); gr.addColorStop(1, css(0.1, 0)); g.fillStyle = gr; g.fillRect(x, y0, pw, pH); };
      hot(0.5, 0.58, 1.05, clamp01(peak * 0.55 + wob));                       // warm body
      hot(0.3, 0.2, 0.75, clamp01(peak * 1.0 + wob));                         // the chip / camera corner
      hot(0.5, 0.82, 0.5, clamp01(peak * 0.45));                              // battery end
      g.restore();
      g.strokeStyle = 'rgba(255,255,255,0.35)'; g.lineWidth = 2.5 * S; g.beginPath(); g.roundRect(x, y0, pw, pH, pw * 0.14); g.stroke();
      const val = lo + (Number(p.temp) - lo) * k;
      T.text(`${val.toFixed(1)}${unit}`, x + pw / 2, y0 + pH + 74 * S, { font: ptFont(S, 64, 900), align: 'center', color: p.highlight ? '#ffb347' : '#FFFFFF', glow: p.highlight ? 'rgba(255,150,40,0.45)' : null, shadow: 0 });
      T.text(String(p.label || ''), x + pw / 2, y0 + pH + 116 * S, { font: ptFont(S, 28, 700, 'sans'), align: 'center', color: '#9aa0b4', shadow: 0 });
    });
    const bx = W * 0.9, by = H * 0.22, bh = H * 0.5, bw = 26 * S, gr = g.createLinearGradient(0, by + bh, 0, by);
    for (const [o, c] of STOPS) gr.addColorStop(o, `rgb(${c[0]},${c[1]},${c[2]})`);
    g.fillStyle = gr; g.beginPath(); g.roundRect(bx, by, bw, bh, 8 * S); g.fill();
    T.text(`${hi}${unit}`, bx + bw / 2, by - 16 * S, { font: ptFont(S, 24, 700, 'sans'), align: 'center', color: '#9aa0b4', shadow: 0 });
    T.text(`${lo}${unit}`, bx + bw / 2, by + bh + 36 * S, { font: ptFont(S, 24, 700, 'sans'), align: 'center', color: '#9aa0b4', shadow: 0 });
    g.restore();
  },
};
