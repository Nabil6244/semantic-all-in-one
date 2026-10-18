// GFX-CORE THEME: the tokens every universal template draws with (palette, fonts, plate background), and the small text/box helpers.
// A niche adapter calls setTheme('documentary' | { ...overrides }) once; templates never hold a colour of their own, only a palette NAME
// ("orange", "teal", "ink") so the same template wears each niche's look. Sizes are px for a 1920-wide frame; makeT(g, W) scales them.

export const THEMES = {
  // map / travel / geopolitics documentary: deep teal-slate plates, chunky colour chips, tracked caps (references: rainfall bars + region card)
  documentary: {
    font: 'GfxSans, PakMapSans, Montserrat, "Helvetica Neue", Arial, sans-serif',
    bg: ['#17323d', '#0c1a22', '#070f15'],                 // plate: light centre-left -> dark edges
    panel: 'rgba(9,17,28,0.90)', panelBorder: 'rgba(255,255,255,0.07)', tagBg: 'rgba(8,14,19,0.88)',
    palette: {
      orange: '#D98A4E', green: '#6FC477', blue: '#4DA6F0', teal: '#2DE0C8', red: '#D9533F', yellow: '#F2C94C', purple: '#9B7BE0',
      white: '#FFFFFF', ink: '#0B1216', muted: '#9AA8B3', grey: '#9AA8B3', dim: '#5E6B76', gold: '#E6B83A',
    },
  },
};

// editorial documentary (reference: "Western New South Wales ..."): near-black warm slate, gold numerals and rules, serif display type
THEMES.editorial = {
  font: 'GfxSans, Inter, "Helvetica Neue", Arial, sans-serif',
  displayFont: 'GfxSerif, "Cormorant Garamond", "Cormorant", "Playfair Display", Georgia, "Times New Roman", serif',
  bg: ['#25282c', '#16181b', '#0c0d0f'], panel: 'rgba(14,15,17,0.92)', panelBorder: 'rgba(201,164,92,0.35)', tagBg: 'rgba(10,10,12,0.85)',
  palette: {
    gold: '#C9A45C', orange: '#D07A3A', green: '#7FA56B', blue: '#6C93B8', teal: '#6FB7AE', red: '#B5503C', yellow: '#E2C275', purple: '#8E7BB5',
    white: '#F4EFE6', ink: '#14120E', muted: '#A39B8C', grey: '#A39B8C', dim: '#6B655B', cream: '#F4EFE6',
  },
};

let current = THEMES.documentary;
export const theme = () => current;
/** put back a theme object taken from theme() (no merging) */
export const restoreTheme = (t) => { current = t; };
/** setTheme('documentary') or setTheme({ palette: { orange: '#...' }, font: '...' }) (overrides merge over the current theme). */
export function setTheme(t) {
  if (typeof t === 'string') { if (THEMES[t]) current = THEMES[t]; return current; }
  current = { ...current, ...t, palette: { ...current.palette, ...(t.palette || {}) } };
  return current;
}

export const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const easeOut = (x) => 1 - (1 - clamp01(x)) ** 3;
export const easeInOut = (x) => { const k = clamp01(x); return k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2; };
export const overshoot = (x) => { const k = clamp01(x), s = 1.5; return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2; };

/** 12345.6 -> "12,346"; decimals when the number is small or `dec` is given. */
export const fmtNum = (v, dec = null) => {
  const d = dec ?? (Math.abs(v) < 10 && !Number.isInteger(v) ? 1 : 0);
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
};

export const col = (c, d = '#FFFFFF') => { if (!c) return d; const p = current.palette[String(c).toLowerCase()]; return p || c; };

/** Drawing helpers on a 2D context, scaled to the frame width. */
export function makeT(g, W, H) {
  const S = W / 1920;
  const T = {
    S, W, H: H ?? W * 9 / 16,
    font: (px, weight = 800, face = 'ui') => `${weight} ${Math.max(6, Math.round(px * S))}px ${face === 'display' ? (current.displayFont || current.font) : current.font}`,
    track(px) { g.letterSpacing = `${(px * S).toFixed(2)}px`; },
    measure(text, px, weight = 800, track = 0, face = 'ui') { g.font = T.font(px, weight, face); g.letterSpacing = `${(track * S).toFixed(2)}px`; const w = g.measureText(String(text)).width; g.letterSpacing = '0px'; return w; },
    /** text at (x, y baseline). opts: px, weight, color, track, align, shadow (0..1), glow (colour), alpha */
    text(text, x, y, { px = 32, weight = 800, color = '#fff', track = 0, align = 'left', shadow = 0.35, glow = null, alpha = 1, base = 'alphabetic', face = 'ui', italic = false } = {}) {
      g.save(); g.font = (italic ? 'italic ' : '') + T.font(px, weight, face); g.letterSpacing = `${(track * S).toFixed(2)}px`; g.textAlign = align; g.textBaseline = base; g.globalAlpha *= alpha;
      const s = String(text);
      if (glow) { g.shadowColor = glow; g.shadowBlur = 26 * S; g.fillStyle = color; g.fillText(s, x, y); g.fillText(s, x, y); }
      g.shadowColor = shadow ? `rgba(0,0,0,${shadow})` : 'transparent'; g.shadowBlur = shadow ? 10 * S : 0; g.shadowOffsetY = shadow ? 2 * S : 0;
      g.fillStyle = color; g.fillText(s, x, y);
      const w = g.measureText(s).width; g.restore(); return w;
    },
    rect(x, y, w, h, fill, r = 0) { g.save(); g.fillStyle = fill; g.beginPath(); if (r) g.roundRect(x, y, w, h, r * S); else g.rect(x, y, w, h); g.fill(); g.restore(); },
    panel(x, y, w, h, { fill = current.panel, border = current.panelBorder, r = 6 } = {}) {
      g.save(); g.shadowColor = 'rgba(0,0,0,0.4)'; g.shadowBlur = 22 * S; g.fillStyle = fill; g.beginPath(); g.roundRect(x, y, w, h, r * S); g.fill();
      g.shadowColor = 'transparent'; g.shadowBlur = 0; g.strokeStyle = border; g.lineWidth = 1.5 * S; g.stroke(); g.restore();
    },
  };
  return T;
}

/** The plate behind a template that brings its own background (references: dark teal slate, lighter centre-left, vignette). */
export function drawPlate(g, W, H, variant = 'documentary') {
  const [a, b, c] = current.bg;
  g.save();
  g.fillStyle = c; g.fillRect(0, 0, W, H);
  const r = g.createRadialGradient(W * 0.32, H * 0.3, 0, W * 0.32, H * 0.3, Math.hypot(W, H) * 0.75);
  r.addColorStop(0, a); r.addColorStop(0.55, b); r.addColorStop(1, c);
  g.fillStyle = r; g.fillRect(0, 0, W, H);
  g.restore();
}
