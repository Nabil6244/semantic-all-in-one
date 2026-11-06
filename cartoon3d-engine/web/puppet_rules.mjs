// The 2D puppet's rules, free of Three.js and canvas so they can be tested on their own: what the voice does to her mouth,
// what a gesture does to her body and arms.

// Mouth per viseme: o = how open 0..1, w = width (1 = her drawn smile), r = round, teeth, ff = top teeth on the lower lip.
const SHAPES = {
  aa: { o: 1, w: 1, teeth: 0.7 }, E: { o: 0.55, w: 1.04, teeth: 1 }, I: { o: 0.38, w: 1.04, teeth: 1 },
  O: { o: 0.82, w: 0.6, r: 1 }, U: { o: 0.5, w: 0.48, r: 1 }, PP: { o: 0, w: 0.82 }, FF: { o: 0.2, w: 0.8, ff: 1, teeth: 1 },
  TH: { o: 0.25, w: 0.85, teeth: 1 }, DD: { o: 0.3, w: 0.88, teeth: 0.8 }, kk: { o: 0.36, w: 0.9, teeth: 0.5 }, CH: { o: 0.3, w: 0.68, r: 0.5, teeth: 0.8 },
  SS: { o: 0.17, w: 0.95, teeth: 1 }, nn: { o: 0.22, w: 0.88, teeth: 0.6 }, RR: { o: 0.3, w: 0.7, r: 0.45, teeth: 0.4 },
};
const REST = { o: 0, w: 0.92, r: 0, teeth: 0, ff: 0 };

/** Viseme weights { aa: 0..1, ... } at time t from plan.visemeTrack. */
export function visemeWeights(track, t) {
  if (!track || !track.frames.length) return {};
  const n = track.frames.length, k = Math.max(0, t * track.fps), i = Math.floor(k), f = k - i;
  const a = track.frames[Math.min(n - 1, i)], b = track.frames[Math.min(n - 1, i + 1)], out = {};
  track.names.forEach((name, j) => { const x = (a[j] * (1 - f) + b[j] * f) / 100; if (x > 0.002) out[name] = x; });
  return out;
}

/** One mouth from the mixed visemes; no visemes = closed in her smile. */
export function mouthShape(weights) {
  const out = { ...REST }; let sum = 0;
  for (const [name, x] of Object.entries(weights)) if (SHAPES[name]) sum += x;
  if (sum < 1e-3) return out;
  const amount = Math.min(1, sum * 1.5);                                       // quiet words still shape the mouth clearly
  for (const key of Object.keys(REST)) {
    let v = 0;
    for (const [name, x] of Object.entries(weights)) { const sh = SHAPES[name]; if (sh) v += (x / sum) * (sh[key] ?? REST[key]); }
    out[key] = REST[key] + (v - REST[key]) * amount;
  }
  return out;
}

/** 1 while she is in a spoken line (her drawn mouth is showing), 0 between lines (her own picture's smile), eased at both ends. */
export function speakingAmount(lines, t) {
  let best = 0;
  for (const l of lines || []) {
    const up = (t - (l.t0 - 0.14)) / 0.1, down = (l.t1 + 0.16 - t) / 0.1;
    best = Math.max(best, Math.min(1, up, down));
  }
  return Math.max(0, best);
}

