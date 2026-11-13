// The explainer graphics of a Review film: drawn from what the narration says, on the dark plate (product_trailer/narration_gfx.py writes them).
// Every item lands on the word that names it (`at`, s after the layer's start, from product_trailer/wordcue.py), else a stagger. Items marked
// `done` were already said in an earlier sentence: they are on screen from the start, so one canvas keeps building across sentences.
//
//   pt_list      { title, mode: "check" | "risk" | "chips", items: [{ text, at?, done? }] }        a checklist, a list of risks, a row of names
//   pt_steps     { title, n, total, text, target, app, steps: [short labels] }                       step n of a how-to, tapped on a drawn phone screen
//   pt_breakdown { total, label, parts: [{ value, label }], inner?: { of, value, label } }            a total split into its parts (179 = 155 + 24)
//   pt_ledger    { cols: [{ title, tone: "green"|"amber"|"red", items: [{ text, at?, done? }] }], active }   known / reported / unknown
import { C, tm, clamp01, quartOut, overshoot, drift, fmt } from './tm_theme.mjs';
import { ptMotion, ptFont, ptFit, cueAge } from './pt_feature.mjs';

const TONE = { green: '#2EE6A8', amber: '#FFB703', red: '#FF4B5C', cyan: '#3AC8FF', violet: '#9B8CFF' };
const tone = (t) => TONE[t] || t || TONE.cyan;

function begin(f, d, S) {
  const m = ptMotion(d, f.t, S, { inDur: 0.35, outDur: 0.3, rise: 0 });
  if (m.k <= 0.002) return null;
  f.g.save(); f.g.globalAlpha = (f.alpha ?? 1) * m.k; drift(f.g, f, d, 0.03);
  return m;
}
const itemAge = (m, it, i, step = 0.55, lead = 0.25) => (it && it.done ? 99 : cueAge(m.age, it, i, step, lead));

function title(T, g, text, x, y, S, k = 1, accent = TONE.cyan) {
  if (!text) return;
  T.text(String(text).toUpperCase(), x, y, { font: T.sans(26, 700), track: 5, color: '#AEB8C6', shadow: 0, alpha: k });
  g.save(); g.globalAlpha *= k; g.fillStyle = accent; g.fillRect(x, y + 14 * S, 64 * S * k, 4 * S); g.restore();
}

// ---- icons drawn with paths (no font glyphs) ----
function tick(g, x, y, s, k, col) {
  g.save(); g.strokeStyle = col; g.lineWidth = s * 0.16; g.lineCap = 'round'; g.lineJoin = 'round';
  const p = [[x - s * 0.32, y + s * 0.02], [x - s * 0.08, y + s * 0.26], [x + s * 0.36, y - s * 0.24]];
  const L1 = Math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]), L2 = Math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1]), len = (L1 + L2) * clamp01(k);
  g.beginPath(); g.moveTo(...p[0]);
  if (len <= L1) g.lineTo(p[0][0] + (p[1][0] - p[0][0]) * len / L1, p[0][1] + (p[1][1] - p[0][1]) * len / L1);
  else { g.lineTo(...p[1]); const r = (len - L1) / L2; g.lineTo(p[1][0] + (p[2][0] - p[1][0]) * r, p[1][1] + (p[2][1] - p[1][1]) * r); }
  g.stroke(); g.restore();
}
function warnIcon(g, x, y, s, col) {
  g.save(); g.fillStyle = col; g.beginPath(); g.moveTo(x, y - s * 0.42); g.lineTo(x + s * 0.46, y + s * 0.36); g.lineTo(x - s * 0.46, y + s * 0.36); g.closePath(); g.fill();
  g.fillStyle = '#10131a'; g.fillRect(x - s * 0.05, y - s * 0.16, s * 0.1, s * 0.3); g.beginPath(); g.arc(x, y + s * 0.24, s * 0.06, 0, Math.PI * 2); g.fill(); g.restore();
}

