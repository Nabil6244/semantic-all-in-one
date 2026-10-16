// TM_DISCMAP: the "where is it from Earth" diagram (V2 0:22): a near-black plate with Earth as a small blue disc at the left edge
// (EARTH in amber under it) and a short line with a glowing node leaving it; at the right a photograph (the JWST deep field) as a
// feather-masked disc. Measured on the reference at 1280x720: Earth centre x 10.4 % / y 50 %, diameter 4.8 % of the width, node at
// x 18.8 %; the photo disc centre x 81 % / y 53.6 %, radius 38.5 % of the height, opaque to 62 % of its radius then fading to nothing.
//   { "type": "tm_discmap", "earth": "EARTH", "image": "jwst.jpg", "keys": [{ "t": 40, "reach": 0.4 }], "start": 38, "end": 46 }
import { C, tm, glideOut, clamp01, drift } from './tm_theme.mjs';

export default {
  type: 'tm_discmap',
  space: 'screen',
  async create(def, ctx) {
    const img = def.image && ctx.loadImage ? await ctx.loadImage(def.image).catch(() => null) : null;
    let disc = null;
    if (img) {
      // the photograph cropped to a square, then masked: opaque to 62 % of the radius, fading out to the edge
      const R = Math.round(def.disc_px || 900), c = document.createElement('canvas'); c.width = c.height = R; const g = c.getContext('2d');
      const side = Math.min(img.width, img.height); g.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, R, R);
      g.globalCompositeOperation = 'destination-in';
      const m = g.createRadialGradient(R / 2, R / 2, 0, R / 2, R / 2, R / 2);
      m.addColorStop(0, 'rgba(0,0,0,1)'); m.addColorStop(0.62, 'rgba(0,0,0,1)'); m.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = m; g.fillRect(0, 0, R, R); disc = c;
    }
    return { def, disc, keys: (def.keys || []).slice().sort((a, b) => a.t - b.t) };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    if (inst.disc) {
      const r = 0.385 * H, k = clamp01((f.t - (d.start ?? 0)) / 0.8);
      g.globalAlpha = f.alpha * k; g.drawImage(inst.disc, 0.81 * W - r, 0.536 * H - r, r * 2, r * 2); g.globalAlpha = f.alpha;
    }
    const ex = 0.104 * W, ey = 0.5 * H, er = 0.024 * W;
    g.fillStyle = '#2F6BDF'; g.beginPath(); g.arc(ex, ey, er, 0, Math.PI * 2); g.fill();
    let reach = 0;
    for (let i = 0; i < inst.keys.length; i++) { if (inst.keys[i].t > f.t) break; const from = i ? inst.keys[i - 1].reach : 0; reach = from + (inst.keys[i].reach - from) * glideOut((f.t - inst.keys[i].t) / 1.4); }
    const x0 = ex + er, x1 = 0.188 * W + reach * (0.62 * W - 0.188 * W);
    T.line(x0, ey, x1, ey, { color: C.cyan, width: 2, alpha: 0.7 });
    T.node(x1, ey, { color: C.cyan, r: 6 });
    T.text(String(d.earth || 'EARTH').toUpperCase(), ex, ey + er + 38 * T.S, { font: T.sans(22, 800), track: 3, align: 'center', color: C.amber, shadow: 0 });
    g.restore();
  },
};
