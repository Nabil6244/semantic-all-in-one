// wind_flow: streaks drifting the way the forecast wind blows around a city, with its label ("WIND · S 10–15 MPH").
// The streaks are seeded, so every render of the same spec draws the same frames. from_deg is where the wind comes FROM.
import { rng } from '../../../pakmap-engine/lib/anim.mjs';

const RADIUS = 210;     // reference px around the city
const STREAKS = 46;

/** Streak positions at time t (pure: tested): [{x, y, len, alpha}] around (cx, cy). */
export function streaksAt(e, t, cx, cy) {
  const to = ((e.from_deg + 180) % 360) * Math.PI / 180;
  const dx = Math.sin(to), dy = -Math.cos(to);                 // north up, east right
  const speed = 26 + Math.min(60, e.mph || 0) * 5;             // reference px per second
  const r = rng(Math.round((e.lon * 1000) ^ (e.lat * 1000)) || 7), out = [];
  for (let i = 0; i < STREAKS; i++) {
    const ox = (r() * 2 - 1) * RADIUS, oy = (r() * 2 - 1) * RADIUS, phase = r() * 2 * RADIUS, len = 26 + r() * 34;
    // travel along the wind, wrapping inside a square around the city
    const s = ((phase + (t - e.t_in) * speed) % (2 * RADIUS)) - RADIUS;
    const x = cx + ox + dx * s, y = cy + oy + dy * s;
    const d = Math.hypot(x - cx, y - cy);
    if (d > RADIUS) continue;
    out.push({ x, y, x0: x - dx * len, y0: y - dy * len, alpha: Math.max(0, 1 - d / RADIUS) });
  }
  return out;
}

export default {
  type: 'wind_flow',
  order: 40,
  validate(e) {
    const bad = [];
    if (!(Number.isFinite(e.lon) && Number.isFinite(e.lat))) bad.push('wind_flow needs lon and lat');
    if (!Number.isFinite(e.from_deg)) bad.push('wind_flow needs from_deg');
    if (!e.label) bad.push('wind_flow needs label');
    return bad;
  },
  draw(e, t, h) {
    const a = h.lifeAlpha(t, e.t_in, e.t_out, 0.6, 0.5) * h.vis(); if (a <= 0) return;
    const q = h.project(e.lon, e.lat); if (!q) return;
    const cx = q.x / h.S, cy = q.y / h.S, { ctx } = h;
    ctx.save(); ctx.lineCap = 'round'; ctx.lineWidth = 3; ctx.shadowColor = 'rgba(0,0,0,0.45)'; ctx.shadowBlur = 4;
    for (const s of streaksAt(e, t, cx, cy)) {
      const g = ctx.createLinearGradient(s.x0, s.y0, s.x, s.y);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(1, `rgba(255,255,255,${(0.85 * s.alpha * a).toFixed(3)})`);
      ctx.strokeStyle = g; ctx.beginPath(); ctx.moveTo(s.x0, s.y0); ctx.lineTo(s.x, s.y); ctx.stroke();
    }
    ctx.restore();
    const label = `WIND · ${e.label}`, px = 22, w = h.measure(label, px) + 28, hh = 40, x = cx - w / 2, y = cy + RADIUS * 0.55;
    ctx.save(); ctx.globalAlpha = a;
    h.panel(x, y, w, hh, 9);
    h.text(label, x + 14, y + hh / 2 + px * 0.36, px, h.COLORS.white, 'left', 800, 0.6);
    ctx.restore();
  },
};
