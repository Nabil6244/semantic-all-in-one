// The approved 3D preschool host (GLB from authoring/, accepted at host Gate 5) driven by the lesson plan:
// visemes from plan.visemeTrack, blink with its arc corrective, emotions as face keys, simple bone gestures that
// follow the same gesture names as the toon tutor. loadHost3D(url) -> Group; poseHost3D(host, t, state, plan).
import * as THREE from '/three/three.module.min.js';
import { GLTFLoader } from '/three/addons/loaders/GLTFLoader.js';
import { blinkAt } from './toon.js';

const AX = { x: new THREE.Vector3(1, 0, 0), y: new THREE.Vector3(0, 1, 0), f: new THREE.Vector3(0, 0, 1) };   // f: front-back axis (arms swing out/in about it)
const D = Math.PI / 180;
const ARM_REST = 0.74;                                  // the rig's A-pose: upper arms ~42 degrees out from hanging

export async function loadHost3D(url) {
  const g = await new GLTFLoader().loadAsync(url), root = new THREE.Group(); root.add(g.scene);
  const meshes = [], bones = {};
  g.scene.traverse((o) => {
    if (o.isMesh) { o.castShadow = o.name !== 'cand_mouth'; o.receiveShadow = true; o.frustumCulled = false; if (o.morphTargetDictionary) meshes.push(o); }
    if (o.isBone) bones[o.name] = { b: o, q: o.quaternion.clone(), p: o.position.clone() };
  });
  root.userData = { host3d: true, meshes, bones, seed: 3 };
  return root;
}

// Rotate a bone about a world axis through its own head, on top of what is already applied.
function turn(H, name, axis, rad) {
  const v = H.bones[THREE.PropertyBinding.sanitizeNodeName(name)]; if (!v || !rad) return;   // Three drops the dots: upperarm01.R -> upperarm01R
  const pq = new THREE.Quaternion(); v.b.parent.getWorldQuaternion(pq);
  const R = new THREE.Quaternion().setFromAxisAngle(axis, rad);
  v.b.quaternion.copy(pq.clone().invert().multiply(R).multiply(pq).multiply(v.b.quaternion)); v.b.updateMatrixWorld(true);
}

// Same gesture vocabulary as toon.js (point/present use her left arm: the props stand on her left, screen right): arm targets per side in radians (shZ out from hanging, shX forward raise, elZ elbow bend, elX elbow forward).
const GESTURES = {
  idle: () => ({}),
  wave: (g) => ({ R: { shZ: 1.25, shX: -0.15, elZ: 1.7 + Math.sin(g * 10) * 0.3 }, tilt: -0.05 }),
  point: () => ({ L: { shZ: 1.45, shX: -0.6, elZ: 0.15 }, look: [0.45, 0.2], tilt: -0.04 }),
  pointDown: () => ({ L: { shZ: 0.65, shX: -0.55, elZ: 0.1 }, look: [0.3, -0.35] }),
  present: (g) => ({ L: { shZ: 0.95, shX: -0.6, elZ: 0.35 + Math.sin(g * 2.2) * 0.06, elX: -0.25 }, look: [0.35, 0.05], tilt: -0.03 }),
  open: (g) => { const b = Math.sin(g * 3) * 0.05; return { R: { shZ: 0.55 + b, shX: -0.5, elZ: 0.25, elX: -0.7 }, L: { shZ: 0.55 + b, shX: -0.5, elZ: 0.25, elX: -0.7 } }; },
  // clap: on a chant the hands meet on every beat
  clap: (g, s) => { const c = Math.abs(Math.sin(g * (s && s.beat ? Math.PI / s.beat : 6.5))); return { R: { shX: -0.5, shZ: 0.08 + c * 0.2, elZ: -1.02 + c * 0.6, elX: -1.0 }, L: { shX: -0.5, shZ: 0.08 + c * 0.2, elZ: -1.02 + c * 0.6, elX: -1.0 }, hop: Math.max(0, Math.sin(g * 13)) * 0.006 }; },
  cheer: (g) => { const b = Math.sin(g * 8) * 0.1; return { R: { shZ: 2.6 + b, elZ: 0.2 }, L: { shZ: 2.6 + b, elZ: 0.2 }, hop: Math.max(0, Math.sin(g * 8)) * 0.02 }; },
  jump: (g) => { const p = (g % 0.9) / 0.9, h = Math.sin(p * Math.PI); return { R: { shZ: 0.3 + 2.2 * h }, L: { shZ: 0.3 + 2.2 * h }, hop: h * 0.12 }; },
  heart: () => ({ R: { shX: -0.9, shZ: 0.1, elZ: -0.9, elX: -1.2 }, L: { shX: -0.9, shZ: 0.1, elZ: -0.9, elX: -1.2 }, lean: 0.05, headTilt: 0.15 }),
  lean: () => ({ lean: 0.1, headTilt: -0.06 }),
  think: () => ({ R: { shX: -0.75, shZ: 0.2, elZ: -1.9, elX: -0.6 }, look: [-0.3, 0.35], headTilt: 0.12 }),
};
const REST = { shZ: 0.16, shX: 0, elZ: 0.12, elX: -0.12 };
const EMO = {                                          // face keys per emotion (applied under the visemes)
  happy: { smile: 0.3 }, laugh: { laugh: 0.55, smile: 0.2 }, surprised: { surprise: 0.55 }, neutral: { smile: 0.08 },
  sad: { browInnerUp: 0.55, browDownLeft: 0, smile: 0 }, curious: { curious: 0.7 },
};
const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };

