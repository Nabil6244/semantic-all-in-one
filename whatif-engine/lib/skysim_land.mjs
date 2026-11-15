// Sky Sim landscape look (docs/skysim/PLAN.md 3.3.1): one held valley, the sky object above it, everything lit by that object.
// The light (sky.flux_x, sunlight at Earth = 1) drives the whole scene continuously, so a held step that brings the object closer
// changes the place in front of you with no cut:
//   night  -> stars, silhouettes              sky level rises with log(light)
//   day    -> blue sky, lit slopes, green forest, a mirror lake
//   scorch -> washed-out sky, browned slopes, the lake shrinking
//   burn   -> the forest glowing, embers rising, smoke, the lake bed dry and cracked
//   melt   -> the camera stops down (the sky darkens again so the object stays visible), rock turning to lava
// Places change the ground (lake_valley, desert, ocean, cracked_rock, ice, meadow, canyon). Plain 2D canvas, pure function of t.
import { skyAt, cameraAt, LENS, drawStars, drawStarDisc, drawGlobe, rng } from './skysim_sky.mjs';

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const lerp = (a, b, k) => a + (b - a) * k;
const mix = (c1, c2, k) => c1.map((v, i) => lerp(v, c2[i], clamp01(k)));
const rgb = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

// ---- places ------------------------------------------------------------------------------------------------------
//   rock: slope colour in daylight; water: a lake (it dries with heat); forest: trees on the lower slopes;
//   walls: how tall the valley sides rise (fraction of H); floor: where the ground meets the far ridges
const PLACES = {
  lake_valley: { rock: '#59606A', ground: '#3A3D3A', water: true, forest: true, walls: 0.42, floor: 0.66 },
  desert: { rock: '#9A7550', ground: '#B08A5E', water: false, forest: false, walls: 0.2, floor: 0.68 },
  ocean: { rock: '#4A525C', ground: '#2A3440', water: true, forest: false, walls: 0.05, floor: 0.6, sea: true },
  cracked_rock: { rock: '#5C5650', ground: '#4C4640', water: false, forest: false, walls: 0.3, floor: 0.67, cracks: true },
  ice: { rock: '#A9BCCF', ground: '#C8D6E2', water: true, forest: false, walls: 0.36, floor: 0.66, frozen: true },
  meadow: { rock: '#5E6B4E', ground: '#4E6A38', water: false, forest: true, walls: 0.16, floor: 0.68 },
  canyon: { rock: '#9A5A3A', ground: '#7A4A30', water: false, forest: false, walls: 0.55, floor: 0.7 },
};

// ---- the heat ladder from the light -------------------------------------------------------------------------------
export function heatOf(flux) {
  const L = Math.log10(Math.max(flux || 0, 1e-30));
  const raw = smooth((L + 4.5) / 4.5);                 // 0 at 3e-5 sunlight (a starry night), 1 at full daylight
  const stop = smooth((L - 1.5) / 3);                  // the camera stops down past ~30x sunlight
  return {
    L, raw, sky: raw * (1 - 0.72 * stop), stop,
    direct: smooth((L + 2.2) / 2.2),                   // slopes lit by the object itself
    scorch: smooth((L - 0.45) / 0.6), burn: smooth((L - 0.85) / 0.4), melt: smooth((L - 2.4) / 2),
    evap: smooth((L - 0.6) / 0.7),
  };
}

// ---- seeded terrain -----------------------------------------------------------------------------------------------
function noise1(seed) {
  const r = rng(seed), v = Array.from({ length: 257 }, () => r());
  return (x) => { const i = Math.floor(x) & 255, f = x - Math.floor(x), k = f * f * (3 - 2 * f); return lerp(v[i], v[i + 1], k); };
}
function fbm(n, x, oct = 5) { let a = 0.5, s = 0, f = 1; for (let o = 0; o < oct; o++) { s += a * n(x * f); a *= 0.5; f *= 2.03; } return s; }

