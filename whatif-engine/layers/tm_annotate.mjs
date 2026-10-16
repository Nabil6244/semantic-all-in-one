// TM_ANNOTATE: a ring and a label on a photograph (V1 6:40, "A LENS CAP / EJECTED FROM ITS CAMERA"): a ring drawn on at (x, y), a short
// leader and the label to its right (bold cyan), a mono line under it. x, y and r are fractions of the frame (r of the width).
//   { "type": "tm_annotate", "x": 0.73, "y": 0.36, "r": 0.027, "label": "A LENS CAP", "sub": "EJECTED FROM ITS CAMERA", "start": 70, "end": 76 }
import { C, tm, colour, glideOut, clamp01 } from './tm_theme.mjs';

export default {
  type: 'tm_annotate',
  space: 'screen',
  create: (def) => { if (def.x == null || def.y == null) throw new Error('tm_annotate: "x" and "y" are required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), cx = d.x * W, cy = d.y * H, r = (d.r ?? 0.027) * W;
    const sweep = glideOut((f.t - (d.start ?? 0)) / 0.6), lab = clamp01((f.t - (d.start ?? 0) - 0.35) / 0.35);
    g.save(); g.globalAlpha = f.alpha;
    g.strokeStyle = '#EAF6FF'; g.lineWidth = 3 * T.S; g.shadowColor = C.cyan; g.shadowBlur = 12 * T.S;
    g.beginPath(); g.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * sweep); g.stroke(); g.shadowBlur = 0;
    g.globalAlpha = f.alpha * lab;
    T.line(cx + r, cy, cx + r + 28 * T.S, cy, { color: '#EAF6FF', width: 2, alpha: 0.9 });
    const x = cx + r + 40 * T.S;
    T.text(String(d.label || '').toUpperCase(), x, cy - 2 * T.S, { font: T.sans(26, 800), track: 2, color: colour(d.color, '#6FD3F2') });
    if (d.sub) T.text(String(d.sub).toUpperCase(), x, cy + 30 * T.S, { font: T.mono(16, 600), track: 1.5, color: C.cream });
    g.restore();
  },
};
