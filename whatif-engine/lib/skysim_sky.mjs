// Sky Sim shot kind `sky` (docs/skysim/PLAN.md): one held place, the sky object drawn at its true angular size.
//   { kind: 'sky', look: 'space' | 'moon_surface' | ..., from, camera, sky: { object, kind, angular_deg, flux_x, stage }, sky_from? }
// A held step (sky_from) moves from the last step's sky to this one's during the step: sizes and light ease in log space.
// Pure function of t, plain 2D canvas (planet globes are textured spheres drawn per pixel), so stills and video agree.
// Each look draws, then leaves s._anchor = { x, y, r } (the sky object on screen) for sk_scalering / sk_leader.

import { drawLandscape } from './skysim_land.mjs';

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const lerp = (a, b, k) => a + (b - a) * k;
const logLerp = (a, b, k) => (a > 0 && b > 0 ? Math.exp(lerp(Math.log(a), Math.log(b), k)) : lerp(a || 0, b || 0, k));

// lens per look, px per degree at 1080p: space is a telephoto (the Sun from Mercury ~1.4° fills a good disc),
// a moon's sky is wide (Mars from Phobos, 42°, about a quarter of the frame)
export const LENS = { space: 142, moon_surface: 13, landscape: 30, lake: 24, city: 40, journey: 60, helmet: 40 };
const TEXTURES = { sun: '2k_sun.jpg', mercury: '2k_mercury.jpg', venus: '2k_venus_atmosphere.jpg', earth: 'earth_bluemarble_5400.jpg',
  moon: 'moon_lroc_4096.jpg', mars: '2k_mars.jpg', jupiter: '2k_jupiter.jpg', saturn: '2k_saturn.jpg', uranus: '2k_uranus.jpg', neptune: '2k_neptune.jpg' };
// the ground under the viewer in the space look: [far, near] colours of the planet's horizon
const GROUND = { mercury: ['#5E5853', '#26231F'], venus: ['#8A5A24', '#2E1C0A'], earth: ['#2B3A4A', '#0C1218'], mars: ['#7A3E22', '#2A140A'],
  jupiter: ['#8C7458', '#2E2418'], saturn: ['#9C8B66', '#352D1E'], uranus: ['#5E8790', '#1B2A2E'], neptune: ['#2E4C8C', '#0C1630'] };

/** The sky at t: sky_from eases into sky over the first 70 % of the step. */
export function skyAt(s, t) {
  const to = s.sky || {}, from = s.sky_from;
  if (!from) return to;
  const k = smooth((t - s.start) / Math.max(0.5, (s.end - s.start) * 0.7));
  return { ...to, angular_deg: logLerp(from.angular_deg, to.angular_deg, k), flux_x: logLerp(from.flux_x, to.flux_x, k), k };
}

/** Camera: a scale and an offset (fractions of H) over the step; never fully still. */
export function cameraAt(s, t) {
  const k = clamp01((t - s.start) / Math.max(0.5, s.end - s.start)), e = smooth(k);
  switch (s.camera) {
    case 'push': return { scale: lerp(1, 1.14, e), dx: 0, dy: 0 };
    case 'pullback': return { scale: lerp(1.12, 1, e), dx: 0, dy: 0 };
    case 'rise': return { scale: 1.02, dx: 0, dy: lerp(0.05, -0.02, e) };
    case 'orbit': return { scale: 1.03, dx: lerp(-0.03, 0.03, e), dy: 0 };
    case 'static': return { scale: 1, dx: 0, dy: 0 };
    default: return { scale: lerp(1, 1.045, k), dx: lerp(0.008, -0.008, k), dy: 0 };   // drift
  }
}

// ---- seeded star field (same every frame and every render part) ------------------------------------------------
export function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
let starCache = null;
function stars(W, H) {
  if (starCache && starCache.W === W) return starCache.list;
  const r = rng(9001), list = [];
  for (let i = 0; i < 2400; i++) { const b = r() ** 3.2; list.push({ x: r() * W, y: r() * H, b, rad: 0.5 + 1.6 * b, ph: r() * 6.28, f: 0.6 + r() * 1.8, warm: r() }); }
  starCache = { W, list };
  return list;
}
export function drawStars(g, W, H, t, alpha, cam) {
  if (alpha <= 0.01) return;
  const k = H / 1080;
  g.save();
  for (const st of stars(W, H)) {
    const tw = 0.82 + 0.18 * Math.sin(t * st.f + st.ph);
    const a = alpha * (0.2 + 0.8 * st.b) * tw;
    if (a < 0.02) continue;
    const x = (st.x - W / 2) * (1 + (cam.scale - 1) * 0.3) + W / 2 + cam.dx * H * 0.3, y = st.y + cam.dy * H * 0.3;
    g.fillStyle = st.warm > 0.8 ? `rgba(255,228,200,${a})` : st.warm < 0.2 ? `rgba(200,215,255,${a})` : `rgba(240,242,255,${a})`;
    g.beginPath(); g.arc(x, y, st.rad * k, 0, Math.PI * 2); g.fill();
  }
  g.restore();
}

