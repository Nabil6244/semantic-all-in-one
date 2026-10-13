// The credit chip of event footage ("VIDEO: NASA · SEP 28, 2022 · GULF OF MEXICO", or "CC BY 4.0 — <author>"), bottom left.
// Event (weather/news/approval.py -> a footage_credit row): {type: 'footage_credit', text}.
//
// It is meant to sit ON the footage. Today every weather graphic hides under full-screen footage (wx_draw.mjs stops drawing
// when footage covers the frame), so this chip only shows around the footage's edges; `overFootage: true` asks the integrator
// to draw it over footage instead (docs/weather/agent_phase3.md, request R3). Until then the credit is also in the video's
// description credits.
import { creditRect, NEWS } from '../wxu_news_anim.mjs';

export default {
  type: 'footage_credit',
  order: 90,
  overFootage: true,
  validate(e) { return e.text ? [] : ['footage_credit needs text']; },
  draw(e, t, h) {
    const vis = h.footage ? 1 : h.vis();   // h.footage: the integrator's over-footage pass (request R3)
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.3, 0.3) * vis; if (a <= 0) return;
    const { ctx } = h, C = NEWS.credit;
    const r = creditRect(h.measure(e.text, C.px, 700) + 2 * C.padX);
    ctx.save(); ctx.globalAlpha = a;
    h.panel(r.x, r.y, r.w, r.h, 8, 'rgba(8,19,32,0.78)');
    h.text(e.text, r.x + C.padX, r.y + r.h / 2 + C.px * 0.36, C.px, h.COLORS.white, 'left', 700, 0.5);
    ctx.restore();
  },
};
