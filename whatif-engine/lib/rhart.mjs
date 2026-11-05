// Rules Horror art, part 2: filled animal silhouettes, props, a crowd grid, documents, a phone, CCTV, a giant eye, bubbles, banners, rule-card parts.
// All pure functions of (g, t, sizes). White on black, one red accent, a little yellow for a light or an eye (like the references).
import { WHITE, RED, DIM, BLACK, clamp01, smooth, wrapText, typedCount, poseAt, skeleton, drawFigure, lineWidth } from './rhkit.mjs';
export const YELLOW = '#E8C21A';
const TAU = Math.PI * 2;
const hash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

// ---------------------------------------------------------------- animals: a solid white silhouette (deer, dog)
// Local units: 1.0 = the animal's full standing height; x forward, y up is negative. Facing -1 mirrors.
const ANIMALS = {
  deer: { body: [0, -0.54, 0.29, 0.125], hip: -0.45, legs: [0.20, 0.12, -0.2, -0.12], legW: 0.034, knee: 0.03, base: [0.2, -0.60], head: [0.36, -0.86], hr: [0.09, 0.042], neckW: [0.095, 0.058], tail: [-0.27, -0.58], antlers: true, ears: 0.05 },
  dog: { body: [0, -0.60, 0.34, 0.15], hip: -0.50, legs: [0.25, 0.17, -0.25, -0.17], legW: 0.058, knee: 0.04, base: [0.27, -0.68], head: [0.47, -0.86], hr: [0.105, 0.055], neckW: [0.14, 0.09], tail: [-0.33, -0.66], antlers: false, ears: 0.075 },
};
export const ANIMAL_NAMES = Object.keys(ANIMALS);
export const ANIMAL_POSES = ['stand', 'head_low', 'stare', 'walk', 'raise_paw'];

// A dog drawn as one smooth shape: deep chest, tucked belly, a long muzzle, big pointed ears, thin bent legs and a low tail.
function drawDog(g, pose, x, ground, size, facing, t, eye, fill = WHITE) {
  g.save(); g.translate(x, ground); g.scale(size * (facing < 0 ? -1 : 1), size);
  g.fillStyle = fill; g.strokeStyle = fill; g.lineCap = 'round'; g.lineJoin = 'round';
  const breath = Math.sin(t * 1.4) * 0.004, walk = pose === 'walk';
  let dx = 0, dy = 0; if (pose === 'head_low') { dx = 0.14; dy = 0.34; } else if (pose === 'stare') { dx = 0.03; dy = 0.0; }
  dx += Math.sin(t * 0.8) * 0.006; dy += breath * 2;
  const hp = (px, py) => [px + dx, py + dy];
  const legs = [[0.24, 0, 0.22], [0.16, 0, 0.14], [-0.36, 1, 0.5], [-0.28, 1, 0.5]];     // x at the body, hind (1) or front (0), phase
  legs.forEach(([lx, hind, ph], i) => {
    const sw = walk ? Math.sin(t * 3.4 + ph * 6.28 + i) * 0.08 : 0, lift = walk ? Math.max(0, Math.cos(t * 3.4 + ph * 6.28 + i)) * 0.04 : 0;
    g.lineWidth = hind ? 0.05 : 0.04; g.beginPath(); g.moveTo(lx, -0.5);
    if (pose === 'raise_paw' && i === 0) { g.lineTo(lx + 0.1, -0.36); g.lineTo(lx + 0.2, -0.38); g.stroke(); return; }
    if (hind) { g.lineTo(lx - 0.07 + sw * 0.5, -0.24); g.lineTo(lx - 0.02 + sw, -lift); } else { g.lineTo(lx + 0.01 + sw * 0.5, -0.24); g.lineTo(lx + 0.015 + sw, -lift); }
    g.stroke(); g.lineWidth = 0.055; g.beginPath(); g.moveTo(lx + (hind ? -0.02 : 0.015) + sw, -lift); g.lineTo(lx + (hind ? 0.04 : 0.075) + sw, -lift); g.stroke();
  });
  g.lineWidth = 0.05; g.beginPath(); g.moveTo(-0.44, -0.6); g.quadraticCurveTo(-0.62, -0.5, -0.6, -0.26 + Math.sin(t * 2) * 0.01); g.stroke();                 // tail
  g.beginPath(); g.moveTo(-0.44, -0.64);
  g.quadraticCurveTo(-0.1, -0.7 + breath, 0.16, -0.66);                                                            // back to the withers
  g.lineTo(...hp(0.30, -0.78)); g.lineTo(...hp(0.40, -0.9)); g.lineTo(...hp(0.46, -0.9));                           // neck up to the crown
  g.lineTo(...hp(0.70, -0.76)); g.lineTo(...hp(0.66, -0.72)); g.lineTo(...hp(0.46, -0.72)); g.lineTo(...hp(0.34, -0.62));   // muzzle, jaw, throat
  g.quadraticCurveTo(0.34, -0.46, 0.22, -0.4);                                                                    // chest
  g.quadraticCurveTo(-0.05, -0.38, -0.32, -0.46); g.quadraticCurveTo(-0.5, -0.48, -0.46, -0.6); g.closePath(); g.fill();
  const [e1x, e1y] = hp(0.40, -0.9), [e2x, e2y] = hp(0.46, -0.9);                                                   // ears
  g.beginPath(); g.moveTo(e1x - 0.02, e1y + 0.02); g.lineTo(e1x - 0.02, e1y - 0.13); g.lineTo(e1x + 0.07, e1y + 0.0); g.closePath(); g.fill();
  g.beginPath(); g.moveTo(e2x - 0.03, e2y + 0.0); g.lineTo(e2x + 0.04, e2y - 0.13); g.lineTo(e2x + 0.09, e2y + 0.05); g.closePath(); g.fill();
  if (eye) { const [ex, ey] = hp(0.50, -0.82), gr = g.createRadialGradient(ex, ey, 0, ex, ey, 0.05); gr.addColorStop(0, `${eye}cc`); gr.addColorStop(1, `${eye}00`);
    g.fillStyle = gr; g.beginPath(); g.arc(ex, ey, 0.05, 0, TAU); g.fill(); g.fillStyle = eye; g.beginPath(); g.arc(ex, ey, 0.014, 0, TAU); g.fill(); }
  g.restore();
  const sgn = facing < 0 ? -1 : 1;
  return { head: [x + (0.46 + dx) * size * sgn, ground + (-0.82 + dy) * size], body: [x, ground - 0.55 * size] };
}

