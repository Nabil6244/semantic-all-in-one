// Sky Sim silhouette-lake look (docs/skysim/QUALITY.md): the competitor's most used picture. A real mountain skyline
// (skysim/ridges.py, from elevation data) as dark silhouettes fading into haze with distance, a still lake mirroring the sky,
// one bright object. Dark, clean and simple on purpose: the quality is in the restraint.
//   shot: { kind: 'sky', look: 'lake', sky: {...}, ridges?: { az_deg: [], layers: [{ deg: [] }] far -> near }, elev_deg? }
import { skyAt, cameraAt, drawStars, rng } from './skysim_sky.mjs';
import { drawObject } from './skysim_land.mjs';
import { airAt, drawAir, drawGlow, drawQuasar, lightColour, mixc, rgba } from './skysim_air.mjs';

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
export const LAKE_LENS = 24;          // px per degree at 1080p: ~80 degrees across, the competitor's lake framing
export const HORIZON = 0.6;           // the water line, fraction of H

// ---- ridges: real ones from the spec, else a seeded low skyline -----------------------------------------------------
let fallback = null;
export function fallbackRidges() {
  if (fallback) return fallback;
  const az = [], layers = [[], [], []];
  const r = rng(77), v = Array.from({ length: 64 }, () => r());
  const n = (x) => { const i = Math.floor(x) & 63, f = x - Math.floor(x), k = f * f * (3 - 2 * f); return v[i] + (v[(i + 1) & 63] - v[i]) * k; };
  for (let a = -52; a <= 52.001; a += 0.25) {
    az.push(a);
    const fb = (o, s) => [1, 0.5, 0.25, 0.12].reduce((acc, w, k) => acc + w * n((a + o) * s * 2 ** k), 0) / 1.87;
    layers[0].push(2.5 + 6.5 * fb(11, 0.05) + 3 * Math.max(0, Math.abs(a) - 25) / 27);
    layers[1].push(Math.max(0, 1 + 7 * fb(41, 0.07) - 3 + 4 * Math.max(0, Math.abs(a) - 30) / 22));
    layers[2].push(Math.max(0, 9 * fb(97, 0.09) - 5.5 + 7 * Math.max(0, Math.abs(a) - 34) / 18));
  }
  for (let i = 0; i < az.length; i++) { layers[1][i] = Math.max(layers[1][i], 0); layers[0][i] = Math.max(layers[0][i], layers[1][i]); }
  fallback = { az_deg: az, layers: layers.map((deg) => ({ deg })) };
  return fallback;
}

/** The skyline angle (deg) of a layer at azimuth a. */
function ridgeAt(R, li, a) {
  const az = R.az_deg, d = R.layers[li].deg, step = az[1] - az[0];
  const f = (a - az[0]) / step, i = Math.max(0, Math.min(az.length - 2, Math.floor(f))), k = clamp01(f - i);
  return d[i] + (d[i + 1] - d[i]) * k;
}

let topCanvas = null;
function canvasFor(W, H) {
  if (!topCanvas || topCanvas.width !== W || topCanvas.height !== H) {
    topCanvas = document.createElement('canvas'); topCanvas.width = W; topCanvas.height = H;
  }
  return topCanvas;
}

/** Where the object sits: straight ahead, above the skyline, a big disc never cut off at the top. */
export function objectPlace(R, sky, lensPx, hy, S, elevDeg) {
  const peak = Math.max(...R.layers[0].deg.filter((_, i) => Math.abs(R.az_deg[i]) <= 12));
  const rDeg = (sky.angular_deg || 0) / 2;
  let el = elevDeg ?? Math.max(peak + 5.5, 11);
  el = Math.max(el, peak + rDeg * 0.35 + 2);                    // a huge disc may set behind the ridge, a point never does
  const maxEl = (hy - 40 * S) / lensPx - rDeg * 0.15;           // keep the centre in frame
  return Math.min(el, Math.max(maxEl, peak + 1));
}

