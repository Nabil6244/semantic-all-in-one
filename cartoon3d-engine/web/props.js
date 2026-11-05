// Toy props for lessons, built once from primitives (no downloads). Each fits a ~0.2 unit box centred on its origin.
// buildProp(kind, color?) -> THREE.Group. PROP_KINDS lists what the planner accepts.
import * as THREE from '/three/three.module.min.js';
import { part, toonMat } from './toon.js';

const SPH = new THREE.SphereGeometry(1, 28, 18), BOX = new THREE.BoxGeometry(1, 1, 1), CYL = new THREE.CylinderGeometry(1, 1, 1, 20), CONE = new THREE.ConeGeometry(1, 1, 20);
const O = { outline: 0.05 };
const add = (g, m, x = 0, y = 0, z = 0) => { m.position.set(x, y, z); g.add(m); return m; };
const sph = (c, sx, sy = sx, sz = sx, o = O) => { const m = part(SPH, c, o); m.scale.set(sx, sy, sz); return m; };

function shapeMesh(shape, color, depth = 0.04) {
  const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: 0.012, bevelSize: 0.01, bevelSegments: 3, curveSegments: 16 });
  geo.center(); return part(geo, color, { outline: 0.04 });
}
function starShape(r1 = 0.11, r0 = 0.05) {
  const s = new THREE.Shape();
  for (let k = 0; k < 10; k++) { const a = Math.PI / 2 + k * Math.PI / 5, r = k % 2 ? r0 : r1; const x = Math.cos(a) * r, y = Math.sin(a) * r; k ? s.lineTo(x, y) : s.moveTo(x, y); }
  s.closePath(); return s;
}
function heartShape(k = 0.011) {
  const s = new THREE.Shape(); s.moveTo(0, -9 * k);
  s.bezierCurveTo(-2 * k, -6 * k, -10 * k, -2 * k, -10 * k, 3 * k); s.bezierCurveTo(-10 * k, 8 * k, -4 * k, 10 * k, 0, 5 * k);
  s.bezierCurveTo(4 * k, 10 * k, 10 * k, 8 * k, 10 * k, 3 * k); s.bezierCurveTo(10 * k, -2 * k, 2 * k, -6 * k, 0, -9 * k); return s;
}

