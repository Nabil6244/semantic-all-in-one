// PT_SUBTITLE: burned-in phrase subtitles for long reviews (the iPhone Duo reference): 6 to 9 words at a time, bottom centre, white sans
// with a dark shadow, one chunk at a time. Chunks come from the planner (even split of a sentence) or, in the app, from the voice-over alignment.
//   { "type": "pt_subtitle", "chunks": [{ "start": 12.0, "end": 14.4, "text": "the folding part really works well" }, ...], "y": 0.9, "size": 0.042 }
import { tm, clamp01, SANS } from './tm_theme.mjs';

function lines(g, text, maxW) {
  const words = String(text).split(/\s+/).filter(Boolean), out = [];
  let cur = '';
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (cur && g.measureText(next).width > maxW) { out.push(cur); cur = w; } else cur = next;
  }
  if (cur) out.push(cur);
  return out.slice(0, 2);
}

export default {
  type: 'pt_subtitle',
  space: 'screen',
  create: (def) => {
    if (!Array.isArray(def.chunks) || !def.chunks.length) throw new Error('pt_subtitle: "chunks" is required');
    return { def, chunks: def.chunks.filter((c) => c && String(c.text || '').trim()).map((c) => ({ start: Number(c.start), end: Number(c.end), text: String(c.text).trim() })).sort((a, b) => a.start - b.start) };
  },
  draw(inst, f) {
    const c = inst.chunks.find((x) => f.t >= x.start && f.t < x.end);
    if (!c) return;
    const { g, W, H } = f, T = tm(g, W), d = inst.def;
    const k = clamp01((f.t - c.start) / 0.12) * clamp01((c.end - f.t) / 0.1);
    const px = Math.round(H * (Number(d.size) > 0 ? Number(d.size) : 0.042));
    g.save();
    g.font = `600 ${px}px ${SANS}, sans-serif`;
    const ls = lines(g, c.text, W * 0.78), lh = px * 1.25, y0 = H * clamp01(d.y ?? 0.9) - ((ls.length - 1) * lh) / 2;
    g.globalAlpha = (f.alpha ?? 1) * k; g.textAlign = 'center'; g.textBaseline = 'middle';
    if (d.box) {                                            // a dark pill so the line reads on a light (paper) shot
      const w = Math.max(...ls.map((x) => g.measureText(x).width)) + px * 1.4, h = lh * ls.length + px * 0.5;
      g.fillStyle = 'rgba(12,14,18,0.8)'; g.beginPath(); g.roundRect(W / 2 - w / 2, H * clamp01(d.y ?? 0.9) - h / 2, w, h, px * 0.5); g.fill();
    }
    ls.forEach((s, i) => {
      g.shadowColor = 'rgba(0,0,0,0.85)'; g.shadowBlur = px * 0.25; g.shadowOffsetY = px * 0.05;
      g.fillStyle = '#FFFFFF'; g.fillText(s, W / 2, y0 + i * lh);
    });
    g.restore();
    void T;
  },
};
