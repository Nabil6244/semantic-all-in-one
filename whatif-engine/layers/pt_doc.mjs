// PT_DOC: an evidence document, as the explainers show for a certification or database listing: a pale page with a header chip, a table of grey rows,
// one row highlighted by a marker that sweeps over it, and a stamp. It draws no readable fake text: rows are bars and the chip carries the real name.
//   { "type": "pt_doc", "start": 0, "end": 5, "chip": "BIS CERTIFICATION", "title": "Battery listing", "rows": 7, "highlight": 3, "stamp": "5G" }
import { tm, clamp01, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

export default {
  type: 'pt_doc',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S;
    const m = ptMotion(d, f.t, S, { inDur: 0.4, outDur: 0.3, rise: 24 });
    if (m.k <= 0.002) return;
    const rows = Math.max(3, Math.min(10, d.rows || 7)), hi = Math.min(rows - 1, d.highlight ?? 3);
    const pw = W * 0.58, ph = H * 0.62, x = (W - pw) / 2, y = (H - ph) / 2 + m.rise;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    g.shadowColor = 'rgba(0,0,0,0.2)'; g.shadowBlur = 30 * S; g.shadowOffsetY = 12 * S; g.fillStyle = '#FFFFFF'; g.beginPath(); g.roundRect(x, y, pw, ph, 14 * S); g.fill();
    g.shadowColor = 'transparent'; g.shadowBlur = 0; g.strokeStyle = 'rgba(0,0,0,0.08)'; g.lineWidth = 2 * S; g.stroke();
    if (d.title) T.text(String(d.title).toUpperCase(), x + 44 * S, y + 70 * S, { font: ptFont(S, 30, 800, 'sans'), track: 2, color: '#2a2f36', shadow: 0 });
    const top = y + 120 * S, rh = (ph - 170 * S) / rows;
    g.fillStyle = '#e4e8ee'; g.fillRect(x + 36 * S, top, pw - 72 * S, rh * 0.8);                  // table header
    for (let i = 0; i < rows; i++) {
      const ry = top + rh * (i + 1);
      if (i % 2 === 0) { g.fillStyle = 'rgba(0,0,0,0.035)'; g.fillRect(x + 36 * S, ry, pw - 72 * S, rh * 0.8); }
      g.fillStyle = '#c3cad4'; const a = 0.25 + ((i * 37) % 11) / 30; g.fillRect(x + 56 * S, ry + rh * 0.28, (pw - 112 * S) * a, rh * 0.24); g.fillRect(x + pw * 0.62, ry + rh * 0.28, (pw - 112 * S) * 0.2, rh * 0.24);
    }
    const sw = quartOut((m.age - 0.7) / 0.7);
    if (sw > 0) { const ry = top + rh * (hi + 1); g.fillStyle = 'rgba(255,214,10,0.6)'; g.fillRect(x + 36 * S, ry, (pw - 72 * S) * sw, rh * 0.8); }
    if (d.chip) {
      const cw = T.measure(String(d.chip), ptFont(S, 28, 800, 'sans')) + 44 * S, cx = x + pw - cw - 30 * S;
      g.fillStyle = '#1d6bf3'; g.beginPath(); g.roundRect(cx, y + 34 * S, cw, 50 * S, 25 * S); g.fill();
      T.text(String(d.chip), cx + cw / 2, y + 68 * S, { font: ptFont(S, 28, 800, 'sans'), align: 'center', color: '#FFFFFF', shadow: 0 });
    }
    if (d.stamp && quartOut((m.age - 1.2) / 0.3) > 0) T.text(String(d.stamp), x + pw - 60 * S, y + ph - 40 * S, { font: ptFont(S, 54, 900), align: 'right', color: 'rgba(29,107,243,0.55)', shadow: 0 });
    g.restore();
    void clamp01;
  },
};
