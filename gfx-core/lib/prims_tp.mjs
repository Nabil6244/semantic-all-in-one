// GFX-CORE BROADCAST PRIMITIVES: the general-purpose graphics of the Weather engine (Teamplate title cards, count-up stat, lower third,
// corner counter, record card and badge, before/after label, value chip on a map place, scale bar), re-drawn as universal canvas pieces.
// Nothing from the weather code is imported and no weather data is assumed: every word and number comes from the template's slots.
import { param } from './tpl.mjs';
import { col, clamp01, easeOut, easeInOut, fmtNum, theme } from './theme.mjs';

const TP = { red: '#D3122B', orange: '#E8552B', black: 'rgba(10,10,12,0.92)', yellow: '#FBE040', navy: 'rgba(8,19,32,0.88)', blue: '#9FB3C8' };
const pos = (c, it, tr, d) => { const a = c.follow && it.follow ? c.follow : param(it, 'at', tr, d); return [a[0] * c.W, a[1] * c.H]; };
const prog = (it, tr, dur = 1, delay = 0) => clamp01((tr - it._in - delay) / Math.max(0.05, dur));
const list = (v) => (Array.isArray(v) ? v : String(v ?? '').split(/[;|]/).map((s) => s.trim()).filter(Boolean));
const rows = (v) => (Array.isArray(v) ? v : []);
const num = (v, d = 0) => { const n = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/,/g, '')); return Number.isFinite(n) ? n : d; };
const vignette = (g, W, H, s) => { const r = g.createRadialGradient(W / 2, H / 2, H * 0.28, W / 2, H / 2, H * 1.06); r.addColorStop(0, 'rgba(0,0,0,0)'); r.addColorStop(1, `rgba(0,0,0,${s})`); g.fillStyle = r; g.fillRect(0, 0, W, H); };

// heavy white words one after another, the key word in a red box ("THE [PATH]"); words = list, accent = index of the boxed word
function kwtitle(c, it, tr) {
  const { g, T } = c, words = list(it.words).map((w) => String(w).toUpperCase()); if (!words.length) return;
  const accent = Math.max(0, Math.min(words.length - 1, num(it.accent, words.length - 1))), padX = 24, gap = 28, boxH = 138, maxW = 1560;
  let px = it.size ?? 100; const width = (ws, p) => ws.reduce((s, w, i) => s + T.measure(w, p, 900, 1.5) / T.S + (words.indexOf(w) === accent && ws[i] === words[accent] ? 2 * padX : 0), 0) + gap * (ws.length - 1);
  while (px > 64 && width(words, px) > maxW) px -= 4;
  const lines = width(words, px) <= maxW ? [words.map((w, i) => i)] : (() => { const head = words.map((_, i) => i).filter((i) => i !== accent), out = []; let cur = []; for (const i of head) { if (cur.length && width([...cur, i].map((k) => words[k]), px) > maxW) { out.push(cur); cur = []; } cur.push(i); } if (cur.length) out.push(cur); out.push([accent]); return out; })();
  const lineH = boxH + 22, top = c.H / 2 - (lines.length * lineH - 22) * T.S / 2; let n = 0;
  lines.forEach((ln, li) => {
    const lw = ln.reduce((s, i) => s + T.measure(words[i], px, 900, 1.5) + (i === accent ? 2 * padX * T.S : 0), 0) + gap * T.S * (ln.length - 1);
    let x = lines.length === 1 ? (c.W - lw) / 2 : 210 * T.S; const y = top + li * lineH * T.S + boxH * T.S / 2 + px * T.S * 0.36;
    for (const i of ln) {
      const w = words[i], ww = T.measure(w, px, 900, 1.5) + (i === accent ? 2 * padX * T.S : 0), k = easeOut(clamp01((tr - it._in - n * 0.28) / 0.18)); n++;
      if (k > 0) { g.save(); g.globalAlpha *= k;
        if (i === accent) { const wipe = clamp01((tr - it._in - (n - 1) * 0.28) / 0.22); g.fillStyle = TP.red; g.fillRect(x, y - px * T.S * 0.36 - boxH * T.S / 2, ww * wipe, boxH * T.S); if (wipe >= 1) T.text(w, x + padX * T.S, y, { px, weight: 900, color: '#fff', track: 1.5, shadow: 0 }); }
        else T.text(w, x, y, { px, weight: 900, color: '#fff', track: 1.5, shadow: 0.6 });
        g.restore(); }
      x += ww + gap * T.S;
    }
  });
}