// ---------------------------------------------------------------------------------------------------------------------------------
const pt_list = {
  type: 'pt_list',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.items) || !def.items.length) throw new Error('pt_list: "items" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = begin(f, d, S);
    if (!m) return;
    const mode = d.mode || 'check', items = d.items.slice(0, mode === 'chips' ? 10 : 7), acc = mode === 'risk' ? TONE.amber : mode === 'chips' ? TONE.cyan : TONE.green;
    const x0 = W * 0.12;
    title(T, g, d.title, x0, H * 0.2, S, quartOut(m.age / 0.5), acc);
    if (mode === 'chips') {                                    // names as pills flowing in rows, each with a round badge of its initials
      let x = x0, y = H * 0.36; const ph = 92 * S, gap = 26 * S;
      items.forEach((it, i) => {
        const age = itemAge(m, it, i, 0.35), k = overshoot(age / 0.45);
        const txt = String(it.text), px = 40, tw = T.measure(txt, T.sans(px, 700)), w = tw + ph + 40 * S;
        if (x + w > W * 0.9) { x = x0; y += ph + gap; }
        if (age > 0) {
          g.save(); g.globalAlpha *= clamp01(age / 0.25); g.translate(x + w / 2, y + ph / 2); g.scale(0.6 + 0.4 * k, 0.6 + 0.4 * k); g.translate(-(x + w / 2), -(y + ph / 2));
          g.fillStyle = 'rgba(20,26,36,0.92)'; g.strokeStyle = 'rgba(58,200,255,0.45)'; g.lineWidth = 2 * S; g.beginPath(); g.roundRect(x, y, w, ph, ph / 2); g.fill(); g.stroke();
          g.fillStyle = acc; g.beginPath(); g.arc(x + ph / 2, y + ph / 2, ph * 0.34, 0, Math.PI * 2); g.fill();
          const ini = txt.split(/\s+/).map((s) => s[0] || '').join('').slice(0, 2).toUpperCase();
          T.text(ini, x + ph / 2, y + ph / 2 + 11 * S, { font: T.sans(30, 800), color: '#08121a', align: 'center', shadow: 0 });
          T.text(txt, x + ph + 8 * S, y + ph / 2 + 14 * S, { font: T.sans(px, 700), color: C.white, shadow: 0.3 });
          g.restore();
        }
        x += w + gap;
      });
      g.restore(); return;
    }
    const rowH = Math.min(104 * S, (H * 0.62) / items.length), y0 = H * 0.3;
    items.forEach((it, i) => {
      const age = itemAge(m, it, i), k = quartOut(age / 0.5);
      if (age <= 0) return;
      const y = y0 + i * rowH, slide = (1 - k) * 60 * S, box = rowH * 0.62;
      g.save(); g.globalAlpha *= k; g.translate(slide, 0);
      g.fillStyle = 'rgba(20,26,36,0.88)'; g.beginPath(); g.roundRect(x0, y, W * 0.66, rowH * 0.84, 16 * S); g.fill();
      if (mode === 'risk') warnIcon(g, x0 + rowH * 0.5, y + rowH * 0.42, box, acc);
      else {
        g.strokeStyle = acc; g.lineWidth = 3 * S; g.beginPath(); g.roundRect(x0 + rowH * 0.5 - box / 2, y + rowH * 0.42 - box / 2, box, box, 10 * S); g.stroke();
        tick(g, x0 + rowH * 0.5, y + rowH * 0.42, box * 0.8, (age - 0.25) / 0.35, acc);
      }
      const px = ptFit(T, String(it.text), 44, W * 0.66 - rowH * 1.3, 700, 'sans');
      T.text(String(it.text), x0 + rowH, y + rowH * 0.42 + px * S * 0.36, { font: ptFont(S, px, 700, 'sans'), color: C.white, shadow: 0.3 });
      g.restore();
    });
    g.restore();
  },
};

