// PT_WORDS: a feature title that types on word by word, each word fading up out of a blur, filled with one gradient across the whole line (the UI-film look:
// "Dynamic Dock", "Lock Screen"). Any text, any colours; long titles shrink, then wrap to two lines.
//   { "type": "pt_words", "text": "Dynamic Dock", "start": 0, "end": 6, "y": 0.13, "x": 0.5, "align": "center", "size": 78 (px at 1920), "weight": 600,
//     "ink": "light" (bright text for a dark block) | "dark" (for a light block), "grad": ["#c9b8ff", "#8fb7ff"], "wps": 4 (words per second), "delay": 0.15, "blur": 12,
//     "times": [0, 0.31, 0.6] (optional: each word arrives when the narrator says it, seconds after start) }
import { tm, clamp01, quartOut, SANS } from './tm_theme.mjs';

const GRADS = { light: ['#e3d9ff', '#9db8ff'], dark: ['#8a4df0', '#3f86f5'] };
const font = (S, px, w) => `${w} ${Math.round(px * S)}px ${SANS}, Inter, sans-serif`;

export default {
  type: 'pt_words',
  space: 'screen',
  create: (def) => { if (!String(def.text || '').trim()) throw new Error('pt_words: "text" is required'); return { def, words: String(def.text).trim().split(/\s+/) }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, age = f.t - (d.start ?? 0), end = d.end ?? (d.start ?? 0) + 5, words = inst.words;
    const wps = d.wps ?? 4, delay = d.delay ?? 0.15, weight = d.weight ?? 600, maxW = W * 0.86, ink = d.ink === 'dark' ? 'dark' : 'light';
    let px = d.size ?? 78; const track = -px * 0.01;
    const lineW = (ws, p) => T.measure(ws.join(' '), font(S, p, weight), track * p / px);
    while (px > 40 && lineW(words, px) > maxW) px -= 3;
    let lines = [words];
    if (lineW(words, px) > maxW && words.length > 1) { const h = Math.ceil(words.length / 2); lines = [words.slice(0, h), words.slice(h)]; }
    const fadeOut = clamp01((end - f.t) / 0.45);
    if (fadeOut <= 0.002 || age < 0) return;
    const align = d.align || 'center', cx = (d.x ?? 0.5) * W, cy = (d.y ?? 0.13) * H, lh = px * 1.18 * S;
    const [c0, c1] = d.grad || GRADS[ink];
    let idx = 0;
    lines.forEach((ws, li) => {
      const wLine = T.measure(ws.join(' '), font(S, px, weight), track), x0 = align === 'left' ? cx : align === 'right' ? cx - wLine : cx - wLine / 2;
      const gr = g.createLinearGradient(x0, 0, x0 + wLine, 0); gr.addColorStop(0, c0); gr.addColorStop(1, c1);
      const y = cy + (li - (lines.length - 1) / 2) * lh + px * S * 0.34, space = T.measure(' ', font(S, px, weight), track);
      let x = x0;
      ws.forEach((w) => {
        const at = Array.isArray(d.times) && Number.isFinite(d.times[idx]) ? d.times[idx] : delay + idx / wps;   // times: when each word is spoken (s after start)
        const ww = T.measure(w, font(S, px, weight), track), k = quartOut((age - at) / 0.42);
        if (k > 0.002) {
          g.save(); g.globalAlpha = f.alpha * k * fadeOut;
          const blur = ((1 - k) * (d.blur ?? 12) + (1 - fadeOut) * 8) * S; if (blur > 0.3) g.filter = `blur(${blur.toFixed(1)}px)`;
          g.translate(0, (1 - k) * 16 * S);
          T.text(w, x, y, { font: font(S, px, weight), track, color: gr, shadow: ink === 'light' ? 0.25 : 0, glow: null });
          g.restore();
        }
        x += ww + space; idx++;
      });
    });
  },
};