// ---- the Sun / a star as a bright disc ---------------------------------------------------------------------------
function starColour(tempK = 5772) {
  if (tempK < 3500) return [255, 170, 110];
  if (tempK < 5000) return [255, 205, 150];
  if (tempK < 6500) return [255, 244, 228];
  if (tempK < 9000) return [235, 240, 255];
  return [200, 218, 255];
}
export function drawStarDisc(g, x, y, r, flux, t, temp, S) {
  const [cr, cg, cb] = starColour(temp);
  const glowK = clamp01(0.35 + 0.18 * Math.log10(1 + flux * 30));
  // wide soft glare, then a tighter halo, then the disc
  const glare = Math.max(r * 4.2, 60 * S) * (0.7 + glowK);
  let grd = g.createRadialGradient(x, y, r * 0.6, x, y, glare);
  grd.addColorStop(0, `rgba(${cr},${cg},${cb},${0.35 * glowK})`); grd.addColorStop(0.35, `rgba(${cr},${cg},${cb},${0.08 * glowK})`); grd.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grd; g.beginPath(); g.arc(x, y, glare, 0, Math.PI * 2); g.fill();
  const halo = r * 1.6 + 6 * S;
  grd = g.createRadialGradient(x, y, r * 0.9, x, y, halo);
  grd.addColorStop(0, `rgba(255,255,255,${0.8 * glowK})`); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.beginPath(); g.arc(x, y, halo, 0, Math.PI * 2); g.fill();
  // slow corona shimmer: faint rays turning, so a held Sun is never frozen
  g.save(); g.globalCompositeOperation = 'screen';
  for (let i = 0; i < 8; i++) {
    const a = i * Math.PI / 4 + t * 0.03 + Math.sin(t * 0.4 + i) * 0.05, len = (r * 1.4 + 14 * S) * (0.8 + 0.25 * Math.sin(t * 0.7 + i * 1.7));
    const lg = g.createLinearGradient(x, y, x + Math.cos(a) * len, y + Math.sin(a) * len);
    lg.addColorStop(0, `rgba(255,250,240,${0.10 * glowK})`); lg.addColorStop(1, 'rgba(255,250,240,0)');
    g.strokeStyle = lg; g.lineWidth = Math.max(1, r * 0.18); g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); g.stroke();
  }
  // a point-like star gets thin diffraction spikes
  if (r < 6 * S) {
    for (const a of [0, Math.PI / 2]) {
      const len = 26 * S * (0.6 + glowK);
      for (const sgn of [1, -1]) {
        const lg = g.createLinearGradient(x, y, x + Math.cos(a) * len * sgn, y + Math.sin(a) * len * sgn);
        lg.addColorStop(0, 'rgba(255,255,255,0.7)'); lg.addColorStop(1, 'rgba(255,255,255,0)');
        g.strokeStyle = lg; g.lineWidth = 1.2 * S; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len * sgn, y + Math.sin(a) * len * sgn); g.stroke();
      }
    }
  }
  g.restore();
  grd = g.createRadialGradient(x, y, 0, x, y, Math.max(r, 1));
  grd.addColorStop(0, '#FFFFFF'); grd.addColorStop(0.82, `rgb(${Math.min(255, cr + 10)},${cg},${cb})`); grd.addColorStop(1, `rgba(${cr},${cg - 20},${cb - 40},0.85)`);
  g.fillStyle = grd; g.beginPath(); g.arc(x, y, Math.max(r, 1.1 * S), 0, Math.PI * 2); g.fill();
}

