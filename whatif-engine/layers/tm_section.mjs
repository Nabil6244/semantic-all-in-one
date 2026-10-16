// TM_SECTION: a vertical cross-section of an atmosphere on a plate -- layers as bands with names and ranges, a "YOU" marker
// and extra marks at altitudes ("VENERA 4 · 1967 · SILENT"). Used for "where the early probes failed", "acid clouds", descents.
//   { "type": "tm_section", "title": "WHERE THE EARLY PROBES FAILED", "unit": "KM", "max": 75,
//     "layers": [{ "from": 48, "to": 70, "label": "ACID CLOUDS", "sub": "70-48 KM", "color": "#E8D8B0" }, ...],
//     "marks": [{ "v": 26, "label": "VENERA 4 · 1967", "color": "red", "t": 12 }], "you": [{ "t": 10, "v": 55 }, { "t": 14, "v": 20 }] }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

export default {
  type: 'tm_section',
  space: 'screen',
  create: (def) => ({ def, you: (def.you || []).slice().sort((a, b) => a.t - b.t) }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), max = d.max || 80, x0 = W * 0.34, x1 = W * 0.66, top = H * 0.24, bot = H * 0.86;
    const yOf = (v) => bot - (bot - top) * (v / max);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.14, { font: T.sans(26, 800), track: 3, align: 'center', shadow: 0 });
    const reveal = glideOut((f.t - (d.start ?? 0)) / 0.9);
    for (const L of d.layers || []) {
      const ya = yOf(L.to), yb = yOf(L.from), h = (yb - ya) * reveal;
      const grd = g.createLinearGradient(0, ya, 0, yb); grd.addColorStop(0, colour(L.color, '#C9B48A')); grd.addColorStop(1, colour(L.color2 || L.color, '#8A6B45'));
      g.fillStyle = grd; g.globalAlpha = f.alpha * 0.92; g.fillRect(x0, yb - h, x1 - x0, h); g.globalAlpha = f.alpha;
      if (reveal > 0.8) {
        T.text(String(L.label).toUpperCase(), x1 + 36 * T.S, (ya + yb) / 2 + 2 * T.S, { font: T.sans(17, 800), track: 2, color: C.white, shadow: 0 });
        if (L.sub) T.text(String(L.sub).toUpperCase(), x1 + 36 * T.S, (ya + yb) / 2 + 24 * T.S, { font: T.mono(13, 600), color: C.label, shadow: 0 });
      }
    }
    for (let v = 0; v <= max; v += d.step || 10) { T.line(x0 - 8 * T.S, yOf(v), x0, yOf(v), { color: C.label, width: 1.5 }); T.text(String(v), x0 - 16 * T.S, yOf(v) + 5 * T.S, { font: T.mono(12, 600), align: 'right', color: C.label, shadow: 0 }); }
    for (const m of d.marks || []) {
      if (m.t != null && f.t < m.t) continue;
      const a = clamp01((f.t - (m.t ?? 0)) / 0.3), y = yOf(m.v), col = colour(m.color, C.red);
      g.save(); g.globalAlpha *= a; T.line(x0 - 6 * T.S, y, x1, y, { color: col, width: 2, dash: [8, 6] });
      T.text(String(m.label).toUpperCase(), x0 + 12 * T.S, y - 8 * T.S, { font: T.sans(15, 800), track: 1.5, color: col, shadow: 0 }); g.restore();
    }
    let v = null;
    for (let i = 0; i < inst.you.length; i++) { const k = inst.you[i]; if (k.t > f.t) break; const from = i ? inst.you[i - 1].v : k.v; v = from + (k.v - from) * glideOut((f.t - k.t) / 1.5); }
    if (v != null) { const y = yOf(v); T.node(W / 2, y, { color: C.cyan, r: 8 }); T.text('YOU', W / 2 + 22 * T.S, y + 5 * T.S, { font: T.sans(17, 800), track: 2, color: C.cyan, shadow: 0 }); }
    g.restore();
  },
};