const BUILD = {
  ball: (c = '#ff5252') => { const g = new THREE.Group(); add(g, sph(c, 0.1)); const band = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.018, 10, 32), toonMat('#ffffff')); band.rotation.set(0.4, 0.3, 0); g.add(band); const b2 = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.012, 10, 32), toonMat('#ffd43b')); b2.rotation.set(-0.6, 1.2, 0); g.add(b2); return g; },
  apple: (c = '#e53935') => { const g = new THREE.Group(); add(g, sph(c, 0.1, 0.092, 0.1)); const st = part(CYL, '#6d4c41', { outline: 0 }); st.scale.set(0.008, 0.05, 0.008); add(g, st, 0, 0.1, 0).rotation.z = -0.25; const leaf = sph('#43a047', 0.035, 0.014, 0.02, { outline: 0.08 }); add(g, leaf, 0.03, 0.115, 0).rotation.z = 0.5; return g; },
  star: (c = '#ffd43b') => { const g = new THREE.Group(); add(g, shapeMesh(starShape(), c)); return g; },
  heart: (c = '#ff4d8d') => { const g = new THREE.Group(); add(g, shapeMesh(heartShape(), c, 0.05)); return g; },
  block: (c = '#42a5f5') => { const g = new THREE.Group(); const b = part(BOX, c, { outline: 0.04 }); b.scale.setScalar(0.16); add(g, b).rotation.set(0.3, 0.6, 0); return g; },
  balloon: (c = '#ab47bc') => { const g = new THREE.Group(); add(g, sph(c, 0.085, 0.105, 0.085), 0, 0.03, 0); const k = part(CONE, c, { outline: 0.05 }); k.scale.set(0.016, 0.02, 0.016); add(g, k, 0, -0.08, 0).rotation.x = Math.PI; const s = part(CYL, '#9e9e9e', { outline: 0 }); s.scale.set(0.002, 0.09, 0.002); add(g, s, 0, -0.135, 0); const hi = sph('#ffffff', 0.016, 0.026, 0.01, { outline: 0 }); add(g, hi, -0.035, 0.07, 0.07); return g; },
  duck: (c = '#ffd43b') => { const g = new THREE.Group(); add(g, sph(c, 0.1, 0.075, 0.08), 0, -0.03, 0); add(g, sph(c, 0.055), 0.055, 0.06, 0); const beak = sph('#ff8f00', 0.03, 0.012, 0.022, { outline: 0.08 }); add(g, beak, 0.11, 0.05, 0); for (const z of [-0.03, 0.03]) add(g, sph('#222222', 0.009, 0.012, 0.009, { outline: 0 }), 0.085, 0.075, z); const tail = sph(c, 0.035, 0.02, 0.03); add(g, tail, -0.1, 0.0, 0).rotation.z = 0.6; g.rotation.y = -0.6; return g; },
  car: (c = '#ef5350') => { const g = new THREE.Group(); const b = part(BOX, c, { outline: 0.03 }); b.scale.set(0.22, 0.06, 0.11); add(g, b, 0, -0.01, 0); const cab = part(BOX, c, { outline: 0.03 }); cab.scale.set(0.11, 0.06, 0.1); add(g, cab, -0.01, 0.05, 0); for (const sx of [-1, 1]) { const w = part(BOX, '#bbdefb', { outline: 0 }); w.scale.set(0.045, 0.04, 0.102); add(g, w, -0.01 + sx * 0.027, 0.052, 0); } for (const x of [-0.07, 0.07]) for (const z of [-0.055, 0.055]) { const wh = part(CYL, '#333333', { outline: 0.05 }); wh.scale.set(0.035, 0.02, 0.035); add(g, wh, x, -0.045, z).rotation.x = Math.PI / 2; } g.rotation.y = -0.5; return g; },
  flower: (c = '#ff8fd0') => { const g = new THREE.Group(); const st = part(CYL, '#43a047', { outline: 0 }); st.scale.set(0.008, 0.12, 0.008); add(g, st, 0, -0.06, 0); for (let k = 0; k < 6; k++) { const a = k * Math.PI / 3, p = sph(c, 0.035, 0.035, 0.012, { outline: 0.08 }); add(g, p, Math.cos(a) * 0.045, 0.03 + Math.sin(a) * 0.045, 0); } add(g, sph('#ffd43b', 0.03, 0.03, 0.016, { outline: 0.08 }), 0, 0.03, 0.008); return g; },
  sun: (c = '#ffca28') => { const g = new THREE.Group(); add(g, sph(c, 0.07, 0.07, 0.03)); for (let k = 0; k < 10; k++) { const a = k * Math.PI / 5, r = part(CONE, '#ffb300', { outline: 0.06 }); r.scale.set(0.018, 0.04, 0.012); add(g, r, Math.cos(a) * 0.1, Math.sin(a) * 0.1, 0).rotation.z = a - Math.PI / 2; } for (const x of [-0.022, 0.022]) add(g, sph('#5d4037', 0.008, 0.011, 0.005, { outline: 0 }), x, 0.012, 0.03); const sm = new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.004, 6, 16, Math.PI), toonMat('#5d4037')); sm.rotation.z = Math.PI; add(g, sm, 0, -0.008, 0.03); return g; },
  fish: (c = '#ff9800') => { const g = new THREE.Group(); add(g, sph(c, 0.1, 0.065, 0.045)); const t = part(CONE, c, { outline: 0.05 }); t.scale.set(0.05, 0.06, 0.02); add(g, t, -0.115, 0, 0).rotation.z = Math.PI / 2; add(g, sph('#ffffff', 0.016, 0.016, 0.01, { outline: 0.1 }), 0.06, 0.018, 0.038); add(g, sph('#222222', 0.008, 0.008, 0.006, { outline: 0 }), 0.064, 0.018, 0.045); return g; },
  banana: (c = '#ffe066') => { const g = new THREE.Group(); const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(-0.1, 0.04, 0), new THREE.Vector3(0, -0.07, 0), new THREE.Vector3(0.1, 0.05, 0)); add(g, part(new THREE.TubeGeometry(curve, 24, 0.028, 12), c, { outline: 0.05 })); add(g, sph('#6d4c41', 0.01, 0.01, 0.01, { outline: 0 }), 0.1, 0.05, 0); return g; },
  cup: (c = '#4dd0e1') => { const g = new THREE.Group(); const b = part(new THREE.CylinderGeometry(1, 0.8, 1, 20), c, { outline: 0.04 }); b.scale.set(0.07, 0.13, 0.07); add(g, b); const h = new THREE.Mesh(new THREE.TorusGeometry(0.035, 0.01, 8, 16, Math.PI * 1.2), toonMat(c)); add(g, h, 0.075, 0.0, 0).rotation.z = -Math.PI * 0.6; return g; },
  // Shapes (flat, chunky, for shape lessons).
  circle: (c = '#339af0') => { const g = new THREE.Group(); const m = part(CYL, c, { outline: 0.04 }); m.scale.set(0.11, 0.04, 0.11); m.rotation.x = Math.PI / 2; add(g, m); return g; },
  square: (c = '#51cf66') => { const g = new THREE.Group(); const m = part(BOX, c, { outline: 0.04 }); m.scale.set(0.19, 0.19, 0.04); add(g, m); return g; },
  triangle: (c = '#ff922b') => { const g = new THREE.Group(); const t = new THREE.Shape(); t.moveTo(0, 0.11); t.lineTo(0.11, -0.08); t.lineTo(-0.11, -0.08); t.closePath(); add(g, shapeMesh(t, c)); return g; },
  // Animals: round, simple, friendly; each faces a little toward camera-left (toward the tutor).
  cat: (c = '#ffa94d') => animal(c, { ears: 'cat', snout: '#fff3e0', tail: true, whiskers: true }),
  dog: (c = '#c08552') => animal(c, { ears: 'dog', snout: '#f5e1c8', tail: true, nose: '#3b2a20' }),
  cow: (c = '#ffffff') => animal(c, { ears: 'cow', snout: '#ffb3c1', spots: '#343a40', horns: true }),
  pig: (c = '#ffa8c5') => animal(c, { ears: 'pig', snout: '#ff8fb1', nostrils: true }),
  sheep: (c = '#f8f9fa') => animal('#5c4b45', { ears: 'sheep', snout: '#7a655c', wool: c }),
  frog: (c = '#69db7c') => { const g = new THREE.Group(); add(g, sph(c, 0.11, 0.08, 0.09), 0, -0.02, 0); for (const sx of [-1, 1]) { add(g, sph(c, 0.04), sx * 0.055, 0.06, 0.02); add(g, sph('#ffffff', 0.028, 0.028, 0.02, { outline: 0.08 }), sx * 0.055, 0.07, 0.045); add(g, sph('#222222', 0.014, 0.014, 0.01, { outline: 0 }), sx * 0.055, 0.07, 0.064); add(g, sph(c, 0.045, 0.02, 0.05), sx * 0.08, -0.09, 0.03); } const m = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.006, 6, 20, Math.PI), toonMat('#2b8a3e')); m.rotation.z = Math.PI; add(g, m, 0, -0.005, 0.085); return g; },
  // Feeling face: a round face; the mood is passed as the colour name (happy, sad, surprised, angry, sleepy).
  face: (c = 'happy') => moodFace(c),
};

