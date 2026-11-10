// PT_FLATPHONES: the explainer-review staple: one to four flat phone cut-outs side by side on the paper, each with a label on the back, a giant
// figure on it ("60W", "$1315") and optionally a battery capsule that fills beside it.
//   { "type": "pt_flatphones", "start": 0, "end": 5, "title": "CHARGING SPEED",
//     "phones": [{ "label": "Galaxy S26 Ultra", "text": "60W", "color": "#5b5a86", "cams": 4, "fill": 0.95, "top": "5000mAh", "highlight": false },
//                { "label": "Galaxy S27 Ultra", "text": "60W", "color": "#2b2b2e", "cams": 3, "fill": 0.99, "top": "5700mAh" }] }
// More per phone: design: "bar" (a camera bar across the top, as on the Galaxy S27 Ultra; default: a lens column), fill_from (the capsule counts from it), cutaway:true (the battery cell is drawn inside the body, level cell_from -> cell), side: {from,to,suffix,prefix}
// or side: {text} (a big figure to the right of the phone), cable: "60W" (a cable out of the bottom with a readout), badge: "+700mAh" (a green pill above).
// fill 0..1 grows from empty over about a second after the phone appears; "cams" is 2..4 lens circles; the phones pop in one after the other.
import { tm, clamp01, overshoot, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont, cueAge } from './pt_feature.mjs';

const GREEN = '#1fc41f';
const shade = (hex, k) => { const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '')); if (!m) return hex; const n = parseInt(m[1], 16); const f = (v) => Math.max(0, Math.min(255, Math.round(v * k))); return `rgb(${f(n >> 16 & 255)},${f(n >> 8 & 255)},${f(n & 255)})`; };

// the camera layout a phone's name or its label above calls for when the scene gives none: an iPhone's square module, a Pixel's visor bar
// ("Google-like" too); everything else keeps the lens column (a camera-bar Galaxy is set by the planner as design "bar")
export function designFor(p) {
  const t = `${p.label || ''} ${p.top || ''}`.toLowerCase();
  if (/\biphone\b/.test(t)) return 'iphone';
  if (/\b(pixel|google)\b/.test(t)) return 'pixel';
  return null;
}

// a realistic camera lens: brushed ring, black glass, a coloured coating glint and a hard specular dot
function lens(g, cx, cy, R) {
  const ring = g.createLinearGradient(cx - R, cy - R, cx + R, cy + R); ring.addColorStop(0, '#d9dde3'); ring.addColorStop(0.5, '#6d727a'); ring.addColorStop(1, '#c4c8ce');
  g.fillStyle = ring; g.beginPath(); g.arc(cx, cy, R, 0, 7); g.fill();
  g.fillStyle = '#07090d'; g.beginPath(); g.arc(cx, cy, R * 0.8, 0, 7); g.fill();
  const glass = g.createRadialGradient(cx - R * 0.2, cy - R * 0.25, R * 0.05, cx, cy, R * 0.62); glass.addColorStop(0, '#2a3f6b'); glass.addColorStop(0.55, '#0d1424'); glass.addColorStop(1, '#05070b');
  g.fillStyle = glass; g.beginPath(); g.arc(cx, cy, R * 0.62, 0, 7); g.fill();
  g.fillStyle = 'rgba(150,110,255,0.35)'; g.beginPath(); g.arc(cx + R * 0.18, cy + R * 0.15, R * 0.22, 0, 7); g.fill();
  g.fillStyle = 'rgba(255,255,255,0.85)'; g.beginPath(); g.arc(cx - R * 0.26, cy - R * 0.28, R * 0.09, 0, 7); g.fill();
}

