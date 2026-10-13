// A number that counts up ("TORNADO REPORTS 46 PRELIMINARY"), in a panel at a corner. The value and words come from
// weather/layers/counters.py (the numbers report lists the value with its source). Event: {type: 'counter', value, label,
// sub, anchor, count_s}.
import { countAt, counterRect, NEWS } from '../wxu_news_anim.mjs';

export default {
  type: 'counter',
  order: 60,
  validate(e) {
    const out = [];
    if (!Number.isInteger(e.value) || e.value < 0) out.push('counter needs a whole, non-negative value');
    if (!e.label) out.push('counter needs a label');
    if (e.anchor && !['tr', 'tl', 'br', 'bl'].includes(e.anchor)) out.push('counter anchor must be tr, tl, br or bl');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h, C = NEWS.counter;
    const w = Math.max(C.minW, h.measure(e.label, C.labelPx, 800) + 2 * C.padX, h.measure(String(e.value), C.valuePx, 800) + 2 * C.padX,
      e.sub ? h.measure(e.sub, C.subPx, 700) + 2 * C.padX : 0);
    const r = counterRect(e.anchor || 'tr', w);
    const slide = (1 - h.easeOut(h.clamp01((t - e.t_in) / 0.35))) * 16;
    ctx.save(); ctx.globalAlpha = a; ctx.translate(0, -slide);
    h.panel(r.x, r.y, r.w, r.h, 16);
    ctx.fillStyle = h.COLORS.yellow; ctx.fillRect(r.x, r.y + 14, 6, r.h - 28);
    h.text(e.label, r.x + C.padX, r.y + 38, C.labelPx, h.COLORS.white, 'left', 800, 0.8);
    h.text(String(countAt(e, t)), r.x + C.padX, r.y + 38 + C.valuePx * 0.95, C.valuePx, h.COLORS.white, 'left', 800, -1);
    if (e.sub) h.text(e.sub, r.x + C.padX, r.y + r.h - 18, C.subPx, h.COLORS.yellow, 'left', 700, 0.8);
    ctx.restore();
    h.placed().push(r);
  },
};
