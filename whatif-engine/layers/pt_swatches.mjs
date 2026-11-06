// PT_SWATCHES: colour options as a row of tall colour cards on the paper (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 3).
// Each card pops in on the word that names it ("at", s after start, from product_trailer/wordcue.py), the name inside in an ink that reads on its
// colour, an optional small tag above it ("Online Exclusive"). "q_at": a "?" drops onto every card (the shades are not known yet). A card's "ref"
// {label, name, color, at}: an older model's colour slides in over that card from the right, a flat phone back on its colour with
// "Galaxy S26 Ultra | Sky Blue", and slides away again after a few seconds (or when the next one comes).
//   { "type": "pt_swatches", "title": "S27 Ultra colour options", "start": 0, "end": 12, "q_at": 6.2,
//     "cards": [{ "name": "Black", "color": "#2b2b2e", "at": 0.4 }, { "name": "Blue", "color": "#3f6fb5", "ref": { "label": "Galaxy S26 Ultra", "name": "Sky Blue", "color": "#8fc3ea", "at": 8 } },
//               { "name": "Violet", "color": "#b98ce0", "tag": "Online Exclusive" }] }
import { tm, clamp01, overshoot, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont, cueAge } from './pt_feature.mjs';

const REF_S = 3.6;                                   // an older model's card stays this long
const lum = (hex) => { const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '')); if (!m) return 0.5; const n = parseInt(m[1], 16); return (0.299 * (n >> 16 & 255) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255; };
const ink = (hex) => (lum(hex) > 0.62 ? '#1d2127' : '#FFFFFF');

export default {
  type: 'pt_swatches',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.cards) || !def.cards.length) throw new Error('pt_swatches: "cards" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, cards = d.cards.slice(0, 6), n = cards.length;
    const m = ptMotion(d, f.t, S, { inDur: 0.3, outDur: 0.3, rise: 0 });
    if (m.k <= 0.002) return;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    const subs = ((f.spec && f.spec.layers) || []).some((L) => L && L.type === 'pt_subtitle');
    const cw = Math.min(W * 0.115, (W * 0.86) / (n + (n - 1) * 0.18)), ch = Math.min(cw * 2.05, H * (subs ? 0.5 : 0.56)), gap = cw * 0.18;
    const x0 = W / 2 - (cw * n + gap * (n - 1)) / 2, y0 = H * 0.53 - ch / 2 - (subs ? H * 0.04 : 0);
    if (d.title) {                                     // "S27 Ultra" bold + "colour options" regular, centred above the row
      const tt = String(d.title), sp = tt.search(/\s(colou?r|options)/i), bold = sp > 0 ? tt.slice(0, sp) : tt, rest = sp > 0 ? tt.slice(sp) : '';
      const fb = ptFont(S, 40, 800, 'sans'), fr = ptFont(S, 40, 500, 'sans'), wb = T.measure(bold, fb), wr = T.measure(rest, fr), tx = W / 2 - (wb + wr) / 2, ty = y0 - 46 * S;
      T.text(bold, tx, ty, { font: fb, color: '#1d2127', shadow: 0 }); if (rest) T.text(rest, tx + wb, ty, { font: fr, color: '#1d2127', shadow: 0 });
    }
    const qk = Number.isFinite(d.q_at) ? m.age - d.q_at : -1;
    const refs = cards.map((c, i) => (c.ref && Number.isFinite(c.ref.at) ? { i, at: c.ref.at } : null)).filter(Boolean).sort((a, b) => a.at - b.at);
    cards.forEach((c, i) => {
      const age = cueAge(m.age, c, i, 0.14, 0.15), a = clamp01(age / 0.22);
      if (a <= 0) return;
      const x = x0 + i * (cw + gap), kin = overshoot(age / 0.42), sc = 0.84 + 0.16 * Math.min(1.06, kin), col = c.color || '#2b2b2e';
      g.save(); g.globalAlpha *= a; g.translate(x + cw / 2, y0 + ch / 2); g.scale(sc, sc); g.translate(-(x + cw / 2), -(y0 + ch / 2));
      g.shadowColor = 'rgba(0,0,0,0.20)'; g.shadowBlur = 22 * S; g.shadowOffsetY = 8 * S; g.fillStyle = col; g.beginPath(); g.roundRect(x, y0, cw, ch, cw * 0.1); g.fill();
      g.shadowColor = 'transparent'; g.strokeStyle = 'rgba(0,0,0,0.08)'; g.lineWidth = 2 * S; g.stroke();
      const nf = (() => { let px = 30; while (px > 16 && T.measure(String(c.name), ptFont(S, px, 600, 'sans')) > cw * 0.86) px -= 2; return ptFont(S, px, 600, 'sans'); })();
      T.text(String(c.name), x + cw / 2, y0 + ch * 0.5, { font: nf, align: 'center', color: ink(col), shadow: 0 });
      if (c.tag) T.text(String(c.tag), x + cw / 2, y0 + ch * 0.38, { font: ptFont(S, 17, 600, 'sans'), align: 'center', color: ink(col), shadow: 0, alpha: 0.85 });
      if (qk > 0) {                                     // the "?" drops in, card by card
        const kq = clamp01((qk - 0.08 * i) / 0.35), drop = (1 - quartOut(kq)) * -40 * S;
        if (kq > 0) T.text('?', x + cw / 2, y0 + ch * 0.68 + drop, { font: ptFont(S, 64, 800, 'sans'), align: 'center', color: ink(col), shadow: 0, alpha: kq });
      }
      g.restore();
    });
    refs.forEach((r, j) => {                           // an older model's colour over its match, sliding in from the right edge and out again
      const c = cards[r.i], ref = c.ref, until = Math.min(r.at + REF_S, refs[j + 1] ? refs[j + 1].at : Infinity), age = m.age - r.at;
      if (age <= 0 || m.age > until + 0.4) return;
      const kin = quartOut(age / 0.45), kout = clamp01((until + 0.4 - m.age) / 0.4), k = Math.min(kin, kout);
      const tx = x0 + r.i * (cw + gap), pw = Math.min(W - tx - W * 0.03, cw * 3.1), px = tx + (1 - k) * (W - tx), col = ref.color || '#8fc3ea';
      g.save(); g.shadowColor = 'rgba(0,0,0,0.25)'; g.shadowBlur = 26 * S; g.fillStyle = col; g.beginPath(); g.roundRect(px, y0 - ch * 0.04, pw, ch * 1.08, cw * 0.1); g.fill(); g.restore();
      const bw = cw * 0.62, bh = ch * 0.78, bx = px + cw * 0.18, by = y0 + ch * 0.11;   // a flat phone back in a lighter tint of the colour
      g.save(); g.fillStyle = 'rgba(255,255,255,0.35)'; g.beginPath(); g.roundRect(bx, by, bw, bh, bw * 0.14); g.fill();
      g.fillStyle = 'rgba(0,0,0,0.75)'; for (let l = 0; l < 3; l++) { g.beginPath(); g.arc(bx + bw * 0.28, by + bw * 0.25 + l * bw * 0.27, bw * 0.1, 0, 7); g.fill(); } g.restore();
      const lx = bx + bw + cw * 0.18, ic = ink(col);
      T.text(String(ref.label || ''), lx, y0 + ch * 0.42, { font: ptFont(S, 22, 500, 'sans'), color: ic, shadow: 0, alpha: k });
      T.text(String(ref.name || ''), lx, y0 + ch * 0.42 + 40 * S, { font: ptFont(S, 34, 800, 'sans'), color: ic, shadow: 0, alpha: k });
    });
    g.restore();
  },
};
