// Effects renderer: block particles (the game look — smoke and dust are tumbling cubes), additive glow for fire, flashes
// and tracers, streaks for rain. One InstancedMesh per material, refilled every frame from the emitters' pure functions.
import * as THREE from '/three/three.module.min.js';
import { emitterParticles } from '../lib/assemble.mjs';
import { h01 } from '../lib/rng.mjs';

const MAX = 2400;
export function makeFxLayer() {
  const cubeG = new THREE.BoxGeometry(1, 1, 1);
  const solid = new THREE.InstancedMesh(cubeG, new THREE.MeshStandardMaterial({ roughness: 1, transparent: true, opacity: 0.62, depthWrite: false }), MAX);
  const glow = new THREE.InstancedMesh(cubeG, new THREE.MeshBasicMaterial({ transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false }), 800);
  const streakG = new THREE.BoxGeometry(0.06, 1, 0.06);
  const rain = new THREE.InstancedMesh(streakG, new THREE.MeshBasicMaterial({ color: 0xb8c4d4, transparent: true, opacity: 0.4, depthWrite: false }), 1400);
  for (const m of [solid, glow, rain]) { m.frustumCulled = false; m.count = 0; m.instanceMatrix.setUsage(THREE.DynamicDrawUsage); }
  solid.castShadow = false;
  const group = new THREE.Group(); group.add(solid, glow, rain);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
  const update = (A, t, camPos, weather) => {
    let ns = 0, ng = 0, nr = 0, live = 0;
    for (const em of A.emitters) {
      const ps = emitterParticles(A, em, t); live += ps.length;
      for (const pt of ps) {
        if (pt.glow) { if (ng >= 800) continue; e.set(pt.spin, pt.spin * 0.7, 0); q.setFromEuler(e); s.setScalar(pt.size); p.set(pt.x, pt.y, pt.z); m4.compose(p, q, s); glow.setMatrixAt(ng, m4); c.setRGB(pt.color[0] * pt.alpha * 2, pt.color[1] * pt.alpha * 1.6, pt.color[2] * pt.alpha); glow.setColorAt(ng++, c); }
        else { if (ns >= MAX) continue; e.set(pt.spin, pt.spin * 1.3, pt.spin * 0.5); q.setFromEuler(e); s.setScalar(pt.size * Math.max(0.15, pt.alpha * 1.4)); p.set(pt.x, pt.y, pt.z); m4.compose(p, q, s); solid.setMatrixAt(ns, m4); c.setRGB(pt.color[0], pt.color[1], pt.color[2]); solid.setColorAt(ns++, c); }
      }
    }
    // rain: a box of streaks around the camera, positions hashed by cell so they are stable from frame to frame
    if (weather === 'rain' || weather === 'storm') {
      const n = weather === 'storm' ? 1400 : 900, R = 60, dry = A.dryAt ? A.dryAt(t) : [];   // horror: a circle the rain never touches
      for (let i = 0; i < n; i++) {
        const fall = 70, ph = h01(i, 7), y = ((ph * 60 - t * fall) % 60 + 60) % 60 - 20;
        p.set(camPos.x + (h01(i, 1) - 0.5) * 2 * R, camPos.y + y, camPos.z + (h01(i, 2) - 0.5) * 2 * R);
        if (dry.length && dry.some((c) => (p.x - c.x) ** 2 + (p.z - c.z) ** 2 < c.r * c.r)) continue;
        q.setFromEuler(e.set(0.18, 0, 0.08)); s.set(1, 2.2, 1); m4.compose(p, q, s); rain.setMatrixAt(nr++, m4);
      }
    }
    solid.count = ns; glow.count = ng; rain.count = nr;
    for (const m of [solid, glow, rain]) { m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true; }
    return live;
  };
  return { group, update };
}
