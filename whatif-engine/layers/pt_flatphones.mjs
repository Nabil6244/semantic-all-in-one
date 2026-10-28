// PT_FLATPHONES: the explainer-review staple: one to four flat phone cut-outs side by side on the paper, each with a label on the back, a giant
// figure on it ("60W", "$1315") and optionally a battery capsule that fills beside it.
//   { "type": "pt_flatphones", "start": 0, "end": 5, "title": "CHARGING SPEED",
//     "phones": [{ "label": "Galaxy S26 Ultra", "text": "60W", "color": "#5b5a86", "cams": 4, "fill": 0.95, "top": "5000mAh", "highlight": false },
//                { "label": "Galaxy S27 Ultra", "text": "60W", "color": "#2b2b2e", "cams": 3, "fill": 0.99, "top": "5700mAh" }] }
// More per phone: fill_from (the capsule counts from it), cutaway:true (the battery cell is drawn inside the body, level cell_from -> cell), side: {from,to,suffix,prefix}
// or side: {text} (a big figure to the right of the phone), cable: "60W" (a cable out of the bottom with a readout), badge: "+700mAh" (a green pill above).
// fill 0..1 grows from empty over about a second after the phone appears; "cams" is 2..4 lens circles; the phones pop in one after the other.
import { tm, clamp01, overshoot, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

const GREEN = '#1fc41f';
const shade = (hex, k) => { const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '')); if (!m) return hex; const n = parseInt(m[1], 16); const f = (v) => Math.max(0, Math.min(255, Math.round(v * k))); return `rgb(${f(n >> 16 & 255)},${f(n >> 8 & 255)},${f(n & 255)})`; };

