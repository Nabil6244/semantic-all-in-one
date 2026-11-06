// Blocky character rig built from a look (lib/characters.mjs) and posed from lib/animation.mjs poses. Feet at the origin,
// facing +z. Rigid limbs pivot at shoulders and hips; the face is a decal on the rounded head.
import * as THREE from '/three/three.module.min.js';
import { plastic, rbox, box, cyl, sphere, cone, faceTexture, torsoTexture } from './gfx.js';

const faceMats = new Map();
function faceMat(face, open) {
  const key = JSON.stringify(face) + open;
  let m = faceMats.get(key);
  if (!m) { m = new THREE.MeshStandardMaterial({ map: faceTexture(face, open), transparent: true, roughness: 0.6, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }); faceMats.set(key, m); }
  return m;
}
const mesh = (g, m, x = 0, y = 0, z = 0, shadow = true) => { const o = new THREE.Mesh(g, m); o.position.set(x, y, z); o.castShadow = shadow; o.receiveShadow = false; return o; };

function hat(look) {
  const h = look.hat; if (!h) return hair(look);
  const g = new THREE.Group(), col = h.color || '#4a4a3a', M = plastic(col, { rough: 0.7 });
  switch (h.type) {
    case 'crest': { const d = mesh(sphere(0.84, 18, 10, Math.PI * 2, Math.PI / 2), M, 0, 0.4, 0); d.scale.set(1, 0.9, 1.05); g.add(d); g.add(mesh(cyl(0.88, 0.92, 0.12, 18), M, 0, 0.42, 0.02)); g.add(mesh(box(0.2, 0.34, 1.1), plastic('#b02a22', { rough: 0.8 }), 0, 1.22, 0)); break; }
    case 'm1': case 'modern': case 'ssh': { const d = mesh(sphere(0.86, 18, 10, Math.PI * 2, Math.PI / 2), M, 0, 0.42, 0); d.scale.set(1, 0.85, 1.05); g.add(d); g.add(mesh(cyl(0.9, 0.95, 0.1, 18), M, 0, 0.44, 0.02)); if (h.net) g.add(mesh(sphere(0.88, 10, 6, Math.PI * 2, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x3a3a2a, wireframe: true }), 0, 0.42, 0)); break; }
    case 'brodie': { g.add(mesh(cyl(1.15, 1.15, 0.08, 20), M, 0, 0.5, 0)); const d = mesh(sphere(0.72, 16, 8, Math.PI * 2, Math.PI / 2), M, 0, 0.5, 0); d.scale.y = 0.7; g.add(d); break; }
    case 'stahl': { const d = mesh(sphere(0.84, 18, 10, Math.PI * 2, Math.PI / 2), M, 0, 0.36, 0); d.scale.set(1, 0.95, 1.08); g.add(d); g.add(mesh(cyl(0.86, 0.98, 0.34, 18), M, 0, 0.26, -0.04)); break; }
    case 'kabuto': case 'adrian': { const d = mesh(sphere(0.82, 16, 8, Math.PI * 2, Math.PI / 2), M, 0, 0.42, 0); g.add(d); g.add(mesh(cyl(0.95, 0.95, 0.08, 16), M, 0, 0.44, 0.1)); if (h.type === 'adrian') g.add(mesh(box(0.12, 0.3, 1.2), M, 0, 1.15, 0)); break; }
    case 'pith': { const d = mesh(sphere(0.95, 16, 8, Math.PI * 2, Math.PI / 2), M, 0, 0.42, 0); d.scale.set(1.08, 0.8, 1.15); g.add(d); g.add(mesh(cyl(1.18, 1.18, 0.06, 18), M, 0, 0.42, 0)); break; }
    case 'peaked': case 'police_cap': { g.add(mesh(cyl(0.78, 0.66, 0.42, 18), M, 0, 0.66, 0)); g.add(mesh(cyl(0.68, 0.68, 0.14, 18), plastic('#2a2a2a'), 0, 0.45, 0)); g.add(mesh(box(0.95, 0.06, 0.5), plastic('#1d1d1d', { rough: 0.3 }), 0, 0.42, 0.7)); g.add(mesh(box(0.22, 0.14, 0.04), plastic('#c8b46a', { metal: 0.6, rough: 0.3 }), 0, 0.66, 0.72)); break; }
    case 'cap_soft': case 'flat_cap': { g.add(mesh(box(1.32, 0.34, 1.34), M, 0, 0.62, -0.02)); g.add(mesh(box(1.2, 0.08, 0.5), M, 0, 0.48, 0.78)); break; }
    case 'beret': { const b = mesh(sphere(0.75, 14, 8), M, -0.12, 0.66, 0); b.scale.set(1.08, 0.3, 1.05); b.rotation.z = 0.2; g.add(b); break; }
    case 'headscarf': { const b = mesh(sphere(0.8, 14, 8, Math.PI * 2, Math.PI * 0.6), M, 0, 0.42, -0.08); b.scale.set(1, 1.15, 1); b.rotation.x = -0.3; g.add(b); break; } // sits back on the head: the eyes stay visible
    case 'straw': { g.add(mesh(cone(1.45, 0.75, 18), plastic('#d8c27a', { rough: 0.9 }), 0, 0.85, 0)); break; }
    case 'conical': { g.add(mesh(cone(1.5, 0.8, 18), plastic('#d8c27a', { rough: 0.9 }), 0, 0.88, 0)); break; }
    case 'hardhat': { const d = mesh(sphere(0.8, 14, 8, Math.PI * 2, Math.PI / 2), plastic('#e0b030'), 0, 0.45, 0); g.add(d); g.add(mesh(cyl(0.95, 0.95, 0.06, 16), plastic('#e0b030'), 0, 0.46, 0.08)); break; }
    case 'sailor_cap': { g.add(mesh(cyl(0.66, 0.6, 0.38, 16), plastic('#f4f4f4'), 0, 0.64, 0)); g.add(mesh(cyl(0.74, 0.74, 0.06, 16), plastic('#f4f4f4'), 0, 0.46, 0)); break; }
    case 'pilot_cap': { const d = mesh(sphere(0.78, 14, 8, Math.PI * 2, Math.PI / 1.7), plastic('#5a3b22', { rough: 0.8 }), 0, 0.2, 0); g.add(d); for (const s of [-1, 1]) g.add(mesh(cyl(0.2, 0.2, 0.1, 10), plastic('#9ab', { metal: 0.4, rough: 0.2 }), s * 0.3, 0.6, 0.62)); break; }
    case 'fedora': { g.add(mesh(cyl(0.62, 0.66, 0.5, 16), plastic('#3a3530'), 0, 0.7, 0)); g.add(mesh(cyl(1.0, 1.0, 0.06, 18), plastic('#3a3530'), 0, 0.46, 0)); break; }
    default: return hair(look);
  }
  if (h.strap) g.add(mesh(box(1.3, 0.08, 0.06), plastic('#3a3020'), 0, -0.45, 0.55, false));
  return g;
}
function hair(look) {
  const f = look.face, g = new THREE.Group(); if (f.hair === 'none') return g;
  const M = plastic(f.hairColor, { rough: 0.8 });
  if (f.hair === 'short' || f.hair === 'side') { g.add(mesh(rbox(1.34, 0.32, 1.34, 0.12), M, 0, 0.52, -0.02)); if (f.hair === 'side') g.add(mesh(box(0.5, 0.2, 0.9), M, -0.35, 0.68, 0.15)); }
  if (f.hair === 'bald_sides') for (const s of [-1, 1]) g.add(mesh(box(0.12, 0.45, 0.9), M, s * 0.66, 0.05, -0.15));
  if (f.hair === 'long') { g.add(mesh(rbox(1.38, 0.34, 1.38, 0.12), M, 0, 0.5, 0)); g.add(mesh(box(1.36, 1.2, 0.3), M, 0, -0.2, -0.56)); }
  if (f.hair === 'bun') { g.add(mesh(rbox(1.34, 0.3, 1.34, 0.12), M, 0, 0.52, 0)); g.add(mesh(sphere(0.32, 10, 8), M, 0, 0.7, -0.6)); }
  return g;
}

