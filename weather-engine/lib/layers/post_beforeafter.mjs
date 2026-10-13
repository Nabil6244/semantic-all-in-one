// post_beforeafter: the big label of a before / after pair of satellite pictures ("BEFORE · AUG 22, 2017" -> "AFTER · AUG 31,
// 2017"), switching with the picture's cross-fade, and a small line naming the picture source.
import { baLabelAt } from '../wxu_post_charts.mjs';

export default {
  type: 'post_beforeafter',
  order: 58,
  validate(e) {
    return Array.isArray(e.frames) && e.frames.length === 2 && e.frames.every((f) => Number.isFinite(f.at) && f.label && f.date)
      ? [] : ['post_beforeafter needs two frames (at, label, date)'];
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.4, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { index, mix } = baLabelAt(e, t), f = e.frames[index], { ctx } = h;
    const fade = mix > 0 && mix < 1 ? Math.abs(mix - 0.5) * 2 : 1;   // the label dips out and back in across the cross-fade
    const px = 46, sub = 22, w = Math.max(h.measure(f.label, px, 800), h.measure(f.date, sub, 700)) + 56, H = 112;
    const x = h.FRAME.w - 63 - w, y = 48;
    ctx.save(); ctx.globalAlpha = a;
    h.panel(x, y, w, H, 14);
    ctx.globalAlpha = a * fade;
    ctx.fillStyle = index === 0 ? '#9FB3C8' : h.COLORS.yellow; h.roundRect(ctx, x, y, 8, H, 4); ctx.fill();
    h.text(f.label, x + 28, y + 56, px, '#FFFFFF', 'left', 800, 1.5);
    h.text(f.date, x + 28, y + 92, sub, index === 0 ? '#9FB3C8' : h.COLORS.yellow, 'left', 700, 0.8);
    ctx.globalAlpha = a;
    if (e.foot) h.text(e.foot, x + w, y + H + 24, 14, 'rgba(255,255,255,0.85)', 'right', 700, 0.5);
    ctx.restore();
  },
};
