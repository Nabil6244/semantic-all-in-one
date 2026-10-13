// post_timeline: the event's days as a line drawing in from the left, with a dot and a label for each dated mark
// ("AUG 25 · 10 PM / LANDFALL / CATEGORY 4 HURRICANE · 130 MPH"). A mark appears as the line reaches its time.
import { POST, timelineLayout, placeMarks } from '../wxu_post_charts.mjs';

export default {
  type: 'post_timeline',
  order: 60,
  validate(e) {
    const bad = [];
    if (!Array.isArray(e.ticks) || e.ticks.length < 2) bad.push('post_timeline needs ticks (the days)');
    if (!Array.isArray(e.marks)) bad.push('post_timeline needs marks');
    else e.marks.forEach((m, i) => { if (!(m.f >= 0 && m.f <= 1) || !m.title || !m.when) bad.push(`post_timeline mark ${i + 1} needs f (0..1), when and title`); });
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const L = timelineLayout(), { ctx } = h;
    const draw = h.easeOut(h.clamp01((t - e.t_in - 0.3) / Math.min(4, Math.max(1.5, (e.t_out - e.t_in) * 0.4))));
    const widthOf = (m) => Math.max(h.measure(m.when, 14, 800), h.measure(m.title, 18, 800), h.measure(m.detail || '', 14, 700)) + 22;
    const marks = placeMarks(e.marks, L, widthOf);
    ctx.save(); ctx.globalAlpha = a;
    h.panel(L.x, L.y, L.w, L.h, L.r);
    h.titleChip(L.x + 20, L.y - 22, 38, 19, e.title || 'TIMELINE');
    // axis: the days, drawn in
    const ax = L.axisX, aw = L.axisW, ay = L.axisY;
    ctx.strokeStyle = 'rgba(255,255,255,0.18)'; ctx.lineWidth = 6; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(ax + aw, ay); ctx.stroke();
    ctx.strokeStyle = h.COLORS.yellow; ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(ax + aw * draw, ay); ctx.stroke();
    const n = e.ticks.length;
    e.ticks.forEach((tk, i) => {
      const x0 = ax + (i / n) * aw;
      ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x0, ay - 9); ctx.lineTo(x0, ay + 9); ctx.stroke();
      h.text(tk.label, ax + tk.f * aw, ay + 36, 15, tk.f <= draw ? '#FFFFFF' : '#5E7287', 'center', 700, 0.4);
    });
    for (const m of marks) {
      if (m.f > draw + 1e-6) continue;
      const k = h.easeOut(h.clamp01((draw - m.f) * 8 + 0.15));
      const top = L.y + 18 + m.level * POST.timeline.level, bh = POST.timeline.box;
      ctx.save(); ctx.globalAlpha = a * k;
      ctx.strokeStyle = 'rgba(255,255,255,0.5)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(m.x, top + bh); ctx.lineTo(m.x, ay - 10); ctx.stroke();
      ctx.fillStyle = '#FFFFFF'; ctx.beginPath(); ctx.arc(m.x, ay, 10, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = h.COLORS.red; ctx.beginPath(); ctx.arc(m.x, ay, 6, 0, Math.PI * 2); ctx.fill();
      h.panel(m.lx, top, m.w, bh, 8, 'rgba(20,38,58,0.96)');
      h.text(m.when, m.lx + 11, top + 17, 14, h.COLORS.yellow, 'left', 800, 0.6);
      h.text(m.title, m.lx + 11, top + 36, 18, '#FFFFFF', 'left', 800, 0.4);
      if (m.detail) h.text(m.detail, m.lx + 11, top + 52, 14, '#9FB3C8', 'left', 700, 0.3);
      ctx.restore();
    }
    ctx.restore();
  },
};