let terrain = null;
function buildTerrain(W, H, place) {
  const key = `${W}x${H}:${place}`;
  if (terrain && terrain.key === key) return terrain;
  const P = PLACES[place] || PLACES.lake_valley, floor = H * P.floor;
  const layers = [0, 1, 2].map((li) => {
    const n = noise1(101 + li * 37), depth = [1, 0.6, 0.25][li];     // far, mid, near
    const wall = P.walls * H * [0.7, 0.95, 1.15][li], pts = [];
    for (let i = 0; i <= 160; i++) {
      const u = i / 160, side = Math.abs(u - 0.5) * 2;                 // 0 in the middle of the valley, 1 at the edges
      const shape = P.sea ? 0.02 : side ** (li === 2 ? 2.2 : 1.6);
      const rough = (fbm(n, u * (6 + li * 3)) - 0.5) * H * (P.sea ? 0.01 : 0.12 + 0.05 * li);
      const y = floor - wall * shape - H * 0.05 * (1 - li * 0.5) + rough * (0.4 + side) + (li === 2 ? H * 0.06 : 0);
      pts.push([u * W, li === 0 ? Math.min(y, floor - H * 0.02) : y]);
    }
    const path = new Path2D(); path.moveTo(0, H); pts.forEach(([x, y]) => path.lineTo(x, y)); path.lineTo(W, H); path.closePath();
    // trees on the lower slopes of the mid and near ridges
    let trees = null;
    if (P.forest && li > 0) {
      trees = new Path2D(); const r = rng(500 + li);
      for (let k = 0; k < (li === 1 ? 900 : 500); k++) {
        const u = r(), j = Math.round(u * 160), [x, y] = pts[j], side = Math.abs(u - 0.5) * 2;
        if (side < 0.25) continue;
        const yy = y + r() * H * 0.16 * (0.4 + side), h = H * (li === 1 ? 0.012 : 0.022) * (0.6 + r() * 0.8), w = h * 0.45;
        trees.moveTo(x, yy - h); trees.lineTo(x + w, yy); trees.lineTo(x - w, yy); trees.closePath();
      }
    }
    return { path, pts, depth, trees };
  });
  // lava / dry-mud cracks: random walks over the ground and the lower slopes
  const cracks = new Path2D(), r = rng(919);
  for (let k = 0; k < 120; k++) {
    let x = r() * W, y = floor + (r() ** 0.7) * (H - floor) * 1.05 - H * (r() < 0.35 ? 0.12 : 0), a = r() * Math.PI * 2;
    cracks.moveTo(x, y);
    for (let s = 0; s < 6 + r() * 10; s++) { a += (r() - 0.5) * 1.4; x += Math.cos(a) * H * 0.03; y += Math.sin(a) * H * 0.008; cracks.lineTo(x, y); }
  }
  terrain = { key, layers, cracks, floor, P };
  return terrain;
}

let scratch = null, flip = null;
const canvasOf = (c, W, H) => { if (!c) c = document.createElement('canvas'); if (c.width !== W || c.height !== H) { c.width = W; c.height = H; } return c; };

// ---- the sky object ----------------------------------------------------------------------------------------------
/** A black hole from a point (a quasar too far to resolve) to the full disc with its lensed arc. */
export function drawBlackHole(g, x, y, rh, flux, t, S) {
  const disc = smooth((rh - 3 * S) / (26 * S));       // 0 = a point of light, 1 = the whole structure
  if (disc < 1) drawStarDisc(g, x, y, Math.max(0.8 * S, rh * 0.5), flux * (1 - disc), t, 14000, S);
  if (disc <= 0.01) return;
  const Ro = rh * 3.4, tilt = 0.2, spin = t * 0.06;
  g.save(); g.globalAlpha *= disc; g.filter = `blur(${(1.5 * S).toFixed(1)}px)`;   // soft bands, not stripes
  const ring = (a0, a1) => {                           // the disc as bands of light, hottest inside, turning slowly
    for (let b = 0; b < 48; b++) {
      const k = b / 47, rr = lerp(rh * 1.25, Ro, k);
      const hot = [255, 246, 226], mid = [246, 160, 82], cold = [120, 46, 22];
      const c = k < 0.35 ? mix(hot, mid, k / 0.35) : mix(mid, cold, (k - 0.35) / 0.65);
      const wob = 0.75 + 0.25 * Math.sin(b * 2.3 + spin * (3 - k * 2));
      g.strokeStyle = rgb(c, (1 - k) ** 1.3 * 0.9 * wob); g.lineWidth = (Ro - rh) / 16;
      g.beginPath(); g.ellipse(x, y, rr, rr * tilt, 0, a0, a1); g.stroke();
    }
  };
  ring(Math.PI, Math.PI * 2);                         // the far half of the disc, behind the hole
  // the far side of the disc bent up over the top of the shadow by the hole's gravity
  for (let b = 0; b < 12; b++) {
    const k = b / 11, rr = rh * (1.18 + 0.55 * k);
    g.strokeStyle = rgb(mix([255, 238, 210], [210, 110, 50], k), (1 - k) ** 1.5 * 0.85); g.lineWidth = rh * 0.07;
    g.beginPath(); g.ellipse(x, y - rh * 0.05, rr, rr * 0.92, 0, Math.PI * 1.02, Math.PI * 1.98); g.stroke();
  }
  g.filter = 'none'; g.fillStyle = '#000'; g.beginPath(); g.arc(x, y, rh, 0, Math.PI * 2); g.fill();
  g.strokeStyle = 'rgba(255,236,200,0.8)'; g.lineWidth = Math.max(1, rh * 0.025);   // photon ring
  g.beginPath(); g.arc(x, y, rh * 1.03, 0, Math.PI * 2); g.stroke();
  g.filter = `blur(${(1.5 * S).toFixed(1)}px)`;
  ring(0, Math.PI);                                   // the near half, in front of the shadow
  g.restore();
}

