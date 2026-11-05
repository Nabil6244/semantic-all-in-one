// Toon character: round body, big head and eyes, mitten hands, stubby legs, toon shading with an ink outline.
// Built from primitives only (no model files). poseToon(rig, t, state) is a pure function of time and state, so any
// frame renders alone. state = { open (0..1 mouth from voice), gesture, gt (seconds into gesture), gw (0..1 blend), emotion, look }.
import * as THREE from '/three/three.module.min.js';

let GRADIENT = null;
function gradient() {
  if (GRADIENT) return GRADIENT;
  const d = new Uint8Array([140, 205, 255]);
  GRADIENT = new THREE.DataTexture(d, 3, 1, THREE.RedFormat);
  GRADIENT.minFilter = GRADIENT.magFilter = THREE.NearestFilter; GRADIENT.needsUpdate = true;
  return GRADIENT;
}
const MATS = new Map();
export function toonMat(color) {
  const k = String(color); if (MATS.has(k)) return MATS.get(k);
  const m = new THREE.MeshToonMaterial({ color: new THREE.Color(color), gradientMap: gradient() });
  MATS.set(k, m); return m;
}
const INK = new THREE.MeshBasicMaterial({ color: 0x2a1e2e, side: THREE.BackSide });
const SPH = new THREE.SphereGeometry(1, 32, 22);
const CAP = new THREE.CapsuleGeometry(1, 1, 8, 16);

// A mesh plus an inverted-hull outline (a slightly larger back-face copy in ink).
export function part(geo, color, { outline = 0.06, shadow = true } = {}) {
  const m = new THREE.Mesh(geo, typeof color === 'object' ? color : toonMat(color));
  m.castShadow = shadow; m.receiveShadow = false;
  if (outline) { const o = new THREE.Mesh(geo, INK); o.scale.setScalar(1 + outline); m.add(o); }
  return m;
}
function ball(color, sx, sy, sz, opts) { const m = part(SPH, color, opts); m.scale.set(sx, sy ?? sx, sz ?? sx); return m; }
function capsule(color, r, len, opts) { const m = part(CAP, color, opts); m.scale.set(r, len / 3, r); return m; }

export const PALETTES = {
  sunny: { body: '#ffb84d', belly: '#fff1c9', head: '#ffd08a', cheek: '#ff8fa3', limb: '#ffb84d', shoe: '#5b6cff', eye: '#3b2a1e' },
  mint: { body: '#5fd6b0', belly: '#e8fff6', head: '#ffd9bd', cheek: '#ff9cab', limb: '#ffd9bd', shoe: '#ff6b6b', eye: '#2b2a40' },
  berry: { body: '#b48cff', belly: '#f3ecff', head: '#ffd2c2', cheek: '#ff8fb0', limb: '#ffd2c2', shoe: '#ffb000', eye: '#2a2240' },
};

