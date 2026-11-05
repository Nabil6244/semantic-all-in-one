// Human cartoon tutor: an original friendly teacher (brown bob with fringe, flower clip, mustard sweater, teal trousers,
// red sneakers). Same joint names as the round toon, so poseToon() drives it; j.cfg holds this body's sizes.
import * as THREE from '/three/three.module.min.js';
import { part, toonMat } from './toon.js';

const SPH = new THREE.SphereGeometry(1, 32, 22), CAP = new THREE.CapsuleGeometry(1, 1, 8, 16);
const ball = (c, sx, sy, sz, o) => { const m = part(SPH, c, o); m.scale.set(sx, sy ?? sx, sz ?? sx); return m; };
const capsule = (c, r, len, o) => { const m = part(CAP, c, o); m.scale.set(r, len / 3, r); return m; };
const NO = { outline: 0, shadow: false };

export const TUTOR_LOOKS = {
  maya: { skin: '#ffd2b3', hair: '#6b3e26', top: '#f4b63f', collar: '#ffffff', pants: '#2a9d8f', shoe: '#ef5350', iris: '#6b4423', clip: '#ff7eb6', cheek: '#ff8f9a', lips: '#c9505f' },
  sam: { skin: '#c98d62', hair: '#2b1d16', top: '#4dabf7', collar: '#ffffff', pants: '#3d405b', shoe: '#ffb703', iris: '#3b2416', clip: '#ffd43b', cheek: '#e9787f', lips: '#a8434f' },
};