// Gestures as body motion. hop = feet off the floor in metres, lean = sideways in metres (+ = toward the props), tilt = body angle, headTilt = head angle
// (radians, - = clockwise on screen, toward the props), nod = head down 0..1 (- = up), squash = stretch of the body height.
const GESTURES = {
  idle: () => ({}),
  wave: (g) => ({ tilt: Math.sin(g * 5) * 0.03, headTilt: Math.sin(g * 5 + 0.6) * 0.05 }),
  point: () => ({ lean: 0.025, tilt: -0.03, headTilt: -0.06 }),
  pointDown: () => ({ lean: 0.02, tilt: -0.03, nod: 0.7, headTilt: -0.04 }),
  present: (g) => ({ lean: 0.03 + Math.sin(g * 2.2) * 0.005, tilt: -0.025, headTilt: -0.07 }),
  open: (g) => ({ squash: 0.012, headTilt: Math.sin(g * 2) * 0.03 }),
  clap: (g, s) => { const c = Math.abs(Math.sin(g * (s && s.beat ? Math.PI / s.beat : 6.5))); return { hop: c * 0.012, nod: c * 0.5, squash: c * 0.01 }; },
  cheer: (g) => { const h = Math.abs(Math.sin(g * 8)); return { hop: h * 0.05, squash: h * 0.02, tilt: Math.sin(g * 4) * 0.03, headTilt: Math.sin(g * 4) * 0.05 }; },
  jump: (g) => { const h = Math.sin(((g % 0.9) / 0.9) * Math.PI); return { hop: h * 0.13, squash: h * 0.03, nod: -h * 0.4, spread: h }; },
  heart: () => ({ tilt: 0.03, lean: -0.01, headTilt: 0.1 }),
  lean: () => ({ lean: 0.03, tilt: -0.03, headTilt: -0.05 }),
  think: () => ({ tilt: 0.02, headTilt: 0.1, nod: -0.5 }),
};
export const GESTURE_NAMES = Object.keys(GESTURES);
const EASE = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };

/** The body and head pose at time t. s is the lesson's gesture state: { gesture, gt, gw, prev, turn, beat }, talk 0..1 how much she speaks. */
export function puppetMotion(s, t, talk = 0) {
  const g = (GESTURES[s.gesture] || GESTURES.idle)(s.gt || 0, s), w = s.gesture && s.gesture !== 'idle' ? EASE(s.gw ?? 1) : 0;
  const p = s.prev && GESTURES[s.prev.gesture] ? GESTURES[s.prev.gesture](s.prev.gt || 0, s.prev) : {}, pw = s.prev ? 1 - w : 0;
  const mix = (k) => (g[k] || 0) * w + (p[k] || 0) * pw;
  return {
    hop: Math.max(0, mix('hop')),
    spread: mix('spread'),
    lean: mix('lean') + Math.sin(t * 0.5) * 0.003 + (s.turn || 0) * 0.03,
    tilt: mix('tilt') + Math.sin(t * 0.9 + 3) * 0.006,
    squash: mix('squash') + Math.sin(t * 2.1 + 1) * 0.0025,
    headTilt: mix('headTilt') + Math.sin(t * 0.55 + 3) * 0.018 - (s.turn || 0) * 0.08,
    nod: mix('nod') + talk * (0.18 + Math.sin(t * 7.3) * 0.12) + Math.sin(t * 1.3 + 3) * 0.05,
  };
}

// ---- arms. One arm = { a, b, hand }: a = upper arm in degrees out from hanging (90 = straight out, 180 = straight up), b = elbow bend in degrees
// (+ = forearm folds in toward her body, - = forearm swings up and out). Her picture's own pose (hands on hips) is the rest.
const D = Math.PI / 180;

/** Elbow and wrist in picture pixels for an arm on `side` (-1 screen left, +1 screen right). uk, fk: upper arm and forearm drawn shorter or longer when pointing toward the viewer. */
export function armJoints(pivot, side, arm, upper, fore) {
  const a = arm.a * D, f = (arm.a - arm.b) * D, U = upper * (arm.uk ?? 1), F = fore * (arm.fk ?? 1), E = [pivot[0] + side * Math.sin(a) * U, pivot[1] + Math.cos(a) * U];
  return { E, W: [E[0] + side * Math.sin(f) * F, E[1] + Math.cos(f) * F] };
}

/**
 * Reach: the arm that puts the wrist on `target` (picture pixels). A straight two-bone solve works when the hand is away from her body. Close to her body
 * the only rigid solutions cross her chest or raise the elbow, so there the elbow stays low and the arm is drawn shortened, as if pointing toward the viewer.
 */
