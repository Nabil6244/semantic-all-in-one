// RH_BG: the scheme's backdrop (dark: night navy gradient, colour: pale gradient). Nothing is drawn for the mono scheme (the shot is black).
//   { "type": "rh_bg", "start": 0, "end": 4 }
import { palOf, schemeOf } from '../lib/rhkit.mjs';
export default {
  type: 'rh_bg', space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const pal = palOf(f, inst.def); if (!pal) return;
    const { g, W, H } = f, gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, pal.bg0); gr.addColorStop(1, pal.bg1);
    g.save(); g.globalAlpha = f.alpha ?? 1; g.fillStyle = gr; g.fillRect(0, 0, W, H);
    if (schemeOf(f) === 'deep') {          // under water: light shafts from above and bubbles rising
      const t = f.t; g.fillStyle = 'rgba(160,225,255,0.05)'; for (let i = 0; i < 4; i++) { const x = W * (0.15 + i * 0.24) + Math.sin(t * 0.3 + i) * W * 0.03; g.beginPath(); g.moveTo(x, 0); g.lineTo(x + W * 0.06, 0); g.lineTo(x + W * 0.16, H); g.lineTo(x + W * 0.02, H); g.fill(); }
      g.strokeStyle = 'rgba(190,235,255,0.35)'; g.lineWidth = Math.max(1, H * 0.0016);
      for (let i = 0; i < 14; i++) { const h1 = Math.abs(Math.sin(i * 12.9898) * 43758.5453) % 1, by = H - ((t * (30 + 40 * h1) + h1 * H * 1.3) % (H * 1.2)); g.beginPath(); g.arc(W * ((h1 * 7.3) % 1) + Math.sin(t * 2 + i) * 4, by, H * (0.003 + 0.006 * h1), 0, Math.PI * 2); g.stroke(); }
    }
    g.restore();
  },
};