// ---- a textured planet as a 2D sphere ----------------------------------------------------------------------------
const texCache = new Map();
function loadTex(name) {
  if (!texCache.has(name)) {
    texCache.set(name, new Promise((ok, fail) => {
      const im = new Image();
      im.onload = () => {
        const w = Math.min(im.width, 2048), h = Math.round(w * im.height / im.width);
        const c = document.createElement('canvas'); c.width = w; c.height = h; const cg = c.getContext('2d');
        cg.drawImage(im, 0, 0, w, h); ok({ w, h, px: cg.getImageData(0, 0, w, h).data });
      };
      im.onerror = () => fail(new Error(`texture ${name} not found`));
      im.src = `/textures/${encodeURIComponent(name)}`;
    }));
  }
  return texCache.get(name);
}
let globeCanvas = null;              // made on first use (the module also loads in plain node for tests)
/** Draw `object`'s globe of radius r at (x, y), lit from direction (lx, ly, lz) (towards the light), turning slowly. */
export async function drawGlobe(g, object, x, y, r, t, light = [-0.6, -0.2, 0.77], rimColour = null) {
  const name = TEXTURES[object];
  if (!name || r < 1.5) {
    g.fillStyle = '#C9CED6'; g.beginPath(); g.arc(x, y, Math.max(r, 1.2), 0, Math.PI * 2); g.fill(); return;
  }
  const tex = await loadTex(name);
  const n = Math.max(8, Math.min(Math.round(r * 2), 900)), R = n / 2;
  if (!globeCanvas) globeCanvas = document.createElement('canvas');
  if (globeCanvas.width !== n) { globeCanvas.width = n; globeCanvas.height = n; }
  const cg = globeCanvas.getContext('2d'), img = cg.createImageData(n, n), d = img.data;
  const ln = Math.hypot(...light), [lx, ly, lz] = light.map((v) => v / ln);
  const spin = t * 0.004;                                   // a slow turn: a held globe is never a frozen picture
  for (let j = 0; j < n; j++) {
    const ny = (j + 0.5 - R) / R;
    for (let i = 0; i < n; i++) {
      const nx = (i + 0.5 - R) / R, rr = nx * nx + ny * ny;
      if (rr > 1) continue;
      const nz = Math.sqrt(1 - rr);
      const lon = Math.atan2(nx, nz) / (2 * Math.PI) + 0.5 + spin, lat = Math.asin(ny) / Math.PI + 0.5;
      const u = ((lon % 1) + 1) % 1, tx = Math.min(tex.w - 1, (u * tex.w) | 0), ty = Math.min(tex.h - 1, (lat * tex.h) | 0), o = (ty * tex.w + tx) * 4;
      const dot = nx * lx + ny * ly + nz * lz, lit = 0.025 + 0.975 * smooth((dot + 0.08) / 0.5) * (0.55 + 0.45 * Math.max(0, dot));
      const limb = 0.75 + 0.25 * nz, edge = clamp01((1 - Math.sqrt(rr)) * R * 1.2), k = 4 * (j * n + i);
      d[k] = tex.px[o] * lit * limb; d[k + 1] = tex.px[o + 1] * lit * limb; d[k + 2] = tex.px[o + 2] * lit * limb; d[k + 3] = 255 * edge;
    }
  }
  cg.putImageData(img, 0, 0);
  g.drawImage(globeCanvas, x - r, y - r, r * 2, r * 2);
  if (rimColour) {                                          // a thin atmosphere rim on the lit side
    g.save(); g.globalCompositeOperation = 'screen';
    const grd = g.createRadialGradient(x, y, r * 0.96, x, y, r * 1.06);
    grd.addColorStop(0, 'rgba(0,0,0,0)'); grd.addColorStop(0.4, rimColour); grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd; g.beginPath(); g.arc(x, y, r * 1.06, 0, Math.PI * 2); g.fill(); g.restore();
  }
}

// ---- looks -------------------------------------------------------------------------------------------------------
function drawGround(g, W, H, cols, cam, t, S, sunX) {
  const y0 = H * (0.8 + cam.dy * 0.5), bend = H * 0.05;
  const grd = g.createLinearGradient(0, y0 - bend, 0, H);
  grd.addColorStop(0, cols[0]); grd.addColorStop(1, cols[1]);
  g.save(); g.fillStyle = grd;
  g.beginPath(); g.moveTo(0, y0 + bend); g.quadraticCurveTo(W / 2, y0 - bend, W, y0 + bend); g.lineTo(W, H); g.lineTo(0, H); g.closePath(); g.fill();
  // the horizon catches the light under the Sun
  const rim = g.createRadialGradient(sunX, y0, 0, sunX, y0, W * 0.6);
  rim.addColorStop(0, 'rgba(255,240,220,0.35)'); rim.addColorStop(1, 'rgba(255,240,220,0)');
  g.strokeStyle = rim; g.lineWidth = 2 * S; g.beginPath(); g.moveTo(0, y0 + bend); g.quadraticCurveTo(W / 2, y0 - bend, W, y0 + bend); g.stroke();
  g.restore();
}