// the back of a camera-bar phone (Galaxy S27 Ultra style): a raised bar across the top holding the big lenses, a pill with the small lens and the
// flash, a metal frame edge and a soft diagonal sheen. Used by phones with design "bar"; the others keep the lens column.
function drawBarBack(g, x, y0, w, h, r, col, cams, S) {
  g.save(); g.beginPath(); g.roundRect(x, y0, w, h, r); g.clip();
  const sheen = g.createLinearGradient(x, y0, x + w, y0 + h * 0.6); sheen.addColorStop(0, 'rgba(255,255,255,0)'); sheen.addColorStop(0.45, 'rgba(255,255,255,0.10)'); sheen.addColorStop(0.55, 'rgba(255,255,255,0)');
  g.fillStyle = sheen; g.fillRect(x, y0, w, h); g.restore();
  const bx = x + w * 0.07, by = y0 + h * 0.035, bw = w * 0.86, bh = h * 0.215, br = bh * 0.32;
  g.save(); g.shadowColor = 'rgba(0,0,0,0.28)'; g.shadowBlur = 10 * S; g.shadowOffsetY = 4 * S;
  const bar = g.createLinearGradient(bx, by, bx, by + bh); bar.addColorStop(0, shade(col, 1.18)); bar.addColorStop(1, shade(col, 0.92));
  g.fillStyle = bar; g.beginPath(); g.roundRect(bx, by, bw, bh, br); g.fill(); g.restore();
  g.strokeStyle = 'rgba(255,255,255,0.22)'; g.lineWidth = 1.5 * S; g.beginPath(); g.roundRect(bx, by, bw, bh, br); g.stroke();
  const R = bh * 0.26, big = Math.min(2, cams - 1);
  for (let i = 0; i < big; i++) lens(g, bx + bh * 0.3, by + bh * (big === 1 ? 0.5 : 0.27 + i * 0.46), R);
  const px = bx + bh * 0.62, pw = R * 1.5, ph = bh * 0.72, py = by + (bh - ph) / 2;
  g.fillStyle = '#0a0c10'; g.beginPath(); g.roundRect(px, py, pw, ph, pw / 2); g.fill();
  g.fillStyle = '#fff6d8'; g.beginPath(); g.arc(px + pw / 2, py + ph * 0.3, pw * 0.17, 0, 7); g.fill();
  lens(g, px + pw / 2, py + ph * 0.7, pw * 0.36);
  const fr = g.createLinearGradient(x, y0, x + w, y0); fr.addColorStop(0, 'rgba(255,255,255,0.45)'); fr.addColorStop(0.5, 'rgba(255,255,255,0.08)'); fr.addColorStop(1, 'rgba(255,255,255,0.35)');
  g.strokeStyle = fr; g.lineWidth = 3 * S; g.beginPath(); g.roundRect(x + 1.5 * S, y0 + 1.5 * S, w - 3 * S, h - 3 * S, r); g.stroke();
}

