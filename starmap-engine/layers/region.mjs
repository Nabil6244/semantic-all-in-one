// REGION_FILL: an area on any body's surface (a landing zone, a mare, a country, a geological unit): a translucent fill
// that turns with the body and is lit by the real Sun (a faint floor keeps it readable at night without hiding the
// terminator), plus an outline on the overlay.
//   { "type": "region", "body": "moon", "geometry": { "circle": { "lon": 23.47, "lat": 0.67, "radius_km": 60 } },
//     "style": { "fill": "#FBE040", "fill_opacity": 0.28, "stroke": "#FBE040", "stroke_width": 4, "dash": [14, 10] },
//     "label": "LANDING ZONE", "reveal": { "t0": 30, "t1": 32 }, "start": 29, "end": 40 }
import { regionOutline, regionCentre } from '../lib/surface.mjs';
import { surfaceDir } from '../lib/world.mjs';
import { progressAt } from '../lib/timing.mjs';
import { runs } from './ui.mjs';

const LIFT = 1.0006;     // the fill floats this fraction of the radius above the sphere (no z-fighting at any distance)

function fillGeometry(THREE, ring, maxDeg = 0.6) {
  // triangulate in lon/lat (unwrapped around the first point), split every triangle until its edges are short, then lift
  // each vertex onto the sphere: large regions follow the curvature instead of cutting through the body
  const lon0 = ring[0][0];
  const flat = ring.map(([lo, la]) => new THREE.Vector2(((lo - lon0 + 540) % 360) - 180 + lon0, la));
  const tris = THREE.ShapeUtils.triangulateShape(flat, []);
  const pos = [];
  const emit = (a, b, c, depth) => {
    const e = Math.max(a.distanceTo(b), b.distanceTo(c), c.distanceTo(a));
    if (e > maxDeg && depth < 8) {
      const ab = a.clone().lerp(b, 0.5), bc = b.clone().lerp(c, 0.5), ca = c.clone().lerp(a, 0.5);
      emit(a, ab, ca, depth + 1); emit(ab, b, bc, depth + 1); emit(ca, bc, c, depth + 1); emit(ab, bc, ca, depth + 1);
      return;
    }
    for (const v of [a, b, c]) pos.push(...surfaceDir(v.x, v.y, 0).map((k) => k * LIFT));
  };
  for (const [i, j, k] of tris) emit(flat[i], flat[j], flat[k], 0);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.computeVertexNormals();
  return geo;
}

export default {
  type: 'region',
  space: 'world',
  create(def, ctx) {
    const { THREE, world } = ctx;
    const body = world.get(def.body);
    if (!body) throw new Error(`region: unknown body ${def.body}`);
    const ring = regionOutline(def.geometry || {}, body.radiusKm);
    const st = def.style || {};
    const color = new THREE.Color(st.fill || '#FBE040');
    const mat = new THREE.MeshLambertMaterial({ color, emissive: color.clone().multiplyScalar(0.18), transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(fillGeometry(THREE, ring), mat);
    mesh.renderOrder = 2; mesh.visible = false;
    ctx.bodyMesh(def.body).add(mesh);             // a child of the body: it turns with the surface
    return { def, ring, mesh, centre: regionCentre(ring) };
  },
  update(inst, f) {
    const st = inst.def.style || {};
    const k = progressAt(inst.def.reveal, f.t);
    inst.mesh.material.opacity = (st.fill_opacity ?? 0.28) * f.alpha * k;
    inst.mesh.visible = inst.mesh.material.opacity > 0.003;
  },
  draw(inst, f) {
    const d = inst.def, st = d.style || {};
    const pts = inst.ring.concat([inst.ring[0]]);
    const k = progressAt(d.reveal, f.t), n = Math.max(2, Math.ceil(pts.length * k));
    const proj = pts.slice(0, n).map(([lo, la]) => {
      const p = f.toCam(d.body, f.world.surfaceOffset(d.body, lo, la, 0));
      const s = f.project(p);
      return { x: s.x, y: s.y, ok: s.front && !f.hidden(p) };
    });
    if (st.stroke !== 'none') for (const r of runs(proj)) f.u.line(r, { color: st.stroke || st.fill || '#FBE040', width: st.stroke_width ?? 4, dash: st.dash || null, alpha: f.alpha, glow: 6 });
    if (d.label && k > 0.6) {
      // under the region (its lowest visible outline point), so the area itself and any marker inside stay clear
      const vis = proj.filter((p) => p.ok);
      if (vis.length) {
        const cx = vis.reduce((a, p) => a + p.x, 0) / vis.length, by = Math.max(...vis.map((p) => p.y));
        const w = f.u.measure(d.label, 22) + 24 * f.u.S, h = 40 * f.u.S;
        f.g.save(); f.g.globalAlpha = f.alpha * Math.min(1, (k - 0.6) / 0.4);
        f.u.chip(cx - w / 2, f.place(cx - w / 2, by + 10 * f.u.S, w, h), d.label, 22, { bg: st.label_bg || '#FBE040', padX: 12, h: 40 });
        f.g.restore();
      }
    }
  },
};