// a serif italic kicker over a tracked title wiped in from the left ("SEPTEMBER 2022" / "HURRICANE IAN")
function chaptercard(c, it, tr) {
  const { g, T } = c, title = String(it.title || '').toUpperCase(); let px = it.size ?? 92; while (px > 56 && T.measure(title, px, 500, 7) > 1460 * T.S) px -= 4;
  const kk = easeOut(prog(it, tr, 0.45)), tk = clamp01((tr - it._in - 0.55) / 0.9), x = c.W * 0.12;
  if (it.kicker) T.text(String(it.kicker), x + 46 * T.S, c.H * 0.567, { face: 'display', italic: true, px: 46, weight: 500, color: 'rgba(255,255,255,0.94)', track: 1, shadow: 0.6, alpha: kk });
  if (tk > 0) { const w = T.measure(title, px, 500, 7); g.save(); g.beginPath(); g.rect(x - 10 * T.S, c.H * 0.67 - px * T.S * 1.1, (w + 40 * T.S) * tk, px * T.S * 1.5); g.clip(); T.text(title, x, c.H * 0.67, { px, weight: 500, color: '#fff', track: 7, shadow: 0.6 }); g.restore(); }
}

// a small tag: tone "black" = context tag at the top centre, "orange" = a fact tag in the middle of the frame; it opens from its centre
function ctxtag(c, it, tr) {
  const { g, T } = c, tone = it.tone === 'orange' ? 'orange' : 'black', px = tone === 'orange' ? 32 : 20, h = (tone === 'orange' ? 60 : 40) * T.S, padX = (tone === 'orange' ? 22 : 18) * T.S, spacing = tone === 'orange' ? 0.6 : 2.2;
  const txt = String(it.text || '').toUpperCase(), w = T.measure(txt, px, 700, spacing) + 2 * padX, k = easeOut(prog(it, tr, 0.25)), x = (c.W - w) / 2, y = tone === 'orange' ? c.H * 0.45 - h / 2 : 50 * T.S;
  g.save(); g.shadowColor = 'rgba(0,0,0,0.35)'; g.shadowBlur = 10 * T.S; g.fillStyle = tone === 'orange' ? TP.orange : TP.black; g.fillRect(x + (w - w * k) / 2, y, w * k, h); g.shadowColor = 'transparent';
  if (k > 0.85) T.text(txt, x + padX, y + h / 2 + px * T.S * 0.36, { px, weight: 700, color: '#fff', track: spacing, shadow: 0 }); g.restore();
}