export function reachFor(pivot, side, target, upper, fore, hand = 'open') {
  const dx = side * (target[0] - pivot[0]), dy = target[1] - pivot[1], dist = Math.hypot(dx, dy), d = Math.min(upper + fore - 1, Math.max(Math.abs(upper - fore) + 1, dist));
  const wrap = (x) => Math.atan2(Math.sin(x), Math.cos(x));
  const toT = Math.atan2(dx, dy), inner = Math.acos((upper * upper + d * d - fore * fore) / (2 * upper * d));
  const cands = [wrap(toT + inner), wrap(toT - inner)].filter((x) => Math.sin(x) > 0.02), overhead = dy < -250;
  const ok = overhead ? cands.reduce((b, x) => (b === null || Math.sin(x) > Math.sin(b) ? x : b), null) : cands.filter((x) => Math.cos(x) > 0.2).reduce((b, x) => (b === null || Math.cos(x) > Math.cos(b) ? x : b), null);
  if (ok !== null && dist <= upper + fore) {
    const ex = Math.sin(ok) * upper, ey = Math.cos(ok) * upper, f = Math.atan2(dx - ex, dy - ey);
    return { a: ok / D, b: wrap(ok - f) / D, hand, uk: 1, fk: Math.hypot(dx - ex, dy - ey) / fore };
  }
  // elbow low and a little out, upper arm shortened; if the forearm would have to stretch too far, the elbow lifts toward the hand
  let ex = Math.sin(18 * D) * upper * 0.6, ey = Math.cos(18 * D) * upper * 0.6;
  const room = Math.hypot(dx - ex, dy - ey), most = fore * 1.12;
  if (room > most) { ex = dx + ((ex - dx) / room) * most; ey = dy + ((ey - dy) / room) * most; }
  const a = Math.atan2(ex, ey), f = Math.atan2(dx - ex, dy - ey);
  return { a: a / D, b: wrap(a - f) / D, hand, uk: Math.hypot(ex, ey) / upper, fk: Math.hypot(dx - ex, dy - ey) / fore };
}

function armPoses(rig) {
  const L = rig.left, R = rig.right, rest = { l: { a: L.rest, b: L.bend, hand: 'fist' }, r: { a: R.rest, b: R.bend, hand: 'fist' } };
  const reachL = (t, h) => reachFor(L.pivot, -1, t, rig.upper, rig.fore, h), reachR = (t, h) => reachFor(R.pivot, 1, t, rig.upper, rig.fore, h);
  return {
    rest,
    idle: () => ({}),
    wave: (g) => ({ r: { a: 118, b: -48 + Math.sin(g * 10) * 24, hand: 'open' } }),
    point: () => ({ r: { a: 80, b: 6, hand: 'point' } }),
    pointDown: () => ({ r: { a: 42, b: 12, hand: 'point' } }),
    present: (g) => ({ r: { a: 56 + Math.sin(g * 2.2) * 4, b: -30, hand: 'open' } }),
    open: (g) => { const b = Math.sin(g * 3) * 5; return { l: { a: 50 + b, b: -35, hand: 'open' }, r: { a: 50 + b, b: -35, hand: 'open' } }; },
    clap: (g, s) => { const c = Math.abs(Math.sin(g * (s && s.beat ? Math.PI / s.beat : 6.5))) * 62, mid = (L.pivot[0] + R.pivot[0]) / 2; return { l: reachL([mid - 26 - c, 1250], 'open'), r: reachR([mid + 26 + c, 1250], 'open') }; },
    cheer: (g) => { const b = Math.sin(g * 8) * 9; return { l: { a: 148 + b, b: 14, hand: 'open' }, r: { a: 148 + b, b: 14, hand: 'open' } }; },
    jump: (g) => { const h = Math.sin(((g % 0.9) / 0.9) * Math.PI); return { l: { a: 40 + h * 115, b: 18, hand: 'open' }, r: { a: 40 + h * 115, b: 18, hand: 'open' } }; },
    heart: () => { const mid = (L.pivot[0] + R.pivot[0]) / 2; return { l: reachL([mid - 34, 1215], 'open'), r: reachR([mid + 34, 1215], 'open') }; },
    lean: (g) => ({ r: { a: 58, b: -58 + Math.sin(g * 2.4) * 8, hand: 'open' } }),
    think: () => ({ r: reachR([720, 1010], 'fist') }),
  };
}

