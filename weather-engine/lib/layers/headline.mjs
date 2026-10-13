// The broadcast lower-third (weather/layers/broadcast.py): a coloured kicker tab, a big title on a white bar, an optional
// date line on a dark strip. Bottom left, above the source line. It wipes in from the left and fades out.
// Event: {type: 'headline', kicker, title, sub, tone: news | forecast | post}.

export const TONE = { news: '#C8102E', forecast: '#1F6FD1', post: '#D98A1B' };
export const LT = { x: 44, bottom: 84, titlePx: 50, kickerPx: 22, subPx: 22, padX: 26, titleH: 78, kickerH: 38, subH: 38, minW: 520, maxW: 1500 };

/** The lower-third's boxes in 1080p units (tested: never past the frame, never over the source line). */
export function headlineLayout(titleW, kickerW, subW) {
  const w = Math.min(LT.maxW, Math.max(LT.minW, titleW + 2 * LT.padX, subW + 2 * LT.padX));
  const subY = 1080 - LT.bottom - (subW ? LT.subH : 0);
  const titleY = subY - LT.titleH;
  const kicker = kickerW ? { x: LT.x, y: titleY - LT.kickerH, w: kickerW + 2 * 16, h: LT.kickerH } : null;
  return { x: LT.x, w, title: { y: titleY, h: LT.titleH }, sub: subW ? { y: subY, h: LT.subH } : null, kicker, top: kicker ? kicker.y : titleY };
}

export default {
  type: 'headline',
  order: 95,
  validate(e) {
    const out = [];
    if (!e.title) out.push('headline needs a title');
    if (e.tone && !TONE[e.tone]) out.push('headline tone must be news, forecast or post');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.25, 0.35) * h.vis(); if (a <= 0) return;
    const { ctx } = h;
    // titles too wide for the bar are drawn smaller, never clipped
    let px = LT.titlePx;
    while (px > 30 && h.measure(e.title, px, 800) + 2 * LT.padX > LT.maxW) px -= 2;
    const L = headlineLayout(h.measure(e.title, px, 800), e.kicker ? h.measure(e.kicker, LT.kickerPx, 800) : 0,
      e.sub ? h.measure(e.sub, LT.subPx, 700) : 0);
    const wipe = h.easeOut(h.clamp01((t - e.t_in) / 0.45));
    ctx.save(); ctx.globalAlpha = a;
    ctx.beginPath(); ctx.rect(L.x - 20, L.top - 20, (L.w + 40) * wipe, 1080 - L.top); ctx.clip();
    ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 18; ctx.shadowOffsetY = 4;
    ctx.fillStyle = '#FFFFFF'; ctx.fillRect(L.x, L.title.y, L.w, L.title.h);
    ctx.shadowColor = 'transparent';
    const tone = TONE[e.tone] || TONE.news;
    ctx.fillStyle = tone; ctx.fillRect(L.x, L.title.y, 10, L.title.h);
    h.text(e.title, L.x + LT.padX, L.title.y + L.title.h / 2 + px * 0.36, px, '#0B1A2B', 'left', 800, 0.2);
    if (L.kicker) {
      ctx.fillStyle = tone; ctx.fillRect(L.kicker.x, L.kicker.y, L.kicker.w, L.kicker.h);
      h.text(e.kicker, L.kicker.x + 16, L.kicker.y + L.kicker.h / 2 + LT.kickerPx * 0.36, LT.kickerPx, '#FFFFFF', 'left', 800, 1.2);
    }
    if (L.sub) {
      ctx.fillStyle = 'rgba(8,19,32,0.92)'; ctx.fillRect(L.x, L.sub.y, L.w, L.sub.h);
      h.text(e.sub, L.x + LT.padX, L.sub.y + L.sub.h / 2 + LT.subPx * 0.36, LT.subPx, '#FFFFFF', 'left', 700, 1.2);
    }
    ctx.restore();
    h.placed().push({ x: L.x, y: L.top, w: L.w, h: 1080 - LT.bottom - L.top });
  },
};