export function drawObject(g, sky, x, y, r, flux, t, S) {
  if (sky.kind === 'black_hole') return drawBlackHole(g, x, y, r, flux, t, S);
  if (sky.kind === 'planet' || sky.kind === 'moon') return drawGlobe(g, sky.object, x, y, r, t, [0.5, -0.3, 0.8]);
  return drawStarDisc(g, x, y, r, flux, t, sky.temp_k || (sky.object === 'sun' ? 5772 : 6500), S);
}

// ---- the look ----------------------------------------------------------------------------------------------------
export async function drawLandscape(g, s, t, W, H) {
  const S = H / 1080, cam = cameraAt(s, t), sky = skyAt(s, t), flux = sky.flux_x ?? 0, h = heatOf(flux);
  const T = buildTerrain(W, H, s.place), P = T.P, floor = T.floor;
  const lens = (s.lens || LENS.landscape) * S, r = Math.max(0.6 * S, (sky.angular_deg || 0) * lens / 2) * cam.scale;
  const objX = W / 2 + cam.dx * H, objY = Math.max(H * (0.27 + cam.dy * 0.6), r * 1.35 + H * 0.05);   // a big disc sits lower, never cut off
  const hot = sky.kind === 'black_hole' ? [235, 225, 255] : [255, 240, 220];          // the light's own colour
  const fire = h.burn * (1 - h.melt * 0.4), lava = h.melt;

  // sky: night navy -> day blue -> washed white-gold -> stopped-down dark amber
  const topNight = [3, 5, 12], horNight = [8, 12, 26], topDay = [58, 104, 176], horDay = [170, 200, 232];
  const top = mix(mix(topNight, topDay, h.sky), [210, 170, 120], h.scorch * 0.5 * (1 - h.stop)), hor = mix(mix(horNight, horDay, h.sky), [250, 210, 160], h.scorch * 0.7);
  const topC = mix(top, [40, 14, 6], lava * 0.7), horC = mix(hor, [160, 60, 20], lava * 0.8);
  const sg = g.createLinearGradient(0, 0, 0, floor);
  sg.addColorStop(0, rgb(topC)); sg.addColorStop(1, rgb(horC));
  g.fillStyle = sg; g.fillRect(0, 0, W, H);
  drawStars(g, W, H * 0.75, t, clamp01(1 - h.raw * 1.6), cam);
  // the sky glows around the object once it lights the air
  if (h.raw > 0.05) {
    const glow = g.createRadialGradient(objX, objY, 0, objX, objY, H * (0.4 + 0.5 * h.raw));
    glow.addColorStop(0, rgb(hot, 0.35 * h.raw * (1 - h.stop * 0.6))); glow.addColorStop(1, rgb(hot, 0));
    g.fillStyle = glow; g.fillRect(0, 0, W, H);
  }
  // seen at all? the naked-eye limit is ~1e-13 of sunlight (magnitude ~6.5)
  const seen = smooth((h.L + 15) / 2);
  if (seen > 0.01) {
    if (h.L > -3) {                                    // a point as bright as a sun floods the air around it
      const bloom = g.createRadialGradient(objX, objY, 0, objX, objY, H * (0.04 + 0.22 * smooth((h.L + 3) / 3.5)));
      bloom.addColorStop(0, rgb(hot, 0.85 * smooth((h.L + 3) / 3) * (1 - h.melt))); bloom.addColorStop(0.25, rgb(hot, 0.25 * smooth((h.L + 3) / 3) * (1 - h.melt))); bloom.addColorStop(1, rgb(hot, 0));
      g.fillStyle = bloom; g.fillRect(0, 0, W, H);
    }
    g.save(); g.globalAlpha *= seen; drawObject(g, sky, objX, objY, r, Math.min(flux, 30), t, S); g.restore();
  }

  // ridges: far to near, each lit from the object, browned by heat, glowing at the end
  const sc = canvasOf(scratch, W, H); scratch = sc; const c2 = sc.getContext('2d');
  const rockDay = hex(P.rock), rockNight = [14, 18, 30];
  T.layers.forEach((L, li) => {
    c2.setTransform(1, 0, 0, 1, 0, 0); c2.clearRect(0, 0, W, H);
    const par = 1 + (cam.scale - 1) * (0.4 + 0.3 * li);                                 // near ridges move more: parallax
    c2.setTransform(par, 0, 0, par, (W - W * par) / 2 + cam.dx * H * li * 0.3, (H - H * par) / 2 + cam.dy * H * 0.5);
    let base = mix(rockNight, rockDay, h.sky * 0.85 + 0.15 * h.direct);
    base = mix(base, [120, 82, 52], h.scorch * 0.6); base = mix(base, [20, 12, 10], lava * 0.85);
    base = mix(base, horC, L.depth * 0.45 * (0.3 + h.sky));                                // haze on far ridges
    c2.fillStyle = rgb(base); c2.fill(L.path);
    c2.globalCompositeOperation = 'source-atop';
    if (L.trees) {                                                                         // forest: green -> brown -> burning -> gone
      const leaf = mix(mix([4, 6, 8], [36, 62, 40], h.sky), [70, 50, 30], h.scorch);
      c2.fillStyle = rgb(leaf, 1 - lava); c2.fill(L.trees);
      if (fire > 0.01) {
        const flick = 0.75 + 0.25 * Math.sin(t * 9 + li) * Math.sin(t * 5.3);
        c2.fillStyle = rgb([255, 120, 30], fire * flick); c2.shadowColor = 'rgba(255,110,20,0.9)'; c2.shadowBlur = 10 * S; c2.fill(L.trees); c2.shadowBlur = 0;
      }
    }
    const lit = c2.createRadialGradient(objX, objY, 0, objX, objY, H * 1.1);             // direct light on the faces towards it
    lit.addColorStop(0, rgb(mix(hot, [255, 150, 70], h.scorch), 0.5 * h.direct * (1 - L.depth * 0.4)));
    lit.addColorStop(0.6, rgb(hot, 0.12 * h.direct)); lit.addColorStop(1, rgb(hot, 0));
    c2.fillStyle = lit; c2.fillRect(0, 0, W, H);
    const shade = c2.createLinearGradient(0, floor - P.walls * H, 0, H);                  // slopes darken downwards
    shade.addColorStop(0, 'rgba(0,0,0,0)'); shade.addColorStop(1, `rgba(0,0,0,${0.45 - 0.2 * L.depth})`);
    c2.fillStyle = shade; c2.fillRect(0, 0, W, H);
    if (lava > 0.01 && li > 0) {                                                           // rock turning to lava
      c2.strokeStyle = rgb([255, 110, 30], lava * (0.7 + 0.3 * Math.sin(t * 2 + li))); c2.lineWidth = 2.5 * S * (1 + li);
      c2.shadowColor = 'rgba(255,90,20,1)'; c2.shadowBlur = 14 * S; c2.stroke(T.cracks); c2.shadowBlur = 0;
      const glowUp = c2.createLinearGradient(0, H, 0, floor - P.walls * H);
      glowUp.addColorStop(0, rgb([255, 90, 20], 0.55 * lava)); glowUp.addColorStop(1, rgb([255, 90, 20], 0));
      c2.fillStyle = glowUp; c2.fillRect(0, 0, W, H);
    }
    c2.globalCompositeOperation = 'source-over'; c2.setTransform(1, 0, 0, 1, 0, 0);
    if (li === 1) {
      // before the near shore: the lake (the scene above, mirrored and rippled), drying into cracked ground with heat
      g.drawImage(sc, 0, 0);
      drawGround(g, W, H, s, t, T, h, objX, S, horC);
      return;
    }
    g.drawImage(sc, 0, 0);
  });

  // smoke and embers while it burns
  if (fire > 0.01) {
    const sm = g.createLinearGradient(0, 0, 0, H);
    sm.addColorStop(0, rgb([60, 40, 32], 0.0)); sm.addColorStop(0.5, rgb([90, 60, 40], 0.35 * fire)); sm.addColorStop(1, rgb([40, 24, 16], 0.3 * fire));
    g.fillStyle = sm; g.fillRect(0, 0, W, H);
    const er = rng(4242);
    for (let i = 0; i < 260; i++) {
      const x0 = er() * W, sp = (0.05 + er() * 0.12) * H, ph = er() * 10, range = H * (0.4 + er() * 0.4);
      const y = H * 0.95 - ((t * sp + ph * range) % range), x = x0 + Math.sin(t * 1.3 + ph) * 18 * S;
      const a = fire * (0.4 + 0.6 * er()) * clamp01((y - (H * 0.95 - range)) / (range * 0.3));
      g.fillStyle = rgb([255, 150 + 60 * er(), 60], a); g.beginPath(); g.arc(x, y, (1 + er() * 1.8) * S, 0, Math.PI * 2); g.fill();
    }
  }
  s._anchor = { x: objX, y: objY, r };
}

