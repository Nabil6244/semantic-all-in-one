// SPC storm reports: a dot per report (tornado red, wind blue, hail green) appearing in the order the reports came in, and a
// legend on the right whose counts tick up with the dots, titled PRELIMINARY (SPC reports are preliminary until reviewed).
// Event (weather/layers/severe.py): {type: 'storm_reports', points: [{lon, lat, kind, at}], legend: [{kind, label, color, total}],
// title, sub}.
import { NEWS, popIn, reportsRect, revealed } from '../wxu_news_anim.mjs';

export default {
  type: 'storm_reports',
  order: 45,
  validate(e) {
    const out = [];
    if (!Array.isArray(e.points)) out.push('storm_reports needs points');
    else if (e.points.some((p) => !Number.isFinite(p.lon) || !Number.isFinite(p.lat) || !Number.isFinite(p.at) || !p.kind)) out.push('storm_reports: every point needs lon, lat, kind and at');
    if (e.legend && e.legend.length && !/PRELIMINARY/i.test(`${e.title} ${e.sub}`)) out.push('storm_reports must be labelled PRELIMINARY');
    return out;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.3, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h, R = NEWS.reports;
    const colors = Object.fromEntries((e.legend || []).map((l) => [l.kind, l.color]));
    ctx.save(); ctx.globalAlpha = a;
    for (const p of e.points) {
      const k = popIn(p, t, 0.25); if (k <= 0) continue;
      const q = h.project(p.lon, p.lat); if (!q) continue;
      const x = q.x / h.S, y = q.y / h.S;
      if (x < -10 || y < -10 || x > h.FRAME.w + 10 || y > h.FRAME.h + 10) continue;
      ctx.globalAlpha = a * k;
      ctx.fillStyle = colors[p.kind] || '#FFFFFF'; ctx.strokeStyle = 'rgba(0,0,0,0.65)'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(x, y, (p.kind === 'tornado' ? 7 : 5.5) * (1 + 0.6 * (1 - k)), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
    ctx.globalAlpha = a;
    if (e.legend && e.legend.length) {
      const { byKind } = revealed(e.points, t);
      const widest = Math.max(...e.legend.map((l) => h.measure(l.label, R.px, 800)), h.measure(e.sub || '', 15, 800) - 70);
      const r = reportsRect(e.legend.length, widest);
      h.panel(r.x, r.y, r.w, r.h, 12);
      h.text(e.title || 'STORM REPORTS', r.x + R.padX, r.y + R.padY + 18, 17, h.COLORS.white, 'left', 800, 0.8);
      h.text(e.sub || 'PRELIMINARY', r.x + R.padX, r.y + R.padY + 36, 13, h.COLORS.yellow, 'left', 800, 1);
      e.legend.forEach((l, i) => {
        const y = r.y + R.padY + R.titleH + 8 + i * R.rowH + R.rowH / 2;
        ctx.fillStyle = l.color; ctx.beginPath(); ctx.arc(r.x + R.padX + R.dot, y, R.dot, 0, Math.PI * 2); ctx.fill();
        h.text(l.label, r.x + 2 * R.padX + 2 * R.dot, y + R.px * 0.36, R.px, h.COLORS.white, 'left', 800, 0.5);
        h.text(String(Math.min(l.total, byKind[l.kind] || 0)), r.x + r.w - R.padX, y + R.px * 0.4, R.px + 4, h.COLORS.white, 'right', 800, 0);
      });
      h.placed().push(r);
    }
    ctx.restore();
  },
};
