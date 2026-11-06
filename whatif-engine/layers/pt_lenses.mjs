// PT_LENSES: lens callouts on the paper (docs/product_trailer/REVIEW_REFERENCE_4.md, gap 4). One or two phone backs, lenses down the top-left;
// a line runs from each named lens out to its label (a small caption over a big figure: "ultrawide / 12MP"). A lens appears on its word ("at",
// s after start, from product_trailer/lenses.py); a figure "??" waits for its answer: "was" shows until "set_at", then the answer flips in.
//   { "type": "pt_lenses", "start": 0, "end": 9, "phones": [{ "label": "Galaxy S27 Plus", "color": "#7a2f45" }, { "label": "Galaxy S27", "color": "#7a2f45" }],
//     "lenses": [{ "kind": "ultrawide", "cap": "ultrawide", "value": "12MP", "at": 0.4 }, { "kind": "main", "cap": "Sony sensor", "value": "50MP", "at": 1.2 },
//                { "kind": "telephoto", "cap": "3x telephoto", "value": "10MP", "was": "??", "at": 2, "set_at": 6.5 }] }
import { tm, clamp01, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

const ROWS = ['ultrawide', 'main', 'telephoto', 'periscope'];
const shade = (hex, k) => { const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '')); if (!m) return hex; const n = parseInt(m[1], 16); const f = (v) => Math.max(0, Math.min(255, Math.round(v * k))); return `rgb(${f(n >> 16 & 255)},${f(n >> 8 & 255)},${f(n & 255)})`; };

export default {
  type: 'pt_lenses',
  space: 'screen',
  create: (def) => { if (!Array.isArray(def.phones) || !def.phones.length) throw new Error('pt_lenses: "phones" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S, ph = d.phones.slice(0, 2), lenses = Array.isArray(d.lenses) ? d.lenses : [];
    const m = ptMotion(d, f.t, S, { inDur: 0.35, outDur: 0.3, rise: 30 });
    if (m.k <= 0.002) return;
    const rows = ROWS.slice(0, lenses.some((l) => l.kind === 'periscope') ? 4 : 3);
    const cams = Math.max(1, Math.min(rows.length, Number(ph[0] && ph[0].cams) || rows.length));   // the phone's own lens count (product_trailer/subject.py)
    const subs = ((f.spec && f.spec.layers) || []).some((L) => L && L.type === 'pt_subtitle');
    const phH = H * (subs ? 0.64 : 0.7), phW = phH * 0.49, y0 = H * 0.5 - phH / 2 - (subs ? H * 0.05 : 0) + m.rise;
    const cols = ph.length === 2 ? [W * 0.08, W * 0.53] : [W * 0.27];
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    ph.forEach((p, pi) => {
      const x = cols[pi], col = p.color || '#7a2f45', r = phW * 0.13;
      g.save(); g.shadowColor = 'rgba(0,0,0,0.22)'; g.shadowBlur = 28 * S; g.shadowOffsetY = 12 * S;
      const gr = g.createLinearGradient(x, y0, x + phW, y0 + phH); gr.addColorStop(0, shade(col, 1.2)); gr.addColorStop(1, shade(col, 0.82));
      g.fillStyle = gr; g.beginPath(); g.roundRect(x, y0, phW, phH, r); g.fill(); g.restore();
      const lr = phW * 0.105, lx = x + phW * 0.24, ly = (j) => y0 + phW * 0.24 + j * phW * 0.29;
      rows.slice(0, cams).forEach((_, j) => {                         // the lenses: dark rings, glass, a glint (only as many as the phone has)
        g.fillStyle = shade(col, 0.55); g.beginPath(); g.arc(lx, ly(j), lr * 1.18, 0, 7); g.fill();
        g.fillStyle = '#10151d'; g.beginPath(); g.arc(lx, ly(j), lr * 0.86, 0, 7); g.fill();
        g.fillStyle = 'rgba(120,170,255,0.5)'; g.beginPath(); g.arc(lx - lr * 0.25, ly(j) - lr * 0.25, lr * 0.22, 0, 7); g.fill();
      });
      g.fillStyle = 'rgba(255,240,210,0.9)'; g.beginPath(); g.arc(x + phW * 0.47, y0 + phW * 0.38, lr * 0.25, 0, 7); g.fill();   // the flash
      if (p.label) {                                                  // the model name on the body, as on the reference renders
        const parts = String(p.label).split(' '), small = parts.length > 1 ? parts[0] : '', big = parts.length > 1 ? parts.slice(1).join(' ') : parts[0];
        if (small) T.text(small, x + phW * 0.08, y0 + phH * 0.8, { font: ptFont(S, 22, 500, 'sans'), color: 'rgba(255,255,255,0.75)', shadow: 0 });
        let px = 46; while (px > 20 && T.measure(big, ptFont(S, px, 700, 'sans')) > phW * 0.86) px -= 2;
        T.text(big, x + phW * 0.08, y0 + phH * 0.8 + px * 1.05 * S, { font: ptFont(S, px, 700, 'sans'), color: 'rgba(255,255,255,0.88)', shadow: 0 });
      }
      lenses.forEach((L, li) => {                                     // the callouts
        const j = rows.indexOf(L.kind);
        if (j < 0) return;
        if (Number.isFinite(L.ring_at) && m.age > L.ring_at) {         // "looks much smaller": a yellow ring sweeps round that lens (gap 5)
          const ks = quartOut((m.age - L.ring_at) / 0.55);
          g.save(); g.strokeStyle = '#f5d000'; g.lineWidth = 5 * S; g.lineCap = 'round'; g.beginPath(); g.arc(lx, ly(j), lr * 1.45, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * ks); g.stroke(); g.restore();
        }
        const age = m.age - (Number.isFinite(L.at) ? L.at : 0.3 + 0.25 * li), kl = quartOut(age / 0.35), kt = clamp01((age - 0.2) / 0.3);
        if (kl <= 0) return;
        const sx = lx + lr * 1.25, ex = x + phW + W * 0.035, ey = ly(j), tx = ex + 14 * S;
        g.save(); if (j >= cams && g.setLineDash) g.setLineDash([6 * S, 8 * S]);   // a lens the phone does not have ("None"): a dashed line to an empty spot
        g.strokeStyle = '#1d2127'; g.lineWidth = 2.5 * S; g.beginPath(); g.moveTo(sx, ey); g.lineTo(sx + (ex - sx) * kl, ey); g.stroke(); g.restore();
        if (kt <= 0) return;
        const hasVal = L.value != null && L.value !== '';
        T.text(String(L.cap || L.kind), tx, ey - (hasVal ? 18 : -8) * S, { font: ptFont(S, hasVal ? 18 : 28, hasVal ? 500 : 700, 'sans'), color: hasVal ? '#4a505a' : '#1d2127', shadow: 0, alpha: kt });
        if (!hasVal) return;
        const vf = ptFont(S, 50, 800, 'sans');
        const swap = L.was != null && Number.isFinite(L.set_at) ? clamp01((m.age - L.set_at) / 0.3) : 1;
        if (swap < 1) T.text(String(L.was), tx, ey + 34 * S - swap * 16 * S, { font: vf, color: '#1d2127', shadow: 0, alpha: kt * (1 - swap) });
        if (swap > 0) T.text(String(L.value), tx, ey + 34 * S + (1 - swap) * 16 * S, { font: vf, color: L.was != null ? '#17a34a' : '#1d2127', shadow: 0, alpha: kt * swap });
      });
    });
    g.restore();
  },
};
