// PT_ICONBUILD: an app icon being built: a construction grid draws itself (centre lines, diagonals, guide circles, the outer square), the squircle outline is
// traced along its edge, then the gradient fill and the glyph arrive and the grid fades. Any glyph name or letter, any colours (lib/uikit.mjs drawTile).
//   { "type": "pt_iconbuild", "start": 0, "end": 6, "x": 0.5, "y": 0.52, "size": 0.36 (fraction of H), "icon": "camera", "label": "Camera", "color": "#7a5cff",
//     "ink": "dark" (grid on a light block) | "light" (grid on a dark block), "build": 2.6 (seconds the construction takes) }
import { tm, clamp01, quartOut, overshoot } from './tm_theme.mjs';
import { drawTile } from '../lib/uikit.mjs';

const TAU = Math.PI * 2;
const squirclePts = (cx, cy, s, n = 5, steps = 160) => Array.from({ length: steps + 1 }, (_, i) => {
  const th = (i / steps) * TAU, c = Math.cos(th), sn = Math.sin(th); return [cx + (s / 2) * Math.sign(c) * Math.abs(c) ** (2 / n), cy + (s / 2) * Math.sign(sn) * Math.abs(sn) ** (2 / n)];
});

export default {
  type: 'pt_iconbuild',
  space: 'screen',
  create: (def) => { if (!def.icon && !def.label) throw new Error('pt_iconbuild: "icon" or "label" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, age = f.t - (d.start ?? 0), end = d.end ?? (d.start ?? 0) + 6;
    const fadeOut = clamp01((end - f.t) / 0.5); if (age < 0 || fadeOut <= 0.002) return;
    const B = Math.max(1, d.build ?? 2.6), s = (d.size ?? 0.36) * H, cx = (d.x ?? 0.5) * W, cy = (d.y ?? 0.52) * H, dark = d.ink !== 'light';
    const grid = dark ? '#8d93a0' : '#9aa3b5', p = clamp01(age / B);
    const gridA = (1 - clamp01((p - 0.78) / 0.22)) * 0.9, line = clamp01(p / 0.55), outline = clamp01((p - 0.22) / 0.5), fill = clamp01((p - 0.7) / 0.28), glyph = clamp01((p - 0.82) / 0.18);
    g.save(); g.globalAlpha = f.alpha * fadeOut; g.translate(cx, cy);
    const hold = clamp01((age - B) / Math.max(0.5, end - (d.start ?? 0) - B)), push = 1 + 0.07 * hold, bob = Math.sin(age * 1.3) * s * 0.008 * clamp01(p * 2);   // never a frozen icon: a slow push in and a faint float once it is built
    g.scale(push, push); g.translate(0, bob);
    // the construction grid: each guide draws from its start to its end as `line` grows, staggered
    g.lineWidth = Math.max(1, 1.6 * S); g.strokeStyle = grid; g.globalAlpha *= gridA; g.lineCap = 'round';
    const seg = (x0, y0, x1, y1, k) => { if (k <= 0) return; g.beginPath(); g.moveTo(x0, y0); g.lineTo(x0 + (x1 - x0) * k, y0 + (y1 - y0) * k); g.stroke(); };
    const half = s * 0.78, k = (i) => quartOut(clamp01(line * 1.6 - i * 0.12));
    seg(-half, 0, half, 0, k(0)); seg(0, -half, 0, half, k(1)); seg(-half, -half, half, half, k(2)); seg(half, -half, -half, half, k(3));
    seg(-s / 2, -half, -s / 2, half, k(4)); seg(s / 2, -half, s / 2, half, k(4)); seg(-half, -s / 2, half, -s / 2, k(5)); seg(-half, s / 2, half, s / 2, k(5));
    [0.5, 0.36, 0.22].forEach((r, i) => { const a = quartOut(clamp01(line * 1.5 - 0.2 - i * 0.12)); if (a > 0) { g.beginPath(); g.arc(0, 0, s * r, -Math.PI / 2, -Math.PI / 2 + TAU * a); g.stroke(); } });
    g.strokeRect(-s / 2 * (0.5 + 0.5 * k(6)), -s / 2 * (0.5 + 0.5 * k(6)), s * (0.5 + 0.5 * k(6)), s * (0.5 + 0.5 * k(6)));
    g.globalAlpha = f.alpha * fadeOut;
    // the squircle outline traced along its edge
    if (outline > 0 && fill < 1) {
      const pts = squirclePts(0, 0, s), n = Math.max(2, Math.floor(pts.length * quartOut(outline)));
      g.strokeStyle = dark ? '#1a1d24' : '#f2f4f8'; g.lineWidth = Math.max(2, 3.2 * S); g.globalAlpha *= 1 - fill; g.beginPath(); pts.slice(0, n).forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y))); g.stroke();
      g.globalAlpha = f.alpha * fadeOut;
    }
    // the finished tile fades in under the outline; the glyph pops in after it
    if (fill > 0) { g.globalAlpha = f.alpha * fadeOut * quartOut(fill); drawTile(g, 0, 0, s, d.label || d.icon, d.color || '#7a5cff', d.icon, overshoot(glyph)); }
    g.restore();
  },
};
