// TM_DIAL: analog instruments on a plate -- a pressure gauge with a swinging needle ("VENERA 4'S PRESSURE GAUGE"), or one or
// two analog clocks whose hands run at different speeds (the two-clocks time-dilation picture).
//   { "type": "tm_dial", "mode": "gauge", "title": "VENERA 4'S PRESSURE GAUGE", "min": 0, "max": 7, "unit": "ATMOSPHERES",
//     "keys": [{ "t": 10, "v": 2.7 }, { "t": 13, "v": 7.5 }], "limit": 7, "start": 9, "end": 16 }
//   { "type": "tm_dial", "mode": "clocks", "clocks": [{ "label": "YOU", "rate": 1, "color": "cyan" }, { "label": "EARTH", "rate": 2, "color": "amber" }] }
import { C, tm, colour, glideOut, drift } from './tm_theme.mjs';

function face(T, g, cx, cy, r, color) {
  g.save(); g.strokeStyle = 'rgba(255,255,255,0.55)'; g.lineWidth = 2 * T.S; g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke();
  g.fillStyle = 'rgba(10,13,18,0.6)'; g.fill();
  g.strokeStyle = color; g.globalAlpha *= 0.35; g.lineWidth = 1.5 * T.S; g.beginPath(); g.arc(cx, cy, r + 10 * T.S, 0, Math.PI * 2); g.stroke(); g.restore();
}
export default {
  type: 'tm_dial',
  space: 'screen',
  create: (def) => ({ def, keys: (def.keys || []).slice().sort((a, b) => a.t - b.t) }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), mode = d.mode || 'gauge';
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.2, { font: T.sans(26, 800), track: 3, align: 'center', shadow: 0 });
    if (mode === 'gauge') {
      const cx = W / 2, cy = H * 0.52, r = 230 * T.S, a0 = 150 * Math.PI / 180, a1 = 390 * Math.PI / 180;
      face(T, g, cx, cy, r, C.cyan);
      const span = d.max - d.min, step = d.step || 1;
      for (let v = d.min; v <= d.max + 1e-9; v += step) {
        const a = a0 + (a1 - a0) * ((v - d.min) / span), x0 = cx + Math.cos(a) * (r - 14 * T.S), y0 = cy + Math.sin(a) * (r - 14 * T.S), x1 = cx + Math.cos(a) * r, y1 = cy + Math.sin(a) * r;
        T.line(x0, y0, x1, y1, { color: C.white, width: 2, alpha: 0.8 });
        T.text(String(Math.round(v * 10) / 10), cx + Math.cos(a) * (r - 40 * T.S), cy + Math.sin(a) * (r - 40 * T.S) + 8 * T.S, { font: T.sans(22, 700), align: 'center', shadow: 0, color: v > (d.limit ?? Infinity) ? C.red : C.white });
      }
      if (d.limit != null) { const a = a0 + (a1 - a0) * ((d.limit - d.min) / span); T.line(cx + Math.cos(a) * (r - 22 * T.S), cy + Math.sin(a) * (r - 22 * T.S), cx + Math.cos(a) * (r + 8 * T.S), cy + Math.sin(a) * (r + 8 * T.S), { color: C.red, width: 4 }); }
      let v = inst.keys.length ? inst.keys[0].v : d.min;
      for (let i = 0; i < inst.keys.length; i++) { if (inst.keys[i].t > f.t) break; const from = i ? inst.keys[i - 1].v : d.min; v = from + (inst.keys[i].v - from) * glideOut((f.t - inst.keys[i].t) / 1.3); }
      // a needle pinned past the stop shakes
      const over = v > d.max, a = a0 + (a1 - a0) * (Math.min(v, d.max * 1.02) - d.min) / span + (over ? Math.sin(f.t * 60) * 0.012 : 0);
      T.line(cx, cy, cx + Math.cos(a) * (r - 30 * T.S), cy + Math.sin(a) * (r - 30 * T.S), { color: C.cyan, width: 4, glow: 12 });
      T.node(cx, cy, { color: C.cyan, r: 8 });
      if (d.unit) T.text(String(d.unit).toUpperCase(), cx, cy + 90 * T.S, { font: T.mono(17, 600), track: 2, align: 'center', color: C.label, shadow: 0 });
    } else {
      const cl = d.clocks || [], n = cl.length, gap = 420 * T.S, x0 = W / 2 - (n - 1) * gap / 2, cy = H * 0.5, r = 150 * T.S, tt = f.t - (d.start ?? 0);
      cl.forEach((c, i) => {
        const cx = x0 + i * gap, col = colour(c.color, C.cyan);
        face(T, g, cx, cy, r, col);
        for (let k = 0; k < 12; k++) { const a = k * Math.PI / 6; T.line(cx + Math.cos(a) * (r - 12 * T.S), cy + Math.sin(a) * (r - 12 * T.S), cx + Math.cos(a) * r, cy + Math.sin(a) * r, { color: C.white, width: 2, alpha: 0.7 }); }
        const sec = tt * (c.rate ?? 1) * (d.speed ?? 1), ah = sec / 60 * Math.PI * 2 - Math.PI / 2, am = sec / 3600 * Math.PI * 2 - Math.PI / 2;
        T.line(cx, cy, cx + Math.cos(ah) * r * 0.86, cy + Math.sin(ah) * r * 0.86, { color: col, width: 3, glow: 8 });
        T.line(cx, cy, cx + Math.cos(am) * r * 0.55, cy + Math.sin(am) * r * 0.55, { color: C.white, width: 5 });
        T.node(cx, cy, { color: col, r: 5 });
        T.text(String(c.label || '').toUpperCase(), cx, cy + r + 52 * T.S, { font: T.sans(20, 800), track: 3, align: 'center', color: col, shadow: 0 });
        if (c.sub) T.text(String(c.sub).toUpperCase(), cx, cy + r + 82 * T.S, { font: T.mono(15, 600), track: 1.5, align: 'center', color: C.label, shadow: 0 });
      });
    }
    g.restore();
  },
};
