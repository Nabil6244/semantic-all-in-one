// PT_TWEET: an evidence card for a rumour or quote, on the paper: a white post card with the author, handle, the text, and a highlighted phrase
// that the "marker" sweeps over a moment after the card lands. It is a generic quote card (no network logo, no real profile picture).
//   { "type": "pt_tweet", "start": 0, "end": 6, "author": "Walle", "handle": "@WalleGalaxy", "date": "Aug 24",
//     "text": "This stems from the new charging optimization, allowing the phone to sustain 55W longer.", "highlight": "sustain 55W longer" }
import { tm, clamp01, quartOut } from './tm_theme.mjs';
import { ptMotion, ptFont } from './pt_feature.mjs';

export default {
  type: 'pt_tweet',
  space: 'screen',
  create: (def) => { if (!String(def.text || '').trim()) throw new Error('pt_tweet: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), S = T.S;
    const m = ptMotion(d, f.t, S, { inDur: 0.45, outDur: 0.3, rise: 30 });
    if (m.k <= 0.002) return;
    const cw = W * 0.62, fs = 38, lh = fs * 1.42 * S, text = String(d.text).trim(), hl = String(d.highlight || '');
    g.save(); T.set(ptFont(S, fs, 500, 'sans'));
    const words = text.split(/\s+/), lines = []; let cur = '';
    for (const w of words) { const t = cur ? cur + ' ' + w : w; if (g.measureText(t).width > cw - 120 * S && cur) { lines.push(cur); cur = w; } else cur = t; }
    if (cur) lines.push(cur); g.restore();
    const ch = (150 + fs * 1.42 * lines.length + 50) * S, x = (W - cw) / 2, y = (H - ch) / 2 + m.rise;
    g.save(); g.globalAlpha = (f.alpha ?? 1) * m.k;
    g.shadowColor = 'rgba(0,0,0,0.18)'; g.shadowBlur = 30 * S; g.shadowOffsetY = 10 * S; g.fillStyle = '#FFFFFF'; g.beginPath(); g.roundRect(x, y, cw, ch, 24 * S); g.fill();
    g.shadowColor = 'transparent'; g.shadowBlur = 0; g.strokeStyle = 'rgba(0,0,0,0.08)'; g.lineWidth = 2 * S; g.stroke();
    g.fillStyle = '#c9ced6'; g.beginPath(); g.arc(x + 80 * S, y + 80 * S, 34 * S, 0, 7); g.fill();       // a neutral avatar disc
    T.text(String(d.author || 'Source'), x + 134 * S, y + 74 * S, { font: ptFont(S, 32, 800, 'sans'), color: '#14171a', shadow: 0 });
    T.text(String([d.handle, d.date].filter(Boolean).join('  ·  ')), x + 134 * S, y + 112 * S, { font: ptFont(S, 26, 500, 'sans'), color: '#6b7380', shadow: 0 });
    const sweep = quartOut((m.age - 0.9) / 0.7);
    lines.forEach((ln, i) => {
      const ly = y + 190 * S + i * lh, hi = hl ? ln.toLowerCase().indexOf(hl.toLowerCase()) : -1;
      if (hi >= 0 && sweep > 0) {
        const pre = T.measure(ln.slice(0, hi), ptFont(S, fs, 500, 'sans')), wid = T.measure(ln.slice(hi, hi + hl.length), ptFont(S, fs, 500, 'sans'));
        g.fillStyle = 'rgba(255,214,10,0.55)'; g.fillRect(x + 60 * S + pre, ly - fs * 0.95 * S, wid * sweep, fs * 1.3 * S);
      }
      T.text(ln, x + 60 * S, ly, { font: ptFont(S, fs, 500, 'sans'), color: '#14171a', shadow: 0 });
    });
    g.restore();
  },
};
