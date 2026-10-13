// Weather Teamplate's number (a Weather counter, re-typed by weather/teamplate apply_spec): a big white number counting up over
// a darkened frame with its label typed beside it ("5  EXTREME WIND WARNINGS ISSUED"), then a compact orange tag top right for
// the rest of its time. The value, label and sub are the counter's own (the numbers report lists them with their source).
// Event: {type: 'tp_stat', value, label, sub, count_s, big_in, big_out}.
import { countAt } from '../wxu_news_anim.mjs';
import { TP, statPhase, compactRect, easeOut } from '../wxu_tp_style.mjs';

export default {
  type: 'tp_stat',
  order: 94,
  overFootage: true,
  validate(e) {
    const out = [];
    if (!Number.isInteger(e.value) || e.value < 0) out.push('tp_stat needs a whole, non-negative value');
    if (!e.label) out.push('tp_stat needs a label');
    if (!(Number.isFinite(e.big_in) && Number.isFinite(e.big_out))) out.push('tp_stat needs big_in and big_out');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.2, 0.3); if (a <= 0) return;
    const { ctx } = h, S = TP.stat, ph = statPhase(e, t);
    if (ph.phase === 'none') return;
    if (ph.phase === 'compact') {
      const txt = `${e.value}  ${e.label}`, r = compactRect(h.measure(txt, S.compactPx, 800) + 0.8 * txt.length);
      const k = easeOut((t - e.big_out) / 0.3);
      ctx.save(); ctx.globalAlpha = a * k;
      ctx.fillStyle = TP.orange; ctx.fillRect(r.x, r.y, r.w, r.h);
      h.text(txt, r.x + 18, r.y + r.h / 2 + S.compactPx * 0.36, S.compactPx, TP.white, 'left', 800, 0.8);
      ctx.restore();
      h.placed().push(r);
      return;
    }
    const big = h.lifeAlpha(t, e.big_in, e.big_out, 0.25, 0.3);
    const n = String(countAt({ ...e, t_in: e.big_in }, t));
    const final = h.measure(String(e.value), S.valuePx, 900);
    ctx.save(); ctx.globalAlpha = a * big;
    ctx.shadowColor = TP.shadow; ctx.shadowBlur = 24; ctx.shadowOffsetY = 3;
    h.text(n, S.left + final, S.baseline, S.valuePx, TP.white, 'right', 900, -2);
    const lx = S.left + final + S.gap;
    if (ph.typed > 0) {
      const label = e.label.slice(0, Math.ceil(e.label.length * ph.typed));
      h.text(label, lx, S.baseline - (e.sub ? S.subPx + 14 : 0), S.labelPx, TP.white, 'left', 700, 2.2);
      if (e.sub && ph.typed >= 1) h.text(e.sub, lx, S.baseline, S.subPx, TP.orange, 'left', 800, 2);
    }
    ctx.restore();
  },
};
