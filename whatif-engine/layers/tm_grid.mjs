// TM_GRID: a grid of cells (telemetry look): the memory of a computer with a few cells going red ("ONE CHIP HAS DIED"), or a
// row of instruments switching off one by one. Cells appear row by row; `dead` cells turn red at their own time.
//   { "type": "tm_grid", "title": "THE MEMORY OF ONE OF THE SHIP'S COMPUTERS", "cols": 40, "rows": 12,
//     "dead": [{ "cell": [20, 5], "w": 4, "h": 2, "t": 6 }], "note": { "text": "ONE MEMORY CHIP HAS DIED", "t": 6.5 }, "start": 3, "end": 10 }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

export default {
  type: 'tm_grid',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), cols = d.cols || 40, rows = d.rows || 12;
    const cw = Math.min(W * 0.62 / cols, 34 * T.S), ch = cw * 0.92, gw = cw * cols, gh = ch * rows, x0 = (W - gw) / 2, y0 = H * 0.5 - gh / 2;
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, y0 - 46 * T.S, { font: T.sans(20, 800), track: 3, align: 'center', color: C.label, shadow: 0 });
    for (let r = 0; r < rows; r++) {
      const a = clamp01((f.t - (d.start ?? 0) - r * 0.06) / 0.35);
      for (let c = 0; c < cols; c++) {
        let dead = false;
        for (const x of d.dead || []) if (f.t >= x.t && c >= x.cell[0] && c < x.cell[0] + (x.w || 1) && r >= x.cell[1] && r < x.cell[1] + (x.h || 1)) dead = true;
        g.fillStyle = dead ? 'rgba(255,42,75,0.85)' : `rgba(0,229,255,${0.18 + 0.1 * ((c * 7 + r * 13) % 5) / 5})`;
        g.globalAlpha = f.alpha * a; g.fillRect(x0 + c * cw + 1.5, y0 + r * ch + 1.5, cw - 3, ch - 3);
      }
    }
    g.globalAlpha = f.alpha;
    if (d.note && f.t >= (d.note.t ?? 0)) T.text(String(d.note.text).toUpperCase(), W / 2, y0 + gh + 70 * T.S, { font: T.sans(26, 800), track: 3, align: 'center', color: C.red, alpha: clamp01((f.t - d.note.t) / 0.3), shadow: 0 });
    g.restore();
  },
};