function animal(c, o) {
  const g = new THREE.Group();
  if (o.wool) { for (let k = 0; k < 7; k++) { const a = k * Math.PI * 2 / 7; add(g, sph(o.wool, 0.055, 0.055, 0.05, { outline: 0.05 }), Math.cos(a) * 0.075, -0.03 + Math.sin(a) * 0.05, -0.03); } }
  else add(g, sph(c, 0.1, 0.075, 0.075), 0, -0.05, -0.03);
  const head = new THREE.Group(); head.position.set(0, 0.05, 0.03); g.add(head);
  add(head, sph(c, 0.075, 0.07, 0.068));
  if (o.spots) { add(head, sph(o.spots, 0.03, 0.025, 0.02, { outline: 0 }), -0.04, 0.035, 0.05); add(g, sph(o.spots, 0.04, 0.03, 0.03, { outline: 0 }), 0.05, -0.03, 0.03); }
  if (o.wool) add(head, sph(o.wool, 0.06, 0.035, 0.05, { outline: 0.05 }), 0, 0.06, 0);
  const sn = sph(o.snout, 0.04, 0.03, 0.03, { outline: 0.06 }); add(head, sn, 0, -0.025, 0.055);
  if (o.nose) add(head, sph(o.nose, 0.014, 0.011, 0.01, { outline: 0 }), 0, -0.012, 0.085);
  if (o.nostrils) for (const sx of [-1, 1]) add(head, sph('#c2255c', 0.006, 0.009, 0.004, { outline: 0 }), sx * 0.013, -0.025, 0.085);
  for (const sx of [-1, 1]) { add(head, sph('#ffffff', 0.017, 0.02, 0.01, { outline: 0.08 }), sx * 0.03, 0.018, 0.058); add(head, sph('#222222', 0.009, 0.012, 0.006, { outline: 0 }), sx * 0.03, 0.016, 0.066); }
  const m = new THREE.Mesh(new THREE.TorusGeometry(0.014, 0.003, 6, 12, Math.PI), toonMat('#3b2a20')); m.rotation.z = Math.PI; add(head, m, 0, -0.035, 0.083);
  for (const sx of [-1, 1]) {
    if (o.ears === 'cat') { const e = part(CONE, c, { outline: 0.06 }); e.scale.set(0.025, 0.04, 0.012); add(head, e, sx * 0.045, 0.07, 0).rotation.z = -sx * 0.3; }
    else if (o.ears === 'dog') { const e = sph('#7a4f2b', 0.022, 0.045, 0.015); add(head, e, sx * 0.07, 0.01, 0).rotation.z = sx * 0.25; }
    else if (o.ears === 'cow' || o.ears === 'sheep') { const e = sph(c, 0.03, 0.014, 0.012); add(head, e, sx * 0.08, 0.035, 0).rotation.z = sx * 0.4; }
    else if (o.ears === 'pig') { const e = part(CONE, c, { outline: 0.06 }); e.scale.set(0.022, 0.03, 0.01); add(head, e, sx * 0.045, 0.065, 0.01).rotation.z = -sx * 0.5; }
    if (o.horns) { const h = part(CONE, '#f1e3c6', { outline: 0.06 }); h.scale.set(0.01, 0.025, 0.01); add(head, h, sx * 0.04, 0.075, -0.01).rotation.z = -sx * 0.4; }
    if (o.whiskers) for (const dy of [-0.004, 0.006]) { const w = part(CYL, '#5c4b45', { outline: 0 }); w.scale.set(0.0015, 0.04, 0.0015); add(head, w, sx * 0.055, -0.025 + dy, 0.07).rotation.z = Math.PI / 2 + sx * dy * 20; }
    add(g, part(CYL, o.wool ? '#5c4b45' : c, { outline: 0.05 }), sx * 0.05, -0.12, 0.01).scale.set(0.018, 0.04, 0.018);
  }
  if (o.tail) { const t = part(CYL, c, { outline: 0.05 }); t.scale.set(0.01, 0.07, 0.01); add(g, t, -0.1, -0.02, -0.06).rotation.z = 0.8; }
  g.rotation.y = -0.35;
  return g;
}

