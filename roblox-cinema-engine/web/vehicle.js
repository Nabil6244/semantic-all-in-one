// Vehicle models: original block-built designs per kind (lib/vehicles.mjs), facing +z, origin on the ground (water line for
// boats). Moving parts (wheels, tracks, turret, propellers, rotor, ramp) are named so poseVehicle() can animate them.
import * as THREE from '/three/three.module.min.js';
import { VEHICLES } from '../lib/vehicles.mjs';
import { plastic, rbox, box, cyl, sphere, cone, studTexture } from './gfx.js';

const M = (g, m, x = 0, y = 0, z = 0) => { const o = new THREE.Mesh(g, m); o.position.set(x, y, z); o.castShadow = true; o.receiveShadow = true; return o; };
const dark = () => plastic('#262626', { rough: 0.8 }), steel = () => plastic('#3a3d40', { metal: 0.45, rough: 0.45 }), glass = () => plastic('#8fb4c8', { rough: 0.1, metal: 0.2 });

function wheel(r, w) { const g = new THREE.Group(); const t = M(cyl(r, r, w, 14), dark()); t.rotation.z = Math.PI / 2; g.add(t); const h = M(cyl(r * 0.5, r * 0.5, w * 1.04, 10), plastic('#5a5a52')); h.rotation.z = Math.PI / 2; g.add(h); return g; }

