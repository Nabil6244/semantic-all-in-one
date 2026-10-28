// PT_GAUGE: speed-test style dials side by side (the "Uploads 30.12 vs 127.51 Mbps" shot): a half-ring that sweeps to its value and a big figure.
//   { "type": "pt_gauge", "start": 0, "end": 5, "title": "UPLOAD SPEED", "unit": "Mbps", "max": 200, "dark": true,
//     "gauges": [{ "label": "iPhone 18 Pro", "value": 30.12, "highlight": false }, { "label": "iPhone 17 Pro", "value": 127.51, "highlight": true }] }
// dark: true draws it as a dark card (for use over a 3D shot); false (default) is the flat paper look.
import { tm, clamp01, glideOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

export default {
  type: 'pt_gauge',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.gauges) || def.gauges.length < 1) throw new Error('pt_gauge: "gauges" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, gs = d.gauges.slice(0, 3), n = gs.length;
    const m = ptMotion(d, f.t, S, { inDur: 0.35, outDur: 0.25, rise: 0 });
    if (m.k <= 0.002) return;
    const max = d.max || Math.max(...gs.map((x) => Number(x.value) || 0)) * 1.15 || 1, ink = d.dark ? '#FFFFFF' : '#1d2127', soft = d.dark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.10)';
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.14, { font: ptFont(S, 34, 700, 'sans'), track: 4, align: 'center', color: d.dark ? '#9DA8B6' : '#8A8F98', shadow: 0 });
    const cw = W * 0.82 / n, R = Math.min(cw * 0.42, H * 0.27);
    gs.forEach((p, i) => {
      const cx = W * 0.09 + cw * (i + 0.5), cy = H * 0.58, k = glideOut((m.age - 0.25 - 0.15 * i) / 1.3), v = Math.max(0, Number(p.value) || 0), a0 = Math.PI * 0.8, a1 = Math.PI * 2.2;
      g.lineCap = 'round'; g.lineWidth = R * 0.18;
      g.strokeStyle = soft; g.beginPath(); g.arc(cx, cy, R, a0, a1); g.stroke();
      g.strokeStyle = p.highlight ? '#1fc41f' : (d.dark ? '#4aa8ff' : '#2f6df6'); g.beginPath(); g.arc(cx, cy, R, a0, a0 + (a1 - a0) * clamp01(v / max) * k); g.stroke();
      const shown = (v * k).toFixed(v < 100 ? 2 : 1);
      T.text(shown, cx, cy + R * 0.12, { font: ptFont(S, Math.min(R * 0.55 / S, 96), 900), align: 'center', color: ink, shadow: 0 });
      T.text(String(d.unit || ''), cx, cy + R * 0.42, { font: ptFont(S, 28, 600, 'sans'), align: 'center', color: d.dark ? '#9DA8B6' : '#8A8F98', shadow: 0 });
      T.text(String(p.label || ''), cx, cy + R * 1.0, { font: ptFont(S, 36, 800), align: 'center', color: ink, shadow: 0 });
    });
    g.restore();
  },
};
