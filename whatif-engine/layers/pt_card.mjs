// PT_CARD: the end disclaimer -- plain small white lines, left-aligned, on its own black background (concept-trailer end card).
//   { "type": "pt_card", "lines": ["This is a fan-made concept.", "Not affiliated with any manufacturer."], "start": 40, "end": 46 }
import { tm, clamp01 } from './tm_theme.mjs';
import { ptFont } from './pt_feature.mjs';

// A line longer than the card's width breaks between words (a long disclaimer never runs off the frame).
export function wrapLines(g, lines, maxW) {
  const out = [];
  for (const line of lines) {
    let cur = '';
    for (const w of line.split(/\s+/).filter(Boolean)) {
      const next = cur ? `${cur} ${w}` : w;
      if (cur && g.measureText(next).width > maxW) { out.push(cur); cur = w; } else cur = next;
    }
    if (cur) out.push(cur);
  }
  return out;
}

export default {
  type: 'pt_card',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.lines) || !def.lines.length) throw new Error('pt_card: "lines" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, a = d.start ?? 0, b = d.end ?? a + 5;
    const bg = clamp01((f.t - a) / 0.4) * clamp01((b - f.t) / 0.4), tx = clamp01((f.t - a - 0.35) / 0.6) * clamp01((b - f.t) / 0.4);
    g.save(); g.globalAlpha = f.alpha * bg; g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
    const font = ptFont(S, 32, 600, 'sans'), x = W * 0.12, lh = 50 * S;
    g.font = font;
    const lines = wrapLines(g, d.lines.map(String), W - 2 * x).slice(0, 12), y0 = H * 0.5 - (lines.length - 1) * lh / 2;
    g.globalAlpha = f.alpha * tx;
    lines.forEach((s, i) => T.text(s, x, y0 + i * lh + 12 * S, { font, color: '#F2F2F2', shadow: 0 }));
    g.restore();
  },
};