function drawGround(g, W, H, s, t, T, h, objX, S, horC) {
  const P = T.P, floor = T.floor, water = P.water ? 1 - h.evap : 0;
  let groundC = mix([12, 14, 20], hex(P.ground), h.sky * 0.9 + 0.1 * h.direct);
  if (P.water) groundC = mix(groundC, mix([168, 146, 118], [150, 120, 92], h.scorch), h.evap * (1 - h.melt));   // the dry lake bed
  groundC = mix(groundC, [150, 56, 20], h.melt * 0.9);   // basalt glowing from below
  g.fillStyle = rgb(groundC); g.fillRect(0, floor, W, H - floor);
  if (water > 0.01) {
    // a mirror: the frame above the waterline flipped, darkened, broken by moving ripples
    const fl = canvasOf(flip, W, H); flip = fl; const f2 = fl.getContext('2d');
    f2.setTransform(1, 0, 0, 1, 0, 0); f2.clearRect(0, 0, W, H); f2.drawImage(g.canvas, 0, 0);
    const rows = Math.ceil((H - floor) / (3 * S));
    g.save(); g.globalAlpha = water;
    for (let i = 0; i < rows; i++) {
      const y = floor + i * 3 * S, src = floor - (y - floor) - 3 * S;
      if (src < 0) break;
      const amp = P.frozen ? 0 : (2 + i * 0.25) * S, dx = Math.sin(i * 0.7 + t * 1.6) * amp + Math.sin(i * 0.23 - t * 0.9) * amp * 0.6;
      g.drawImage(fl, 0, src, W, 3 * S, dx, y, W, 3 * S + 0.5);
    }
    const dark = g.createLinearGradient(0, floor, 0, H);
    dark.addColorStop(0, rgb(horC, 0.15)); dark.addColorStop(1, 'rgba(0,0,0,0.5)');
    g.fillStyle = dark; g.fillRect(0, floor, W, H - floor);
    g.restore();
  }
  const dry = P.cracks ? 1 : P.water ? h.evap : h.scorch;
  if (dry > 0.01) {                                                                    // dried mud / cracked rock, glowing once it melts
    g.save(); g.beginPath(); g.rect(0, floor, W, H - floor); g.clip();
    g.strokeStyle = h.melt > 0.05 ? rgb([255, 110, 30], h.melt) : `rgba(0,0,0,${0.55 * dry})`;
    g.lineWidth = (1.5 + 2.5 * h.melt) * S;
    if (h.melt > 0.05) { g.shadowColor = 'rgba(255,90,20,1)'; g.shadowBlur = 12 * S; }
    g.globalAlpha = dry; g.stroke(T.cracks); g.restore();
  }
}
