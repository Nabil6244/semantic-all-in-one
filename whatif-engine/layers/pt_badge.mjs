// PT_BADGE: a generic chip badge (rounded square, gradient metal-gold, title inside; no real brand logo) centred, with a gold
// spark burst behind it. Deterministic: every spark comes from a seeded rng, so a frame is a pure function of t.
//   { "type": "pt_badge", "title": "AI CORE", "subtitle": "Next-gen processor", "color": "#d4a017", "start": 20, "end": 24 }
import { tm, clamp01, quartOut, overshoot, colour } from './tm_theme.mjs';
import { ptFont, ptFit } from './pt_feature.mjs';

const rng = (seed) => () => { seed = (seed + 0x6D2B79F5) | 0; let x = Math.imul(seed ^ (seed >>> 15), 1 | seed); x ^= x + Math.imul(x ^ (x >>> 7), 61 | x); return ((x ^ (x >>> 14)) >>> 0) / 4294967296; };
const mix = (hex, to, k) => { const n = parseInt(hex.slice(1), 16), c = [(n >> 16) & 255, (n >> 8) & 255, n & 255], t = to === 'w' ? 255 : 0; return `rgb(${c.map((v) => Math.round(v + (t - v) * k)).join(',')})`; };

export default {
  type: 'pt_badge',
  space: 'screen',
  create: (def) => { if (!def.title) throw new Error('pt_badge: "title" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, a = d.start ?? 0, b = d.end ?? a + 5, age = f.t - a;
    let gold = colour(d.color, '#d4a017'); if (!/^#[0-9a-f]{6}$/i.test(gold)) gold = '#d4a017';
    const kout = clamp01((b - f.t) / 0.45), kin = quartOut(age / 0.6), sc = 0.82 + 0.18 * overshoot(age / 0.7) + 0.02 * clamp01((age - 0.7) / 5);
    const cx = W / 2, cy = H * 0.46, side = 360 * S;
    g.save(); g.globalAlpha = f.alpha * kout;
    // glow
    const halo = g.createRadialGradient(cx, cy, 0, cx, cy, side * 1.6);
    halo.addColorStop(0, `rgba(255,200,90,${0.35 * kin})`); halo.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = halo; g.fillRect(cx - side * 2, cy - side * 2, side * 4, side * 4);
    // spark burst: 70 seeded sparks, each its own angle / speed / delay; streaks fly out and fade
    const r = rng(9137 + String(d.title).length * 31);
    g.lineCap = 'round';
    for (let i = 0; i < 70; i++) {
      const ang = r() * Math.PI * 2, sp = (260 + r() * 520) * S, del = r() * 0.35, life = 0.9 + r() * 0.9, w = (1.5 + r() * 3) * S;
      const u = (age - del) / life; if (u <= 0 || u >= 1) continue;
      const e = 1 - (1 - u) ** 2, d0 = side * 0.45 + sp * e, d1 = d0 - (40 + 90 * (1 - u)) * S;
      g.globalAlpha = f.alpha * kout * (1 - u) * 0.95; g.strokeStyle = i % 3 ? mix(gold, 'w', 0.45) : '#fff6d8'; g.lineWidth = w;
      g.beginPath(); g.moveTo(cx + Math.cos(ang) * Math.max(side * 0.4, d1), cy + Math.sin(ang) * Math.max(side * 0.4, d1)); g.lineTo(cx + Math.cos(ang) * d0, cy + Math.sin(ang) * d0); g.stroke();
    }
    g.globalAlpha = f.alpha * kout * kin;
    // chip: rounded square, metal-gold gradient, pins on four sides, inset face, title
    g.translate(cx, cy); g.scale(sc, sc);
    const h = side / 2, pins = 7;
    g.fillStyle = mix(gold, 'k', 0.25);
    for (let i = 0; i < pins; i++) { const p = -h * 0.7 + (i * h * 1.4) / (pins - 1), pl = 26 * S, pw = 14 * S;
      g.fillRect(p - pw / 2, -h - pl, pw, pl); g.fillRect(p - pw / 2, h, pw, pl); g.fillRect(-h - pl, p - pw / 2, pl, pw); g.fillRect(h, p - pw / 2, pl, pw); }
    const grad = g.createLinearGradient(-h, -h, h, h);
    grad.addColorStop(0, mix(gold, 'w', 0.55)); grad.addColorStop(0.35, gold); grad.addColorStop(0.6, mix(gold, 'k', 0.35)); grad.addColorStop(1, mix(gold, 'w', 0.25));
    g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 30 * S; g.fillStyle = grad; g.beginPath(); g.roundRect(-h, -h, side, side, 46 * S); g.fill();
    g.shadowColor = 'transparent'; g.shadowBlur = 0;
    const inner = g.createLinearGradient(0, -h, 0, h); inner.addColorStop(0, mix(gold, 'k', 0.55)); inner.addColorStop(1, mix(gold, 'k', 0.75));
    g.fillStyle = inner; g.beginPath(); g.roundRect(-h * 0.8, -h * 0.8, side * 0.8, side * 0.8, 30 * S); g.fill();
    g.strokeStyle = mix(gold, 'w', 0.5); g.lineWidth = 3 * S; g.stroke();
    // a moving sheen across the face (pure function of age)
    const sx = -h * 1.6 + clamp01((age - 0.4) / 1.2) * h * 3.2, sh = g.createLinearGradient(sx - 60 * S, 0, sx + 60 * S, 0);
    sh.addColorStop(0, 'rgba(255,255,255,0)'); sh.addColorStop(0.5, 'rgba(255,250,230,0.28)'); sh.addColorStop(1, 'rgba(255,255,255,0)');
    g.save(); g.beginPath(); g.roundRect(-h, -h, side, side, 46 * S); g.clip(); g.fillStyle = sh; g.fillRect(-h, -h, side, side); g.restore();
    const title = String(d.title), tpx = ptFit(T, title, 92, side * 0.68, 900, 'display', 0);
    T.text(title, 0, tpx * S * 0.36, { font: ptFont(S, tpx, 900), color: mix(gold, 'w', 0.7), align: 'center', glow: `rgba(255,210,120,0.45)`, shadow: 0 });
    g.restore();
    if (d.subtitle) { const k2 = clamp01((age - 0.5) / 0.6);
      T.text(String(d.subtitle), cx, cy + side * 0.5 * sc + 110 * S + (1 - k2) * 12 * S, { font: ptFont(S, 44, 600, 'sans'), color: '#F2F2F2', align: 'center', shadow: 0.35, alpha: f.alpha * kout * k2 }); }
  },
};
