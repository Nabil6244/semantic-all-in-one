// Weather Teamplate's place on the map (a Weather place_label, re-typed): a white dot with a pulsing ring and the name in an
// orange tag above it, joined by a short line; it steps aside while a title card is up (`hide`). Event: {type: 'tp_place', lon, lat, text, hide}.
import { TP, placeRect, pulse, easeOut, shown } from '../wxu_tp_style.mjs';

export default {
  type: 'tp_place',
  order: 30,
  validate(e) {
    const out = [];
    if (!Number.isFinite(e.lon) || !Number.isFinite(e.lat)) out.push('tp_place needs lon and lat');
    if (!e.text) out.push('tp_place needs text');
    return out;
  },
  draw(e, t, h) {
    const q = h.project(e.lon, e.lat); if (!q) return;
    const x = q.x / h.S, y = q.y / h.S;
    if (x < 0 || y < 0 || x > 1920 || y > 1080) return;
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.3, 0.3) * h.vis() * shown(e.hide, t); if (a <= 0) return;
    const { ctx } = h, P = TP.place;
    const r = placeRect(x, y, h.measure(e.text, P.px, 700) + 0.6 * e.text.length, h.placed());
    const k = easeOut((t - e.t_in) / 0.35), p = pulse(t, e.t_in);
    ctx.save(); ctx.globalAlpha = a;
    ctx.strokeStyle = `rgba(255,255,255,${0.85 * p.a})`; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(x, y, p.r, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = 'rgba(255,255,255,0.18)'; ctx.beginPath(); ctx.arc(x, y, P.ring * 0.62 * k, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = TP.white; ctx.beginPath(); ctx.arc(x, y, P.dot * k, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = TP.orange; ctx.beginPath(); ctx.arc(x, y, P.dot * 0.5 * k, 0, Math.PI * 2); ctx.fill();
    const y0 = r.side === 'above' ? r.y + r.h : r.y, y1 = r.side === 'above' ? y - P.dot - 4 : y + P.dot + 4;
    ctx.strokeStyle = TP.orange; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(x, y1); ctx.lineTo(x, y1 + (y0 - y1) * k); ctx.stroke();
    if (k > 0.6) {
      ctx.globalAlpha = a * Math.min(1, (k - 0.6) / 0.4);
      ctx.shadowColor = 'rgba(0,0,0,0.35)'; ctx.shadowBlur = 10;
      ctx.fillStyle = TP.orange; ctx.fillRect(r.x, r.y, r.w, r.h); ctx.shadowColor = 'transparent';
      h.text(e.text, r.x + P.padX, r.y + r.h / 2 + P.px * 0.36, P.px, TP.white, 'left', 700, 0.6);
    }
    ctx.restore();
    h.placed().push(r);
  },
};
