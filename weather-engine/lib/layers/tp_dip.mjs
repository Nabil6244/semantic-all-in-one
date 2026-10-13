// Weather Teamplate: the frame dims while a title card or a big number is up (the reference darkens its footage under every
// card), with a soft vignette. Drawn over footage and map alike, under the card itself. Event: {type: 'tp_dip'}.
import { TP } from '../wxu_tp_style.mjs';

export function vignette(ctx, strength) {
  const g = ctx.createRadialGradient(960, 540, 300, 960, 540, 1150);
  g.addColorStop(0, 'rgba(0,0,0,0)');
  g.addColorStop(1, `rgba(0,0,0,${strength})`);
  ctx.fillStyle = g; ctx.fillRect(0, 0, 1920, 1080);
}

export default {
  type: 'tp_dip',
  order: 2,
  overFootage: true,
  validate() { return []; },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.35, 0.45); if (a <= 0) return;
    const { ctx } = h;
    ctx.save(); ctx.globalAlpha = a;
    ctx.fillStyle = `rgba(0,0,0,${TP.vignette.flat})`; ctx.fillRect(0, 0, 1920, 1080);
    vignette(ctx, TP.vignette.dip);
    ctx.restore();
  },
};
