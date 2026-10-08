// SPACECRAFT: any craft, from data. Where it is comes from a trajectory (or a fixed position); what it looks like comes
// from an optional 3D model file or, as the fallback, procedural PARTS (cylinders, cones, nozzles, boxes, panels, dishes,
// legs) -- so Apollo, Voyager, New Horizons, Chandrayaan or a made-up probe are each a parts list, not renderer code.
//   { "type": "spacecraft", "id": "csm", "label": "COLUMBIA", "trajectory": "apollo11_csm",
//     "position": { "anchor": "moon", "km": [0, 0, 1900] },            instead of a trajectory: a fixed point
//     "orientation": "prograde" | "radial" | "fixed",                   +Z along the motion / +Z away from the body
//     "model": "csm.glb",                                               optional; parts are used if absent or it fails
//     "parts": [ { "shape": "cylinder", "radius_m": 2, "length_m": 7.5, "at_m": 0, "color": "#c9ccd1" }, ... ],
//     "min_px": 24,            real size is a few metres: shown at least this big (a documentary convention, not scale)
//     "show": "flying" | "always", "label_side": "r",
//     "motion": { "t0": 12, "t1": 20, "from_utc": "...", "to_utc": "..." },   optional: carried along by narration, not the clock
//     "burns": [ { "from_utc": "...", "to_utc": "..." } ] }               optional: an engine burn glows on the craft then
// Model axes: +Z forward (the nose), +Y up; parts are placed along Z by at_m.
import { motionWhen } from '../lib/timing.mjs';

const RAD = Math.PI / 180;

function buildParts(THREE, parts) {
  const group = new THREE.Group();
  const mat = (p) => new THREE.MeshStandardMaterial({ color: p.color || '#c9ccd1', metalness: p.metalness ?? 0.35, roughness: p.roughness ?? 0.5, side: p.shape === 'nozzle' || p.shape === 'dish' ? THREE.DoubleSide : THREE.FrontSide, emissive: p.emissive || '#000000' });
  for (const p of parts) {
    let geo, z = (p.at_m || 0) + (p.length_m || 0) / 2;
    const len = p.length_m || 1;
    if (p.shape === 'cylinder') geo = new THREE.CylinderGeometry(p.radius_m, p.radius_m, len, 32).rotateX(Math.PI / 2);
    else if (p.shape === 'cone') geo = new THREE.CylinderGeometry(p.radius_top_m ?? 0.05, p.radius_m, len, 32).rotateX(Math.PI / 2);
    else if (p.shape === 'nozzle') geo = new THREE.CylinderGeometry(p.radius_top_m ?? p.radius_m * 0.45, p.radius_m, len, 32, 1, true).rotateX(Math.PI / 2);
    else if (p.shape === 'box') { const [x, y, zz] = p.size_m || [1, 1, 1]; geo = new THREE.BoxGeometry(x, y, zz); z = (p.at_m || 0) + zz / 2; }
    else if (p.shape === 'sphere') geo = new THREE.SphereGeometry(p.radius_m, 24, 16);
    else if (p.shape === 'dish') { geo = new THREE.SphereGeometry(p.radius_m * 1.6, 32, 8, 0, Math.PI * 2, 0, 0.67).rotateX(-Math.PI / 2); z = p.at_m || 0; }
    else if (p.shape === 'panel') {
      // a pair of flat wings either side of the body (span = one wing's length)
      const g2 = new THREE.Group(), w = p.width_m || 1, span = p.span_m || 4, gap = p.gap_m || 1;
      for (const s of [-1, 1]) { const m = new THREE.Mesh(new THREE.BoxGeometry(span, 0.05, w), mat(p)); m.position.set(s * (gap + span / 2), 0, (p.at_m || 0) + w / 2); g2.add(m); }
      if (p.rotate_deg) g2.rotation.set(...p.rotate_deg.map((a) => a * RAD));
      group.add(g2); continue;
    } else if (p.shape === 'legs') {
      const g2 = new THREE.Group(), n = p.count || 4, r = p.radius_m || 2, L = p.length_m || 2;
      for (let k = 0; k < n; k++) {
        const a = (k / n) * Math.PI * 2 + (p.phase_deg || 45) * RAD, splay = (p.splay_deg ?? 30) * RAD;
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(p.thickness_m || 0.08, p.thickness_m || 0.08, L, 8), mat(p));
        const foot = new THREE.Mesh(new THREE.CylinderGeometry(p.foot_m || 0.45, p.foot_m || 0.45, 0.08, 16), mat(p));
        const dir = new THREE.Vector3(Math.cos(a) * Math.sin(splay), Math.sin(a) * Math.sin(splay), -Math.cos(splay));
        const top = new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, p.at_m || 0);
        leg.position.copy(top).addScaledVector(dir, L / 2); leg.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        foot.position.copy(top).addScaledVector(dir, L); foot.rotation.x = Math.PI / 2;
        g2.add(leg, foot);
      }
      group.add(g2); continue;
    } else throw new Error(`spacecraft part: unknown shape "${p.shape}"`);
    const m = new THREE.Mesh(geo, mat(p));
    m.position.set(...(p.offset_m || [0, 0, 0])); m.position.z += z;
    if (p.rotate_deg) m.rotation.set(...p.rotate_deg.map((a) => a * RAD));
    group.add(m);
  }
  return group;
}

const DEFAULT_PARTS = [   // a generic capsule when a craft has neither a model nor parts
  { shape: 'cylinder', radius_m: 1.5, length_m: 4, at_m: 0, color: '#c9ccd1' },
  { shape: 'cone', radius_m: 1.5, radius_top_m: 0.3, length_m: 2, at_m: 4, color: '#e2e3e6' },
];

