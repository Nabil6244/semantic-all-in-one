// storm_stats: a storm's record card (weather/layers/stormstats.py) -- its name, then one row per fact (PEAK STRENGTH
// "CAT 5 · 160 MPH", LOWEST PRESSURE "937 MB", LANDFALL "CAT 4 · 150 MPH"), each with its date and time, and the source
// at the foot. Rows slide in one after the other. Every string is written by Python (the numbers report lists each value).
// Event: {type: 'storm_stats', title, rows: [{label, value, sub}], foot, anchor: 'l' | 'r'}.
import { sidePanel } from '../wxu_post_charts.mjs';

export const SS = { w: 560, titleH: 86, rowH: 108, foot: 50, radius: 18, padX: 30, titlePx: 30, labelPx: 17, valuePx: 44, subPx: 17, step: 0.35 };

/** The card's box: at the side, vertically centred between the HUD title and the source line. */
export function statsLayout(rows, anchor = 'l') {
  return sidePanel(SS.w, SS.titleH + rows * SS.rowH + SS.foot, anchor);
}

export default {
  type: 'storm_stats',
  order: 61,
  validate(e) {
    const bad = [];
    if (!e.title) bad.push('storm_stats needs a title');
    if (!Array.isArray(e.rows) || !e.rows.length || e.rows.length > 4) bad.push('storm_stats needs 1 to 4 rows');
    else for (const r of e.rows) if (!r.label || !r.value) bad.push('each storm_stats row needs label and value');
    if (e.anchor && !['l', 'r'].includes(e.anchor)) bad.push('storm_stats anchor must be l or r');
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const L = statsLayout(e.rows.length, e.anchor || 'l'), { ctx } = h;
    ctx.save(); ctx.globalAlpha = a;
    h.panel(L.x, L.y, L.w, L.h, SS.radius);
    ctx.fillStyle = h.COLORS.red; ctx.fillRect(L.x, L.y + 18, 6, SS.titleH - 36);
    h.text(e.title, L.x + SS.padX, L.y + SS.titleH / 2 + SS.titlePx * 0.36, SS.titlePx, h.COLORS.white, 'left', 800, 0.6);
    e.rows.forEach((r, i) => {
      const k = h.easeOut(h.clamp01((t - e.t_in - 0.3 - i * SS.step) / 0.35)); if (k <= 0) return;
      const y = L.y + SS.titleH + i * SS.rowH;
      ctx.save(); ctx.globalAlpha = a * k; ctx.translate((1 - k) * -18, 0);
      ctx.fillStyle = 'rgba(255,255,255,0.12)'; ctx.fillRect(L.x + SS.padX, y, L.w - 2 * SS.padX, 2);
      h.text(r.label, L.x + SS.padX, y + 30, SS.labelPx, h.COLORS.yellow, 'left', 800, 1.2);
      h.text(r.value, L.x + SS.padX, y + 30 + SS.valuePx, SS.valuePx, h.COLORS.white, 'left', 800, -0.5);
      if (r.sub) h.text(r.sub, L.x + L.w - SS.padX, y + 30, SS.subPx, '#9FB3C8', 'right', 700, 0.6);
      ctx.restore();
    });
    if (e.foot) h.text(e.foot, L.x + SS.padX, L.y + L.h - 20, 14, '#9FB3C8', 'left', 700, 0.8);
    ctx.restore();
    h.placed().push({ x: L.x, y: L.y, w: L.w, h: L.h });
  },
};