export default {
  type: 'pt_flatphones',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.phones) || !def.phones.length) throw new Error('pt_flatphones: "phones" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, ph = d.phones.slice(0, 4), n = ph.length;
    let m = ptMotion(d, f.t, S, { inDur: 0.3, outDur: 0.25, rise: 0 });
    if (d.hold) m = { k: clamp01(((d.end ?? f.t + 1) - f.t) / 0.05), kin: 1, age: 99, rise: 0 };        // a continuation of the scene before it: already settled, no new entrance
    if (m.k <= 0.002) return;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    const zoom = 1 + Math.min(0.06, 0.008 * Math.max(0, f.t - (d.t0 ?? d.start ?? 0)));            // a slow push so a held scene is never a still
    g.translate(W / 2, H / 2); g.scale(zoom, zoom); g.translate(-W / 2, -H / 2);
    const ph_h = Math.min(H * 0.66, W * 0.78 / n * 1.9), ph_w = ph_h * 0.49, hasCap = ph.some((p) => p.fill != null), hasSide = ph.some((p) => p.side), gap = ph_w * (hasCap ? 0.9 : hasSide ? 0.5 : 0.6), capW = hasSide ? ph_w * 1.25 : hasCap ? ph_w * 0.42 : 0;
    const unit = ph_w + gap + capW * 0.9, x0 = W / 2 - (unit * n - gap) / 2, y0 = H * 0.5 - ph_h / 2 + H * 0.03;
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.11, { font: ptFont(S, 34, 700, 'sans'), track: 4, align: 'center', color: '#8A8F98', shadow: 0 });
    ph.forEach((p, i) => {
      const age = m.age - 0.12 * i, kin = overshoot(age / 0.45), x = x0 + unit * i, a = clamp01(age / 0.25);
      if (a <= 0) return;
      const bob = d.bob === false ? 0 : Math.sin(f.t * 1.3 + i) * ph_h * 0.008;
      g.save(); g.globalAlpha *= a; g.translate(0, bob); g.translate(x + ph_w / 2, y0 + ph_h / 2); const sc = 0.82 + 0.18 * Math.min(1.08, kin); g.scale(sc, sc); g.translate(-(x + ph_w / 2), -(y0 + ph_h / 2));
      const r = ph_w * 0.14, col = p.color || '#2b2b2e';
      g.shadowColor = 'rgba(0,0,0,0.22)'; g.shadowBlur = 26 * S; g.shadowOffsetY = 12 * S;
      const gr = g.createLinearGradient(x, y0, x + ph_w, y0 + ph_h); gr.addColorStop(0, shade(col, 1.25)); gr.addColorStop(1, shade(col, 0.8));
      g.fillStyle = gr; g.beginPath(); g.roundRect(x, y0, ph_w, ph_h, r); g.fill();
      g.shadowColor = 'transparent'; g.shadowBlur = 0; g.strokeStyle = 'rgba(255,255,255,0.18)'; g.lineWidth = 2 * S; g.stroke();
      const cams = Math.max(2, Math.min(4, p.cams || 3)), cr = ph_w * 0.095;      // lens circles down the top-left
      for (let c = 0; c < cams; c++) {
        const cx = x + ph_w * 0.26, cy = y0 + ph_h * 0.075 + c * cr * 2.5;
        g.fillStyle = 'rgba(0,0,0,0.65)'; g.beginPath(); g.arc(cx, cy, cr * 1.08, 0, 7); g.fill();
        g.fillStyle = '#10151d'; g.beginPath(); g.arc(cx, cy, cr * 0.72, 0, 7); g.fill();
        g.fillStyle = 'rgba(120,170,255,0.55)'; g.beginPath(); g.arc(cx - cr * 0.2, cy - cr * 0.2, cr * 0.2, 0, 7); g.fill();
      }
      if (p.cutaway) {                                                           // see-through body: the battery cell inside, filling
        g.fillStyle = 'rgba(255,255,255,0.10)'; g.beginPath(); g.roundRect(x + ph_w * 0.07, y0 + ph_h * 0.2, ph_w * 0.86, ph_h * 0.72, ph_w * 0.08); g.fill();
        const cx0 = x + ph_w * 0.14, cw = ph_w * 0.72, cy0 = y0 + ph_h * 0.26, chh = ph_h * 0.6, kk = quartOut((age - 0.25) / 1.2), c0 = p.cell_from ?? 0, c1 = p.cell ?? p.fill ?? 0.5, lv = clamp01(c0 + (c1 - c0) * kk);
        g.fillStyle = 'rgba(210,214,222,0.9)'; g.beginPath(); g.roundRect(cx0, cy0, cw, chh, ph_w * 0.05); g.fill();
        const cg = g.createLinearGradient(0, cy0 + chh, 0, cy0); cg.addColorStop(0, '#3b2bd6'); cg.addColorStop(1, '#17c7a0'); g.fillStyle = cg;
        g.beginPath(); g.roundRect(cx0, cy0 + chh * (1 - lv), cw, chh * lv, ph_w * 0.05); g.fill();
        g.fillStyle = 'rgba(255,255,255,0.35)'; g.fillRect(cx0 + cw * 0.1, cy0 + 4 * S, cw * 0.08, chh - 8 * S);
      }
      if (p.label && !p.cutaway) T.text(String(p.label), x + ph_w / 2, y0 + ph_h * 0.87, { font: ptFont(S, 22, 600, 'sans'), align: 'center', color: 'rgba(255,255,255,0.7)', shadow: 0 });
      if (p.text) { const fit = (px) => { while (px > 24 && T.measure(String(p.text), ptFont(S, px, 900)) > ph_w * 0.92) px -= 4; return px; }; const px = fit(Math.min(ph_w * 0.5 / S, 110)); T.text(String(p.text), x + ph_w / 2, y0 + ph_h * 0.58, { font: ptFont(S, px, 900), align: 'center', color: '#FFFFFF', shadow: 0.35 }); }
      g.restore();
      if (p.top) T.text(String(p.top), x + ph_w / 2, y0 - 18 * S, { font: ptFont(S, 26, 700, 'sans'), align: 'center', color: '#3a3f47', shadow: 0, alpha: a });
      if (p.fill != null) {                                                        // the battery capsule beside the phone
        const cx = x + ph_w + capW * 0.25, ch = ph_h * 0.34, cy = y0 + ph_h * 0.5 - ch / 2, k = quartOut((age - 0.3) / 1.2), lvl = clamp01((p.fill_from ?? 0) + (clamp01(p.fill) - (p.fill_from ?? 0)) * k);
        g.save(); g.beginPath(); g.roundRect(cx, cy, capW, ch, capW / 2); g.clip();
        g.fillStyle = 'rgba(0,0,0,0.07)'; g.fillRect(cx, cy, capW, ch);
        g.fillStyle = lvl > 0.2 ? GREEN : '#e8a21a'; g.fillRect(cx, cy + ch * (1 - lvl), capW, ch * lvl);
        g.fillStyle = 'rgba(255,255,255,0.28)'; g.fillRect(cx + capW * 0.14, cy, capW * 0.14, ch); g.restore();
        g.strokeStyle = 'rgba(0,0,0,0.5)'; g.lineWidth = 3 * S; g.beginPath(); g.roundRect(cx, cy, capW, ch, capW / 2); g.stroke();
        T.text('%' + Math.round(lvl * 100), cx + capW / 2, cy + ch / 2 + 11 * S, { font: ptFont(S, 32, 800), align: 'center', color: '#FFFFFF', shadow: 0.6 });
      }
      if (p.side) {
        const sd = p.side, kk = quartOut((age - 0.25) / 1.2), v = sd.text != null ? sd.text : `${sd.prefix ?? ''}${Math.round((sd.from ?? 0) + ((sd.to ?? 0) - (sd.from ?? 0)) * kk)}${sd.suffix ?? ''}`;
        T.text(v, x + ph_w + gap * 0.3, y0 + ph_h * 0.56, { font: ptFont(S, sd.size || 96, 900), color: sd.color || '#1d2127', shadow: 0, alpha: a });
      }
      if (p.cable) {
        const cxp = x + ph_w / 2, yb = y0 + ph_h;
        g.save(); g.globalAlpha *= a; g.strokeStyle = '#1b1d21'; g.lineWidth = 7 * S; g.lineCap = 'round'; g.beginPath(); g.moveTo(cxp, yb); g.lineTo(cxp, Math.min(H * 0.99, yb + H * 0.12)); g.stroke();
        g.fillStyle = '#1b1d21'; g.beginPath(); g.roundRect(cxp - 12 * S, yb - 4 * S, 24 * S, 22 * S, 5 * S); g.fill(); g.restore();
        if (typeof p.cable === 'string' && p.cable) T.text(p.cable, cxp, yb + 52 * S, { font: ptFont(S, 28, 800, 'sans'), align: 'center', color: '#1d2127', shadow: 0, alpha: a });
      }
      if (p.badge) {
        const bw = T.measure(String(p.badge), ptFont(S, 26, 800, 'sans')) + 40 * S, bx = x + ph_w / 2 - bw / 2, by = y0 - 78 * S;
        g.save(); g.globalAlpha *= clamp01((age - 0.4) / 0.25); g.fillStyle = '#17c964'; g.beginPath(); g.roundRect(bx, by, bw, 44 * S, 22 * S); g.fill(); g.restore();
        T.text(String(p.badge), x + ph_w / 2, by + 31 * S, { font: ptFont(S, 26, 800, 'sans'), align: 'center', color: '#FFFFFF', shadow: 0, alpha: clamp01((age - 0.4) / 0.25) });
      }
    });
    g.restore();
  },
};