// While she speaks with no gesture of her own, one hand comes off the hip and moves with the sentence.
const LEN = (a = 1, b = 1, u = 1) => a + (b - a) * u;
const talkArm = (t) => ({ a: 50 + Math.sin(t * 1.7) * 7, b: -22 + Math.sin(t * 3.1) * 15, hand: 'open' });

/** Both arms at time t: { l, r }, each { a, b, hand }. speaking = 0..1 from speakingAmount. */
export function armPose(rig, s, t, speaking = 0) {
  const P = armPoses(rig), rest = P.rest;
  const pick = (name, g, st) => { const f = P[name]; return typeof f === 'function' ? f(g, st) : {}; };
  const cur = pick(s.gesture, s.gt || 0, s), prev = s.prev ? pick(s.prev.gesture, s.prev.gt || 0, s.prev) : null, w = s.gesture && s.gesture !== 'idle' ? EASE(s.gw ?? 1) : (s.prev ? EASE(s.gw ?? 1) : 1);
  const out = {};
  for (const side of ['l', 'r']) {
    let base = { ...rest[side] };
    if (side === 'r' && speaking > 0.001) { const T = talkArm(t), e = EASE(speaking); base = { a: base.a + (T.a - base.a) * e, b: base.b + (T.b - base.b) * e, hand: e > 0.5 ? T.hand : base.hand }; }
    const to = cur[side] || base, from = (prev && prev[side]) || base, u = prev ? w : (cur[side] ? w : 1);
    const fromUse = prev ? from : base;
    out[side] = { a: fromUse.a + (to.a - fromUse.a) * u, b: fromUse.b + (to.b - fromUse.b) * u, hand: u > 0.5 ? to.hand : fromUse.hand, uk: LEN(fromUse.uk, to.uk, u), fk: LEN(fromUse.fk, to.fk, u) };
    const sway = Math.sin(t * 1.6 + (side === 'l' ? 1.7 : 0)) * 1.1;   // never quite still
    out[side].a += sway;
  }
  return out;
}

