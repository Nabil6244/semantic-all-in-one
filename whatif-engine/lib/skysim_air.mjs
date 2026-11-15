// Sky Sim shared air (docs/skysim/QUALITY.md): the clean sky gradient and the soft glow every look uses.
// The competitor's skies are smooth, dark-zenith gradients with a lighter horizon band and a colour cast from the light source;
// their bright objects bloom softly. Measured targets: sky roughness <= 1.5, real blacks at night. Pure 2D canvas.

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const lerp = (a, b, k) => a + (b - a) * k;
export const mixc = (c1, c2, k) => c1.map((v, i) => lerp(v, c2[i], clamp01(k)));
export const rgba = (c, a = 1) => `rgba(${Math.round(c[0])},${Math.round(c[1])},${Math.round(c[2])},${a})`;

/** The colour of a light source by its kind / temperature, 0..255. */
export function lightColour(sky) {
  if (sky.kind === 'black_hole') return [255, 214, 170];
  const T = sky.temp_k || (sky.object === 'sun' ? 5772 : 6500);
  if (T < 3500) return [255, 150, 80];
  if (T < 5000) return [255, 196, 130];
  if (T < 6500) return [255, 238, 214];
  if (T < 9000) return [228, 236, 255];
  return [190, 210, 255];
}

/** How the sky looks for this much light (flux: sunlight at Earth = 1) -> {zenith, mid, horizon, band, night, ...}.
 *  Like the competitor: a navy night (never pure black, so silhouettes read), blue day, a warm band at twilight, and past
 *  daylight the camera stops down so the sky turns deep blue again around the blinding object (never white, never brown). */
export function airAt(flux, light = [255, 238, 214]) {
  const L = Math.log10(Math.max(flux || 0, 1e-30));
  const day = smooth((L + 4.2) / 4.0);            // 0 a moonless night, 1 full daylight
  const dusk = Math.max(0, 1 - Math.abs(day - 0.45) / 0.35) * 0.7;
  const stop = smooth((L - 0.8) / 2.5);           // brighter than the Sun: exposure drops
  const night = 1 - day;
  let zenith = mixc([12, 15, 26], [50, 92, 162], day);
  let mid = mixc([18, 22, 35], [92, 138, 196], day);
  let horizon = mixc([48, 56, 76], [176, 196, 216], day);
  horizon = mixc(horizon, mixc([214, 150, 110], light, 0.35), dusk);
  mid = mixc(mid, [70, 80, 120], dusk * 0.5);
  zenith = mixc(zenith, [10, 24, 66], stop * 0.9);
  mid = mixc(mid, [30, 58, 116], stop * 0.85);
  horizon = mixc(horizon, mixc([96, 118, 156], light, 0.15), stop * 0.8);
  return { zenith, mid, horizon, band: mixc(horizon, [255, 255, 255], 0.08 * day), night, day, dusk, stop, flood: 0, L };
}

// a fixed fine dither tile: 8-bit gradients band on YouTube without it; +-1 level is below what the eye or the check sees
let ditherTile = null;
function dither() {
  if (ditherTile || typeof document === 'undefined') return ditherTile;
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d'), im = g.createImageData(128, 128);
  let s = 12345;
  for (let i = 0; i < im.data.length; i += 4) {
    s = (s * 1664525 + 1013904223) >>> 0; const v = s & 1 ? 255 : 0;
    im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 3;
  }
  g.putImageData(im, 0, 0);
  ditherTile = c;
  return c;
}

/** Fill the sky from y0 (top) to the horizon line hy with the clean gradient. */
export function drawAir(g, W, y0, hy, air) {
  const gr = g.createLinearGradient(0, y0, 0, hy);
  gr.addColorStop(0, rgba(air.zenith)); gr.addColorStop(0.55, rgba(air.mid)); gr.addColorStop(0.9, rgba(air.horizon));
  gr.addColorStop(1, rgba(air.band));
  g.fillStyle = gr; g.fillRect(0, y0, W, hy - y0);
  const d = dither();
  if (d) { g.save(); g.fillStyle = g.createPattern(d, 'repeat'); g.globalCompositeOperation = 'overlay'; g.fillRect(0, y0, W, hy - y0); g.restore(); }
}

/** A soft bloom around a bright thing: three stacked falloffs (core, halo, wide scatter), additive. */
export function drawGlow(g, x, y, r, colour, strength, S) {
  if (strength <= 0.003) return;
  g.save(); g.globalCompositeOperation = 'lighter';
  for (const [rad, a] of [[Math.max(r * 1.8, 10 * S), 0.55], [Math.max(r * 4, 46 * S), 0.22], [Math.max(r * 11, 220 * S), 0.09]]) {
    const gr = g.createRadialGradient(x, y, Math.min(r, rad * 0.2), x, y, rad);
    gr.addColorStop(0, rgba(colour, a * strength)); gr.addColorStop(0.4, rgba(colour, a * strength * 0.35)); gr.addColorStop(1, rgba(colour, 0));
    g.fillStyle = gr; g.beginPath(); g.arc(x, y, rad, 0, Math.PI * 2); g.fill();
  }
  g.restore();
}