export function buildToon(look = {}) {
  const P = { ...PALETTES[look.palette || 'sunny'], ...(look.colors || {}) };
  const rig = new THREE.Group(), j = {};
  rig.add(j.hips = new THREE.Group());
  // Body: one soft egg, belly patch in front.
  j.body = new THREE.Group(); j.body.position.y = 0.42; j.hips.add(j.body);
  const torso = ball(P.body, 0.34, 0.36, 0.3); torso.position.y = 0.18; j.body.add(torso);
  const belly = ball(P.belly, 0.24, 0.26, 0.1, { outline: 0 }); belly.position.set(0, 0.13, 0.23); j.body.add(belly);
  // Head: big round head, sits on the body.
  j.head = new THREE.Group(); j.head.position.y = 0.52; j.body.add(j.head);
  const skull = ball(P.head, 0.42, 0.4, 0.4); skull.position.y = 0.36; j.head.add(skull);
  j.face = new THREE.Group(); j.face.position.set(0, 0.36, 0); j.head.add(j.face);
  // Hair tuft so the silhouette reads.
  const tuft = ball(P.body, 0.12, 0.16, 0.12); tuft.position.set(0.02, 0.4, 0.05); tuft.rotation.z = -0.3; j.face.add(tuft);
  // Eyes: white, pupil, highlight. The eye group's y-scale is the blink.
  j.eyes = [];
  for (const sx of [-1, 1]) {
    const e = new THREE.Group(); e.position.set(sx * 0.145, 0.05, 0.33); e.rotation.y = sx * 0.28; j.face.add(e);
    e.add(ball('#ffffff', 0.1, 0.13, 0.06, { outline: 0.12, shadow: false }));
    const pupil = ball(P.eye, 0.065, 0.085, 0.04, { outline: 0, shadow: false }); pupil.position.z = 0.035; e.add(pupil);
    const hi = ball('#ffffff', 0.022, 0.022, 0.01, { outline: 0, shadow: false }); hi.position.set(0.022, 0.035, 0.07); e.add(hi);
    e.userData.pupil = pupil; j.eyes.push(e);
  }
  // Brows: angle shows the emotion.
  j.brows = [];
  for (const sx of [-1, 1]) {
    const b = ball('#4a3226', 0.07, 0.018, 0.02, { outline: 0, shadow: false }); b.position.set(sx * 0.15, 0.22, 0.36); j.face.add(b); j.brows.push(b);
  }
  // Cheeks.
  for (const sx of [-1, 1]) { const c = ball(P.cheek, 0.06, 0.035, 0.02, { outline: 0, shadow: false }); c.position.set(sx * 0.25, -0.07, 0.31); c.rotation.y = sx * 0.6; j.face.add(c); }
  // Mouth: dark opening that grows with the voice, tongue inside, upper lip line on top.
  j.mouth = new THREE.Group(); j.mouth.position.set(0, -0.13, 0.36); j.mouth.rotation.x = -0.25; j.face.add(j.mouth);
  j.mouthHole = ball('#5a1424', 0.09, 0.03, 0.03, { outline: 0.1, shadow: false }); j.mouth.add(j.mouthHole);
  j.tongue = ball('#ff7a8a', 0.05, 0.025, 0.02, { outline: 0, shadow: false }); j.tongue.position.set(0, -0.012, 0.015); j.mouth.add(j.tongue);
  // Arms: shoulder -> elbow -> mitten. Arms hang along -y; +z rotation swings an arm toward +x.
  j.arms = {};
  for (const [side, sx] of [['L', -1], ['R', 1]]) {
    const sh = new THREE.Group(); sh.position.set(sx * 0.29, 0.36, 0); j.body.add(sh);
    const up = capsule(P.limb, 0.07, 0.24); up.position.y = -0.13; sh.add(up);
    const el = new THREE.Group(); el.position.y = -0.27; sh.add(el);
    const fo = capsule(P.limb, 0.065, 0.22); fo.position.y = -0.12; el.add(fo);
    const hand = ball('#ffffff', 0.09, 0.09, 0.09); hand.position.y = -0.27; el.add(hand);
    j.arms[side] = { sh, el, hand, sx };
  }
  // Legs and shoes.
  j.legs = {};
  for (const [side, sx] of [['L', -1], ['R', 1]]) {
    const hip = new THREE.Group(); hip.position.set(sx * 0.14, 0.38, 0); j.hips.add(hip);
    const leg = capsule(P.limb, 0.08, 0.16); leg.position.y = -0.14; hip.add(leg);
    const shoe = ball(P.shoe, 0.11, 0.07, 0.15); shoe.position.set(0, -0.33, 0.04); hip.add(shoe);
    j.legs[side] = { hip, sx };
  }
  rig.userData.j = j;
  return rig;
}

const ease = (x) => x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x);
const hash = (n) => { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); };

// Blink: about every 2.4-4.4 s, 0.16 s long, seeded per character so two characters do not blink together.
export function blinkAt(t, seed = 0) {
  let k = 0, start = 0.8 + hash(seed) * 1.5;
  while (start < t) { const end = start + 0.16; if (t < end) { const u = (t - start) / 0.16; return u < 0.5 ? u * 2 : (1 - u) * 2; } k++; start = end + 2.4 + hash(seed + k * 7.3) * 2; }
  return 0;
}

