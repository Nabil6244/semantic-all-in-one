// PT_COMPARE3: two to four things side by side on a frosted panel (the review's "Duo vs 18 Pro Max vs 18 Pro, 300 nit"): a label on top, a tall bar
// that rises to its value, and a big figure with its unit; the highlighted column is the one the story is about.
//   { "type": "pt_compare3", "title": "PEAK BRIGHTNESS", "note": "OUTDOORS, AS TESTED", "unit": "NIT",
//     "cols": [{ "label": "FOLDABLE", "value": 300, "highlight": true }, { "label": "MAX", "value": 300 }, { "label": "PRO", "value": 300 }], "max": 350, "start": 5, "end": 11 }
import { C, tm, glideOut, quartOut, colour } from './tm_theme.mjs';

export default {
  type: 'pt_compare3',
  space: 'screen',
  create: (def) => {
    const cols = (def.cols || []).filter((c) => c && Number.isFinite(Number(c.value))).slice(0, 4);
    if (cols.length < 2) throw new Error('pt_compare3: "cols" needs at least two columns with a number');
    return { def, cols };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, age = f.t - (d.start ?? 0), cols = inst.cols;
    const px = W * 0.08, pw = W * 0.84, py = H * 0.16, ph = H * 0.7;
    const max = d.max || Math.max(...cols.map((c) => Number(c.value))) * 1.15 || 1;
    g.save(); g.globalAlpha = f.alpha * quartOut(age / 0.4);
    T.card(px, py, pw, ph, { r: 22, fill: 'rgba(6,10,18,0.72)', border: 'rgba(255,255,255,0.14)', accent: C.cyan, accentW: 90 });
    T.text(String(d.title || '').toUpperCase(), px + 56 * S, py + 82 * S, { font: T.sans(40, 800), track: 3, color: C.white, shadow: 0 });
    if (d.note) T.text(String(d.note).toUpperCase(), px + 56 * S, py + 126 * S, { font: T.mono(24, 600), track: 2, color: '#9DA8B6', shadow: 0 });
    const n = cols.length, left = px + 90 * S, right = px + pw - 90 * S, slot = (right - left) / n, bw = Math.min(150 * S, slot * 0.42);
    const top = py + 250 * S, base = py + ph - 120 * S;
    T.line(left - 30 * S, base, right + 30 * S, base, { color: '#6F7A88', width: 2, alpha: 0.9 });
    cols.forEach((c, i) => {
      const k = glideOut((age - 0.4 - 0.25 * i) / 1.0), cx = left + slot * (i + 0.5), h = (base - top) * Math.max(0, Number(c.value)) / max * k;
      const col = c.highlight ? C.cyan : colour(c.color, '#C9B79A');
      g.save(); g.fillStyle = 'rgba(255,255,255,0.06)'; g.beginPath(); g.roundRect(cx - bw / 2, top, bw, base - top, 10 * S); g.fill();
      g.fillStyle = col; g.shadowColor = c.highlight ? C.cyan : 'transparent'; g.shadowBlur = c.highlight ? 24 * S : 0;
      g.beginPath(); g.roundRect(cx - bw / 2, base - Math.max(0.1, h), bw, Math.max(0.1, h), 10 * S); g.fill(); g.restore();
      T.text(String(c.label).toUpperCase(), cx, py + ph - 64 * S, { font: T.sans(28, 800), track: 1.5, align: 'center', color: c.highlight ? C.cyan : '#EDE7DC', shadow: 0 });
      if (k > 0.5) {
        const val = `${c.text ?? Number(c.value).toLocaleString('en-US')}`;
        T.text(val, cx, base - Math.max(0.1, h) - 24 * S, { font: T.display(64), align: 'center', color: c.highlight ? C.white : '#EDE7DC', glow: c.highlight ? 'rgba(80,200,255,0.5)' : null, shadow: 0, alpha: (k - 0.5) / 0.5 });
        if (d.unit) T.text(String(d.unit).toUpperCase(), cx, base - Math.max(0.1, h) + 28 * S, { font: T.mono(22, 700), track: 2, align: 'center', color: '#101722', shadow: 0, alpha: 0.0 });
      }
    });
    if (d.unit) T.text(String(d.unit).toUpperCase(), px + pw - 56 * S, py + 82 * S, { font: T.display(64), align: 'right', color: C.amber, shadow: 0 });
    g.restore();
  },
};