function weapon(kind) {
  const g = new THREE.Group(), wood = plastic('#6b4a2a', { rough: 0.7 }), steel = plastic('#2b2d30', { metal: 0.5, rough: 0.4 });
  const L = kind === 'smg' ? 2.2 : kind === 'spear' ? 5 : 3.4;
  if (kind === 'spear') { g.add(mesh(cyl(0.06, 0.06, 5, 6), wood, 0, 0, 0)); g.add(mesh(cone(0.14, 0.5, 6), steel, 0, 2.7, 0)); g.rotation.x = Math.PI / 2; return g; }
  if (kind === 'sword') { g.add(mesh(box(0.1, 2.2, 0.04), plastic('#c9ccd0', { metal: 0.7, rough: 0.2 }), 0, 1, 0)); g.rotation.x = Math.PI / 2; return g; }
  g.add(mesh(box(0.22, 0.3, L * 0.55), kind === 'rifle_assault' ? steel : wood, 0, 0, -L * 0.05));
  g.add(mesh(box(0.12, 0.12, L * 0.5), steel, 0, 0.12, L * 0.42));
  g.add(mesh(box(0.2, 0.36, 0.5), kind === 'rifle_assault' ? steel : wood, 0, -0.1, -L * 0.36));
  if (kind === 'smg' || kind === 'rifle_assault') g.add(mesh(box(0.14, 0.5, 0.22), steel, 0, -0.32, 0.25));
  const tip = new THREE.Object3D(); tip.position.set(0, 0.12, L * 0.68); g.add(tip); g.userData.tip = tip;
  return g;
}

