// GFX-CORE NEWS PRIMITIVES: the broadcast-documentary effects of the News Doc / Weather styles, redone as universal canvas pieces (yellow
// pill tag, words-in boxed quote, year wipe, paper checklist, side panel with bullets, glitch cut, name bar, polaroid board, timeline strip).
// Same contract as prims.mjs: draw(c, it, tr). Nothing here depends on a niche; the weather code is not imported (the looks are re-drawn).
import { param } from './tpl.mjs';
import { col, clamp01, easeOut, easeInOut, fmtNum } from './theme.mjs';

const W_ = (c, it, tr, d) => { const a = c.follow && it.follow ? c.follow : param(it, 'at', tr, d); return [a[0] * c.W, a[1] * c.H]; };
const prog = (it, tr, dur = 1, delay = 0) => clamp01((tr - it._in - delay) / Math.max(0.05, dur));
const rnd = (seed) => { let s = (seed >>> 0) || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
const list = (v) => (Array.isArray(v) ? v : String(v ?? '').split(/[;|]/).map((s) => s.trim()).filter(Boolean));
const wrapWords = (T, words, px, weight, maxW, track = 0, face = 'ui') => {
  const lines = [[]]; let w = 0; const sp = T.measure(' ', px, weight, track, face);
  for (const word of words) { const ww = T.measure(word, px, weight, track, face); if (lines.at(-1).length && w + sp + ww > maxW) { lines.push([]); w = 0; } lines.at(-1).push(word); w += (lines.at(-1).length > 1 ? sp : 0) + ww; }
  return lines;
};

// yellow pill tag, top-left, slides in from the right
function pill(c, it, tr) {
  const { g, T } = c, [x, y] = W_(c, it, tr, [0.05, 0.07]), k = easeOut(prog(it, tr, 0.4)), px = it.size ?? 34, txt = String(it.text || '').toUpperCase();
  const w = T.measure(txt, px, 900, 3) + 56 * T.S, h = px * T.S * 1.9;
  g.save(); g.translate((1 - k) * 260 * T.S, 0); g.fillStyle = col(it.color || 'yellow'); g.beginPath(); g.roundRect(x, y, w, h, h / 2); g.fill();
  T.text(txt, x + 28 * T.S, y + h / 2 + px * T.S * 0.35, { px, weight: 900, color: col('ink'), track: 3, shadow: 0 }); g.restore();
}

// heavy caps, words appearing one by one; the closing phrase named in "mark" sits in a red box. solid = full black card, else a dim over the picture.
function boxquote(c, it, tr) {
  const { g, T } = c, k = easeOut(prog(it, tr, 0.3)), px = it.size ?? 92, words = String(it.text || '').toUpperCase().split(/\s+/).filter(Boolean);
  g.save(); g.fillStyle = it.solid ? '#000' : 'rgba(0,0,0,0.6)'; g.globalAlpha *= k; g.fillRect(0, 0, c.W, c.H); g.restore();
  const mark = String(it.mark || '').toUpperCase().split(/\s+/).filter(Boolean), clean = (w) => w.replace(/[.,!?]/g, '');
  const from = mark.length && words.slice(-mark.length).map(clean).join(' ') === mark.map(clean).join(' ') ? words.length - mark.length : words.length;
  const lines = wrapWords(T, words, px, 900, c.W * 0.69, 0), lh = px * T.S * 1.35, shown = Math.floor(words.length * clamp01((tr - it._in) / Math.max(0.8, Math.min(1.8, (it.dur ?? 3) * 0.4)))) + 1;
  let y = (c.H - lh * lines.length) / 2 + px * T.S * 1.0, n = 0; const sp = T.measure(' ', px, 900);
  for (const ln of lines) {
    let x = c.W * 0.156;
    for (const w of ln) {
      const ww = T.measure(w, px, 900);
      if (n < shown) { if (n >= from) { g.fillStyle = col('red'); g.fillRect(x - 10 * T.S, y - px * T.S * 0.95, ww + 20 * T.S, px * T.S * 1.2); } T.text(w, x, y, { px, weight: 900, color: '#fff', shadow: 0.5 }); }
      x += ww + sp; n++;
    }
    y += lh;
  }
}

// a huge year/number wiping in digit by digit over a dimmed picture
function yearwipe(c, it, tr) {
  const { g, T } = c, txt = String(it.text ?? ''), n = Math.min(txt.length, Math.floor((tr - it._in) / 0.12) + 1), px = it.size ?? 230, k = easeOut(prog(it, tr, 0.3));
  g.save(); g.fillStyle = `rgba(0,0,0,${0.31 * k})`; g.fillRect(0, 0, c.W, c.H); g.restore();
  const w = T.measure(txt, px, 900); T.text(txt.slice(0, n), (c.W - w) / 2, c.H / 2 + px * T.S * 0.33, { px, weight: 900, color: '#fff', shadow: 0.6 });
  if (it.sub) T.text(String(it.sub).toUpperCase(), c.W / 2, c.H / 2 + px * T.S * 0.33 + 70 * T.S, { px: 30, weight: 800, color: '#E4EAED', track: 8, align: 'center', shadow: 0, alpha: easeOut(prog(it, tr, 0.6, 0.6)) });
}

// a paper card on the right, red header, items ticked one after the other
function checklist(c, it, tr) {
  const { g, T } = c, items = list(it.items).slice(0, 6), k = easeOut(prog(it, tr, 0.35)), x = c.W * 0.5625 + (1 - k) * 80 * T.S, y = c.H * 0.11, w = c.W * 0.396, h = (110 + 76 * items.length + 30) * T.S;
  g.save(); g.globalAlpha *= clamp01(k * 2); g.shadowColor = 'rgba(0,0,0,0.4)'; g.shadowBlur = 24 * T.S; g.shadowOffsetY = 8 * T.S; g.fillStyle = '#F6ECDE'; g.fillRect(x, y, w, h); g.shadowColor = 'transparent';
  g.strokeStyle = '#962020'; g.lineWidth = 3 * T.S; g.strokeRect(x, y, w, h); g.fillStyle = '#AA1A20'; g.fillRect(x, y, w, 74 * T.S);
  T.text(String(it.title || '').toUpperCase().slice(0, 34), x + 26 * T.S, y + 50 * T.S, { px: 34, weight: 800, color: '#fff', track: 2, shadow: 0 });
  const step = Math.max(0.35, ((it.dur ?? 6) - 1.2) / Math.max(1, items.length));
  items.forEach((s, i) => {
    const yy = y + (106 + 76 * i) * T.S; g.strokeStyle = '#AA1A20'; g.lineWidth = 3 * T.S; g.strokeRect(x + 26 * T.S, yy + 8 * T.S, 34 * T.S, 34 * T.S);
    if (tr - it._in >= 0.5 + i * step) { g.lineWidth = 6 * T.S; g.lineCap = 'round'; g.beginPath(); g.moveTo(x + 31 * T.S, yy + 25 * T.S); g.lineTo(x + 41 * T.S, yy + 37 * T.S); g.lineTo(x + 58 * T.S, yy + 6 * T.S); g.stroke(); }
    T.text(String(s).slice(0, 26), x + 82 * T.S, yy + 38 * T.S, { face: 'display', italic: true, px: 46, weight: 600, color: '#28221E', shadow: 0 });
  });
  g.restore();
}

// a dark navy panel on the right 44%, thin teal edge, a title and up to three bullets
function panel(c, it, tr) {
  const { g, T } = c, k = easeOut(prog(it, tr, 0.4)), px = c.W * 0.56 + (1 - k) * 300 * T.S, bullets = list(it.bullets).slice(0, 3), edge = col(it.edge || 'teal');
  g.save(); g.fillStyle = 'rgba(12,20,32,0.94)'; g.fillRect(px, 0, c.W - px, c.H); g.fillStyle = edge; g.fillRect(px, 0, 4 * T.S, c.H);
  let y = c.H * 0.35; const x = px + 70 * T.S, mw = c.W - px - 140 * T.S;
  for (const ln of wrapWords(T, String(it.title || '').toUpperCase().split(/\s+/), 40, 800, mw, 2)) { T.text(ln.join(' '), x, y, { px: 40, weight: 800, color: '#fff', track: 2, shadow: 0 }); y += 54 * T.S; }
  y += 30 * T.S;
  bullets.forEach((b, i) => {
    const bk = easeOut(clamp01((tr - it._in - 0.5 - 0.6 * i) / 0.5)); if (bk <= 0) return; g.save(); g.globalAlpha *= bk;
    g.fillStyle = edge; g.beginPath(); g.arc(x + 4 * T.S, y - 10 * T.S, 6 * T.S, 0, Math.PI * 2); g.fill();
    for (const ln of wrapWords(T, String(b).split(/\s+/), 30, 500, mw - 40 * T.S).slice(0, 3)) { T.text(ln.join(' '), x + 34 * T.S, y, { px: 30, weight: 500, color: '#DCE2E8', shadow: 0 }); y += 40 * T.S; }
    y += 22 * T.S; g.restore();
  });
  g.restore();
}

// the cut that hides a change: RGB slices over the outgoing picture, then a white flash with cyan diagonal stripes fading out
function glitch(c, it, tr) {
  const { g, T } = c, t = tr - it._in, d = it.dur ?? 0.7, r = rnd(Math.floor(t * 30) + (it.seed ?? 0) * 7919);
  if (t < 0 || t > d) return;
  if (t < 0.14) {
    const cols = ['rgba(255,0,80,0.6)', 'rgba(0,255,200,0.6)', 'rgba(80,120,255,0.63)', 'rgba(255,255,255,0.47)', 'rgba(255,230,0,0.55)'];
    for (let i = 0; i < 18; i++) { g.fillStyle = cols[Math.floor(r() * cols.length)]; g.fillRect((r() * 1.1 - 0.1) * c.W, r() * (c.H - 40 * T.S), (0.1 + r() * 0.47) * c.W, (8 + r() * 52) * T.S); }
    return;
  }
  const k = (t - 0.14) / Math.max(0.01, d - 0.14), a = 1 - easeOut(clamp01((k - 0.45) / 0.55));
  g.save(); g.globalAlpha *= a; g.fillStyle = '#fff'; g.fillRect(0, 0, c.W, c.H); g.strokeStyle = 'rgb(150,235,245)'; g.lineWidth = 22 * T.S;
  for (let i = -c.H; i < c.W; i += 70 * T.S) { g.beginPath(); g.moveTo(i, c.H); g.lineTo(i + c.H, 0); g.stroke(); } g.restore();
}

// orange bar with a condensed white name and the role under it
function nametag(c, it, tr) {
  const { g, T } = c, [x0, y] = W_(c, it, tr, [0.047, 0.68]), k = easeOut(prog(it, tr, 0.35)), x = x0 - 60 * T.S * (1 - k);
  g.save(); g.globalAlpha *= clamp01(k * 2); g.fillStyle = col(it.accent || 'orange'); g.fillRect(x, y, 10 * T.S, 96 * T.S);
  T.text(String(it.name || '').toUpperCase(), x + 26 * T.S, y + 52 * T.S, { px: 58, weight: 900, color: '#fff', shadow: 0.7 });
  if (it.role) T.text(String(it.role), x + 28 * T.S, y + 88 * T.S, { px: 24, weight: 600, color: '#E6E6E6', shadow: 0.6 });
  g.restore();
}

// two pinned polaroids on a warm paper board, a taped title above
function polaroids(c, it, tr) {
  const { g, T } = c, rows = (Array.isArray(it.rows) ? it.rows : []).slice(0, 2);
  const bg = g.createRadialGradient(c.W / 2, c.H / 2, c.H * 0.1, c.W / 2, c.H / 2, c.H * 1.1); bg.addColorStop(0, '#C8B898'); bg.addColorStop(1, '#8F7F62'); g.fillStyle = bg; g.fillRect(0, 0, c.W, c.H);
  const title = String(it.title || '').toUpperCase(), tw = T.measure(title, 46, 800, 4) + 80 * T.S;
  g.fillStyle = '#F5F0E4'; g.fillRect((c.W - tw) / 2, 90 * T.S, tw, 80 * T.S); T.text(title, c.W / 2, 144 * T.S, { px: 46, weight: 800, color: '#3C3228', track: 4, align: 'center', shadow: 0 });
  rows.forEach((r, i) => {
    const k = easeOut(clamp01((tr - it._in - 0.3 - 0.4 * i) / 0.5)); if (k <= 0) return; const w = 560 * T.S, h = 600 * T.S, cx = c.W * (0.3 + 0.4 * i), cy = c.H * 0.56 + (1 - k) * 40 * T.S;
    g.save(); g.globalAlpha *= clamp01(k * 2); g.translate(cx, cy); g.rotate(i ? 0.087 : -0.07); g.shadowColor = 'rgba(0,0,0,0.45)'; g.shadowBlur = 26 * T.S; g.shadowOffsetY = 10 * T.S;
    g.fillStyle = '#FAFAF8'; g.fillRect(-w / 2, -h / 2, w, h); g.shadowColor = 'transparent';
    const img = c.image ? c.image(r.image || r.media) : null, px = -w / 2 + 30 * T.S, py = -h / 2 + 30 * T.S, pw = w - 60 * T.S, ph = 420 * T.S;
    if (img) { const ar = img.width / img.height, br = pw / ph; let sw = img.width, sh = img.height, sx = 0, sy = 0; if (ar > br) { sw = img.height * br; sx = (img.width - sw) / 2; } else { sh = img.width / br; sy = (img.height - sh) / 2; } g.drawImage(img, sx, sy, sw, sh, px, py, pw, ph); } else { g.fillStyle = '#3a3d42'; g.fillRect(px, py, pw, ph); }
    T.text(String(r.label || ''), 0, h / 2 - 60 * T.S, { px: 30, weight: 700, color: '#323232', align: 'center', shadow: 0 }); g.restore();
  });
}

// a horizontal timeline: a line that draws itself, milestones (year over a short label) appearing in turn
function timeline(c, it, tr) {
  const { g, T } = c, ev = (Array.isArray(it.rows) ? it.rows : []).slice(0, 7); if (!ev.length) return;
  const x0 = c.W * 0.08, x1 = c.W * 0.92, y = c.H * (it.y ?? 0.52), k = easeInOut(prog(it, tr, (it.dur ?? 3) * 0.6)), accent = col(it.accent || 'gold');
  if (it.title) T.text(String(it.title).toUpperCase(), x0, c.H * 0.16, { px: 30, weight: 800, color: '#fff', track: 5, shadow: 0 });
  g.save(); g.strokeStyle = 'rgba(255,255,255,0.35)'; g.lineWidth = 3 * T.S; g.beginPath(); g.moveTo(x0, y); g.lineTo(x0 + (x1 - x0) * k, y); g.stroke(); g.restore();
  ev.forEach((e, i) => {
    const px = x0 + ((x1 - x0) * (i + 0.5)) / ev.length, t0 = it._in + 0.3 + i * ((it.dur ?? 3) * 0.6) / ev.length, a = easeOut(clamp01((tr - t0) / 0.45)); if (a <= 0) return;
    g.save(); g.globalAlpha *= a; const up = i % 2 === 0, dy = up ? -1 : 1; g.strokeStyle = accent; g.lineWidth = 2 * T.S; g.beginPath(); g.moveTo(px, y); g.lineTo(px, y + dy * 70 * T.S * a); g.stroke();
    g.fillStyle = accent; g.beginPath(); g.arc(px, y, 9 * T.S, 0, Math.PI * 2); g.fill();
    T.text(String(e.year ?? e.label ?? ''), px, y + (up ? -92 : 138) * T.S, { face: 'display', px: 54, weight: 700, color: accent, align: 'center', shadow: 0.4 });
    T.text(String(e.text ?? '').toUpperCase(), px, y + (up ? -160 : 182) * T.S, { px: 26, weight: 700, color: '#E4EAED', track: 2, align: 'center', shadow: 0 });
    g.restore();
  });
}

// three outlined circles on black, each with a word, popping in one by one
function threerings(c, it, tr) {
  const { g, T } = c, items = list(it.items).slice(0, 3), k0 = easeOut(prog(it, tr, 0.3));
  if (it.solid !== false) { g.save(); g.globalAlpha *= k0; g.fillStyle = '#000'; g.fillRect(0, 0, c.W, c.H); g.restore(); }
  items.forEach((s, i) => {
    const k = easeOut(clamp01((tr - it._in - 0.25 - 0.35 * i) / 0.35)); if (k <= 0) return; const cx = c.W / 2 + (i - (items.length - 1) / 2) * 420 * T.S, r = 120 * T.S * (0.6 + 0.4 * k);
    g.save(); g.globalAlpha *= k; g.strokeStyle = '#fff'; g.lineWidth = 5 * T.S; g.beginPath(); g.arc(cx, c.H / 2, r, 0, Math.PI * 2); g.stroke();
    T.text(String(s).toUpperCase(), cx, c.H / 2 + 10 * T.S, { px: 28, weight: 800, color: '#fff', track: 2, align: 'center', shadow: 0 }); g.restore();
  });
}

// small caps typed in at the bottom-left over the shot, on a soft dark floor
function typedcaption(c, it, tr) {
  const { g, T } = c, txt = String(it.text || '').toUpperCase(), n = Math.max(1, Math.min(txt.length, Math.floor((tr - it._in) / 0.03))), k = easeOut(prog(it, tr, 0.3));
  const gr = g.createLinearGradient(0, c.H - 260 * T.S, 0, c.H); gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(1, 'rgba(0,0,0,0.55)');
  g.save(); g.globalAlpha *= k; g.fillStyle = gr; g.fillRect(0, c.H - 260 * T.S, c.W, 260 * T.S); g.restore();
  T.text(txt.slice(0, n), c.W * 0.042, c.H - 150 * T.S + 34 * T.S, { px: it.size ?? 34, weight: 800, color: '#fff', track: 3, shadow: 0.6 });
}

// a case file on paper: the name circled in red, facts typed under it ("fields" = rows "KEY=value")
function dossier(c, it, tr) {
  const { g, T } = c, k0 = easeOut(prog(it, tr, 0.3)), rows = (Array.isArray(it.rows) ? it.rows : []).slice(0, 6), z = 1 + 0.04 * clamp01((tr - it._in) / 6);
  g.save(); g.globalAlpha *= k0; g.translate(c.W / 2, c.H / 2); g.scale(z, z); g.translate(-c.W / 2, -c.H / 2);
  g.fillStyle = '#E8E6E0'; g.fillRect(0, 0, c.W, c.H); g.fillStyle = 'rgba(0,0,0,0.025)'; for (let x = 0; x < c.W; x += 6 * T.S) g.fillRect(x, 0, 3 * T.S, c.H);
  let size = 120; const title = String(it.title || ''); while (T.measure(title, size, 900, 0, 'ui') > c.W - 400 * T.S && size > 60) size -= 6;
  const tw = T.measure(title, size, 900), x = (c.W - tw) / 2, y = 330 * T.S;
  T.text(title, x, y, { px: size, weight: 900, color: '#141414', shadow: 0 });
  const k = easeOut(clamp01((tr - it._in - 0.4) / 0.8));
  if (k > 0) { g.strokeStyle = '#C8141E'; g.lineWidth = 10 * T.S; g.lineCap = 'round'; g.beginPath(); g.ellipse(c.W / 2, y - size * T.S * 0.32, tw / 2 + 60 * T.S, size * T.S * 0.78, 0, 3.5, 3.5 + Math.PI * 2 * k); g.stroke(); }
  rows.forEach((r, i) => { if (tr - it._in < 0.9 + 0.3 * i) return; const yy = 620 * T.S + i * 70 * T.S; T.text(`${r.label}:`, c.W * 0.27, yy, { px: 34, weight: 600, color: '#5A5A5A', shadow: 0 }); T.text(String(r.text ?? r.value ?? '').toUpperCase(), c.W * 0.42, yy, { px: 34, weight: 700, color: '#141414', shadow: 0 }); });
  g.restore();
}

// a headline over the shot, left-centre, on a dark wash from the left; a grey line under it
function headline(c, it, tr) {
  const { g, T } = c, k = easeOut(prog(it, tr, 0.4)), wash = g.createLinearGradient(0, 0, c.W * 0.57, 0);
  wash.addColorStop(0, 'rgba(0,0,0,0.6)'); wash.addColorStop(1, 'rgba(0,0,0,0)'); g.save(); g.globalAlpha *= k; g.fillStyle = wash; g.fillRect(0, 0, c.W * 0.57, c.H); g.restore();
  let y = c.H * 0.4; const x = c.W * 0.083 - 50 * T.S * (1 - k);
  g.save(); g.globalAlpha *= k;
  for (const ln of wrapWords(T, String(it.title || '').split(/\s+/), 46, 800, c.W * 0.4).slice(0, 3)) { T.text(ln.join(' '), x, y, { px: it.size ?? 46, weight: 800, color: '#fff', shadow: 0.6 }); y += 58 * T.S; }
  if (it.sub && tr - it._in > 0.4) T.text(String(it.sub), x + 2 * T.S, y + 30 * T.S, { px: 28, weight: 500, color: '#CDD2D7', shadow: 0.5 });
  g.restore();
}

// a still in a thin light frame on dark navy, its caption under it, slowly pushing in
function framed(c, it, tr) {
  const { g, T } = c, k = easeOut(prog(it, tr, 0.3)), z = 1 + 0.05 * clamp01((tr - it._in) / (it.dur ?? 6)), w = 980 * T.S * z, h = 560 * T.S * z, x = (c.W - w) / 2, y = (c.H - h) / 2 - 40 * T.S;
  g.save(); g.globalAlpha *= k; g.fillStyle = '#0E1624'; g.fillRect(0, 0, c.W, c.H); g.fillStyle = '#E6E8EC'; g.fillRect(x - 8 * T.S, y - 8 * T.S, w + 16 * T.S, h + 16 * T.S);
  const img = c.image ? c.image(it.image) : null;
  if (img) { const ar = img.width / img.height, br = w / h; let sw = img.width, sh = img.height, sx = 0, sy = 0; if (ar > br) { sw = img.height * br; sx = (img.width - sw) / 2; } else { sh = img.width / br; sy = (img.height - sh) / 2; } g.drawImage(img, sx, sy, sw, sh, x, y, w, h); } else { g.fillStyle = '#2a3140'; g.fillRect(x, y, w, h); }
  T.text(String(it.caption || '').toUpperCase(), c.W / 2, y + h + 60 * T.S, { px: 26, weight: 700, color: '#E1E4E8', track: 6, align: 'center', shadow: 0 }); g.restore();
}

// orange place tag with a white pulse ring beside it (pins to a map place with "follow")
function placepulse(c, it, tr) {
  const { g, T } = c, [x, y] = W_(c, it, tr, [0.53, 0.4]), k = easeOut(prog(it, tr, 0.35)), pulse = ((tr - it._in) % 1.2) / 1.2, rr = (14 + 36 * pulse) * T.S, name = String(it.name || '').toUpperCase(), sub = String(it.sub || '');
  const w = Math.max(T.measure(name, 38, 800, 2), sub ? T.measure(sub, 22, 600) : 0) + 44 * T.S, h = (sub ? 92 : 62) * T.S;
  g.save(); g.globalAlpha *= clamp01(k * 2); g.strokeStyle = `rgba(255,255,255,${1 - pulse})`; g.lineWidth = 4 * T.S; g.beginPath(); g.arc(x - 70 * T.S, y + 30 * T.S, rr, 0, Math.PI * 2); g.stroke();
  g.fillStyle = '#fff'; g.beginPath(); g.arc(x - 70 * T.S, y + 30 * T.S, 8 * T.S, 0, Math.PI * 2); g.fill();
  const off = 30 * T.S * (1 - k); g.fillStyle = 'rgba(255,112,20,0.94)'; g.fillRect(x + off, y, w, h);
  T.text(name, x + off + 22 * T.S, y + 42 * T.S, { px: 38, weight: 800, color: '#fff', track: 2, shadow: 0 }); if (sub) T.text(sub, x + off + 22 * T.S, y + 76 * T.S, { px: 22, weight: 600, color: '#FFECDC', shadow: 0 });
  g.restore();
}

// a row of cards dealt in one by one: heading, big value, unit (a forecast, a few countries, a few dates)
function cardsrow(c, it, tr) {
  const { g, T } = c, k0 = easeOut(prog(it, tr, 0.3)), rows = (Array.isArray(it.rows) ? it.rows : []).slice(0, 5); if (!rows.length) return;
  g.save(); g.globalAlpha *= k0; g.fillStyle = '#0E1624'; g.fillRect(0, 0, c.W, c.H); g.restore();
  T.text(String(it.title || '').toUpperCase(), c.W / 2, 170 * T.S, { px: 44, weight: 800, color: '#fff', track: 3, align: 'center', shadow: 0 });
  const cw = 280 * T.S, gap = 36 * T.S, x0 = (c.W - (rows.length * cw + (rows.length - 1) * gap)) / 2;
  rows.forEach((r, i) => {
    const k = easeOut(clamp01((tr - it._in - 0.25 - 0.18 * i) / 0.5)); if (k <= 0) return; const x = x0 + i * (cw + gap), y = 330 * T.S + 40 * T.S * (1 - k);
    g.save(); g.globalAlpha *= k; g.fillStyle = '#1A263A'; g.strokeStyle = '#3C5A78'; g.lineWidth = 2 * T.S; g.beginPath(); g.roundRect(x, y, cw, 420 * T.S, 18 * T.S); g.fill(); g.stroke();
    T.text(String(r.label || '').toUpperCase(), x + cw / 2, y + 80 * T.S, { px: 30, weight: 800, color: '#BECDDC', track: 2, align: 'center', shadow: 0 });
    T.text(String(r.text ?? r.value ?? ''), x + cw / 2, y + 230 * T.S, { px: 70, weight: 900, color: '#fff', align: 'center', shadow: 0.3 });
    if (it.unit) T.text(String(it.unit).toUpperCase(), x + cw / 2, y + 320 * T.S, { px: 30, weight: 800, color: '#00CDEB', track: 2, align: 'center', shadow: 0 }); g.restore();
  });
}

export const NEWS_PRIMS = { pill, boxquote, yearwipe, checklist, panel, glitch, nametag, polaroids, timeline, threerings, typedcaption, dossier, headline, framed, placepulse, cardsrow };
