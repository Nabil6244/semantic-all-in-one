// GFX-CORE TEXT STYLES: how a line of text arrives and lives. Every style is a pure function of progress p (0..1 over `dur` seconds) and
// draws with the shared helpers, so any template item  { "p": "text", "style": "slam", ... }  can wear any style. Add a style here and
// it is available to every template and every niche.
import { col, clamp01, easeOut, easeInOut, overshoot } from './theme.mjs';

const words = (s) => String(s).split(/\s+/).filter(Boolean);

function base(T, g, text, x, y, o, extra = {}) {
  return T.text(text, x, y, { face: o.face, italic: o.italic, px: o.px, weight: o.weight, color: o.color, track: o.track, align: o.align, shadow: o.shadow, ...extra });
}
function clipTo(g, x, y, w, h, fn) { g.save(); g.beginPath(); g.rect(x, y, w, h); g.clip(); fn(); g.restore(); }
function boxOf(T, text, o) { const w = T.measure(text, o.px, o.weight, o.track); const x0 = o.align === 'center' ? -w / 2 : o.align === 'right' ? -w : 0; return { w, x0, h: o.px * T.S }; }

export const TEXT_STYLES = {
  plain(T, g, text, x, y, p, o) { base(T, g, text, x, y, o, { alpha: easeOut(p * 3) }); },

  // heavy title lands from large with a small overshoot (opening title, numbers)
  slam(T, g, text, x, y, p, o) {
    const k = overshoot(clamp01(p * 2.2)), sc = 1.55 - 0.55 * k;
    g.save(); g.translate(x, y - o.px * T.S * 0.35); g.scale(sc, sc); g.translate(-x, -(y - o.px * T.S * 0.35));
    base(T, g, text, x, y, o, { alpha: clamp01(p * 6), shadow: 0.55 }); g.restore();
  },

  // outline draws first, fill fades in after
  outline(T, g, text, x, y, p, o) {
    g.save(); g.font = T.font(o.px, o.weight); g.letterSpacing = `${(o.track * T.S).toFixed(2)}px`; g.textAlign = o.align; g.textBaseline = 'alphabetic';
    g.lineJoin = 'round'; g.lineWidth = Math.max(2, o.px * T.S * 0.05); g.strokeStyle = o.color; g.globalAlpha *= clamp01(p * 4);
    g.strokeText(String(text), x, y);
    const f = clamp01((p - 0.45) / 0.4); if (f > 0) { g.globalAlpha *= f; g.fillStyle = o.color; g.fillText(String(text), x, y); }
    g.restore();
  },

  typewriter(T, g, text, x, y, p, o) {
    const s = String(text), n = Math.floor(s.length * clamp01(p / 0.8) + 1e-9), shown = s.slice(0, n);
    const { x0 } = boxOf(T, s, o); const w = T.measure(shown, o.px, o.weight, o.track);
    g.save(); g.textAlign = 'left'; base(T, g, shown, x + x0, y, { ...o, align: 'left' });
    if (p < 1 || Math.floor(p * 6) % 2 === 0) T.rect(x + x0 + w + 4 * T.S, y - o.px * T.S * 0.8, Math.max(2, o.px * T.S * 0.08), o.px * T.S * 0.9, col(o.accent || 'yellow'));
    g.restore();
  },

  // each word pops in on its own beat
  word_pop(T, g, text, x, y, p, o) {
    const ws = words(text), space = T.measure(' ', o.px, o.weight, o.track), widths = ws.map((w) => T.measure(w, o.px, o.weight, o.track));
    const total = widths.reduce((a, b) => a + b, 0) + space * (ws.length - 1);
    let cx = x - (o.align === 'center' ? total / 2 : o.align === 'right' ? total : 0);
    ws.forEach((w, i) => {
      const k = clamp01((p * (ws.length + 1.2) - i) / 1.2), sc = 0.7 + 0.3 * overshoot(k);
      g.save(); g.translate(cx + widths[i] / 2, y - o.px * T.S * 0.35); g.scale(sc, sc); g.translate(-(cx + widths[i] / 2), -(y - o.px * T.S * 0.35));
      base(T, g, w, cx, y, { ...o, align: 'left' }, { alpha: easeOut(k * 2) }); g.restore();
      cx += widths[i] + space;
    });
  },

  // a bright band sweeps across the text
  sweep(T, g, text, x, y, p, o) {
    const { w, x0 } = boxOf(T, text, o);
    base(T, g, text, x, y, o, { alpha: easeOut(p * 4) });
    const k = easeInOut(clamp01((p - 0.15) / 0.7)); if (k <= 0 || k >= 1) return;
    g.save(); g.font = T.font(o.px, o.weight); g.letterSpacing = `${(o.track * T.S).toFixed(2)}px`; g.textAlign = 'left'; g.textBaseline = 'alphabetic';
    const bx = x + x0 + (w + o.px * T.S * 2) * k - o.px * T.S;
    const gr = g.createLinearGradient(bx - o.px * T.S, 0, bx + o.px * T.S, 0);
    gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(0.5, 'rgba(255,255,255,0.95)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillText(String(text), x + x0, y); g.restore();
  },

  // rubber stamp: boxed, tilted, thumps down
  stamp(T, g, text, x, y, p, o) {
    const k = overshoot(clamp01(p * 3)), sc = 2.1 - 1.1 * k, { w, x0 } = boxOf(T, text, o), pad = o.px * T.S * 0.35, h = o.px * T.S;
    g.save(); g.translate(x + x0 + w / 2, y - h * 0.35); g.rotate(-0.1); g.scale(sc, sc); g.globalAlpha *= clamp01(p * 6) * 0.95;
    g.strokeStyle = o.color; g.lineWidth = Math.max(3, h * 0.09); g.beginPath(); g.roundRect(-w / 2 - pad, -h * 0.65 - pad * 0.4, w + pad * 2, h * 1.2 + pad * 0.6, 8 * T.S); g.stroke();
    T.text(text, 0, h * 0.35, { px: o.px, weight: o.weight, color: o.color, track: o.track, align: 'center', shadow: 0 }); g.restore();
  },

  // lines of a longer text slide up one after another out of a mask (kinetic stack); lines are split on "|" or at ~16 chars
  stack(T, g, text, x, y, p, o) {
    const lines = String(text).includes('|') ? String(text).split('|').map((s) => s.trim()) : wrap(String(text), 16), lh = o.px * T.S * 1.08;
    lines.forEach((ln, i) => {
      const k = easeOut(clamp01((p * (lines.length + 0.6) - i) / 1.1));
      clipTo(g, x - 2000, y - lh * 0.9 + i * lh, 4000, lh * 1.05, () => base(T, g, ln, x, y + i * lh + (1 - k) * lh, o, { alpha: clamp01(k * 3) }));
    });
  },

  // text, then an underline draws itself under it
  underline(T, g, text, x, y, p, o) {
    const { w, x0 } = boxOf(T, text, o);
    base(T, g, text, x, y, o, { alpha: easeOut(p * 4) });
    const k = easeOut(clamp01((p - 0.35) / 0.5)); if (k <= 0) return;
    g.save(); g.strokeStyle = col(o.accent || 'yellow'); g.lineWidth = Math.max(3, o.px * T.S * 0.07); g.lineCap = 'round';
    g.beginPath(); g.moveTo(x + x0, y + o.px * T.S * 0.22); g.lineTo(x + x0 + w * k, y + o.px * T.S * 0.22); g.stroke(); g.restore();
  },

  // revealed from the middle outward, two halves of a mask
  split(T, g, text, x, y, p, o) {
    const { w, x0 } = boxOf(T, text, o), k = easeOut(clamp01(p / 0.7)), half = (w / 2) * k, cx = x + x0 + w / 2, h = o.px * T.S;
    clipTo(g, cx - half, y - h, half * 2, h * 1.4, () => base(T, g, text, x, y, o));
  },

  // neon: a coloured glow that breathes
  glow(T, g, text, x, y, p, o) {
    const pulse = 0.75 + 0.25 * Math.sin(p * Math.PI * 6);
    base(T, g, text, x, y, o, { alpha: easeOut(p * 3), glow: o.glow || o.color, shadow: 0 });
    g.save(); g.globalAlpha *= 0.25 * pulse; base(T, g, text, x, y, o, { glow: o.glow || o.color, shadow: 0 }); g.restore();
  },

  // text on a colour box that wipes open
  box(T, g, text, x, y, p, o) {
    const { w, x0 } = boxOf(T, text, o), pad = o.px * T.S * 0.4, h = o.px * T.S, k = easeOut(clamp01(p / 0.5));
    T.rect(x + x0 - pad, y - h * 0.85, (w + pad * 2) * k, h * 1.25, col(o.accent || 'yellow'), 3);
    clipTo(g, x + x0 - pad, y - h, (w + pad * 2) * k, h * 1.5, () => base(T, g, text, x, y, { ...o, color: col('ink') }, { alpha: clamp01((p - 0.2) * 5) }));
  },
};

export const TEXT_STYLE_NAMES = Object.keys(TEXT_STYLES);

function wrap(s, n) {
  const out = []; let cur = '';
  for (const w of words(s)) { if (cur && (cur + ' ' + w).length > n) { out.push(cur); cur = w; } else cur = cur ? `${cur} ${w}` : w; }
  if (cur) out.push(cur); return out;
}

/** Draw text in a named style. o: { px, weight, color, track, align, shadow, accent, glow }. p: 0..1 progress of the arrival. */
export function styledText(T, g, text, x, y, style, p, o = {}) {
  const f = TEXT_STYLES[style] || TEXT_STYLES.plain;
  f(T, g, text, x, y, clamp01(p), { px: 64, weight: 800, color: '#fff', track: 0, align: 'left', shadow: 0.35, ...o });
}
