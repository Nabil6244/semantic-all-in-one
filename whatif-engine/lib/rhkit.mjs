// Rules Horror drawing kit: white lines on black, one red accent. Pure functions of (g, t, W, H) -- the same time always draws the same frame.
// Stick figure (FK skeleton + poses + cycles), line-drawn sets, tags, sight lines, countdown ring, typed card text, glitch.
export const WHITE = '#F2F2F2', RED = '#E0201C', DIM = '#8C8C8C', BLACK = '#000000';
export const clamp01 = (x) => Math.min(1, Math.max(0, x));
export const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const D2R = Math.PI / 180;
const lerp = (a, b, k) => a + (b - a) * k;

// ---------------------------------------------------------------- stick figure
// A pose: lean/neck (deg, + = forward), arms aL/aR = [upper, fore] and legs lL/lR = [thigh, shin] as ABSOLUTE angles from straight down
// (+ = forward), rot = whole-body rotation (deg), chair = draw a seat under the hip. Cycles (walk, run) are functions of time.
const P = (o) => ({ lean: 0, neck: 0, aL: [6, 4], aR: [-6, -4], lL: [2, 0], lR: [-2, 0], rot: 0, chair: false, ...o });
const swing = (t, freq, amp, lean, bend, armBend) => {
  const p = t * freq * 2 * Math.PI, hl = amp * Math.sin(p), hr = -hl;
  const b = (ph) => bend * Math.max(0, Math.cos(p + ph));
  return P({ lean, aL: [-hl * 0.7, -hl * 0.7 + armBend], aR: [-hr * 0.7, -hr * 0.7 + armBend],
    lL: [hl, hl - b(0.6)], lR: [hr, hr - b(0.6 + Math.PI)] });
};
export const POSES = {
  stand: () => P({}),
  look: () => P({ neck: 12, aR: [118, 165], aL: [6, 4] }),
  flinch: () => P({ lean: -14, neck: -8, aL: [140, 172], aR: [128, 166], lL: [-10, -12], lR: [12, 4] }),
  sit: () => P({ lean: 4, aL: [22, 78], aR: [18, 74], lL: [88, 4], lR: [84, 0], chair: true }),
  sleep: () => P({ rot: 90, aL: [8, 6], aR: [-8, -6] }),
  walk: (t) => swing(t, 1.1, 26, 3, 34, 14),
  run: (t) => swing(t, 2.1, 48, 16, 58, 72),
};
export const POSE_NAMES = Object.keys(POSES);
const LEN = { torso: 0.30, neck: 0.035, head: 0.09, ua: 0.13, fa: 0.13, th: 0.22, sh: 0.22 };
const TOTAL = LEN.torso + LEN.neck + LEN.head * 2 + LEN.th + LEN.sh;   // standing height in figure units

export function poseAt(def, t) {
  const get = (n) => (POSES[n] || POSES.stand)(t);
  let cur = get(def.pose || 'stand');
  for (const m of def.moves || []) {
    if (t >= m.at) { cur = get(m.pose); const k = smooth((t - m.at) / 0.3); if (k < 1) cur = mixPose(get(m.from || def.pose || 'stand'), cur, k); }
  }
  // idle: a slow breath and a small head drift, so a held pose is never frozen
  const idle = Math.sin(t * 1.3);
  return { ...cur, neck: cur.neck + 1.4 * Math.sin(t * 0.9), breath: 0.004 * idle };
}
function mixPose(a, b, k) {
  const m = (x, y) => (Array.isArray(x) ? x.map((v, i) => lerp(v, y[i], k)) : lerp(x, y, k));
  return { lean: m(a.lean, b.lean), neck: m(a.neck, b.neck), aL: m(a.aL, b.aL), aR: m(a.aR, b.aR), lL: m(a.lL, b.lL), lR: m(a.lR, b.lR),
    rot: m(a.rot, b.rot), chair: k > 0.5 ? b.chair : a.chair };
}

/** Joint positions in pixels. x/ground = where the lowest point rests; size = standing height in pixels; facing 1 right, -1 left. */
export function skeleton(pose, x, ground, size, facing = 1) {
  const u = size / TOTAL, hip = [0, 0];
  const dir = (a) => [Math.sin(a * D2R), Math.cos(a * D2R)];               // from straight down
  const add = (p, a, l) => { const d = dir(a); return [p[0] + d[0] * l * u, p[1] + d[1] * l * u]; };
  const up = (p, a, l) => { const d = dir(a); return [p[0] + d[0] * l * u, p[1] - d[1] * l * u]; };   // from straight up
  const sh = up(hip, pose.lean, LEN.torso); sh[1] -= (pose.breath || 0) * size;
  const headC = up(sh, pose.lean + pose.neck, LEN.neck + LEN.head);
  const arm = (a) => { const e = add(sh, a[0], LEN.ua), w = add(e, a[1], LEN.fa); return [sh, e, w]; };
  const leg = (a) => { const k = add(hip, a[0], LEN.th), f = add(k, a[1], LEN.sh); return [hip, k, f]; };
  const J = { hip, sh, head: headC, r: LEN.head * u, aL: arm(pose.aL), aR: arm(pose.aR), lL: leg(pose.lL), lR: leg(pose.lR) };
  const rot = pose.rot * D2R, c = Math.cos(rot), s = Math.sin(rot);
  const fix = (p) => { const rx = p[0] * c - p[1] * s, ry = p[0] * s + p[1] * c; return [rx * facing, ry]; };
  for (const k of ['hip', 'sh', 'head']) J[k] = fix(J[k]);
  for (const k of ['aL', 'aR', 'lL', 'lR']) J[k] = J[k].map(fix);
  let low = -1e9;
  for (const k of ['aL', 'aR', 'lL', 'lR']) for (const p of J[k]) low = Math.max(low, p[1]);
  low = Math.max(low, J.head[1] + J.r, J.hip[1]);
  const dx = x, dy = ground - low;
  const mv = (p) => [p[0] + dx, p[1] + dy];
  for (const k of ['hip', 'sh', 'head']) J[k] = mv(J[k]);
  for (const k of ['aL', 'aR', 'lL', 'lR']) J[k] = J[k].map(mv);
  J.facing = facing; J.low = ground;
  return J;
}

