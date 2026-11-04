// The on-screen layer, drawn on a 2D canvas over the 3D frame, in a block-game style of our own: Monocraft (SIL OFL 1.1)
// for all text, hard one-step pixel shadows, beveled pixel panels, chunky caption lines, a hotbar-style chapter timeline.
// Pieces: date panel with legend, caption log, chapter card, hotbar timeline with time left, place tags, letterbox.

import { at, captionsAt } from './timeline.mjs';

const PANEL = 'rgba(14,12,20,0.84)', LIGHT = 'rgba(190,190,200,0.55)', DARK = 'rgba(0,0,0,0.75)';
const AMBER = '#ffd84a', WHITE = '#f6f6f0', GREY = '#b9b9b0', SHADOW = 'rgba(40,36,20,0.95)';
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fade = (t, t0, t1, f = 0.6) => clamp(Math.min((t - t0) / f, (t1 - t) / f), 0, 1);
const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

/** A beveled pixel panel: light top-left edge, dark bottom-right edge, one pixel step = p. */
function panel(g, x, y, w, h, p, fill = PANEL) {
  x = Math.round(x); y = Math.round(y); w = Math.round(w); h = Math.round(h);
  g.fillStyle = DARK; g.fillRect(x - p, y - p, w + 2 * p, h + 2 * p);
  g.fillStyle = fill; g.fillRect(x, y, w, h);
  g.fillStyle = LIGHT; g.fillRect(x, y, w, p); g.fillRect(x, y, p, h);
  g.fillStyle = DARK; g.fillRect(x, y + h - p, w, p); g.fillRect(x + w - p, y, p, h);
}
/** Text with a hard pixel shadow one step down and right. */
function text(g, s, x, y, colour, p, shadow = SHADOW) {
  g.fillStyle = shadow; g.fillText(s, Math.round(x + p), Math.round(y + p));
  g.fillStyle = colour; g.fillText(s, Math.round(x), Math.round(y));
}

