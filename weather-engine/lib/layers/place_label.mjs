// A place on the map (weather/layers/broadcast.py): a white dot with a dark ring and the place's name beside it, so the
// viewer always knows where they are. The name goes right of the dot, or left when that side is taken or off frame.
// Event: {type: 'place_label', lon, lat, text}.

export const PL = { px: 26, dot: 7, gap: 12, padX: 10, h: 38 };

export default {
  type: 'place_label',
  order: 85,   // after the data panels, so a name never hides under one (it is left out instead)
  validate(e) {
    const out = [];
    if (!Number.isFinite(e.lon) || !Number.isFinite(e.lat)) out.push('place_label needs lon and lat');
    if (!e.text) out.push('place_label needs text');
    return out;
  },
  draw(e, t, h) {
    const q = h.project(e.lon, e.lat); if (!q) return;
    const x = q.x / h.S, y = q.y / h.S;
    if (x < 0 || y < 0 || x > 1920 || y > 1080) return;
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.3, 0.3) * h.vis(); if (a <= 0) return;
    const { ctx } = h;
    const w = h.measure(e.text, PL.px, 800) + 2 * PL.padX;
    const taken = [...h.placed(), ...(h.panels ? h.panels() : [])];
    const hits = (bx) => bx < 40 || bx + w > 1880 || taken.some((r) => bx - 4 < r.x + r.w && bx + w + 4 > r.x && y - PL.h / 2 - 4 < r.y + r.h && y + PL.h / 2 + 4 > r.y);
    const dotHit = taken.some((r) => x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h);
    let bx = x + PL.dot + PL.gap;
    if (hits(bx)) bx = x - PL.dot - PL.gap - w;
    if (dotHit || hits(bx)) return;   // no room on either side (a panel, another name): leave this place out rather than overlap
    const pop = h.easeOut(h.clamp01((t - e.t_in) / 0.3));
    ctx.save(); ctx.globalAlpha = a;
    ctx.beginPath(); ctx.arc(x, y, (PL.dot + 3) * pop, 0, Math.PI * 2); ctx.fillStyle = 'rgba(8,19,32,0.85)'; ctx.fill();
    ctx.beginPath(); ctx.arc(x, y, PL.dot * pop, 0, Math.PI * 2); ctx.fillStyle = '#FFFFFF'; ctx.fill();
    h.panel(bx, y - PL.h / 2, w, PL.h, 6, 'rgba(8,19,32,0.78)');
    h.text(e.text, bx + PL.padX, y + PL.px * 0.36, PL.px, '#FFFFFF', 'left', 800, 0.8);
    ctx.restore();
    h.placed().push({ x: bx, y: y - PL.h / 2, w, h: PL.h });
  },
};