// ---- signs: a hand sign for a key word, on the word. Targets are wrist positions in picture pixels, mirrored around her centre (x = 605).
// u runs 0..1 over the sign (for moves that travel), g is seconds since it began (for moves that repeat).
const CX = 605;
const mirror = (dx, y, hand, extra = {}) => [{ t: [CX - dx, y], hand, ...extra }, { t: [CX + dx, y], hand, ...extra }];
const lerp = (a, b, u) => a + (b - a) * u;
const SIGNS = {
  open: () => mirror(390, 1020, 'spread'),
  shut: () => mirror(390, 1030, 'fist'),
  clap: (u, g, beat) => { const c = Math.abs(Math.cos((g / beat) * Math.PI)) * 70; return mirror(24 + c, 1175, 'flat'); },
  lap: () => mirror(150, 1610, 'flat', { body: { nod: 0.5, lean: 0 } }),
  creep: (u, g) => { const w = Math.sin(g * 11) * 16, y = lerp(1330, 1060, u); return [{ t: [CX - 70, y + w], hand: 'walk' }, { t: [CX + 70, y - w], hand: 'walk' }]; },
  chin: () => mirror(70, 1010, 'point'),
  mouth: () => mirror(235, 915, 'spread', { body: { nod: -0.3, bigO: 1 } }),
  close: (u, g) => mirror(205 + Math.sin(g * 6) * 12, 950, 'flat', { body: { shake: Math.sin(g * 6) * 0.07 } }),
  mama: () => [null, { t: [CX + 56, 1010], hand: 'flat' }],
  dada: () => [null, { t: [CX + 62, 980], hand: 'point' }],
  fingers: (u, g) => mirror(235, 1090, 'wiggle', { phase: g }),
  toes: () => mirror(190, 1640, 'point', { body: { nod: 0.8 } }),
  belly: (u, g) => [null, { t: [CX + 25 + Math.cos(g * 6) * 55, 1330 + Math.sin(g * 6) * 45], hand: 'flat' }],
  knees: () => mirror(170, 1650, 'flat', { body: { nod: 0.8 } }),
  nose: () => [null, { t: [CX + 150, 905], hand: 'point' }],
  spider: (u, g) => { const up = Math.sin(g * 8) * 26, y = lerp(1200, 760, u); return [{ t: [CX - 38, y + up], hand: 'pinch' }, { t: [CX + 38, y - up], hand: 'pinch' }]; },
  rain: (u, g) => mirror(300, lerp(860, 1270, u), 'wiggle', { phase: g }),
  wash: (u) => [{ t: [lerp(CX - 180, CX + 140, u), 1290], hand: 'flat' }, { t: [lerp(CX + 180, CX + 500, u), lerp(1270, 1230, u)], hand: 'flat' }],
  sun: (u) => mirror(lerp(300, 480, u), lerp(1040, 720, u), 'spread'),
  wheels: (u, g) => { const c = Math.cos(g * 8) * 62, s = Math.sin(g * 8) * 34; return [{ t: [CX - 44 + c, 1205 + s], hand: 'fist' }, { t: [CX + 44 - c, 1205 - s], hand: 'fist' }]; },
  beep: (u, g) => [null, { t: [CX + 120 + Math.max(0, Math.sin(g * 9)) * 110, 1215], hand: 'spread' }],
  swish: (u, g) => { const x = Math.sin(g * 7.5) * 150; return [{ t: [CX - 170 + x, 1040], hand: 'spread' }, { t: [CX + 170 + x, 1040], hand: 'spread' }]; },
};
export const SIGN_NAMES = Object.keys(SIGNS);

/** Arm targets and body hints for one sign: { l, r, body }. A side with no target keeps its arm where it was. */
export function signPose(rig, name, u, g, beat = 0.5) {
  const f = SIGNS[name]; if (!f) return null;
  const [lt, rt] = f(Math.max(0, Math.min(1, u)), g, beat), reach = (S, sd, x) => (x ? { ...reachFor(S.pivot, sd, x.t, rig.upper, rig.fore, x.hand), phase: x.phase || 0 } : null);
  return { l: reach(rig.left, -1, lt), r: reach(rig.right, 1, rt), body: (lt && lt.body) || (rt && rt.body) || {} };
}

/**
 * The sign showing at time t. Between two signs close together the hands hold the first sign and travel straight to the next, never via the hips.
 * Returns { name, u, g, w, beat, from } or null; from = the sign it is coming from, w = how far along.
 */
export function signAt(signs, t) {
  const S = signs || []; let i = -1;
  for (let k = 0; k < S.length; k++) if (t >= S[k].t0 - 0.14) i = k;
  if (i < 0) return null;
  const cur = S[i], prev = S[i - 1], next = S[i + 1], near = (a, b) => a && b && b.t0 - a.t1 <= 1.4;
  const frozen = (x) => ({ name: x.sign, u: 1, g: x.t1 - x.t0, beat: x.beat || 0.5 });
  const info = (x, w, from) => ({ name: x.sign, u: (t - x.t0) / Math.max(0.05, x.t1 - x.t0), g: Math.max(0, t - x.t0), w, beat: x.beat || 0.5, from });
  if (t < cur.t1) return info(cur, EASE((t - (cur.t0 - 0.14)) / 0.14), near(prev, cur) ? frozen(prev) : null);
  if (near(cur, next)) return { ...frozen(cur), w: 1, from: null };             // hold until the next sign takes over
  const out = 1 - EASE((t - cur.t1) / 0.35);
  return out > 0 ? { ...frozen(cur), w: out, from: null } : null;
}