export function drawFigure(g, J, lw, { color = WHITE, eye = null, stare = false, hollow = false, look = null, pal = null, seed = 3, outfit = null, face = 'neutral' } = {}) {
  if (pal && !hollow && look !== 'mannequin') return drawFigureColour(g, J, lw, pal, { seed, outfit, face: look === 'grin' ? 'grin' : face, stare, look });
  if (look === 'mannequin') color = '#C9C9C9';
  if (look === 'hazmat' && !eye) eye = RED;
  g.save(); g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = color; g.fillStyle = color;
  const body = hollow ? lw : Math.max(lw * 4.5, J.r * 1.3), limb = hollow ? lw : Math.max(lw * 3.4, J.r * 0.8);
  const line = (pts, w) => { g.lineWidth = w; g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (const p of pts.slice(1)) g.lineTo(p[0], p[1]); g.stroke(); };
  line([J.hip, J.sh], body);
  for (const k of ['aL', 'aR', 'lL', 'lR']) line(J[k], limb);
  const nx = J.sh, hd = J.head, dd = Math.hypot(hd[0] - nx[0], hd[1] - nx[1]) || 1, ux = (hd[0] - nx[0]) / dd, uy = (hd[1] - nx[1]) / dd;
  line([nx, [hd[0] - ux * J.r, hd[1] - uy * J.r]], limb);
  g.lineWidth = lw; g.fillStyle = hollow ? BLACK : color; g.beginPath(); g.arc(hd[0], hd[1], J.r, 0, Math.PI * 2); g.fill(); if (hollow) g.stroke();
  if (look === 'grin') {                         // a face with eyes and a huge smile full of teeth
    const hd2 = J.head, r = J.r; g.fillStyle = BLACK; for (const ex of [-0.36, 0.36]) { g.beginPath(); g.arc(hd2[0] + ex * r, hd2[1] - r * 0.25, r * 0.17, 0, Math.PI * 2); g.fill(); }
    g.strokeStyle = BLACK; g.lineWidth = Math.max(lw * 0.8, r * 0.1); g.beginPath(); g.arc(hd2[0], hd2[1] - r * 0.05, r * 0.68, 0.12, Math.PI - 0.12); g.stroke();
    g.fillStyle = BLACK; g.beginPath(); g.arc(hd2[0], hd2[1] - r * 0.05, r * 0.68, 0.12, Math.PI - 0.12); g.closePath(); g.fill();
    g.strokeStyle = WHITE; g.lineWidth = Math.max(1, r * 0.04); for (let k = -3; k <= 3; k++) { const x = hd2[0] + k * r * 0.17; g.beginPath(); g.moveTo(x, hd2[1] + r * 0.1); g.lineTo(x, hd2[1] + r * 0.5); g.stroke(); }
  } else if (look === 'mannequin') { /* a smooth blank head */ } else if (eye || !hollow) {                          // a solid head still has a small dark eye (red when the figure is "wrong")
    g.fillStyle = eye || BLACK; const er = Math.max(1.5, lw * 0.55, J.r * 0.14), ey = hd[1] - J.r * 0.1;
    for (const ex of stare ? [-J.r * 0.36, J.r * 0.36] : [J.facing * J.r * 0.38]) { g.beginPath(); g.arc(hd[0] + ex, ey, er, 0, Math.PI * 2); g.fill(); }
  }
  g.restore();
}