export function drawHud(g, W, H, tl, legendAt, t, opts = {}) {
  const S = H / 720, P = Math.max(1, Math.round(2 * S)); // P: one pixel step of the HUD
  const font = (px, bold = true) => `${bold ? 700 : 400} ${Math.round(px * S)}px "HudFont", ui-monospace, monospace`;
  g.textBaseline = 'alphabetic'; g.imageSmoothingEnabled = false;

  // letterbox for ground sets
  const lb = opts.letterbox ?? 0, bh = H * 0.105 * lb;
  if (lb > 0) { g.fillStyle = '#000'; g.fillRect(0, 0, W, bh); g.fillRect(0, H - bh, W, bh); }

  // place tags (already projected by the page)
  for (const tag of opts.tags || []) {
    if (tag.a <= 0) continue;
    g.globalAlpha = tag.a;
    const big = tag.kind === 'country', label = big ? tag.name.toUpperCase() : tag.name;
    g.font = font(big ? 14 : 12, big);
    const w = g.measureText(label).width + 10 * S;
    if (tag.kind === 'site') text(g, label, tag.x - w / 2 + 5 * S, tag.y, AMBER, P);
    else {
      panel(g, tag.x - w / 2, tag.y - 14 * S, w, 18 * S, P, 'rgba(14,12,20,0.7)');
      text(g, label, tag.x - w / 2 + 5 * S, tag.y, tag.kind === 'city' ? WHITE : AMBER, P);
    }
    g.globalAlpha = 1;
  }

  // date panel + legend
  const d = at(tl.dates, t);
  if (d && !opts.noDate) {
    const legend = legendAt(t), pad = 12 * S, x = 20 * S, y = 20 * S + (lb > 0 ? bh * 0.35 : 0);
    g.font = font(36); const dw = g.measureText(d.label).width;
    g.font = font(12, false); const lw = Math.max(0, ...legend.map((l) => g.measureText(l.label).width + 22 * S));
    const w = Math.max(dw, lw) + pad * 2, h = 54 * S + legend.length * 17 * S + (legend.length ? 6 * S : 0);
    panel(g, x, y, w, h, P);
    g.font = font(36); text(g, d.label, x + pad, y + 44 * S, AMBER, P * 1.5);
    g.font = font(12, false);
    legend.forEach((l, i) => {
      const ly = y + 66 * S + i * 17 * S, sw = Math.round(11 * S);
      g.fillStyle = DARK; g.fillRect(x + pad - P, ly - sw - P + 1, sw + 2 * P, sw + 2 * P);
      g.fillStyle = l.color; g.fillRect(x + pad, ly - sw + 1, sw, sw);
      text(g, l.label, x + pad + 18 * S, ly, WHITE, P);
    });
  }

  // film title over a globe opening
  if (tl.title) {
    const a = fade(t, tl.title.t0, tl.title.t1, 0.8);
    if (a > 0) {
      g.globalAlpha = a; g.textAlign = 'center';
      g.font = font(44); text(g, tl.title.text, W / 2, H * 0.36, WHITE, P * 1.5, 'rgba(0,0,0,0.85)');
      if (tl.title.sub) { g.font = font(17); text(g, tl.title.sub, W / 2, H * 0.36 + 32 * S, AMBER, P); }
      g.textAlign = 'left'; g.globalAlpha = 1;
    }
  }

  // chapter card
  for (const c of tl.chapters) {
    const a = fade(t, c.cardT0, c.cardT1, 0.7);
    if (a <= 0) continue;
    g.globalAlpha = a; g.textAlign = 'center';
    g.font = font(34); text(g, c.title, W / 2, H * 0.2, WHITE, P * 1.5, 'rgba(0,0,0,0.85)');
    g.font = font(15); text(g, c.date, W / 2, H * 0.2 + 28 * S, AMBER, P);
    g.textAlign = 'left'; g.globalAlpha = 1;
  }

  // hotbar timeline: one slot per chapter, the current one selected and filling; time left beside it
  const n = Math.max(1, tl.chapters.length), slot = Math.round(34 * S), gap = Math.round(4 * S);
  const barW = n * slot + (n - 1) * gap, hx = Math.round((W - barW) / 2), hy = Math.round(H - (lb > 0 ? bh * 0.5 : 0) - slot - 12 * S);
  const cur = at(tl.chapters, t) || tl.chapters[0], ci = cur ? tl.chapters.indexOf(cur) : 0;
  const chEnd = (i) => (i + 1 < tl.chapters.length ? tl.chapters[i + 1].t : tl.duration);
  for (let i = 0; i < n; i++) {
    const sx = hx + i * (slot + gap), done = i < ci, now = i === ci;
    panel(g, sx, hy, slot, slot, P, done ? 'rgba(120,96,30,0.85)' : 'rgba(14,12,20,0.78)');
    if (now && tl.chapters[i]) {
      const k = clamp((t - tl.chapters[i].t) / Math.max(0.1, chEnd(i) - tl.chapters[i].t), 0, 1), fh = Math.round((slot - 2 * P) * k);
      g.fillStyle = 'rgba(255,216,74,0.55)'; g.fillRect(sx + P, hy + slot - P - fh, slot - 2 * P, fh);
    }
    g.font = font(15); g.textAlign = 'center';
    text(g, String(i + 1), sx + slot / 2, hy + slot / 2 + 6 * S, now ? WHITE : done ? AMBER : GREY, P);
    g.textAlign = 'left';
    if (now) { g.strokeStyle = WHITE; g.lineWidth = 2 * P; g.strokeRect(sx - 2 * P, hy - 2 * P, slot + 4 * P, slot + 4 * P); }
  }
  if (cur) {
    g.font = font(12, false);
    const label = `${cur.title}`;
    g.textAlign = 'center'; text(g, label, W / 2, hy - 10 * S, WHITE, P); g.textAlign = 'left';
  }
  g.font = font(12, false); g.textAlign = 'right';
  text(g, `${fmt(Math.max(0, tl.duration - t))} left`, W - 20 * S, hy + slot / 2 + 5 * S, GREY, P);
  g.textAlign = 'left';

  // museum inset (top right): the real object, turning on a plinth, its name and where it is kept
  const mu = opts.museum;
  if (mu && mu.a > 0) {
    g.globalAlpha = mu.a;
    const iw = Math.round(150 * S), x = W - iw - 24 * S, y = 20 * S + (lb > 0 ? bh * 0.35 : 0);
    g.font = font(12, false);
    const noteLines = mu.note ? wrap(g, mu.note, iw - 8 * S) : [];
    const ih = iw + 30 * S + noteLines.length * 15 * S;
    panel(g, x - 6 * S, y - 6 * S, iw + 12 * S, ih + 12 * S, P, 'rgba(214,214,206,0.95)');
    g.imageSmoothingEnabled = true; g.drawImage(mu.image, x, y, iw, iw); g.imageSmoothingEnabled = false;
    g.font = font(13); text(g, mu.name, x + 2 * S, y + iw + 18 * S, '#1c1c22', P, 'rgba(255,255,255,0.6)');
    g.font = font(12, false); noteLines.forEach((ln, i) => text(g, ln, x + 2 * S, y + iw + 34 * S + i * 15 * S, '#3a3a40', P, 'rgba(255,255,255,0.5)'));
    g.globalAlpha = 1;
  }
  // item bar (bottom right): every museum object shown so far, the current one framed
  const items = opts.items || [];
  if (items.length) {
    const sz = Math.round(30 * S), gp = Math.round(3 * S), slots = Math.max(items.length, 4);
    const ix = Math.round(W - 20 * S - slots * (sz + gp)), iy = Math.round(H - (lb > 0 ? bh * 0.5 : 0) - sz - 12 * S - 44 * S);
    for (let i = 0; i < slots; i++) {
      const sx = ix + i * (sz + gp); panel(g, sx, iy, sz, sz, P, 'rgba(14,12,20,0.7)');
      if (items[i]) { g.imageSmoothingEnabled = true; g.drawImage(items[i].icon, sx + P, iy + P, sz - 2 * P, sz - 2 * P); g.imageSmoothingEnabled = false; }
      if (items[i] && items[i].current) { g.strokeStyle = WHITE; g.lineWidth = 2 * P; g.strokeRect(sx - 2 * P, iy - 2 * P, sz + 4 * P, sz + 4 * P); }
    }
  }
  // credits panel and end card over a globe ending
  const cr = tl.credits;
  if (cr && t >= cr.t0) {
    const a = clamp((t - cr.t0) / 1.2, 0, 1);
    g.globalAlpha = a; g.font = font(12, false); g.textAlign = 'center';
    const lw = Math.max(...cr.lines.map((l) => g.measureText(l).width)) + 30 * S, lh = 17 * S, ch = cr.lines.length * lh + 18 * S;
    panel(g, W / 2 - lw / 2, 22 * S, lw, ch, P, 'rgba(14,12,20,0.6)');
    cr.lines.forEach((l, i) => text(g, l, W / 2, 22 * S + 20 * S + i * lh, i === 0 && cr.lines.length > 3 ? WHITE : GREY, P));
    if (cr.endcard && t > cr.t1 - 4.5) {
      const ea = clamp((t - (cr.t1 - 4.5)) / 0.8, 0, 1); g.globalAlpha = ea;
      g.font = font(28); const ew = g.measureText(cr.endcard).width + 40 * S;
      panel(g, W / 2 - ew / 2, H * 0.47, ew, 52 * S, P);
      text(g, cr.endcard, W / 2, H * 0.47 + 36 * S, WHITE, P * 1.5);
    }
    g.textAlign = 'left'; g.globalAlpha = 1;
  }

  // caption log: chunky chat lines above the hotbar, left side
  const lines = captionsAt(tl.captions, t), maxW = W * 0.52;
  let y = hy - 40 * S;
  for (const ln of [...lines].reverse()) {
    g.font = font(15, false);
    const wrapped = wrap(g, `${ln.tag} ${ln.text}`, maxW);
    for (let k = wrapped.length - 1; k >= 0; k--) {
      const s = wrapped[k], w = g.measureText(s).width + 14 * S;
      g.fillStyle = 'rgba(0,0,0,0.55)'; g.fillRect(Math.round(20 * S), Math.round(y - 17 * S), Math.round(w), Math.round(23 * S));
      if (k === 0 && !ln.old) { const tw = g.measureText(ln.tag).width; text(g, ln.tag, 27 * S, y, AMBER, P); text(g, s.slice(ln.tag.length), 27 * S + tw, y, WHITE, P); }
      else text(g, s, 27 * S, y, ln.old ? GREY : WHITE, P);
      y -= 23 * S;
    }
    y -= 4 * S;
  }
}

function wrap(g, s, maxW) {
  const out = []; let line = '';
  for (const w of s.split(' ')) { const tryL = line ? `${line} ${w}` : w; if (g.measureText(tryL).width > maxW && line) { out.push(line); line = w; } else line = tryL; }
  if (line) out.push(line);
  return out;
}
