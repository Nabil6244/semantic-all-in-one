// PT_RING: a ring drawn round one named part (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 5): the references circle the 5x lens in yellow
// when the narrator says it "looks smaller". Over a 3D product shot the ring follows that lens as the camera moves (frame.parts.lenses, reported
// by lib/product.mjs through page.js); without them (another shot, a lens facing away) it sits at the fallback x / y / r (fractions of the frame).
// It sweeps round from the top on its word ("at", s after start, from product_trailer/wordcue.py), then breathes a little.
//   { "type": "pt_ring", "part": "lens", "index": -1, "phrase": "5X", "at": 0.6, "x": 0.5, "y": 0.42, "r": 0.07, "color": "#f5d000", "start": 3, "end": 8 }
import { clamp01, quartOut } from './tm_theme.mjs';
import { ptMotion } from './pt_feature.mjs';

export default {
  type: 'pt_ring',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, S = W / 1920;
    const m = ptMotion(d, f.t, S, { inDur: 0.01, outDur: 0.25, rise: 0 });
    const age = m.age - (Number.isFinite(d.at) ? d.at : 0.4);
    if (m.k <= 0.002 || age <= 0) return;
    const key = { lens: 'lenses' }[d.part || 'lens'] || String(d.part), list = (f.parts && Array.isArray(f.parts[key]) && f.parts[key]) || [];
    const n = list.length, i = Number.isInteger(d.index) ? (d.index < 0 ? n + d.index : d.index) : n - 1;
    const p = n && i >= 0 && i < n ? list[i] : null;
    const x = p ? p.x : (d.x ?? 0.5) * W, y = p ? p.y : (d.y ?? 0.45) * H;
    const r0 = p ? Math.max(14 * S, p.r * 1.25) : (d.r ?? 0.07) * H;
    if (![x, y, r0].every(Number.isFinite)) return;
    const sweep = quartOut(age / 0.55), r = r0 * (1 + 0.035 * Math.sin(Math.max(0, age - 0.6) * 3.2));
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k * clamp01(age / 0.12);
    g.strokeStyle = d.color || '#f5d000'; g.lineWidth = Math.max(3, (d.width ?? 6) * S); g.lineCap = 'round';
    g.shadowColor = 'rgba(0,0,0,0.35)'; g.shadowBlur = 8 * S;
    g.beginPath(); g.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * sweep); g.stroke();
    g.restore();
  },
};