// ---------------------------------------------------------------------------------------------------------------------------------
function phoneScreen(g, T, S, x, y, w, h, d, age) {
  // the body
  g.save(); g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = 40 * S;
  g.fillStyle = '#0b0d12'; g.beginPath(); g.roundRect(x, y, w, h, w * 0.12); g.fill(); g.restore();
  g.strokeStyle = '#5a6476'; g.lineWidth = 4 * S; g.beginPath(); g.roundRect(x, y, w, h, w * 0.12); g.stroke();
  const sx = x + w * 0.045, sy = y + w * 0.045, sw = w * 0.91, sh = h - w * 0.09;
  g.save(); g.beginPath(); g.roundRect(sx, sy, sw, sh, w * 0.09); g.clip();
  const bg = g.createLinearGradient(sx, sy, sx, sy + sh); bg.addColorStop(0, '#151b26'); bg.addColorStop(1, '#0d1118'); g.fillStyle = bg; g.fillRect(sx, sy, sw, sh);
  g.fillStyle = '#000'; g.beginPath(); g.arc(sx + sw / 2, sy + 26 * S, 9 * S, 0, Math.PI * 2); g.fill();           // punch-hole camera
  T.text(String(d.app || 'Settings'), sx + 28 * S, sy + 110 * S, { font: T.sans(38, 800), color: C.white, shadow: 0 });
  const rows = (d.rows && d.rows.length ? d.rows : ['Notifications', 'Display', 'Battery', d.target || 'Software update', 'About phone']).slice(0, 6);
  const ti = Math.max(0, rows.findIndex((r) => r === d.target));
  const rh = 84 * S, r0 = sy + 150 * S;
  rows.forEach((r, i) => {
    const ry = r0 + i * (rh + 12 * S), hit = i === ti, pulse = hit ? clamp01((age - 0.9) / 0.4) : 0;
    g.fillStyle = hit ? `rgba(58,200,255,${0.12 + 0.2 * pulse})` : 'rgba(255,255,255,0.05)';
    g.beginPath(); g.roundRect(sx + 18 * S, ry, sw - 36 * S, rh, 20 * S); g.fill();
    if (hit) { g.strokeStyle = TONE.cyan; g.lineWidth = 3 * S * pulse; g.stroke(); }
    g.fillStyle = hit ? TONE.cyan : '#3a4354'; g.beginPath(); g.arc(sx + 58 * S, ry + rh / 2, 18 * S, 0, Math.PI * 2); g.fill();
    const px = ptFit(T, String(r), 28, sw - 150 * S, hit ? 700 : 500, 'sans');
    T.text(String(r), sx + 92 * S, ry + rh / 2 + 10 * S, { font: ptFont(S, px, hit ? 700 : 500, 'sans'), color: hit ? C.white : '#B9C2CF', shadow: 0 });
    if (hit) {                                                   // the finger's tap: a ripple on the row
      const tk = clamp01((age - 1.0) / 0.7);
      if (tk > 0 && tk < 1) { g.strokeStyle = `rgba(255,255,255,${0.7 * (1 - tk)})`; g.lineWidth = 4 * S; g.beginPath(); g.arc(sx + sw * 0.7, ry + rh / 2, (12 + 70 * tk) * S, 0, Math.PI * 2); g.stroke(); }
      const fk = clamp01((age - 0.4) / 0.6), fx = sx + sw * 0.7, fy = ry + rh / 2 + (1 - quartOut(fk)) * 160 * S;
      if (fk > 0) { g.save(); g.globalAlpha *= Math.min(fk * 2, clamp01((2.6 - age) / 0.5) + 0.25); g.fillStyle = 'rgba(255,255,255,0.85)'; g.beginPath(); g.arc(fx, fy, 22 * S, 0, Math.PI * 2); g.fill(); g.restore(); }
    }
  });
  g.restore();
}