let flashMat = null, chuteMat = null;
/** Build a character from its look. Returns the rig used by poseRig(). */
export function buildCharacter(look) {
  const root = new THREE.Group(), body = new THREE.Group(); root.add(body);
  const skin = plastic(look.skin, { rough: 0.5 }), shirt = plastic(look.shirt, { rough: 0.62 }), pants = plastic(look.pants, { rough: 0.68 });
  const torsoM = plastic('#ffffff', { map: torsoTexture(look), rough: 0.62 });
  const hips = new THREE.Group(); hips.position.y = 2; body.add(hips);
  const legL = new THREE.Group(), legR = new THREE.Group(); legL.position.set(-0.5, 0, 0); legR.position.set(0.5, 0, 0); hips.add(legL, legR);
  for (const leg of [legL, legR]) { leg.add(mesh(rbox(0.98, 2, 0.98, 0.06), pants, 0, -1, 0)); leg.add(mesh(box(1.0, 0.42, 1.08), plastic('#2a2420', { rough: 0.6 }), 0, -1.79, 0.03)); }
  const torso = new THREE.Group(); hips.add(torso);
  torso.add(mesh(rbox(2, 2, 1, 0.07), torsoM, 0, 1, 0));
  const armL = new THREE.Group(), armR = new THREE.Group(); armL.position.set(-1.5, 1.78, 0); armR.position.set(1.5, 1.78, 0); torso.add(armL, armR);
  const sleeve = look.torso === 'shirt' && look.role !== 'crowd' ? skin : look.torso === 'suit' ? plastic(look.shirt) : shirt;
  for (const arm of [armL, armR]) { arm.add(mesh(rbox(0.98, 1.6, 0.98, 0.06), sleeve, 0, -0.58, 0)); arm.add(mesh(rbox(0.96, 0.42, 0.96, 0.08), skin, 0, -1.58, 0)); }
  const head = new THREE.Group(); head.position.y = 2.02; torso.add(head);
  head.add(mesh(rbox(1.22, 1.15, 1.22, 0.32), skin, 0, 0.58, 0));
  const face = new THREE.Mesh(new THREE.PlaneGeometry(1.18, 1.12), faceMat(look.face, false)); face.position.set(0, 0.56, 0.615); head.add(face);
  const hatG = hat(look); hatG.position.y = 0.58; head.add(hatG);
  if (look.costume === 'sheet') {   // a plain white sheet with two eyeholes: no face, no hair, just the shape
    const sheet = plastic('#e8e5da', { rough: 0.95 }), hole = plastic('#0b0b0d', { rough: 1 });
    face.visible = false; hatG.visible = false;
    head.add(mesh(sphere(0.98, 16, 12), sheet, 0, 0.55, 0));
    for (const s of [-1, 1]) { const e = mesh(cyl(0.15, 0.15, 0.06, 10), hole, s * 0.33, 0.68, 0.93, false); e.rotation.x = Math.PI / 2; head.add(e); }
    torso.add(mesh(cyl(0.95, 1.8, 3.5, 14), sheet, 0, 0.35, 0));
    for (const arm of [armL, armR]) arm.add(mesh(rbox(1.04, 1.7, 1.04, 0.08), sheet, 0, -0.55, 0));
  }
  // gear
  if (look.gear.includes('backpack')) torso.add(mesh(rbox(1.6, 1.4, 0.6, 0.12), plastic(look.gearColor, { rough: 0.8 }), 0, 1.1, -0.8));
  if (look.gear.includes('chute_pack')) torso.add(mesh(rbox(1.5, 1.1, 0.5, 0.12), plastic('#6f6a4a', { rough: 0.8 }), 0, 1.6, -0.75));
  if (look.gear.includes('radio')) torso.add(mesh(box(1.1, 1.3, 0.55), plastic('#4a4d38'), 0, 1.15, -1.25)), torso.add(mesh(cyl(0.03, 0.03, 2.2, 4), plastic('#222'), 0.4, 2.6, -1.3));
  if (look.gear.includes('medbag')) torso.add(mesh(box(0.8, 0.7, 0.4), plastic('#e9e4d4'), 1.05, 0.25, 0.3));
  if (look.gear.includes('holster')) torso.add(mesh(box(0.35, 0.55, 0.3), plastic('#3a2a1c'), 1.05, 0.15, 0.1));
  if (look.gear.includes('binoculars')) torso.add(mesh(box(0.6, 0.35, 0.3), plastic('#222'), 0, 1.4, 0.62));
  if (look.gear.includes('camera')) torso.add(mesh(box(0.7, 0.5, 0.4), plastic('#1d1d1d'), 0.3, 1.2, 0.7));
  if (look.gear.includes('papers')) armL.add(mesh(box(0.8, 0.04, 0.6), plastic('#f1efe6'), 0.2, -1.8, 0.5));
  let gun = null;
  if (look.weapon) { gun = weapon(look.weapon); torso.add(gun); }
  if (!flashMat) flashMat = new THREE.MeshBasicMaterial({ color: 0xffd27a, transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending });
  const flash = new THREE.Mesh(sphere(0.45, 8, 6), flashMat); flash.visible = false; if (gun && gun.userData.tip) gun.userData.tip.add(flash);   // spears and swords have no muzzle
  // parachute canopy (hidden unless the pose has one)
  if (!chuteMat) chuteMat = new THREE.MeshStandardMaterial({ color: 0xd9d4c0, roughness: 0.85, side: THREE.DoubleSide });
  const chute = new THREE.Group();
  const canopy = new THREE.Mesh(sphere(6, 16, 6, Math.PI * 2, Math.PI / 2.6), chuteMat); canopy.position.y = 9; canopy.scale.y = 0.55; canopy.castShadow = true; chute.add(canopy);
  for (let i = 0; i < 6; i++) { const a = i / 6 * Math.PI * 2, l = new THREE.Mesh(cyl(0.03, 0.03, 7, 3), plastic('#555')); l.position.set(Math.cos(a) * 2.4, 6.5, Math.sin(a) * 2.4); l.rotation.set(Math.sin(a) * 0.55, 0, -Math.cos(a) * 0.55); chute.add(l); }
  chute.visible = false; chute.position.y = 2; torso.add(chute);
  root.scale.setScalar(look.scale || 1);
  root.userData = { body, hips, torso, legL, legR, armL, armR, head, face, gun, flash, chute, look, talk: false };
  return root;
}

