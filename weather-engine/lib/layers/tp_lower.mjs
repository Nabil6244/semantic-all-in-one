// Weather Teamplate's lower third (a Weather headline, re-typed): no bar, as in the reference: a small orange kicker tag, the
// title in heavy white with a soft shadow, and a line of small capitals under it; bottom left, clear of the source line.
// It steps aside under footage (`hide`). Event: {type: 'tp_lower', kicker, title, sub, hide}.
import { TP, easeOut, shown } from '../wxu_tp_style.mjs';

export default {
  type: 'tp_lower',
  order: 93,
  overFootage: true,
  validate(e) { return e.title ? [] : ['tp_lower needs a title']; },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.25, 0.35) * shown(e.hide, t, 0.15); if (a <= 0) return;
    const { ctx } = h, L = TP.lower;
    let px = L.titlePx;
    while (px > 34 && h.measure(e.title, px, 800) > 1400) px -= 2;
    const subY = 1080 - L.bottom, titleY = subY - (e.sub ? L.subPx + 18 : 0), kickY = titleY - px - 14;
    const k = easeOut((t - e.t_in) / 0.4), dx = (1 - k) * -24;
    ctx.save(); ctx.globalAlpha = a * k; ctx.translate(dx, 0);
    if (e.kicker) {
      const w = h.measure(e.kicker, L.kickerPx, 800) + 1.5 * e.kicker.length + 28;
      ctx.fillStyle = TP.orange; ctx.fillRect(L.left, kickY - L.kickerH + 8, w, L.kickerH);
      h.text(e.kicker, L.left + 14, kickY - L.kickerH / 2 + 8 + L.kickerPx * 0.36, L.kickerPx, TP.white, 'left', 800, 1.5);
    }
    ctx.shadowColor = TP.shadow; ctx.shadowBlur = 18; ctx.shadowOffsetY = 3;
    h.text(e.title, L.left, titleY, px, TP.white, 'left', 800, 0.5);
    if (e.sub) h.text(e.sub, L.left, subY, L.subPx, 'rgba(255,255,255,0.9)', 'left', 600, 1.6);
    ctx.restore();
  },
};