// ---- the quasar as the competitor draws it: a big tilted spiral disc, a small black centre, a thin twin jet ----------------
let discTex = null;
function quasarTexture() {
  if (discTex || typeof document === 'undefined') return discTex;
  const N = 1024, c = document.createElement('canvas'); c.width = c.height = N;
  const g = c.getContext('2d'), im = g.createImageData(N, N), d = im.data;
  let seed = 7; const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
  const ph = Array.from({ length: 6 }, () => rnd() * 6.28);
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      const u = (x + 0.5) / N * 2 - 1, v = (y + 0.5) / N * 2 - 1, r = Math.hypot(u, v), i = (y * N + x) * 4;
      if (r > 1) { d[i + 3] = 0; continue; }
      const th = Math.atan2(v, u), lr = Math.log(Math.max(r, 0.004));
      const arms = 0.5 + 0.5 * Math.sin(th * 2 + lr * 7 + ph[0]);
      const fine = 0.5 + 0.5 * Math.sin(th * 5 + lr * 19 + ph[1] + Math.sin(th * 3 + ph[2]) * 0.8);
      // turbulence: hashed value noise in (log r, angle), two octaves, so the lanes break up like the reference's gas
      const vn = (a, b) => { const ia = Math.floor(a), ib = Math.floor(b), fa = a - ia, fb = b - ib;
        const h = (i, j) => { let q = (i * 374761393 + j * 668265263) >>> 0; q = (q ^ (q >>> 13)) * 1274126177 >>> 0; return (q & 1023) / 1023; };
        const sa = fa * fa * (3 - 2 * fa), sb = fb * fb * (3 - 2 * fb);
        return (h(ia, ib) * (1 - sa) + h(ia + 1, ib) * sa) * (1 - sb) + (h(ia, ib + 1) * (1 - sa) + h(ia + 1, ib + 1) * sa) * sb; };
      const tu = vn(lr * 14 + 50, (th + Math.PI) * 9 + lr * 6) * 0.6 + vn(lr * 40 + 9, (th + Math.PI) * 26 + lr * 18) * 0.4;
      const band = 0.5 + 0.2 * arms + 0.1 * fine + 0.35 * (tu - 0.5) * 2 * 0.5 + 0.12;
      const k = Math.min(1, r);                                    // colour: white-hot core -> yellow -> orange -> deep red edge
      const col = k < 0.04 ? [255, 250, 236] : k < 0.15 ? [255, 214, 140] : k < 0.45 ? [255, 150, 50] : k < 0.8 ? [226, 96, 26] : [140, 46, 14];
      const fall = Math.pow(1 - k, 1.35) * (0.35 + 0.65 * Math.exp(-k * 2.2));
      const a = Math.min(1, fall * band * 1.4) * Math.min(1, r / 0.02);
      d[i] = col[0]; d[i + 1] = col[1]; d[i + 2] = col[2]; d[i + 3] = Math.round(255 * a);
    }
  }
  g.putImageData(im, 0, 0);
  discTex = c;
  return c;
}

/** rh: the event horizon radius in px. The glowing disc reaches DISC_RADII horizons (the competitor's proportions). */
export const DISC_RADII = 80;
export function drawQuasar(g, x, y, rh, t, S, W, H) {
  const Ro = Math.min(rh * DISC_RADII, Math.max(W, H) * 6);
  const show = smooth((Ro - 14 * S) / (70 * S));          // a point of light until the disc spans ~15 px
  const tilt = 0.36, rot = -0.2, spin = -t * 0.02;
  if (show > 0.01) {
    const tex = quasarTexture();
    g.save(); g.globalAlpha *= show; g.translate(x, y); g.rotate(rot); g.scale(1, tilt); g.rotate(spin);
    if (tex) g.drawImage(tex, -Ro, -Ro, Ro * 2, Ro * 2);      // normal blend: it stays orange over a bright sky
    g.restore();
    // the twin jet along the disc's axis: thin, bright at the core, fading out
    const len = Math.max(H * 0.9, Ro * 1.6) * smooth((Ro - 14 * S) / (200 * S)), w = Math.max(1.6 * S, Math.min(rh * 1.4, 9 * S));
    g.save(); g.globalAlpha *= show; g.translate(x, y); g.rotate(rot); g.globalCompositeOperation = 'lighter';
    for (const sgn of [-1, 1]) {
      const lg = g.createLinearGradient(0, 0, 0, sgn * len);
      lg.addColorStop(0, 'rgba(225,235,255,0.95)'); lg.addColorStop(0.4, 'rgba(200,215,255,0.45)'); lg.addColorStop(1, 'rgba(200,215,255,0)');
      g.fillStyle = lg; g.beginPath(); g.moveTo(-w / 2, 0); g.lineTo(-w * 0.9, sgn * len); g.lineTo(w * 0.9, sgn * len); g.lineTo(w / 2, 0); g.fill();
    }
    g.restore();
    g.save(); g.fillStyle = '#000'; g.globalAlpha *= show; g.beginPath(); g.arc(x, y, Math.max(rh * 1.6, 0.5 * S), 0, Math.PI * 2); g.fill(); g.restore();
  }
  return show;
}