const GUN = {
  carry: { p: [0.75, 1.0, 0.75], r: [-0.9, 0.2, 0.7] }, port: { p: [0.4, 1.1, 0.95], r: [-0.55, 0.65, 0] }, aim: { p: [0.95, 2.05, 1.1], r: [0, 0, 0] },
  back: { p: [0, 1.2, -0.9], r: [0.1, 0, 0.9] }, upright: { p: [1.2, 0.6, 0.5], r: [-1.45, 0, 0] },
};
/** A small thing held in a hand (lib/horror.mjs HELD_ITEMS), built at the hand's tip in the arm's own space. */
export function buildHeld(item, color) {
  const g = new THREE.Group();
  if (item === 'paper_bag') { g.add(mesh(box(1.5, 1.9, 1.0), plastic('#b48a5a', { rough: 0.95 }), 0, -0.9, 0.1)); g.add(mesh(box(1.52, 0.25, 1.02), plastic('#9a7448', { rough: 0.95 }), 0, 0.02, 0.1)); }
  else if (item === 'gift_small') {
    const wrap = plastic(color || '#d9b13b', { metal: 0.65, rough: 0.28 });
    const body = mesh(cyl(0.2, 0.2, 0.5, 12), wrap); body.rotation.z = Math.PI / 2; g.add(body);           // a sweet in a twisted wrapper
    for (const k of [-1, 1]) { const end = mesh(cone(0.2, 0.28, 8), wrap, k * 0.38, 0, 0); end.rotation.z = k * Math.PI / 2; g.add(end); }
  } else if (item === 'letter') g.add(mesh(box(1.0, 0.04, 0.65), plastic('#efe8d6'), 0, 0, 0.1));
  else if (item === 'card_id') g.add(mesh(box(0.7, 0.04, 0.45), plastic('#dfe6ea'), 0, 0, 0.05));
  else if (item === 'drawing') g.add(mesh(box(1.1, 0.03, 0.85), plastic('#f6f3ea'), 0, 0, 0.1));
  else if (item === 'phone') g.add(mesh(rbox(0.42, 0.08, 0.8, 0.04), plastic('#1c1d20', { rough: 0.3 }), 0, 0, 0.05), mesh(box(0.36, 0.02, 0.7), plastic('#9fc3ff', { emissive: '#7fa8ff', emissiveIntensity: 0.9 }), 0, 0.05, 0.05));
  g.position.set(0, -1.95, 0.15);
  return g;
}

