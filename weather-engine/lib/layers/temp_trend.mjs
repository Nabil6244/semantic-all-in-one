// temp_trend: the week's highs and lows of one city as a line chart in a panel like the forecast strip. The lines draw in from
// the first day, each point pops when its line reaches it, and its number (formatted by weather/layers/trend.py) shows above
// the high or below the low; day names along the bottom.
import { TREND, trendLayout, trendPoints, drawProgress, partialLine, popScale } from '../wxu_auto_trend.mjs';

const HIGH = '#FF8A3D', LOW = '#5AB0FF', MUTED = '#9FB3C8';

export default {
  type: 'temp_trend',
  order: 55,
  validate(e) {
    const bad = [];
    if (!e.title) bad.push('temp_trend needs title');
    if (!(Array.isArray(e.days) && e.days.length >= 3 && e.days.length <= 7)) { bad.push('temp_trend needs 3 to 7 days'); return bad; }
    e.days.forEach((d, i) => {
      if (!d.dow || !d.hi || !Number.isFinite(d.hi_v)) bad.push(`temp_trend day ${i + 1} needs dow, hi and hi_v`);
      if (d.lo && !Number.isFinite(d.lo_v)) bad.push(`temp_trend day ${i + 1} has lo without lo_v`);
    });
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h, n = e.days.length, L = trendLayout(n), P = trendPoints(e.days, L);
    const slide = (1 - h.easeOut(h.clamp01((t - e.t_in) / 0.35))) * 24;
    ctx.save(); ctx.globalAlpha = a; ctx.translate(0, slide);
    h.panel(L.x, L.y, L.w, L.h, L.r);
    h.titleChip(L.title.x, L.title.y, L.title.h, L.title.px, e.title);
    e.days.forEach((d, i) => {   // day names and faint column guides
      h.text(d.dow, L.cols[i], L.dowY, TREND.dowPx, h.COLORS.white, 'center', 800, 1.2);
      if (i > 0) {
        const x = L.x + TREND.padX + i * L.cellW;
        ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x, L.plot.top); ctx.lineTo(x, L.dowY - 30); ctx.stroke();
      }
    });
    const p = drawProgress(t, e.t_in, n);
    for (const [pts, color] of [[P.highs, HIGH], [P.lows, LOW]]) {
      const line = partialLine(pts, p);
      if (line.length > 1) {
        ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
        ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 6;
        ctx.beginPath(); line.forEach((q, k) => (k ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y))); ctx.stroke(); ctx.restore();
      }
    }
    for (const [pts, color, above] of [[P.highs, HIGH, true], [P.lows, LOW, false]]) {
      for (const q of pts) {
        const s = popScale(t, e.t_in, q.i, n); if (s <= 0) continue;
        ctx.save(); ctx.translate(q.x, q.y); ctx.scale(s, s);
        ctx.fillStyle = color; ctx.strokeStyle = h.COLORS.white; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.arc(0, 0, TREND.dot, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.restore();
        ctx.save(); ctx.globalAlpha = a * Math.min(1, s);
        h.text(q.text, q.x, above ? q.y - 16 : q.y + 16 + TREND.numPx * 0.75, TREND.numPx, above ? h.COLORS.white : MUTED, 'center', 800, -0.3);
        ctx.restore();
      }
    }
    ctx.restore();
  },
};