// a big white number counting up with its label typed beside it, then a compact orange tag top-right for the rest of the time
function statbig(c, it, tr) {
  const { g, T } = c, to = num(it.value), big = it.big_s ?? 3.6, t = tr - it._in, kd = easeOut(clamp01(t / 0.35)) * (t < big ? 1 : 1 - easeOut(clamp01((t - big) / 0.3)));
  const label = String(it.label || '').toUpperCase();
  if (kd > 0) { g.save(); g.fillStyle = `rgba(0,0,0,${0.4 * kd})`; g.fillRect(0, 0, c.W, c.H); vignette(g, c.W, c.H, 0.34 * kd); g.restore(); }
  if (t < big) {
    const k = easeOut(clamp01((t - 0.2) / (it.count_s ?? 2))), n = Math.round(to * k), size = it.size ?? 156, fw = T.measure(fmtNum(to, 0), size, 900, -2), left = c.W * 0.156, base = c.H * 0.56;
    g.save(); g.globalAlpha *= kd; T.text(fmtNum(n, 0), left + fw, base, { px: size, weight: 900, color: '#fff', track: -2, align: 'right', shadow: 0.6 });
    const typed = clamp01((t - 0.35 - (it.count_s ?? 2)) / 0.6), lx = left + fw + 30 * T.S;
    if (typed > 0) { T.text(label.slice(0, Math.ceil(label.length * typed)), lx, base - (it.sub ? 36 * T.S : 0), { px: 30, weight: 700, color: '#fff', track: 2.2, shadow: 0.6 }); if (it.sub && typed >= 1) T.text(String(it.sub).toUpperCase(), lx, base, { px: 22, weight: 800, color: TP.orange, track: 2, shadow: 0 }); }
    g.restore();
  } else {
    const txt = `${fmtNum(to, 0)}  ${label}`, w = T.measure(txt, 24, 800, 0.8) + 36 * T.S, k = easeOut(clamp01((t - big) / 0.3));
    g.save(); g.globalAlpha *= k; g.fillStyle = TP.orange; g.fillRect(c.W - 72 * T.S - w, 50 * T.S, w, 46 * T.S); T.text(txt, c.W - 72 * T.S - w + 18 * T.S, 50 * T.S + 23 * T.S + 24 * T.S * 0.36, { px: 24, weight: 800, color: '#fff', track: 0.8, shadow: 0 }); g.restore();
  }
}

// lower third without a bar: a small orange kicker tag, the title heavy white with a soft shadow, a line of small caps under it
function lowerkick(c, it, tr) {
  const { g, T } = c, k = easeOut(prog(it, tr, 0.4)); let px = it.size ?? 56; const title = String(it.title || ''); while (px > 34 && T.measure(title, px, 800, 0.5) > 1400 * T.S) px -= 2;
  const subY = c.H - 92 * T.S, titleY = subY - (it.sub ? 40 * T.S : 0), kickY = titleY - px * T.S - 14 * T.S, left = 72 * T.S;
  g.save(); g.globalAlpha *= k; g.translate((1 - k) * -24 * T.S, 0);
  if (it.kicker) { const kw = T.measure(String(it.kicker).toUpperCase(), 20, 800, 1.5) + 28 * T.S; g.fillStyle = TP.orange; g.fillRect(left, kickY - 28 * T.S, kw, 36 * T.S); T.text(String(it.kicker).toUpperCase(), left + 14 * T.S, kickY - 10 * T.S + 20 * 0.36 * T.S, { px: 20, weight: 800, color: '#fff', track: 1.5, shadow: 0 }); }
  T.text(title, left, titleY, { px, weight: 800, color: '#fff', track: 0.5, shadow: 0.6 }); if (it.sub) T.text(String(it.sub).toUpperCase(), left, subY, { px: 22, weight: 600, color: 'rgba(255,255,255,0.9)', track: 1.6, shadow: 0.4 });
  g.restore();
}

// the frame dims with a soft vignette while a card is up
function dip(c, it, tr) { const { g } = c, k = easeInOut(prog(it, tr, 0.4)); g.save(); g.fillStyle = `rgba(0,0,0,${0.4 * k})`; g.fillRect(0, 0, c.W, c.H); vignette(g, c.W, c.H, 0.34 * k); g.restore(); }

// a number counting up in a corner panel: label, big value, a small line
function countercard(c, it, tr) {
  const { g, T } = c, a = it.anchor || 'tr', k = easeOut(prog(it, tr, 0.35)), kc = easeOut(clamp01((tr - it._in - 0.35) / (it.count_s ?? 2))), label = String(it.label || '').toUpperCase(), val = num(it.value);
  const w = Math.max(300 * T.S, T.measure(label, 22, 800, 0.8) + 52 * T.S, T.measure(fmtNum(val, 0), 92, 800, -1) + 52 * T.S, it.sub ? T.measure(String(it.sub).toUpperCase(), 16, 700, 0.8) + 52 * T.S : 0), h = 168 * T.S;
  const x = a.includes('l') ? 44 * T.S : c.W - 63 * T.S - w, y = a.includes('b') ? c.H - 120 * T.S - h : 52 * T.S;
  g.save(); g.globalAlpha *= clamp01(k * 2); g.translate(0, -(1 - k) * 16 * T.S); T.panel(x, y, w, h, { r: 16 }); g.fillStyle = TP.yellow; g.fillRect(x, y + 14 * T.S, 6 * T.S, h - 28 * T.S);
  T.text(label, x + 26 * T.S, y + 38 * T.S, { px: 22, weight: 800, color: '#fff', track: 0.8, shadow: 0 }); T.text(fmtNum(Math.round(val * kc), 0), x + 26 * T.S, y + 38 * T.S + 92 * T.S * 0.95, { px: 92, weight: 800, color: '#fff', track: -1, shadow: 0 });
  if (it.sub) T.text(String(it.sub).toUpperCase(), x + 26 * T.S, y + h - 18 * T.S, { px: 16, weight: 700, color: TP.yellow, track: 0.8, shadow: 0 }); g.restore();
}

