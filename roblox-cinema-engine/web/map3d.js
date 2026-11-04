// The tabletop map: countries as raised plastic tiles on a studded sea baseplate, borders and coasts as dark seams, pins that
// pop up, routes that draw themselves. Geometry comes projected from Node (render.mjs crops Natural Earth to the bbox).
import * as THREE from '/three/three.module.min.js';
import { plastic, studTexture, cyl, sphere, cone, rbox } from './gfx.js';
import { makeProj } from '../lib/mapproj.mjs';

const LAND = ['#c9bd8f', '#b9c48a', '#d3b98a', '#bfb38a', '#c6c79a', '#d6c59a', '#b8b48a'];

export function buildMap(scene, geo, look) {
  const root = new THREE.Group(), P = makeProj(scene.map.bbox);
  const sea = new THREE.Mesh(new THREE.BoxGeometry(6000, 2, 6000), plastic('#3f7f9f', { map: studTexture('#3f7f9f'), rough: 0.75 }));
  sea.material.map.repeat.set(380, 380); sea.position.y = -1; sea.receiveShadow = true; root.add(sea);
  const focus = new Set((geo.focus || []).map((x) => x.toLowerCase()));
  (geo.countries || []).forEach((c, ci) => {
    const hl = focus.has(c.name.toLowerCase());
    const col = hl ? '#d9b86a' : LAND[ci % LAND.length];
    for (const poly of c.polys) {
      if (poly.length < 3) continue;
      const shape = new THREE.Shape(poly.map(([x, z]) => new THREE.Vector2(x, -z)));
      const g = new THREE.ExtrudeGeometry(shape, { depth: hl ? 4.2 : 3, bevelEnabled: true, bevelThickness: 0.5, bevelSize: 0.5, bevelSegments: 1 });
      g.rotateX(-Math.PI / 2);
      const m = new THREE.Mesh(g, plastic(col, { rough: 0.62 })); m.castShadow = true; m.receiveShadow = true; root.add(m);
      const line = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(poly.map(([x, z]) => new THREE.Vector3(x, (hl ? 4.8 : 3.6), z))), new THREE.LineBasicMaterial({ color: 0x5a5040, transparent: true, opacity: 0.55 }));
      root.add(line);
    }
  });
  const pins = (scene.map.pins || []).map((p) => {
    const [x, z] = P.toXZ(p.lon, p.lat), g = new THREE.Group(); g.position.set(x, 4, z);
    g.add(new THREE.Mesh(cyl(0.6, 0.6, 9, 8), plastic('#f2efe6')).translateY(4.5));
    const head = new THREE.Mesh(rbox(5, 5, 5, 1.2), plastic('#c8432f', { rough: 0.4 })); head.position.y = 11; head.castShadow = true; g.add(head);
    g.add(new THREE.Mesh(cyl(1.2, 1.2, 0.8, 12), plastic('#f2efe6', { rough: 0.4 })).translateY(14));
    g.scale.setScalar(0.001); root.add(g);
    return { ...p, obj: g, x, z };
  });
  const arrows = (scene.map.arrows || []).map((a) => {
    const [x0, z0] = P.toXZ(...a.from), [x1, z1] = P.toXZ(...a.to), L = Math.hypot(x1 - x0, z1 - z0);
    const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(x0, 6, z0), new THREE.Vector3((x0 + x1) / 2, 6 + L * 0.25, (z0 + z1) / 2), new THREE.Vector3(x1, 6, z1));
    const tube = new THREE.TubeGeometry(curve, 64, 1.6, 8, false), mesh = new THREE.Mesh(tube, plastic('#c8432f', { rough: 0.45 })); mesh.castShadow = true;
    const head = new THREE.Mesh(cone(4, 9, 10), plastic('#c8432f', { rough: 0.45 })); head.castShadow = true;
    root.add(mesh, head);
    return { ...a, mesh, head, curve, count: tube.index.count };
  });
  root.userData.animate = (t) => {
    for (const p of pins) { const k = Math.max(0, Math.min(1, (t - p.t) / 0.45)); const s = k <= 0 ? 0.001 : 1 + Math.sin(k * Math.PI) * 0.3 * (1 - k) ; p.obj.scale.setScalar(Math.max(0.001, k * s * 1.1)); p.obj.rotation.y = t * 0.6; }
    for (const a of arrows) {
      const k = Math.max(0, Math.min(1, (t - a.t0) / (a.t1 - a.t0))), e = k * k * (3 - 2 * k);
      a.mesh.geometry.setDrawRange(0, Math.floor(a.count * e / 6) * 6); a.mesh.visible = e > 0.01; a.head.visible = e > 0.01;
      const p = a.curve.getPoint(Math.max(0.001, e)), q = a.curve.getPoint(Math.min(1, Math.max(0.002, e) + 0.001));
      a.head.position.copy(p); a.head.lookAt(q); a.head.rotateX(Math.PI / 2);
    }
  };
  root.userData.labels = (t) => pins.filter((p) => t > p.t + 0.25).map((p) => ({ text: p.name.toUpperCase(), world: [p.x, 20, p.z] }));
  root.userData.proj = P;
  return root;
}
