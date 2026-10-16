// The "telemetry" look's shared vocabulary (not a layer): the colours, the three type families and the small drawing helpers
// every tm_* layer uses. A documentary-science look -- near-black slate plates, white heavy numbers with a soft glow, small
// tracked labels, a monospaced line for data and citations, and only three strong colours, each with a meaning:
// cyan = information / you, amber = heat / Earth time / warning, red = lethal / failure.
// All sizes are for a 1920-wide frame; tm(g, W) scales them.
import { opacityAt } from '../lib/timing.mjs';

export const C = {
  base0: '#05070B', base1: '#0B0E14', white: '#FFFFFF', label: '#8E99A8', dim: 'rgba(142,153,168,0.55)',
  cyan: '#00E5FF', amber: '#FFB703', red: '#FF2A4B', green: '#2EE6A8', cream: '#F3E3C3',
  card: 'rgba(10,13,18,0.85)', border: 'rgba(255,255,255,0.12)',
};
const NAMED = { cyan: C.cyan, info: C.cyan, amber: C.amber, warn: C.amber, warning: C.amber, red: C.red, alert: C.red, lethal: C.red,
  white: C.white, gray: C.label, grey: C.label, green: C.green, cream: C.cream };
/** A colour by meaning ("cyan", "lethal", ...) or as given ("#ffcc00"). */
export const colour = (c, fallback = C.white) => (c ? NAMED[String(c).toLowerCase()] || c : fallback);

export const DISPLAY = 'StarMapSans';                    // Montserrat, weight 900: the big numbers and titles
export const SANS = 'TMSans';                             // Inter: labels, captions
export const MONO = 'WIMono, Menlo, Consolas, monospace';   // data and citations

export const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const quartOut = (x) => 1 - (1 - clamp01(x)) ** 4;            // cubic-bezier(0.16, 1, 0.3, 1), close enough
export const glideOut = (x) => 1 - (1 - clamp01(x)) ** 3;            // cubic-bezier(0.25, 1, 0.5, 1)
/** Ease out with a small overshoot (2% of the travel), for panels sliding in from the sides. */
export const overshoot = (x) => { const k = clamp01(x), s = 1.2; return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2; };

/** 1 while the shot on screen is a diagram plate (HUD widgets that belong to the pictures step back over diagrams). */
export function plateAlpha(spec, t) {
  const s = (spec.shots || []).find((x) => t >= x.start && t < x.end);
  return s && s.kind === 'plate' && !s.lockup ? 1 : 0;
}

/** The slow push every diagram lives in (1.00 -> 1.04 over its time on screen, about its centre): a plate is never a still. */
export function drift(g, f, d, amount = 0.04) {
  const a = d.start ?? 0, b = d.end ?? a + 5, k = 1 + amount * clamp01((f.t - a) / Math.max(0.5, b - a));
  g.translate(f.W / 2, f.H / 2); g.scale(k, k); g.translate(-f.W / 2, -f.H / 2);
}

/** Keys [{t, ...}] -> the last one at or before t (null before the first). */
export const stepKey = (keys, t) => { let k = null; for (const x of keys || []) if (x.t <= t + 1e-6) k = x; return k; };

export function tm(g, W) {
  const S = W / 1920, H = (g.canvas && g.canvas.height) || (W * 9 / 16);
  const fonts = {
    display: (px) => `900 ${Math.round(px * S)}px ${DISPLAY}, sans-serif`,
    sans: (px, w = 700) => `${w} ${Math.round(px * S)}px ${SANS}, ${DISPLAY}, sans-serif`,
    mono: (px, w = 500) => `${w} ${Math.round(px * S)}px ${MONO}`,
  };
  const set = (font, track = 0) => { g.font = font; g.letterSpacing = `${(track * S).toFixed(2)}px`; };
  const self = {
    S, W, H, ...fonts, set,
    measure(text, font, track = 0) { set(font, track); return g.measureText(String(text)).width; },
    /** Text at (x, y): { font, color, track, align, base, glow (colour), shadow (0..1) }. Returns its width. */
    text(text, x, y, { font, color = C.white, track = 0, align = 'left', base = 'alphabetic', glow = null, shadow = 0.55, alpha = 1 } = {}) {
      const s = String(text);
      g.save(); set(font, track); g.textAlign = align; g.textBaseline = base; g.globalAlpha *= alpha;
      if (glow) { g.shadowColor = glow; g.shadowBlur = 34 * S; g.fillStyle = color; g.fillText(s, x, y); }
      if (shadow) { g.shadowColor = `rgba(0,0,0,${shadow})`; g.shadowBlur = 12 * S; g.shadowOffsetY = 2 * S; }
      else { g.shadowColor = 'transparent'; g.shadowBlur = 0; }
      g.fillStyle = color; g.fillText(s, x, y);
      const w = g.measureText(s).width;
      g.restore();
      return w;
    },
    /** The frosted dark card the HUD lives in. */
    card(x, y, w, h, { r = 12, fill = C.card, border = C.border, accent = null, accentW = 56 } = {}) {
      g.save();
      g.shadowColor = 'rgba(0,0,0,0.45)'; g.shadowBlur = 18 * S;
      g.fillStyle = fill; g.beginPath(); g.roundRect(x, y, w, h, r * S); g.fill();
      g.shadowColor = 'transparent'; g.shadowBlur = 0;
      g.strokeStyle = border; g.lineWidth = 1.5 * S; g.stroke();
      if (accent) { g.fillStyle = accent; g.fillRect(x + 14 * S, y - 1.5 * S, accentW * S, 3 * S); }
      g.restore();
    },
    line(x0, y0, x1, y1, { color = C.white, width = 2, alpha = 1, dash = null, glow = 0 } = {}) {
      g.save(); g.globalAlpha *= alpha; g.strokeStyle = color; g.lineWidth = width * S; g.lineCap = 'round';
      g.setLineDash(dash ? dash.map((d) => d * S) : []);
      if (glow) { g.shadowColor = color; g.shadowBlur = glow * S; }
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke(); g.restore();
    },
    /** A glowing node: a bright core with a soft halo (radius 6, glow 12 at 1920). */
    node(x, y, { color = C.cyan, r = 7, ring = true } = {}) {
      g.save();
      const halo = g.createRadialGradient(x, y, 0, x, y, r * 3.2 * S);
      halo.addColorStop(0, color); halo.addColorStop(1, 'rgba(0,0,0,0)');
      g.globalAlpha *= 0.55; g.fillStyle = halo; g.beginPath(); g.arc(x, y, r * 3.2 * S, 0, Math.PI * 2); g.fill();
      g.globalAlpha /= 0.55; g.fillStyle = ring ? C.white : color; g.beginPath(); g.arc(x, y, r * S, 0, Math.PI * 2); g.fill();
      if (ring) { g.strokeStyle = color; g.lineWidth = 2.5 * S; g.stroke(); }
      g.restore();
    },
  };
  return self;
}

/** Numbers as the narrator would read them on screen: 25902068371 -> "25,902,068,371", 1.3 -> "1.3". */
export const fmt = (v, dec = null) => {
  const d = dec ?? (Math.abs(v) < 10 && !Number.isInteger(v) ? 1 : 0);
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};