const GESTURES = {
  // Each returns joint angles for weight 1. a = arm targets {R:{shZ, shX, elZ, elX}, L:{...}}, body = {y, sq, tilt}.
  idle: () => ({}),
  wave: (g) => ({ R: { shZ: 1.1, shX: -0.2, elZ: 1.85 + Math.sin(g * 10) * 0.3 }, body: { tilt: -0.07 } }),
  point: (g) => ({ R: { shZ: 2.35, shX: -0.3, elZ: 0.3 }, L: { shZ: -0.15 }, body: { tilt: -0.05 }, look: [0.45, 0.8] }),
  clap: (g) => { const c = Math.abs(Math.sin(g * 6.5)); return { R: { shX: -1.3, shZ: -0.12 - c * 0.14, elZ: -0.38 }, L: { shX: -1.3, shZ: 0.12 + c * 0.14, elZ: 0.38 }, body: { y: Math.max(0, Math.sin(g * 13)) * 0.015 } }; },
  jump: (g) => { const p = (g % 0.9) / 0.9, h = Math.sin(p * Math.PI); return { R: { shZ: 2.6 * h + 0.3 }, L: { shZ: -2.6 * h - 0.3 }, body: { y: h * 0.32, sq: p < 0.12 || p > 0.88 ? -0.12 : h * 0.08 } }; },
  open: (g) => { const b = Math.sin(g * 3) * 0.06; return { R: { shZ: 0.45 + b, shX: -0.55, elZ: 0.25, elX: -0.9 }, L: { shZ: -0.45 - b, shX: -0.55, elZ: -0.25, elX: -0.9 }, body: { tilt: 0 }, look: [0, -0.05] }; },
  cheer: (g) => { const b = Math.sin(g * 8) * 0.12; return { R: { shZ: 2.7 + b, elZ: 0.2 }, L: { shZ: -2.7 - b, elZ: -0.2 }, body: { y: Math.max(0, Math.sin(g * 8)) * 0.05 } }; },
  pointDown: () => ({ R: { shZ: 0.75, shX: -0.45, elZ: -0.05 }, body: { tilt: 0.04 }, look: [0.3, -0.45] }),
  present: (g) => ({ R: { shZ: 1.05, shX: -0.55, elZ: 0.3 + Math.sin(g * 2.2) * 0.06, elX: -0.2 }, body: { tilt: -0.04 }, look: [0.35, 0.05] }),
  heart: () => ({ R: { shX: -0.3, shZ: -0.08, elZ: -0.6, elX: -1.85 }, L: { shX: -0.3, shZ: 0.08, elZ: 0.6, elX: -1.85 }, body: { tilt: 0, lean: 0.06 }, tilt: 0.2 }),
  lean: () => ({ body: { lean: 0.12 }, tilt: -0.08 }),
  think: () => ({ R: { shX: -0.6, shZ: -0.5, elZ: -1.9 }, body: { tilt: 0.1 }, look: [-0.3, 0.4] }),
};
export const GESTURE_NAMES = Object.keys(GESTURES);

const BROWS = { laugh: [-0.12, 0.27], happy: [-0.04, 0.25], neutral: [0, 0.23], sad: [-0.35, 0.22], surprised: [-0.12, 0.3], angry: [0.45, 0.2] };

// Per-rig sizes so one pose function drives any body. The round toon uses these defaults; the tutor passes its own.
export const TOON_CFG = { k: 1, browY: 0.23, mouth: [0.085, 0.025, 0.022, 0.085, 0.03, 0.02, 0.03], tongue: [0.03, 0.06], hop: 1, squash: 1, armRest: 0.3, elRest: 0.15, nod: 0.12 };

