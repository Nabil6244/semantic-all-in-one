// Picture-card art (horror story, lib/horror.mjs). drawCard paints a code-made card on a 2D canvas: a phone or clock showing the time, a name
// in ink or pencil on a wrapper or paper, a child's handwriting, drawings with blank faces, a blank ID card or letter, a note. drawPicture
// fills the same canvas with a fetched picture. Nothing here touches WebGL: web/look.js adds the grain and the scene's grade when it composites.
// Every mark comes from a generator seeded by the card's id, so a frame looks the same however the film is cut into render parts.
import { makeRng } from '../lib/rng.mjs';

const HAND_FONT = '"Bradley Hand", "Segoe Script", "Snell Roundhand", "Comic Sans MS", cursive';
const CHILD_FONT = '"Chalkboard SE", "Comic Sans MS", "Marker Felt", cursive';

const backdrop = (g, w, h, a = '#17130f', b = '#050403') => { const q = g.createRadialGradient(w / 2, h * 0.45, h * 0.1, w / 2, h * 0.45, w * 0.7); q.addColorStop(0, a); q.addColorStop(1, b); g.fillStyle = q; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 70; i++) { g.fillStyle = `rgba(125,88,52,${(0.05 + 0.05 * Math.sin(i * 12.9)).toFixed(3)})`; g.fillRect(0, (i / 70) * h, w, h / 80); } };   // a dark table: the card lies somewhere, not on nothing
function roundRect(g, x, y, w, h, r) { g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r); g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath(); }

/** a sheet lying a little crooked, with paper grain and a fold; subtitles stay readable under it, so what is written sits in its upper part */
function paper(g, w, h, R, { color = '#e9dfc6', ruled = false } = {}) {
  backdrop(g, w, h);
  g.save(); g.translate(w / 2, h / 2); g.rotate(R.range(-0.025, 0.025));
  const pw = w * 0.84, ph = h * 1.16, x = -pw / 2, y = -ph / 2;
  g.shadowColor = 'rgba(0,0,0,0.7)'; g.shadowBlur = h * 0.03; g.fillStyle = color; g.fillRect(x, y, pw, ph); g.shadowBlur = 0;
  for (let i = 0; i < 900; i++) { g.fillStyle = R() < 0.5 ? 'rgba(90,70,40,0.05)' : 'rgba(255,255,255,0.06)'; g.fillRect(x + R() * pw, y + R() * ph, R.range(1, h * 0.006), R.range(1, h * 0.006)); }
  g.fillStyle = 'rgba(60,45,25,0.08)'; g.fillRect(x, y + ph * 0.56, pw, h * 0.004);
  if (ruled) { g.strokeStyle = 'rgba(70,110,170,0.32)'; g.lineWidth = Math.max(1, h * 0.002); for (let yy = y + h * 0.1; yy < y + ph; yy += h * 0.105) { g.beginPath(); g.moveTo(x, yy); g.lineTo(x + pw, yy); g.stroke(); } }
  g.restore();
}

function wrapText(g, text, maxW) {
  const lines = []; let line = '';
  for (const word of String(text).split(/\s+/)) { const next = line ? `${line} ${word}` : word; if (line && g.measureText(next).width > maxW) { lines.push(line); line = word; } else line = next; }
  if (line) lines.push(line);
  return lines;
}