export function drawAnimal(g, kind, pose, x, ground, size, facing, t, { eye = YELLOW, fill = WHITE } = {}) {
  if (kind === 'dog') return drawDog(g, pose, x, ground, size, facing, t, eye, fill);
  const A = ANIMALS[kind] || ANIMALS.deer, s = size;
  g.save(); g.translate(x, ground); g.scale(s * (facing < 0 ? -1 : 1), s);
  g.fillStyle = fill; g.strokeStyle = fill; g.lineCap = 'round'; g.lineJoin = 'round';
  const breath = Math.sin(t * 1.4) * 0.004, sway = Math.sin(t * 0.8) * 0.006;
  let [hx, hy] = A.head;
  if (pose === 'head_low') { hx = kind === 'deer' ? 0.47 : 0.62; hy = kind === 'deer' ? -0.24 : -0.42; } else if (pose === 'stare') { hx += 0.02; hy -= 0.02; }
  hx += sway; hy += breath * 2;
  // legs (behind the body): a walk swings them, raise_paw lifts the near front leg
  const walk = pose === 'walk';
  A.legs.forEach((lx, i) => {
    const ph = t * 3.2 + (i % 2) * Math.PI + (i > 1 ? Math.PI * 0.5 : 0), swing = walk ? Math.sin(ph) * 0.09 : 0, lift = walk ? Math.max(0, Math.cos(ph)) * 0.04 : 0;
    let kx = lx + swing * 0.5 + A.knee, ky = A.hip / 2, fx = lx + swing, fy = -lift;
    if (pose === 'raise_paw' && i === 0) { kx = lx + 0.12; ky = A.hip + 0.12; fx = lx + 0.2; fy = A.hip + 0.2; }
    g.lineWidth = A.legW; g.beginPath(); g.moveTo(lx, A.hip); g.lineTo(kx, ky); g.lineTo(fx, fy); g.stroke();
    g.lineWidth = A.legW * 1.35; g.beginPath(); g.moveTo(fx, fy); g.lineTo(fx + 0.012, fy); g.stroke();
  });
  // tail
  g.lineWidth = A.legW * (kind === 'dog' ? 0.55 : 1.2); g.beginPath(); g.moveTo(A.tail[0] + 0.1, A.tail[1] + 0.06); g.quadraticCurveTo(A.tail[0] - 0.03, A.tail[1] + (kind === 'dog' ? 0.1 : 0.03), A.tail[0] - 0.05, A.tail[1] + (kind === 'dog' ? 0.26 : 0.0)); g.stroke();
  // body
  g.beginPath(); g.ellipse(A.body[0], A.body[1] + breath, A.body[2], A.body[3] + breath, 0, 0, TAU); g.fill();
  // neck: a tapered quad from the shoulder to the head
  const [bx, by] = A.base, ang = Math.atan2(hy - by, hx - bx), nx = -Math.sin(ang), ny = Math.cos(ang);
  g.beginPath();
  g.moveTo(bx + nx * A.neckW[0], by + ny * A.neckW[0]); g.lineTo(hx + nx * A.neckW[1], hy + ny * A.neckW[1]);
  g.lineTo(hx - nx * A.neckW[1], hy - ny * A.neckW[1]); g.lineTo(bx - nx * A.neckW[0], by - ny * A.neckW[0]); g.closePath(); g.fill();
  // head: an ellipse pointing along the neck's direction, tipped a little downward (a snout)
  const tilt = ang * 0.35 + 0.28;
  g.save(); g.translate(hx, hy); g.rotate(tilt); g.beginPath(); g.ellipse(A.hr[0] * 0.45, 0, A.hr[0], A.hr[1], 0, 0, TAU); g.fill();
  if (kind === 'dog') { g.beginPath(); g.moveTo(A.hr[0] * 0.9, -A.hr[1] * 0.6); g.lineTo(A.hr[0] * 1.7, A.hr[1] * 0.1); g.lineTo(A.hr[0] * 0.9, A.hr[1] * 0.7); g.closePath(); g.fill(); }
  g.restore();
  // ears
  g.beginPath(); g.moveTo(hx - 0.01, hy - A.hr[1] * 0.7); g.lineTo(hx - 0.04, hy - A.hr[1] * 0.7 - A.ears * 1.5); g.lineTo(hx + 0.03, hy - A.hr[1] * 0.9); g.closePath(); g.fill();
  g.beginPath(); g.moveTo(hx + 0.02, hy - A.hr[1] * 0.8); g.lineTo(hx + 0.04, hy - A.hr[1] * 0.8 - A.ears * 1.4); g.lineTo(hx + 0.07, hy - A.hr[1] * 0.5); g.closePath(); g.fill();
  if (A.antlers) {                                                       // a main beam sweeping back and up, with three tines on each side
    g.lineWidth = 0.011;
    for (const side of [0, 1]) {
      const ox = hx + 0.005 + side * 0.03, oy = hy - A.hr[1] * 0.9;
      g.beginPath(); g.moveTo(ox, oy); g.quadraticCurveTo(ox - 0.06, oy - 0.1, ox - 0.03 - side * 0.01, oy - 0.2); g.stroke();
      for (const k of [0.35, 0.6, 0.85]) { const px = ox - 0.05 * k - side * 0.004, py = oy - 0.2 * k; g.beginPath(); g.moveTo(px, py); g.lineTo(px + 0.05, py - 0.06); g.stroke(); }
    }
  }
  if (eye) {                                                             // a small glowing eye (blinks rarely)
    const blink = (t % 6.3) > 6.18 ? 0.25 : 1, ex = hx + A.hr[0] * 0.55, ey = hy - A.hr[1] * 0.15;
    const gr = g.createRadialGradient(ex, ey, 0, ex, ey, 0.05); gr.addColorStop(0, `${eye}cc`); gr.addColorStop(1, `${eye}00`);
    g.fillStyle = gr; g.beginPath(); g.arc(ex, ey, 0.05, 0, TAU); g.fill();
    g.fillStyle = eye; g.beginPath(); g.ellipse(ex, ey, 0.014, 0.012 * blink, 0, 0, TAU); g.fill();
  }
  g.restore();
  return { head: [x + hx * s * (facing < 0 ? -1 : 1), ground + hy * s], body: [x, ground + A.body[1] * s] };
}

// ---------------------------------------------------------------- props
const sheet = (g, x, y, w, h, rot = 0) => {
  g.save(); g.translate(x, y); g.rotate(rot); g.fillStyle = '#EDEDED'; g.fillRect(-w / 2, -h / 2, w, h); g.restore(); return () => {};
};
const inkLines = (g, x0, y0, w, n, gap, t, seed, color = '#7a7a7a') => {
  g.strokeStyle = color; g.lineWidth = Math.max(1.5, gap * 0.09); g.lineCap = 'round';
  for (let i = 0; i < n; i++) { const len = w * (0.55 + 0.4 * hash(seed + i)); g.beginPath(); g.moveTo(x0, y0 + i * gap); g.lineTo(x0 + len, y0 + i * gap); g.stroke(); }
};
const drawPencil = (g, x, y, len, rot, lw) => {
  g.save(); g.translate(x, y); g.rotate(rot); g.lineCap = 'butt';
  g.fillStyle = YELLOW; g.fillRect(0, -lw, len, lw * 2); g.fillStyle = '#d9a99a'; g.beginPath(); g.moveTo(0, -lw); g.lineTo(-lw * 3, 0); g.lineTo(0, lw); g.closePath(); g.fill();
  g.fillStyle = '#333'; g.beginPath(); g.moveTo(-lw * 2, -lw * 0.3); g.lineTo(-lw * 3, 0); g.lineTo(-lw * 2, lw * 0.3); g.closePath(); g.fill();
  g.fillStyle = '#c33'; g.fillRect(len, -lw, lw * 2, lw * 2); g.restore();
};