export function buildTutor(look = {}) {
  const P = { ...TUTOR_LOOKS[look.name || 'maya'], ...(look.colors || {}) };
  const rig = new THREE.Group(), j = {};
  j.cfg = { k: 0.42, browY: 0.098, mouth: [0.04, 0.012, 0.01, 0.04, 0.018, 0.01, 0.012], tongue: [0.012, 0.022], hop: 0.45, squash: 0.35, armRest: 0.14, elRest: 0.12, nod: 0.08 };
  rig.add(j.hips = new THREE.Group());
  // Legs + shoes.
  j.legs = {};
  for (const [side, sx] of [['L', -1], ['R', 1]]) {
    const hip = new THREE.Group(); hip.position.set(sx * 0.1, 0.84, 0); j.hips.add(hip);
    const leg = capsule(P.pants, 0.075, 0.8); leg.position.y = -0.4; hip.add(leg);
    const shoe = ball(P.shoe, 0.08, 0.055, 0.13); shoe.position.set(0, -0.8, 0.04); hip.add(shoe);
    const sole = ball('#ffffff', 0.082, 0.02, 0.132, NO); sole.position.set(0, -0.835, 0.04); hip.add(sole);
    j.legs[side] = { hip, sx };
  }
  // Body: pelvis + sweater torso + collar.
  j.body = new THREE.Group(); j.body.position.y = 0.86; j.hips.add(j.body);
  const pelvis = ball(P.pants, 0.19, 0.13, 0.13); pelvis.position.y = 0.02; j.body.add(pelvis);
  const torso = ball(P.top, 0.205, 0.3, 0.145); torso.position.y = 0.3; j.body.add(torso);
  const hem = ball(P.top, 0.2, 0.06, 0.142); hem.position.y = 0.06; j.body.add(hem);
  for (const sx of [-1, 1]) { const c = ball(P.collar, 0.075, 0.03, 0.05, { outline: 0.1 }); c.position.set(sx * 0.055, 0.565, 0.085); c.rotation.z = sx * -0.35; j.body.add(c); }
  // A small heart badge so the sweater is not plain.
  const badge = ball('#ff6b8b', 0.03, 0.03, 0.01, { outline: 0.15, shadow: false }); badge.position.set(-0.09, 0.42, 0.14); j.body.add(badge);
  // Skin uses a soft two-tone ramp so the lower face never drops into a hard dark band.
  const SOFT = new THREE.DataTexture(new Uint8Array([205, 236, 255]), 3, 1, THREE.RedFormat); SOFT.minFilter = SOFT.magFilter = THREE.NearestFilter; SOFT.needsUpdate = true;
  const skin = new THREE.MeshToonMaterial({ color: new THREE.Color(P.skin), gradientMap: SOFT, emissive: new THREE.Color(P.skin).multiplyScalar(0.08) });
  // Head: round face with soft full cheeks and a small chin (not an egg).
  j.head = new THREE.Group(); j.head.position.y = 0.56; j.head.scale.setScalar(1.32); j.body.add(j.head);
  const neck = capsule(skin, 0.045, 0.12); neck.position.y = 0.04; j.head.add(neck);
  const skull = ball(skin, 0.205, 0.2, 0.195); skull.position.y = 0.22; j.head.add(skull);
  const jaw = ball(skin, 0.175, 0.15, 0.17, { outline: 0.04 }); jaw.position.set(0, 0.17, 0.012); j.head.add(jaw);
  j.face = new THREE.Group(); j.face.position.y = 0.21; j.head.add(j.face);
  for (const sx of [-1, 1]) { const ear = ball(skin, 0.028, 0.04, 0.022); ear.position.set(sx * 0.196, 0.0, -0.01); j.face.add(ear); }
  // Eyes: large, set close and a little below the middle; big iris, two catch-lights, a thin lash arc that hugs the lid.
  j.eyes = [];
  const LID = new THREE.TorusGeometry(0.05, 0.0045, 6, 24, 0.82 * Math.PI);
  for (const sx of [-1, 1]) {
    const e = new THREE.Group(); e.position.set(sx * 0.068, -0.005, 0.172); e.rotation.y = sx * 0.26; j.face.add(e);
    e.add(ball('#ffffff', 0.05, 0.06, 0.024, { outline: 0.08, shadow: false }));
    const iris = new THREE.Group(); iris.position.z = 0.014; e.add(iris);
    iris.add(ball(P.iris, 0.037, 0.044, 0.016, NO));
    const ring = ball(new THREE.MeshBasicMaterial({ color: new THREE.Color(P.iris).offsetHSL(0, 0, 0.12) }), 0.026, 0.031, 0.01, NO); ring.position.set(0, -0.006, 0.007); iris.add(ring);
    const pupil = ball('#120c0a', 0.018, 0.022, 0.01, NO); pupil.position.z = 0.013; iris.add(pupil);
    const h1 = ball(new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.012, 0.013, 0.004, NO); h1.position.set(sx * -0.012 + 0.003, 0.016, 0.022); iris.add(h1);
    const h2 = ball(new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.005, 0.005, 0.003, NO); h2.position.set(0.012, -0.014, 0.022); iris.add(h2);
    const lid = new THREE.Mesh(LID, new THREE.MeshBasicMaterial({ color: '#2a1a14' })); lid.rotation.z = 0.09 * Math.PI; lid.position.set(0, 0.0, 0.012); lid.scale.set(1, 1.15, 1); e.add(lid);
    const flick = ball(new THREE.MeshBasicMaterial({ color: '#2a1a14' }), 0.013, 0.005, 0.006, NO); flick.position.set(sx * 0.05, 0.03, 0.006); flick.rotation.z = sx * 0.75; e.add(flick);
    e.userData.pupil = iris; j.eyes.push(e);
  }
  // Brows: soft, slightly thick, high arches - friendly by default.
  j.brows = [];
  const ARC = new THREE.TorusGeometry(0.036, 0.0085, 8, 24, 0.6 * Math.PI);
  for (const sx of [-1, 1]) {
    const b = new THREE.Group(); b.position.set(sx * 0.072, 0.098, 0.183); b.rotation.y = sx * 0.25; j.face.add(b); j.brows.push(b);
    const arc = new THREE.Mesh(ARC, toonMat(P.hair)); arc.rotation.z = 0.2 * Math.PI; arc.position.y = -0.03; b.add(arc);
  }
  // Tiny button nose, soft round blush.
  const nose = ball(skin, 0.016, 0.013, 0.014, NO); nose.position.set(0, -0.052, 0.197); j.face.add(nose);
  for (const sx of [-1, 1]) { const c = ball(new THREE.MeshBasicMaterial({ color: P.cheek, transparent: true, opacity: 0.55 }), 0.03, 0.02, 0.008, NO); c.position.set(sx * 0.112, -0.062, 0.158); c.rotation.y = sx * 0.62; j.face.add(c); }
  // Mouth: small and high under the nose; a smile arc when closed, a soft D-shaped opening with teeth when talking.
  j.mouth = new THREE.Group(); j.mouth.position.set(0, -0.098, 0.172); j.mouth.rotation.x = -0.22; j.face.add(j.mouth);
  j.mouthHole = ball('#7a2633', 0.042, 0.01, 0.018, { outline: 0.12, shadow: false }); j.mouthHole.children[0].material = new THREE.MeshBasicMaterial({ color: P.lips, side: THREE.BackSide }); j.mouth.add(j.mouthHole);
  j.smile = new THREE.Mesh(new THREE.TorusGeometry(0.032, 0.0062, 8, 24, 0.82 * Math.PI), new THREE.MeshBasicMaterial({ color: '#a2424f' })); j.smile.rotation.z = 1.09 * Math.PI; j.smile.position.set(0, 0.026, 0.01); j.mouth.add(j.smile);
  j.teeth = ball(new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.03, 0.007, 0.01, NO); j.teeth.position.z = 0.008; j.mouth.add(j.teeth);
  j.tongue = ball('#ff8a98', 0.024, 0.011, 0.01, NO); j.tongue.position.z = 0.007; j.mouth.add(j.tongue);
  // Hair: back bob shell, a smooth top cap, one big side-swept fringe instead of separate locks, side locks, flower clip.
  const hm = new THREE.MeshToonMaterial({ color: new THREE.Color(P.hair), gradientMap: toonMat('#000').gradientMap, side: THREE.DoubleSide });
  const hair = new THREE.Group(); hair.position.y = 0.22; hair.scale.set(1.02, 1.04, 1); j.head.add(hair);
  const back = part(new THREE.SphereGeometry(0.222, 40, 24, 0.82 * Math.PI, 1.36 * Math.PI, 0, 0.8 * Math.PI), hm, { outline: 0.03 }); back.position.z = -0.008; hair.add(back);
  const top = part(new THREE.SphereGeometry(0.214, 40, 20, 0, 2 * Math.PI, 0, 0.3 * Math.PI), hm, { outline: 0.03 }); top.position.y = 0.006; hair.add(top);
  const sweep = ball(hm, 0.15, 0.046, 0.06, { outline: 0.05 }); sweep.position.set(-0.03, 0.168, 0.122); sweep.rotation.set(-0.8, 0, 0.26); hair.add(sweep);
  const sweep2 = ball(hm, 0.09, 0.04, 0.05, { outline: 0.05 }); sweep2.position.set(0.1, 0.168, 0.11); sweep2.rotation.set(-0.7, 0.3, -0.25); hair.add(sweep2);
  for (const sx of [-1, 1]) { const s = ball(hm, 0.05, 0.13, 0.06, { outline: 0.06 }); s.position.set(sx * 0.19, -0.07, 0.02); s.rotation.z = sx * 0.12; hair.add(s); }
  const clip = new THREE.Group(); clip.position.set(0.12, 0.16, 0.12); clip.rotation.set(-0.5, 0.5, 0); hair.add(clip);
  for (let k = 0; k < 5; k++) { const a = k * 2 * Math.PI / 5, pt = ball(P.clip, 0.022, 0.022, 0.01, { outline: 0.12, shadow: false }); pt.position.set(Math.cos(a) * 0.022, Math.sin(a) * 0.022, 0); clip.add(pt); }
  const cc = ball('#ffd43b', 0.013, 0.013, 0.008, NO); cc.position.z = 0.006; clip.add(cc);
  // Arms: sweater sleeves, cuff, five-finger hand.
  j.arms = {};
  for (const [side, sx] of [['L', -1], ['R', 1]]) {
    const sh = new THREE.Group(); sh.position.set(sx * 0.215, 0.5, 0); j.body.add(sh);
    const cap = ball(P.top, 0.07, 0.07, 0.07); sh.add(cap);
    const up = capsule(P.top, 0.058, 0.3); up.position.y = -0.14; sh.add(up);
    const el = new THREE.Group(); el.position.y = -0.29; sh.add(el);
    const fo = capsule(P.top, 0.052, 0.26); fo.position.y = -0.12; el.add(fo);
    const cuff = ball(P.collar, 0.054, 0.02, 0.054, { outline: 0.08 }); cuff.position.y = -0.25; el.add(cuff);
    const hand = new THREE.Group(); hand.position.y = -0.31; el.add(hand);
    // Five-finger hand: flat palm facing the camera, four spread fingers, thumb out to the side.
    const palm = ball(P.skin, 0.044, 0.05, 0.02, { outline: 0.08 }); palm.position.y = -0.02; hand.add(palm);
    for (let f = 0; f < 4; f++) {
      const x = (f - 1.5) * 0.021, len = [0.05, 0.058, 0.056, 0.046][f];
      const fg = capsule(P.skin, 0.0105, len, { outline: 0.12 }); fg.position.set(x * 1.15, -0.065 - len * 0.35, 0); fg.rotation.z = x * 5; hand.add(fg);
    }
    const th = capsule(P.skin, 0.012, 0.045, { outline: 0.12 }); th.position.set(-sx * 0.048, -0.008, 0.006); th.rotation.z = -sx * 0.85; hand.add(th);
    j.arms[side] = { sh, el, hand, sx };
  }
  rig.userData.j = j;
  return rig;
}
