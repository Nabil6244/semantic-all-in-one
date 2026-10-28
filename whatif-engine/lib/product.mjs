// PRODUCT shots: a studio-lit hero object in the dark, drawn as a product launch film does -- glossy metal that reflects soft-boxes, a
// camera that glides (macro, low monolith angle, floating hero, flat profile), a coloured glow behind the object and a bloom on the
// bright parts. Built from code (no model file), so nothing is downloaded. Opt-in: only a shot of kind "product" uses this.
//   { id, start, end, kind: "product", object: "phone" | "iphone" | "galaxy" | "chip", phone: "<id>" | {spec} (lib/phone_models.mjs, when present),
//     move: "island" | "monolith" | "hero" | "profile" | "orbit" | "screen" | "edge" | "flip" (back turns to front) | "rise" (up from below)
//           | "port" (macro on the bottom edge) | "buttons" (macro on the side keys) | "chip" | "chip_macro"
//           | "reveal" (back to camera, a 180-degree turn to the front at turn_at -- fraction of the shot, default 0.45, ~0.8 s eased --
//             while the camera pulls back the whole shot, phone centred),
//     backdrop: "stars" (default) | "wash" (full-frame coloured light; wash_style "swoosh" red/orange ribbon | "aurora" purple/blue)
//               | "horizon" (dark land, warm city lights, stars) | "studio" (dark cyclorama, floor, contact shadow; floor_y -1.3)
//               | "charcoal" (dark charcoal-grey soft gradient studio: lighter centre, vignette, no stars),
//     wash: "#ff4a1f", wash2: "#ff9a3c" (second backdrop colour), wash_at: [dx, dy], wash_gain: 1, tone: "#8fa3b5",
//     screen: { time: "09:41", date: "Tue 27 Oct", clock: false (no time/date), wallpaper: "liquid" (default, animated glossy ripples)
//               | "wave" (flowing S-shaped colour bands) | "clock" (the old static clock screen), tint: "#hex" (default: the phone's back
//               colour), power_on: seconds into the shot the screen switches on (black glass before, 0.5 s fade up; "reveal" default:
//               the moment the front faces the camera, otherwise on from the start) },
//     fog: true | { color: "#cfd8e6", height: 0.25 } (dry-ice smoke rolling along the bottom of the frame, in front of and behind the phone),
//     streak: true (a hard-edged diagonal window-light band sweeping right to left across the back),
//     glow: true (a soft halo in the screen's tint on the backdrop behind the phone while the screen is on),
//     dim_in: seconds, dim_out: seconds (key/rim/env lights ease from/to ~15% over the first/last N seconds),
//     turn_at: 0.45 ("reveal"), bloom: 0.5 (capped on light finishes and macro moves), sweep: true | false | speed (a soft-box gliding across the metal),
//     cam_side: "left" | "right" (left mirrors the move), frame_side: "left" | "right" (object sits in that half; frame_shift 0.2), color: phone colour option name,
//     samples: 8 (sub-frames per frame: motion blur over a 180-degree shutter + subpixel AA; env PRODUCT_SAMPLES overrides), fps: 30, shutter: 0.5 }
// A pure function of the time inside the shot, like every other shot (sub-frames, sweep and sparks included), so parallel parts match.

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const ease = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
// camera travel inside one shot: near-constant speed (a hard cut already starts the next shot, so no slow start from rest) and a shorter move
// (the reference trailers move about a tenth as far per frame as a full smoothstep). shot.travel 0..1 scales the move (default `tr`); 1 = as authored.
const camE = (k, tr = 0.5, shot = null) => { const kk = clamp01(k), lin = 0.75 * kk + 0.25 * ease(kk), t = shot && shot.travel != null ? shot.travel : tr; return 0.5 + (lin - 0.5) * t; };
const linE = (k) => { const kk = clamp01(k); return 0.75 * kk + 0.25 * ease(kk); };
const SEMANTIC_MOVES = new Set(['flip', 'rise', 'reveal']);   // these end on a pose the shot needs: full travel, constant speed
const lerp = (a, b, k) => a + (b - a) * k;

export const PRODUCT_OBJECTS = ['phone', 'iphone', 'galaxy', 'chip'];
export const PRODUCT_MOVES = ['island', 'monolith', 'hero', 'profile', 'orbit', 'screen', 'edge', 'flip', 'rise', 'port', 'buttons', 'chip', 'chip_macro', 'reveal'];
export const PRODUCT_BACKDROPS = ['stars', 'wash', 'horizon', 'studio', 'charcoal'];
const seeded = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

// a rounded rectangle as a three.js Shape, centred on the origin
function roundedRect(THREE, w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}
function slab(THREE, w, h, r, depth, bevel, mat) {
  const geo = new THREE.ExtrudeGeometry(roundedRect(THREE, w, h, r), { depth: Math.max(0.0005, depth - 2 * bevel), bevelEnabled: bevel > 0,
    bevelThickness: bevel, bevelSize: bevel, bevelSegments: 5, curveSegments: 28 });
  geo.translate(0, 0, -(depth - 2 * bevel) / 2);
  return new THREE.Mesh(geo, mat);
}

// the studio the metal reflects: a dim gradient room, a long soft-box overhead, cool and warm strips, a back rim card, a round hot spot, and
// (sweep) a tall card gliding across the front, so highlights travel over the frame. Re-baked per frame only when it sweeps.
function studioEnvironment(THREE, renderer, shot) {
  const env = new THREE.Scene();
  const room = new THREE.SphereGeometry(40, 32, 16), col = [], pa = room.attributes.position;
  for (let i = 0; i < pa.count; i++) { const y = pa.getY(i) / 40, v = 0.004 + 0.05 * Math.max(0, y) ** 1.5; col.push(v, v * 1.02, v * 1.08); }
  room.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  env.add(new THREE.Mesh(room, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.BackSide })));
  const panel = (w, h, colour, strength, pos, look, circle) => {
    const m = new THREE.Mesh(circle ? new THREE.CircleGeometry(w, 32) : new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color(colour).multiplyScalar(strength), side: THREE.DoubleSide }));
    m.position.set(...pos); m.lookAt(...look); env.add(m); return m;
  };
  panel(14, 2.2, '#ffffff', 5.0, [0, 7, 1], [0, 0, 0]);          // overhead strip
  panel(6, 3.5, '#f4f6ff', 1.6, [-2, 4, 7], [0, 0, 0]);           // big soft key, front-top
  panel(2.0, 12, '#bcd6ff', 3.2, [-8, 1, 2], [0, 0, 0]);          // cool side strip
  panel(1.4, 9, '#ffd9b0', 2.0, [8, 0.5, -3], [0, 0, 0]);         // warm edge strip behind
  panel(0.5, 10, '#ffffff', 4.0, [-3, 0, -8], [0, 0, 0]);         // back rim strips
  panel(0.5, 10, '#ffffff', 3.0, [3.5, 0, -8], [0, 0, 0]);
  panel(0.9, 0, '#ffffff', 9.0, [5, 5, 5], [0, 0, 0], true);      // a round hot spot
  panel(10, 1.0, '#ffffff', 1.4, [0, -6, 3], [0, 0, 0]);          // faint floor bounce
  if (shot.wash) panel(3, 8, shot.wash, 1.2, [6, -1, -6], [0, 0, 0]);   // the wash colour picked up on the edges
  const sweep = shot.sweep === false ? null : panel(1.1, 14, '#ffffff', 6.0, [0, 0, 8], [0, 0, 0]);
  const pm = new THREE.PMREMGenerator(renderer);
  let rt = pm.fromScene(env, 0.02), last = null;
  const speed = typeof shot.sweep === 'number' ? shot.sweep : 0.35;
  return {
    get texture() { return rt.texture; },
    // the sweep card at time t: returns the new texture when it changed (the caller swaps it on the materials)
    update(t) {
      if (!sweep || last === t) return null; last = t;
      const x = Math.sin(t * speed + 0.6) * 9; sweep.position.set(x, 1, 8 - Math.abs(x) * 0.25); sweep.lookAt(0, 0, 0);
      const old = rt; rt = pm.fromScene(env, 0.02); const prev = old.texture; old.dispose(); return { from: prev, to: rt.texture };
    },
  };
}