export default {
  type: 'spacecraft',
  space: 'world',
  async create(def, ctx) {
    const { THREE } = ctx;
    if (!def.trajectory && !def.position) throw new Error(`spacecraft ${def.id || ''}: needs a "trajectory" or a "position"`);
    let model = null;
    if (def.model) {
      try { model = (await ctx.loadModel(def.model)); } catch (e) { console.warn(`spacecraft ${def.id}: model ${def.model} failed (${e.message}); using parts`); }
    }
    if (!model) model = buildParts(THREE, def.parts || DEFAULT_PARTS);
    const box = new THREE.Box3().setFromObject(model), size = box.getSize(new THREE.Vector3());
    const lengthM = def.size_m || Math.max(size.x, size.y, size.z) || 10;
    const holder = new THREE.Group(); holder.add(model); holder.visible = false; ctx.scene.add(holder);
    const mats = []; model.traverse((o) => { if (o.material) mats.push(o.material); });
    return { def, ctx, holder, lengthM, mats, rel: null, onScreen: false };
  },
  /** Where the craft is (frame + position + direction), for this frame's date; null when it is not flying. */
  state(inst, f) {
    const d = inst.def;
    if (d.position) {
      const local = d.position.km || f.world.surfaceOffset(d.position.anchor, d.position.lon, d.position.lat, d.position.alt_km || 0);
      return { frame: d.position.anchor, position: local, direction: null };
    }
    const traj = inst.ctx.layer(d.trajectory).traj, st = traj.at(d.motion ? motionWhen(d.motion, f.t, f.mu) : f.date);
    if (st.phase === 'before' && d.show !== 'always') return null;
    if (st.phase === 'after' && d.after === 'hide') return null;
    return { frame: traj.frame, ...st };
  },
  locate: (inst) => inst.rel,
  update(inst, f) {
    const st = f.alpha > 0.002 ? this.state(inst, f) : null;
    inst.rel = null; inst.holder.visible = false;
    if (!st) return;
    const p = f.toCam(st.frame, st.position), dist = Math.hypot(...p);
    inst.rel = p;
    // true size in km, or at least min_px on screen (and at most max_px)
    const realKm = inst.lengthM / 1000, px = (realKm / dist) * f.focalPx;
    let k = Math.max(1, (inst.def.min_px ?? 24) / px);
    if (inst.def.max_px) k = Math.min(k, Math.max(1, inst.def.max_px / px));
    inst.holder.scale.setScalar(0.001 * k);             // parts are in metres, the scene in km
    inst.holder.position.set(p[0], p[1], p[2]);
    const centre = f.toCam(st.frame, [0, 0, 0]);
    const radial = [p[0] - centre[0], p[1] - centre[1], p[2] - centre[2]];
    const T = f.THREE, mode = inst.def.orientation || 'prograde';
    if (mode === 'prograde' && st.direction) {
      inst.holder.up.set(...radial).normalize();
      inst.holder.lookAt(new T.Vector3(p[0] + st.direction[0], p[1] + st.direction[1], p[2] + st.direction[2]));
    } else if (mode === 'radial') {
      if (st.direction) inst.holder.up.set(...st.direction).normalize();
      inst.holder.lookAt(new T.Vector3(p[0] + radial[0], p[1] + radial[1], p[2] + radial[2]));
    }
    for (const m of inst.mats) { m.transparent = f.alpha < 0.999; m.opacity = f.alpha; }
    inst.holder.visible = true;
    inst.screenR = Math.max(px * k, 4) / 2;
  },
  draw(inst, f) {
    if (!inst.rel) return;
    const s = f.project(inst.rel);
    if (!s.front || f.hidden(inst.rel)) return;
    const when = +(inst.def.motion ? motionWhen(inst.def.motion, f.t, f.mu) : f.date);
    if ((inst.def.burns || []).some((b) => when >= Date.parse(b.from_utc) && when <= Date.parse(b.to_utc))) {
      // an engine burn: a warm pulsing glow on the craft (generic: any craft, any manoeuvre the data names)
      const g = f.g, r = (inst.screenR + 16 * f.u.S) * (1 + 0.15 * Math.sin(f.t * 12)), grd = g.createRadialGradient(s.x, s.y, 0, s.x, s.y, r);
      grd.addColorStop(0, 'rgba(255,240,200,0.95)'); grd.addColorStop(0.35, 'rgba(255,170,60,0.7)'); grd.addColorStop(1, 'rgba(255,120,30,0)');
      g.save(); g.globalAlpha = f.alpha; g.fillStyle = grd; g.beginPath(); g.arc(s.x, s.y, r, 0, Math.PI * 2); g.fill(); g.restore();
    }
    if (!inst.def.label) return;
    const { u, g } = f, left = inst.def.label_side === 'l', w = u.measure(inst.def.label, 24) + 28 * u.S;
    const x = left ? s.x - inst.screenR - 18 * u.S - w : s.x + inst.screenR + 18 * u.S;
    f.claim(s.x - inst.screenR, s.y - inst.screenR, 2 * inst.screenR, 2 * inst.screenR);
    const y = f.place(x, s.y - 23 * u.S, w, 46 * u.S);
    g.save(); g.globalAlpha = f.alpha;
    u.chip(x, y, inst.def.label, 24, { bg: inst.def.label_bg || '#FBE040', h: 46 });
    g.restore();
  },
};
