// post_hydrograph: a river gauge's gage height over the days, drawn left to right, with NWS flood-stage lines and the crest
// marked. A gap in the gauge record stays a gap (the line breaks), so a failed gauge never looks like a smooth reading.
import { hydroLayout, hydroPoints } from '../wxu_post_charts.mjs';

export default {
  type: 'post_hydrograph',
  order: 60,
  validate(e) {
    const bad = [];
    if (!Array.isArray(e.values) || e.values.filter((v) => Number.isFinite(v)).length < 2) bad.push('post_hydrograph needs values (at least two readings)');
    if (!e.title) bad.push('post_hydrograph needs a title');
    if (e.crest && !(Number.isInteger(e.crest.index) && e.crest.text)) bad.push('post_hydrograph crest needs index and text');
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const L = hydroLayout(e.values, e.lines || [], e.anchor), B = L.box, { ctx } = h;
    const n = e.values.length - 1, k = h.easeOut(h.clamp01((t - e.t_in - 0.3) / 2.2));
    const yOf = (v) => B.y + B.h - ((v - L.lo) / (L.hi - L.lo)) * B.h;
    ctx.save(); ctx.globalAlpha = a;
    h.panel(L.x, L.y, L.w, L.h, L.r);
    h.titleChip(L.x + 24, L.y + 18, 40, 21, e.title);
    h.text(e.sub || '', L.x + 26, L.y + 82, 16, '#9FB3C8', 'left', 700, 0.5);
    if (e.tag) { const tw = h.measure(e.tag, 14, 800) + 18; h.panel(L.x + L.w - 24 - tw, L.y + 26, tw, 24, 6, 'rgba(251,224,64,0.95)'); h.text(e.tag, L.x + L.w - 24 - tw + 9, L.y + 43, 14, h.COLORS.text_dark, 'left', 800, 0.8); }
    // grid + y labels
    ctx.lineWidth = 1;
    for (let v = L.lo; v <= L.hi + 1e-9; v += L.step) {
      ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.beginPath(); ctx.moveTo(B.x, yOf(v)); ctx.lineTo(B.x + B.w, yOf(v)); ctx.stroke();
      h.text(`${+v.toFixed(2)}`, B.x - 10, yOf(v) + 6, 15, '#9FB3C8', 'right', 700, 0);
    }
    // day labels
    const per = e.per_day || 24;
    (e.days || []).forEach((d, i) => {
      const x = B.x + ((i * per + per / 2) / n) * B.w;
      if (x < B.x + B.w && i % Math.max(1, Math.ceil((e.days.length) / 7)) === 0) h.text(d, x, B.y + B.h + 26, 14, '#9FB3C8', 'center', 700, 0.4);
    });
    // flood-stage lines
    let lastLabel = -1e9;   // flood stages close together: every line is drawn, only labels with room are written
    for (const ln of [...(e.lines || [])].sort((p, q) => q.value - p.value)) {
      if (ln.value < L.lo || ln.value > L.hi) continue;
      ctx.save(); ctx.setLineDash([8, 6]); ctx.strokeStyle = ln.color || '#E2402A'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(B.x, yOf(ln.value)); ctx.lineTo(B.x + B.w, yOf(ln.value)); ctx.stroke(); ctx.restore();
      if (yOf(ln.value) - lastLabel >= 18) { h.text(ln.label, B.x + 8, yOf(ln.value) - 6, 13, ln.color || '#E2402A', 'left', 800, 0.5); lastLabel = yOf(ln.value); }
    }
    // the reading, drawn in as far as k
    const pts = hydroPoints(e.values, L, k * n);
    ctx.strokeStyle = '#3FC8E0'; ctx.lineWidth = 4; ctx.lineJoin = 'round'; ctx.beginPath();
    let pen = false;
    for (const p of pts) { if (!p) { pen = false; continue; } if (pen) ctx.lineTo(p[0], p[1]); else { ctx.moveTo(p[0], p[1]); pen = true; } }
    ctx.stroke();
    if (e.crest && k * n >= e.crest.index) {
      const v = e.values[e.crest.index];
      if (Number.isFinite(v)) {
        const cx = B.x + (e.crest.index / n) * B.w, cy = yOf(v);
        ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2); ctx.fill();
        const tw = h.measure(`CREST ${e.crest.text}`, 17, 800) + 20, tx = Math.min(cx + 12, B.x + B.w - tw);
        h.panel(tx, cy - 16, tw, 30, 6, h.COLORS.yellow);
        h.text(`CREST ${e.crest.text}`, tx + 10, cy + 5, 17, h.COLORS.text_dark, 'left', 800, 0.4);
      }
    }
    ctx.restore();
  },
};