const jointsOf = (rig, key, arm) => { const S = key === 'l' ? rig.left : rig.right, J = armJoints(S.pivot, key === 'l' ? -1 : 1, arm, rig.upper, rig.fore); return { E: J.E, W: J.W, hand: arm.hand, phase: arm.phase || 0 }; };
const mixJ = (a, b, w) => ({ E: [a.E[0] + (b.E[0] - a.E[0]) * w, a.E[1] + (b.E[1] - a.E[1]) * w], W: [a.W[0] + (b.W[0] - a.W[0]) * w, a.W[1] + (b.W[1] - a.W[1]) * w], hand: w > 0.5 ? b.hand : a.hand, phase: w > 0.5 ? b.phase : a.phase });

/**
 * The elbow and wrist of each arm in picture pixels: the arms' pose with a sign blended over it. Blending the joints themselves, not the angles,
 * sends the hand on a straight path with the elbow following, so an arm never flips or swings through her body. Returns { l: { E, W, hand, phase }, r, body }.
 */
export function withSign(rig, base, active) {
  const baseJ = { l: jointsOf(rig, 'l', base.l), r: jointsOf(rig, 'r', base.r) };
  if (!active) return { ...baseJ, body: {} };
  const sp = signPose(rig, active.name, active.u, active.g, active.beat);
  if (!sp) return { ...baseJ, body: {} };
  const fr = active.from ? signPose(rig, active.from.name, active.from.u, active.from.g, active.from.beat) : null, w = active.w, out = { body: Object.fromEntries(Object.entries(sp.body).map(([k, v]) => [k, v * w])) };
  for (const key of ['l', 'r']) {
    const start = fr && fr[key] ? jointsOf(rig, key, fr[key]) : baseJ[key];
    out[key] = sp[key] ? mixJ(start, jointsOf(rig, key, sp[key]), w) : (fr && fr[key] ? mixJ(start, baseJ[key], w) : baseJ[key]);
  }
  return out;
}

/** The sleeve for an arm: it always starts at the shoulder and reaches toward the elbow, so it cannot come away from her body. */
export function sleeveShape(pivot, E, sl) {
  const dx = E[0] - pivot[0], dy = E[1] - pivot[1], len = Math.max(1, Math.hypot(dx, dy)), d = [dx / len, dy / len], n = [-d[1], d[0]], L = Math.min(sl.length, len * 0.74);
  const H = [pivot[0] + d[0] * L, pivot[1] + d[1] * L];
  return { d, n, L, H, cap: sl.capRadius, half: sl.halfWidth };
}

