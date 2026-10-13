// post_chip: an observed value at a place on the map -- a station's rain total ("HOUSTON (IAH) 31.26 IN") or a river crest
// ("BUFFALO BAYOU 41.9 FT · CREST AUG 28 · MAJOR FLOOD"). The number counts up to the value it is given; a tag
// (PROVISIONAL, PRELIMINARY, 1 DAY MISSING, RECORD CREST) sits above the chip.
import { POST, chipLayout, countText } from '../wxu_post_charts.mjs';

const ACCENT = { rain: '#3FC8E0', river: '#3FC8E0' };

export default {
  type: 'post_chip',
  order: 55,
  validate(e) {
    const bad = [];
    if (!(Number.isFinite(e.lon) && Number.isFinite(e.lat))) bad.push('post_chip needs lon and lat');
    if (!e.label || !e.value) bad.push('post_chip needs label and value');
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.markerPop, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const q = h.project(e.lon, e.lat); if (!q) return;
    const x = q.x / h.S, y = q.y / h.S, c = POST.chip, { ctx } = h;
    if (x < 0 || y < 0 || x > h.FRAME.w || y > h.FRAME.h) return;
    const k = h.clamp01((t - e.t_in - 0.15) / 0.9);
    const value = e.count ? countText(e.value, k, e.decimals) : e.value;
    const vw = h.measure(e.value, c.valuePx, 800), lw = Math.max(h.measure(e.label, c.labelPx, 800), e.sub ? h.measure(e.sub, c.subPx, 700) : 0);
    const L = chipLayout(x, y, c.padX * 2 + 6 + vw + c.gap + lw, e.side || 'auto');
    const accent = e.accent || ACCENT[e.kind] || h.COLORS.yellow;
    const pop = h.easeOut(h.clamp01((t - e.t_in) / h.TIMING.markerPop));
    ctx.save(); ctx.globalAlpha = a;
    // the place: a ring dot
    ctx.save(); ctx.translate(x, y); ctx.scale(pop, pop);
    ctx.fillStyle = h.COLORS.panel; ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 3.5;
    ctx.beginPath(); ctx.arc(0, 0, c.dot, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = accent; ctx.beginPath(); ctx.arc(0, 0, 4, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    const slide = (1 - h.easeOut(h.clamp01((t - e.t_in) / h.TIMING.chipIn))) * 8, y0 = L.y + slide;
    h.panel(L.x, y0, L.w, L.h, L.r);
    ctx.fillStyle = accent; h.roundRect(ctx, L.x, y0, 6, L.h, 3); ctx.fill();
    const vx = L.x + c.padX + 6;
    h.text(value, vx, y0 + L.h / 2 + c.valuePx * 0.36, c.valuePx, '#FFFFFF', 'left', 800, -0.4);
    const lx = vx + vw + c.gap;
    h.text(e.label, lx, y0 + (e.sub ? L.h / 2 - 4 : L.h / 2 + c.labelPx * 0.36), c.labelPx, '#FFFFFF', 'left', 800, 0.6);
    if (e.sub) h.text(e.sub, lx, y0 + L.h / 2 + c.subPx + 4, c.subPx, h.COLORS.yellow, 'left', 700, 0.7);
    if (e.tag) {
      const px = 14, tw = h.measure(e.tag, px, 800) + 18;
      h.panel(L.x, y0 - 28, tw, 24, 6, e.tag.includes('RECORD') ? h.COLORS.red : 'rgba(251,224,64,0.95)');
      h.text(e.tag, L.x + 9, y0 - 11, px, e.tag.includes('RECORD') ? '#FFFFFF' : h.COLORS.text_dark, 'left', 800, 0.8);
    }
    ctx.restore();
  },
};
