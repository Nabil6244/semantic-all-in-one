// Weather Teamplate's small tags: tone 'black' is the context tag at the top centre ("NHC BEST TRACK"), tone 'orange' a fact
// tag in the middle of the frame. It opens from its centre, and steps aside under footage (`hide`). Event: {type: 'tp_tag', tone, text, hide}.
import { TP, tagRect, easeOut, shown } from '../wxu_tp_style.mjs';

export default {
  type: 'tp_tag',
  order: 92,
  overFootage: true,
  validate(e) {
    const out = [];
    if (!e.text) out.push('tp_tag needs text');
    if (e.tone && !TP.tag[e.tone]) out.push('tp_tag tone must be black or orange');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.2, 0.3) * shown(e.hide, t, 0.15); if (a <= 0) return;
    const { ctx } = h, tone = e.tone || 'black', T = TP.tag[tone];
    const r = tagRect(tone, h.measure(e.text, T.px, T.weight) + T.spacing * e.text.length);
    const k = easeOut((t - e.t_in) / 0.25), w = r.w * k;
    ctx.save(); ctx.globalAlpha = a;
    ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 10;
    ctx.fillStyle = tone === 'orange' ? TP.orange : TP.black; ctx.fillRect(r.x + (r.w - w) / 2, r.y, w, r.h);
    ctx.shadowColor = 'transparent';
    if (k > 0.85) h.text(e.text, r.x + T.padX, r.y + r.h / 2 + T.px * 0.36, T.px, TP.white, 'left', T.weight, T.spacing);
    ctx.restore();
    h.placed().push(r);
  },
};