/** written by a hand: letter by letter on a wobbling line. pencil = grey and grainy, ink = a slight bleed, crayon = thick and doubled */
function writeHand(g, text, cx, cy, size, { style = 'ink', color = '#1c2f6b', child = false, maxW = 0, R }) {
  const print = style === 'print';   // cheap printed letters: even and upright, no hand in them
  if (print) { child = false; text = String(text).toUpperCase(); }
  const font = (s) => print ? `bold ${Math.round(s * 0.8)}px "Helvetica Neue", Arial, sans-serif` : `${child || style === 'crayon' ? '' : 'italic '}${style === 'crayon' ? 'bold ' : ''}${Math.round(s)}px ${child || style === 'crayon' ? CHILD_FONT : HAND_FONT}`;
  let s = size; g.font = font(s);
  let lines = wrapText(g, text, maxW || 1e9);
  while (s > size * 0.45 && (lines.length > 3 || lines.some((l) => g.measureText(l).width > maxW && maxW))) { s *= 0.88; g.font = font(s); lines = wrapText(g, text, maxW || 1e9); }
  g.textAlign = 'left'; g.textBaseline = 'middle';
  const wobble = print ? 0.006 : child ? 0.1 : 0.035, passes = style === 'crayon' ? 3 : style === 'pencil' ? 2 : 1;
  lines.forEach((l, k) => {
    let x = cx - g.measureText(l).width / 2; const y0 = cy + (k - (lines.length - 1) / 2) * s * 1.3, tilt = R.range(-0.02, 0.02);
    for (const ch of l) {
      const adv = g.measureText(ch).width, dy = R.range(-s, s) * wobble, rot = R.range(-wobble, wobble) * 1.6 + tilt;
      for (let p = 0; p < passes; p++) {
        g.save(); g.translate(x + adv / 2 + (p ? R.range(-1, 1) * s * 0.012 : 0), y0 + dy + (p ? R.range(-1, 1) * s * 0.012 : 0)); g.rotate(rot);
        g.fillStyle = color; g.globalAlpha = style === 'pencil' ? 0.62 : style === 'crayon' ? 0.7 : 0.94;
        if (style === 'ink') { g.shadowColor = color; g.shadowBlur = s * 0.03; }
        g.fillText(ch, -adv / 2, 0); g.restore();
      }
      x += adv * (child ? R.range(1.02, 1.14) : 1);
    }
    if (style === 'pencil') for (let i = 0; i < 260; i++) { g.fillStyle = 'rgba(233,223,198,0.55)'; g.fillRect(cx - maxW / 2 + R() * maxW, y0 - s * 0.6 + R() * s * 1.2, 1.5, 1.5); }   // the paper's tooth shows through
  });
}

function phoneScreen(g, w, h, c, R) {
  backdrop(g, w, h, '#0c0e13', '#020203');
  const pw = h * 0.72, x = (w - pw) / 2, y = -h * 0.08, ph = h * 1.3;
  g.fillStyle = '#2a2c33'; roundRect(g, x - h * 0.02, y, pw + h * 0.04, ph, h * 0.06); g.fill();
  g.strokeStyle = 'rgba(255,255,255,0.24)'; g.lineWidth = Math.max(1, h * 0.003); g.stroke();
  const q = g.createLinearGradient(0, y, 0, y + ph); q.addColorStop(0, '#1d3158'); q.addColorStop(0.55, '#101a30'); q.addColorStop(1, '#070b14');
  g.fillStyle = q; roundRect(g, x, y + h * 0.015, pw, ph - h * 0.03, h * 0.05); g.fill();
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#f2f5fb'; g.shadowColor = 'rgba(160,190,255,0.6)'; g.shadowBlur = h * 0.03;
  g.font = `200 ${Math.round(h * 0.2)}px "Helvetica Neue", Arial, sans-serif`; g.fillText(c.time, w / 2, h * 0.33); g.shadowBlur = 0;
  g.fillStyle = 'rgba(235,240,250,0.75)'; roundRect(g, w / 2 - h * 0.09, h * 0.46, h * 0.18, h * 0.012, h * 0.006); g.fill();
  for (let i = 0; i < 90; i++) { g.fillStyle = 'rgba(255,255,255,0.025)'; g.fillRect(x + R() * pw, y + R() * ph, R.range(4, h * 0.05), 1); }   // smears on the glass
}

