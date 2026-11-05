// RH_PICTURE: a Flow picture (a white shape on pure black) drawn with a lighten blend, so the black disappears and the line set shows through
// everywhere the picture is dark. mode "subject": scaled by "height" (fraction of H for the whole picture), its white shape's bottom on the ground
// line and its centre at x. mode "full": covers the frame (a reveal close-up).
//   { "type": "rh_picture", "file": "p1.png", "mode": "subject", "x": 0.7, "ground": 0.8, "height": 0.7, "flip": true, "cam": {...} }
import { applyCam } from '../lib/rhkit.mjs';
const bbox = (img) => {                                        // the white shape's box (pixels brighter than a threshold), once
  const c = document.createElement('canvas'); c.width = img.naturalWidth || img.width; c.height = img.naturalHeight || img.height;
  const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(img, 0, 0);
  const { data, width, height } = x.getImageData(0, 0, c.width, c.height);
  let x0 = width, y0 = height, x1 = -1, y1 = -1;
  for (let y = 0; y < height; y += 2) for (let xx = 0; xx < width; xx += 2) { if (data[(y * width + xx) * 4] > 60) { if (xx < x0) x0 = xx; if (xx > x1) x1 = xx; if (y < y0) y0 = y; if (y > y1) y1 = y; } }
  return x1 < 0 ? { x0: 0, y0: 0, x1: width, y1: height } : { x0, y0, x1, y1 };
};
export default {
  type: 'rh_picture', space: 'screen',
  async create(def, ctx) {
    if (!def.file) throw new Error('rh_picture: "file" is required');
    const img = await ctx.loadImage(def.file);
    return { def, img, box: def.mode === 'full' || typeof document === 'undefined' ? null : bbox(img) };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, img = inst.img;
    if (!img) return;
    const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
    g.save(); g.globalAlpha = f.alpha ?? 1; applyCam(g, W, H, d, f.t);
    g.globalCompositeOperation = 'lighten';
    if (d.mode === 'full') {
      const s = Math.max(W / iw, H / ih) * (1 + 0.03 * Math.min(1, Math.max(0, (f.t - (d.start ?? 0)) / 3)));   // a slow push so the face is never a still
      g.drawImage(img, (W - iw * s) / 2, (H - ih * s) / 2, iw * s, ih * s);
    } else {
      const s = (H * (d.height ?? 0.7)) / ih, b = inst.box || { x0: 0, y0: 0, x1: iw, y1: ih };
      const cx = ((b.x0 + b.x1) / 2) * s, bottom = b.y1 * s, X = (d.x ?? 0.6) * W, Y = (d.ground ?? 0.8) * H;
      g.translate(X, 0); if (d.flip) g.scale(-1, 1);
      g.drawImage(img, -cx, Y - bottom, iw * s, ih * s);
    }
    g.restore();
  },
};
