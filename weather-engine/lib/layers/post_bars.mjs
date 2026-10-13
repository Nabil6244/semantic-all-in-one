// post_bars: observed totals for several places as a bar chart ("RAINFALL TOTALS · AUG 25–SEP 1, 2017 · OBSERVED"): the bars
// grow one after another and each value counts up to the number it is given.
import { POST, barsLayout, barGrow, barLength, countText } from '../wxu_post_charts.mjs';

export default {
  type: 'post_bars',
  order: 60,
  validate(e) {
    const bad = [];
    if (!Array.isArray(e.bars) || e.bars.length < 1 || e.bars.length > 8) bad.push('post_bars needs 1 to 8 bars');
    else e.bars.forEach((b, i) => { if (!b.label || !Number.isFinite(b.value) || !b.text) bad.push(`post_bars bar ${i + 1} needs label, value and text`); });
    if (!e.title) bad.push('post_bars needs a title');
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const L = barsLayout(e.bars.length, e.anchor), b = POST.bars, { ctx } = h;
    const top = Math.max(...e.bars.map((x) => x.value));
    const slide = (1 - h.easeOut(h.clamp01((t - e.t_in) / 0.35))) * 30 * (e.anchor === 'l' ? -1 : 1);
    ctx.save(); ctx.globalAlpha = a; ctx.translate(slide, 0);
    h.panel(L.x, L.y, L.w, L.h, L.r);
    h.titleChip(L.x + 24, L.y + 20, 42, 22, e.title);
    if (e.tag) { const tw = h.measure(e.tag, 14, 800) + 18; h.panel(L.x + L.w - 24 - tw, L.y + 29, tw, 24, 6, 'rgba(251,224,64,0.95)'); h.text(e.tag, L.x + L.w - 24 - tw + 9, L.y + 46, 14, h.COLORS.text_dark, 'left', 800, 0.8); }
    h.text(e.sub || '', L.x + 26, L.y + 84, 17, '#9FB3C8', 'left', 700, 0.5);
    e.bars.forEach((bar, i) => {
      const r = L.rows[i], k = barGrow(t, e.t_in, i);
      h.text(bar.label, L.x + 26, r.cy + 7, 19, '#FFFFFF', 'left', 800, 0.4);
      if (bar.note) h.text(bar.note, L.x + 26, r.cy + 26, 12, h.COLORS.yellow, 'left', 700, 0.6);
      ctx.fillStyle = 'rgba(255,255,255,0.08)'; h.roundRect(ctx, L.barX, r.cy - b.barH / 2, L.barMax, b.barH, 7); ctx.fill();
      if (k > 0) {
        const len = barLength(bar.value, top, L.barMax) * k;
        const g = ctx.createLinearGradient(L.barX, 0, L.barX + L.barMax, 0);
        g.addColorStop(0, '#2F78D0'); g.addColorStop(1, '#3FC8E0');
        ctx.fillStyle = g; h.roundRect(ctx, L.barX, r.cy - b.barH / 2, len, b.barH, 7); ctx.fill();
      }
      h.text(countText(bar.text, k, e.decimals), L.valueX, r.cy + 10, 28, '#FFFFFF', 'right', 800, -0.3);
    });
    h.text(`${e.unit ? `INCHES · ` : ''}${e.foot || ''}`, L.x + 26, L.y + L.h - 22, 15, '#9FB3C8', 'left', 600, 0.4);
    ctx.restore();
  },
};
