// post_record: a record badge -- "WETTEST DAY ON RECORD" (or "3RD WETTEST ..."), the place, the new value and its date, and the
// old record it beat (or the record it did not), with when the station's records begin. A stamp pops in, then the old value.
import { recordLayout } from '../wxu_post_charts.mjs';

const KIND = { rain: '#2F78D0', snow: '#7FB8E8', heat: '#E2402A', cold: '#3FA7E0' };

export default {
  type: 'post_record',
  order: 62,
  validate(e) {
    const bad = [];
    for (const k of ['headline', 'place', 'value', 'date', 'prev_value', 'prev_date']) if (!e[k]) bad.push(`post_record needs ${k}`);
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const L = recordLayout(e.anchor), { ctx } = h, col = KIND[e.kind] || h.COLORS.red;
    const k = h.clamp01((t - e.t_in) / 0.45), pop = 1 + 0.25 * (1 - h.easeOut(k));
    ctx.save(); ctx.globalAlpha = a;
    h.panel(L.x, L.y, L.w, L.h, L.r);
    // the stamp: a coloured band with the headline (it shrinks into place)
    ctx.save(); ctx.translate(L.x + L.w / 2, L.y + 58); ctx.scale(pop, pop);
    const hw = Math.min(L.w - 40, h.measure(e.headline, 30, 800) + 48);
    ctx.fillStyle = col; h.roundRect(ctx, -hw / 2, -32, hw, 64, 12); ctx.fill();
    h.text(e.headline, 0, 11, 30, '#FFFFFF', 'center', 800, 0.8);
    ctx.restore();
    h.text(e.place, L.x + L.w / 2, L.y + 128, 22, h.COLORS.yellow, 'center', 800, 1.2);
    h.text(e.value, L.x + L.w / 2, L.y + 214, 84, '#FFFFFF', 'center', 800, -1);
    h.text(e.date, L.x + L.w / 2, L.y + 250, 22, '#FFFFFF', 'center', 700, 0.8);
    const k2 = h.clamp01((t - e.t_in - 0.7) / 0.4);
    if (k2 > 0) {
      ctx.save(); ctx.globalAlpha = a * h.easeOut(k2);
      ctx.strokeStyle = 'rgba(255,255,255,0.14)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(L.x + 30, L.y + 274); ctx.lineTo(L.x + L.w - 30, L.y + 274); ctx.stroke();
      h.text(`${e.prev_label || 'PREVIOUS RECORD'}: ${e.prev_value} · ${e.prev_date}`, L.x + L.w / 2, L.y + 310, 20, '#9FB3C8', 'center', 700, 0.5);
      h.text([e.since, e.foot].filter(Boolean).join(' · '), L.x + L.w / 2, L.y + 346, 15, '#9FB3C8', 'center', 600, 0.4);
      ctx.restore();
    }
    if (e.tag) { const tw = h.measure(e.tag, 14, 800) + 18; h.panel(L.x + L.w - 20 - tw, L.y - 12, tw, 24, 6, 'rgba(251,224,64,0.95)'); h.text(e.tag, L.x + L.w - 20 - tw + 9, L.y + 5, 14, h.COLORS.text_dark, 'left', 800, 0.8); }
    ctx.restore();
  },
};
