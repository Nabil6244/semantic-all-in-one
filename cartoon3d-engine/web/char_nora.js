// Nora — cartoon build matching the user’s drawn ref:
// oval face, big brown eyes + lashes, open joyful smile, light-pink knotted headband,
// dark low curly ponytail, pink tee + blue denim overalls. Same joints as Maya for poseToon().
import * as THREE from '/three/three.module.min.js';
import { part, toonMat } from './toon.js';

const SPH = new THREE.SphereGeometry(1, 32, 22), CAP = new THREE.CapsuleGeometry(1, 1, 8, 16);
const ball = (c, sx, sy, sz, o) => { const m = part(SPH, c, o); m.scale.set(sx, sy ?? sx, sz ?? sx); return m; };
const capsule = (c, r, len, o) => { const m = part(CAP, c, o); m.scale.set(r, len / 3, r); return m; };
const NO = { outline: 0, shadow: false };

export const NORA_LOOKS = {
  nora: {
    skin: '#f5c9a8', hair: '#1a1210', top: '#ff8eb8', pants: '#4a7ab0', shoe: '#ff8eb8',
    iris: '#3d2418', band: '#ffc4dc', bandKnot: '#ffb0d0', cheek: '#f0a0a0', lips: '#c94d5c',
    button: '#d0d6de', pocket: '#3d6a9a', stitch: '#e8a84a',
  },
};