// seven-segment digits: a bedside clock that is exact in any font
const SEG = { 0: 'abcdef', 1: 'bc', 2: 'abged', 3: 'abgcd', 4: 'fgbc', 5: 'afgcd', 6: 'afgedc', 7: 'abc', 8: 'abcdefg', 9: 'abfgcd' };
function segDigit(g, d, x, y, dw, dh, t) {
  const on = SEG[d] || ''; const seg = { a: [x + t, y, dw - 2 * t, t], d: [x + t, y + dh - t, dw - 2 * t, t], g: [x + t, y + (dh - t) / 2, dw - 2 * t, t], f: [x, y + t, t, dh / 2 - t], e: [x, y + dh / 2, t, dh / 2 - t], b: [x + dw - t, y + t, t, dh / 2 - t], c: [x + dw - t, y + dh / 2, t, dh / 2 - t] };
  for (const k of on) g.fillRect(...seg[k]);
}
function clockFace(g, w, h, c) {
  backdrop(g, w, h, '#120d0b', '#030202');
  const bw = w * 0.66, bh = h * 0.46, x = (w - bw) / 2, y = h * 0.1;
  g.fillStyle = '#29292e'; roundRect(g, x, y, bw, bh, h * 0.03); g.fill(); g.fillStyle = '#060405'; roundRect(g, x + bw * 0.04, y + bh * 0.1, bw * 0.92, bh * 0.8, h * 0.015); g.fill();
  const [hh, mm] = String(c.time).split(':'), digits = [...String(Number(hh) || 12), ':', ...String(mm || '00').padStart(2, '0')], n = digits.length - 1;
  const dh = bh * 0.62, dw = dh * 0.5, t = dh * 0.11, gap = dw * 0.3, colon = dw * 0.5, total = dw * n + gap * (n - 1) + colon + gap * 0.5; let px = w / 2 - total / 2; const py = y + (bh - dh) / 2;
  g.fillStyle = '#ff3b2e'; g.shadowColor = '#ff2a1a'; g.shadowBlur = h * 0.025;
  for (const ch of digits) { if (ch === ':') { g.fillRect(px + colon * 0.2, py + dh * 0.28, t, t); g.fillRect(px + colon * 0.2, py + dh * 0.62, t, t); px += colon + gap * 0.5; } else { segDigit(g, ch, px, py, dw, dh, t); px += dw + gap; } }
  g.shadowBlur = 0;
}

function wrapperCard(g, w, h, c, R) {
  backdrop(g, w, h);
  const col = c.wrapColor || '#d9b13b', bw = w * 0.56, bh = h * 0.46, x = (w - bw) / 2, y = h * 0.12;
  // the twisted ends, then the foil body with its crinkles
  g.fillStyle = col; for (const s of [-1, 1]) { const ex = s < 0 ? x : x + bw, far = ex + s * w * 0.14; g.beginPath(); g.moveTo(ex, y + bh * 0.42); g.lineTo(far, y + bh * 0.1); g.lineTo(far - s * w * 0.02, y + bh * 0.5); g.lineTo(far, y + bh * 0.92); g.lineTo(ex, y + bh * 0.58); g.closePath(); g.fill(); }
  g.fillStyle = col; roundRect(g, x, y, bw, bh, h * 0.04); g.fill();
  for (let i = 0; i < 150; i++) { const px = x + R() * bw, py = y + R() * bh; g.fillStyle = R() < 0.5 ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.09)'; g.beginPath(); g.moveTo(px, py); g.lineTo(px + R.range(-1, 1) * h * 0.09, py + R.range(-1, 1) * h * 0.09); g.lineTo(px + R.range(-1, 1) * h * 0.09, py + R.range(-1, 1) * h * 0.09); g.closePath(); g.fill(); }
  // what is written sits on a pale band so dark ink still reads on any foil
  g.fillStyle = 'rgba(245,238,220,0.92)'; g.fillRect(x + bw * 0.1, y + bh * 0.3, bw * 0.8, bh * 0.4);
  writeHand(g, c.text || 'your name', w / 2, y + bh * 0.5, h * 0.09, { style: c.style, color: c.color, child: c.child, maxW: bw * 0.74, R });
}

function nameOnPaper(g, w, h, c, R) { paper(g, w, h, R); writeHand(g, c.text || 'your name', w / 2, h * 0.34, h * 0.14, { style: c.style, color: c.color, child: c.child, maxW: w * 0.68, R }); }
function handwriting(g, w, h, c, R) { paper(g, w, h, R, { ruled: true, color: '#efe8d6' }); writeHand(g, c.text || 'your name', w / 2, h * 0.34, h * 0.11, { style: c.style === 'ink' ? 'pencil' : c.style, color: c.style === 'ink' ? '#55565c' : c.color, child: c.child !== false, maxW: w * 0.68, R }); }
function noteCard(g, w, h, c, R) { paper(g, w, h, R, { color: '#e2d7bc' }); writeHand(g, c.text || c.what || '…', w / 2, h * 0.34, h * 0.09, { style: c.style, color: c.color, child: c.child, maxW: w * 0.68, R }); }