const pt_steps = {
  type: 'pt_steps',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('pt_steps: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = begin(f, d, S);
    if (!m) return;
    const n = Math.max(1, d.n | 0), total = Math.max(n, d.total | 0), k = quartOut(m.age / 0.6);
    const lx = W * 0.09;
    title(T, g, d.title || 'How to', lx, H * 0.2, S, k);
    T.text(String(n).padStart(2, '0'), lx, H * 0.47, { font: T.display(220), color: TONE.cyan, shadow: 0.3, alpha: k, glow: 'rgba(58,200,255,0.5)' });
    T.text(`STEP ${n} OF ${total}`, lx + 6 * S, H * 0.55, { font: T.mono(26, 600), color: '#8E99A8', alpha: k, shadow: 0 });
    const px = ptFit(T, String(d.text), 54, W * 0.46, 800, 'sans');
    T.text(String(d.text), lx, H * 0.64, { font: ptFont(S, px, 800, 'sans'), color: C.white, alpha: clamp01((m.age - 0.2) / 0.4), shadow: 0.3 });
    for (let i = 0; i < total; i++) {                            // progress: one bar per step, the done ones filled
      const bx = lx + i * 92 * S, fill = i < n - 1 ? 1 : i === n - 1 ? clamp01((m.age - 0.3) / 0.8) : 0;
      g.fillStyle = 'rgba(255,255,255,0.14)'; g.fillRect(bx, H * 0.72, 76 * S, 8 * S);
      g.fillStyle = TONE.cyan; g.fillRect(bx, H * 0.72, 76 * S * fill, 8 * S);
    }
    const ph = H * 0.8, pw = ph * 0.48, ppx = W * 0.64, ppy = H * 0.1 + (1 - k) * 80 * S;
    phoneScreen(g, T, S, ppx, ppy, pw, ph, d, m.age);
    g.restore();
  },
};

