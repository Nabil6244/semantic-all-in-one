// post_rainlegend: the colour key of a rain map, in inches ("RAINFALL · AUG 25 7 AM – SEP 1 7 AM CDT · MRMS radar estimate").
import { rainLegendLayout } from '../wxu_post_charts.mjs';

export default {
  type: 'post_rainlegend',
  order: 52,
  validate(e) {
    return Array.isArray(e.stops) && e.stops.length >= 2 && e.stops.every((s) => s.color && s.text) ? [] : ['post_rainlegend needs stops (colour and text each)'];
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.4, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const L = rainLegendLayout(e.stops.length), { ctx } = h;
    ctx.save(); ctx.globalAlpha = a;
    h.panel(L.x, L.y, L.w, L.h, L.r);
    h.text(`${e.title || 'RAINFALL'} (${e.unit || 'IN'})`, L.x + 22, L.y + 34, 20, '#FFFFFF', 'left', 800, 0.8);
    h.text(e.sub || '', L.x + L.w - 22, L.y + 34, 15, '#9FB3C8', 'right', 700, 0.4);
    e.stops.forEach((s, i) => {
      ctx.fillStyle = s.color; ctx.fillRect(L.cells[i], L.barY, L.cellW + 0.5, L.barH);
      h.text(s.text, L.cells[i] + 3, L.barY + L.barH + 20, 14, '#FFFFFF', 'left', 700, 0);
    });
    h.text([e.foot, e.peak].filter(Boolean).join(' · '), L.x + L.w - 22, L.y + L.h - 10, 13, '#9FB3C8', 'right', 600, 0.4);
    ctx.restore();
  },
};