// the backdrop as one camera-facing plate behind everything (inside the star sphere): painted once, drifting a little in time
function backdropCanvas(THREE, shot, W, H) {
  const kind = shot.backdrop; if (!kind || kind === 'stars') return null;
  const s = Math.min(1, 2048 / Math.max(W, H)), cw = Math.round(W * s), ch = Math.round(H * s);
  const c = document.createElement('canvas'); c.width = cw; c.height = ch; const g = c.getContext('2d'), r = seeded(shot.seed ?? 23);
  const u = Math.min(cw, ch) / 1080;
  if (kind === 'wash') {
    const aurora = shot.wash_style === 'aurora';
    const c1 = new THREE.Color(shot.wash || (aurora ? '#7b3cff' : '#ff2a12')), c2 = new THREE.Color(shot.wash2 || (aurora ? '#2f7bff' : '#ff9a3c'));
    const css = (col, a, m = 1) => `rgba(${Math.min(255, col.r * 255 * m) | 0},${Math.min(255, col.g * 255 * m) | 0},${Math.min(255, col.b * 255 * m) | 0},${a})`;
    g.fillStyle = '#020204'; g.fillRect(0, 0, cw, ch); g.globalCompositeOperation = 'lighter';
    if (aurora) {   // curtains: vertical streaks whose tops ride slow waves, purple fading to blue, a soft haze beneath
      g.filter = `blur(${10 * u}px)`;
      for (let i = 0; i < 260; i++) {
        const x = r() * cw, ph = x / cw * 6.0, top = ch * (0.18 + 0.16 * Math.sin(ph) + 0.06 * Math.sin(ph * 2.7 + 1)), len = ch * (0.25 + 0.3 * r());
        const gr = g.createLinearGradient(0, top, 0, top + len); const m = r() < 0.5 ? c1 : c2;
        gr.addColorStop(0, css(m, 0)); gr.addColorStop(0.35, css(m, 0.10 + 0.08 * r(), 1.2)); gr.addColorStop(1, css(c2, 0));
        g.fillStyle = gr; g.fillRect(x, top, (3 + 9 * r()) * u, len);
      }
      g.filter = `blur(${120 * u}px)`; g.fillStyle = css(c1, 0.35); g.beginPath(); g.ellipse(cw * 0.35, ch * 0.55, cw * 0.4, ch * 0.22, 0, 0, Math.PI * 2); g.fill();
      g.fillStyle = css(c2, 0.3); g.beginPath(); g.ellipse(cw * 0.72, ch * 0.62, cw * 0.35, ch * 0.2, 0, 0, Math.PI * 2); g.fill();
    } else {        // the "Aluminum Frame" swoosh: a silk ribbon of many thin strokes flowing low-left to high-right, a hot core
      const curve = (o, w) => { g.beginPath(); g.moveTo(-0.1 * cw, ch * (0.95 + o)); g.bezierCurveTo(cw * 0.3, ch * (0.55 + o * 1.4), cw * 0.55, ch * (1.05 + o), cw * 1.1, ch * (0.12 + o * 0.8)); g.lineWidth = w; g.stroke(); };
      g.filter = `blur(${70 * u}px)`; g.strokeStyle = css(c1, 0.55); curve(0, 380 * u); g.strokeStyle = css(c2, 0.35); curve(-0.08, 160 * u);
      g.filter = `blur(${1.5 * u}px)`;
      for (let i = 0; i < 90; i++) { const o = (r() - 0.5) * 0.22, m = r(); g.strokeStyle = css(m < 0.6 ? c1 : c2, 0.05 + 0.12 * r(), 1 + m * 0.5); curve(o, (2 + 10 * r()) * u); }
      g.filter = `blur(${18 * u}px)`; g.strokeStyle = css(c2, 0.5, 1.5); curve(-0.02, 26 * u);
    }
    g.filter = 'none'; g.globalCompositeOperation = 'source-over';
  } else if (kind === 'horizon') {   // transparent sky (the stars show), a warm-blue glow on the horizon, a black ridge, city lights
    const hy = ch * (shot.horizon_y ?? 0.78);
    const glow = g.createLinearGradient(0, hy - ch * 0.35, 0, hy); glow.addColorStop(0, 'rgba(20,40,90,0)'); glow.addColorStop(0.7, 'rgba(40,60,120,0.35)'); glow.addColorStop(1, 'rgba(255,150,80,0.55)');
    g.fillStyle = glow; g.fillRect(0, hy - ch * 0.35, cw, ch * 0.35);
    const f = [r() * 6, r() * 6, r() * 6], ridge = (x) => hy - ch * (0.025 + 0.02 * Math.sin(x / cw * 7 + f[0]) + 0.012 * Math.sin(x / cw * 19 + f[1]) + 0.005 * Math.sin(x / cw * 53 + f[2]));
    g.fillStyle = '#010102'; g.beginPath(); g.moveTo(0, ch); for (let x = 0; x <= cw; x += 4) g.lineTo(x, ridge(x)); g.lineTo(cw, ch); g.closePath(); g.fill();
    g.globalCompositeOperation = 'lighter';
    for (let cl = 0; cl < 7; cl++) {   // clusters of warm lights near the skyline, sparser lower down
      const cx = r() * cw, spread = (60 + 160 * r()) * u, n = 80 + r() * 220;
      g.filter = `blur(${30 * u}px)`; g.fillStyle = 'rgba(255,150,70,0.18)'; g.beginPath(); g.ellipse(cx, ridge(cx) + 10 * u, spread, 18 * u, 0, 0, Math.PI * 2); g.fill(); g.filter = 'none';
      for (let i = 0; i < n; i++) { const x = cx + (r() + r() - 1) * spread, y = ridge(x) + (4 + r() ** 2 * 60) * u; g.fillStyle = `rgba(255,${170 + r() * 60 | 0},${90 + r() * 70 | 0},${0.5 + 0.5 * r()})`; g.fillRect(x, y, (1 + r()) * u, (1 + r()) * u); }
    }
    g.globalCompositeOperation = 'source-over';
  } else if (kind === 'studio') {   // a dark cyclorama: a soft lift behind the object fading to black at the edges
    const gr = g.createRadialGradient(cw * 0.5, ch * 0.42, 0, cw * 0.5, ch * 0.5, Math.max(cw, ch) * 0.75);
    const tint = new THREE.Color(shot.wash || '#3a3f48');
    gr.addColorStop(0, `rgb(${30 + tint.r * 30 | 0},${30 + tint.g * 30 | 0},${34 + tint.b * 30 | 0})`); gr.addColorStop(0.55, '#0b0c0f'); gr.addColorStop(1, '#020203');
    g.fillStyle = gr; g.fillRect(0, 0, cw, ch);
  } else if (kind === 'charcoal') {   // a charcoal-grey studio sweep: a soft lighter centre, a vignette to near black at the corners
    const gr = g.createRadialGradient(cw * 0.5, ch * 0.45, 0, cw * 0.5, ch * 0.5, Math.max(cw, ch) * 0.72);
    gr.addColorStop(0, '#55585c'); gr.addColorStop(0.35, '#3a3c40'); gr.addColorStop(0.75, '#1c1d20'); gr.addColorStop(1, '#0b0b0d');
    g.fillStyle = gr; g.fillRect(0, 0, cw, ch);
    const v = g.createLinearGradient(0, 0, 0, ch); v.addColorStop(0, 'rgba(0,0,0,0.25)'); v.addColorStop(0.5, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.3)');
    g.fillStyle = v; g.fillRect(0, 0, cw, ch);
  } else if (kind === 'gradient') {   // one colour glowing softly behind the object, fading to black at the edges
    const col = new THREE.Color(shot.wash || '#2f6bff'), rgb = (m) => `rgb(${Math.min(255, col.r * 255 * m) | 0},${Math.min(255, col.g * 255 * m) | 0},${Math.min(255, col.b * 255 * m) | 0})`;
    const gr = g.createRadialGradient(cw * 0.5, ch * 0.45, 0, cw * 0.5, ch * 0.5, Math.max(cw, ch) * 0.7);
    gr.addColorStop(0, rgb(0.55)); gr.addColorStop(0.45, rgb(0.18)); gr.addColorStop(1, '#020203');
    g.fillStyle = gr; g.fillRect(0, 0, cw, ch);
  } else if (kind === 'image') {   // the user's picture (shot.backdrop_file under the spec's media folder): loaded in buildProduct
    return null;
  }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function softSpot(THREE) {
  const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d');
  const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.4, 'rgba(255,255,255,0.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256); return new THREE.CanvasTexture(c);
}

function ribbonWallpaper(g, opt) {
  const bg = g.createLinearGradient(0, 0, 540, 1170); bg.addColorStop(0, '#4a1a2c'); bg.addColorStop(1, '#2e1019'); g.fillStyle = bg; g.fillRect(0, 0, 540, 1170);
  const rib = (y, dir, w) => {
    const gr = g.createLinearGradient(0, y, 540, y + 120 * dir);
    gr.addColorStop(0, 'rgba(255,170,190,0.0)'); gr.addColorStop(0.55, 'rgba(255,160,185,0.55)'); gr.addColorStop(1, 'rgba(255,200,215,0.95)');
    g.save(); g.shadowColor = 'rgba(255,150,180,0.7)'; g.shadowBlur = 40; g.lineCap = 'round'; g.strokeStyle = gr; g.lineWidth = w;
    g.beginPath(); g.moveTo(-60, y); g.bezierCurveTo(260, y - 40 * dir, 300, y + 200 * dir, 600, y + 150 * dir); g.stroke(); g.restore();
    g.save(); g.strokeStyle = 'rgba(112,40,62,0.98)'; g.lineWidth = w - 16; g.lineCap = 'round';
    g.beginPath(); g.moveTo(-60, y); g.bezierCurveTo(260, y - 40 * dir, 300, y + 200 * dir, 600, y + 150 * dir); g.stroke(); g.restore();
  };
  rib(250, 1, 150); rib(520, -1, 150); rib(800, 1, 150); rib(1080, -1, 150);
  g.fillStyle = '#05070a'; g.beginPath(); g.roundRect(195, 30, 150, 44, 22); g.fill();
}
function screenTexture(THREE, opt = {}) {
  const c = document.createElement('canvas'); c.width = 540; c.height = 1170; const g = c.getContext('2d');
  if (opt.ribbons) { ribbonWallpaper(g, opt); const t0 = new THREE.CanvasTexture(c); t0.colorSpace = THREE.SRGBColorSpace; t0.anisotropy = 8; return t0; }
  const bg = g.createLinearGradient(0, 0, 540, 1170);
  bg.addColorStop(0, '#f7e9dc'); bg.addColorStop(0.55, '#f1ddd0'); bg.addColorStop(1, '#e9d2c4'); g.fillStyle = bg; g.fillRect(0, 0, 540, 1170);
  const swoosh = g.createLinearGradient(0, 700, 540, 1170); swoosh.addColorStop(0, 'rgba(255,255,255,0)'); swoosh.addColorStop(1, 'rgba(36,112,210,0.95)');
  g.fillStyle = swoosh; g.beginPath(); g.moveTo(540, 640); g.bezierCurveTo(420, 860, 300, 1000, 120, 1170); g.lineTo(540, 1170); g.closePath(); g.fill();
  const orb = g.createRadialGradient(270, 330, 10, 270, 330, 300); orb.addColorStop(0, 'rgba(255,170,110,0.75)'); orb.addColorStop(1, 'rgba(255,170,110,0)');
  g.fillStyle = orb; g.fillRect(0, 0, 540, 800);
  g.fillStyle = '#10151d'; g.textAlign = 'center';
  if (opt.clock === false) {   // the planner turns the clock off when big type sits over the screen: a small date only (or none)
    if (opt.date !== false) { g.globalAlpha = 0.55; g.font = '600 24px TMSans, sans-serif'; g.fillText(opt.date ?? 'Tue 27 Oct', 270, 190); g.globalAlpha = 1; }
  } else {
    g.font = '600 30px TMSans, sans-serif'; g.fillText(opt.date ?? 'Tue 27 Oct', 270, 250);
    g.font = '800 190px TMSans, sans-serif'; g.fillText(opt.time ?? '09:41', 270, 430);
  }
  g.fillStyle = '#05070a';
  if (opt.pill) { g.beginPath(); g.roundRect(195, 30, 150, 44, 22); g.fill(); }                           // a pill-shaped cut-out
  else { g.beginPath(); g.arc(270, 46, 13, 0, Math.PI * 2); g.fill(); }                                    // the camera punch-hole
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

// ---------- the live lock screen: an animated wallpaper redrawn from t, and a power-on fade (black glass until shot.screen.power_on) ----------
// screen.wallpaper "liquid" (default): glossy liquid ripples round a centred swirl; "wave": soft flowing S-shaped colour bands;
// "clock": the old static clock screen. Tinted from screen.tint, else the phone's back colour. Time/date stay small at the top.
function wallpaperTint(THREE, hex) {
  const c = new THREE.Color(hex || '#3fb6e0'), hsl = c.getHSL({});
  if (hsl.s < 0.12) c.lerp(new THREE.Color('#5cbfe8'), 0.6);           // a grey/white body: an icy blue screen rather than a grey one
  const h = c.getHSL({}); c.setHSL(h.h, Math.max(0.6, h.s), Math.min(0.66, Math.max(0.5, h.l))); return c;
}
function liveScreen(THREE, shot, tintHex) {
  const opt = shot.screen || {}, kind = opt.wallpaper || 'liquid';
  const c = document.createElement('canvas'); c.width = 540; c.height = 1170; const g = c.getContext('2d');
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 8;
  const tint = wallpaperTint(THREE, opt.tint || tintHex), T = [tint.r, tint.g, tint.b];
  let still = null;
  if (kind === 'clock') { still = screenTexture(THREE, opt).image; }
  const SW = 135, SH = 292, small = document.createElement('canvas'); small.width = SW; small.height = SH;
  const sg = small.getContext('2d'), img = sg.createImageData(SW, SH);
  const height = (x, y, t) => {
    const dx = x, dy = y - 0.12, r = Math.hypot(dx, dy * 1.15), a = Math.atan2(dy, dx) * Math.min(1, r / 0.35);   // no pinwheel at the centre
    return Math.sin(r * 15 - t * 0.9 + a + 1.6 * Math.sin(r * 3.2 - t * 0.35 + a * 2)) * Math.exp(-r * 0.7)
      + 0.35 * Math.sin(r * 30 - t * 1.3 + 3 * a) * Math.exp(-r * 1.6) + 0.18 * Math.sin(x * 6 + y * 4 + t * 0.4);
  };
  const liquid = (t) => {
    const d = img.data, e = 0.012, L = [-0.45, 0.55, 0.7], ll = Math.hypot(...L);
    for (let j = 0; j < SH; j++) for (let i = 0; i < SW; i++) {
      const x = (i / SW - 0.5) * 1.0, y = (0.5 - j / SH) * 2.17, h0 = height(x, y, t);
      const hx = (height(x + e, y, t) - h0) / e, hy = (height(x, y + e, t) - h0) / e, k = 0.035;
      let nx = -hx * k, ny = -hy * k, nz = 1; const nl = Math.hypot(nx, ny, nz); nx /= nl; ny /= nl; nz /= nl;
      const dif = Math.max(0, (nx * L[0] + ny * L[1] + nz * L[2]) / ll);
      const ndl = (nx * L[0] + ny * L[1] + nz * L[2]) / ll, spec = Math.pow(Math.max(0, 2 * ndl * nz - L[2] / ll), 28);
      const top = Math.max(0, y - 0.2) * 0.45, depth = 0.6 + 0.7 * dif;
      for (let ch = 0; ch < 3; ch++) d[(j * SW + i) * 4 + ch] = Math.min(255, 255 * (T[ch] * depth * 0.95 + spec * 0.9 + top * (0.75 + 0.25 * T[ch]) + (1 - nz) * 0.6 * T[ch]));
      d[(j * SW + i) * 4 + 3] = 255;
    }
    sg.putImageData(img, 0, 0); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high'; g.drawImage(small, 0, 0, 540, 1170);
  };
  const css = (m, a = 1, w = 0) => `rgba(${Math.min(255, 255 * (T[0] * m + w)) | 0},${Math.min(255, 255 * (T[1] * m + w)) | 0},${Math.min(255, 255 * (T[2] * m + w)) | 0},${a})`;
  const wave = (t) => {
    const bg = g.createLinearGradient(0, 0, 540, 1170); bg.addColorStop(0, css(0.6, 1, 0.45)); bg.addColorStop(1, css(0.8, 1, 0.25)); g.fillStyle = bg; g.fillRect(0, 0, 540, 1170);
    for (let b = 0; b < 4; b++) {
      const o = Math.sin(t * 0.35 + b * 1.3) * 30, w = 150 - b * 28, x0 = 120 + b * 70 + o;
      const gr = g.createLinearGradient(x0 - w, 0, x0 + w, 1170); gr.addColorStop(0, css(1.1 - b * 0.1, 0.9, 0.15)); gr.addColorStop(0.5, css(0.75, 0.95, 0.05 + b * 0.08)); gr.addColorStop(1, css(1.15, 0.9, 0.3));
      g.fillStyle = gr; g.save(); g.shadowColor = css(0.4, 0.5); g.shadowBlur = 40;
      g.beginPath(); g.moveTo(x0 + 260, -40);
      g.bezierCurveTo(x0 - 260 + o, 260, x0 - 280, 560, x0 + 40, 700 + o);
      g.bezierCurveTo(x0 + 340, 840, x0 + 220 - o, 1060, x0 - 60, 1220);
      g.lineTo(x0 - 60 - w, 1220); g.bezierCurveTo(x0 + 120 - o, 1060, x0 + 200, 860, x0 - 120 - w * 0.2, 720 + o);
      g.bezierCurveTo(x0 - 420 - w * 0.3, 560, x0 - 300, 200, x0 + 160 - w * 0.4, -40); g.closePath(); g.fill(); g.restore();
    }
  };
  let last = null;
  return {
    texture: tex,
    // t seconds into the shot; on 0..1 = how far the screen has powered up (0 = black glass)
    update(t, on) {
      const tq = Math.round(t * 30) / 30, key = `${tq}|${Math.round(on * 60)}`; if (key === last) return; last = key;
      if (on <= 0) { g.fillStyle = '#000'; g.fillRect(0, 0, 540, 1170); }
      else {
        if (still) g.drawImage(still, 0, 0); else if (kind === 'wave') wave(tq); else liquid(tq);
        if (!still && opt.clock !== false) {   // small time and date at the top
          g.fillStyle = 'rgba(255,255,255,0.92)'; g.textAlign = 'center'; g.shadowColor = 'rgba(0,0,0,0.25)'; g.shadowBlur = 8;
          g.font = '600 22px TMSans, sans-serif'; g.fillText(opt.date ?? 'Tue 27 Oct', 270, 128);
          g.font = '700 74px TMSans, sans-serif'; g.fillText(opt.time ?? '09:41', 270, 205); g.shadowBlur = 0;
        }
        if (on < 1) { g.fillStyle = `rgba(0,0,0,${1 - on})`; g.fillRect(0, 0, 540, 1170); }
      }
      g.fillStyle = '#05070a'; g.beginPath(); g.arc(270, 46, 13, 0, Math.PI * 2); g.fill();   // the punch-hole
      tex.needsUpdate = true;
    },
  };
}

// a soft dry-ice puff: many seeded soft blobs inside a wide ellipse
function puffTexture(THREE, seed) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 128; const g = c.getContext('2d'), r = seeded(seed);
  for (let i = 0; i < 60; i++) {
    const a = r() * Math.PI * 2, d = Math.sqrt(r()), x = 128 + Math.cos(a) * d * 95, y = 72 + Math.sin(a) * d * 38, R = 10 + r() * 30;
    const gr = g.createRadialGradient(x, y, 0, x, y, R); gr.addColorStop(0, `rgba(255,255,255,${0.05 + 0.1 * r()})`); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.fillRect(x - R, y - R, 2 * R, 2 * R);
  }
  g.filter = 'blur(3px)';
  for (let i = 0; i < 14; i++) {   // soft curling wisps
    g.strokeStyle = `rgba(255,255,255,${0.04 + 0.06 * r()})`; g.lineWidth = 2 + r() * 5; g.beginPath();
    const x = 30 + r() * 196, y = 40 + r() * 60; g.moveTo(x, y); g.bezierCurveTo(x + 30, y - 30 * r(), x + 50, y + 20, x + 20 + 60 * r(), y - 25 * r()); g.stroke();
  }
  g.filter = 'none';
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

// a fine brushed grain for the metal: long streaks of slightly different roughness
function brushedTexture(THREE) {
  const c = document.createElement('canvas'); c.width = 512; c.height = 512; const g = c.getContext('2d');
  g.fillStyle = '#a0a0a0'; g.fillRect(0, 0, 512, 512);
  let s = 99; const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let i = 0; i < 3200; i++) {   // each streak also drawn one tile left, so the texture wraps without a seam (the UVs cross 0 mid-panel)
    const v = 120 + r() * 110 | 0, x = r() * 512, y = r() * 512, w = 30 + r() * 220; g.fillStyle = `rgba(${v},${v},${v},0.35)`; g.fillRect(x, y, w, 1); g.fillRect(x - 512, y, w, 1);
  }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(2, 2); t.anisotropy = 8; return t;
}

function glowTexture(THREE) {
  const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d');
  const gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,255,255,0.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

// the phone: height 2 units, titanium-look frame, satin back with a raised lens island, glass screen
function buildPhone(THREE, shot, envMap, screenMap = null) {
  const iph = shot.object === 'iphone', gal = shot.object === 'galaxy', W = gal ? 0.9557 : 0.96, H = 2.0, D = gal ? 0.0973 : 0.105, tone = new THREE.Color(shot.tone || '#8fa3b5');
  const brushed = brushedTexture(THREE);
  const metal = iph ? new THREE.MeshPhysicalMaterial({ color: tone, metalness: 0.88, roughness: 0.4, roughnessMap: brushed, anisotropy: 0.3, envMap, envMapIntensity: 2.0 })
    : new THREE.MeshPhysicalMaterial({ color: tone, metalness: 1, roughness: 0.3, roughnessMap: brushed, anisotropy: 0.55, envMap, envMapIntensity: 1.35 });
  const satin = new THREE.MeshPhysicalMaterial({ color: tone.clone().multiplyScalar(iph ? 0.62 : gal ? 1.15 : 0.8), metalness: iph ? 0.25 : 0.8, roughness: iph ? 0.6 : 0.5, roughnessMap: brushed, clearcoat: 0.25, clearcoatRoughness: 0.35, envMap, envMapIntensity: iph ? 2.2 : 1.1 });
  const plateMat = new THREE.MeshPhysicalMaterial({ color: tone.clone().multiplyScalar(0.9), metalness: 0.9, roughness: 0.34, roughnessMap: brushed, anisotropy: 0.4, envMap, envMapIntensity: 1.3 });
  const lensGlass = new THREE.MeshPhysicalMaterial({ color: '#030409', metalness: 0, roughness: 0.03, clearcoat: 1, clearcoatRoughness: 0.02, iridescence: 1, iridescenceIOR: 1.6, iridescenceThicknessRange: [180, 520], envMap, envMapIntensity: 2.6 });
  const darkMetal = new THREE.MeshPhysicalMaterial({ color: '#1b1f26', metalness: 1, roughness: 0.3, envMap, envMapIntensity: 1.1 });
  const glassBlack = new THREE.MeshPhysicalMaterial({ color: '#030409', metalness: 0.1, roughness: 0.03, clearcoat: 1, clearcoatRoughness: 0.03, envMap, envMapIntensity: 1.8 });
  const grp = new THREE.Group();
  grp.add(slab(THREE, W, H, iph ? 0.17 : gal ? 0.12 : 0.15, D, 0.014, metal));                                                          // the frame
  const back = slab(THREE, W - 0.03, H - 0.03, 0.135, 0.01, 0.002, satin); back.position.z = -D / 2 - 0.004; grp.add(back);   // back panel
  const bezel = slab(THREE, W - 0.045, H - 0.045, 0.13, 0.004, 0.0005, glassBlack); bezel.position.z = D / 2 + 0.0012; grp.add(bezel);
  const scr = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(THREE, W - 0.07, H - 0.07, 0.115), 24),
    new THREE.MeshBasicMaterial({ map: screenMap || screenTexture(THREE, { ...shot.screen, pill: iph, ribbons: iph && !(shot.screen && shot.screen.clock) }), color: '#d8d8dc', toneMapped: false }));
  // map the picture to the shape's bounding box (ShapeGeometry's uvs are in shape units)
  const uv = scr.geometry.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, (uv.getX(i) + (W - 0.07) / 2) / (W - 0.07), (uv.getY(i) + (H - 0.07) / 2) / (H - 0.07));
  scr.position.z = D / 2 + 0.0036; grp.add(scr);
  const sheen = new THREE.Mesh(new THREE.ShapeGeometry(roundedRect(THREE, W - 0.07, H - 0.07, 0.115), 24),
    new THREE.MeshPhysicalMaterial({ color: '#000', transparent: true, opacity: 0.0, roughness: 0.02, metalness: 0, clearcoat: 1, envMap, envMapIntensity: 0.9, depthWrite: false }));
  sheen.material.opacity = 0.12; sheen.position.z = D / 2 + 0.0042; grp.add(sheen);                          // the glass reflection over the screen
  // the lens island: a thick raised plate with two stepped, coated lenses stacked and an oval sensor beside them
  const bz = -D / 2 - 0.009, island = new THREE.Group(); island.position.set(iph || gal ? 0 : -0.17, iph ? 0.63 : gal ? 0.79 : 0.66, bz); grp.add(island);
  const pd = gal ? 0.056 : 0.06;
  const plate = slab(THREE, gal ? 0.84 : iph ? W - 0.05 : 0.5, gal ? 0.32 : iph ? 0.72 : 0.6, gal ? 0.07 : iph ? 0.12 : 0.11, pd, 0.01, iph || gal ? metal : plateMat); plate.position.z = -pd / 2; island.add(plate);
  const V = (r, h) => new THREE.Vector2(r, h);
  const lens = (x, y, R) => {
    const l = new THREE.Group(); l.position.set(x, y, -pd);
    const lathe = (pts, mat) => { const gm = new THREE.LatheGeometry(pts, 96); gm.rotateX(-Math.PI / 2); return new THREE.Mesh(gm, mat); };
    l.add(lathe([V(R * 1.12, 0), V(R * 1.12, 0.006), V(R * 1.08, 0.012), V(R * 1.0, 0.014), V(R * 0.98, 0.006), V(R * 0.9, 0.004)], satin));              // collar
    l.add(lathe([V(R * 1.0, 0.014), V(R * 1.0, 0.03), V(R * 0.97, 0.038), V(R * 0.9, 0.04), V(R * 0.86, 0.034), V(R * 0.82, 0.028)], metal));              // bright ring
    l.add(lathe([V(R * 0.82, 0.028), V(R * 0.8, 0.012), V(R * 0.74, 0.008), V(R * 0.0, 0.008)], darkMetal));                                               // recess floor
    const dome = new THREE.Mesh(new THREE.SphereGeometry(R * 0.76, 64, 32, 0, Math.PI * 2, 0, 0.62), lensGlass);
    dome.geometry.scale(1, 0.42, 1); dome.geometry.rotateX(-Math.PI / 2); dome.geometry.translate(0, 0, -0.004); l.add(dome);
    const coat = new THREE.Mesh(new THREE.RingGeometry(R * 0.3, R * 0.36, 64), new THREE.MeshBasicMaterial({ color: new THREE.Color('#3c58ff').multiplyScalar(0.9), transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }));
    coat.position.z = -0.027; coat.rotation.y = Math.PI; l.add(coat);
    return l;
  };
  if (gal) {   // the leaked layout: a raised horizontal bar with two round lenses, a pill-shaped periscope lens and the flash at the end (arrangement inside the bar is not in the leak)
    island.add(lens(-0.27, 0.0, 0.1), lens(-0.04, 0.0, 0.1));
    const pill = slab(THREE, 0.12, 0.215, 0.058, 0.04, 0.008, darkMetal); pill.position.set(0.2, 0, -pd - 0.01); island.add(pill);
    const pillGlass = slab(THREE, 0.088, 0.185, 0.042, 0.012, 0.003, lensGlass); pillGlass.position.set(0.2, 0, -pd - 0.028); island.add(pillGlass);
    const flash = new THREE.Mesh(new THREE.CircleGeometry(0.02, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color('#ffd9a0').multiplyScalar(0.55), toneMapped: false }));
    flash.position.set(0.345, 0.065, -pd - 0.0015); flash.rotation.y = Math.PI; island.add(flash);
    const sens = new THREE.Mesh(new THREE.CircleGeometry(0.014, 24), new THREE.MeshBasicMaterial({ color: '#05060a' }));
    sens.position.set(0.345, -0.06, -pd - 0.0015); sens.rotation.y = Math.PI; island.add(sens);
  } else if (iph) {
    island.add(lens(-0.2, 0.17, 0.125), lens(-0.2, -0.17, 0.125), lens(0.16, 0.0, 0.125));
    const flash = new THREE.Mesh(new THREE.CircleGeometry(0.02, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color('#ffd9a0').multiplyScalar(1.5), toneMapped: false }));
    flash.position.set(0.32, 0.27, -0.0615); flash.rotation.y = Math.PI; island.add(flash);
    const lidar = new THREE.Mesh(new THREE.CircleGeometry(0.026, 32), new THREE.MeshBasicMaterial({ color: '#05060a' }));
    lidar.position.set(0.32, -0.25, -0.0615); lidar.rotation.y = Math.PI; island.add(lidar);
  } else {
    island.add(lens(-0.12, 0.15, 0.1), lens(-0.12, -0.14, 0.1));
    const oval = slab(THREE, 0.115, 0.27, 0.055, 0.04, 0.008, darkMetal); oval.position.set(0.13, 0.15, -0.06 - 0.01); island.add(oval);
    const ovalGlass = slab(THREE, 0.085, 0.24, 0.04, 0.012, 0.003, lensGlass); ovalGlass.position.set(0.13, 0.15, -0.0805); island.add(ovalGlass);
    const flash = new THREE.Mesh(new THREE.CircleGeometry(0.02, 32), new THREE.MeshBasicMaterial({ color: new THREE.Color('#ffb347').multiplyScalar(1.6), toneMapped: false }));
    flash.position.set(0.13, 0.08, -0.0868); flash.rotation.y = Math.PI; island.add(flash);
    const dot = new THREE.Mesh(new THREE.CircleGeometry(0.011, 24), new THREE.MeshBasicMaterial({ color: '#9fb0e8', toneMapped: false }));
    dot.position.set(0.13, 0.235, -0.0868); dot.rotation.y = Math.PI; island.add(dot);
    const sensor = new THREE.Mesh(new THREE.CircleGeometry(0.024, 32), new THREE.MeshBasicMaterial({ color: '#05060a' }));
    sensor.position.set(0.13, 0.165, -0.0868); sensor.rotation.y = Math.PI; island.add(sensor);
  }
  // side keys, and the bottom edge's port and speaker slots
  const key = (y, len) => { const k = slab(THREE, 0.02, len, 0.009, 0.03, 0.004, darkMetal); k.rotation.y = Math.PI / 2; k.position.set(W / 2 + 0.003, y, 0); return k; };
  grp.add(key(0.38, 0.26), key(0.0, 0.14));
  // the USB-C port: a matte black opening with a chamfered metal lip and the tongue inside; speaker and mic holes as dark discs (matte, so
  // they never catch the soft-boxes like LEDs), each a hair proud of the frame's bevelled edge (H/2 + 0.014) so nothing z-fights
  const hole = new THREE.MeshStandardMaterial({ color: '#000000', roughness: 1, metalness: 0, envMapIntensity: 0 });
  const lip = slab(THREE, 0.17, 0.04, 0.02, 0.006, 0.002, darkMetal); lip.rotation.x = Math.PI / 2; lip.position.set(0, -H / 2 - 0.013, 0); grp.add(lip);
  const port = slab(THREE, 0.15, 0.028, 0.014, 0.006, 0.001, hole); port.rotation.x = Math.PI / 2; port.position.set(0, -H / 2 - 0.0155, 0); grp.add(port);
  const tongue = slab(THREE, 0.1, 0.008, 0.003, 0.004, 0, new THREE.MeshStandardMaterial({ color: '#15171b', roughness: 0.7, metalness: 0.2 })); tongue.rotation.x = Math.PI / 2; tongue.position.set(0, -H / 2 - 0.0175, 0); grp.add(tongue);
  for (const sx of [-1, 1]) for (let i = 0; i < 5; i++) {
    const h = new THREE.Mesh(new THREE.CircleGeometry(0.0085, 20), hole); h.rotation.x = Math.PI / 2; h.position.set(sx * (0.15 + i * 0.03), -H / 2 - 0.0145, 0); grp.add(h);
  }
  return grp;
}