/** Change a face for this frame (the reflection): {mouth, eyes, blank, stretch}. */
export function setFace(rig, f) {
  const u = rig.userData; u.baseFace = u.baseFace || u.look.face;
  const face = { ...u.baseFace, ...(f.mouth ? { mouth: f.mouth } : {}), ...(f.eyes ? { eyes: f.eyes } : {}) };
  u.look = { ...u.look, face }; u.face.material = faceMat(face, false); u.face.visible = !f.blank;
  const k = f.stretch || 1; u.face.scale.set(k, k, 1);
}

/** Apply a pose (lib/animation.mjs) to a rig; t drives the mouth flap while talking. */
export function poseRig(rig, pose, t) {
  const u = rig.userData;
  u.body.position.y = pose.root.y; u.body.rotation.set(0, 0, 0);
  u.hips.rotation.set(pose.root.pitch, pose.root.yaw || 0, pose.root.roll || 0);
  u.hips.position.y = 2 + 0; u.torso.rotation.set(pose.torso.pitch, pose.torso.yaw, 0);
  u.head.rotation.set(pose.head.pitch, pose.head.yaw, 0);
  u.armL.rotation.set(-pose.armL.x, 0, -pose.armL.z); u.armR.rotation.set(-pose.armR.x, 0, pose.armR.z);
  u.legL.rotation.set(-pose.legL.x, 0, -(pose.legL.z || 0)); u.legR.rotation.set(-pose.legR.x, 0, pose.legR.z || 0);
  if (u.gun) {
    const g = GUN[pose.gun];
    u.gun.visible = !!g;
    if (g) { u.gun.position.set(...g.p); u.gun.rotation.set(...g.r); }
    u.flash.visible = pose.flash > 0 && pose.gun === 'aim';
  }
  u.chute.visible = (pose.chute || 0) > 0.5;
  const talking = !!pose.talking, open = talking && Math.sin(t * 34) > 0.1;
  if (open !== u.talk) { u.face.material = faceMat(u.look.face, open); u.talk = open; }
}