// a record card at the side: a title, then rows (LABEL / BIG VALUE / small date), sliding in one after another, a source line at the foot
function recordcard(c, it, tr) {
  const { g, T } = c, rs = rows(it.rows).slice(0, 4); if (!rs.length) return; const w = 560 * T.S, h = (86 + rs.length * 108 + 50) * T.S, x = it.anchor === 'r' ? c.W - 63 * T.S - w : 44 * T.S, y = Math.max(160 * T.S, (c.H - h) / 2), k0 = easeOut(prog(it, tr, 0.3));
  g.save(); g.globalAlpha *= k0; T.panel(x, y, w, h, { r: 18 }); g.fillStyle = TP.red; g.fillRect(x, y + 18 * T.S, 6 * T.S, 50 * T.S);
  T.text(String(it.title || '').toUpperCase(), x + 30 * T.S, y + 43 * T.S + 30 * 0.36 * T.S, { px: 30, weight: 800, color: '#fff', track: 0.6, shadow: 0 });
  rs.forEach((r, i) => { const k = easeOut(clamp01((tr - it._in - 0.3 - i * 0.35) / 0.35)); if (k <= 0) return; const yy = y + (86 + i * 108) * T.S; g.save(); g.globalAlpha *= k; g.translate((1 - k) * -18 * T.S, 0);
    g.fillStyle = 'rgba(255,255,255,0.12)'; g.fillRect(x + 30 * T.S, yy, w - 60 * T.S, 2 * T.S);
    T.text(String(r.label || '').toUpperCase(), x + 30 * T.S, yy + 30 * T.S, { px: 17, weight: 800, color: TP.yellow, track: 1.2, shadow: 0 }); T.text(String(r.text ?? r.value ?? ''), x + 30 * T.S, yy + 30 * T.S + 44 * T.S, { px: 44, weight: 800, color: '#fff', track: -0.5, shadow: 0 });
    if (r.sub) T.text(String(r.sub).toUpperCase(), x + w - 30 * T.S, yy + 30 * T.S, { px: 17, weight: 700, color: TP.blue, track: 0.6, align: 'right', shadow: 0 }); g.restore(); });
  if (it.foot) T.text(String(it.foot).toUpperCase(), x + 30 * T.S, y + h - 20 * T.S, { px: 14, weight: 700, color: TP.blue, track: 0.8, shadow: 0 }); g.restore();
}