function envelope(g, w, h, c, R) {
  backdrop(g, w, h);
  const bw = w * 0.62, bh = h * 0.58, x = (w - bw) / 2, y = h * 0.06;
  g.save(); g.translate(w / 2, y + bh / 2); g.rotate(R.range(-0.03, 0.03)); g.translate(-w / 2, -(y + bh / 2));
  g.shadowColor = 'rgba(0,0,0,0.7)'; g.shadowBlur = h * 0.03; g.fillStyle = '#d9cdb0'; g.fillRect(x, y, bw, bh); g.shadowBlur = 0;
  g.fillStyle = '#cbbd9d'; g.beginPath(); g.moveTo(x, y); g.lineTo(x + bw, y); g.lineTo(x + bw / 2, y + bh * 0.52); g.closePath(); g.fill();
  g.strokeStyle = 'rgba(70,55,35,0.4)'; g.lineWidth = Math.max(1, h * 0.003); g.stroke();
  for (const [a, b] of [[x, y + bh], [x + bw, y + bh]]) { g.beginPath(); g.moveTo(a, b); g.lineTo(x + bw / 2, y + bh * 0.42); g.stroke(); }
  g.restore();
  if (c.text) writeHand(g, c.text, w / 2, y + bh * 0.72, h * 0.07, { style: c.style, color: c.color, child: c.child, maxW: bw * 0.7, R });
}

function letterCard(g, w, h, c, R) {
  if (c.envelope) return envelope(g, w, h, c, R);
  paper(g, w, h, R);
  if (c.text) writeHand(g, c.text, w / 2, h * 0.34, h * 0.09, { style: c.style, color: c.color, child: c.child, maxW: w * 0.68, R });
  else { g.strokeStyle = 'rgba(70,60,45,0.26)'; g.lineWidth = Math.max(1, h * 0.002); for (let k = 0; k < 7; k++) { const yy = h * (0.12 + k * 0.1); g.beginPath(); g.moveTo(w * 0.16, yy); g.lineTo(w * 0.84, yy + R.range(-1, 1)); g.stroke(); } }   // ruled, nothing written: the blank is the point
}

/** a figure as a child draws one: a round head, a stick body, arms and legs, gone over more than once with a wax crayon */
function crayonFigure(g, x, y, s, color, blank, R) {
  const j = () => R.range(-1, 1) * s * 0.035, line = (x0, y0, x1, y1) => { for (let p = 0; p < 3; p++) { g.beginPath(); g.moveTo(x0 + j(), y0 + j()); g.lineTo(x1 + j(), y1 + j()); g.stroke(); } };
  g.strokeStyle = color; g.lineWidth = Math.max(2, s * 0.042); g.globalAlpha = 0.75; g.lineCap = 'round';
  for (let p = 0; p < 3; p++) { g.beginPath(); g.ellipse(x + R.range(-1, 1) * s * 0.015, y, s * 0.2, s * 0.23, 0, 0, Math.PI * 2); g.stroke(); }
  // a body scribbled in, back and forth, the way a child colours a coat
  g.beginPath(); for (let k = 0; k <= 12; k++) { const u = k / 12, half = s * (0.08 + 0.15 * u); g.lineTo(x + (k % 2 ? half : -half) + j() * 0.4, y + s * (0.27 + 0.48 * u)); } g.stroke();
  line(x, y + s * 0.38, x - s * 0.3, y + s * 0.58); line(x, y + s * 0.38, x + s * 0.3, y + s * 0.58); line(x, y + s * 0.75, x - s * 0.2, y + s * 1.08); line(x, y + s * 0.75, x + s * 0.2, y + s * 1.08);
  if (!blank) { g.fillStyle = color; g.beginPath(); g.arc(x - s * 0.07, y - s * 0.04, s * 0.025, 0, 7); g.arc(x + s * 0.07, y - s * 0.04, s * 0.025, 0, 7); g.fill(); g.beginPath(); g.arc(x, y + s * 0.03, s * 0.09, 0.2, Math.PI - 0.2); g.stroke(); }
  g.globalAlpha = 1;
}
function drawingCard(g, w, h, c, R) {
  paper(g, w, h, R, { color: '#f0ead9' });
  const colors = ['#b0302a', '#2f5fa8', '#3f7a3a', '#6a3f8f'], n = 3 + R.int(0, 1), s = h * 0.46;
  for (let i = 0; i < n; i++) crayonFigure(g, w * (0.24 + 0.52 * (i / Math.max(1, n - 1))), h * (0.17 + R.range(-0.01, 0.02)), s * (i === 0 ? 1.05 : R.range(0.74, 0.92)), colors[i % colors.length], c.blankFaces !== false, R);
  g.strokeStyle = '#3f7a3a'; g.lineWidth = h * 0.006; g.globalAlpha = 0.6; for (let p = 0; p < 2; p++) { g.beginPath(); g.moveTo(w * 0.12, h * 0.71); g.lineTo(w * 0.88, h * (0.7 + R() * 0.01)); g.stroke(); } g.globalAlpha = 1;
  if (c.text) writeHand(g, c.text, w / 2, h * 0.075, h * 0.06, { style: 'crayon', color: '#b0302a', child: true, maxW: w * 0.7, R });
}

