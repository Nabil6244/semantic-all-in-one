// Hurricane positions: category-coloured dots along an NHC track, each popping in as the track line reaches it, and label
// chips ("CAT 4 · 155 MPH · WED 2 PM") on the points weather/layers/storms.py labelled. Event: {type: 'storm_points',
// points: [{lon, lat, color, label, at, size, ring}], name}.
import { NEWS, pointChip, popIn } from '../wxu_news_anim.mjs';

const overlaps = (r, taken) => taken.some((o) => r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h);

export default {
  type: 'storm_points',
  order: 40,
  validate(e) {
    if (!Array.isArray(e.points) || !e.points.length) return ['storm_points needs points'];
    return e.points.some((p) => !Number.isFinite(p.lon) || !Number.isFinite(p.lat) || !Number.isFinite(p.at)) ? ['storm_points: every point needs lon, lat and at'] : [];
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.2, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h, P = NEWS.points;
    ctx.save(); ctx.globalAlpha = a;
    const labels = [];
    for (const p of e.points) {
      const k = popIn(p, t); if (k <= 0) continue;
      const q = h.project(p.lon, p.lat); if (!q) continue;
      const x = q.x / h.S, y = q.y / h.S;
      if (x < -20 || y < -20 || x > h.FRAME.w + 20 || y > h.FRAME.h + 20) continue;
      const r = (p.size || 9) * (0.6 + 0.4 * k);
      ctx.save(); ctx.globalAlpha = a * k;
      ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 6;
      ctx.fillStyle = p.color || '#FFFFFF'; ctx.strokeStyle = '#FFFFFF'; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      if (p.ring) { ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, r + 6, 0, Math.PI * 2); ctx.stroke(); }
      ctx.restore();
      if (p.label) labels.push({ p, x, y, k });
    }
    const taken = h.placed();
    for (const { p, x, y, k } of labels) {
      const w = h.measure(p.label, P.px, 800) + 2 * P.padX;
      let r = pointChip(x, y, w);
      for (const dy of [0, -44, 44, -88, 88]) { const c = { ...r, y: r.y + dy }; if (!overlaps(c, taken)) { r = c; break; } }
      taken.push(r);
      ctx.save(); ctx.globalAlpha = a * k;
      h.panel(r.x, r.y, r.w, r.h, 8);
      ctx.fillStyle = p.color || '#FFFFFF'; ctx.fillRect(r.x, r.y + 6, 4, r.h - 12);
      h.text(p.label, r.x + P.padX, r.y + r.h / 2 + P.px * 0.36, P.px, h.COLORS.white, 'left', 800, 0.4);
      ctx.restore();
    }
    ctx.restore();
  },
};