function drawSpace(g, s, t, W, H) {
  const S = H / 1080, cam = cameraAt(s, t), sky = skyAt(s, t), lens = (s.lens || LENS.space) * S;
  g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
  const flux = sky.flux_x ?? 1;
  drawStars(g, W, H, t, clamp01(0.95 - 0.22 * Math.log10(1 + flux * 4)), cam);
  const x = W / 2 + cam.dx * H, y = H * (0.44 + cam.dy), r = Math.max(0.5, (sky.angular_deg || 0.5) * lens / 2) * cam.scale;
  if (sky.kind === 'planet' || sky.kind === 'moon') return drawGlobe(g, sky.object, x, y, r, t).then(() => { s._anchor = { x, y, r }; });
  drawStarDisc(g, x, y, r, flux, t, sky.temp_k, S);
  if (s.from && GROUND[s.from]) drawGround(g, W, H, GROUND[s.from], cam, t, S, x);
  s._anchor = { x, y, r };
  return null;
}

let craterCache = null;
function drawMoonGround(g, W, H, cam, t, S) {
  const y0 = H * (0.74 + cam.dy * 0.6);
  const grd = g.createLinearGradient(0, y0, 0, H);
  grd.addColorStop(0, '#4A4744'); grd.addColorStop(0.25, '#2C2A28'); grd.addColorStop(1, '#141312');
  g.fillStyle = grd; g.beginPath(); g.moveTo(0, y0 + H * 0.02); g.quadraticCurveTo(W / 2, y0 - H * 0.02, W, y0 + H * 0.02); g.lineTo(W, H); g.lineTo(0, H); g.fill();
  if (!craterCache || craterCache.W !== W) {
    const r = rng(77), list = [];
    for (let i = 0; i < 70; i++) { const depth = r() ** 1.5; list.push({ x: r() * W, d: depth, w: (20 + 220 * r() * (0.3 + depth)) }); }
    craterCache = { W, list: list.sort((a, b) => a.d - b.d) };
  }
  const drift = (t * 4 * S) % W;                            // the ground slides a little: the camera is never locked off
  for (const c of craterCache.list) {
    const yy = y0 + (H - y0) * (0.05 + 0.95 * c.d), w = c.w * S * (0.4 + c.d), h = w * (0.12 + 0.2 * c.d);
    const xx = ((c.x + drift * (0.3 + c.d)) % (W + w)) - w / 2;
    g.fillStyle = `rgba(0,0,0,${0.25 + 0.3 * c.d})`; g.beginPath(); g.ellipse(xx, yy, w / 2, h / 2, 0, 0, Math.PI * 2); g.fill();
    g.strokeStyle = `rgba(160,150,140,${0.12 + 0.2 * c.d})`; g.lineWidth = 1.5 * S; g.beginPath(); g.ellipse(xx, yy + h * 0.08, w / 2, h / 2, 0, 0.1 * Math.PI, 0.9 * Math.PI); g.stroke();
  }
}

async function drawMoonSurface(g, s, t, W, H) {
  const S = H / 1080, cam = cameraAt(s, t), sky = skyAt(s, t), lens = (s.lens || LENS.moon_surface) * S;
  g.fillStyle = '#000'; g.fillRect(0, 0, W, H);
  drawStars(g, W, H, t, 0.9, cam);
  const r = Math.max(0.8, (sky.angular_deg || 1) * lens / 2) * cam.scale, x = W / 2 + cam.dx * H, y = H * (0.74 + cam.dy) - Math.min(r * 0.55, H * 0.32);
  await drawGlobe(g, sky.object, x, y, r, t, [0.75, -0.25, 0.6]);
  drawMoonGround(g, W, H, cam, t, S);
  s._anchor = { x, y, r };
}

/** Draw a `sky` shot at t. Unbuilt looks fall back to the space look (logged once by the caller's warn). */
export async function drawSky(g, s, t, W, H) {
  if (s.look === 'moon_surface') return drawMoonSurface(g, s, t, W, H);
  if (s.look === 'landscape') return drawLandscape(g, s, t, W, H);
  if (s.look === 'lake') { const { drawLake } = await import('./skysim_lake.mjs'); return drawLake(g, s, t, W, H); }
  return drawSpace(g, s, t, W, H);
}
export const BUILT_LOOKS = ['space', 'moon_surface', 'landscape', 'lake'];