export async function drawLake(g, s, t, W, H) {
  const S = H / 1080, cam = cameraAt(s, t), sky = skyAt(s, t), flux = sky.flux_x ?? 0;
  const light = lightColour(sky), air = airAt(flux, light);
  const lens = (s.lens || LAKE_LENS) * S * cam.scale;
  const hy = Math.round(H * (HORIZON + cam.dy * 0.5));
  const R = s.ridges && s.ridges.layers && s.ridges.layers.length ? s.ridges : fallbackRidges();
  const cx = W / 2 + cam.dx * H;

  // 1) sky, stars, object, ridges on an offscreen canvas (the lake mirrors it)
  const tc = canvasFor(W, H), c = tc.getContext('2d');
  c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, W, H);
  drawAir(c, W, 0, hy, air);
  c.save(); c.beginPath(); c.rect(0, 0, W, hy); c.clip();
  drawStars(c, W, hy, t, clamp01(air.night * 1.15 - air.flood) * 0.5, cam);   // the competitor's night: a calm sky, few stars
  const seen = smooth((air.L + 15) / 2);
  const el = objectPlace(R, sky, lens, hy, S, s.elev_deg);
  const ox = cx, oy = hy - el * lens, r = Math.max(0.7 * S, (sky.angular_deg || 0) * lens / 2);
  if (seen > 0.01) {
    const glowK = seen * clamp01(0.25 + 0.17 * (air.L + 6)) * (sky.kind === 'black_hole' ? 0.7 : 1);
    drawGlow(c, ox, oy, r, light, glowK * (1 - 0.75 * air.stop), S);
    c.save(); c.globalAlpha *= seen;
    if (sky.kind === 'black_hole') {
      const shown = drawQuasar(c, ox, oy, (sky.angular_deg || 0) * lens / 2, t, S, W, H);   // the true horizon size, no minimum
      if (shown < 0.99) { c.globalAlpha *= 1 - shown; await drawObject(c, { ...sky, kind: 'star', temp_k: 14000 }, ox, oy, 0.8 * S, Math.min(flux, 30), t, S); }
    } else {
      await drawObject(c, sky, ox, oy, r, Math.min(flux, 30), t, S);
    }
    c.restore();
  }
  // ridges far -> near: silhouettes, the far ones melting into the horizon haze
  const nL = R.layers.length;
  const sil = mixc(mixc([3, 4, 7], [24, 32, 42], air.day * 0.9), [6, 10, 24], air.stop * 0.8);
  for (let li = 0; li < nL; li++) {
    const depth = nL === 1 ? 1 : 1 - li / (nL - 1);               // 1 far .. 0 near
    const col = mixc(sil, air.horizon, depth * (0.12 + 0.4 * air.day) + 0.04 * air.day);
    const par = 0.25 + 0.75 * (1 - depth);                         // near ridges move more as the camera drifts
    const shift = cam.dx * H * par, zoom = 1 + (cam.scale - 1) * (0.5 + 0.5 * par);
    c.fillStyle = rgba(col); c.beginPath(); c.moveTo(-10, hy + 2);
    for (let x = -10; x <= W + 10; x += 3) {
      const a = (x - W / 2 - shift) / (lens / cam.scale * zoom);
      c.lineTo(x, hy - ridgeAt(R, li, a) * lens / cam.scale * zoom);
    }
    c.lineTo(W + 10, hy + 2); c.closePath(); c.fill();
  }
  // a faint haze band on the water line (where the far shore meets the lake)
  const hb = c.createLinearGradient(0, hy - 26 * S, 0, hy);
  hb.addColorStop(0, rgba(air.horizon, 0)); hb.addColorStop(1, rgba(air.horizon, 0.18 + 0.12 * air.day));
  c.fillStyle = hb; c.fillRect(0, hy - 26 * S, W, 26 * S);
  c.restore();

  // 2) the picture above the water
  g.drawImage(tc, 0, 0, W, hy, 0, 0, W, hy);

  // 3) the lake: the same picture mirrored, in thin strips that sway a little (wider ripples nearer the camera)
  const depthPx = H - hy;
  for (let y = hy; y < H; y += 2) {
    const k = (y - hy) / depthPx;
    const amp = (0.4 + 5 * k * k) * S;
    const dx = Math.sin(y * 0.085 / S + t * 1.1) * amp + Math.sin(y * 0.027 / S - t * 0.6) * amp * 0.7;
    const src = Math.max(0, hy - (y - hy) - 2);
    g.drawImage(tc, 0, src, W, 2, dx, y, W, 2);
  }
  // water absorbs: the reflection darkens toward the camera; a very light cool tint
  const wd = g.createLinearGradient(0, hy, 0, H);
  wd.addColorStop(0, 'rgba(0,0,0,0.12)'); wd.addColorStop(0.35, 'rgba(0,0,0,0.38)'); wd.addColorStop(1, 'rgba(0,0,0,0.62)');
  g.fillStyle = wd; g.fillRect(0, hy, W, depthPx);
  g.fillStyle = rgba(mixc([10, 18, 30], air.horizon, 0.3), 0.08); g.fillRect(0, hy, W, depthPx);
  // the water line itself: one soft light seam
  g.fillStyle = rgba(air.horizon, 0.25 + 0.2 * air.day); g.fillRect(0, hy, W, Math.max(1, S));

  s._anchor = { x: ox, y: oy, r };
}