// ---------------------------------------------------------------- schemes: mono (white on black), dark (night colour), colour (lit interiors)
export const PALETTES = {
  mono: null,
  dark: { bg0: '#0a0f1f', bg1: '#1a2440', line: '#9db0d6', wall: '#1a2442', floor: '#0e1428', glow: '#E8C21A', accent: RED,
    skin: ['#d9b69b', '#c68e6c', '#8e5c3d', '#f0d2ba'], hair: ['#1a1410', '#4b3322', '#9a7b4f', '#cfcfcf'], shirt: ['#3d62ad', '#a83d3d', '#3f8a6b', '#c9a13a', '#6b4aa0', '#8a93a0'], pants: ['#232b40', '#303b54', '#3a3a3a'] },
  colour: { bg0: '#d9d5cb', bg1: '#bfc6d2', line: '#4b5160', wall: '#e6e2d8', floor: '#b4b0a4', glow: '#F2C318', accent: RED,
    skin: ['#e0bba0', '#c98f6a', '#8e5c3d', '#f1d3bb'], hair: ['#1f1a16', '#5a3d27', '#a78555', '#d6d6d6'], shirt: ['#2f6fbf', '#c0392b', '#2e8b57', '#d9a520', '#7a4fb3', '#6c7480'], pants: ['#2a3550', '#3b4660', '#4a4a4a'] },
};
const PEOPLE = { skin: ['#d9b69b', '#c68e6c', '#8e5c3d', '#f0d2ba'], hair: ['#1a1410', '#4b3322', '#9a7b4f', '#cfcfcf'], shirt: ['#3d62ad', '#a83d3d', '#3f8a6b', '#c9a13a', '#6b4aa0', '#8a93a0'], pants: ['#232b40', '#303b54', '#3a3a3a'] };
PALETTES.night = PALETTES.dark; PALETTES.day = PALETTES.colour;
PALETTES.warm = { bg0: '#2b1a0c', bg1: '#5a3a1a', line: '#e8c88a', wall: '#6a4726', floor: '#3a2412', glow: '#ffd27a', accent: RED, ...PEOPLE };
PALETTES.cold = { bg0: '#08141b', bg1: '#1d3a47', line: '#a9d0dc', wall: '#17303b', floor: '#0c1a22', glow: '#bfe6f2', accent: RED, ...PEOPLE };
PALETTES.red = { bg0: '#14040a', bg1: '#3d0b14', line: '#e8a3a8', wall: '#2c0a12', floor: '#16050a', glow: '#ff5a4a', accent: '#ff3b30', ...PEOPLE };
PALETTES.deep = { bg0: '#06222e', bg1: '#0d3b4c', line: '#8fc4d2', wall: '#0f3442', floor: '#082430', glow: '#9fe3ff', accent: RED, ...PEOPLE };
PALETTES.dawn = { bg0: '#2b2a4d', bg1: '#d9a07a', line: '#4d4458', wall: '#c9b3b8', floor: '#8c7b85', glow: '#ffd9a0', accent: RED, ...PEOPLE };
export const schemeOf = (f) => (f && f.spec && f.spec.rh && f.spec.rh.scheme) || 'mono';
/** The palette for a layer: none in the mono scheme; in the "story" scheme the layer's own mood (the colour follows the narration), otherwise the fixed scheme. */
export const palOf = (f, d) => { const sc = schemeOf(f); if (sc === 'mono') return null; return PALETTES[(sc === 'story' && d && d.mood) || (sc === 'story' ? 'night' : sc)] || null; };
export const moodOf = (f, d) => (schemeOf(f) === 'story' ? (d && d.mood) || 'night' : schemeOf(f));
const pickOf = (arr, k) => arr[Math.abs(Math.floor(k)) % arr.length];
const TAU2 = Math.PI * 2;
/** A flat-shaded person: skin, hair, shirt, trousers, shoes, a face; outfits: attendant, usher, hazmat (yellow suit, gas mask, red lenses). face: neutral | scared | grin. */
export function drawFigureColour(g, J, lw, pal, { seed = 3, outfit = null, face = 'neutral', stare = false, look = null } = {}) {
  // Cartoon people like the colour references: front-facing, outlined flat shapes, shoulders and hips with width, sleeves, small hands,
  // a big head with ears, one of five hair styles, white eyes with pupils. The skeleton gives the pose; limbs are pushed out to the shoulder/hip edges.
  const hz = look === 'hazmat' || outfit === 'hazmat';
  const skin = pickOf(pal.skin, seed), hair = pickOf(pal.hair, seed * 3 + 1), style = Math.abs(seed * 7 + 3) % 5;
  let top = pickOf(pal.shirt, seed * 5 + 2), bottom = pickOf(pal.pants, seed * 7 + 3);
  if (outfit === 'attendant') { top = bottom = '#1f2f5c'; } else if (outfit === 'usher') { top = '#5a1218'; bottom = '#1b1b1b'; } else if (hz) { top = bottom = '#F2C318'; }
  const r = J.r * 1.18, ol = '#1c1e25', ow = Math.max(1.2, J.r * 0.13);
  const sx = J.sh[0] - J.hip[0], sy = J.sh[1] - J.hip[1], sl = Math.hypot(sx, sy) || 1, px = -sy / sl, py = sx / sl;     // across the body
  const shw = J.r * (hz ? 1.35 : 1.1), hpw = J.r * (hz ? 1.15 : 0.85), limb = Math.max(lw * 2.6, J.r * (hz ? 0.95 : 0.72));
  const off = (pts, k) => pts.map((q, i) => (i === 0 ? [q[0] + px * k, q[1] + py * k] : [q[0] + px * k, q[1] + py * k]));
  const darker = (c, k = 0.22) => { const v = parseInt(c.slice(1), 16), f = (x) => Math.round(x * (1 - k)); return `rgb(${f((v >> 16) & 255)},${f((v >> 8) & 255)},${f(v & 255)})`; };
  g.save(); g.lineCap = 'round'; g.lineJoin = 'round';
  const limbLine = (pts, w, c) => { for (const [ww, cc] of [[w + ow * 2, ol], [w, c]]) { g.strokeStyle = cc; g.lineWidth = ww; g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (const q of pts.slice(1)) g.lineTo(q[0], q[1]); g.stroke(); } };
  const blob = (fn, fill) => { g.beginPath(); fn(); g.fillStyle = fill; g.fill(); g.strokeStyle = ol; g.lineWidth = ow; g.stroke(); };
  const lL = off(J.lL, -hpw * 0.5), lR = off(J.lR, hpw * 0.5), aL = off(J.aL, -shw * 0.92), aR = off(J.aR, shw * 0.92);
  // legs and shoes
  limbLine(lL, limb * 1.15, bottom); limbLine(lR, limb * 1.15, bottom);
  for (const L of [lL, lR]) { const f = L[2]; blob(() => g.ellipse(f[0] + J.facing * limb * 0.25, f[1] - limb * 0.15, limb * 0.85, limb * 0.42, 0, 0, TAU2), hz ? '#8a6a00' : '#22252d'); }
  // torso: a rounded trapezoid from the shoulders to the hips, shaded on one side
  const S0 = [J.sh[0] - px * shw, J.sh[1] - py * shw], S1 = [J.sh[0] + px * shw, J.sh[1] + py * shw], H1 = [J.hip[0] + px * hpw, J.hip[1] + py * hpw], H0 = [J.hip[0] - px * hpw, J.hip[1] - py * hpw];
  blob(() => { g.moveTo(S0[0], S0[1]); g.quadraticCurveTo(J.sh[0] - (sx / sl) * r * 0.25, J.sh[1] - (sy / sl) * r * 0.25, S1[0], S1[1]); g.lineTo(H1[0], H1[1]); g.lineTo(H0[0], H0[1]); g.closePath(); }, top);
  g.save(); g.beginPath(); g.moveTo(S1[0], S1[1]); g.lineTo(H1[0], H1[1]); g.lineTo((H1[0] + J.hip[0]) / 2, (H1[1] + J.hip[1]) / 2); g.lineTo((S1[0] + J.sh[0]) / 2 + px * shw * 0.3, (S1[1] + J.sh[1]) / 2 + py * shw * 0.3); g.closePath(); g.fillStyle = 'rgba(0,0,0,0.14)'; g.fill(); g.restore();
  if (outfit === 'attendant') { g.fillStyle = RED; g.beginPath(); g.moveTo(J.sh[0], J.sh[1]); g.lineTo(J.sh[0] - px * shw * 0.5 + (J.hip[0] - J.sh[0]) * 0.3, J.sh[1] - py * shw * 0.5 + (J.hip[1] - J.sh[1]) * 0.3); g.lineTo(J.sh[0] + px * shw * 0.2 + (J.hip[0] - J.sh[0]) * 0.25, J.sh[1] + py * shw * 0.2 + (J.hip[1] - J.sh[1]) * 0.25); g.closePath(); g.fill(); }
  if (outfit === 'usher') { g.fillStyle = RED; g.fillRect(J.sh[0] - r * 0.25, J.sh[1] + r * 0.05, r * 0.5, r * 0.22); g.fillStyle = '#c9a13a'; for (let k = 1; k < 4; k++) { g.beginPath(); g.arc(J.sh[0] + (J.hip[0] - J.sh[0]) * k * 0.25, J.sh[1] + (J.hip[1] - J.sh[1]) * k * 0.25, r * 0.06, 0, TAU2); g.fill(); } }
  // arms (sleeves) and hands
  limbLine(aL, limb, top); limbLine(aR, limb, top);
  for (const A of [aL, aR]) { const w = A[2]; blob(() => g.arc(w[0], w[1], limb * 0.55, 0, TAU2), hz ? '#E0AE12' : skin); }
  // head
  const hd = [J.head[0], J.head[1] - (r - J.r) * 0.6];
  if (hz) {                                                                                  // hood, gas mask, two red lenses, a round filter
    blob(() => g.arc(hd[0], hd[1], r * 1.15, 0, TAU2), '#F2C318');
    g.fillStyle = '#1b1e24'; g.beginPath(); g.ellipse(hd[0] + J.facing * r * 0.05, hd[1] + r * 0.1, r * 0.8, r * 0.7, 0, 0, TAU2); g.fill();
    for (const ex of [-0.36, 0.36]) { const x = hd[0] + J.facing * r * 0.05 + ex * r, y = hd[1] - r * 0.02; g.fillStyle = RED; g.beginPath(); g.arc(x, y, r * 0.26, 0, TAU2); g.fill(); g.fillStyle = 'rgba(255,255,255,0.7)'; g.beginPath(); g.arc(x - r * 0.08, y - r * 0.08, r * 0.07, 0, TAU2); g.fill(); }
    g.fillStyle = '#4a4f58'; g.beginPath(); g.arc(hd[0] + J.facing * r * 0.05, hd[1] + r * 0.5, r * 0.25, 0, TAU2); g.fill();
    g.restore(); return;
  }
  limbLine([J.sh, [hd[0], hd[1] + r * 0.7]], limb * 0.95, skin);
  if (style === 2) blob(() => { g.moveTo(hd[0] - r * 1.05, hd[1]); g.lineTo(hd[0] - r * 1.1, hd[1] + r * 1.25); g.lineTo(hd[0] + r * 1.1, hd[1] + r * 1.25); g.lineTo(hd[0] + r * 1.05, hd[1]); g.closePath(); }, hair);   // long hair behind
  for (const ex of [-1, 1]) blob(() => g.ellipse(hd[0] + ex * r * 0.98, hd[1] + r * 0.08, r * 0.2, r * 0.27, 0, 0, TAU2), skin);
  blob(() => g.ellipse(hd[0], hd[1], r * 0.98, r * 1.04, 0, 0, TAU2), skin);
  g.fillStyle = hair; g.strokeStyle = ol; g.lineWidth = ow;
  if (style === 0 || style === 2) { g.beginPath(); g.ellipse(hd[0], hd[1] - r * 0.12, r * 1.02, r * 0.95, 0, Math.PI * 1.02, Math.PI * 1.98); g.quadraticCurveTo(hd[0] + r * 0.2, hd[1] - r * 0.45, hd[0] - r * 1.0, hd[1] - r * 0.1); g.closePath(); g.fill(); g.stroke(); }
  else if (style === 1) { g.beginPath(); g.ellipse(hd[0], hd[1] - r * 0.2, r * 1.04, r * 0.9, 0, Math.PI, TAU2); g.lineTo(hd[0] + r * 1.04, hd[1] - r * 0.1); g.lineTo(hd[0] - r * 1.04, hd[1] - r * 0.1); g.closePath(); g.fill(); g.stroke(); g.fillRect(hd[0] - r * 0.1, hd[1] - r * 0.32, r * 1.1 * J.facing, r * 0.12); }       // cap
  else if (style === 3) { g.beginPath(); g.ellipse(hd[0], hd[1] - r * 0.15, r * 1.0, r * 0.92, 0, Math.PI * 1.05, Math.PI * 1.95); g.closePath(); g.fill(); g.stroke(); g.beginPath(); g.arc(hd[0], hd[1] - r * 1.15, r * 0.35, 0, TAU2); g.fill(); g.stroke(); }  // bun
  else { g.beginPath(); g.ellipse(hd[0], hd[1] - r * 0.35, r * 0.85, r * 0.55, 0, Math.PI * 1.1, Math.PI * 1.9); g.fill(); }                                         // short / thin
  const eo = stare ? 0 : J.facing * r * 0.1, ey = hd[1] + r * 0.05, big = face === 'scared' ? 1.25 : 1;
  for (const ex of [-0.36, 0.36]) { g.fillStyle = '#fbfbfb'; g.beginPath(); g.ellipse(hd[0] + ex * r + eo, ey, r * 0.22 * big, r * 0.25 * big, 0, 0, TAU2); g.fill(); g.strokeStyle = ol; g.lineWidth = ow * 0.7; g.stroke();
    g.fillStyle = '#15171c'; g.beginPath(); g.arc(hd[0] + ex * r + eo + J.facing * r * 0.05, ey + r * 0.02, r * (face === 'scared' ? 0.07 : 0.1), 0, TAU2); g.fill(); }
  g.strokeStyle = '#2a211b'; g.lineWidth = Math.max(1.2, r * 0.07);
  for (const ex of [-0.36, 0.36]) { const tilt = face === 'scared' ? (ex < 0 ? 0.08 : -0.08) : 0; g.beginPath(); g.moveTo(hd[0] + ex * r + eo - r * 0.2, ey - r * (0.4 - tilt)); g.lineTo(hd[0] + ex * r + eo + r * 0.2, ey - r * (0.4 + tilt)); g.stroke(); }
  g.strokeStyle = darker(skin, 0.3); g.lineWidth = Math.max(1, r * 0.06); g.beginPath(); g.moveTo(hd[0] + eo * 1.4, ey + r * 0.12); g.lineTo(hd[0] + eo * 1.4 + J.facing * r * 0.08, ey + r * 0.32); g.stroke();
  const mx = hd[0] + eo * 0.8, my = hd[1] + r * 0.62;
  if (face === 'grin') { g.fillStyle = '#15171c'; g.beginPath(); g.ellipse(mx, my - r * 0.06, r * 0.66, r * 0.34, 0, 0, Math.PI); g.closePath(); g.fill(); g.fillStyle = '#f4f4f4'; g.fillRect(mx - r * 0.6, my - r * 0.06, r * 1.2, r * 0.14); g.strokeStyle = '#15171c'; g.lineWidth = Math.max(1, r * 0.04); for (let k = -4; k <= 4; k++) { g.beginPath(); g.moveTo(mx + k * r * 0.13, my - r * 0.06); g.lineTo(mx + k * r * 0.13, my + r * 0.08); g.stroke(); } }
  else if (face === 'scared') { g.fillStyle = '#2a1414'; g.beginPath(); g.ellipse(mx, my, r * 0.13, r * 0.18, 0, 0, TAU2); g.fill(); }
  else { g.strokeStyle = '#6b3b33'; g.lineWidth = Math.max(1.2, r * 0.06); g.beginPath(); g.moveTo(mx - r * 0.18, my); g.quadraticCurveTo(mx, my + r * 0.05, mx + r * 0.18, my); g.stroke(); }
  g.restore();
}