function visemesAt(plan, t) {
  const V = plan.visemeTrack; if (!V) return {};
  const k = t * V.fps, i = Math.floor(k), f = k - i, a = V.frames[Math.max(0, Math.min(V.frames.length - 1, i))], b = V.frames[Math.max(0, Math.min(V.frames.length - 1, i + 1))], out = {};
  V.names.forEach((n, j) => { const x = (a[j] * (1 - f) + b[j] * f) / 100; if (x > 0.002) out['viseme_' + n] = x; });
  return out;
}

export function poseHost3D(host, t, s, plan) {
  const H = host.userData;
  for (const v of Object.values(H.bones)) { v.b.quaternion.copy(v.q); v.b.position.copy(v.p); }
  host.updateMatrixWorld(true);
  const g = GESTURES[s.gesture] ? GESTURES[s.gesture](s.gt || 0, s) : {}, w = s.gesture && s.gesture !== 'idle' ? ease(s.gw ?? 1) : 0;
  const prev = s.prev && GESTURES[s.prev.gesture] ? GESTURES[s.prev.gesture](s.prev.gt || 0, s.prev) : {}, pw = s.prev ? 1 - w : 0;
  const mix = (key, rest = 0) => rest + ((g[key] ?? rest) - rest) * w + ((prev[key] ?? rest) - rest) * pw;
  const arm = (side, key) => REST[key] + (((g[side] || {})[key] ?? REST[key]) - REST[key]) * w + (((prev[side] || {})[key] ?? REST[key]) - REST[key]) * pw;
  const vis = visemesAt(plan, t), talk = Math.min(1, Object.values(vis).reduce((a, b) => a + b, 0));
  // Body: breathing, a small sway, gesture lean/tilt and hops.
  const root = H.bones.root; if (root) root.b.position.y += mix('hop') * 1;
  turn(H, 'spine03', AX.f, Math.sin(t * 0.9 + H.seed) * 0.012 + mix('tilt'));
  turn(H, 'spine02', AX.x, Math.sin(t * 2.1 + H.seed) * 0.008 + mix('lean'));
  // Arms: from the rig's A-pose down to a relaxed hang, then the gesture. Her right arm sits at -x.
  for (const [side, sx] of [['R', -1], ['L', 1]]) {          // sign checked on renders
    const idle = Math.sin(t * 1.6 + (sx > 0 ? 0 : 1.7) + H.seed) * 0.03;
    turn(H, `upperarm01.${side}`, AX.f, sx * (arm(side, 'shZ') + idle - ARM_REST));
    turn(H, `upperarm01.${side}`, AX.x, arm(side, 'shX'));
    turn(H, `lowerarm01.${side}`, AX.f, sx * arm(side, 'elZ'));
    turn(H, `lowerarm01.${side}`, AX.x, arm(side, 'elX'));
  }
  // Head: speech nods, idle sway, the gesture's look, and the plan's turn toward the props (tutor stands left of them).
  const look = g.look ? [g.look[0] * w, g.look[1] * w] : [0, 0];
  const yaw = Math.sin(t * 0.7 + H.seed * 2) * 0.06 + look[0] * 0.45 + (s.turn || 0);
  const pitch = talk * 0.04 + Math.sin(t * 1.3 + H.seed) * 0.02 - look[1] * 0.25;
  const roll = Math.sin(t * 0.55 + H.seed) * 0.03 + mix('headTilt');
  for (const [n, k] of [['neck02', 0.25], ['neck03', 0.25], ['head', 0.5]]) { turn(H, n, AX.y, yaw * k); turn(H, n, AX.x, pitch * k); turn(H, n, AX.f, -roll * k); }
  for (const e of ['eye.L', 'eye.R']) { turn(H, e, AX.y, look[0] * 0.25); turn(H, e, AX.x, -look[1] * 0.15); }
  // Face: emotion under the speech, visemes, blink with its arc corrective (renderer rule from Gate 2).
  const emo = EMO[s.emotion] || EMO.happy, keys = {};
  for (const [n, x] of Object.entries(emo)) keys[n] = n === 'smile' ? x * (1 - 0.45 * talk) : n === 'surprise' || n === 'laugh' ? x * (1 - 0.6 * talk) : x;
  Object.assign(keys, vis);
  const bw = blinkAt(t, H.seed); Object.assign(keys, { eyeBlinkLeft: bw, eyeBlinkRight: bw, eyeBlinkArcLeft: 4 * bw * (1 - bw), eyeBlinkArcRight: 4 * bw * (1 - bw) });
  for (const m of H.meshes) { const d = m.morphTargetDictionary; m.morphTargetInfluences.fill(0); for (const n in keys) if (n in d) m.morphTargetInfluences[d[n]] = keys[n]; }
  host.updateMatrixWorld(true);
}