// the chip: a processor package lying flat, facing +z -- dark substrate, a metal lid, circuit lines that glow through it, gold contacts
// and capacitors. A glow colour and a heat curve (shot.heat = [from, to], 0..1) turn it from cool to white-hot.
function chipTexture(THREE, shot) {
  const c = document.createElement('canvas'); c.width = c.height = 1024; const g = c.getContext('2d');
  g.fillStyle = '#05070b'; g.fillRect(0, 0, 1024, 1024);
  let s = 5; const r = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  g.strokeStyle = '#ffffff'; g.lineCap = 'round';
  for (let i = 0; i < 150; i++) {                              // circuit traces: right-angle runs with nodes
    let x = 60 + r() * 900, y = 60 + r() * 900; g.lineWidth = 1.5 + r() * 2.5; g.globalAlpha = 0.25 + r() * 0.55; g.beginPath(); g.moveTo(x, y);
    for (let k = 0; k < 4; k++) { if (r() < 0.5) x += (r() - 0.5) * 300; else y += (r() - 0.5) * 300; g.lineTo(x, y); } g.stroke();
    g.beginPath(); g.arc(x, y, 3 + r() * 3, 0, Math.PI * 2); g.fillStyle = '#fff'; g.fill();
  }
  g.globalAlpha = 1; g.strokeStyle = '#ffffff'; g.lineWidth = 3;
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { g.globalAlpha = 0.55; g.strokeRect(170 + i * 190, 170 + j * 190, 150, 150); }   // a core grid
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function labelTexture(THREE, shot) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 256; const g = c.getContext('2d');
  g.clearRect(0, 0, 1024, 256); g.fillStyle = 'rgba(230,236,245,0.92)'; g.textAlign = 'center';
  const lab = String(shot.label || 'CHIP').toUpperCase(); let px = 92; g.font = `800 ${px}px TMSans, sans-serif`;
  while (px > 30 && g.measureText(lab).width > 900) { px -= 4; g.font = `800 ${px}px TMSans, sans-serif`; }
  g.fillText(lab, 512, 118);
  g.font = '600 38px WIMono, monospace'; g.fillText(String(shot.sublabel || '').toUpperCase(), 512, 190);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function buildChip(THREE, shot, envMap) {
  const grp = new THREE.Group(), glow = new THREE.Color(shot.glow || '#3ac8ff');
  const sub = new THREE.MeshPhysicalMaterial({ color: '#12161d', metalness: 0.6, roughness: 0.55, envMap, envMapIntensity: 0.9 });
  const lid = new THREE.MeshPhysicalMaterial({ color: '#a9b4c2', metalness: 1, roughness: 0.28, roughnessMap: brushedTexture(THREE), anisotropy: 0.5, envMap, envMapIntensity: 0.8 });
  const gold = new THREE.MeshPhysicalMaterial({ color: '#c9a24a', metalness: 1, roughness: 0.3, envMap, envMapIntensity: 1.4 });
  grp.add(slab(THREE, 1.7, 1.7, 0.07, 0.08, 0.012, sub));
  const base = slab(THREE, 1.2, 1.2, 0.05, 0.05, 0.01, lid); base.position.z = 0.06; grp.add(base);
  const emis = new THREE.MeshStandardMaterial({ color: '#000', emissive: glow, emissiveMap: chipTexture(THREE, shot), emissiveIntensity: 1.0, transparent: true, opacity: 0.95, roughness: 0.5, metalness: 0, depthWrite: false });
  const face = new THREE.Mesh(new THREE.PlaneGeometry(1.0, 1.0), emis); face.position.z = 0.0875; grp.add(face);
  const lab = new THREE.Mesh(new THREE.PlaneGeometry(1.0, 0.25), new THREE.MeshBasicMaterial({ map: labelTexture(THREE, shot), transparent: true, toneMapped: false })); lab.position.set(0, -0.34, 0.0885); grp.add(lab);
  for (let i = 0; i < 18; i++) for (const side of [0, 1, 2, 3]) {      // gold contacts along the four edges
    const u = -0.78 + i * 0.092, b = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.018, 0.012), gold);
    const e = 0.84; if (side === 0) b.position.set(u, e, 0.04); else if (side === 1) b.position.set(u, -e, 0.04); else { b.rotation.z = Math.PI / 2; b.position.set(side === 2 ? e : -e, u, 0.04); }
    grp.add(b);
  }
  for (const [x, y] of [[-0.7, 0.7], [0.7, 0.7], [-0.7, -0.7], [0.7, -0.7], [0, 0.72], [0, -0.72], [0.72, 0], [-0.72, 0]]) {
    const cap = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.04, 0.03), new THREE.MeshPhysicalMaterial({ color: '#7a6a3a', metalness: 0.8, roughness: 0.4, envMap })); cap.position.set(x, y, 0.055); grp.add(cap);
  }
  // heat shimmer: sparks rising off the lid while it is hot
  const n = 140, pos = new Float32Array(n * 3), seed = new Float32Array(n);
  const rs = seeded(shot.seed ?? 31);
  for (let i = 0; i < n; i++) { seed[i] = rs(); pos.set([(rs() - 0.5) * 1.1, (rs() - 0.5) * 1.1, 0.1], i * 3); }
  const pg = new THREE.BufferGeometry(); pg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const sparks = new THREE.Points(pg, new THREE.PointsMaterial({ color: '#ff8a3a', size: 0.018, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false })); grp.add(sparks);
  const hot = new THREE.Color('#ff5a1f'), cold = glow.clone(), white = new THREE.Color('#ffd9a0');
  grp.userData.update = (k, t) => {
    const h = shot.heat || [0, 0], v = Math.min(1, Math.max(0, h[0] + (h[1] - h[0]) * k));
    emis.emissive.copy(cold).lerp(hot, Math.min(1, v * 1.6)).lerp(white, Math.max(0, v - 0.7) * 2.2);
    emis.emissiveIntensity = 0.9 + v * 2.6 + Math.sin(t * 6) * 0.08 * v;
    sparks.material.opacity = Math.min(0.9, v * 1.2);
    const a = pg.attributes.position; for (let i = 0; i < n; i++) { const life = (t * (0.35 + seed[i] * 0.5) + seed[i]) % 1; a.setZ(i, 0.1 + life * 0.9); a.setX(i, (seed[i] - 0.5) * 1.1 + Math.sin(t * 2 + i) * 0.03 * life); a.setY(i, (((seed[(i * 7) % n]) - 0.5) * 1.1)); } a.needsUpdate = true;
  };
  return grp;
}

