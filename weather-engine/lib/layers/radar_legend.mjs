// The radar legend: the dBZ colour bar of the radar loop, with words instead of numbers (LIGHT ... HEAVY ... HAIL), bottom
// right. Event (weather/layers/radar.py): {type: 'radar_legend', stops: [{dbz, color}], labels: [{dbz, text}], title}.
import { dbzX, legendRect, NEWS } from '../wxu_news_anim.mjs';

export default {
  type: 'radar_legend',
  order: 55,
  validate(e) {
    const out = [];
    if (!Array.isArray(e.stops) || e.stops.length < 2) out.push('radar_legend needs at least 2 stops');
    else if (e.stops.some((s, i) => !Number.isFinite(s.dbz) || !s.color || (i && s.dbz <= e.stops[i - 1].dbz))) out.push('radar_legend stops need dbz (rising) and color');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h, L = NEWS.legend, r = legendRect();
    ctx.save(); ctx.globalAlpha = a;
    h.panel(r.x, r.y, r.w, r.h, 12);
    const x0 = r.x + 18, w = r.w - 36, y = r.y + 40;
    h.text(e.title || 'RADAR', x0, r.y + 26, L.titlePx, h.COLORS.yellow, 'left', 800, 1);
    const g = ctx.createLinearGradient(x0, 0, x0 + w, 0);
    e.stops.forEach((s) => g.addColorStop((dbzX(s.dbz, e.stops, x0, w) - x0) / w, s.color));
    ctx.fillStyle = g; h.roundRect(ctx, x0, y, w, L.barH, 4); ctx.fill();
    for (const lb of e.labels || []) {
      const x = dbzX(lb.dbz, e.stops, x0, w);
      ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fillRect(x - 1, y + L.barH, 2, 6);
      h.text(lb.text, Math.min(x0 + w, Math.max(x0, x)), y + L.barH + 24, L.px, h.COLORS.white, 'center', 800, 0.6);
    }
    ctx.restore();
  },
};