// ---------------------------------------------------------------------------------------------------------------------------------
const pt_breakdown = {
  type: 'pt_breakdown',
  space: 'screen',
  create: (def) => { if (!(Number(def.total) > 0) || !Array.isArray(def.parts) || !def.parts.length) throw new Error('pt_breakdown: "total" and "parts" are required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = begin(f, d, S);
    if (!m) return;
    const total = Number(d.total), cnt = quartOut(m.age / 1.2), x0 = W * 0.1, bw = W * 0.8;
    title(T, g, d.title, x0, H * 0.18, S, quartOut(m.age / 0.5), TONE.red);
    T.text(fmt(Math.round(total * cnt)), x0, H * 0.43, { font: T.display(190), color: C.white, shadow: 0.35 });
    T.text(String(d.label || '').toUpperCase(), x0 + 8 * S, H * 0.5, { font: T.sans(30, 700), track: 4, color: '#AEB8C6', shadow: 0 });
    const by = H * 0.6, bh = 74 * S, cols = [TONE.cyan, TONE.violet, TONE.amber, TONE.green];
    g.fillStyle = 'rgba(255,255,255,0.08)'; g.beginPath(); g.roundRect(x0, by, bw, bh, 14 * S); g.fill();
    let x = x0;
    d.parts.slice(0, 4).forEach((p, i) => {
      const age = itemAge(m, p, i, 0.8, 1.0), k = quartOut(age / 0.7), w = bw * Number(p.value) / total;
      if (age > 0) {
        g.fillStyle = cols[i % 4]; g.globalAlpha *= 1; g.beginPath(); g.roundRect(x + 3 * S, by + 3 * S, Math.max(0, w * k - 6 * S), bh - 6 * S, 11 * S); g.fill();
        T.text(fmt(Number(p.value)), x + 6 * S, by + bh + 64 * S, { font: T.display(56), color: cols[i % 4], alpha: k, shadow: 0 });
        T.text(String(p.label || ''), x + 6 * S, by + bh + 104 * S, { font: T.sans(28, 600), color: '#D5DCE6', alpha: k, shadow: 0 });
      }
      if (d.inner && d.inner.of === i && age > 0) {               // a part of a part (20 critical of the 155): a bracket over that bar
        const ia = itemAge(m, d.inner, 9, 0, 0), ik = quartOut((Number.isFinite(d.inner.at) ? ia : age - 1.0) / 0.6), iw = w * Number(d.inner.value) / Number(p.value);
        if (ik > 0) {
          g.save(); g.globalAlpha *= ik; g.fillStyle = 'rgba(255,75,92,0.9)'; g.beginPath(); g.roundRect(x + 3 * S, by + 3 * S, Math.max(0, iw * ik - 6 * S), bh - 6 * S, 11 * S); g.fill();
          g.strokeStyle = TONE.red; g.lineWidth = 3 * S; g.beginPath(); g.moveTo(x + 3 * S, by - 18 * S); g.lineTo(x + 3 * S, by - 34 * S); g.lineTo(x + iw, by - 34 * S); g.lineTo(x + iw, by - 18 * S); g.stroke();
          T.text(`${fmt(Number(d.inner.value))} ${String(d.inner.label || '').toUpperCase()}`, x + 3 * S, by - 50 * S, { font: T.sans(30, 800), track: 3, color: TONE.red, shadow: 0 });
          g.restore();
        }
      }
      x += w;
    });
    g.restore();
  },
};

// ---------------------------------------------------------------------------------------------------------------------------------
const pt_ledger = {
  type: 'pt_ledger',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.cols) || !def.cols.length) throw new Error('pt_ledger: "cols" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, m = begin(f, d, S);
    if (!m) return;
    const cols = d.cols.slice(0, 3), n = cols.length, gap = 34 * S, cw = (W * 0.86 - gap * (n - 1)) / n, x0 = W * 0.07, y0 = H * 0.16;
    cols.forEach((c, ci) => {
      const x = x0 + ci * (cw + gap), act = d.active == null || d.active === ci, col = tone(c.tone), a = act ? 1 : 0.42;
      const ck = c.done ? 1 : quartOut((m.age - (act ? 0 : 0.1 * ci)) / 0.5);
      g.save(); g.globalAlpha *= a * ck;
      g.fillStyle = 'rgba(16,21,30,0.9)'; g.beginPath(); g.roundRect(x, y0, cw, H * 0.68, 22 * S); g.fill();
      if (act) { g.strokeStyle = col; g.lineWidth = 3 * S; g.stroke(); }
      g.fillStyle = col; g.fillRect(x + 28 * S, y0 + 30 * S, 10 * S, 46 * S);
      T.text(String(c.title || '').toUpperCase(), x + 54 * S, y0 + 68 * S, { font: T.sans(38, 800), track: 3, color: col, shadow: 0 });
      (c.items || []).slice(0, 5).forEach((it, i) => {
        const age = act ? itemAge(m, it, i, 0.7, 0.4) : (c.done || it.done ? 99 : -1), k = quartOut(age / 0.5);
        if (age <= 0) return;
        const iy = y0 + 140 * S + i * 92 * S;
        g.save(); g.globalAlpha *= k; g.translate((1 - k) * 30 * S, 0);
        g.fillStyle = col; g.beginPath(); g.arc(x + 42 * S, iy - 10 * S, 8 * S, 0, Math.PI * 2); g.fill();
        const px = ptFit(T, String(it.text), 34, cw - 96 * S, 600, 'sans');
        T.text(String(it.text), x + 66 * S, iy, { font: ptFont(S, px, 600, 'sans'), color: C.white, shadow: 0 });
        g.restore();
      });
      g.restore();
    });
    g.restore();
  },
};

export { pt_list, pt_steps, pt_breakdown, pt_ledger };
export default pt_list;
