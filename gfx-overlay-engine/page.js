// The browser side: one canvas, one gfx-core template at a time, one transparent PNG per frame.
import { createGfx, drawGfx } from '/gfx/lib/render.mjs';

const c = document.getElementById('c');
let g = null, W = 0, H = 0, inst = null, images = new Map(), dy = 0, sc = 1, ax = 0, ay = 0, env = null;

window.setup = async (w, h) => {
  W = w; H = h; c.width = w; c.height = h;
  g = c.getContext('2d', { willReadFrequently: false });
  await document.fonts.load('800 40px GfxSans');
  await document.fonts.load('600 40px GfxSerif');
  await document.fonts.load('italic 500 40px GfxSerif');
  return true;
};

/** Build the template instance; images = { name: url } preloaded so a template's photos draw on frame 1. */
window.begin = async (template, slots, len, cues, imageUrls, shiftY, scale, anchorX, anchorY) => {
  images = new Map();
  dy = Number(shiftY) || 0; sc = Number(scale) || 1; ax = Number(anchorX) || 0; ay = Number(anchorY) || 0;   // scale is about the anchor point (fractions of the frame)                       // the whole graphic moved up/down by this share of the frame height (caption clearance)
  env = new Uint8Array(W * H);                    // strongest alpha every pixel ever gets: where this graphic can ever draw
  for (const [name, url] of Object.entries(imageUrls || {})) {
    try { const r = await fetch(url); images.set(name, await createImageBitmap(await r.blob())); } catch { /* the template draws without it */ }
  }
  const warnings = [];
  inst = createGfx(template, slots || {}, { len, cues: cues || {}, warn: (m) => warnings.push(String(m)) });
  return warnings;
};

/** Frame at t seconds: { png: base64, box: [x0,y0,x1,y1] | null } (box = where anything is drawn, measured on every `scan`th frame). */
window.frame = (t, scan, wantEntry) => {
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
  g.clearRect(0, 0, W, H);
  if (dy) g.translate(0, dy * H);
  if (sc !== 1) { g.translate(ax * W, ay * H); g.scale(sc, sc); g.translate(-ax * W, -ay * H); }   // uniform: aspect ratio and proportions are kept
  drawGfx(inst, g, W, H, t, { image: (n) => images.get(n) || null });
  g.setTransform(1, 0, 0, 1, 0, 0);
  let box = null, ink = null, band = 0, entry = false;
  if (wantEntry && !scan) {   // cheap: is anything clearly visible yet (alpha >= 96 in a few dozen sampled pixels)
    const d = g.getImageData(0, 0, W, H).data;
    let n = 0;
    for (let y = 0; y < H && n < 40; y += 3) for (let x = 0; x < W && n < 40; x += 3) if (d[(y * W + x) * 4 + 3] >= 96) n++;
    entry = n >= 40;
  }
  if (scan) {
    const d = g.getImageData(0, 0, W, H).data;
    let x0 = W, y0 = H, x1 = -1, y1 = -1, i0 = W, j0 = H, i1 = -1, j1 = -1;
    const bandTop = Math.round(H * 0.78), bx0 = Math.round(W * 0.08), bx1 = Math.round(W * 0.92);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const a = d[(y * W + x) * 4 + 3];
      if (a > env[y * W + x]) env[y * W + x] = a;
      if (a > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      if (a > 200) { if (x < i0) i0 = x; if (x > i1) i1 = x; if (y < j0) j0 = y; if (y > j1) j1 = y; }   // ink: type, bars, rings (a soft backing is never this opaque)
      if (y >= bandTop && x >= bx0 && x <= bx1 && a > band) band = a;                                    // the caption area: how much of anything lies over it
    }
    if (x1 >= 0) box = [x0, y0, x1, y1];
    if (i1 >= 0) ink = [i0, j0, i1, j1];
    if (wantEntry) { let n = 0; for (let y = 0; y < H && n < 40; y += 3) for (let x = 0; x < W && n < 40; x += 3) if (d[(y * W + x) * 4 + 3] >= 96) n++; entry = n >= 40; }
  }
  return { png: c.toDataURL('image/png').slice('data:image/png;base64,'.length), box, ink, band, entry };
};

/** The alpha envelope as a grey PNG (base64): lets the planner test any rectangle (a caption) for overlap without redrawing. */
window.envelope = () => {
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const cx = cv.getContext('2d'), im = cx.createImageData(W, H);
  for (let i = 0; i < W * H; i++) { const a = env[i]; im.data[i * 4] = a; im.data[i * 4 + 1] = a; im.data[i * 4 + 2] = a; im.data[i * 4 + 3] = 255; }
  cx.putImageData(im, 0, 0);
  return cv.toDataURL('image/png').slice('data:image/png;base64,'.length);
};

window.__ready = true;
