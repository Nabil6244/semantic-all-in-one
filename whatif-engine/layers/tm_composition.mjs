// TM_COMPOSITION: what something is made of, as one segmented bar filling left to right (telemetry look) -- "CO₂ 96.5%" in
// orange, "N₂ 3.5%" in blue -- then a verdict line under it ("OXYGEN: NONE" in red).
//   { "type": "tm_composition", "title": "VENUS'S AIR", "parts": [{ "label": "CARBON DIOXIDE", "pct": 96.5, "color": "#E8833A" },
//     { "label": "NITROGEN", "pct": 3.5, "color": "#4AA3FF" }], "note": { "text": "OXYGEN: NONE", "color": "red" }, "start": 87, "end": 92 }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

const DEFAULTS = ['#E8833A', '#4AA3FF', '#9AA6B5', '#2EE6A8', '#FFB703'];

export default {
  type: 'tm_composition',
  space: 'screen',
  create: (def) => { if (!def.parts?.length) throw new Error('tm_composition: "parts" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const age = f.t - (d.start ?? 0), fill = glideOut(age / 1.2);
    const x0 = W * 0.2, x1 = W * 0.8, y = H * 0.5, h = 56 * T.S;
    const total = d.parts.reduce((a, p) => a + Math.max(0, Number(p.pct) || 0), 0) || 100;
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, y - 90 * T.S, { font: T.sans(26, 800), track: 3, align: 'center', shadow: 0 });
    g.strokeStyle = 'rgba(255,255,255,0.25)'; g.lineWidth = 1.5 * T.S; g.strokeRect(x0, y - h / 2, x1 - x0, h);
    let x = x0;
    d.parts.forEach((p, i) => {
      const w = (x1 - x0) * (Math.max(0, Number(p.pct) || 0) / total);
      const shown = Math.max(0, Math.min(w, (x1 - x0) * fill - (x - x0)));
      g.fillStyle = colour(p.color, DEFAULTS[i % DEFAULTS.length]); g.fillRect(x, y - h / 2, shown, h);
      if (fill * (x1 - x0) >= x - x0 + w * 0.5) {
        const lx = Math.max(x + 4 * T.S, Math.min(x + w / 2, x1 - 140 * T.S)), al = w < 120 * T.S ? 'left' : 'center';
        T.text(`${p.pct}%`, al === 'center' ? x + w / 2 : x + w + 12 * T.S, y + 12 * T.S, { font: T.display(30), align: al, shadow: 0.3 });
        T.text(String(p.label).toUpperCase(), al === 'center' ? lx : x + w + 12 * T.S, y + h / 2 + 34 * T.S, { font: T.sans(16, 800), track: 2, align: al,
          color: colour(p.color, DEFAULTS[i % DEFAULTS.length]), shadow: 0 });
      }
      x += w;
    });
    if (d.note?.text) T.text(String(d.note.text).toUpperCase(), W / 2, y + h / 2 + 110 * T.S, { font: T.sans(34, 800), track: 3, align: 'center',
      color: colour(d.note.color, C.red), alpha: clamp01((age - 1.3) / 0.3) });
    g.restore();
  },
};