// camera and phone placement for each move, as a function of k (0..1 through the shot) and t (seconds into it)
function placement(THREE, shot, k, t) {
  const e = SEMANTIC_MOVES.has(shot.move) ? linE(k) : camE(k, 0.3, shot), c = shot.cam || {}, fl = Math.sin(t * 0.9) * 0.012;
  const flat = (spin) => new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), spin).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2));
  const eul = (x, y, z) => new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z, 'YXZ'));
  switch (shot.move) {
    case 'island': if (shot.object === 'galaxy') {   // macro along the raised bar
      const tg = new THREE.Vector3(lerp(0.2, -0.1, e), 0.79, 0.1);
      return { q: eul(0.06, Math.PI + lerp(0.12, -0.08, e), -0.05), pos: new THREE.Vector3(lerp(0.75, -0.55, e), lerp(0.62, 0.9, e), lerp(1.35, 1.2, e)), at: tg, fov: 30, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    } // falls through otherwise
    // eslint-disable-next-line no-fallthrough
    case 'island_old': {   // macro on the lens island, gliding across it, back of the phone to camera
      const tgt = new THREE.Vector3(lerp(0.2, 0.15, e), lerp(0.66, 0.62, e), 0.1);
      return { q: eul(0.08, Math.PI + lerp(0.1, -0.1, e), -0.16), pos: new THREE.Vector3(lerp(c.x0 ?? 0.75, c.x1 ?? -0.05, e), lerp(0.55, 0.78, e), lerp(1.3, 1.08, e)), at: tgt, fov: 30, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'monolith': {   // a low angle up the back of the phone: it stands over the camera like a monolith, turning slowly
      return { q: eul(0.0, Math.PI + lerp(-0.6, 0.35, e), 0.03), pos: new THREE.Vector3(lerp(0.9, 0.5, e), lerp(-1.75, -1.35, e), lerp(2.3, 1.95, e)), at: new THREE.Vector3(0, lerp(0.15, 0.35, e), 0), fov: 38, roll: lerp(0.04, -0.02, e), phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'hero': {   // the front, floating and turning a little, screen lit
      return { q: eul(lerp(0.16, 0.06, e), lerp(-0.62, 0.42, e), lerp(0.04, -0.03, e)), pos: new THREE.Vector3(0, 0.05, lerp(4.6, 3.8, e)), at: new THREE.Vector3(0, 0, 0), fov: 32, roll: 0, phone: new THREE.Vector3(0, fl * 2, 0) };
    }
    case 'profile': {   // lying flat, seen edge-on to show how thin it is
      return { q: flat(0.0), pos: new THREE.Vector3(lerp(-1.9, 0.9, e), lerp(0.2, 0.32, e), 2.1), at: new THREE.Vector3(lerp(-0.7, 0.7, e), 0, 0), fov: 28, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'chip': {   // the chip tilted back, turning slowly, camera easing in
      return { q: eul(-0.95, lerp(-0.55, 0.5, e), lerp(0.1, -0.08, e)), pos: new THREE.Vector3(0, 0.15, lerp(4.8, 3.7, e)), at: new THREE.Vector3(0, 0, 0.05), fov: 32, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'chip_macro': {   // skimming low across the lid and its glowing circuits
      return { q: eul(-1.15, lerp(0.25, -0.2, e), 0), pos: new THREE.Vector3(lerp(-1.5, 0.6, e), lerp(1.0, 0.8, e), lerp(2.4, 2.1, e)), at: new THREE.Vector3(lerp(-0.1, 0.1, e), -0.1, 0.05), fov: 30, roll: 0.02, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'orbit': {   // a half circle round the phone, back first, then the side
      const a = lerp(0.35, 2.5, e), r = lerp(3.3, 2.8, e);
      return { q: eul(0.04, Math.PI, 0.02), pos: new THREE.Vector3(Math.sin(a) * r, lerp(0.2, 0.55, e), Math.cos(a) * r), at: new THREE.Vector3(0, 0.1, 0), fov: 30, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'screen': {   // a macro on the top of the front: the screen and its cut-out
      return { q: eul(0.04, lerp(-0.12, 0.1, e), 0), pos: new THREE.Vector3(lerp(-0.45, 0.25, e), lerp(0.95, 0.85, e), lerp(1.5, 1.15, e)), at: new THREE.Vector3(0, 0.78, 0.05), fov: 30, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'edge': {   // along the frame from a corner: the bevel, the keys, the glint
      return { q: eul(0.0, lerp(0.95, 1.25, e), 0.02), pos: new THREE.Vector3(lerp(1.5, 1.2, e), lerp(1.35, 1.0, e), lerp(1.2, 1.0, e)), at: new THREE.Vector3(0.1, lerp(0.95, 0.6, e), 0), fov: 30, roll: 0.03, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'flip': {   // the back to camera, turning through the edge to the front, the camera easing in
      return { q: eul(lerp(0.1, 0.05, e), lerp(Math.PI + 0.35, -0.3, e), lerp(-0.04, 0.03, e)), pos: new THREE.Vector3(0, 0.05, lerp(4.4, 3.9, e)), at: new THREE.Vector3(0, 0, 0), fov: 32, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    }
    case 'rise': {   // rising slowly from below the frame into the centre, a quarter turn as it settles
      const r = 1 - (1 - clamp01(k)) ** 3;
      return { q: eul(lerp(0.3, 0.08, r), lerp(-0.5, 0.25, r), 0), pos: new THREE.Vector3(0, 0.1, 4.2), at: new THREE.Vector3(0, 0, 0), fov: 32, roll: 0, phone: new THREE.Vector3(0, lerp(-3.4, 0, r) + fl * r, 0) };
    }
    case 'port': {   // macro along the bottom edge: the USB-C port and the speaker holes, the phone tipped toward the lens
      return { q: eul(-0.55, lerp(-0.18, 0.18, e), 0), pos: new THREE.Vector3(lerp(-0.35, 0.3, e), lerp(-1.62, -1.55, e), lerp(1.0, 0.92, e)), at: new THREE.Vector3(lerp(-0.18, 0.15, e), -0.86, 0.47), fov: 30, roll: 0, phone: new THREE.Vector3(0, fl * 0.5, 0) };
    }
    case 'buttons': {   // macro down the side keys, the frame turned a little toward the lens
      return { q: eul(0, lerp(-0.3, -0.12, e), 0.02), pos: new THREE.Vector3(lerp(1.15, 1.0, e), lerp(0.6, 0.0, e), lerp(0.75, 0.55, e)), at: new THREE.Vector3(0.45, lerp(0.42, 0.0, e), 0.1), fov: 28, roll: 0.02, phone: new THREE.Vector3(0, fl * 0.5, 0) };
    }
    case 'reveal': {   // back to camera, a half turn to the front at turn_at, the camera pulling back the whole shot
      const dur = Math.max(0.5, (shot.end ?? 0) - (shot.start ?? 0)), t0 = (shot.turn_at ?? 0.45) * dur, turn = ease((t - t0) / 0.8);
      const sway = Math.sin(t * 0.5) * 0.04 * (1 - turn);
      return { q: eul(0.04, Math.PI + sway + turn * Math.PI, 0), pos: new THREE.Vector3(0, 0.05, lerp(3.55, 4.5, 1 - (1 - clamp01(k)) ** 2)), at: new THREE.Vector3(0, -0.02, 0), fov: 32, roll: 0, phone: new THREE.Vector3(0, fl * 0.5, 0) };
    }
    default: return { q: eul(0, lerp(-0.6, 0.6, e), 0), pos: new THREE.Vector3(0, 0, 4), at: new THREE.Vector3(0, 0, 0), fov: 34, roll: 0, phone: new THREE.Vector3() };
  }
}

// the planner's phone choice plus its colour option name (shot.color) as one resolvePhone spec
const phoneSpec = (shot) => {
  const p = typeof shot.phone === 'string' ? { id: shot.phone } : { ...shot.phone };
  if (shot.color && !p.color && !p.colour) p.color = shot.color; return p;
};
const halton = (i, b) => { let f = 1, r = 0; while (i > 0) { f /= b; r += f * (i % b); i = Math.floor(i / b); } return r; };

export async function buildProduct(THREE, shot, { stars, renderer, W, H }) {
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#020306');
  const bd = shot.backdrop || 'stars';
  const sky = stars(shot.seed ?? 11); if (sky.children[1]) sky.children[1].material.opacity = bd === 'horizon' ? 0.08 : 0.16; if (sky.children[0]) sky.children[0].material.opacity = 0.8;
  if (bd === 'stars' || bd === 'horizon') scene.add(sky);
  const studio = studioEnvironment(THREE, renderer, shot); let envMap = studio.texture;
  scene.environment = envMap; let darkness = 0; scene.environmentIntensity = shot.object === 'iphone' ? 1.7 : shot.object === 'chip' ? 0.9 : 0.9;
  let phone = null, live = null, spec = null;
  const wantLive = shot.object !== 'chip' && !(shot.screen && shot.screen.wallpaper === 'model');
  if (shot.object !== 'chip' && (shot.phone || shot.glb)) { try { const pmx = await import('./phone_models.mjs'); spec = pmx.resolvePhone(phoneSpec(shot)); } catch { spec = null; } }
  if (wantLive) live = liveScreen(THREE, shot, spec?.back_color || shot.tone || '#8fa3b5');
  if (shot.object === 'chip') phone = buildChip(THREE, shot, envMap);
  else if (shot.phone || shot.glb) {   // a real model (assets/models/phones/<id>.glb) first, then the code-built preset, then the built-in phone
    let pm = null;
    try { pm = await import('./phone_models.mjs'); spec = pm.resolvePhone(phoneSpec(shot)); } catch (err) { console.warn(`product: phone library not loaded (${err && err.message})`); }
    if (shot.glb !== false) {
      try { const { loadPhoneGlb } = await import('./phone_glb.mjs');
        phone = await loadPhoneGlb(THREE, spec?.id || String(shot.phone || ''), { envMap, file: typeof shot.glb === 'string' ? shot.glb : spec?.glb || null,
          screenMap: live ? live.texture : shot.screen ? screenTexture(THREE, shot.screen) : null });
      } catch (err) { console.warn(`product: model file for ${JSON.stringify(shot.phone)} not used (${err && err.message})`); phone = null; }
    }
    if (!phone && pm && spec) {
      try { phone = pm.buildPhoneModel(THREE, spec, { envMap, shot, screenMap: live ? live.texture : shot.screen && shot.screen.clock === false ? screenTexture(THREE, shot.screen) : null }); } catch (err) { console.warn(`product: phone model ${JSON.stringify(shot.phone)} not used (${err && err.message})`); phone = null; }
    }
  }
  if (!phone) phone = buildPhone(THREE, shot, envMap, live ? live.texture : null);
  const holder = new THREE.Group(); holder.add(phone); scene.add(holder);
  // dark finishes (Titanium Black...) reflect almost nothing as pure metal: lift the base colour to a floor and the reflections with it,
  // so the frame and back still carry broad soft highlights; light finishes are left as they are so they never blow out
  if (shot.object !== 'chip') {
    const seen = new Set(), lum = (c) => 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b, FLOOR = 0.075;
    // how dark the finish is comes from the body colours (frame + back); the small dark metal parts (lens collars, port lip) would
    // otherwise make every phone count as black and push every light to full
    const body = phone.userData && phone.userData.model;
    const bodyDark = body && body.frame_color && body.back_color
      ? clamp01((0.2 - (lum(new THREE.Color(body.frame_color)) + lum(new THREE.Color(body.back_color))) / 2) / 0.2) : null;
    phone.traverse((o) => {
      const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
      for (const m of ms) {
        if (seen.has(m) || !m.color || m.isMeshBasicMaterial || m.envMapIntensity === 0 || (m.metalness ?? 0) < 0.4) continue; seen.add(m);
        const L = lum(m.color);
        if (L < 0.003) continue;                                        // true blacks (holes, lens glass) stay black
        const d = clamp01((0.2 - L) / 0.2); darkness = bodyDark ?? Math.max(darkness, d);
        if (L < FLOOR) m.color.multiplyScalar(FLOOR / L);
        m.envMapIntensity = (m.envMapIntensity ?? 1) * (1 + 1.3 * d);
        if (m.roughness !== undefined) m.roughness = Math.max(m.roughness, 0.22 + 0.1 * d);   // broader, softer highlights
      }
    });
  }
  if (shot.object !== 'chip' && shot.object !== 'iphone') scene.environmentIntensity = 0.9 + 0.5 * darkness;
  const keyI = shot.object === 'iphone' ? 2.2 : shot.object === 'chip' ? 0.9 : 0.9 + 1.6 * darkness;
  const key = new THREE.DirectionalLight(0xffffff, keyI); key.position.set(-3, 4, 5); scene.add(key);
  const fill = new THREE.DirectionalLight(0xdfe8ff, shot.object === 'chip' ? 0 : 0.2 + 0.7 * darkness); fill.position.set(4, 1, 3); scene.add(fill);
  const wash = shot.wash ? new THREE.Color(shot.wash) : null, washTex = glowTexture(THREE);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: washTex, color: wash || '#000', transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: wash && bd !== 'wash' ? 0.24 : 0 }));
  glow.scale.setScalar(shot.wash_size ?? 14); scene.add(glow);
  // light finishes on macro / edge-on moves are where the frame turns into a white sheet: rim, key and reflections are capped there
  const NEAR = ['island', 'island_old', 'screen', 'edge', 'port', 'buttons', 'profile'].includes(shot.move), lightFin = shot.object !== 'chip' && shot.object !== 'iphone' && darkness < 0.35;
  const glareCap = lightFin && NEAR ? 0.4 : lightFin ? 0.8 : 1;
  if (glareCap < 1) { key.intensity *= 0.55 + 0.45 * glareCap; fill.intensity *= 0.7; }
  const rimK = (shot.object === 'chip' || shot.object === 'iphone' ? 1 : 0.4 + 0.6 * darkness) * glareCap;   // light finishes get a gentler rim, or the edges blow out
  const rimA = new THREE.PointLight(wash || 0x7fa6ff, (wash ? 14 : 4) * rimK, 12, 1.6), rimB = new THREE.PointLight(0x9fd8ff, (bd === 'studio' ? 1.2 : 5) * rimK, 12, 1.6);   // studio: low, or it pools on the floor
  scene.add(rimA, rimB);   // the silhouette edge against the dark
  // the backdrop plate (wash / horizon / studio): camera-facing, beyond the object, in front of the star sphere
  let plateTex = backdropCanvas(THREE, shot, W, H); const PD = 150;
  if (bd === 'image' && shot.backdrop_file) {   // a picture the user chose, dimmed so the phone stays the brightest thing
    try { plateTex = await new THREE.TextureLoader().loadAsync(`/media/${encodeURIComponent(shot.backdrop_file)}`); plateTex.colorSpace = THREE.SRGBColorSpace; }
    catch (err) { console.warn(`product: backdrop ${shot.backdrop_file} not loaded (${err && err.message})`); plateTex = null; }
  }
  const plate = plateTex ? new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: plateTex, transparent: bd === 'horizon', depthWrite: false, fog: false,
    color: new THREE.Color(1, 1, 1).multiplyScalar(shot.wash_gain ?? (bd === 'wash' ? 1.15 : bd === 'image' ? 0.6 : 1)) })) : null;
  if (plate) { plate.renderOrder = bd === 'horizon' ? 10 : -1; scene.add(plate); }   // the horizon is drawn over the stars (its land hides them)
  // ---- the reveal kit: power-on, the screen's halo, the window-light streak, dry-ice fog, light dims (all pure functions of t) ----
  const dur0 = Math.max(0.5, (shot.end ?? 0) - (shot.start ?? 0)), scrOpt = shot.screen || {};
  const powerOn = typeof scrOpt.power_on === 'number' ? scrOpt.power_on : shot.move === 'reveal' ? (shot.turn_at ?? 0.45) * dur0 + 0.8 : -1;
  const halo = shot.glow && shot.object !== 'chip' ? new THREE.Sprite(new THREE.SpriteMaterial({ map: washTex, color: wallpaperTint(THREE, scrOpt.tint || spec?.back_color || shot.tone),
    transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0 })) : null;
  if (halo) { halo.scale.set(2.5, 3.6, 1); scene.add(halo); }
  let streak = null;
  if (shot.streak && shot.object !== 'chip') {   // a crisp diagonal band of window light riding just above the back glass (the island occludes it)
    const ud = phone.userData || {}, PW = ud.W || 0.9557, PH = ud.H || 2, PZ = (ud.D || 0.0973) / 2 + 0.0095;
    const col = new THREE.Color(spec?.back_color || shot.tone || '#c8ccd2').lerp(new THREE.Color("#ffffff"), 0.25);
    streak = new THREE.Mesh(new THREE.PlaneGeometry(PW, PH), new THREE.ShaderMaterial({
      uniforms: { c: { value: 1 }, amt: { value: 0.5 }, col: { value: col }, size: { value: new THREE.Vector2(PW - 0.01, PH - 0.01) }, rad: { value: 0.11 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2,
      vertexShader: 'varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `uniform float c, amt, rad; uniform vec3 col; uniform vec2 size; varying vec2 vP;
        void main(){ vec2 q = abs(vP) - size * 0.5 + rad; if (length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - rad > 0.0) discard;
          float p = dot(vP / size.y, normalize(vec2(1.0, 0.85))), w = 0.15, e = 0.018;
          float band = smoothstep(c - w - e, c - w + e, p) * (1.0 - smoothstep(c + w - e, c + w + e, p));
          float fall = 0.35 + 0.65 * smoothstep(c - w, c + w, p);                 // brightest at the leading edge, like light through a window
          float along = 0.55 + 0.45 * smoothstep(-0.6, 0.4, vP.y / size.y);        // and fading towards the bottom of the back
          gl_FragColor = vec4(col * band * fall * along * amt, 1.0); }` }));
    streak.userData.gain = 1 - 0.65 * (0.2126 * col.r + 0.7152 * col.g + 0.0722 * col.b);   // light backs need far less, or it turns to a flat white shape
    streak.rotation.y = Math.PI; streak.position.z = -PZ; phone.add(streak);
  }
  let puffs = null; const fogO = typeof shot.fog === 'object' && shot.fog ? shot.fog : {}, fogCol = new THREE.Color(fogO.color || '#cfd8e6'), fogH = fogO.height ?? 0.25;
  if (shot.fog) {
    const texs = [1, 2, 3].map((i) => puffTexture(THREE, 70 + i)), rs = seeded((shot.seed ?? 0) + 57); puffs = [];
    for (let i = 0; i < 54; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: texs[i % 3], color: fogCol.clone(), transparent: true, depthWrite: false, opacity: 0, fog: false }));
      sp.renderOrder = 5; scene.add(sp);
      puffs.push({ sp, x0: rs(), y: rs(), back: i % 5 < 2, dz: rs(), v: (0.012 + 0.03 * rs()) * (rs() < 0.5 ? -1 : 1), s: 0.7 + 0.9 * rs(), rot: (rs() - 0.5) * 0.8, spin: (rs() - 0.5) * 0.25, a: 0.12 + 0.24 * rs(), ph: rs() * 6.28 });
    }
  }
  const dimF = (t) => {
    let f = 1;
    if (shot.dim_in) f = Math.min(f, lerp(0.15, 1, ease(t / shot.dim_in)));
    if (shot.dim_out) f = Math.min(f, lerp(0.15, 1, ease((dur0 - t) / shot.dim_out)));
    return f;
  };
  const lightBase = [key, fill, rimA, rimB].map((l) => [l, l.intensity]), envMats = [], seenM = new Set();
  phone.traverse((o) => { const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : []; for (const m of ms) if (!seenM.has(m) && m.envMap) { seenM.add(m); if (glareCap < 1 && m.metalness >= 0.5) m.envMapIntensity *= 0.6 + 0.4 * glareCap; envMats.push([m, m.envMapIntensity]); } });
  const plateGain = plate ? plate.material.color.r : 1;
  // studio: a dark floor that fades out, and a soft contact shadow under the object that thins as it floats up
  const floorY = shot.floor_y ?? -1.3, spot = bd === 'studio' ? softSpot(THREE) : null;
  let floor = null, shadow = null; const box = new THREE.Box3(), bsz = new THREE.Vector3(), bc = new THREE.Vector3();
  if (spot) {
    floor = new THREE.Mesh(new THREE.PlaneGeometry(9, 9), new THREE.MeshStandardMaterial({ color: '#07080a', roughness: 0.6, metalness: 0.1, envMap, envMapIntensity: 0.12, alphaMap: spot, transparent: true, depthWrite: false }));
    floor.rotation.x = -Math.PI / 2; floor.position.y = floorY; floor.renderOrder = 0; scene.add(floor);
    shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: '#000', alphaMap: spot, transparent: true, depthWrite: false, opacity: 0.8 }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = floorY + 0.002; shadow.renderOrder = 1; scene.add(shadow);
  }
  let focusAt = 1.2;
  const mods = await (async () => {
    const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { BokehPass }, { OutputPass }, { TexturePass }, { FullScreenQuad }] = await Promise.all([
      import('/three/addons/postprocessing/EffectComposer.js'), import('/three/addons/postprocessing/RenderPass.js'),
      import('/three/addons/postprocessing/UnrealBloomPass.js'), import('/three/addons/postprocessing/BokehPass.js'), import('/three/addons/postprocessing/OutputPass.js'),
      import('/three/addons/postprocessing/TexturePass.js'), import('/three/addons/postprocessing/Pass.js')]);
    return { EffectComposer, RenderPass, UnrealBloomPass, BokehPass, OutputPass, TexturePass, FullScreenQuad };
  })();
  const dur = Math.max(0.5, (shot.end ?? 0) - (shot.start ?? 0));
  const envSamples = typeof process === 'undefined' ? (globalThis.PRODUCT_SAMPLES ?? globalThis.__PRODUCT_SAMPLES) : process.env.PRODUCT_SAMPLES;
  const N = Math.max(1, Math.min(64, Math.round(Number(envSamples || shot.samples || 8))));
  const fps = shot.fps ?? 30, shutter = shot.shutter ?? 0.5;
  // cam_side "left": the move mirrored left-right (camera, target, phone offset, turn and roll); "right"/unset: as written.
  // frame_side "left"/"right": the picture is shifted so the object sits in that half (text goes in the other); frame_shift 0.2 of the width
  // only upright, mid-sized moves take the side shift; thin and macro moves (profile, edge, port, buttons, screen, island...) stay centred
  const SIDE_OK = ['hero', 'monolith', 'orbit', 'flip', 'rise', 'chip', undefined, 'default'];
  const mirror = shot.cam_side === 'left', fShift = !SIDE_OK.includes(shot.move) ? 0 : shot.frame_side === 'left' ? 1 : shot.frame_side === 'right' ? -1 : 0, fAmt = (shot.frame_shift ?? 0.2) * W;
  const pbox = new THREE.Box3(), pv = new THREE.Vector3(), MACRO = ['island', 'island_old', 'screen', 'edge', 'port', 'buttons', 'chip_macro'];
  // the object's projected box in pixels (no view offset), or null when it is behind the camera
  const projBox = (camera) => {
    holder.updateMatrixWorld(true); pbox.setFromObject(holder);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < 8; i++) {
      pv.set(i & 1 ? pbox.max.x : pbox.min.x, i & 2 ? pbox.max.y : pbox.min.y, i & 4 ? pbox.max.z : pbox.min.z);
      const vz = pv.clone().applyMatrix4(camera.matrixWorldInverse).z; if (vz > -0.01) return null;
      pv.project(camera); const px = (pv.x + 1) / 2 * W, py = (1 - pv.y) / 2 * H;
      x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
    }
    return { x0, x1, y0, y1 };
  };
  let viewX = 0;
  const place = (camera, k, t) => {
    const p = placement(THREE, shot, k, t);
    if (mirror) { p.pos.x = -p.pos.x; p.at.x = -p.at.x; p.phone.x = -p.phone.x; p.q.set(p.q.x, -p.q.y, -p.q.z, p.q.w); p.roll = -p.roll; }
    camera.clearViewOffset();
    holder.quaternion.copy(p.q); holder.position.copy(p.phone);
    if (phone.userData.update) phone.userData.update(k, t);
    camera.fov = p.fov; camera.aspect = W / H; camera.updateProjectionMatrix();
    camera.position.copy(p.pos); camera.up.set(Math.sin(p.roll), Math.cos(p.roll), 0); camera.lookAt(p.at); camera.updateMatrixWorld(true);
    // keep the object in the picture: a wide move whose object drifts off-centre is re-aimed at it and pulled in when it reads small;
    // a macro is re-aimed only when its subject has slid mostly out of frame
    let b = projBox(camera);
    if (b && shot.move !== 'rise') {
      const cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2, bw = b.x1 - b.x0, bh = b.y1 - b.y0;
      const ix = Math.max(0, Math.min(W, b.x1) - Math.max(0, b.x0)), iy = Math.max(0, Math.min(H, b.y1) - Math.max(0, b.y0));
      const macro = MACRO.includes(shot.move), seenFrac = (ix * iy) / Math.max(1, Math.min(bw, W) * Math.min(bh, H));
      // the re-aim blends in smoothly (0 inside a dead zone, rising to its full weight): a hard threshold made the picture jump mid-shot (a visible
      // hiccup at 5.5 s of the first trailer, 2026-10-28)
      const off = macro ? clamp01((0.75 - seenFrac) / 0.25) : Math.max(clamp01((Math.abs(cx - W / 2) - W * 0.06) / (W * 0.12)), clamp01((Math.abs(cy - H / 2) - H * 0.07) / (H * 0.14)));
      const w = (macro ? 0.5 : 0.85) * ease(off);
      if (w > 0.001) { pbox.getCenter(pv); p.at.lerp(pv, w); camera.lookAt(p.at); camera.updateMatrixWorld(true); b = projBox(camera) || b; }
      const big = Math.max((b.x1 - b.x0) / W, (b.y1 - b.y0) / H);
      if (!macro && big < 0.42) {   // too small: dolly in toward the target until it fills ~half the frame
        const f = Math.min(2.5, 0.42 / Math.max(0.05, big));
        camera.position.lerp(p.at, 1 - 1 / f); camera.lookAt(p.at); camera.updateMatrixWorld(true); b = projBox(camera) || b;
      }
    }
    focusAt = camera.position.distanceTo(p.at);
    viewX = fShift * fAmt;
    if (viewX && b) {   // clamp so >= 90% of the object's width stays inside the frame
      const bw = b.x1 - b.x0, slack = 0.05 * bw;
      viewX = Math.max(b.x1 - W - slack, Math.min(b.x0 + slack, viewX));
      if (fShift > 0) viewX = Math.max(0, viewX); else viewX = Math.min(0, viewX);
    }
    if (viewX) camera.setViewOffset(W, H, viewX, 0, W, H); else camera.clearViewOffset();
    // the glow stands behind the phone as seen from the camera, off to one side
    const dir = new THREE.Vector3().subVectors(holder.position, camera.position).normalize();
    const side = new THREE.Vector3().crossVectors(dir, camera.up).normalize(), up = new THREE.Vector3().crossVectors(side, dir).normalize();
    const at = shot.wash_at || [0.25, -0.1];
    glow.position.copy(holder.position).addScaledVector(dir, 4.5).addScaledVector(side, at[0] * 5).addScaledVector(up, at[1] * 5);
    rimA.position.copy(holder.position).addScaledVector(dir, 2.2).addScaledVector(side, -2.4).addScaledVector(up, 1.2);
    rimB.position.copy(holder.position).addScaledVector(dir, 2.0).addScaledVector(side, 2.6).addScaledVector(up, -0.6);
    if (plate) {   // fills the view with a margin, drifting slowly so the light is never still
      const h = 2 * PD * Math.tan(p.fov * Math.PI / 360) * (1.18 + (fShift ? 2.2 * (shot.frame_shift ?? 0.2) : 0)), fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
      const cx = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion), cy = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
      plate.position.copy(camera.position).addScaledVector(fwd, PD).addScaledVector(cx, Math.sin(t * 0.11) * h * 0.03).addScaledVector(cy, Math.sin(t * 0.07 + 1) * h * 0.02);
      plate.quaternion.copy(camera.quaternion); plate.scale.set(h * W / H, h, 1);
    }
    // the reveal kit at t
    const on = live ? (powerOn < 0 ? 1 : clamp01((t - powerOn) / 0.5)) : 1, f = dimF(t);
    if (live) live.update(t, on);
    for (const [l, b] of lightBase) l.intensity = b * f;
    for (const [m, b] of envMats) m.envMapIntensity = b * f;
    if (plate) plate.material.color.setScalar(plateGain * lerp(0.4, 1, f));
    if (halo) { halo.position.copy(holder.position).addScaledVector(dir, 0.8); halo.material.opacity = 0.55 * on; }
    if (streak) {   // right to left across the back; on a reveal it is done before the turn
      const span = shot.move === 'reveal' ? Math.max(0.5, (shot.turn_at ?? 0.45) * dur0 + 0.3) : dur0;
      streak.material.uniforms.c.value = lerp(0.75, -0.75, clamp01(t / span)); streak.material.uniforms.amt.value = 0.34 * f * streak.userData.gain;
    }
    if (puffs) {   // dry ice along the bottom of the frame: some puffs behind the phone, most in front, drifting, curling, breathing
      const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion), cx = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion), cy = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
      const d0 = camera.position.distanceTo(holder.position), tf = Math.tan(camera.fov * Math.PI / 360);
      for (const P of puffs) {
        const depth = Math.max(0.4, d0 + (P.back ? 0.35 + 0.9 * P.dz : -(0.15 + 0.7 * P.dz))), hh = depth * tf, hw = hh * W / H;
        const u = (((P.x0 + P.v * t) % 1) + 1) % 1, x = u * 2.6 - 1.3, y = -1 + fogH * 2 * (0.05 + 0.55 * P.y) + 0.03 * Math.sin(t * 0.5 + P.ph);
        P.sp.position.copy(camera.position).addScaledVector(fwd, depth).addScaledVector(cx, x * hw).addScaledVector(cy, y * hh);
        const sz = P.s * hh * fogH * 1.9; P.sp.scale.set(sz * 2, sz, 1); P.sp.material.rotation = P.rot + P.spin * t;
        P.sp.material.opacity = P.a * (1 - clamp01((Math.abs(x) - 1.0) / 0.3)) * (0.75 + 0.25 * Math.sin(t * 0.6 + P.ph));
        P.sp.material.color.copy(fogCol).multiplyScalar(0.45 + 0.55 * f);
      }
    }
    if (floor) {
      floor.visible = shadow.visible = camera.position.y > floorY + 0.05;
      holder.updateMatrixWorld(true); box.setFromObject(holder); box.getSize(bsz); box.getCenter(bc);
      const gap = Math.max(0, box.min.y - floorY);
      shadow.position.x = bc.x; shadow.position.z = bc.z; shadow.scale.set(bsz.x * 1.5 + 0.3 + gap * 0.6, bsz.z * 1.5 + 0.35 + gap * 0.6, 1);
      shadow.material.opacity = 0.85 * clamp01(1 - gap / 1.2);
    }
  };
  // swaps a re-baked environment onto every material that holds the old one
  const swapEnv = (ch) => {
    if (!ch) return; envMap = ch.to; scene.environment = envMap;
    scene.traverse((o) => { const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : []; for (const m of ms) if (m.envMap === ch.from) m.envMap = envMap; });
  };
  let sub = null, fin = null, acc = null, addQuad = null, dof = null;
  const build = (camera) => {
    sub = new mods.EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 })); sub.setPixelRatio(1); sub.setSize(W, H); sub.renderToScreen = false;
    sub.addPass(new mods.RenderPass(scene, camera));
    if (shot.dof !== false && ['island', 'monolith', 'screen', 'edge', 'chip_macro', 'port', 'buttons'].includes(shot.move)) {
      dof = new mods.BokehPass(scene, camera, { focus: 1.2, aperture: shot.aperture ?? 0.03, maxblur: shot.maxblur ?? 0.012 }); sub.addPass(dof);
    }
    acc = new THREE.WebGLRenderTarget(W, H, { type: THREE.FloatType, depthBuffer: false });
    addQuad = new mods.FullScreenQuad(new THREE.ShaderMaterial({ uniforms: { tDiffuse: { value: null }, w: { value: 1 } }, depthTest: false, depthWrite: false, transparent: true,
      blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneFactor, blendEquation: THREE.AddEquation,
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'uniform sampler2D tDiffuse; uniform float w; varying vec2 vUv; void main(){ gl_FragColor = vec4(texture2D(tDiffuse, vUv).rgb * w, w); }' }));
    fin = new mods.EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType })); fin.setPixelRatio(1); fin.setSize(W, H);
    fin.addPass(new mods.TexturePass(acc.texture));
    fin.addPass(new mods.UnrealBloomPass(new THREE.Vector2(W, H), (shot.bloom ?? 0.55) * (glareCap < 1 ? 0.35 + 0.4 * glareCap : NEAR ? 0.7 : 1), 0.65, glareCap < 1 ? 0.95 : 0.88));
    fin.addPass(new mods.OutputPass());
  };
  return {
    scene,
    place,
    // N sub-frames spread over the shutter (k and t evaluated at each sub-time) with a subpixel jitter, averaged in linear light, then
    // bloom and the output transform once. Without k/t (an older caller) the frame placed last is drawn N times with jitter only.
    render(renderer, camera, k, t) {
      if (!sub) build(camera);
      const timed = typeof t === 'number';
      if (timed) swapEnv(studio.update(t));
      const clear = renderer.getClearColor(new THREE.Color()), ca = renderer.getClearAlpha();
      renderer.setRenderTarget(acc); renderer.setClearColor(0x000000, 0); renderer.clear(); renderer.setClearColor(clear, ca);
      for (let i = 0; i < N; i++) {
        if (timed && N > 1) { const ti = t + ((i + 0.5) / N - 0.5) * shutter / fps; place(camera, clamp01(ti / dur), ti); }
        if (N > 1) camera.setViewOffset(W, H, viewX + halton(i + 1, 2) - 0.5, halton(i + 1, 3) - 0.5, W, H);
        if (dof) dof.uniforms.focus.value = focusAt;
        sub.render();
        addQuad.material.uniforms.tDiffuse.value = sub.readBuffer.texture; addQuad.material.uniforms.w.value = 1 / N;
        renderer.setRenderTarget(acc); const ac = renderer.autoClear; renderer.autoClear = false; addQuad.render(renderer); renderer.autoClear = ac;
      }
      if (timed && N > 1) place(camera, k, t); else if (viewX) camera.setViewOffset(W, H, viewX, 0, W, H); else camera.clearViewOffset();   // leave the camera where the frame's centre time puts it
      renderer.setRenderTarget(null);
      fin.render();
    },
  };
}