// a record badge: a coloured stamp with the headline, the place, the new value and date, then the old record it beat
function badge(c, it, tr) {
  const { g, T } = c, w = 640 * T.S, h = 380 * T.S, x = it.anchor === 'l' ? 44 * T.S : c.W - 63 * T.S - w, y = (c.H - h) / 2, k = clamp01((tr - it._in) / 0.45), pop = 1 + 0.25 * (1 - easeOut(k)), color = col(it.color || 'red');
  g.save(); g.globalAlpha *= clamp01(k * 3); T.panel(x, y, w, h, { r: 20 });
  g.save(); g.translate(x + w / 2, y + 58 * T.S); g.scale(pop, pop); const hw = Math.min(w - 40 * T.S, T.measure(String(it.headline || '').toUpperCase(), 30, 800, 0.8) + 48 * T.S); g.fillStyle = color; g.beginPath(); g.roundRect(-hw / 2, -32 * T.S, hw, 64 * T.S, 12 * T.S); g.fill();
  T.text(String(it.headline || '').toUpperCase(), 0, 11 * T.S, { px: 30, weight: 800, color: '#fff', track: 0.8, align: 'center', shadow: 0 }); g.restore();
  T.text(String(it.place || '').toUpperCase(), x + w / 2, y + 128 * T.S, { px: 22, weight: 800, color: TP.yellow, track: 1.2, align: 'center', shadow: 0 }); T.text(String(it.value || ''), x + w / 2, y + 214 * T.S, { px: 84, weight: 800, color: '#fff', track: -1, align: 'center', shadow: 0 });
  T.text(String(it.date || '').toUpperCase(), x + w / 2, y + 250 * T.S, { px: 22, weight: 700, color: '#fff', track: 0.8, align: 'center', shadow: 0 });
  const k2 = easeOut(clamp01((tr - it._in - 0.7) / 0.4)); if (k2 > 0 && it.prev_value) { g.save(); g.globalAlpha *= k2; g.fillStyle = 'rgba(255,255,255,0.14)'; g.fillRect(x + 30 * T.S, y + 274 * T.S, w - 60 * T.S, 2 * T.S);
    T.text(`${String(it.prev_label || 'PREVIOUS RECORD').toUpperCase()}: ${it.prev_value}${it.prev_date ? ' · ' + String(it.prev_date).toUpperCase() : ''}`, x + w / 2, y + 310 * T.S, { px: 20, weight: 700, color: TP.blue, track: 0.5, align: 'center', shadow: 0 }); g.restore(); }
  g.restore();
}

// the big label of a before / after pair that switches at `switch_s`, a small source line under it
function beforeafter(c, it, tr) {
  const { g, T } = c, fr = rows(it.rows).slice(0, 2); if (fr.length < 2) return; const sw = it.switch_s ?? 3, t = tr - it._in, idx = t < sw ? 0 : 1, mix = clamp01((t - sw) / 0.5), fade = mix > 0 && mix < 1 ? Math.abs(mix - 0.5) * 2 : 1, f = fr[idx];
  const label = String(f.label || '').toUpperCase(), date = String(f.text ?? '').toUpperCase(), w = Math.max(T.measure(label, 46, 800, 1.5), T.measure(date, 22, 700, 0.8)) + 56 * T.S, h = 112 * T.S, x = c.W - 63 * T.S - w, y = 48 * T.S;
  g.save(); g.globalAlpha *= easeOut(prog(it, tr, 0.4)); T.panel(x, y, w, h, { r: 14 }); g.globalAlpha *= fade; g.fillStyle = idx ? TP.yellow : TP.blue; g.fillRect(x, y, 8 * T.S, h);
  T.text(label, x + 28 * T.S, y + 56 * T.S, { px: 46, weight: 800, color: '#fff', track: 1.5, shadow: 0 }); T.text(date, x + 28 * T.S, y + 92 * T.S, { px: 22, weight: 700, color: idx ? TP.yellow : TP.blue, track: 0.8, shadow: 0 }); g.restore();
  if (it.foot) T.text(String(it.foot).toUpperCase(), x + w, y + h + 24 * T.S, { px: 14, weight: 700, color: 'rgba(255,255,255,0.85)', track: 0.5, align: 'right', shadow: 0 });
}

