// StarMap's screen graphics vocabulary, drawn on the 2D overlay. The same documentary family as PakMap (white chips with
// black type, yellow numbers on a dark navy panel, soft shadows, yellow photo captions) but StarMap's own code.
// All sizes are for a 1920-wide frame; ui(ctx, W) scales them for other sizes.
export const YELLOW = '#FBE040', PANEL = 'rgba(8,19,32,0.92)', WHITE = '#ffffff', INK = '#0a0a0a';

export function ui(g, W) {
  const S = W / 1920;
  const font = (px, weight = 800) => `${weight} ${Math.round(px * S)}px StarMapSans, sans-serif`;
  const shadow = (blur, alpha) => { g.shadowColor = `rgba(0,0,0,${alpha})`; g.shadowBlur = blur * S; g.shadowOffsetY = 2 * S; };
  const noShadow = () => { g.shadowColor = 'transparent'; g.shadowBlur = 0; g.shadowOffsetY = 0; };
  const box = (x, y, w, h, r, fill) => { g.fillStyle = fill; g.beginPath(); g.roundRect(x, y, w, h, r * S); g.fill(); };
  const measure = (text, px, weight) => { g.font = font(px, weight); return g.measureText(text).width; };
  return {
    S, font, shadow, noShadow, box, measure,
    /** A white (or any) chip with text, left edge at x: returns its width. */
    chip(x, y, text, px, { bg = WHITE, fg = INK, padX = 14, h = px + 22, r = 8, shadowBlur = 8 } = {}) {
      const w = measure(text, px) + padX * 2 * S, hh = h * S;
      shadow(shadowBlur, 0.45); box(x, y, w, hh, r, bg); noShadow();
      g.fillStyle = fg; g.textBaseline = 'middle'; g.textAlign = 'left'; g.fillText(text, x + padX * S, y + hh / 2 + 1 * S);
      return w;
    },
    /** A navy panel with a big yellow line and a small white line under it (numbers, clocks). */
    panel(x, y, big, small, { bigPx = 50, smallPx = 17, minW = 190, h = 104, r = 18, align = 'right' } = {}) {
      const w = Math.max(measure(big, bigPx), small ? measure(small, smallPx) : 0, minW * S) + 44 * S, hh = h * S;
      const bx = align === 'right' ? x - w : x;
      shadow(16, 0.5); box(bx, y, w, hh, r, PANEL); noShadow();
      g.textAlign = 'center'; g.textBaseline = 'middle';
      g.font = font(bigPx); g.fillStyle = YELLOW; g.fillText(big, bx + w / 2, y + (small ? hh * 0.41 : hh / 2));
      if (small) { g.font = font(smallPx); g.fillStyle = WHITE; g.fillText(small, bx + w / 2, y + hh * 0.77); }
      g.textAlign = 'left';
      return { x: bx, y, w, h: hh };
    },
    /** A map pin: white ring with a dark core. */
    pin(x, y, color = WHITE) {
      shadow(6, 0.6);
      g.fillStyle = color; g.beginPath(); g.arc(x, y, 13 * S, 0, Math.PI * 2); g.fill(); noShadow();
      g.fillStyle = INK; g.beginPath(); g.arc(x, y, 7 * S, 0, Math.PI * 2); g.fill();
      g.fillStyle = color; g.beginPath(); g.arc(x, y, 4 * S, 0, Math.PI * 2); g.fill();
    },
    /** A polyline with an optional glow and dash pattern (screen points [[x, y], ...]). */
    line(pts, { color = YELLOW, width = 6, dash = null, glow = 0, alpha = 1, cap = 'round' } = {}) {
      if (pts.length < 2) return;
      g.save(); g.globalAlpha *= alpha; g.lineJoin = 'round'; g.lineCap = cap; g.strokeStyle = color; g.lineWidth = width * S;
      g.setLineDash(dash ? dash.map((d) => d * S) : []);
      if (glow) { g.shadowColor = color; g.shadowBlur = glow * S; }
      g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); g.stroke();
      g.restore();
    },
    /** A filled arrowhead at (x, y) pointing along (dx, dy). */
    arrow(x, y, dx, dy, size = 18, color = YELLOW) {
      const l = Math.hypot(dx, dy) || 1, ux = dx / l, uy = dy / l, s = size * S;
      g.fillStyle = color; g.beginPath();
      g.moveTo(x + ux * s, y + uy * s); g.lineTo(x - ux * s * 0.6 - uy * s * 0.7, y - uy * s * 0.6 + ux * s * 0.7); g.lineTo(x - ux * s * 0.6 + uy * s * 0.7, y - uy * s * 0.6 - ux * s * 0.7);
      g.closePath(); g.fill();
    },
  };
}

/** Split a projected polyline into visible runs: points are { x, y, ok } (ok = in front of the camera and not hidden). */
export function runs(points) {
  const out = []; let cur = [];
  for (const p of points) {
    if (p.ok) cur.push([p.x, p.y]);
    else if (cur.length) { out.push(cur); cur = []; }
  }
  if (cur.length) out.push(cur);
  return out.filter((r) => r.length > 1);
}
