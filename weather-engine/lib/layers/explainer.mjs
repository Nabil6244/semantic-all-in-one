// explainer: fixed, words-only cards side by side (weather/layers/explainer.py), e.g. TORNADO WATCH vs TORNADO WARNING in the
// National Weather Service's terms. Each card: a coloured kicker, the meaning, and what to do. They rise in one after the other.
// Event: {type: 'explainer', cards: [{kicker, text, act, color}]}.

export const EX = { w: 600, h: 230, gap: 40, bottom: 130, radius: 18, padX: 30, kickerPx: 30, textPx: 22, actPx: 20, lineH: 30, step: 0.5 };

/** The cards' boxes: centred at the bottom of the frame, above the source line. */
export function explainerRects(n) {
  const total = n * EX.w + (n - 1) * EX.gap, x0 = (1920 - total) / 2;
  return Array.from({ length: n }, (_, i) => ({ x: x0 + i * (EX.w + EX.gap), y: 1080 - EX.bottom - EX.h, w: EX.w, h: EX.h }));
}

/** Words wrapped to lines no wider than `max` (measured with `measure`). */
export function wrap(text, max, measure) {
  const out = []; let line = '';
  for (const w of String(text).split(/\s+/)) {
    const next = line ? `${line} ${w}` : w;
    if (line && measure(next) > max) { out.push(line); line = w; } else line = next;
  }
  if (line) out.push(line);
  return out;
}

export default {
  type: 'explainer',
  order: 63,
  validate(e) {
    if (!Array.isArray(e.cards) || e.cards.length < 1 || e.cards.length > 2) return ['explainer needs 1 or 2 cards'];
    return e.cards.some((c) => !c.kicker || !c.text) ? ['each explainer card needs kicker and text'] : [];
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h;
    explainerRects(e.cards.length).forEach((r, i) => {
      const k = h.easeOut(h.clamp01((t - e.t_in - i * EX.step) / 0.4)); if (k <= 0) return;
      const c = e.cards[i];
      ctx.save(); ctx.globalAlpha = a * k; ctx.translate(0, (1 - k) * 24);
      h.panel(r.x, r.y, r.w, r.h, EX.radius);
      ctx.fillStyle = c.color || h.COLORS.yellow; ctx.fillRect(r.x, r.y, r.w, 8);
      h.text(c.kicker, r.x + EX.padX, r.y + 58, EX.kickerPx, c.color || h.COLORS.yellow, 'left', 800, 0.8);
      const lines = wrap(c.text, r.w - 2 * EX.padX, (s) => h.measure(s, EX.textPx, 700)).slice(0, 3);
      lines.forEach((ln, j) => h.text(ln, r.x + EX.padX, r.y + 104 + j * EX.lineH, EX.textPx, h.COLORS.white, 'left', 700, 0.4));
      if (c.act) h.text(c.act, r.x + EX.padX, r.y + r.h - 26, EX.actPx, c.color || h.COLORS.yellow, 'left', 800, 1.2);
      ctx.restore();
      h.placed().push(r);
    });
  },
};