const MOODS = { happy: ['#ffd43b', 0, 1], sad: ['#74c0fc', 0, -1], surprised: ['#ffa94d', 1, 0], angry: ['#ff6b6b', 0, -0.4], sleepy: ['#b197fc', 2, 0.3] };
function moodFace(mood) {
  const [c, mouthType, curve] = MOODS[mood] || MOODS.happy, g = new THREE.Group();
  add(g, sph(c, 0.11, 0.11, 0.06));
  for (const sx of [-1, 1]) {
    if (mouthType === 2) { const lid = new THREE.Mesh(new THREE.TorusGeometry(0.014, 0.004, 6, 12, Math.PI), toonMat('#3b2a20')); lid.rotation.z = Math.PI; add(g, lid, sx * 0.035, 0.025, 0.057); }
    else add(g, sph('#3b2a20', 0.012, mouthType === 1 ? 0.02 : 0.016, 0.006, { outline: 0 }), sx * 0.035, 0.025, 0.058);
    if (mood === 'angry') { const b = sph('#3b2a20', 0.018, 0.004, 0.004, { outline: 0 }); add(g, b, sx * 0.035, 0.055, 0.055).rotation.z = sx * -0.5; }
    if (mood === 'sad') { const b = sph('#3b2a20', 0.016, 0.004, 0.004, { outline: 0 }); add(g, b, sx * 0.035, 0.052, 0.055).rotation.z = sx * 0.45; }
  }
  if (mouthType === 1) add(g, sph('#7a2633', 0.018, 0.024, 0.006, { outline: 0 }), 0, -0.04, 0.058);
  else { const m = new THREE.Mesh(new THREE.TorusGeometry(0.035, 0.0055, 6, 20, Math.PI * 0.9), toonMat('#3b2a20')); m.rotation.z = curve >= 0 ? Math.PI * 1.05 : Math.PI * 0.05; add(g, m, 0, curve >= 0 ? -0.02 : -0.06, 0.058); if (curve > 0 && curve < 0.5) m.scale.set(0.6, 0.4, 1); }
  if (mood === 'sad') add(g, sph('#74c0fc', 0.008, 0.013, 0.004, { outline: 0.1 }), 0.05, -0.0, 0.06);
  if (mood === 'sleepy') add(g, sph('#ffffff', 0.009, 0.009, 0.004, { outline: 0.1 }), 0.075, 0.08, 0.04);
  return g;
}

export const PROP_KINDS = Object.keys(BUILD);
export const COLORS = { red: '#f03e3e', blue: '#339af0', yellow: '#ffd43b', green: '#51cf66', orange: '#ff922b', purple: '#9775fa', pink: '#f783ac', white: '#f8f9fa', black: '#343a40', brown: '#a0703a' };
export function buildProp(kind, color) { const f = BUILD[kind] || BUILD.ball; if (kind === 'face') return f(color || 'happy'); return f(color ? (COLORS[color] || color) : undefined); }