/** kinds: paper (a test sheet and a pencil), note (a folded paper with a name), clock, phone (chat), report (in-world document), eye, cctv (overlay), door_feet */
export function drawProp(g, kind, W, H, t, age, d, fam, pal = null) {
  const cx = W / 2, cy = H / 2, u = H;
  if (kind === 'paper' || kind === 'report') {
    const w = u * 0.62, h = u * 0.84, done = sheet(g, cx, cy - u * 0.01, w, h, Math.sin(t * 0.5) * 0.012);
    g.fillStyle = '#222'; g.font = `700 ${Math.round(u * 0.027)}px ${fam}`; g.textAlign = 'left'; g.textBaseline = 'middle';
    g.fillText(String(d.title || (kind === 'report' ? 'INCIDENT REPORT' : 'CHEMISTRY - UNIT 4 TEST')).toUpperCase(), cx - w * 0.42, cy - h * 0.43);
    g.fillStyle = RED; g.fillRect(cx - w * 0.42, cy - h * 0.39, w * 0.84, Math.max(2, u * 0.004));
    const lines = d.lines || (kind === 'report' ? ['FLIGHT 902 / 1994', 'DESTINATION: NEVER ARRIVED', 'STATUS: UNRESOLVED'] : ['1. 2Na + Cl2 -> 2NaCl', '2. conductor bond', '3. electrons are shared']);
    g.fillStyle = '#333'; g.font = `600 ${Math.round(u * 0.03)}px ${fam}`;
    let n = typedCount(age, 26, 0.2);
    lines.forEach((ln, i) => { const part = ln.slice(0, Math.max(0, n)); n -= ln.length; g.fillText(part, cx - w * 0.42, cy - h * 0.28 + i * u * 0.085); });
    inkLines(g, cx - w * 0.42, cy - h * 0.28 + lines.length * u * 0.085, w * 0.84, 7, u * 0.065, t, 7);
    done();
    if (kind === 'paper' && d.pencil !== false) {                                            // the pencil writes: a small circling motion
      const px = cx - w * 0.05 + Math.sin(t * 2.3) * u * 0.05, py = cy + h * 0.05 + Math.cos(t * 1.7) * u * 0.02;
      drawPencil(g, px, py, u * 0.28, -2.2 + Math.sin(t * 2.3) * 0.06, u * 0.012);
    }
    if (d.red_corners) { g.strokeStyle = RED; g.lineWidth = u * 0.005; const c = u * 0.03; for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) { g.beginPath(); g.moveTo(cx + sx * w * 0.6, cy + sy * h * 0.55 - sy * c); g.lineTo(cx + sx * w * 0.6, cy + sy * h * 0.55); g.lineTo(cx + sx * w * 0.6 - sx * c, cy + sy * h * 0.55); g.stroke(); } }
  } else if (kind === 'note') {                                                              // a folded triangle with a name on it
    const s = u * 0.34, k = smooth(age / 0.4);
    g.save(); g.translate(cx, cy + u * 0.04); g.rotate((1 - k) * 0.5); g.scale(0.7 + 0.3 * k, 0.7 + 0.3 * k);
    g.fillStyle = '#F2F2F2'; g.beginPath(); g.moveTo(0, -s); g.lineTo(s * 1.05, s * 0.7); g.lineTo(-s * 1.05, s * 0.7); g.closePath(); g.fill();
    g.fillStyle = '#d4d4d4'; g.beginPath(); g.moveTo(0, -s); g.lineTo(0, s * 0.7); g.lineTo(-s * 1.05, s * 0.7); g.closePath(); g.fill();
    g.fillStyle = '#222'; g.font = `italic 600 ${Math.round(u * 0.07)}px ${fam}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.save(); g.rotate(-0.05); g.fillText(String(d.text || 'Jordan'), 0, s * 0.35); g.restore();
    g.restore();
  } else if (kind === 'clock') {
    const r = u * 0.28; g.save(); g.translate(cx, cy);
    g.fillStyle = '#EDEDED'; g.beginPath(); g.arc(0, 0, r, 0, TAU); g.fill(); g.strokeStyle = WHITE; g.lineWidth = u * 0.012; g.stroke();
    g.strokeStyle = '#222'; g.lineWidth = u * 0.008; for (let i = 0; i < 12; i++) { const a = i * TAU / 12; g.beginPath(); g.moveTo(Math.sin(a) * r * 0.84, -Math.cos(a) * r * 0.84); g.lineTo(Math.sin(a) * r * 0.95, -Math.cos(a) * r * 0.95); g.stroke(); }
    const hand = (a, l, w, c) => { g.strokeStyle = c; g.lineWidth = w; g.lineCap = 'round'; g.beginPath(); g.moveTo(0, 0); g.lineTo(Math.sin(a) * r * l, -Math.cos(a) * r * l); g.stroke(); };
    const mins = (d.minute ?? 41) + age * 0.0 , stepped = Math.floor(age * 2) / 2;
    hand(((d.hour ?? 3) + mins / 60) * TAU / 12, 0.5, u * 0.014, '#222'); hand(mins * TAU / 60, 0.78, u * 0.009, '#222'); hand((stepped * 6 + (d.second ?? 0)) * TAU / 60 * 1, 0.85, u * 0.004, RED);
    g.restore();
  } else if (kind === 'phone') {
    const w = u * 0.4, h = u * 0.82; g.save(); g.translate(cx, cy);
    g.fillStyle = '#101216'; g.beginPath(); g.roundRect(-w / 2, -h / 2, w, h, u * 0.04); g.fill(); g.strokeStyle = WHITE; g.lineWidth = u * 0.006; g.stroke();
    g.font = `600 ${Math.round(u * 0.028)}px ${fam}`; g.textBaseline = 'middle'; g.textAlign = 'left';
    const msgs = d.messages || [['them', 'im fine lol'], ['them', 'made it home'], ['them', 'wanna see another movie?']];
    msgs.forEach(([who, txt], i) => {
      const at = 0.3 + i * 0.9, k = smooth((age - at) / 0.25); if (k <= 0) return;
      const bw = Math.min(w * 0.8, g.measureText(txt).width + u * 0.04), by = -h * 0.36 + i * u * 0.095;
      g.globalAlpha = k; g.fillStyle = who === 'me' ? '#2a5bd7' : '#2b2e35'; g.beginPath(); g.roundRect(who === 'me' ? w / 2 - bw - u * 0.03 : -w / 2 + u * 0.03, by, bw, u * 0.07, u * 0.03); g.fill();
      g.fillStyle = WHITE; g.fillText(txt, (who === 'me' ? w / 2 - bw - u * 0.03 : -w / 2 + u * 0.03) + u * 0.02, by + u * 0.036); g.globalAlpha = 1;
    });
    g.restore();
  } else if (kind === 'eye') {                                                               // a giant eye: opens, the iris looks about
    const open = smooth(age / 0.35), w = W * 0.7, h = H * 0.5 * open;
    g.save(); g.translate(cx, cy); g.fillStyle = '#EDEDED'; g.beginPath(); g.moveTo(-w / 2, 0); g.quadraticCurveTo(0, -h * 1.1, w / 2, 0); g.quadraticCurveTo(0, h * 1.1, -w / 2, 0); g.fill();
    g.save(); g.beginPath(); g.moveTo(-w / 2, 0); g.quadraticCurveTo(0, -h * 1.1, w / 2, 0); g.quadraticCurveTo(0, h * 1.1, -w / 2, 0); g.clip();
    const ix = Math.sin(t * 0.9) * w * 0.07, ir = H * 0.2; g.fillStyle = '#16181c'; g.beginPath(); g.arc(ix, 0, ir, 0, TAU); g.fill();
    g.fillStyle = d.color === 'red' ? RED : '#000'; g.beginPath(); g.arc(ix, 0, ir * 0.45, 0, TAU); g.fill(); g.restore();
    g.strokeStyle = WHITE; g.lineWidth = u * 0.008; g.beginPath(); g.moveTo(-w / 2, 0); g.quadraticCurveTo(0, -h * 1.1, w / 2, 0); g.quadraticCurveTo(0, h * 1.1, -w / 2, 0); g.stroke(); g.restore();
  } else if (kind === 'cctv') {
    const m = W * 0.035, lw = Math.max(2, u * 0.006); g.save(); g.strokeStyle = 'rgba(242,242,242,0.85)'; g.lineWidth = lw;
    const c = u * 0.05; for (const [sx, sy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) { const x = sx ? W - m : m, y = sy ? H - m : m, dx = sx ? -c : c, dy = sy ? -c : c; g.beginPath(); g.moveTo(x + dx, y); g.lineTo(x, y); g.lineTo(x, y + dy); g.stroke(); }
    g.font = `700 ${Math.round(u * 0.03)}px ${fam}`; g.fillStyle = WHITE; g.textBaseline = 'top'; g.textAlign = 'left';
    if (Math.floor(t * 1.2) % 2 === 0) { g.fillStyle = RED; g.beginPath(); g.arc(m + u * 0.016, m + u * 0.05, u * 0.011, 0, TAU); g.fill(); }
    g.fillStyle = WHITE; g.fillText('REC', m + u * 0.04, m + u * 0.035); g.textAlign = 'right'; g.fillText(String(d.label || 'CAM 02 FRONT YARD'), W - m - u * 0.01, m + u * 0.035);
    const sec = Math.floor((d.clock ?? 10800) + t), hh = String(Math.floor(sec / 3600) % 24).padStart(2, '0'), mi = String(Math.floor(sec / 60) % 60).padStart(2, '0'), ss = String(sec % 60).padStart(2, '0');
    g.textBaseline = 'bottom'; g.fillText(`${hh}:${mi}:${ss}`, W - m - u * 0.01, H - m - u * 0.02);
    g.fillStyle = 'rgba(255,255,255,0.05)'; for (let y = 0; y < H; y += 4) g.fillRect(0, y, W, 1);
    g.restore();
  } else if (kind === 'door_feet') {                                                         // a door with a strip of light under it and two shadows of feet
    const w = u * 0.5, h = u * 0.86, gy = H * 0.9; g.save(); g.strokeStyle = WHITE; g.lineWidth = Math.max(2, u * 0.006);
    g.strokeRect(cx - w / 2, gy - h, w, h); g.beginPath(); g.arc(cx + w * 0.36, gy - h * 0.48, u * 0.012, 0, TAU); g.stroke();
    g.fillStyle = '#d8d19a'; g.fillRect(cx - w * 0.46, gy - u * 0.012, w * 0.92, u * 0.012);
    const on = smooth((age - 0.4) / 0.2); g.fillStyle = BLACK; g.globalAlpha = on; g.fillRect(cx - w * 0.2, gy - u * 0.014, w * 0.12, u * 0.014); g.fillRect(cx + w * 0.08, gy - u * 0.014, w * 0.12, u * 0.014); g.restore();
  } else if (kind === 'ring_hand') {                                                         // the back of a hand with a ring: it is on the wrong hand (flip_at swaps left to right with a flash)
    const flipped = d.flip_at != null && t >= d.flip_at, side = flipped ? (d.side === 'left' ? 'right' : 'left') : (d.side || 'left');
    const skin = pal ? pal.skin[0] : '#EDEDED';
    drawHand(g, cx, cy + u * 0.08 - smooth(age / 0.5) * u * 0.02, u * 1.5, side, skin, 'rgba(0,0,0,0.35)', true);
    if (flipped && t - d.flip_at < 0.18) { g.fillStyle = `rgba(255,255,255,${0.5 * (1 - (t - d.flip_at) / 0.18)})`; g.fillRect(0, 0, W, H); }
    g.fillStyle = side === (d.side || 'left') ? WHITE : RED; g.font = `800 ${Math.round(u * 0.04)}px ${fam}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(side === 'left' ? 'LEFT HAND' : 'RIGHT HAND', cx, H * 0.9);
  } else if (kind === 'handprint') {                                                         // fogged glass; a hand pressed on the other side, warm, with drips
    g.fillStyle = pal ? 'rgba(178,200,214,0.96)' : 'rgba(210,210,210,0.92)'; g.fillRect(0, 0, W, H);
    for (let i = 0; i < 40; i++) { const x = hash(i * 3.1) * W, y0 = hash(i * 5.3) * H * 0.6, len = (0.1 + hash(i * 7.9) * 0.3) * H * smooth(age / 2.5); g.strokeStyle = 'rgba(255,255,255,0.35)'; g.lineWidth = Math.max(1.5, u * 0.003); g.beginPath(); g.moveTo(x, y0); g.lineTo(x, y0 + len); g.stroke(); }
    const k = smooth((age - 0.4) / 0.5); g.save(); g.globalAlpha = k;
    drawHand(g, cx, cy + u * 0.05, u * 2.3, 'right', 'rgba(255,214,140,0.55)', 'rgba(255,225,170,0.9)', false); g.restore();
    g.fillStyle = 'rgba(0,0,0,0.25)'; g.fillRect(0, 0, W, H * 0.04);
  } else if (kind === 'phone_black') {                                                       // a phone with a dark screen: a smaller mirror, a face that smiles early
    const w = u * 0.4, h = u * 0.82; g.save(); g.translate(cx, cy);
    g.fillStyle = '#05060a'; g.beginPath(); g.roundRect(-w / 2, -h / 2, w, h, u * 0.04); g.fill(); g.strokeStyle = pal ? pal.line : WHITE; g.lineWidth = u * 0.006; g.stroke();
    g.save(); g.beginPath(); g.roundRect(-w / 2 + u * 0.012, -h / 2 + u * 0.012, w - u * 0.024, h - u * 0.024, u * 0.035); g.clip();
    g.globalAlpha = 0.28 + 0.1 * Math.sin(t * 2); const sk = pal ? pal.skin[0] : '#bbb', r = w * 0.27;
    g.fillStyle = sk; g.beginPath(); g.arc(0, -h * 0.02, r, 0, TAU); g.fill(); g.fillStyle = '#05060a'; for (const ex of [-0.36, 0.36]) { g.beginPath(); g.arc(ex * r, -h * 0.05, r * 0.1, 0, TAU); g.fill(); }
    const sm = d.smile_at != null ? clamp01((t - d.smile_at) / 0.4) : 0; g.strokeStyle = '#05060a'; g.lineWidth = r * 0.07; g.beginPath(); g.arc(0, h * 0.0 + r * 0.1, r * 0.5, 0.2, Math.PI - 0.2); if (sm > 0) g.stroke(); g.globalAlpha = 1;
    g.restore();
    if (d.text) { const k = smooth((age - 0.6) / 0.3); g.globalAlpha = k; g.fillStyle = 'rgba(255,255,255,0.12)'; g.beginPath(); g.roundRect(-w * 0.42, -h * 0.4, w * 0.84, u * 0.07, u * 0.02); g.fill(); g.fillStyle = WHITE; g.font = `600 ${Math.round(u * 0.026)}px ${fam}`; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText(String(d.text), -w * 0.38, -h * 0.4 + u * 0.035); g.globalAlpha = 1; }
    g.restore();
  } else if (kind === 'floorboards') {                                                       // a hallway floor in perspective; the boards light up one by one, and a twelfth that should not exist
    const hy = H * 0.34, n = (d.count ?? 11) + (d.extra ? 1 : 0), cnt = Math.min(n, Math.floor(age / 0.42) + 1), line = pal ? pal.line : WHITE;
    g.fillStyle = pal ? pal.wall : BLACK; g.fillRect(0, 0, W, hy);
    for (let i = 0; i < n + 1; i++) {
      const y0 = hy + (H - hy) * Math.pow(i / (n + 1), 1.7), y1 = hy + (H - hy) * Math.pow((i + 1) / (n + 1), 1.7), hw0 = W * (0.11 + 0.45 * (y0 - hy) / (H - hy)), hw1 = W * (0.11 + 0.45 * (y1 - hy) / (H - hy));
      const lit = i < cnt, extra = d.extra && i === n - 1;
      g.fillStyle = extra && lit ? '#6a1018' : lit ? (pal ? '#6b5236' : '#2c2c2c') : (pal ? '#3d2f22' : '#101010');
      g.beginPath(); g.moveTo(cx - hw0, y0); g.lineTo(cx + hw0, y0); g.lineTo(cx + hw1, y1); g.lineTo(cx - hw1, y1); g.closePath(); g.fill();
      g.strokeStyle = extra && lit ? RED : line; g.lineWidth = Math.max(1.5, u * 0.004); g.stroke();
    }
    g.fillStyle = cnt > (d.count ?? 11) ? RED : WHITE; g.font = `900 ${Math.round(u * 0.16)}px ${fam}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(String(cnt), cx, H * 0.16);
  } else if (kind === 'hair_part') {                                                         // a head seen from above: the parting is on the other side (flip_at)
    const flipped = d.flip_at != null && t >= d.flip_at, side = flipped ? (d.side === 'left' ? 'right' : 'left') : (d.side || 'left'), r = u * 0.34, sg = side === 'left' ? -1 : 1;
    g.save(); g.translate(cx, cy + u * 0.02); g.fillStyle = pal ? pal.hair[1] : '#CFCFCF'; g.beginPath(); g.ellipse(0, 0, r, r * 1.08, 0, 0, TAU); g.fill();
    g.strokeStyle = pal ? pal.skin[0] : BLACK; g.lineWidth = u * 0.012; g.lineCap = 'round'; g.beginPath(); g.moveTo(sg * r * 0.28, -r * 1.0); g.quadraticCurveTo(sg * r * 0.38, -r * 0.2, sg * r * 0.2, r * 0.7); g.stroke();
    g.strokeStyle = 'rgba(0,0,0,0.25)'; g.lineWidth = u * 0.004; for (let i = 0; i < 18; i++) { const a = i / 18 * TAU; g.beginPath(); g.moveTo(Math.cos(a) * r * 0.5, Math.sin(a) * r * 0.5); g.lineTo(Math.cos(a) * r * 0.95, Math.sin(a) * r * 0.95); g.stroke(); }
    g.restore();
    if (flipped && t - d.flip_at < 0.18) { g.fillStyle = `rgba(255,255,255,${0.5 * (1 - (t - d.flip_at) / 0.18)})`; g.fillRect(0, 0, W, H); }
    g.fillStyle = flipped ? RED : WHITE; g.font = `800 ${Math.round(u * 0.04)}px ${fam}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(`PARTED ON THE ${side === 'left' ? 'LEFT' : 'RIGHT'}`, cx, H * 0.9);
  }
}