export function drawChair(g, J, lw, color = WHITE) {
  g.save(); g.strokeStyle = color; g.lineWidth = lw; g.lineCap = 'round';
  const seatY = J.hip[1] + lw * 1.2, w = J.r * 3.2, x = J.hip[0];
  g.beginPath(); g.moveTo(x - w * 0.7 * J.facing, seatY); g.lineTo(x + w * 0.9 * J.facing, seatY);
  g.moveTo(x - w * 0.7 * J.facing, seatY); g.lineTo(x - w * 0.7 * J.facing, seatY - w * 1.6);
  g.moveTo(x + w * 0.8 * J.facing, seatY); g.lineTo(x + w * 0.8 * J.facing, J.low);
  g.moveTo(x - w * 0.6 * J.facing, seatY); g.lineTo(x - w * 0.6 * J.facing, J.low); g.stroke(); g.restore();
}

// ---------------------------------------------------------------- tags, sight lines, ring, danger cross
export function drawTag(g, text, x, y, px, { color = WHITE, font, fill = false } = {}) {
  g.save(); g.font = font || `700 ${Math.round(px)}px sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
  const pad = px * 0.55, w = g.measureText(text).width + pad * 2, h = px * 1.55;
  g.lineWidth = Math.max(2, px * 0.09); g.strokeStyle = color;
  if (fill) { g.fillStyle = color; g.fillRect(x - w / 2, y - h / 2, w, h); g.fillStyle = BLACK; } else { g.fillStyle = BLACK; g.fillRect(x - w / 2, y - h / 2, w, h); g.strokeRect(x - w / 2, y - h / 2, w, h); g.fillStyle = color; }
  g.fillText(text, x, y + px * 0.04); g.restore();
  return { w, h };
}

export function drawSight(g, a, b, t, lw, { color = RED, dash = true, grow = 1 } = {}) {
  g.save(); g.strokeStyle = color; g.lineWidth = lw; g.lineCap = 'round';
  const bx = lerp(a[0], b[0], clamp01(grow)), by = lerp(a[1], b[1], clamp01(grow));
  if (dash) { g.setLineDash([lw * 3.2, lw * 2.8]); g.lineDashOffset = -t * lw * 6; }
  g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(bx, by); g.stroke();
  g.setLineDash([]);
  if (grow >= 1) { const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), s = lw * 5; g.fillStyle = color; g.beginPath(); g.moveTo(b[0], b[1]);
    g.lineTo(b[0] - Math.cos(ang - 0.45) * s, b[1] - Math.sin(ang - 0.45) * s); g.lineTo(b[0] - Math.cos(ang + 0.45) * s, b[1] - Math.sin(ang + 0.45) * s); g.closePath(); g.fill(); }
  g.restore();
}

export function drawRing(g, x, y, r, frac, lw, text, font, { color = RED } = {}) {
  g.save(); g.lineWidth = lw; g.lineCap = 'round';
  g.strokeStyle = 'rgba(242,242,242,0.25)'; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.stroke();
  g.strokeStyle = color; g.beginPath(); g.arc(x, y, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * clamp01(frac)); g.stroke();
  g.fillStyle = WHITE; g.font = font; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(text, x, y); g.restore();
}

export function drawCross(g, x, y, r, lw, color = RED) {
  g.save(); g.strokeStyle = color; g.lineWidth = lw * 1.4; g.lineCap = 'round';
  g.beginPath(); g.moveTo(x - r, y - r); g.lineTo(x + r, y + r); g.moveTo(x + r, y - r); g.lineTo(x - r, y + r); g.stroke(); g.restore();
}

// ---------------------------------------------------------------- sets (line-drawn)
const hash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
export const SET_NAMES = ['bedroom', 'hallway', 'house_section', 'yard', 'door', 'window', 'classroom', 'stairs', 'hall_lit', 'street', 'cutaway', 'cabin', 'store', 'bathroom', 'kitchen', 'hall_mirror'];
export const setGround = (name) => ({ bedroom: 0.80, hallway: 0.80, house_section: 0.84, yard: 0.80, door: 0.88, window: 0.88, classroom: 0.82, stairs: 0.84, hall_lit: 0.80, street: 0.80, cutaway: 0.84, cabin: 0.90, store: 0.90, bathroom: 0.84, kitchen: 0.84, hall_mirror: 0.80 }[name] ?? 0.80);

export function drawSet(g, name, W, H, lw, t = 0, pal = null) {
  const nm = SET_NAMES.includes(name) ? name : 'yard';
  g.save(); g.strokeStyle = pal ? pal.line : WHITE; g.fillStyle = BLACK; g.lineWidth = lw; g.lineCap = 'round'; g.lineJoin = 'round';
  const gy = H * setGround(nm);
  const L = (x1, y1, x2, y2) => { g.beginPath(); g.moveTo(x1 * W, y1 * H); g.lineTo(x2 * W, y2 * H); g.stroke(); };
  const R = (x, y, w, h) => { g.strokeRect(x * W, y * H, w * W, h * H); };
  const moon = (x, y, r) => { g.beginPath(); g.arc(x * W, y * H, r * H, 0, Math.PI * 2); g.stroke(); };
  const clock = (x, y, s) => { R(x, y, s, s * (W / H) * 0.6); };
  const floor = () => L(0.02, gy / H, 0.98, gy / H);
  if (pal) {                                                              // colour: a floor, and a wall where the set is a room
    const wall = { bedroom: [0.02, 0.18, 0.96, 0.62], classroom: [0.02, 0.0, 0.96, 0.82], stairs: [0.02, 0.1, 0.96, 0.74], cutaway: [0.10, 0.23, 0.8, 0.61], house_section: [0.18, 0.28, 0.46, 0.56], door: [0.0, 0.0, 1.0, 0.88], window: [0.0, 0.0, 1.0, 0.88],
      hallway: [0, 0, 1, 1], hall_lit: [0, 0, 1, 1], cabin: [0, 0, 1, 1], store: [0, 0, 1, 1], hall_mirror: [0, 0, 1, 1], bathroom: [0, 0, 1, 0.84], kitchen: [0, 0, 1, 0.84] }[nm];
    if (wall) { g.fillStyle = pal.wall; g.fillRect(wall[0] * W, wall[1] * H, wall[2] * W, wall[3] * H); }
    if (!['hallway', 'hall_lit', 'cabin', 'store', 'hall_mirror'].includes(nm)) { g.fillStyle = pal.floor; g.fillRect(0, gy, W, H - gy); }
    else { g.fillStyle = pal.floor; g.beginPath(); g.moveTo(0, H); g.lineTo(W, H); g.lineTo(0.59 * W, 0.62 * H); g.lineTo(0.41 * W, 0.62 * H); g.closePath(); g.fill(); }
    g.fillStyle = BLACK;
  }
  if (nm === 'bedroom') {
    floor(); L(0.02, 0.18, 0.98, 0.18);                                  // ceiling line
    R(0.60, 0.30, 0.13, 0.22); L(0.665, 0.30, 0.665, 0.52); L(0.60, 0.41, 0.73, 0.41); moon(0.69, 0.22, 0.03);  // window + moon
    R(0.12, 0.60, 0.34, 0.12); R(0.12, 0.56, 0.05, 0.16); R(0.40, 0.66, 0.06, 0.06); L(0.12, 0.72, 0.12, gy / H); L(0.46, 0.72, 0.46, gy / H);   // bed
    R(0.50, 0.63, 0.08, 0.17); clock(0.52, 0.55, 0.035);                  // bedside table + clock
    R(0.82, 0.34, 0.11, 0.46); g.beginPath(); g.arc(0.84 * W, 0.58 * H, 0.006 * W, 0, 7); g.stroke();   // door
  } else if (nm === 'hallway') {
    const vx = 0.5, vy = 0.46;
    L(0.0, 0.0, vx - 0.09, vy - 0.12); L(1.0, 0.0, vx + 0.09, vy - 0.12); L(0.0, 1.0, vx - 0.09, vy + 0.16); L(1.0, 1.0, vx + 0.09, vy + 0.16);
    R(vx - 0.09, vy - 0.12, 0.18, 0.28);
    for (const k of [0.25, 0.5, 0.72]) {                                  // doors on both walls, shrinking toward the end
      const top = lerp(0.18, vy - 0.07, k), bot = lerp(0.82, vy + 0.11, k), xa = lerp(0.04, vx - 0.075, k), xb = lerp(0.12, vx - 0.065, k);
      L(xa, top, xb, top + 0.01); L(xa, bot, xb, bot - 0.01); L(xa, top, xa, bot); L(xb, top + 0.01, xb, bot - 0.01);
      L(1 - xa, top, 1 - xb, top + 0.01); L(1 - xa, bot, 1 - xb, bot - 0.01); L(1 - xa, top, 1 - xa, bot); L(1 - xb, top + 0.01, 1 - xb, bot - 0.01);
    }
  } else if (nm === 'house_section') {
    L(0.02, gy / H, 0.98, gy / H);
    R(0.18, 0.28, 0.46, 0.56); L(0.14, 0.28, 0.41, 0.10); L(0.41, 0.10, 0.68, 0.28);                   // house + roof
    L(0.18, 0.56, 0.64, 0.56);                                                                          // floor between storeys
    L(0.41, 0.28, 0.41, 0.56);                                                                          // wall upstairs
    R(0.23, 0.36, 0.08, 0.12); L(0.27, 0.36, 0.27, 0.48); R(0.50, 0.36, 0.08, 0.12);                   // windows
    for (let i = 0; i < 6; i++) { L(0.44 + i * 0.022, 0.56 + i * 0.045, 0.44 + (i + 1) * 0.022, 0.56 + i * 0.045); L(0.44 + (i + 1) * 0.022, 0.56 + i * 0.045, 0.44 + (i + 1) * 0.022, 0.56 + (i + 1) * 0.045); }
    R(0.55, 0.62, 0.07, 0.22); R(0.22, 0.64, 0.10, 0.08);
    for (let x = 0.70; x < 0.97; x += 0.045) { L(x, gy / H - 0.09, x, gy / H); } L(0.70, gy / H - 0.06, 0.97, gy / H - 0.06); moon(0.86, 0.16, 0.035);
  } else if (nm === 'yard') {
    floor(); moon(0.82, 0.16, 0.05);
    R(0.06, 0.34, 0.26, 0.46); L(0.04, 0.34, 0.19, 0.20); L(0.19, 0.20, 0.34, 0.34); R(0.11, 0.46, 0.07, 0.12); L(0.145, 0.46, 0.145, 0.58); R(0.22, 0.58, 0.06, 0.22);   // house
    for (let x = 0.42; x < 0.99; x += 0.055) { L(x, gy / H - 0.13, x, gy / H); L(x - 0.008, gy / H - 0.13, x, gy / H - 0.15); L(x + 0.008, gy / H - 0.13, x, gy / H - 0.15); }
    L(0.42, gy / H - 0.09, 0.99, gy / H - 0.09); L(0.42, gy / H - 0.04, 0.99, gy / H - 0.04);
    L(0.36, gy / H, 0.36, 0.52); L(0.36, 0.58, 0.31, 0.50); L(0.36, 0.52, 0.40, 0.44); L(0.36, 0.64, 0.41, 0.56);   // bare tree
  } else if (nm === 'door') {
    floor(); R(0.36, 0.14, 0.28, 0.74); R(0.39, 0.18, 0.22, 0.30); R(0.39, 0.52, 0.22, 0.30);
    g.beginPath(); g.arc(0.58 * W, 0.54 * H, 0.012 * W, 0, 7); g.stroke();
    L(0.37, 0.88, 0.63, 0.88);                                            // crack of light under the door
  } else if (nm === 'window') {
    floor(); R(0.30, 0.16, 0.40, 0.56); L(0.50, 0.16, 0.50, 0.72); L(0.30, 0.44, 0.70, 0.44); R(0.28, 0.72, 0.44, 0.03); moon(0.62, 0.30, 0.03);
    L(0.26, 0.12, 0.26, 0.76); L(0.74, 0.12, 0.74, 0.76); L(0.26, 0.12, 0.31, 0.16); L(0.74, 0.12, 0.69, 0.16);   // curtain edges
  } else if (nm === 'stairs') {
    floor(); R(0.62, 0.20, 0.13, 0.64); g.beginPath(); g.arc(0.725 * W, 0.52 * H, 0.006 * W, 0, 7); g.stroke();                  // a door at the top landing
    L(0.10, gy / H, 0.62, 0.52); for (let i = 0; i < 8; i++) { const x = 0.10 + i * 0.065, y = gy / H - i * 0.04; L(x, y, x + 0.065, y); L(x + 0.065, y, x + 0.065, y - 0.04); }
    L(0.62, 0.52, 0.92, 0.52); L(0.10, gy / H - 0.17, 0.62, 0.35); moon(0.85, 0.12, 0.03);
  } else if (nm === 'hall_lit') {                                         // a hallway ending in a lit doorway
    const vx = 0.5, vy = 0.46;
    L(0.0, 0.0, vx - 0.07, vy - 0.12); L(1.0, 0.0, vx + 0.07, vy - 0.12); L(0.0, 1.0, vx - 0.07, vy + 0.16); L(1.0, 1.0, vx + 0.07, vy + 0.16);
    g.fillStyle = '#2b2812'; g.fillRect((vx - 0.07) * W, (vy - 0.12) * H, 0.14 * W, 0.28 * H); R(vx - 0.07, vy - 0.12, 0.14, 0.28);
    for (const s of [-1, 1]) for (const k of [0.3, 0.62]) { const top = lerp(0.2, vy - 0.08, k), bot = lerp(0.8, vy + 0.12, k), xa = lerp(0.04, vx - 0.06, k); const X = s < 0 ? xa : 1 - xa; L(X, top, X, bot); }
    g.fillStyle = '#E8C21A'; g.globalAlpha = 0.2; g.beginPath(); g.moveTo((vx - 0.07) * W, (vy + 0.16) * H); g.lineTo((vx + 0.07) * W, (vy + 0.16) * H); g.lineTo(0.78 * W, H); g.lineTo(0.22 * W, H); g.closePath(); g.fill(); g.globalAlpha = 1;
    g.fillStyle = WHITE; const fx = vx * W, fy = (vy + 0.16) * H; g.beginPath(); g.arc(fx, fy - 0.19 * H * 0.98, 0.016 * H, 0, 7); g.fill(); g.fillRect(fx - 0.007 * W, fy - 0.17 * H, 0.014 * W, 0.1 * H);
    g.fillRect(fx - 0.007 * W, fy - 0.075 * H, 0.005 * W, 0.075 * H); g.fillRect(fx + 0.002 * W, fy - 0.075 * H, 0.005 * W, 0.075 * H);
  } else if (nm === 'street') {                                           // a street lamp with a cone of light, a bare tree, a kerb
    floor(); L(0.02, gy / H + 0.05, 0.98, gy / H + 0.05); L(0.18, gy / H, 0.18, 0.28); L(0.18, 0.28, 0.24, 0.26); R(0.235, 0.24, 0.045, 0.03);
    g.fillStyle = '#E8C21A'; g.globalAlpha = 0.16; g.beginPath(); g.moveTo(0.24 * W, 0.28 * H); g.lineTo(0.38 * W, gy); g.lineTo(0.10 * W, gy); g.closePath(); g.fill(); g.globalAlpha = 1;
    L(0.78, gy / H, 0.78, 0.38); L(0.78, 0.50, 0.72, 0.42); L(0.78, 0.44, 0.84, 0.34); L(0.78, 0.58, 0.85, 0.50); moon(0.55, 0.14, 0.03);
    for (let i = 0; i < 14; i++) { const sx = (hash(i * 3.1) * 0.9 + 0.05), sy = hash(i * 7.7) * 0.4 + 0.04; g.fillStyle = WHITE; g.fillRect(sx * W, sy * H, 2, 2); }
  } else if (nm === 'cabin') {                                            // an aircraft cabin from the aisle: rows of seat backs with heads, overhead bins
    const vx = 0.5, vy = 0.42;
    L(0.0, 0.08, vx - 0.07, vy - 0.12); L(1.0, 0.08, vx + 0.07, vy - 0.12); L(0.0, 1.0, vx - 0.07, vy + 0.14); L(1.0, 1.0, vx + 0.07, vy + 0.14);
    L(0.0, 0.22, vx - 0.07, vy - 0.07); L(1.0, 0.22, vx + 0.07, vy - 0.07); R(vx - 0.07, vy - 0.12, 0.14, 0.26);
    for (let k = 0; k < 6; k++) { const f = 1 - k / 6.5, sc = 0.18 + 0.82 * f * f, y = vy + 0.14 + (0.86 - 0.0) * f * f * 0.9;
      for (const side of [-1, 1]) { const cx = vx + side * (0.06 + 0.3 * f * f), w = 0.075 * sc * 1.8, h = 0.16 * sc * 1.8;
        g.fillStyle = '#141414'; g.fillRect((cx - w / 2) * W, (y - h) * H, w * W, h * H); g.strokeRect((cx - w / 2) * W, (y - h) * H, w * W, h * H);
        if (hash(k * 5 + side) > 0.35) { g.fillStyle = '#9a9a9a'; g.beginPath(); g.arc(cx * W, (y - h * 1.05) * H, w * W * 0.22, 0, 7); g.fill(); } } }
    g.fillStyle = BLACK;
  } else if (nm === 'store') {                                            // a shop aisle: shelf banks with coloured goods either side, a double door at the end under a blue sign
    const vx = 0.5, vy = 0.44, cols = ['#d94f4f', '#e8c63a', '#3fa56b', '#3d78d8', '#e98a2f', '#a86bd1'];
    for (const side of [-1, 1]) {
      const x0 = side < 0 ? 0 : 1, x1 = vx + side * 0.13;
      for (let sh = 0; sh < 5; sh++) {
        const a = sh / 5, b = (sh + 0.78) / 5, yA0 = lerp(0.16, vy - 0.1, 0), yTop = (u) => lerp(0.14, vy - 0.08, u), yBot = (u) => lerp(0.98, vy + 0.15, u);
        const ya = lerp(yTop(0), yBot(0), a), yb = lerp(yTop(0), yBot(0), b), za = lerp(yTop(1), yBot(1), a), zb = lerp(yTop(1), yBot(1), b);
        if (pal) { g.fillStyle = pal.floor; g.beginPath(); g.moveTo(x0 * W, ya * H); g.lineTo(x1 * W, za * H); g.lineTo(x1 * W, zb * H); g.lineTo(x0 * W, yb * H); g.closePath(); g.fill();
          for (let k = 0; k < 9; k++) { const u0 = k / 9, u1 = (k + 0.7) / 9, X = (u) => lerp(x0, x1, u), Ya = (u) => lerp(lerp(yTop(u), yBot(u), a), lerp(yTop(u), yBot(u), b), 0.2), Yb = (u) => lerp(lerp(yTop(u), yBot(u), a), lerp(yTop(u), yBot(u), b), 0.95);
            g.fillStyle = cols[Math.floor(hash(sh * 11 + k * 3 + side) * 6)]; g.beginPath(); g.moveTo(X(u0) * W, Ya(u0) * H); g.lineTo(X(u1) * W, Ya(u1) * H); g.lineTo(X(u1) * W, Yb(u1) * H); g.lineTo(X(u0) * W, Yb(u0) * H); g.closePath(); g.fill(); } }
        L(x0, yb, x1, zb);
      }
      L(x0, 0.14, x1, vy - 0.08); L(x0, 0.98, x1, vy + 0.15);
    }
    g.fillStyle = pal ? '#cfd6e0' : BLACK; g.fillRect((vx - 0.13) * W, (vy - 0.08) * H, 0.26 * W, 0.23 * H); R(vx - 0.13, vy - 0.08, 0.26, 0.23);
    g.fillStyle = pal ? '#3b4a63' : BLACK; g.fillRect((vx - 0.06) * W, (vy - 0.02) * H, 0.12 * W, 0.17 * H); R(vx - 0.06, vy - 0.02, 0.12, 0.17); L(vx, vy - 0.02, vx, vy + 0.15);
    g.fillStyle = pal ? '#2f58b8' : BLACK; g.fillRect((vx - 0.045) * W, (vy - 0.07) * H, 0.09 * W, 0.04 * H); R(vx - 0.045, vy - 0.07, 0.09, 0.04);
    for (const lx of [0.3, 0.5, 0.7]) { g.fillStyle = pal ? '#fffbe0' : BLACK; g.fillRect((lx - 0.04) * W, 0.02 * H, 0.08 * W, 0.02 * H); R(lx - 0.04, 0.02, 0.08, 0.02); }
    g.fillStyle = BLACK;
  } else if (nm === 'bathroom') {                                         // a sink wall: tiles, a door, a towel on a hook, a cabinet and basin, a framed mirror with a lamp above
    floor(); g.save(); g.globalAlpha = 0.28; for (let x = 0.06; x < 0.99; x += 0.09) L(x, 0.0, x, gy / H); for (let y = 0.1; y < gy / H; y += 0.12) L(0.0, y, 1.0, y); g.restore();
    R(0.04, 0.26, 0.11, gy / H - 0.26); g.beginPath(); g.arc(0.135 * W, 0.56 * H, 0.006 * W, 0, 7); g.stroke();
    L(0.22, 0.30, 0.22, 0.28); R(0.205, 0.31, 0.04, 0.15); L(0.205, 0.37, 0.245, 0.37);
    R(0.58, 0.60, 0.30, gy / H - 0.60); L(0.58, 0.60, 0.88, 0.60); L(0.73, 0.60, 0.73, 0.54); L(0.73, 0.54, 0.70, 0.54); L(0.73, 0.64, 0.73, gy / H);
    R(0.58, 0.12, 0.30, 0.44); R(0.59, 0.13, 0.28, 0.42); R(0.66, 0.05, 0.14, 0.03);
    g.fillStyle = pal ? '#cfe0ee' : BLACK; g.fillRect(0.59 * W, 0.13 * H, 0.28 * W, 0.42 * H);
    if (pal) { g.fillStyle = pal.glow; g.globalAlpha = 0.5; g.fillRect(0.66 * W, 0.05 * H, 0.14 * W, 0.03 * H); g.globalAlpha = 1; }
    g.fillStyle = BLACK;
  } else if (nm === 'kitchen') {                                          // counter and cupboards, a window, a fridge, a table, a hanging lamp
    floor(); R(0.05, 0.60, 0.38, gy / H - 0.60); L(0.05, 0.60, 0.43, 0.60); R(0.05, 0.18, 0.38, 0.16); L(0.24, 0.18, 0.24, 0.34); L(0.24, 0.60, 0.24, gy / H);
    R(0.50, 0.20, 0.14, 0.2); L(0.57, 0.20, 0.57, 0.40); L(0.50, 0.30, 0.64, 0.30);
    R(0.78, 0.16, 0.14, gy / H - 0.16); L(0.78, 0.44, 0.92, 0.44); L(0.80, 0.24, 0.80, 0.34); L(0.80, 0.50, 0.80, 0.60);
    L(0.52, 0.66, 0.70, 0.66); L(0.54, 0.66, 0.54, gy / H); L(0.68, 0.66, 0.68, gy / H);
    L(0.46, 0.0, 0.46, 0.10); g.beginPath(); g.arc(0.46 * W, 0.12 * H, 0.025 * H, 0, 7); g.stroke();
    if (pal) { g.fillStyle = pal.glow; g.globalAlpha = 0.25; g.beginPath(); g.arc(0.46 * W, 0.12 * H, 0.12 * H, 0, 7); g.fill(); g.globalAlpha = 1; g.fillStyle = BLACK; }
  } else if (nm === 'hall_mirror') {                                      // a hallway whose far end is a tall mirror with a glint
    const vx = 0.5, vy = 0.46;
    L(0.0, 0.0, vx - 0.07, vy - 0.12); L(1.0, 0.0, vx + 0.07, vy - 0.12); L(0.0, 1.0, vx - 0.07, vy + 0.16); L(1.0, 1.0, vx + 0.07, vy + 0.16);
    for (const k of [0.3, 0.62]) for (const sd of [-1, 1]) { const top = lerp(0.2, vy - 0.08, k), bot = lerp(0.8, vy + 0.12, k), xa = lerp(0.04, vx - 0.06, k); const X = sd < 0 ? xa : 1 - xa; L(X, top, X, bot); }
    g.fillStyle = pal ? '#cfd8e2' : BLACK; g.fillRect((vx - 0.07) * W, (vy - 0.12) * H, 0.14 * W, 0.28 * H); R(vx - 0.07, vy - 0.12, 0.14, 0.28);
    g.save(); g.globalAlpha = 0.5; L(vx - 0.05, vy + 0.1, vx - 0.01, vy - 0.1); L(vx - 0.02, vy + 0.1, vx + 0.02, vy - 0.1); g.restore(); g.fillStyle = BLACK;
  } else if (nm === 'cutaway') {                                          // a house in section: two floors, stairs, a bed upstairs, a sofa and a cupboard below
    const x0 = 0.10, x1 = 0.90, y0 = 0.16, ym = 0.50, y1 = 0.84;
    R(x0, ym, x1 - x0, y1 - ym); R(x0, y0 + 0.07, x1 - x0, ym - y0 - 0.07); L(x0 - 0.02, y0 + 0.07, 0.50, y0); L(0.50, y0, x1 + 0.02, y0 + 0.07); L(0.50, y0 + 0.07, 0.50, ym);
    L(0.02, y1, 0.98, y1);
    for (let i = 0; i < 7; i++) { const x = 0.42 + i * 0.03, y = y1 - i * 0.048; L(x, y, x + 0.03, y); L(x + 0.03, y, x + 0.03, y - 0.048); }
    R(0.14, ym - 0.1, 0.22, 0.05); R(0.14, ym - 0.14, 0.03, 0.09); L(0.14, ym - 0.05, 0.14, ym); L(0.36, ym - 0.05, 0.36, ym);          // bed upstairs
    R(0.14, y1 - 0.09, 0.15, 0.09); R(0.14, y1 - 0.15, 0.03, 0.06); R(0.76, y1 - 0.26, 0.08, 0.26); R(0.62, ym - 0.17, 0.08, 0.17); R(0.15, ym + 0.06, 0.07, 0.10); R(0.78, ym + 0.06, 0.07, 0.10);
    moon(0.95, 0.12, 0.03);
  } else {                                                               // classroom: a grid of desks, one empty seat
    floor(); R(0.30, 0.10, 0.40, 0.12); L(0.30, 0.16, 0.70, 0.16);       // board
    for (let r = 0; r < 2; r++) for (let c = 0; c < 5; c++) { const x = 0.12 + c * 0.17, y = 0.50 + r * 0.17; R(x, y, 0.09, 0.045); L(x + 0.01, y + 0.045, x + 0.01, y + 0.10); L(x + 0.08, y + 0.045, x + 0.08, y + 0.10); }
  }
  g.restore();
}

// ---------------------------------------------------------------- typed card text
export function wrapText(g, text, maxW) {
  const words = String(text).split(/\s+/).filter(Boolean), lines = [];
  let cur = '';
  for (const w of words) { const next = cur ? `${cur} ${w}` : w; if (cur && g.measureText(next).width > maxW) { lines.push(cur); cur = w; } else cur = next; }
  if (cur) lines.push(cur);
  return lines;
}
/** How many characters are typed at age seconds: ~30 per second after a short beat, with tiny deterministic stalls. */
export const typedCount = (age, cps = 30, delay = 0.25) => Math.max(0, Math.floor((age - delay) * cps));

// ---------------------------------------------------------------- glitch (colour split + torn strips + static)
export const glitchOn = (def, t) => {
  const b = def.bursts;
  if (!b || !b.length) return 1;
  for (const x of b) if (t >= x.at && t <= x.at + (x.dur ?? 0.25)) return x.amount ?? 1;
  return 0;
};
export function drawGlitch(g, W, H, t, amount, mk) {
  if (amount <= 0.01) return;
  const step = Math.floor(t * 24), r = (i) => hash(step * 13.7 + i);
  const shift = Math.round(W * 0.012 * amount * (0.6 + r(1)));
  if (mk) {
    const src = mk.copy(g);                                              // the frame so far
    g.save(); g.globalCompositeOperation = 'source-over'; g.fillStyle = BLACK; g.fillRect(0, 0, W, H);
    g.globalCompositeOperation = 'lighter';
    g.drawImage(mk.tint(src, '#ff0000'), -shift, 0); g.drawImage(mk.tint(src, '#00ffff'), shift, 0);
    g.globalCompositeOperation = 'source-over';
    for (let i = 0; i < 4; i++) {                                         // torn horizontal strips
      const y = Math.floor(r(2 + i) * H * 0.9), h = Math.floor(H * (0.01 + r(8 + i) * 0.05)), dx = Math.round((r(14 + i) - 0.5) * W * 0.12 * amount);
      g.drawImage(src, 0, y, W, h, dx, y, W, h);
    }
    g.restore();
  }
  g.save();                                                              // static: thin light scan lines + dark bars
  g.fillStyle = `rgba(255,255,255,${0.10 * amount})`;
  for (let i = 0; i < 18; i++) g.fillRect(0, Math.floor(r(30 + i) * H), W, 1 + Math.floor(r(50 + i) * 2));
  g.fillStyle = `rgba(0,0,0,${0.35 * amount})`;
  for (let i = 0; i < 3; i++) g.fillRect(0, Math.floor(r(70 + i) * H), W, Math.floor(H * 0.012));
  g.restore();
}

// ---------------------------------------------------------------- shared by the layers
/** A stable but alive camera: a tiny constant drift, plus an optional slow push-in ({push, start, end} on def.cam). The planner gives every layer of a shot the same cam. */
export function applyCam(g, W, H, def, t) {
  const c = def.cam || {}, s0 = c.start ?? def.start ?? 0, e0 = c.end ?? def.end ?? s0 + 4;
  const k = smooth((t - s0) / Math.max(0.1, e0 - s0)), sc = (c.zoom ?? 1) * (1 + (c.push ?? 0) * k);
  const dx = Math.sin(t * 0.55) * W * 0.0025, dy = Math.cos(t * 0.43) * H * 0.002;
  if (c.focus) { g.translate(W / 2 + dx, H / 2 + dy); g.scale(sc, sc); g.translate(-c.focus[0] * W, -c.focus[1] * H); return; }    // zoom into a point of the frame
  g.translate(W / 2 + dx, H / 2 + dy); g.scale(sc, sc); g.translate(-W / 2, -H / 2);
}
export const lineWidth = (H) => Math.max(2, H * 0.0048);
/** Offscreen canvases for the glitch (browser only; node tests pass no document and the glitch draws only its static). */
export function makeMk(W, H) {
  if (typeof document === 'undefined') return null;
  const mk = () => { const c = document.createElement('canvas'); c.width = W; c.height = H; return c; };
  const a = mk(), b = mk();
  return {
    copy(g) { const x = a.getContext('2d'); x.globalCompositeOperation = 'source-over'; x.clearRect(0, 0, W, H); x.drawImage(g.canvas, 0, 0); return a; },
    tint(src, colour) { const x = b.getContext('2d'); x.globalCompositeOperation = 'source-over'; x.clearRect(0, 0, W, H); x.drawImage(src, 0, 0);
      x.globalCompositeOperation = 'multiply'; x.fillStyle = colour; x.fillRect(0, 0, W, H); x.globalCompositeOperation = 'source-over'; return b; },
  };
}
