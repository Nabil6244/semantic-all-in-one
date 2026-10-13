// Weather Teamplate: a soft vignette on the map (the reference's maps sit in dark edges). Not over footage. Event: {type: 'tp_vignette'}.
import { TP } from '../wxu_tp_style.mjs';
import { vignette } from './tp_dip.mjs';

export default {
  type: 'tp_vignette',
  order: 1,
  validate() { return []; },
  draw(e, t, h) {
    const a = h.vis(); if (a <= 0) return;
    const { ctx } = h;
    ctx.save(); ctx.globalAlpha = a; vignette(ctx, TP.vignette.map); ctx.restore();
  },
};