export function poseToon(rig, t, s = {}) {
  const j = rig.userData.j, C = j.cfg || TOON_CFG, seed = rig.userData.seed || 0, open = Math.max(0, Math.min(1, s.open || 0));
  const g = GESTURES[s.gesture] ? GESTURES[s.gesture](s.gt || 0) : {}, w = s.gesture && s.gesture !== 'idle' ? ease(s.gw ?? 1) : 0;
  const prev = s.prev && GESTURES[s.prev.gesture] ? GESTURES[s.prev.gesture](s.prev.gt || 0) : {}, pw = s.prev ? 1 - w : 0;
  const val = (G, side, key, rest) => (G[side] && G[side][key] !== undefined ? G[side][key] : rest);
  const pick = (side, key, rest) => rest + (val(g, side, key, rest) - rest) * w + (val(prev, side, key, rest) - rest) * pw;
  // Breathing + talking bounce + squash and stretch.
  const breath = Math.sin(t * 2.1 + seed) * 0.012, talk = open * 0.02;
  const by = ((g.body && g.body.y) || 0) * w + ((prev.body && prev.body.y) || 0) * pw;
  const sq = ((g.body && g.body.sq) || 0) * w + ((prev.body && prev.body.sq) || 0) * pw;
  j.hips.position.y = by * C.hop;
  const Q = C.squash;
  j.body.scale.set(1 - (sq * 0.5 + breath * 0.5) * Q, 1 + (sq + breath + talk * 0.5) * Q, 1 - sq * 0.5 * Q);
  j.body.rotation.z = Math.sin(t * 0.9 + seed) * 0.025 + (((g.body && g.body.tilt) || 0) * w);
  j.body.rotation.x = ((g.body && g.body.lean) || 0) * w + ((prev.body && prev.body.lean) || 0) * pw;
  // Head: nods with speech, sways when idle, looks where the gesture looks.
  const look = g.look ? [g.look[0] * w, g.look[1] * w] : [0, 0];
  j.head.rotation.x = -open * C.nod + Math.sin(t * 1.3 + seed) * 0.03 - look[1] * 0.35;
  j.head.rotation.y = Math.sin(t * 0.7 + seed * 2) * 0.12 + look[0] * 0.6 + (s.turn || 0);
  const laugh = s.emotion === 'laugh' ? 1 : 0;
  j.head.rotation.z = Math.sin(t * 0.55 + seed) * 0.05 + (g.tilt || 0) * w + (prev.tilt || 0) * pw;
  j.head.rotation.x -= laugh * open * 0.12;
  // Eyes: blink, pupils follow the look.
  const bl = blinkAt(t, seed), surprised = s.emotion === 'surprised' ? 1.15 : 1, squint = laugh ? 0.78 : s.emotion === 'happy' ? 1 - open * 0.12 : 1;
  for (const e of j.eyes) { e.scale.y = Math.max(0.08, (1 - bl) * surprised * squint); e.userData.pupil.position.x = look[0] * 0.03 * C.k; e.userData.pupil.position.y = look[1] * 0.035 * C.k; }
  const br = BROWS[s.emotion] || BROWS.happy;
  j.brows.forEach((b, i) => { const sx = i ? 1 : -1; b.rotation.z = sx * br[0]; b.position.y = C.browY + (br[1] - 0.23 + open * 0.015) * C.k; });
  // Mouth.
  const smile = s.emotion === 'sad' ? 0.6 : 1;
  const M = C.mouth;
  const grin = laugh ? 1.3 : s.emotion === 'happy' || s.emotion === 'surprised' ? 1.12 : 1;
  j.mouthHole.scale.set((M[0] + open * M[1]) * grin, M[2] + open * M[3], M[4] + open * M[5]);
  j.mouthHole.position.y = -open * M[6];
  j.tongue.visible = open > 0.25; j.tongue.position.y = -C.tongue[0] - open * C.tongue[1];
  if (j.smile) { j.smile.visible = open < 0.18; j.mouthHole.visible = open > 0.06; }
  if (j.teeth) { j.teeth.visible = open > 0.2; j.teeth.position.y = M[2] * 0.6 + open * M[3] * 0.2 - open * M[6]; } j.mouth.rotation.z = 0; j.mouth.scale.x = smile;
  // Arms: rest pose hangs slightly out; gestures add on top, with a little idle swing.
  for (const side of ['L', 'R']) {
    const a = j.arms[side], sx = a.sx, idle = Math.sin(t * 1.6 + (sx > 0 ? 0 : 1.7) + seed) * 0.05;
    a.sh.rotation.z = pick(side, 'shZ', sx * C.armRest) + sx * idle;
    a.sh.rotation.x = pick(side, 'shX', 0);
    a.el.rotation.z = pick(side, 'elZ', sx * C.elRest);
    a.el.rotation.x = pick(side, 'elX', -0.1);
  }
  for (const side of ['L', 'R']) { const l = j.legs[side]; l.hip.rotation.x = 0; l.hip.rotation.z = l.sx * 0.04; }
}
