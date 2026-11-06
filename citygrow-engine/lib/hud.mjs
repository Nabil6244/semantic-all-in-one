// The text layer, drawn on a 2D canvas over the 3D frame: year (bottom right), population (top right), era badge with
// flag and name (bottom left), centred serif title cards and bottom captions. Fonts: Montserrat (numbers, labels) and
// Cormorant Garamond (titles, captions), both SIL OFL 1.1, already in the repo.
//
// Flags are drawn from a short spec, so no flag images are needed:
//   "h:#a,#b,#c"  horizontal stripes      "v:#a,#b,#c"  vertical stripes      "plain:#a"
//   "cross:#bg,#fg"  Nordic cross          "george:#bg,#fg"  centred cross     "saltire:#bg,#fg"
//   "crescent:#bg,#fg"  crescent and star  "disc:#bg,#fg"  centred circle
//   any spec may end with "|TEXT" to letter a symbol in the middle (e.g. "plain:#6b1d5c,#e9c46a|☧" or "|SPQR").

const FLAG_W = 64, FLAG_H = 42;

export function parseFlag(spec) {
  if (!spec) return null;
  const [main, text] = String(spec).split('|');
  const [kind, cols = ''] = main.includes(':') ? main.split(':') : ['plain', main];
  const colors = cols.split(',').map((c) => c.trim()).filter(Boolean);
  return { kind: kind.trim().toLowerCase(), colors: colors.length ? colors : ['#6b3a2e'], text: text ? text.trim() : '' };
}