// a value at a place on the map: a ring dot and a chip (value counting up, label, small line), an optional tag above it
function valuechip(c, it, tr) {
  const { g, T } = c, [x, y] = pos(c, it, tr, [0.5, 0.5]), pop = easeOut(prog(it, tr, 0.22)), k = clamp01((tr - it._in - 0.15) / 0.9), accent = col(it.accent || 'teal'), val = String(it.value ?? '');
  const m = val.match(/^(-?)(\d+(?:\.(\d+))?)(.*)$/), shown = it.count !== false && m ? `${m[1]}${(Number(m[2]) * easeOut(k)).toFixed(m[3] ? m[3].length : 0)}${m[4]}` : val;
  const vw = T.measure(val, 40, 800, -0.4), label = String(it.label || '').toUpperCase(), lw = Math.max(T.measure(label, 20, 800, 0.6), it.sub ? T.measure(String(it.sub).toUpperCase(), 15, 700, 0.7) : 0), cw = 32 * T.S + 6 * T.S + vw + 12 * T.S + lw, ch = 70 * T.S, cx = x + 24 * T.S, cy = y - ch / 2;
  g.save(); g.globalAlpha *= clamp01(pop * 2); g.save(); g.translate(x, y); g.scale(pop, pop); g.fillStyle = theme().panel; g.strokeStyle = '#fff'; g.lineWidth = 3.5 * T.S; g.beginPath(); g.arc(0, 0, 10 * T.S, 0, Math.PI * 2); g.fill(); g.stroke(); g.fillStyle = accent; g.beginPath(); g.arc(0, 0, 4 * T.S, 0, Math.PI * 2); g.fill(); g.restore();
  T.panel(cx, cy, cw, ch, { r: 12 }); g.fillStyle = accent; g.fillRect(cx, cy, 6 * T.S, ch);
  T.text(shown, cx + 22 * T.S, cy + ch / 2 + 40 * 0.36 * T.S, { px: 40, weight: 800, color: '#fff', track: -0.4, shadow: 0 }); const lx = cx + 22 * T.S + vw + 12 * T.S;
  T.text(label, lx, cy + (it.sub ? ch / 2 - 4 * T.S : ch / 2 + 20 * 0.36 * T.S), { px: 20, weight: 800, color: '#fff', track: 0.6, shadow: 0 }); if (it.sub) T.text(String(it.sub).toUpperCase(), lx, cy + ch / 2 + 19 * T.S, { px: 15, weight: 700, color: TP.yellow, track: 0.7, shadow: 0 });
  if (it.tag) { const tw = T.measure(String(it.tag).toUpperCase(), 14, 800, 0.8) + 18 * T.S; g.fillStyle = TP.yellow; g.fillRect(cx, cy - 28 * T.S, tw, 24 * T.S); T.text(String(it.tag).toUpperCase(), cx + 9 * T.S, cy - 11 * T.S, { px: 14, weight: 800, color: '#0A0A0A', track: 0.8, shadow: 0 }); }
  g.restore();
}

// a scale legend: a gradient bar through colours with end labels and a title (a rain scale, a temperature scale, a share scale)
function scalebar(c, it, tr) {
  const { g, T } = c, [x, y] = pos(c, it, tr, [0.6, 0.86]), w = (it.w ?? 0.3) * c.W, h = 118 * T.S, k = easeOut(prog(it, tr, 0.4)), stops = list(it.colors).length ? list(it.colors) : ['blue', 'teal', 'yellow', 'red'], labels = list(it.labels);
  g.save(); g.globalAlpha *= k; T.panel(x, y, w, h, { r: 14 }); T.text(String(it.title || '').toUpperCase(), x + 20 * T.S, y + 34 * T.S, { px: 16, weight: 800, color: '#fff', track: 1.4, shadow: 0 });
  const gr = g.createLinearGradient(x + 20 * T.S, 0, x + w - 20 * T.S, 0); stops.forEach((s, i) => gr.addColorStop(i / Math.max(1, stops.length - 1), col(s))); g.fillStyle = gr; g.fillRect(x + 20 * T.S, y + 50 * T.S, w - 40 * T.S, 16 * T.S);
  labels.forEach((l, i) => T.text(String(l), x + 20 * T.S + ((w - 40 * T.S) * i) / Math.max(1, labels.length - 1), y + 96 * T.S, { px: 15, weight: 700, color: TP.blue, align: i === 0 ? 'left' : i === labels.length - 1 ? 'right' : 'center', shadow: 0 })); g.restore();
}

export const TP_PRIMS = { kwtitle, chaptercard, ctxtag, statbig, lowerkick, dip, countercard, recordcard, badge, beforeafter, valuechip, scalebar };