/** The back of a hand, fingers up. side: left (thumb on the right) | right (thumb on the left). The ring sits on the ring finger. */
function drawHand(g, cx, cy, u, side, fill, stroke, ring) {
  g.save(); g.translate(cx, cy); if (side === 'right') g.scale(-1, 1);
  g.fillStyle = fill; g.strokeStyle = stroke; g.lineWidth = Math.max(1.5, u * 0.004); g.lineJoin = 'round';
  const L = [0.13, 0.17, 0.19, 0.17], px = -0.12 * u, py = -0.02 * u;
  g.beginPath(); g.roundRect(px, py, 0.24 * u, 0.28 * u, 0.05 * u); g.fill(); g.stroke();
  L.forEach((len, k) => { const x = px + 0.012 * u + k * 0.058 * u; g.beginPath(); g.roundRect(x, py - len * u, 0.05 * u, (len + 0.04) * u, 0.025 * u); g.fill(); g.stroke(); });
  g.save(); g.translate(0.12 * u, 0.12 * u); g.rotate(0.85); g.beginPath(); g.roundRect(-0.025 * u, -0.17 * u, 0.055 * u, 0.2 * u, 0.027 * u); g.fill(); g.stroke(); g.restore();
  if (ring) { const x = px + 0.012 * u + 0.058 * u, y = py - 0.17 * u * 0.38; g.strokeStyle = '#d9b44a'; g.lineWidth = u * 0.013; g.beginPath(); g.ellipse(x + 0.025 * u, y, 0.027 * u, 0.012 * u, 0, 0, Math.PI * 2); g.stroke(); g.fillStyle = '#fff3c0'; g.beginPath(); g.arc(x + 0.03 * u, y - 0.012 * u, u * 0.006, 0, Math.PI * 2); g.fill(); }
  g.restore();
}
export const PROP_KINDS = ['paper', 'report', 'note', 'clock', 'phone', 'eye', 'cctv', 'door_feet', 'ring_hand', 'handprint', 'phone_black', 'floorboards', 'hair_part'];