export function buildNora(look = {}) {
  const P = { ...NORA_LOOKS[look.name || 'nora'], ...(look.colors || {}) };
  const rig = new THREE.Group(), j = {};
  // Wider open mouth so the laughing draw expression reads when talking.
  j.cfg = { k: 0.42, browY: 0.1, mouth: [0.055, 0.02, 0.014, 0.045, 0.022, 0.014, 0.014], tongue: [0.014, 0.028], hop: 0.45, squash: 0.35, armRest: 0.14, elRest: 0.12, nod: 0.08 };
  rig.add(j.hips = new THREE.Group());

  // Legs: denim overalls + pink shoes.
  j.legs = {};
  for (const [side, sx] of [['L', -1], ['R', 1]]) {
    const hip = new THREE.Group(); hip.position.set(sx * 0.1, 0.84, 0); j.hips.add(hip);
    const leg = capsule(P.pants, 0.08, 0.8); leg.position.y = -0.4; hip.add(leg);
    // Yellow stitch line on denim (draw detail).
    const st = capsule(P.stitch, 0.006, 0.55, NO); st.position.set(sx * 0.02, -0.38, 0.07); hip.add(st);
    const shoe = ball(P.shoe, 0.08, 0.055, 0.13); shoe.position.set(0, -0.8, 0.04); hip.add(shoe);
    const sole = ball('#ffffff', 0.082, 0.02, 0.132, NO); sole.position.set(0, -0.835, 0.04); hip.add(sole);
    j.legs[side] = { hip, sx };
  }

  // Body: light pink tee under denim bib + straps + pocket (draw).
  j.body = new THREE.Group(); j.body.position.y = 0.86; j.hips.add(j.body);
  const pelvis = ball(P.pants, 0.21, 0.145, 0.14); pelvis.position.y = 0.02; j.body.add(pelvis);
  const torso = ball(P.top, 0.2, 0.27, 0.14); torso.position.y = 0.3; j.body.add(torso);
  // Overall bib — flatter panel like the draw.
  const bib = part(new THREE.BoxGeometry(0.28, 0.26, 0.06), toonMat(P.pants), { outline: 0.08 });
  bib.position.set(0, 0.4, 0.12); j.body.add(bib);
  // Rectangular chest pocket.
  const pocket = part(new THREE.BoxGeometry(0.12, 0.1, 0.03), toonMat(P.pocket), { outline: 0.1 });
  pocket.position.set(0, 0.38, 0.16); j.body.add(pocket);
  const pocketSt = part(new THREE.BoxGeometry(0.1, 0.008, 0.01), toonMat(P.stitch), NO);
  pocketSt.position.set(0, 0.42, 0.175); j.body.add(pocketSt);
  // Straps + metal clasps.
  for (const sx of [-1, 1]) {
    const strap = capsule(P.pants, 0.024, 0.44, { outline: 0.08 });
    strap.position.set(sx * 0.09, 0.54, 0.02); strap.rotation.z = sx * 0.32; j.body.add(strap);
    const clasp = ball(P.button, 0.02, 0.014, 0.012, { outline: 0.12, shadow: false });
    clasp.position.set(sx * 0.075, 0.5, 0.145); j.body.add(clasp);
    const btn = ball(P.button, 0.016, 0.016, 0.01, { outline: 0.12, shadow: false });
    btn.position.set(sx * 0.19, 0.08, 0.09); j.body.add(btn);
  }

  const SOFT = new THREE.DataTexture(new Uint8Array([205, 236, 255]), 3, 1, THREE.RedFormat);
  SOFT.minFilter = SOFT.magFilter = THREE.NearestFilter; SOFT.needsUpdate = true;
  const skin = new THREE.MeshToonMaterial({ color: new THREE.Color(P.skin), gradientMap: SOFT, emissive: new THREE.Color(P.skin).multiplyScalar(0.08) });

  // Head — soft oval like the draw (not a tall capsule).
  j.head = new THREE.Group(); j.head.position.y = 0.56; j.head.scale.setScalar(1.3); j.body.add(j.head);
  const neck = capsule(skin, 0.048, 0.13); neck.position.y = 0.03; j.head.add(neck);
  const skull = ball(skin, 0.2, 0.205, 0.19); skull.position.y = 0.22; j.head.add(skull);
  const jaw = ball(skin, 0.17, 0.15, 0.165, { outline: 0.04 }); jaw.position.set(0, 0.155, 0.015); j.head.add(jaw);
  j.face = new THREE.Group(); j.face.position.y = 0.2; j.head.add(j.face);
  for (const sx of [-1, 1]) { const ear = ball(skin, 0.026, 0.038, 0.02); ear.position.set(sx * 0.185, -0.01, -0.015); j.face.add(ear); }

  // Eyes — large dark brown with outer lashes (draw).
  j.eyes = [];
  const LID = new THREE.TorusGeometry(0.048, 0.0042, 6, 24, 0.78 * Math.PI);
  for (const sx of [-1, 1]) {
    const e = new THREE.Group(); e.position.set(sx * 0.062, 0.005, 0.168); e.rotation.y = sx * 0.2; j.face.add(e);
    e.add(ball('#ffffff', 0.046, 0.052, 0.022, { outline: 0.06, shadow: false }));
    const iris = new THREE.Group(); iris.position.z = 0.012; e.add(iris);
    iris.add(ball(P.iris, 0.034, 0.038, 0.014, NO));
    const ring = ball(new THREE.MeshBasicMaterial({ color: new THREE.Color(P.iris).offsetHSL(0, 0, 0.1) }), 0.022, 0.026, 0.009, NO);
    ring.position.set(0, -0.004, 0.006); iris.add(ring);
    const pupil = ball('#100a08', 0.015, 0.018, 0.009, NO); pupil.position.z = 0.012; iris.add(pupil);
    const h1 = ball(new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.01, 0.011, 0.003, NO);
    h1.position.set(sx * -0.01, 0.012, 0.02); iris.add(h1);
    const h2 = ball(new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.004, 0.004, 0.002, NO);
    h2.position.set(0.008, -0.01, 0.02); iris.add(h2);
    const lid = new THREE.Mesh(LID, new THREE.MeshBasicMaterial({ color: '#2a1a14' }));
    lid.rotation.z = 0.1 * Math.PI; lid.position.set(0, 0.002, 0.01); lid.scale.set(1, 1.08, 1); e.add(lid);
    // Outer lash flicks (draw).
    for (let k = 0; k < 3; k++) {
      const flick = ball(new THREE.MeshBasicMaterial({ color: '#2a1a14' }), 0.01, 0.0035, 0.004, NO);
      flick.position.set(sx * (0.038 + k * 0.008), 0.02 + k * 0.006, 0.008);
      flick.rotation.z = sx * (0.55 + k * 0.2); e.add(flick);
    }
    e.userData.pupil = iris; j.eyes.push(e);
  }

  // Thin arched brows (draw).
  j.brows = [];
  const ARC = new THREE.TorusGeometry(0.032, 0.0065, 8, 24, 0.5 * Math.PI);
  for (const sx of [-1, 1]) {
    const b = new THREE.Group(); b.position.set(sx * 0.065, 0.1, 0.175); b.rotation.y = sx * 0.18; j.face.add(b); j.brows.push(b);
    const arc = new THREE.Mesh(ARC, toonMat(P.hair)); arc.rotation.z = 0.28 * Math.PI; arc.position.y = -0.025; b.add(arc);
  }

  // Tiny button nose (draw keeps it subtle).
  const nose = ball(skin, 0.014, 0.012, 0.014, NO); nose.position.set(0, -0.045, 0.19); j.face.add(nose);
  for (const sx of [-1, 1]) {
    const c = ball(new THREE.MeshBasicMaterial({ color: P.cheek, transparent: true, opacity: 0.4 }), 0.03, 0.02, 0.006, NO);
    c.position.set(sx * 0.105, -0.055, 0.15); c.rotation.y = sx * 0.55; j.face.add(c);
  }

  // Wide joyful mouth — teeth + tongue when open (draw’s laughing smile).
  j.mouth = new THREE.Group(); j.mouth.position.set(0, -0.1, 0.165); j.mouth.rotation.x = -0.18; j.face.add(j.mouth);
  j.mouthHole = ball('#6b2030', 0.055, 0.014, 0.022, { outline: 0.08, shadow: false });
  j.mouthHole.children[0].material = new THREE.MeshBasicMaterial({ color: P.lips, side: THREE.BackSide }); j.mouth.add(j.mouthHole);
  j.smile = new THREE.Mesh(new THREE.TorusGeometry(0.042, 0.006, 8, 28, 0.9 * Math.PI), new THREE.MeshBasicMaterial({ color: P.lips }));
  j.smile.rotation.z = 1.12 * Math.PI; j.smile.position.set(0, 0.022, 0.01); j.mouth.add(j.smile);
  j.teeth = ball(new THREE.MeshBasicMaterial({ color: '#ffffff' }), 0.042, 0.011, 0.012, NO); j.teeth.position.set(0, 0.006, 0.01); j.mouth.add(j.teeth);
  j.tongue = ball('#ff7a8a', 0.028, 0.014, 0.012, NO); j.tongue.position.z = 0.006; j.mouth.add(j.tongue);

  // Hair: pulled back under headband + LOW curly ponytail at the nape (draw).
  const hm = new THREE.MeshToonMaterial({ color: new THREE.Color(P.hair), gradientMap: toonMat('#000').gradientMap, side: THREE.DoubleSide });
  const hair = new THREE.Group(); hair.position.y = 0.22; j.head.add(hair);
  const back = part(new THREE.SphereGeometry(0.2, 40, 24, 0.9 * Math.PI, 1.2 * Math.PI, 0.05 * Math.PI, 0.8 * Math.PI), hm, { outline: 0.03 });
  back.position.set(0, 0.0, -0.02); hair.add(back);
  const top = part(new THREE.SphereGeometry(0.195, 36, 18, 0, 2 * Math.PI, 0, 0.22 * Math.PI), hm, { outline: 0.03 });
  top.position.set(0, 0.02, -0.01); hair.add(top);
  for (const sx of [-1, 1]) {
    const s = ball(hm, 0.04, 0.1, 0.045, { outline: 0.05 }); s.position.set(sx * 0.175, -0.05, -0.02); s.rotation.z = sx * 0.15; hair.add(s);
  }
  // Low curly ponytail at nape — peeks beside the neck from front.
  const ponyRoot = new THREE.Group(); ponyRoot.position.set(0.06, -0.06, -0.12); hair.add(ponyRoot);
  const bun = ball(hm, 0.08, 0.075, 0.085, { outline: 0.05 }); bun.position.set(0, 0.0, 0); ponyRoot.add(bun);
  const curl1 = ball(hm, 0.06, 0.075, 0.065, { outline: 0.05 }); curl1.position.set(0.05, -0.07, 0.0); curl1.rotation.z = 0.45; ponyRoot.add(curl1);
  const curl2 = ball(hm, 0.055, 0.07, 0.06, { outline: 0.05 }); curl2.position.set(-0.02, -0.12, -0.03); curl2.rotation.z = -0.3; ponyRoot.add(curl2);
  const curl3 = ball(hm, 0.05, 0.06, 0.055, { outline: 0.05 }); curl3.position.set(0.06, -0.16, -0.04); curl3.rotation.z = 0.2; ponyRoot.add(curl3);
  // Side peek so curls read from the front camera.
  const peek = ball(hm, 0.045, 0.07, 0.05, { outline: 0.05 }); peek.position.set(0.12, 0.02, 0.04); peek.rotation.z = -0.4; ponyRoot.add(peek);

  // Light-pink knotted headband — flat wrap across crown (draw), not a beanie.
  const band = new THREE.Group(); band.position.set(0, 0.1, 0.02); hair.add(band);
  const wrapFront = capsule(P.band, 0.034, 0.38, { outline: 0.05 });
  wrapFront.rotation.z = Math.PI / 2; wrapFront.position.set(0, 0.05, 0.13); band.add(wrapFront);
  const wrapTop = capsule(P.band, 0.03, 0.28, { outline: 0.05 });
  wrapTop.rotation.x = Math.PI / 2; wrapTop.position.set(0, 0.08, -0.02); band.add(wrapTop);
  for (const sx of [-1, 1]) {
    const side = capsule(P.band, 0.028, 0.2, { outline: 0.05 });
    side.position.set(sx * 0.155, 0.02, 0.04); side.rotation.z = sx * 0.95; side.rotation.y = sx * -0.2; band.add(side);
  }
  const knot = ball(P.bandKnot, 0.055, 0.045, 0.05, { outline: 0.06 }); knot.position.set(0, 0.09, 0.14); band.add(knot);
  const bowL = ball(P.band, 0.048, 0.03, 0.022, { outline: 0.06 }); bowL.position.set(-0.05, 0.1, 0.13); bowL.rotation.z = 0.4; band.add(bowL);
  const bowR = ball(P.band, 0.048, 0.03, 0.022, { outline: 0.06 }); bowR.position.set(0.05, 0.1, 0.13); bowR.rotation.z = -0.4; band.add(bowR);

  // Arms: pink short sleeves, skin forearms, five-finger hands.
  j.arms = {};
  for (const [side, sx] of [['L', -1], ['R', 1]]) {
    const sh = new THREE.Group(); sh.position.set(sx * 0.215, 0.5, 0); j.body.add(sh);
    const cap = ball(P.top, 0.07, 0.07, 0.07); sh.add(cap);
    const up = capsule(P.top, 0.058, 0.22); up.position.y = -0.1; sh.add(up);
    const el = new THREE.Group(); el.position.y = -0.29; sh.add(el);
    const fo = capsule(skin, 0.05, 0.26); fo.position.y = -0.12; el.add(fo);
    const hand = new THREE.Group(); hand.position.y = -0.31; el.add(hand);
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