export function buildVehicle(kind, colorOverride) {
  const spec = VEHICLES[kind], col = colorOverride || spec.color, body = plastic(col, { rough: 0.6 }), root = new THREE.Group(), parts = { wheels: [], props: [] };
  const L = spec.len, Wd = spec.wid, H = spec.hgt;
  switch (kind) {
    case 'tank': case 'tank_ww1': {
      for (const s of [-1, 1]) { const tr = M(rbox(1.8, 2.2, L, 0.5), dark(), s * (Wd / 2 - 0.9), 1.1, 0); root.add(tr); for (let i = 0; i < 6; i++) { const w = wheel(0.75, 1.9); w.position.set(s * (Wd / 2 - 0.9), 0.85, -L / 2 + 1.4 + i * (L - 2.8) / 5); root.add(w); parts.wheels.push(w); } }
      root.add(M(rbox(Wd - 3.4, 1.6, L - 1, 0.25), body, 0, 2.2, 0));
      root.add(M(rbox(Wd - 0.4, 0.5, L - 2.4, 0.15), body, 0, 3.1, -0.4));
      if (kind === 'tank') {
        const turret = new THREE.Group(); turret.position.set(0, 3.35, -0.8);
        turret.add(M(rbox(Wd * 0.62, 1.7, L * 0.38, 0.45), body, 0, 0.85, 0));
        const gun = M(cyl(0.22, 0.26, L * 0.48, 10), steel()); gun.rotation.x = Math.PI / 2; gun.position.set(0, 0.95, L * 0.38); turret.add(gun);
        turret.add(M(cyl(0.55, 0.6, 0.45, 12), body, -0.9, 1.9, -0.4));
        root.add(turret); parts.turret = turret;
      } else root.add(M(rbox(2.4, 1.2, 3, 0.2), body, 0, 4, 1));
      break;
    }
    case 'halftrack': case 'apc': case 'truck': case 'truck_old': case 'jeep': case 'humvee': case 'car_old': case 'car': {
      const isJeep = kind === 'jeep' || kind === 'humvee', isTruck = kind.startsWith('truck'), isCar = kind.startsWith('car');
      const r = isTruck ? 1.1 : 0.85;
      for (const z of isTruck ? [L * 0.33, -L * 0.18, -L * 0.36] : [L * 0.32, -L * 0.3]) for (const s of [-1, 1]) { const w = wheel(r, 0.8); w.position.set(s * (Wd / 2 - 0.3), r, z); root.add(w); parts.wheels.push(w); }
      if (kind === 'halftrack' || kind === 'apc') for (const s of [-1, 1]) root.add(M(rbox(1.2, 1.8, L * 0.5, 0.4), dark(), s * (Wd / 2 - 0.6), 0.9, -L * 0.2));
      const cabZ = isTruck ? L * 0.26 : isCar ? 0 : 0.6;
      root.add(M(rbox(Wd - 0.6, 1.4, L - 0.6, 0.25), body, 0, r + 0.6, 0));
      if (isJeep) { root.add(M(box(Wd - 0.6, 0.12, 0.12), steel(), 0, r + 2.2, L * 0.12)); root.add(M(box(Wd - 0.8, 0.9, 0.08), glass(), 0, r + 1.8, L * 0.12)); root.add(M(rbox(1.4, 0.4, 1.4, 0.15), dark(), 0, r + 1.4, -L * 0.35)); }
      else if (isCar) { root.add(M(rbox(Wd - 0.8, 1.4, L * 0.55, 0.45), body, 0, r + 1.9, -0.3)); root.add(M(box(Wd - 0.7, 0.9, L * 0.4), glass(), 0, r + 2.0, -0.3)); }
      else { root.add(M(rbox(Wd - 0.4, 2.0, 3.4, 0.3), body, 0, r + 2.0, cabZ)); root.add(M(box(Wd - 0.8, 0.9, 0.1), glass(), 0, r + 2.4, cabZ + 1.72)); }
      if (isTruck) { const bed = new THREE.Group(); bed.add(M(rbox(Wd, 0.4, L * 0.58, 0.1), body, 0, r + 1.4, -L * 0.18)); const cover = M(cyl(Wd / 2, Wd / 2, L * 0.56, 12, 1), plastic('#6b6a50', { rough: 0.9 })); cover.rotation.x = Math.PI / 2; cover.scale.set(1, 1, 0.9); cover.position.set(0, r + 2.8, -L * 0.18); bed.add(cover); root.add(bed); }
      if (kind === 'halftrack' || kind === 'apc') root.add(M(box(Wd - 0.2, 1.2, L * 0.55), body, 0, r + 1.8, -L * 0.18));
      break;
    }
    case 'motorbike': case 'bicycle': { for (const z of [1.6, -1.6]) { const w = wheel(0.8, 0.25); w.position.set(0, 0.8, z); root.add(w); parts.wheels.push(w); } root.add(M(box(0.4, 0.4, 3.2), body, 0, 1.5, 0)); break; }
    case 'artillery': { for (const s of [-1, 1]) { const w = wheel(1.1, 0.4); w.position.set(s * 1.8, 1.1, 0); root.add(w); } root.add(M(box(2.6, 1.6, 0.25), body, 0, 1.8, 0.6)); const b = M(cyl(0.25, 0.32, 7, 10), steel()); b.rotation.x = Math.PI / 2 - 0.35; b.position.set(0, 2.8, 2.6); root.add(b); for (const s of [-1, 1]) { const tr = M(box(0.3, 0.3, 5), body, s * 0.8, 0.5, -2.6); tr.rotation.y = s * 0.25; root.add(tr); } break; }
    case 'radar': { root.add(M(box(4, 3, 4), body, 0, 1.5, 0)); const dish = new THREE.Group(); dish.position.y = 6; const d = M(sphere(3, 14, 8, Math.PI * 2, Math.PI / 3), steel()); d.rotation.x = -Math.PI / 2 - 0.4; dish.add(d); dish.add(M(cyl(0.2, 0.2, 3), steel(), 0, -1.5, 0)); root.add(dish); parts.turret = dish; break; }
    case 'cart': { for (const s of [-1, 1]) { const w = wheel(1.3, 0.25); w.position.set(s * 1.7, 1.3, 0); root.add(w); parts.wheels.push(w); } root.add(M(box(3.2, 0.9, 5), plastic('#7a5a3a', { rough: 0.9 }), 0, 1.8, 0)); break; }
    case 'train': { root.add(M(rbox(Wd, H * 0.6, L, 0.3), plastic('#2b2b2b'), 0, H * 0.4, 0)); root.add(M(cyl(1.6, 1.6, 3, 10), plastic('#222'), 0, H * 0.85, L * 0.35)); break; }
    case 'horse': { root.add(M(rbox(1.6, 1.8, 4, 0.5), body, 0, 3.4, 0)); root.add(M(rbox(0.9, 2, 1, 0.3), body, 0, 4.6, 2.2)); for (const [x, z] of [[-0.5, 1.4], [0.5, 1.4], [-0.5, -1.4], [0.5, -1.4]]) root.add(M(box(0.45, 2.6, 0.45), body, x, 1.3, z)); break; }
    case 'landing_craft': case 'patrol_boat': case 'sampan': {
      const hull = M(rbox(Wd, 3, L, 0.4), body, 0, 0.3, 0); root.add(hull);
      root.add(M(box(Wd - 1.4, 0.3, L - 3), plastic('#4e5856', { rough: 0.8 }), 0, 0.2, -0.5));
      if (kind === 'landing_craft') {
        for (const s of [-1, 1]) root.add(M(box(0.4, 3.2, L - 4.4), body, s * (Wd / 2 - 0.2), 2.0, -1.8));
        root.add(M(rbox(2.6, 2.2, 2.4, 0.25), body, 0, 2.6, -L / 2 + 1.8));
        const ramp = new THREE.Group(); ramp.position.set(0, 0.5, L / 2 - 0.3); const rp = M(box(Wd - 0.4, 0.4, 3.8), plastic('#5d6865', { rough: 0.7 })); rp.position.set(0, 1.9, 0); rp.rotation.x = Math.PI / 2; ramp.add(rp); root.add(ramp); parts.ramp = ramp;
      } else if (kind === 'patrol_boat') root.add(M(rbox(3, 2.4, 4, 0.3), body, 0, 2.5, -1));
      break;
    }
    case 'ship': case 'battleship': case 'steam_ship': case 'submarine': {
      const sub = kind === 'submarine';
      const hull = new THREE.Group();
      const mid = M(rbox(Wd, sub ? 4 : 6, L * 0.8, 1), body, 0, sub ? -0.5 : 0.8, -L * 0.04); hull.add(mid);
      const bow = M(cone(Wd / 2, L * 0.22, 4), body); bow.rotation.set(Math.PI / 2, Math.PI / 4, 0); bow.scale.set(1, 1, sub ? 0.7 : 1.1); bow.position.set(0, sub ? -0.5 : 1.2, L * 0.43); hull.add(bow);
      hull.add(M(box(Wd - 0.6, 0.3, L * 0.78), plastic('#8c8a80', { map: studTexture('#8c8a80'), rough: 0.8 }), 0, sub ? 1.5 : 3.9, -L * 0.04));
      if (!sub) {
        const sup = kind === 'battleship' ? 3 : 2;
        hull.add(M(rbox(Wd * 0.55, H * 0.35, L * 0.18, 0.3), body, 0, 4 + H * 0.17, -L * 0.02));
        hull.add(M(rbox(Wd * 0.4, H * 0.25, L * 0.08, 0.2), body, 0, 4 + H * 0.45, -L * 0.02));
        hull.add(M(cyl(Wd * 0.13, Wd * 0.15, H * 0.3, 10), plastic('#4a4c4e'), 0, 4 + H * 0.4, -L * 0.14));
        hull.add(M(cyl(0.2, 0.25, H * 0.5, 6), steel(), 0, 4 + H * 0.7, 0.02 * L));
        for (let i = 0; i < sup; i++) { const z = (i < sup - 1 ? L * 0.22 + i * L * 0.11 : -L * 0.3), tr = new THREE.Group(); tr.position.set(0, 4.3, z); tr.add(M(rbox(Wd * 0.38, 2, Wd * 0.42, 0.4), body, 0, 1, 0)); for (const s of [-1, 1]) { const g = M(cyl(0.3, 0.35, Wd * 0.7, 8), steel()); g.rotation.x = Math.PI / 2; g.position.set(s * 0.8, 1.2, (z > 0 ? 1 : -1) * Wd * 0.45); tr.add(g); } hull.add(tr); }
      } else { hull.add(M(rbox(2.4, 4, 7, 0.6), body, 0, 3, 2)); }
      root.add(hull);
      break;
    }
    case 'galley': case 'sailing_ship': { root.add(M(rbox(Wd, 4, L, 1.2), body, 0, 1, 0)); const mast = M(cyl(0.4, 0.5, H, 8), plastic('#5a3b22'), 0, H / 2, 0); root.add(mast); root.add(M(box(Wd * 1.6, H * 0.4, 0.2), plastic('#e9e2cf', { side: 'double' }), 0, H * 0.55, 0.5)); break; }
    case 'transport_plane': case 'bomber': case 'fighter_prop': case 'biplane': case 'jet': case 'drone': {
      const fus = M(cyl(H * 0.32, H * 0.22, L, 14), body); fus.rotation.x = Math.PI / 2; root.add(fus);
      const nose = M(sphere(H * 0.32, 12, 8), body); nose.position.z = L / 2; nose.scale.z = 1.4; root.add(nose);
      root.add(M(rbox(Wd, 0.5, L * (kind === 'fighter_prop' ? 0.26 : 0.18), 0.2), body, 0, kind === 'transport_plane' || kind === 'bomber' ? H * 0.15 : -H * 0.12, L * 0.06));
      if (kind === 'biplane') root.add(M(rbox(Wd, 0.4, L * 0.22, 0.15), body, 0, H * 0.6, L * 0.1));
      root.add(M(rbox(Wd * 0.36, 0.35, L * 0.12, 0.12), body, 0, H * 0.1, -L * 0.44));
      root.add(M(rbox(0.35, H * 0.7, L * 0.14, 0.12), body, 0, H * 0.45, -L * 0.44));
      root.add(M(box(H * 0.4, H * 0.22, L * 0.12), glass(), 0, H * 0.25, L * 0.36));
      const engines = spec.props === 4 ? [-0.36, -0.18, 0.18, 0.36] : spec.props === 2 ? [-0.22, 0.22] : spec.props === 1 ? [0] : [];
      for (const ex of engines) {
        const x = ex * Wd, z = spec.props === 1 ? L / 2 + 0.6 : L * 0.16;
        if (spec.props !== 1) root.add(M(cyl(0.9, 0.8, 4.6, 10), body, x, H * 0.12, z - 1.6)).rotation.x = Math.PI / 2;
        const prop = new THREE.Group(); prop.position.set(x, H * 0.12, z + 0.9); for (let b = 0; b < 3; b++) { const bl = M(box(0.35, 3.6, 0.12), dark()); bl.rotation.z = b * Math.PI * 2 / 3; bl.position.set(Math.sin(b * 2.094) * 1.6, Math.cos(b * 2.094) * 1.6, 0); bl.rotation.z = -b * 2.094; prop.add(bl); } prop.add(M(sphere(0.4, 8, 6), plastic('#444'))); root.add(prop); parts.props.push(prop);
      }
      // invasion-style identification stripes are a period fact; drawn as plain bands, no insignia
      if (kind === 'transport_plane' || kind === 'fighter_prop') for (let k = 0; k < 5; k++) root.add(M(box(0.3, H * 0.66, 0.6), plastic(k % 2 ? '#1d1d1d' : '#f0f0f0'), 0, 0, -L * 0.25 + k * 0.62)).scale.set(H * 2.2, 1, 1);
      break;
    }
    case 'helicopter': {
      root.add(M(rbox(Wd, H * 0.7, L * 0.45, 1.2), body, 0, H * 0.4, L * 0.08));
      root.add(M(box(Wd * 0.9, H * 0.4, 1), glass(), 0, H * 0.55, L * 0.3));
      root.add(M(cyl(0.5, 0.8, L * 0.55, 8), body, 0, H * 0.6, -L * 0.36)).rotation.x = Math.PI / 2;
      for (const s of [-1, 1]) root.add(M(box(0.3, 0.3, L * 0.5), steel(), s * Wd * 0.45, 0.15, L * 0.08));
      const rotor = new THREE.Group(); rotor.position.y = H + 0.4; for (let b = 0; b < 2; b++) { const bl = M(box(0.8, 0.12, L * 1.05), dark()); bl.rotation.y = b * Math.PI / 2; rotor.add(bl); } root.add(rotor); parts.rotor = rotor;
      break;
    }
    default: root.add(M(rbox(Wd, H, L, 0.3), body, 0, H / 2, 0));
  }
  root.userData = { parts, kind, spec };
  root.traverse((o) => { if (o.isMesh) o.castShadow = spec.cls !== 'water' || L < 30; });
  return root;
}

/** Pose a vehicle model from vehicleState(). */
export function poseVehicle(rig, st) {
  const { parts } = rig.userData;
  rig.position.set(st.x, st.y, st.z);
  rig.rotation.set(0, 0, 0); rig.rotateY(st.yaw); rig.rotateX(st.pitch); rig.rotateZ(st.roll);
  for (const w of parts.wheels) w.rotation.x = st.wheel;
  for (const p of parts.props) p.rotation.z = st.prop;
  if (parts.rotor) parts.rotor.rotation.y = st.rotor;
  if (parts.ramp) parts.ramp.rotation.x = st.ramp * 1.45;
  if (parts.turret && rig.userData.kind === 'radar') parts.turret.rotation.y = st.rotor * 0.05;
  rig.visible = st.visible !== false;
}