// ---------------------------------------------------------------- crowd grid: seated figures in rows, one of them marked
/** kind classroom: figures behind desks; cinema: figures in front of seat backs. mark = [row, col] (0 = front row); turn = the time every head turns to the viewer. */
export function drawCrowd(g, W, H, t, d, fam, pal = null) {
  const rows = d.rows ?? 4, cols = d.cols ?? 9, kind = d.kind || 'classroom', mark = d.mark || null, age = t - (d.start ?? 0);
  const top = H * 0.30, bottom = H * 0.80;
  if (kind === 'cinema' && d.screen !== false) {                      // the screen: a pale rectangle with a small sad face on it
    g.fillStyle = '#D9DDE3'; g.fillRect(W * 0.3, H * 0.04, W * 0.4, H * 0.2); g.fillStyle = '#7a7f88'; g.beginPath(); g.arc(W * 0.5, H * 0.14, H * 0.06, 0, TAU); g.fill();
    g.strokeStyle = '#2a2a2a'; g.lineWidth = Math.max(2, H * 0.006); g.beginPath(); g.arc(W * 0.5, H * 0.165, H * 0.02, Math.PI * 1.15, Math.PI * 1.85); g.stroke();
    g.strokeStyle = RED; g.lineWidth = Math.max(2, H * 0.005); g.strokeRect(W * 0.07, H * 0.05, W * 0.04, H * 0.03); g.strokeRect(W * 0.89, H * 0.05, W * 0.04, H * 0.03);
  }
  for (let r = rows - 1; r >= 0; r--) {                              // back rows first, so the front rows cover them
    const rowY = bottom - (bottom - top) * (r / rows) * 0.92, headR = H * 0.034 * (1.25 - 0.55 * (r / rows)), gapX = W * 0.9 / cols * (1.0 - 0.2 * (r / rows));
    for (let c = 0; c < cols; c++) {
      const x = W / 2 + (c - (cols - 1) / 2) * gapX + (r % 2 ? gapX * 0.5 : 0), isM = mark && mark[0] === r && mark[1] === c;
      const back = hash(r * 31 + c) > 0.5;
      if (kind === 'cinema') {
        g.fillStyle = '#1a1a1a'; g.strokeStyle = DIM; g.lineWidth = 1.5; g.beginPath(); g.roundRect(x - headR * 1.7, rowY - headR * 0.8, headR * 3.4, headR * 3.6, headR * 0.6); g.fill(); g.stroke();
      }
      const turned = d.turn != null && t >= d.turn + hash(r * 17 + c) * 0.5;
      const pk = Math.floor(hash(r * 7 + c * 13) * 997);
      g.fillStyle = pal ? pal.skin[pk % pal.skin.length] : (isM ? WHITE : (turned ? '#EDEDED' : '#BDBDBD'));
      g.beginPath(); g.arc(x, rowY - headR * 0.4, headR, 0, TAU); g.fill();                              // head
      g.fillStyle = pal ? pal.shirt[(pk >> 2) % pal.shirt.length] : g.fillStyle;
      g.beginPath(); g.roundRect(x - headR * 1.25, rowY + headR * 0.7, headR * 2.5, headR * 2.2, headR * 0.5); g.fill();                    // shoulders
      if (turned || isM) {                                                                                  // faces: the eyes and a wide mouth
        g.fillStyle = '#111'; g.beginPath(); g.arc(x - headR * 0.35, rowY - headR * 0.5, headR * 0.12, 0, TAU); g.arc(x + headR * 0.35, rowY - headR * 0.5, headR * 0.12, 0, TAU); g.fill();
        if (turned && kind === 'cinema') { g.strokeStyle = '#111'; g.lineWidth = Math.max(1.5, headR * 0.09); g.beginPath(); g.arc(x, rowY - headR * 0.35, headR * 0.6, 0.15, Math.PI - 0.15); g.stroke(); }
      }
      if (kind === 'classroom') { g.fillStyle = '#2a2a2a'; g.strokeStyle = DIM; g.lineWidth = 1.5; g.fillRect(x - headR * 1.7, rowY + headR * 2.0, headR * 3.4, headR * 0.5); g.strokeRect(x - headR * 1.7, rowY + headR * 2.0, headR * 3.4, headR * 0.5); }
      if (isM) {
        const k2 = clamp01(age / 0.4), col = d.mark_color === 'white' ? WHITE : RED;
        g.strokeStyle = col; g.lineWidth = Math.max(2.5, H * 0.006); g.beginPath(); g.arc(x, rowY, headR * 2.6 * (1.6 - 0.6 * k2), 0, TAU * k2); g.stroke();
        if (d.label) { g.save(); const px = Math.round(H * 0.026); g.font = `800 ${px}px ${fam}`; const w = g.measureText(d.label).width + px; g.fillStyle = BLACK; g.fillRect(x - w / 2, rowY - headR * 3.9, w, px * 1.5); g.strokeStyle = col; g.strokeRect(x - w / 2, rowY - headR * 3.9, w, px * 1.5); g.fillStyle = col; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(d.label, x, rowY - headR * 3.9 + px * 0.75); g.restore(); }
        if (d.eyes_red && age > 0.5) { g.fillStyle = RED; g.beginPath(); g.arc(x - headR * 0.35, rowY - headR * 0.5, headR * 0.17, 0, TAU); g.arc(x + headR * 0.35, rowY - headR * 0.5, headR * 0.17, 0, TAU); g.fill(); }
      }
    }
  }
  if (kind === 'classroom' && d.board !== false) {                    // a board and a window at the top
    g.strokeStyle = WHITE; g.lineWidth = Math.max(2, H * 0.005); g.strokeRect(W * 0.35, H * 0.06, W * 0.3, H * 0.15);
    if (d.board_text) { g.fillStyle = WHITE; g.font = `700 ${Math.round(H * 0.03)}px ${fam}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(d.board_text, W / 2, H * 0.135); }
    g.strokeRect(W * 0.08, H * 0.06, W * 0.14, H * 0.16); g.strokeRect(W * 0.78, H * 0.06, W * 0.14, H * 0.16);
  }
}

// ---------------------------------------------------------------- bubble / banner
export function drawBubble(g, text, x, y, tx, ty, px, fam, age = 1) {
  g.save(); g.font = `700 ${Math.round(px)}px ${fam}`; const k = smooth(age / 0.15); g.globalAlpha *= k;
  const w = g.measureText(text).width + px * 1.1, h = px * 1.8;
  g.fillStyle = BLACK; g.strokeStyle = WHITE; g.lineWidth = Math.max(2, px * 0.09);
  g.beginPath(); g.roundRect(x - w / 2, y - h / 2, w, h, px * 0.5); g.fill(); g.stroke();
  g.beginPath(); g.moveTo(x - px * 0.4, y + h / 2 - 1); g.lineTo(tx, ty); g.lineTo(x + px * 0.4, y + h / 2 - 1); g.closePath(); g.fillStyle = BLACK; g.fill(); g.stroke();
  g.fillStyle = BLACK; g.fillRect(x - px * 0.38, y + h / 2 - 3, px * 0.76, 5);
  g.fillStyle = WHITE; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, x, y + px * 0.04); g.restore();
}
export function drawBanner(g, text, x, y, px, fam) {
  g.save(); g.font = `800 ${Math.round(px)}px ${fam}`; g.letterSpacing = `${(px * 0.1).toFixed(1)}px`; const w = g.measureText(text).width + px * 1.2, h = px * 1.7;
  g.fillStyle = RED; g.fillRect(x - w / 2, y - h / 2, w, h); g.fillStyle = WHITE; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, x, y + px * 0.04); g.restore();
}

// ---------------------------------------------------------------- the big rule card
/** "RULE" small, the number large, a red rule line, the typed sentence, and seven progress dashes (the first `number` filled). */
export function drawRuleCard(g, W, H, d, age, fam, total = 7, { dim = false } = {}) {
  g.fillStyle = dim ? 'rgba(4,6,12,0.8)' : BLACK; g.fillRect(0, 0, W, H);      // dim: the scene drawn before it stays faintly visible
  const px = H * 0.058, big = H * 0.2;
  g.textAlign = 'center'; g.textBaseline = 'middle';
  if (d.number != null) {
    g.fillStyle = DIM; g.font = `700 ${Math.round(H * 0.026)}px ${fam}`; g.letterSpacing = `${(H * 0.01).toFixed(1)}px`; g.fillText('RULE', W / 2, H * 0.17);
    g.letterSpacing = '0px'; g.fillStyle = WHITE; g.font = `900 ${Math.round(big)}px ${fam}`; g.fillText(String(d.number).padStart(2, '0'), W / 2, H * 0.31);
    g.fillStyle = RED; g.fillRect(W / 2 - W * 0.11, H * 0.44, W * 0.22, Math.max(3, H * 0.005));
  }
  g.font = `700 ${Math.round(px)}px ${fam}`;
  const lines = wrapText(g, String(d.text), W * 0.66), tot = lines.join('').length, n = Math.min(tot, typedCount(age, 30, 0.35));
  g.textAlign = 'left'; g.fillStyle = WHITE;
  let left = n, y = H * 0.58 + (d.number != null ? 0 : -H * 0.05), lastX = W / 2, lastY = y;
  for (const ln of lines) {
    const w = g.measureText(ln).width, x = (W - w) / 2, part = ln.slice(0, Math.max(0, Math.min(ln.length, left)));
    g.fillText(part, x, y); lastX = x + g.measureText(part).width; lastY = y; left -= ln.length; y += px * 1.35; if (left <= 0) break;
  }
  if (n >= tot || Math.floor(age * 2.4) % 2 === 0) g.fillRect(lastX + px * 0.1, lastY - px * 0.42, px * 0.45, px * 0.84);
  if (d.number != null) {
    const dw = W * 0.045, gap = W * 0.012, x0 = W / 2 - (total * dw + (total - 1) * gap) / 2;
    for (let i = 0; i < total; i++) { g.fillStyle = i < d.number ? RED : 'rgba(242,242,242,0.3)'; g.fillRect(x0 + i * (dw + gap), H * 0.88, dw, Math.max(3, H * 0.006)); }
  }
}

/** The colour look's rule card (like the shop video): a yellow panel with a hazard-striped frame, a red header "RULE n" with progress diamonds, the rule typed in black. */
export function drawHazardCard(g, W, H, d, age, fam, total = 7) {
  g.fillStyle = '#0d0f14'; g.fillRect(0, 0, W, H);
  const k = smooth(age / 0.25), cx = W / 2, cy = H / 2, w = W * 0.72 * (0.92 + 0.08 * k), h = H * 0.5 * (0.92 + 0.08 * k), x = cx - w / 2, y = cy - h / 2, bd = H * 0.035;
  g.save(); g.globalAlpha *= k; g.fillStyle = '#F2C318'; g.fillRect(x, y, w, h);
  g.save(); g.beginPath(); g.rect(x, y, w, h); g.rect(x + bd, y + bd, w - 2 * bd, h - 2 * bd); g.clip('evenodd'); g.fillStyle = '#16181d'; g.fillRect(x, y, w, h);
  g.fillStyle = '#F2C318'; for (let i = -h; i < w + h; i += bd * 1.8) { g.beginPath(); g.moveTo(x + i, y); g.lineTo(x + i + bd * 0.9, y); g.lineTo(x + i + bd * 0.9 - h, y + h); g.lineTo(x + i - h, y + h); g.closePath(); g.fill(); } g.restore();
  const hh = h * 0.2; g.fillStyle = RED; g.fillRect(x + bd, y + bd, w - 2 * bd, hh);
  g.fillStyle = WHITE; g.font = `900 ${Math.round(hh * 0.62)}px ${fam}`; g.textAlign = 'left'; g.textBaseline = 'middle';
  g.fillText(`\u26A0 RULE${d.number != null ? ' ' + d.number : ''}`, x + bd * 1.8, y + bd + hh * 0.52);
  if (d.number != null) for (let i = 0; i < total; i++) { const dx = x + w - bd * 1.6 - (total - i) * hh * 0.34, dy = y + bd + hh * 0.52; g.fillStyle = i < d.number ? WHITE : 'rgba(255,255,255,0.4)'; g.beginPath(); g.moveTo(dx, dy - hh * 0.14); g.lineTo(dx + hh * 0.12, dy); g.lineTo(dx, dy + hh * 0.14); g.lineTo(dx - hh * 0.12, dy); g.closePath(); g.fill(); }
  const px = hh * 0.62; g.font = `800 ${Math.round(px)}px ${fam}`; g.fillStyle = '#15171c';
  const lines = wrapText(g, String(d.text), w - 2 * bd * 2.2), tot = lines.join('').length, n = Math.min(tot, typedCount(age, 30, 0.35));
  let left = n, ty = y + bd + hh + (h - 2 * bd - hh) / 2 - (lines.length - 1) * px * 0.6, lastX = x + bd * 2.2, lastY = ty;
  for (const ln of lines) { const part = ln.slice(0, Math.max(0, Math.min(ln.length, left))); g.fillText(part, x + bd * 2.2, ty); lastX = x + bd * 2.2 + g.measureText(part).width; lastY = ty; left -= ln.length; ty += px * 1.25; if (left <= 0) break; }
  if (n >= tot || Math.floor(age * 2.4) % 2 === 0) g.fillRect(lastX + px * 0.1, lastY - px * 0.4, px * 0.4, px * 0.8);
  g.restore();
}

// ---------------------------------------------------------------- per-reference rule cards (tag, paper, sign)
/** Types `text` into a column; returns where the cursor ends. align 'center' centres each line on cx, 'left' starts at cx. */
function typeBlock(g, text, cx, y, maxW, px, age, align = 'center') {
  const lines = wrapText(g, String(text), maxW), tot = lines.join('').length, n = Math.min(tot, typedCount(age, 30, 0.35));
  let left = n, lastX = cx, lastY = y; g.textAlign = 'left';
  for (const ln of lines) { const part = ln.slice(0, Math.max(0, Math.min(ln.length, left))), w = g.measureText(ln).width, x = align === 'center' ? cx - w / 2 : cx;
    g.fillText(part, x, y); lastX = x + g.measureText(part).width; lastY = y; left -= ln.length; y += px * 1.3; if (left <= 0) break; }
  if (n >= tot || Math.floor(age * 2.4) % 2 === 0) g.fillRect(lastX + px * 0.08, lastY - px * 0.42, px * 0.4, px * 0.84);
}
const vignette = (g, W, H, a = 0.6) => { const v = g.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, H * 0.95); v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, `rgba(0,0,0,${a})`); g.fillStyle = v; g.fillRect(0, 0, W, H); };
const dots = (g, x, y, r, total, n, on, off) => { for (let i = 0; i < total; i++) { g.fillStyle = i < n ? on : off; g.fillRect(x + i * r * 3, y - r, r * 2, r * 2); } };

/** The mall reference: a white shop tag on a string drops in and swings; a hand pinches the top; "RULE n" (n red), the rule typed, a barcode. */
export function drawTagCard(g, W, H, d, age, fam, total = 7) {
  const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#3a302a'); bg.addColorStop(1, '#1c1714'); g.fillStyle = bg; g.fillRect(0, 0, W, H);
  g.fillStyle = 'rgba(255,240,220,0.06)'; for (let i = 0; i < 5; i++) g.fillRect(W * (0.1 + i * 0.2), 0, W * 0.012, H);
  const drop = smooth(age / 0.45), sw = Math.sin(age * 3.2) * Math.exp(-age * 1.4) * 0.05, w = W * 0.46, h = H * 0.5, cx = W / 2, top = H * 0.2 - (1 - drop) * H * 0.7;
  g.save(); g.translate(cx, top - H * 0.05); g.rotate(sw);
  g.strokeStyle = '#d8d0c4'; g.lineWidth = Math.max(1.5, H * 0.003); g.beginPath(); g.moveTo(0, -H * 0.3); g.lineTo(0, H * 0.05); g.stroke();
  g.fillStyle = '#e8c5a8'; g.beginPath(); g.ellipse(0, -H * 0.02, H * 0.035, H * 0.05, 0.3, 0, TAU); g.fill();            // the pinching fingers
  g.fillStyle = '#f4f2ee'; const x = -w / 2, y = H * 0.05, r = H * 0.03, nt = H * 0.05;
  g.beginPath(); g.moveTo(x + nt, y); g.lineTo(x + w - nt, y); g.lineTo(x + w, y + nt); g.lineTo(x + w, y + h - r); g.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  g.lineTo(x + r, y + h); g.quadraticCurveTo(x, y + h, x, y + h - r); g.lineTo(x, y + nt); g.closePath(); g.shadowColor = 'rgba(0,0,0,0.45)'; g.shadowBlur = H * 0.04; g.fill(); g.shadowBlur = 0;
  g.fillStyle = '#c8c2b8'; g.beginPath(); g.arc(0, y + H * 0.035, H * 0.01, 0, TAU); g.fill();
  g.textBaseline = 'middle'; g.textAlign = 'center'; const big = H * 0.075; g.font = `900 ${Math.round(big)}px ${fam}`;
  const head = 'RULE' + (d.number != null ? ' ' : ''), hw = g.measureText(head).width, nw = d.number != null ? g.measureText(String(d.number)).width : 0;
  g.textAlign = 'left'; g.fillStyle = '#1b1b1f'; g.fillText(head, -(hw + nw) / 2, y + h * 0.27); if (d.number != null) { g.fillStyle = RED; g.fillText(String(d.number), -(hw + nw) / 2 + hw, y + h * 0.27); }
  const px = H * 0.042; g.font = `800 ${Math.round(px)}px ${fam}`; g.fillStyle = '#1b1b1f'; typeBlock(g, String(d.text).toUpperCase(), 0, y + h * 0.5, w * 0.84, px, age - 0.3);
  g.fillStyle = '#2a2a2a'; for (let i = 0; i < 22; i++) g.fillRect(x + w * 0.07 + i * w * 0.009, y + h * 0.84, (i % 3 ? 1 : 2) * Math.max(1, H * 0.0018), h * 0.08);
  if (d.number != null) dots(g, x + w * 0.62, y + h * 0.88, H * 0.007, total, d.number, RED, '#c9c4bc');
  g.restore(); vignette(g, W, H, 0.55);
}

/** The school reference: a printed sheet on a wooden desk, "RULE NO." with a big red number, the rule typed in black, a pencil beside it. */
export function drawPaperCard(g, W, H, d, age, fam, total = 7) {
  g.fillStyle = '#8a643f'; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 26; i++) { g.strokeStyle = `rgba(60,36,18,${0.15 + 0.15 * hash(i)})`; g.lineWidth = H * 0.002; g.beginPath(); const yy = H * (i / 26) + hash(i + 3) * 8;
    g.moveTo(0, yy); g.bezierCurveTo(W * 0.3, yy + 6 * hash(i + 1), W * 0.7, yy - 6 * hash(i + 2), W, yy + 3); g.stroke(); }
  const k = smooth(age / 0.35), w = W * 0.5, h = H * 0.78, cx = W / 2 + (1 - k) * W * 0.3, cy = H * 0.52;
  g.save(); g.translate(cx, cy); g.rotate(-0.03 + (1 - k) * 0.1); g.shadowColor = 'rgba(0,0,0,0.4)'; g.shadowBlur = H * 0.03; g.fillStyle = '#f7f4ec'; g.fillRect(-w / 2, -h / 2, w, h); g.shadowBlur = 0;
  g.fillStyle = '#9a968c'; g.font = `700 ${Math.round(H * 0.018)}px ${fam}`; g.textAlign = 'left'; g.textBaseline = 'middle'; g.fillText('POSTED NOTICE', -w * 0.44, -h * 0.42);
  g.textAlign = 'right'; g.fillText('PAGE 1 OF 1', w * 0.44, -h * 0.42); g.fillRect(-w * 0.44, -h * 0.37, w * 0.88, Math.max(1, H * 0.002));
  const big = H * 0.085; g.font = `900 ${Math.round(big)}px ${fam}`; g.textAlign = 'left'; g.fillStyle = '#18181c'; g.fillText('RULE NO.', -w * 0.44, -h * 0.24);
  if (d.number != null) { g.fillStyle = RED; g.font = `900 ${Math.round(big * 1.4)}px ${fam}`; g.fillText(String(d.number), -w * 0.44 + g.measureText('RULE NO. ').width * 0.75 + big * 2.6, -h * 0.25); }
  const px = H * 0.046; g.font = `900 ${Math.round(px)}px ${fam}`; g.fillStyle = '#18181c'; typeBlock(g, String(d.text).toUpperCase(), -w * 0.44, -h * 0.04, w * 0.86, px, age - 0.25, 'left');
  if (d.number != null) dots(g, -w * 0.12, h * 0.42, H * 0.006, total, d.number, RED, '#cfcabe');
  g.restore();
  g.save(); g.translate(W * 0.84, H * 0.7); g.rotate(-0.5); g.fillStyle = '#e8b730'; g.fillRect(-H * 0.2, -H * 0.012, H * 0.36, H * 0.024); g.fillStyle = '#e9c9a0';
  g.beginPath(); g.moveTo(H * 0.16, -H * 0.012); g.lineTo(H * 0.21, 0); g.lineTo(H * 0.16, H * 0.012); g.fill(); g.fillStyle = '#d98a8a'; g.fillRect(-H * 0.23, -H * 0.012, H * 0.03, H * 0.024); g.restore();
  vignette(g, W, H, 0.5);
}

/** The aquarium reference: deep teal water, rising bubbles, a pale board held up by two hands and bobbing, the rule in marker. */
export function drawSignCard(g, W, H, d, age, fam, total = 7) {
  const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#0f4456'); bg.addColorStop(1, '#041820'); g.fillStyle = bg; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 26; i++) { const bx = W * hash(i), by = H - ((age * (40 + 60 * hash(i + 9)) + hash(i + 4) * H * 1.2) % (H * 1.2)), r = H * (0.004 + 0.01 * hash(i + 2));
    g.strokeStyle = 'rgba(190,235,255,0.5)'; g.lineWidth = Math.max(1, H * 0.0018); g.beginPath(); g.arc(bx + Math.sin(age * 2 + i) * 6, by, r, 0, TAU); g.stroke(); }
  const k = smooth(age / 0.4), bob = Math.sin(age * 1.6) * H * 0.01, w = W * 0.5, h = H * 0.44, x = W / 2 - w / 2, y = H * 0.24 + (1 - k) * H * 0.6 + bob;
  g.save(); g.translate(W / 2, y + h / 2); g.rotate(Math.sin(age * 1.1) * 0.02); g.translate(-W / 2, -(y + h / 2));
  g.fillStyle = '#e8cfc6'; g.shadowColor = 'rgba(0,0,0,0.5)'; g.shadowBlur = H * 0.03; g.fillRect(x, y, w, h); g.shadowBlur = 0;
  g.strokeStyle = '#b89d94'; g.lineWidth = H * 0.006; g.strokeRect(x + H * 0.012, y + H * 0.012, w - H * 0.024, h - H * 0.024);
  g.fillStyle = '#3a2a2e'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = `800 ${Math.round(H * 0.03)}px ${fam}`;
  if (d.number != null) g.fillText(`RULE ${d.number}`, W / 2, y + h * 0.17);
  const px = H * 0.06; g.font = `italic 900 ${Math.round(px)}px ${fam}`; typeBlock(g, String(d.text).toUpperCase(), W / 2, y + h * 0.42, w * 0.86, px, age - 0.3);
  g.fillStyle = '#c99a7c'; for (const hx of [x + w * 0.08, x + w * 0.92]) { g.beginPath(); g.ellipse(hx, y + h * 0.98, H * 0.04, H * 0.055, 0, 0, TAU); g.fill(); }
  g.restore();
  if (d.number != null) dots(g, W / 2 - total * H * 0.0105, H * 0.92, H * 0.007, total, d.number, RED, 'rgba(190,235,255,0.35)');
  vignette(g, W, H, 0.6);
}

// ---------------------------------------------------------------- the mirror: a framed glass with a warm, slightly wrong room and a reflection that moves first
export const MIRRORS = { bathroom: [0.59, 0.13, 0.28, 0.42], hall_mirror: [0.43, 0.34, 0.14, 0.28] };
/** The reflection copies the person's pose `lead` seconds EARLY (it moves first), smiles from smile_at, presses its face to the glass at press_at; a tap runs on the real side only. */
export function drawMirror(g, W, H, t, d, pal) {
  const r = d.rect || MIRRORS[d.set] || MIRRORS.bathroom, mx = r[0] * W, my = r[1] * H, mw = r[2] * W, mh = r[3] * H, lw = lineWidth(H);
  g.save(); g.beginPath(); g.rect(mx, my, mw, mh); g.clip();
  const gr = g.createLinearGradient(0, my, 0, my + mh); gr.addColorStop(0, pal ? '#e2c27a' : '#1d1a0d'); gr.addColorStop(1, pal ? '#b58f45' : '#0d0b05');
  g.fillStyle = gr; g.fillRect(mx, my, mw, mh);
  g.strokeStyle = pal ? '#6e5420' : '#7a7355'; g.lineWidth = lw; g.strokeRect(mx + mw * 0.7, my + mh * 0.22, mw * 0.2, mh * 0.78);          // the door sits a little farther from the wall here
  g.beginPath(); g.moveTo(mx + mw * 0.2, my + mh * 0.2); g.lineTo(mx + mw * 0.2, my + mh * 0.3); g.stroke(); g.strokeRect(mx + mw * 0.15, my + mh * 0.3, mw * 0.1, mh * 0.28);   // the towel hangs on the OTHER hook
  const pressed = d.press_at != null && t >= d.press_at;
  const pose = poseAt({ pose: d.pose || 'stand', moves: d.moves || [] }, t + (d.lead ?? 0.5)), smile = d.smile_at != null && t >= d.smile_at;
  const size = mh * (pressed ? 4.2 : 1.4) * (d.scale ?? 1), sx = mx + mw * 0.5, gy0 = my + mh * 0.12 + size;   // the head sits near the top of the glass
  let J = skeleton(pose, sx, gy0, size, -1);
  if (pressed) { const dy = my + mh * 0.5 - J.head[1], dx = sx - J.head[0]; J = skeleton(pose, sx + dx + Math.sin(t * 30) * 1.5, gy0 + dy, size, -1); }
  drawFigure(g, J, lw, { pal, look: (smile || pressed) ? 'grin' : null, seed: d.seed ?? 3, color: WHITE, stare: pressed });
  g.fillStyle = 'rgba(255,255,255,0.07)'; g.beginPath(); g.moveTo(mx, my + mh * 0.5); g.lineTo(mx + mw * 0.4, my); g.lineTo(mx + mw * 0.55, my); g.lineTo(mx, my + mh * 0.85); g.closePath(); g.fill();   // a glint
  g.restore();
  g.strokeStyle = pal ? pal.line : WHITE; g.lineWidth = lw * 1.6; g.strokeRect(mx, my, mw, mh);
  if (d.water) {                                                                                                  // a running tap: only on this side of the glass
    const fx = (d.faucet?.[0] ?? 0.70) * W, fy = (d.faucet?.[1] ?? 0.545) * H, by = (d.basin ?? 0.60) * H;
    g.save(); g.strokeStyle = 'rgba(205,228,255,0.85)'; g.lineWidth = lw * 1.2; g.setLineDash([lw * 3, lw * 2.4]); g.lineDashOffset = -t * lw * 14;
    g.beginPath(); g.moveTo(fx, fy); g.lineTo(fx, by); g.stroke(); g.restore();
  }
}