export function drawFlag(g, spec, x, y, w = FLAG_W, h = FLAG_H) {
  const f = parseFlag(spec); if (!f) return;
  const c = f.colors, fg = c[1] || '#f1e3b3';
  g.save(); g.beginPath(); g.rect(x, y, w, h); g.clip();
  g.fillStyle = c[0]; g.fillRect(x, y, w, h);
  if (f.kind === 'h') c.forEach((col, i) => { g.fillStyle = col; g.fillRect(x, y + (h * i) / c.length, w, h / c.length + 1); });
  else if (f.kind === 'v') c.forEach((col, i) => { g.fillStyle = col; g.fillRect(x + (w * i) / c.length, y, w / c.length + 1, h); });
  else if (f.kind === 'cross') { g.fillStyle = fg; g.fillRect(x + w * 0.3, y, w * 0.14, h); g.fillRect(x, y + h * 0.42, w, h * 0.16); }
  else if (f.kind === 'george') { g.fillStyle = fg; g.fillRect(x + w * 0.43, y, w * 0.14, h); g.fillRect(x, y + h * 0.4, w, h * 0.2); }
  else if (f.kind === 'saltire') { g.strokeStyle = fg; g.lineWidth = h * 0.18; g.beginPath(); g.moveTo(x, y); g.lineTo(x + w, y + h); g.moveTo(x + w, y); g.lineTo(x, y + h); g.stroke(); }
  else if (f.kind === 'disc') { g.fillStyle = fg; g.beginPath(); g.arc(x + w / 2, y + h / 2, h * 0.3, 0, Math.PI * 2); g.fill(); }
  else if (f.kind === 'crescent') {
    g.fillStyle = fg; g.beginPath(); g.arc(x + w * 0.42, y + h / 2, h * 0.3, 0, Math.PI * 2); g.fill();
    g.fillStyle = c[0]; g.beginPath(); g.arc(x + w * 0.48, y + h / 2, h * 0.25, 0, Math.PI * 2); g.fill();
    g.fillStyle = fg; star(g, x + w * 0.66, y + h / 2, h * 0.12);
  }
  if (f.text) {
    g.fillStyle = f.kind === 'plain' ? fg : '#f6ecd0';
    g.font = `600 ${Math.round(h * (f.text.length > 2 ? 0.42 : 0.62))}px CitySerif, serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(f.text, x + w / 2, y + h / 2 + 1);
  }
  g.restore();
  g.strokeStyle = 'rgba(0,0,0,0.35)'; g.lineWidth = 1; g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
}

function star(g, cx, cy, r) {
  g.beginPath();
  for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + (i * Math.PI) / 5, rr = i % 2 ? r * 0.45 : r; g.lineTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr); }
  g.closePath(); g.fill();
}

function shadowText(g, text, x, y, blur = 10) {
  g.save(); g.shadowColor = 'rgba(0,0,0,0.55)'; g.shadowBlur = blur; g.shadowOffsetY = 2; g.fillText(text, x, y); g.restore();
}

function spaced(g, text, x, y, spacing, align = 'left') {
  // letter-spaced text (canvas letterSpacing where available, else per letter)
  if ('letterSpacing' in g) { g.letterSpacing = `${spacing}px`; g.textAlign = align; shadowText(g, text, x, y); g.letterSpacing = '0px'; return; }
  const widths = [...text].map((ch) => g.measureText(ch).width + spacing);
  const total = widths.reduce((a, b) => a + b, 0) - spacing;
  let cx = align === 'center' ? x - total / 2 : align === 'right' ? x - total : x;
  g.textAlign = 'left'; [...text].forEach((ch, i) => { shadowText(g, ch, cx, y); cx += widths[i]; });
}

/** Draw the text layer. h: hudAt() result. */
export function drawHud(g, W, H, h) {
  const u = H / 1080, pad = 64 * u;
  g.save(); g.globalAlpha = h.hudAlpha; g.fillStyle = '#fbf6ea'; g.textBaseline = 'alphabetic';
  // year
  g.font = `800 ${Math.round(92 * u)}px CityNum, sans-serif`; g.textAlign = 'right';
  shadowText(g, h.year, W - pad, H - pad, 14 * u);
  // population
  g.font = `500 ${Math.round(38 * u)}px CityNum, sans-serif`; g.textAlign = 'right';
  const py = pad + 30 * u;
  shadowText(g, h.pop, W - pad, py, 10 * u);
  const pw = g.measureText(h.pop).width, ix = W - pad - pw - 34 * u, iy = py - 14 * u;
  g.save(); g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 8 * u;
  g.beginPath(); g.arc(ix, iy - 9 * u, 7.5 * u, 0, Math.PI * 2); g.fill();
  g.beginPath(); g.ellipse(ix, iy + 9 * u, 12 * u, 9 * u, 0, Math.PI, 0); g.fill(); g.restore();
  // era badge (cross-fade on change)
  const badge = (b, a) => {
    if (!b || !a) return;
    g.save(); g.globalAlpha *= a;
    const fy = H - pad - 92 * u;
    if (b.flag) drawFlag(g, b.flag, pad, fy, FLAG_W * 1.25 * u, FLAG_H * 1.25 * u);
    g.fillStyle = '#fbf6ea'; g.font = `500 ${Math.round(30 * u)}px CityNum, sans-serif`;
    spaced(g, (b.name || '').toUpperCase(), pad, H - pad - 4 * u, 3 * u);
    g.restore();
  };
  badge(h.badgePrev, h.badgeSwap < 1 ? 1 - h.badgeSwap : 0);
  badge(h.badge, h.badgeSwap);
  g.restore();
  // title card
  if (h.title && h.title.alpha > 0) {
    g.save(); g.globalAlpha = h.title.alpha; g.fillStyle = '#fbf6ea';
    const cy = h.title.big ? H * 0.47 : H * 0.62, size = h.title.big ? 112 : 84;
    if (h.title.kicker && !h.title.big) {
      g.font = `500 ${Math.round(30 * u)}px CitySerif, serif`; spaced(g, h.title.kicker.toUpperCase(), W / 2, cy - 78 * u, 6 * u, 'center');
      g.fillRect(W / 2 - 40 * u, cy - 62 * u, 80 * u, 1.5 * u);
    }
    g.font = `500 ${Math.round(size * u)}px CitySerif, serif`; spaced(g, h.title.title, W / 2, cy, 12 * u, 'center');
    if (h.title.kicker && h.title.big) {
      g.fillRect(W / 2 - 160 * u, cy + 28 * u, 320 * u, 1.5 * u);
      g.font = `500 ${Math.round(40 * u)}px CitySerif, serif`; spaced(g, h.title.kicker, W / 2, cy + 80 * u, 4 * u, 'center');
    }
    g.restore();
  }
  // caption
  if (h.caption && h.caption.alpha > 0) {
    g.save(); g.globalAlpha = h.caption.alpha; g.fillStyle = '#fbf6ea'; g.textAlign = 'center';
    g.font = `500 ${Math.round(40 * u)}px CitySerif, serif`;
    const lines = wrap(g, h.caption.text, W * 0.56);
    const y0 = H * 0.8 - (lines.length - 1) * 48 * u;
    lines.forEach((l, i) => shadowText(g, l, W / 2, y0 + i * 48 * u, 12 * u));
    g.restore();
  }
  if (h.black > 0) { g.fillStyle = `rgba(0,0,0,${h.black})`; g.fillRect(0, 0, W, H); }
}

export function wrap(g, text, maxW) {
  const words = String(text).split(/\s+/), lines = []; let cur = '';
  for (const w of words) { const n = cur ? `${cur} ${w}` : w; if (g.measureText(n).width > maxW && cur) { lines.push(cur); cur = w; } else cur = n; }
  if (cur) lines.push(cur);
  return lines;
}