// ---- performance: what her head, brows and hair do with the words, the way a children's presenter sings to a child. Pure functions of time.
const SMALL = new Set(['a', 'an', 'the', 'to', 'of', 'in', 'on', 'at', 'and', 'it', 'is', 'we', 'you', 'your', 'them', 'my', 'me', 'for', 'be', 'so']);
const bare = (w) => String(w).toLowerCase().replace(/[^a-z']/g, '');
const unit = (k) => { const x = Math.sin((k + 1) * 12.9898) * 43758.5453; return x - Math.floor(x); };
export const TILT_MAX = 0.19;
const PULSE = 2 * Math.PI * 1.6;                                      // a pulse of about 96 per minute, the feel of the reference's songs

// The stressed words of all lines, once per lesson: [{ t, sign, size, line }].
function accentsOf(lines) {
  if (lines.__acc) return lines.__acc;
  const out = []; let k = 0;
  lines.forEach((l, li) => { for (const w of l.words || []) { const b = bare(w.text); if (b.length >= 2 && !SMALL.has(b)) { out.push({ t: w.t0, sign: k % 2 ? 1 : -1, size: 0.06 + 0.07 * unit(k), line: li }); k++; } } });
  Object.defineProperty(lines, '__acc', { value: out, enumerable: false });
  return out;
}
const pulse = (dt, tau) => (dt < 0 ? 0 : Math.exp(-dt / tau));

/** { tilt, nod, brow, leanIn, wink:{eye,w}|null, sway } at time t. Emotion 'surprised' lifts the brows. */
export function performance(lines, t, emotion) {
  const L = lines || [], acc = accentsOf(L);
  let i = -1; for (let k = 0; k < acc.length; k++) { if (acc[k].t - 0.08 <= t) i = k; else break; }
  const speaking = speakingAmount(L, t);
  // The head leans one way per stressed word, easing over 0.22 s; between lines it sways gently to the music instead.
  // Each lean starts from wherever the last one had reached, so fast words never make the head jump.
  let worded = 0;
  for (let k = Math.max(0, i - 4); k <= i; k++) { const end = k < i ? acc[k + 1].t - 0.08 : t, v = EASE((end - (acc[k].t - 0.08)) / 0.3); worded += (acc[k].sign * acc[k].size - worded) * v; }
  const swayed = Math.sin(t * 3.2) * 0.045;
  // the head settles slowly from word-leaning into swaying, so a line's end has no sudden move
  let settled = 0; for (const l of L) settled = Math.max(settled, Math.min(1, (t - (l.t0 - 0.5)) / 0.45, (l.t1 + 0.85 - t) / 0.7)); settled = EASE(settled);
  const tilt = worded * settled + swayed * (1 - settled);
  const dt = i >= 0 ? t - acc[i].t : 9;
  const nod = speaking * pulse(dt + 0.04, 0.17) * 0.85 + (1 - speaking) * Math.max(0, Math.sin(t * 6.4)) * 0.22;
  let brow = speaking * pulse(dt, 0.32) * 0.55 + (emotion === 'surprised' ? 0.65 : 0) * speaking, leanIn = 0, wink = null;
  L.forEach((l, li) => {
    const words = l.words || [], last = words.length ? String(words[words.length - 1].text) : '', asks = /\?\s*$/.test(last) || l.type === 'repeat';
    if (asks && t > l.t0 - 0.4 && t < l.t1 + 0.5) { leanIn = Math.max(leanIn, Math.min(EASE((t - (l.t0 - 0.4)) / 0.35), 1 - EASE((t - (l.t1 + 0.15)) / 0.35))); brow = Math.max(brow, 0.5 * speaking); }
    if (li % 3 === 2) { const w = (t - (l.t1 + 0.04)) / 0.34; if (w > 0 && w < 1) wink = { eye: 1, w: Math.sin(w * Math.PI) }; }   // now and then, a wink at the end of a line
  });
  // a steady pulse under everything, so she never freezes in a held pose or a pause
  const beat = Math.sin(t * PULSE), under = Math.sin(t * PULSE * 0.5 + 0.7);
  return { tilt: tilt + under * 0.022, nod: nod + Math.max(0, beat) * 0.16, brow: Math.min(1, brow), leanIn, wink, pulse: beat, under };
}

/** The ponytail's swing in radians: it trails her head by a moment and keeps a little life of its own. */
export function ponySwing(lines, t, hop = 0) {
  const now = performance(lines, t).tilt, then = performance(lines, t - 0.2).tilt;
  const v = Math.max(-0.4, Math.min(0.4, (then - now) * 3 + then * 0.8));
  return v + Math.sin(t * 2.3) * 0.03 + hop * 1.2;
}