function idCard(g, w, h, c, R) {
  backdrop(g, w, h, '#1a1612', '#050403');
  const bw = w * 0.66, bh = h * 0.62, x = (w - bw) / 2, y = h * 0.05;
  g.save(); g.translate(w / 2, y + bh / 2); g.rotate(R.range(-0.03, 0.03)); g.translate(-w / 2, -(y + bh / 2));
  g.shadowColor = 'rgba(0,0,0,0.7)'; g.shadowBlur = h * 0.03; g.fillStyle = '#dfe3e2'; roundRect(g, x, y, bw, bh, h * 0.03); g.fill(); g.shadowBlur = 0;
  g.fillStyle = '#2f5a8f'; roundRect(g, x, y, bw, bh * 0.17, h * 0.03); g.fill(); g.fillRect(x, y + bh * 0.09, bw, bh * 0.08);
  g.fillStyle = '#f2f4f4'; g.font = `bold ${Math.round(bh * 0.085)}px "Helvetica Neue", Arial, sans-serif`; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText("DRIVER LICENSE", x + bw * 0.05, y + bh * 0.085);
  const px = x + bw * 0.05, py = y + bh * 0.25, pw = bw * 0.28, ph = bh * 0.62;
  g.fillStyle = '#c4c9c8'; g.fillRect(px, py, pw, ph); g.strokeStyle = 'rgba(40,50,60,0.4)'; g.lineWidth = Math.max(1, h * 0.003); g.strokeRect(px, py, pw, ph);   // the photo box: nobody in it
  g.fillStyle = 'rgba(50,60,70,0.55)'; g.font = `600 ${Math.round(bh * 0.04)}px "Helvetica Neue", Arial, sans-serif`;
  const fx = px + pw + bw * 0.05, fw = bw * 0.55; ['NAME', 'ADDRESS', 'DATE OF BIRTH', 'EXPIRES'].forEach((lab, k) => {
    const fy = py + k * bh * 0.16; g.fillText(lab, fx, fy); g.fillStyle = 'rgba(50,60,70,0.25)'; g.fillRect(fx, fy + bh * 0.08, fw, Math.max(1, h * 0.003)); g.fillStyle = 'rgba(50,60,70,0.55)';
  });
  g.restore();
  if (c.text) writeHand(g, c.text, x + bw * 0.66, y + bh * 0.33, bh * 0.08, { style: 'ink', color: '#1c2f6b', maxW: fw, R });
}

const ART = { phone_screen: phoneScreen, clock: clockFace, name: (g, w, h, c, R) => (c.surface === 'wrapper' ? wrapperCard : nameOnPaper)(g, w, h, c, R), handwriting, drawing: drawingCard, id_card: idCard, letter: letterCard, note: noteCard };

/** paints the code-made card: any kind this file does not know is a note, so a card is never blank */
export function drawCard(g, w, h, card) {
  (ART[card.kind] || noteCard)(g, w, h, card, makeRng(`card:${card.id}:${card.kind}`));
}

/** a fetched picture, cropped to fill the frame */
export function drawPicture(g, w, h, img) {
  const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height, k = Math.max(w / iw, h / ih), dw = iw * k, dh = ih * k;
  g.fillStyle = '#000'; g.fillRect(0, 0, w, h); g.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
}