export default {
  type: 'pt_flatphones',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.phones) || !def.phones.length) throw new Error('pt_flatphones: "phones" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, ph = d.phones.slice(0, 4), n = ph.length;
    let m = ptMotion(d, f.t, S, { inDur: 0.3, outDur: 0.25, rise: 0 });
    if (d.hold) m = { k: clamp01(((d.end ?? f.t + 1) - f.t) / 0.05), kin: 1, age: 99, rise: 0 };        // a continuation of the scene before it: already settled, no new entrance
    // a building canvas (product_trailer/canvas.py): "keep" = the next sentence continues this scene, so no fade-out; "cont" = this continues the
    // scene before it, so the phones are already there; only the facts in p.fresh come in (on their word), facts in p.dim stay at 40 %
    if (!d.hold && (d.keep || d.cont)) m = { ...m, k: (d.cont ? 1 : m.kin) * (d.keep ? 1 : clamp01(((d.end ?? f.t + 1) - f.t) / 0.25)) };
    if (m.k <= 0.002) return;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    const zoom = 1 + Math.min(0.06, 0.008 * Math.max(0, f.t - (d.t0 ?? d.start ?? 0)));            // a slow push so a held scene is never a still
    g.translate(W / 2, H / 2); g.scale(zoom, zoom); g.translate(-W / 2, -H / 2);
    const hasCap0 = ph.some((p) => p.fill != null), hasSide0 = ph.some((p) => p.side), per = 0.49 * (1 + (hasCap0 ? 0.9 : hasSide0 ? 0.5 : 0.6)) + (hasSide0 ? 0.49 * 1.25 * 0.9 : hasCap0 ? 0.49 * 0.42 * 0.9 : 0);
    // the row of n phones, their gaps and capsules fits in 90 % of the width (four phones used to run off both edges)
    const subs = ((f.spec && f.spec.layers) || []).some((L) => L && L.type === 'pt_subtitle');
    const ph_h = Math.min(subs ? H * 0.6 : H * 0.66, W * 0.78 / n * 1.9, W * 0.9 / Math.max(0.01, n * per - 0.49 * (hasCap0 ? 0.9 : hasSide0 ? 0.5 : 0.6))), ph_w = ph_h * 0.49, hasCap = ph.some((p) => p.fill != null), hasSide = ph.some((p) => p.side), gap = ph_w * (hasCap ? 0.9 : hasSide ? 0.5 : 0.6), capW = hasSide ? ph_w * 1.25 : hasCap ? ph_w * 0.42 : 0;
    // a film with subtitles keeps its bottom band clear: the phones end above the caption box (they ran under it on the price and size cards)
    const lift = subs ? Math.max(0, H * 0.53 + ph_h / 2 - H * 0.82) : 0;
    const unit = ph_w + gap + capW * 0.9, x0 = W / 2 - (unit * n - gap) / 2, y0 = H * 0.5 - ph_h / 2 + H * 0.03 - lift;
    if (d.title) T.text(String(d.title).toUpperCase(), W / 2, H * 0.11, { font: ptFont(S, 34, 700, 'sans'), track: 4, align: 'center', color: '#8A8F98', shadow: 0 });
    ph.forEach((p, i) => {
      const cont = !!d.cont && !d.hold, fresh = new Set(cont ? p.fresh || [] : []), dims = new Set(cont ? p.dim || [] : []), was = (cont && p.was) || {};
      const age = cont ? 99 : cueAge(m.age, p, i, 0.12), kin = overshoot(age / 0.45), x = x0 + unit * i, a = clamp01(age / 0.25);
      if (a <= 0) return;
      const fAge = (k) => (fresh.has(k) ? cueAge(m.age, p, i, 0.12) : age), fA = (k) => (dims.has(k) ? 0.4 : fresh.has(k) ? clamp01(fAge(k) / 0.25) : 1);
      const bob = d.bob === false ? 0 : Math.sin(f.t * 1.3 + i) * ph_h * 0.008;
      g.save(); g.globalAlpha *= a; g.translate(0, bob); g.translate(x + ph_w / 2, y0 + ph_h / 2); const sc = 0.82 + 0.18 * Math.min(1.08, kin); g.scale(sc, sc); g.translate(-(x + ph_w / 2), -(y0 + ph_h / 2));
      const r = ph_w * 0.14, col = p.color || '#2b2b2e';
      g.shadowColor = 'rgba(0,0,0,0.22)'; g.shadowBlur = 26 * S; g.shadowOffsetY = 12 * S;
      const gr = g.createLinearGradient(x, y0, x + ph_w, y0 + ph_h); gr.addColorStop(0, shade(col, 1.25)); gr.addColorStop(1, shade(col, 0.8));
      g.fillStyle = gr; g.beginPath(); g.roundRect(x, y0, ph_w, ph_h, r); g.fill();
      g.shadowColor = 'transparent'; g.shadowBlur = 0; g.strokeStyle = 'rgba(255,255,255,0.18)'; g.lineWidth = 2 * S; g.stroke();
      const cams = Math.max(2, Math.min(4, p.cams || 3)), cr = ph_w * 0.095;      // lens circles down the top-left
      const design = p.design || designFor(p);
      if (design === 'bar') { drawBarBack(g, x, y0, ph_w, ph_h, r, col, cams, S); }
      else if (design === 'iphone') {                                            // a square camera module, lenses in a triangle, the flash beside them
        const side = ph_w * 0.47, mx = x + ph_w * 0.07, my = y0 + ph_w * 0.07, R = side * 0.2;
        g.fillStyle = shade(col, 1.12); g.strokeStyle = 'rgba(255,255,255,0.25)'; g.lineWidth = Math.max(1, 1.5 * S); g.beginPath(); g.roundRect(mx, my, side, side, side * 0.26); g.fill(); g.stroke();
        [[0.3, 0.29], [0.3, 0.71], [0.71, 0.5]].slice(0, Math.max(2, Math.min(3, cams))).forEach(([u, v]) => lens(g, mx + side * u, my + side * v, R));
        g.fillStyle = '#f4ead2'; g.beginPath(); g.arc(mx + side * 0.71, my + side * 0.2, R * 0.28, 0, 7); g.fill();
      } else if (design === 'pixel') {                                           // a camera visor across the full width, lenses in a row
        const bh = ph_h * 0.085, by = y0 + ph_h * 0.12, R = bh * 0.32;
        g.fillStyle = '#15171b'; g.beginPath(); g.roundRect(x - ph_w * 0.01, by, ph_w * 1.02, bh, bh / 2); g.fill();
        for (let c = 0; c < Math.max(2, Math.min(3, cams)); c++) lens(g, x + ph_w * (0.22 + c * 0.16), by + bh / 2, R);
        g.fillStyle = '#f4ead2'; g.beginPath(); g.arc(x + ph_w * 0.8, by + bh / 2, R * 0.35, 0, 7); g.fill();
      } else for (let c = 0; c < cams; c++) {
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
      if (p.text) { const fit = (px) => { while (px > 24 && T.measure(String(p.text), ptFont(S, px, 900)) > ph_w * 0.92) px -= 4; return px; }; const px = fit(Math.min(ph_w * 0.5 / S, 110)); T.text(String(p.text), x + ph_w / 2, y0 + ph_h * 0.58, { font: ptFont(S, px, 900), align: 'center', color: '#FFFFFF', shadow: 0.35, alpha: fA('text') }); }
      if (was.text != null && fA('text') < 1) T.text(String(was.text), x + ph_w / 2, y0 + ph_h * 0.58, { font: ptFont(S, Math.min(ph_w * 0.5 / S, 110), 900), align: 'center', color: '#FFFFFF', shadow: 0.35, alpha: 1 - fA('text') });
      g.restore();
      if (p.top) T.text(String(p.top), x + ph_w / 2, y0 - 18 * S, { font: ptFont(S, 26, 700, 'sans'), align: 'center', color: '#3a3f47', shadow: 0, alpha: a * fA('top') });
      if (was.top != null && fA('top') < 1) T.text(String(was.top), x + ph_w / 2, y0 - 18 * S, { font: ptFont(S, 26, 700, 'sans'), align: 'center', color: '#3a3f47', shadow: 0, alpha: a * (1 - fA('top')) });
      if (p.fill != null) {                                                        // the battery capsule beside the phone
        const cx = x + ph_w + capW * 0.25, ch = ph_h * 0.34, cy = y0 + ph_h * 0.5 - ch / 2, k = quartOut((fAge('fill') - 0.3) / 1.2), lvl = clamp01((p.fill_from ?? 0) + (clamp01(p.fill) - (p.fill_from ?? 0)) * k);
        g.save(); g.beginPath(); g.roundRect(cx, cy, capW, ch, capW / 2); g.clip();
        g.fillStyle = 'rgba(0,0,0,0.07)'; g.fillRect(cx, cy, capW, ch);
        g.fillStyle = lvl > 0.2 ? GREEN : '#e8a21a'; g.fillRect(cx, cy + ch * (1 - lvl), capW, ch * lvl);
        g.fillStyle = 'rgba(255,255,255,0.28)'; g.fillRect(cx + capW * 0.14, cy, capW * 0.14, ch); g.restore();
        g.strokeStyle = 'rgba(0,0,0,0.5)'; g.lineWidth = 3 * S; g.beginPath(); g.roundRect(cx, cy, capW, ch, capW / 2); g.stroke();
        T.text('%' + Math.round(lvl * 100), cx + capW / 2, cy + ch / 2 + 11 * S, { font: ptFont(S, 32, 800), align: 'center', color: '#FFFFFF', shadow: 0.6 });
      }
      if (p.side) {
        const sd = p.side, kk = quartOut((fAge('side') - 0.25) / 1.2), v = sd.text != null ? sd.text : `${sd.prefix ?? ''}${Math.round((sd.from ?? 0) + ((sd.to ?? 0) - (sd.from ?? 0)) * kk)}${sd.suffix ?? ''}`;
        T.text(v, x + ph_w + gap * 0.3, y0 + ph_h * 0.56, { font: ptFont(S, sd.size || 96, 900), color: sd.color || '#1d2127', shadow: 0, alpha: a * fA('side') });
        if (sd.sub) T.text(String(sd.sub).toUpperCase(), x + ph_w + gap * 0.3 + 4 * S, y0 + ph_h * 0.56 + (sd.size || 96) * 0.42 * S, { font: ptFont(S, 28, 700, 'sans'), track: 3, color: '#5d636d', shadow: 0, alpha: a * fA('side') * clamp01((fAge('side') - 0.2) / 0.3) });   // what the figure is for
      }
      if (p.cable) {
        const cxp = x + ph_w / 2, yb = y0 + ph_h;
        g.save(); g.globalAlpha *= a; g.strokeStyle = '#1b1d21'; g.lineWidth = 7 * S; g.lineCap = 'round'; g.beginPath(); g.moveTo(cxp, yb); g.lineTo(cxp, Math.min(H * 0.99, yb + H * 0.12)); g.stroke();
        g.fillStyle = '#1b1d21'; g.beginPath(); g.roundRect(cxp - 12 * S, yb - 4 * S, 24 * S, 22 * S, 5 * S); g.fill(); g.restore();
        if (typeof p.cable === 'string' && p.cable) T.text(p.cable, cxp, yb + 52 * S, { font: ptFont(S, 28, 800, 'sans'), align: 'center', color: '#1d2127', shadow: 0, alpha: a });
      }
      const kb = !p.badge ? 0 : dims.has('badge') ? 0.4 : cont && !fresh.has('badge') ? 1 : clamp01(((Number.isFinite(p.badge_at) ? m.age - p.badge_at : fAge('badge') - 0.4)) / 0.25);   // a badge named later lands on its own word
      if (p.badge && kb > 0) {
        const bw = T.measure(String(p.badge), ptFont(S, 26, 800, 'sans')) + 40 * S, bx = x + ph_w / 2 - bw / 2, by = y0 - (p.top ? 104 : 78) * S;   // above the top label, never on it
        g.save(); g.globalAlpha *= kb; g.fillStyle = '#17c964'; g.beginPath(); g.roundRect(bx, by, bw, 44 * S, 22 * S); g.fill(); g.restore();
        T.text(String(p.badge), x + ph_w / 2, by + 31 * S, { font: ptFont(S, 26, 800, 'sans'), align: 'center', color: '#FFFFFF', shadow: 0, alpha: kb });
      }
    });
    g.restore();
  },
};
