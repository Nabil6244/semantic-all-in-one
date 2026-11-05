// Builds the 3D set from a world description (lib/world.mjs). Terrain is one vertex-coloured mesh; trees, hedges and props
// are instanced (one draw per part type, however many there are); buildings share geometries and facade textures.
import * as THREE from '/three/three.module.min.js';
import { Reflector } from 'three/addons/objects/Reflector.js';
import { plastic, rbox, box, cyl, sphere, cone, geo, studTexture, facadeTexture, grainTexture, stats } from './gfx.js';
import { distToPolyline, SIZE } from '../lib/world.mjs';
import { makeRng, fbm2 } from '../lib/rng.mjs';
import { buildVehicle } from './vehicle.js';

const C = (hex) => new THREE.Color(hex);
const GROUND = {
  grass: ['#6f9a45', '#5f8a3c', '#7da64e'], paved: ['#8f8a80', '#9a958a', '#85817a'], dirt: ['#8a7553', '#7d6a4a', '#93805c'], sand: ['#d9c38f', '#cfb77f', '#e2cc98'],
  mud: ['#5e5140', '#544838', '#6a5b47'], jungle: ['#3f7a35', '#356e2e', '#4a8a3a'], floor: ['#6b4a32', '#6b4a32', '#6b4a32'],
};
const ROAD = { dirt: '#8f7a58', cobble: '#7d7870', boulevard: '#5c5d60', street: '#66676a', trail: '#7a6448', sand_road: '#c8ad78', runway: '#55575a', taxiway: '#5d5f62', rail: '#5a4a3a' };

export function buildWorld(W, look) {
  const root = new THREE.Group(), night = look.night;
  root.add(terrain(W, look));
  if (W.water) root.add(water(W, look));
  if (W.env !== 'interior') root.add(farGround(W, look));
  for (const r of W.roads) if (['boulevard', 'street', 'runway', 'taxiway', 'cobble'].includes(r.kind)) root.add(roadRibbon(W, r));
  root.add(hedges(W));
  root.add(trees(W));
  for (const b of W.buildings) root.add(building(b, night));
  root.add(props(W, night));
  if (W.interior) root.add(interior(W, look));
  return root;
}

function terrain(W, look) {
  if (W.env === 'interior') return new THREE.Group();
  const seg = 220, g = new THREE.PlaneGeometry(SIZE * 2, SIZE * 2, seg, seg); g.rotateX(-Math.PI / 2);
  const pos = g.attributes.position, col = new Float32Array(pos.count * 3), n = fbm2(`gcol:${W.seed}`, 3), c = new THREE.Color();
  const pal = GROUND[W.ground] || GROUND.grass;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i), h = W.heightAt(x, z); pos.setY(i, h);
    const v = n(x / 40, z / 40) * 0.5 + 0.5;
    c.set(pal[0]).lerp(C(pal[v > 0.5 ? 2 : 1]), Math.abs(v - 0.5) * 2);
    const surf = W.surfaceAt(x, z), slope = W.slopeAt(x, z);
    if (surf === 'sand' || (W.water && h < 1.2 && h > -3)) c.set(h < 0.25 ? '#b9a479' : pal === GROUND.sand ? pal[1] : '#d6c08c').offsetHSL(0, 0, (v - 0.5) * 0.06);
    if (W.water && h < -0.2) c.lerp(C('#6d7d6a'), Math.min(1, -h / 4));
    for (const f of W.fields) { const dx = x - f.x, dz = z - f.z, cr = Math.cos(f.rot), sr = Math.sin(f.rot), lx = dx * cr - dz * sr, lz = dx * sr + dz * cr; if (Math.abs(lx) < f.w / 2 && Math.abs(lz) < f.d / 2) { c.set(f.color); if (Math.floor((lx + 999) / 3) % 2) c.offsetHSL(0, 0, -0.035); } }
    for (const r of W.roads) { const d = distToPolyline(x, z, r.points); if (d < r.width / 2 + 1.5) c.lerp(C(ROAD[r.kind] || ROAD.dirt), d < r.width / 2 ? 0.92 : 0.4); }
    if (slope > 0.75 && surf !== 'road') c.lerp(C('#7d776d'), Math.min(1, (slope - 0.75) * 1.4));
    if (h > 40) c.lerp(C('#f2f4f6'), Math.min(1, (h - 40) / 10));
    for (const cr of W.craters) { const d = Math.hypot(x - cr.x, z - cr.z) / cr.r; if (d < 1.3) c.lerp(C('#4a3e30'), (1 - d / 1.3) * 0.85); }
    if (look.tint) c.lerp(C(look.tint), 0.18);
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
  }
  g.setAttribute('color', new THREE.BufferAttribute(col, 3)); g.computeVertexNormals();
  const grain = grainTexture(); grain.repeat.set(70, 70);
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, map: grain, flatShading: false });
  const mesh = new THREE.Mesh(g, m); mesh.receiveShadow = true; mesh.name = 'terrain';
  return mesh;
}

function farGround(W, look) {
  if (W.env === 'sea' || W.env === 'map') return new THREE.Group();
  const g = new THREE.RingGeometry(SIZE * 0.98, 9000, 64, 1); g.rotateX(-Math.PI / 2);
  const pal = GROUND[W.ground === 'paved' ? 'grass' : W.ground] || GROUND.grass;
  const m = new THREE.Mesh(g, plastic(pal[1], { rough: 1 })); m.position.y = W.env === 'beach' || W.env === 'port' || W.env === 'island' ? -30 : W.heightAt(SIZE, 0) - 0.6; m.receiveShadow = false;
  if (W.water) m.position.y = -30; // the sea covers it
  return m;
}

let waterTex = null;
function waterNormal() {
  if (waterTex) return waterTex;
  const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'), img = g.createImageData(256, 256), n = fbm2('water', 4);
  for (let y = 0; y < 256; y++) for (let x = 0; x < 256; x++) {
    const f = (a, b) => n(a / 18, b / 18) + n(a / 7 + 30, b / 7) * 0.3;
    const dx = f(x + 1, y) - f(x - 1, y), dy = f(x, y + 1) - f(x, y - 1), i = (y * 256 + x) * 4;
    img.data[i] = 128 + dx * 220; img.data[i + 1] = 128 + dy * 220; img.data[i + 2] = 255; img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0); waterTex = new THREE.CanvasTexture(c); waterTex.wrapS = waterTex.wrapT = THREE.RepeatWrapping; waterTex.repeat.set(60, 60); stats.textures++;
  return waterTex;
}
function water(W, look) {
  const g = new THREE.PlaneGeometry(W.water.kind === 'river' ? SIZE * 2 : 16000, W.water.kind === 'river' ? SIZE * 2 : 16000, 1, 1); g.rotateX(-Math.PI / 2);
  const m = new THREE.MeshStandardMaterial({ color: C(look.water || '#2f5f6a'), roughness: 0.12, metalness: 0.15, normalMap: waterNormal(), normalScale: new THREE.Vector2(0.55, 0.55), transparent: true, opacity: 0.93 });
  const mesh = new THREE.Mesh(g, m); mesh.position.y = W.water.level; mesh.receiveShadow = true; mesh.name = 'water'; mesh.userData.animate = (t) => { m.normalMap.offset.set(t * 0.004, t * 0.0065); };
  return mesh;
}

function roadRibbon(W, r) {
  const pts = r.points, verts = [], idx = [], uvs = [];
  let along = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, az] = pts[i], [bx, bz] = pts[i + 1], L = Math.hypot(bx - ax, bz - az), steps = Math.max(2, Math.ceil(L / 6));
    const nx = -(bz - az) / L, nz = (bx - ax) / L;
    for (let k = 0; k <= steps; k++) {
      if (k === 0 && i > 0) continue;
      const x = ax + (bx - ax) * k / steps, z = az + (bz - az) * k / steps;
      for (const s of [-1, 1]) { const px = x + nx * s * r.width / 2, pz = z + nz * s * r.width / 2; verts.push(px, Math.max(W.heightAt(px, pz), W.heightAt(x, z)) + 0.12, pz); uvs.push(s < 0 ? 0 : 1, along / r.width); }
      along += L / steps;
    }
  }
  for (let i = 0; i < verts.length / 6 - 1; i++) { const a = i * 2; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); g.setIndex(idx); g.computeVertexNormals();
  const tex = roadTexture(r.kind);
  const mesh = new THREE.Mesh(g, plastic('#ffffff', { map: tex, rough: 0.85 })); mesh.receiveShadow = true;
  return mesh;
}
const roadTex = new Map();
function roadTexture(kind) {
  if (roadTex.has(kind)) return roadTex.get(kind);
  const c = document.createElement('canvas'); c.width = 64; c.height = 256; const g = c.getContext('2d');
  g.fillStyle = ROAD[kind] || '#666'; g.fillRect(0, 0, 64, 256);
  if (kind === 'cobble') for (let y = 0; y < 256; y += 8) for (let x = (y / 8) % 2 ? 0 : 4; x < 64; x += 8) { g.fillStyle = `rgba(0,0,0,${0.06 + ((x * 7 + y * 3) % 5) * 0.02})`; g.fillRect(x, y, 7, 7); }
  if (kind === 'runway') { g.fillStyle = '#e8e8e8'; g.fillRect(30, 0, 4, 120); g.fillRect(2, 0, 3, 256); g.fillRect(59, 0, 3, 256); }
  if (kind === 'boulevard' || kind === 'street') { g.fillStyle = '#d9d3c4'; g.fillRect(0, 0, 4, 256); g.fillRect(60, 0, 4, 256); g.fillStyle = 'rgba(240,240,230,0.7)'; g.fillRect(31, 0, 2, 90); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; roadTex.set(kind, t); stats.textures++;
  return t;
}

// ---- instancing helper: one InstancedMesh per part (geometry + material + local transform) ------------------------------------
function instanced(parts, placements, { shadow = true, colorVar = 0 } = {}) {
  const g = new THREE.Group(); if (!placements.length) return g;
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), e = new THREE.Euler();
  for (const part of parts) {
    const im = new THREE.InstancedMesh(part.geo, part.mat, placements.length);
    placements.forEach((pl, i) => {
      e.set(pl.rx || 0, pl.rot || 0, pl.rz || 0); q.setFromEuler(e); s.set(pl.sx ?? pl.scale ?? 1, pl.sy ?? pl.scale ?? 1, pl.sz ?? pl.scale ?? 1); p.set(pl.x, pl.y, pl.z);
      m4.compose(p, q, s).multiply(part.local); im.setMatrixAt(i, m4);
      if (colorVar || pl.color) { const c = new THREE.Color(1, 1, 1); if (pl.color) { const t = C(pl.color), b = part.mat.color; c.set(b.r > 0.01 ? t.r / b.r : 1, b.g > 0.01 ? t.g / b.g : 1, b.b > 0.01 ? t.b / b.b : 1); } else c.multiplyScalar(1 + ((i * 0.618) % 1 - 0.5) * colorVar * 1.6); im.setColorAt(i, c); }
    });
    im.castShadow = shadow && part.shadow !== false; im.receiveShadow = true; im.instanceMatrix.needsUpdate = true; if (im.instanceColor) im.instanceColor.needsUpdate = true;
    g.add(im);
  }
  return g;
}
const part = (g, mat, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, sx = 1, sy = 1, sz = 1, shadow = true) => ({ geo: g, mat, local: new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), new THREE.Vector3(sx, sy, sz)), shadow });

const TREES = () => ({
  oak: [part(cyl(0.6, 0.8, 5, 7), plastic('#6b4b30')), part(rbox(7, 5, 7, 1.6), plastic('#4f7f35'), 0, 6.5, 0), part(rbox(5, 4, 5, 1.4), plastic('#5b8e3d'), 1.5, 9, -0.8)],
  plane: [part(cyl(0.5, 0.7, 6, 7), plastic('#7a6a55')), part(rbox(6, 5.5, 6, 1.8), plastic('#5c8a3e'), 0, 8, 0)],
  pine: [part(cyl(0.45, 0.6, 4, 6), plastic('#5e4630')), part(cone(4, 6, 8), plastic('#2f5e35'), 0, 5.5, 0), part(cone(3.2, 5, 8), plastic('#356a3b'), 0, 8.5, 0), part(cone(2.2, 4, 8), plastic('#3c7442'), 0, 11.2, 0)],
  poplar: [part(cyl(0.4, 0.5, 3, 6), plastic('#6b5a44')), part(rbox(3.2, 12, 3.2, 1.4), plastic('#557f3a'), 0, 8.5, 0)],
  birch: [part(cyl(0.35, 0.45, 8, 6), plastic('#e8e4da')), part(rbox(4.5, 5, 4.5, 1.6), plastic('#7aa24a'), 0, 9, 0)],
  palm: [part(cyl(0.45, 0.6, 10, 7), plastic('#8a6e4a'), 0, 5, 0, 0, 0, 0.12), ...[0, 1, 2, 3, 4, 5].map((k) => part(box(1.4, 0.3, 6), plastic('#3f8a3a'), Math.sin(k * 1.05) * 2.6 + 0.6, 10.2, Math.cos(k * 1.05) * 2.6, -0.35, k * 1.05, 0))],
  broadleaf: [part(cyl(0.7, 1, 9, 7), plastic('#5e4a34')), part(sphere(5.5, 10, 7), plastic('#2f6e2e'), 0, 11, 0, 0, 0, 0, 1, 0.6, 1), part(sphere(3.8, 9, 6), plastic('#3a7d33'), 2.5, 9, 1.5, 0, 0, 0, 1, 0.65, 1)],
  fern: [0, 1, 2, 3, 4].map((k) => part(box(0.8, 0.2, 3.2), plastic('#3c8a3c'), Math.sin(k * 1.25) * 1.2, 0.7, Math.cos(k * 1.25) * 1.2, -0.5, k * 1.25, 0)),
  bush: [part(rbox(3.4, 2.4, 3.4, 1), plastic('#4c7a34'), 0, 1.1, 0)],
  dead: [part(cyl(0.35, 0.55, 7, 5), plastic('#4a4038')), part(cyl(0.15, 0.2, 3, 4), plastic('#4a4038'), 0.8, 5.5, 0, 0, 0, -0.8), part(cyl(0.12, 0.18, 2.4, 4), plastic('#4a4038'), -0.7, 4.5, 0, 0, 0, 0.9)],
  rock: [part(rbox(3, 2, 2.6, 0.6), plastic('#8a8780'), 0, 0.6, 0, 0.1, 0.3, 0.05)],
});
let treeParts = null;
function trees(W) {
  treeParts = treeParts || TREES();
  const g = new THREE.Group(), by = {};
  for (const t of W.trees) (by[t.kind] = by[t.kind] || []).push({ x: t.x, y: t.y - 0.2, z: t.z, rot: t.rot, scale: t.scale });
  for (const [k, pl] of Object.entries(by)) if (treeParts[k]) g.add(instanced(treeParts[k], pl, { colorVar: 0.12 }));
  return g;
}
function hedges(W) {
  const pl = [];
  for (const h of W.hedges) for (let i = 1; i < h.points.length; i++) {
    const [ax, az] = h.points[i - 1], [bx, bz] = h.points[i], L = Math.hypot(bx - ax, bz - az), n = Math.ceil(L / 3);
    for (let k = 0; k <= n; k++) { const x = ax + (bx - ax) * k / n, z = az + (bz - az) * k / n; if (W.roads.some((r) => distToPolyline(x, z, r.points) < r.width / 2 + 2)) continue; pl.push({ x, y: W.heightAt(x, z), z, rot: Math.atan2(bx - ax, bz - az) + k * 0.7, scale: 0.85 + ((k * 7) % 5) * 0.07 }); }
  }
  return instanced([part(rbox(3.6, 3.8, 3.6, 1.2), plastic('#3f6b2e'), 0, 1.7, 0), part(rbox(2.4, 2, 2.4, 0.8), plastic('#4b7a34'), 0.6, 3.6, 0.3)], pl, { colorVar: 0.15 });
}

// ---- buildings -------------------------------------------------------------------------------------------------------------
function gableGeo(w, d, h) {
  return geo(`gable:${w}:${d}:${h}`, () => {
    const s = new THREE.Shape(); s.moveTo(-w / 2 - 0.6, 0); s.lineTo(0, h); s.lineTo(w / 2 + 0.6, 0); s.lineTo(-w / 2 - 0.6, 0);
    const g = new THREE.ExtrudeGeometry(s, { depth: d + 1.2, bevelEnabled: false }); g.translate(0, 0, -(d + 1.2) / 2); return g;
  });
}
function building(b, night) {
  const g = new THREE.Group(); g.position.set(b.x, b.y, b.z); g.rotation.y = b.rot || 0;
  const wallM = plastic('#ffffff', { map: facadeTexture(b.wall, Math.max(1, b.floors || 1), night, b.seed || 1, b.kind), rough: 0.85 });
  const roofM = plastic(b.roof, { rough: 0.75 });
  const add = (o) => { o.castShadow = true; o.receiveShadow = true; g.add(o); return o; };
  const H = b.h, dmg = b.damaged;
  const K = b.kind;
  if (K === 'stilt_house') {
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) add(new THREE.Mesh(cyl(0.35, 0.35, 3.2, 6), plastic('#6b5236'))).position.set(x * b.w * 0.42, 1.6, z * b.d * 0.42);
    add(new THREE.Mesh(box(b.w, 0.5, b.d), plastic('#7a5c3c'))).position.y = 3.2;
    add(new THREE.Mesh(box(b.w * 0.9, H - 3.4, b.d * 0.9), plastic('#b89a6a', { rough: 0.95 }))).position.y = 3.4 + (H - 3.4) / 2;
    const r = add(new THREE.Mesh(cyl(0.01, Math.max(b.w, b.d) * 0.82, 4.4, 4), plastic('#a08a5a', { rough: 1 }))); r.rotation.y = Math.PI / 4; r.scale.set(b.w / Math.max(b.w, b.d), 1, b.d / Math.max(b.w, b.d)); r.position.y = H + 2.2;
    return g;
  }
  if (K === 'hangar' || K === 'quonset') {
    const r = add(new THREE.Mesh(geo(`arch:${b.w}:${b.d}`, () => new THREE.CylinderGeometry(b.w / 2, b.w / 2, b.d, 20, 1, false, -Math.PI / 2, Math.PI)), plastic(b.wall, { rough: 0.6, metal: 0.3 })));
    r.rotation.z = Math.PI / 2; r.rotation.y = Math.PI / 2; r.position.y = 0; r.scale.set(1, 1, (H + (b.roofH || 0)) / (b.w / 2));
    add(new THREE.Mesh(box(b.w * 0.5, H * 0.8, 0.3), plastic('#3a3d38'))).position.set(0, H * 0.4, b.d / 2 + 0.1);
    return g;
  }
  if (K === 'church' || K === 'temple' || K === 'courthouse' || K === 'dome') {
    add(new THREE.Mesh(box(b.w, H, b.d), wallM)).position.y = H / 2;
    add(new THREE.Mesh(gableGeo(b.w, b.d, b.roofH || 6), roofM)).position.y = H;
    if (K === 'church') { add(new THREE.Mesh(box(6, H + 12, 6), wallM)).position.set(0, (H + 12) / 2, b.d / 2 + 2); add(new THREE.Mesh(cone(4.4, 12, 4), roofM)).position.set(0, H + 18, b.d / 2 + 2); g.children[g.children.length - 1].rotation.y = Math.PI / 4; }
    if (K === 'dome') add(new THREE.Mesh(sphere(b.w * 0.35, 16, 10, Math.PI * 2, Math.PI / 2), plastic('#c9b07a'))).position.y = H;
    return g;
  }
  const wallH = dmg ? H * 0.8 : H;
  add(new THREE.Mesh(box(b.w, wallH, b.d), dmg ? plastic('#ffffff', { map: facadeTexture('#8a8278', Math.max(1, b.floors || 1), false, b.seed || 1, b.kind), rough: 0.95 }) : wallM)).position.y = wallH / 2;
  add(new THREE.Mesh(box(b.w + 0.3, 0.6, b.d + 0.3), plastic('#6f6a60'))).position.y = 0.3;
  if (dmg) { for (let i = 0; i < 5; i++) add(new THREE.Mesh(rbox(2 + (i % 3), 1 + (i % 2), 2, 0.3), plastic('#7a746a'))).position.set((i - 2) * 2.2, 0.6, b.d / 2 + 1.5 + (i % 2)); return g; }
  if (b.roofType === 'gable') add(new THREE.Mesh(gableGeo(b.w, b.d, b.roofH), roofM)).position.y = H;
  else if (b.roofType === 'mansard') { const r = add(new THREE.Mesh(cyl(Math.max(b.w, b.d) * 0.48, Math.max(b.w, b.d) * 0.74, b.roofH, 4), roofM)); r.rotation.y = Math.PI / 4; r.scale.set(b.w / Math.max(b.w, b.d), 1, b.d / Math.max(b.w, b.d)); r.position.y = H + b.roofH / 2; }
  else if (b.roofType === 'sawtooth') for (let i = 0; i < 5; i++) { const s = add(new THREE.Mesh(gableGeo(b.d / 5, b.w, b.roofH), roofM)); s.rotation.y = Math.PI / 2; s.position.set(0, H, -b.d / 2 + b.d / 10 + i * b.d / 5); }
  else { const top = add(new THREE.Mesh(box(b.w + 0.4, 0.8, b.d + 0.4), plastic(b.roof, { map: studTexture(b.roof), rough: 0.7 }))); top.position.y = H + 0.4; top.material.map.repeat.set(b.w / 4, b.d / 4); }
  if (K === 'concrete_block' && !dmg) { add(new THREE.Mesh(cyl(1.3, 1.3, 2.4, 10), plastic('#2f3a40', { rough: 0.6 }))).position.set(b.w * 0.25, H + 1.8, -b.d * 0.2); add(new THREE.Mesh(box(b.w + 0.4, 1.1, 0.4), plastic(b.wall, { rough: 0.9 }))).position.set(0, H + 1.2, b.d / 2 + 0.1); }
  if (b.awning) add(new THREE.Mesh(box(b.w * 0.8, 0.3, 3), plastic(['#9a3b32', '#2f5d7a', '#3f6b3a'][b.seed % 3]))).position.set(0, 4.4, b.d / 2 + 1.5);
  if (b.shutters) for (const s of [-1, 1]) add(new THREE.Mesh(box(0.5, 2.6, 0.2), plastic('#4a6a5a'))).position.set(s * b.w * 0.36, H * 0.55, b.d / 2 + 0.12);
  return g;
}

// ---- props (instanced by kind) ---------------------------------------------------------------------------------------------
const PROPS = (night) => ({
  hedgehog: [part(box(0.5, 0.5, 5), plastic('#4a4642', { metal: 0.4, rough: 0.5 }), 0, 1.2, 0, 0.7, 0, 0), part(box(0.5, 0.5, 5), plastic('#4a4642', { metal: 0.4, rough: 0.5 }), 0, 1.2, 0, 0.7, 2.1, 0), part(box(0.5, 0.5, 5), plastic('#4a4642', { metal: 0.4, rough: 0.5 }), 0, 1.2, 0, 0.7, 4.2, 0)],
  stake: [part(cyl(0.25, 0.3, 5, 6), plastic('#5a4632'), 0, 1.8, 0, 0.6, 0, 0)],
  wire: [part(cyl(0.6, 0.6, 4, 6, 1), new THREE.MeshStandardMaterial({ color: 0x3a3a3a, wireframe: true }), 0, 0.6, 0, 0, 0, Math.PI / 2, 1, 1, 1, false)],
  bunker: [part(rbox(16, 6, 12, 1.2), plastic('#9a978d', { rough: 0.95 }), 0, 2.4, 0), part(box(9, 0.9, 0.5), plastic('#1a1a1a'), 0, 3.4, 6.05)],
  tent: [part(gableGeo(8, 12, 5), plastic('#6f6c4c', { rough: 1 }), 0, 0, 0)],
  crates: [part(box(2.4, 2.4, 2.4), plastic('#8a6a40', { map: studTexture('#8a6a40'), rough: 0.8 }), 0, 1.2, 0), part(box(2.4, 2.4, 2.4), plastic('#7a5e3a', { rough: 0.8 }), 2.6, 1.2, 0.3), part(box(2.4, 2.4, 2.4), plastic('#8a6a40', { rough: 0.8 }), 1.2, 3.6, 0.2)],
  barrel: [part(cyl(1, 1, 2.6, 12), plastic('#4d5a3a', { metal: 0.2, rough: 0.5 }), 0, 1.3, 0)],
  sandbags: [part(rbox(6, 1.2, 1.6, 0.5), plastic('#a8976d', { rough: 1 }), 0, 0.6, 0), part(rbox(5, 1.2, 1.6, 0.5), plastic('#9c8b62', { rough: 1 }), 0.4, 1.7, 0)],
  tower_watch: [...[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([x, z]) => part(cyl(0.3, 0.3, 14, 5), plastic('#6b5236'), x * 2.5, 7, z * 2.5)), part(box(7, 0.6, 7), plastic('#7a5c3c'), 0, 14, 0), part(cone(5.5, 3, 4), plastic('#5a4a3a'), 0, 17, 0, 0, Math.PI / 4)],
  fence: [part(cyl(0.2, 0.2, 3, 5), plastic('#6b5236'), 0, 1.5, 0), part(box(12, 0.25, 0.25), plastic('#6b5236'), 6, 2.2, 0), part(box(12, 0.25, 0.25), plastic('#6b5236'), 6, 1.0, 0)],
  flagpole: [part(cyl(0.15, 0.2, 18, 6), plastic('#cfcfcf', { metal: 0.6 }), 0, 9, 0), part(box(5, 3, 0.1), plastic('#7a6a4a', { side: 'double' }), 2.6, 16, 0)],
  lamp: [part(cyl(0.15, 0.25, 8, 6), plastic('#2a2a2a'), 0, 4, 0), part(rbox(0.9, 1.2, 0.9, 0.2), plastic(night ? '#ffd890' : '#e8e2cf', { emissive: night ? '#ffbf60' : null, emissiveIntensity: 2 }), 0, 8.4, 0)],
  kiosk: [part(cyl(1.6, 1.6, 6, 10), plastic('#3f5a3a'), 0, 3, 0), part(cone(2.2, 2, 10), plastic('#2f4a2a'), 0, 7, 0)],
  cart: [part(box(3, 1, 5), plastic('#7a5a3a', { rough: 0.9 }), 0, 1.6, 0), part(cyl(1.2, 1.2, 0.3, 10), plastic('#4a3a2a'), 1.7, 1.2, 0, 0, 0, Math.PI / 2), part(cyl(1.2, 1.2, 0.3, 10), plastic('#4a3a2a'), -1.7, 1.2, 0, 0, 0, Math.PI / 2)],
  well: [part(cyl(2, 2, 2, 12), plastic('#8a8478', { rough: 1 }), 0, 1, 0), part(box(0.3, 4, 0.3), plastic('#5a4632'), 1.8, 3, 0), part(box(0.3, 4, 0.3), plastic('#5a4632'), -1.8, 3, 0), part(gableGeo(4.4, 3, 1.4), plastic('#7a3b2e'), 0, 5, 0)],
  hay: [part(cyl(1.6, 1.6, 2.6, 12), plastic('#d2b86a', { rough: 1 }), 0, 1.6, 0, 0, 0, Math.PI / 2)],
  pier: [part(box(10, 1, 60), plastic('#7a5c3c', { map: studTexture('#7a5c3c'), rough: 0.8 }), 0, 1.6, 0), ...[-24, -8, 8, 24].flatMap((z) => [part(cyl(0.6, 0.6, 6, 6), plastic('#4a3a2a'), -4, -1, z), part(cyl(0.6, 0.6, 6, 6), plastic('#4a3a2a'), 4, -1, z)])],
  crane: [part(box(2, 30, 2), plastic('#9a7a3a'), 0, 15, 0), part(box(2, 2, 30), plastic('#9a7a3a'), 0, 30, 8), part(box(6, 4, 6), plastic('#7a5a2a'), 0, 2, 0)],
  warehouse: [],
  chimney: [part(cyl(1.6, 2.2, 30, 10), plastic('#8a4a36'), 0, 15, 0)],
  trench: [part(box(420, 0.4, 7), plastic('#3a3024', { rough: 1 }), 0, 0.15, 0, 0, 0, 0, 1, 1, 1, false), part(rbox(420, 1.4, 2, 0.5), plastic('#9c8b62', { rough: 1 }), 0, 0.6, -4.5)],
  arch: [part(box(10, 34, 12), plastic('#d8cfb8', { rough: 0.9 }), -14, 17, 0), part(box(10, 34, 12), plastic('#d8cfb8', { rough: 0.9 }), 14, 17, 0), part(box(38, 10, 12), plastic('#d8cfb8', { rough: 0.9 }), 0, 39, 0), part(box(40, 2, 13), plastic('#cbc2aa'), 0, 44.5, 0)],
  bridge: [part(box(10, 1.4, 80), plastic('#8a8478'), 0, 3, 0), part(box(3, 8, 3), plastic('#7a746a'), 0, -1, -14), part(box(3, 8, 3), plastic('#7a746a'), 0, -1, 14)],
  windsock: [part(cyl(0.12, 0.12, 9, 5), plastic('#ddd'), 0, 4.5, 0), part(cone(0.8, 4, 8), plastic('#e07a30'), 2, 8.6, 0, 0, 0, -Math.PI / 2)],
  table_map: [part(rbox(20, 0.6, 10, 0.2), plastic('#5a3b22', { rough: 0.5 }), 0, 3.2, 0), part(box(17, 0.06, 8), plastic('#c9c2a0', { map: mapPaper() }), 0, 3.53, 0), ...[[-9, -4], [9, -4], [-9, 4], [9, 4]].map(([x, z]) => part(box(0.6, 3.2, 0.6), plastic('#4a3020'), x, 1.6, z))],
  wall_map: [part(box(16, 9, 0.3), plastic('#d8cfae', { map: mapPaper() }), 0, 8, 0)],
  lamp_hang: [part(cyl(0.05, 0.05, 3, 4), plastic('#333'), 0, 12.5, 0), part(cone(1.6, 1.2, 12), plastic('#2f3a2f'), 0, 10.8, 0), part(sphere(0.5, 8, 6), plastic('#ffe0a0', { emissive: '#ffc070', emissiveIntensity: 3 }), 0, 10.2, 0, 0, 0, 0, 1, 1, 1, false)],
  bookcase: [part(box(8, 11, 2), plastic('#4a3020'), 0, 5.5, 0), ...[2, 5, 8].map((y) => part(box(7.4, 2.2, 1.6), plastic(['#7a2f2f', '#2f4a7a', '#5a5a2f'][y % 3]), 0, y, 0.1))],
  clock: [part(cyl(1.2, 1.2, 0.3, 16), plastic('#efe9d8'), 0, 10, 0, Math.PI / 2, 0, 0)],
  chair: [part(box(2.4, 0.4, 2.4), plastic('#5a3b22'), 0, 2, 0), part(box(2.4, 2.6, 0.3), plastic('#5a3b22'), 0, 3.3, -1.1), ...[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([x, z]) => part(box(0.3, 2, 0.3), plastic('#4a3020'), x, 1, z))],
  phone: [part(box(1, 0.5, 0.8), plastic('#151515', { rough: 0.3 }), 0, 0.25, 0)],
  mirror: [part(box(9, 8, 0.2), plastic('#2c2a28', { rough: 0.5 }), 0, 6.8, 0)],
  vanity: [part(rbox(10, 3, 3.6, 0.1), plastic('#e7e3da', { rough: 0.5 }), 0, 1.5, 0), part(box(10.4, 0.3, 4, 0), plastic('#cfcac0', { rough: 0.3 }), 0, 3.15, 0), part(cyl(1.5, 1.2, 0.2, 18), plastic('#8d9aa0', { rough: 0.25 }), 0, 3.32, 0.1), part(cyl(0.16, 0.16, 1.2, 8), plastic('#c8cdd0', { metal: 0.8, rough: 0.25 }), 0, 3.9, -1.3), part(box(0.25, 0.2, 1), plastic('#c8cdd0', { metal: 0.8, rough: 0.25 }), 0, 4.4, -0.9)],
  towel_rail: [part(box(5, 0.2, 0.2), plastic('#c8cdd0', { metal: 0.8, rough: 0.3 }), 0, 7, 0.3), part(box(3.6, 3.4, 0.25), plastic('#b5483a', { rough: 1 }), 0, 5.4, 0.42)],
  bathtub: [part(rbox(7, 3.2, 14, 0.4), plastic('#efece4', { rough: 0.35 }), 0, 1.6, 0), part(box(5.6, 0.1, 12.4), plastic('#a9c0c9', { rough: 0.15 }), 0, 3.22, 0)],
  toilet: [part(cyl(1.5, 1.1, 2.2, 16), plastic('#efece4', { rough: 0.3 }), 0, 1.1, 0.8), part(cyl(1.6, 1.6, 0.2, 16), plastic('#dedad0', { rough: 0.3 }), 0, 2.3, 0.8), part(rbox(3.4, 3.4, 1.4, 0.2), plastic('#efece4', { rough: 0.3 }), 0, 3.4, -1.2)],
  door: [part(box(6, 10.6, 0.3), plastic('#6e4a30', { rough: 0.7 }), 0, 5.3, 0), part(box(4.4, 3.6, 0.1), plastic('#7d573a', { rough: 0.7 }), 0, 7.6, 0.17), part(box(4.4, 3.6, 0.1), plastic('#7d573a', { rough: 0.7 }), 0, 3, 0.17), part(sphere(0.3, 10, 8), plastic('#c8b070', { metal: 0.8, rough: 0.3 }), 2.3, 5, 0.3)],
  light_switch: [part(box(0.7, 1.1, 0.12), plastic('#efe9d8'), 0, 5.2, 0), part(box(0.2, 0.4, 0.1), plastic('#c9c2b0'), 0, 5.2, 0.1)],
  counter: [part(box(30, 3.2, 3.6), plastic('#7a5c44', { rough: 0.7 }), 0, 1.6, 0), part(box(30.4, 0.3, 4, 0), plastic('#d9d4c8', { rough: 0.35 }), 0, 3.35, 0), part(box(4, 0.08, 2.4), plastic('#8d9aa0', { rough: 0.25 }), 0, 3.52, 0), part(cyl(0.15, 0.15, 1.4, 8), plastic('#c8cdd0', { metal: 0.8, rough: 0.25 }), 0, 4.2, -1.3)],
  wall_cabinet: [part(box(30, 4, 1.8), plastic('#8a6a4e', { rough: 0.65 }), 0, 9, 0), ...[-12, -6, 0, 6, 12].map((x) => part(box(5.4, 3.6, 0.1), plastic('#9a7a5c', { rough: 0.65 }), x, 9, 0.95))],
  table_plain: [part(rbox(13, 0.5, 7, 0.15), plastic('#8a6238', { rough: 0.5 }), 0, 3.2, 0), ...[[-6, -3], [6, -3], [-6, 3], [6, 3]].map(([x, z]) => part(box(0.5, 3, 0.5), plastic('#5a3b22'), x, 1.5, z))],
  coffee_pot: [part(cyl(0.7, 0.85, 1.5, 12), plastic('#2d2d2f', { rough: 0.3 }), 0, 0.75, 0), part(box(0.2, 0.8, 0.5), plastic('#2d2d2f'), 0.9, 0.9, 0)],
  cup: [part(cyl(0.42, 0.36, 0.9, 12), plastic('#e8e3d6', { rough: 0.35 }), 0, 0.45, 0)],
  plate: [part(cyl(1.1, 0.9, 0.1, 18), plastic('#f0ece2', { rough: 0.35 }), 0, 0.06, 0), part(cyl(0.45, 0.45, 0.08, 14), plastic('#f4c542'), 0, 0.15, 0)],
  side_table: [part(box(3.4, 0.3, 3.4), plastic('#5a3b22'), 0, 3, 0), ...[[-1.4, -1.4], [1.4, -1.4], [-1.4, 1.4], [1.4, 1.4]].map(([x, z]) => part(box(0.3, 3, 0.3), plastic('#4a3020'), x, 1.5, z))],
  table_lamp: [part(cyl(0.2, 0.5, 1.2, 10), plastic('#6a6a5a'), 0, 0.6, 0), part(cone(1, 1.3, 14), plastic('#f2d9a0', { emissive: '#ffc070', emissiveIntensity: 1.6 }), 0, 1.8, 0)],
  bed: [part(box(11, 1.8, 15), plastic('#5a3b22', { rough: 0.7 }), 0, 0.9, 0), part(rbox(10.4, 1.2, 14.4, 0.3), plastic('#d9d4c8', { rough: 1 }), 0, 2.3, 0), part(rbox(10.6, 0.5, 9, 0.2), plastic('#51667f', { rough: 1 }), 0, 2.95, 2.6), part(rbox(4.2, 0.8, 2.4, 0.3), plastic('#f2eee4', { rough: 1 }), -2.5, 3.2, -5.4), part(rbox(4.2, 0.8, 2.4, 0.3), plastic('#f2eee4', { rough: 1 }), 2.5, 3.2, -5.4)],
  tv: [part(box(10, 5.8, 0.4), plastic('#101012', { rough: 0.15 }), 0, 6, 0), part(box(12, 2.8, 2.6), plastic('#5a3b22'), 0, 1.4, 0.4)],
  sofa: [part(rbox(13, 1.8, 5, 0.3), plastic('#6c7a68', { rough: 1 }), 0, 1.6, 0), part(rbox(13, 3, 1.4, 0.3), plastic('#5f6d5c', { rough: 1 }), 0, 3, 2.4), part(rbox(1.4, 2.4, 5, 0.3), plastic('#5f6d5c', { rough: 1 }), -6.8, 2.2, 0), part(rbox(1.4, 2.4, 5, 0.3), plastic('#5f6d5c', { rough: 1 }), 6.8, 2.2, 0)],
  wreck: [],
});
let mapPaperTex = null;
function mapPaper() {
  if (mapPaperTex) return mapPaperTex;
  const c = document.createElement('canvas'); c.width = 512; c.height = 256; const g = c.getContext('2d');
  g.fillStyle = '#9fb7c2'; g.fillRect(0, 0, 512, 256); g.fillStyle = '#d9cfa8';
  g.beginPath(); g.moveTo(0, 60); g.bezierCurveTo(120, 40, 220, 90, 330, 70); g.bezierCurveTo(400, 60, 470, 30, 512, 40); g.lineTo(512, 0); g.lineTo(0, 0); g.fill();
  g.beginPath(); g.moveTo(0, 190); g.bezierCurveTo(90, 170, 170, 205, 260, 180); g.bezierCurveTo(330, 160, 420, 200, 512, 175); g.lineTo(512, 256); g.lineTo(0, 256); g.fill();
  g.strokeStyle = '#7a2f2f'; g.lineWidth = 3; g.setLineDash([8, 6]); for (const x of [150, 220, 290, 350, 410]) { g.beginPath(); g.moveTo(260, 40); g.lineTo(x, 182); g.stroke(); }
  mapPaperTex = new THREE.CanvasTexture(c); mapPaperTex.colorSpace = THREE.SRGBColorSpace; stats.textures++;
  return mapPaperTex;
}
let propParts = null;
function props(W, night) {
  propParts = propParts || PROPS(night);
  const g = new THREE.Group(), by = {};
  for (const p of W.props) {
    if (p.kind === 'wreck') { const v = buildVehicle('tank', '#2e2a26'); v.position.set(p.x, p.y - 0.4, p.z); v.rotation.set(0.08, p.rot, 0.12); g.add(v); continue; }
    if (p.kind === 'warehouse') continue;
    (by[p.kind] = by[p.kind] || []).push({ x: p.x, y: p.y, z: p.z, rot: p.rot || 0, scale: p.scale || 1 });
  }
  for (const [k, pl] of Object.entries(by)) if (propParts[k]) g.add(instanced(propParts[k], pl));
  return g;
}

function interior(W, look) {
  const I = W.interior, g = new THREE.Group(), side = (I.d - I.winW) / 2;
  const wallM = I.tile ? plastic('#ffffff', { map: tiles(I.wall, 7, 4), rough: 0.35 }) : plastic(I.wall, { rough: 0.9 }), floorM = plastic('#ffffff', { map: I.floor === 'tile' ? tiles('#8f9a9c', 6, 5) : planks(), rough: I.floor === 'tile' ? 0.3 : 0.6 });
  const fl = new THREE.Mesh(box(I.w, 0.4, I.d), floorM); fl.position.y = -0.2; fl.receiveShadow = true; g.add(fl);
  const ce = new THREE.Mesh(box(I.w, 0.4, I.d), plastic('#d9d2c0')); ce.position.y = I.h; g.add(ce);
  const wall = (w, h, x, y, z, ry = 0) => { const m = new THREE.Mesh(box(w, h, 0.6), wallM); m.position.set(x, y, z); m.rotation.y = ry; m.receiveShadow = true; m.castShadow = true; g.add(m); };
  wall(I.w, I.h, 0, I.h / 2, -I.d / 2); wall(I.w, I.h, 0, I.h / 2, I.d / 2);
  // left wall with a window: the night and rain outside
  wall(I.d, 4, -I.w / 2, 2, 0, Math.PI / 2); wall(I.d, 3.5, -I.w / 2, I.h - 1.75, 0, Math.PI / 2);
  wall(side, I.h - 7.5, -I.w / 2, 4 + (I.h - 7.5) / 2, -I.d / 2 + side / 2, Math.PI / 2); wall(side, I.h - 7.5, -I.w / 2, 4 + (I.h - 7.5) / 2, I.d / 2 - side / 2, Math.PI / 2);
  const out = new THREE.Mesh(new THREE.PlaneGeometry(I.d, I.h), new THREE.MeshBasicMaterial({ color: look.night ? 0x1a2433 : 0x8aa0b0 })); out.position.set(-I.w / 2 - 3, I.h / 2, 0); out.rotation.y = Math.PI / 2; g.add(out);
  const pane = new THREE.Mesh(new THREE.PlaneGeometry(I.winW, I.h - 7.5), new THREE.MeshStandardMaterial({ color: 0x9fb6c8, transparent: true, opacity: 0.18, roughness: 0.05 })); pane.position.set(-I.w / 2 + 0.05, 4 + (I.h - 7.5) / 2, 0); pane.rotation.y = Math.PI / 2; g.add(pane);
  wall(I.d, I.h, I.w / 2, I.h / 2, 0, Math.PI / 2);
  if (I.beams) for (let x = -I.w / 2 + 3; x < I.w / 2; x += 8) { const b = new THREE.Mesh(box(0.6, I.h, 0.8), plastic('#8a7a60')); b.position.set(x, I.h / 2, -I.d / 2 + 0.6); g.add(b); }
  // a mirror really reflects the room and whoever stands at it
  for (const p of W.props) if (p.kind === 'mirror') {
    const m = new Reflector(new THREE.PlaneGeometry(8.2, 7.2), { textureWidth: 1024, textureHeight: 900, clipBias: 0.003, color: 0xb8bcbc, multisample: 4 });
    m.position.set(p.x, 6.8, p.z + 0.12); g.add(m);
    const glow = new THREE.PointLight(0xffe6c0, 70, 26, 1.6); glow.position.set(p.x, 11, p.z + 3); g.add(glow); // the light over the glass: faces in the mirror are not in shadow
  }
  return g;
}
const tilesTex = new Map();
function tiles(color, rx, ry) {
  const key = `${color}:${rx}:${ry}`; if (tilesTex.has(key)) return tilesTex.get(key);
  const c = document.createElement('canvas'); c.width = 128; c.height = 128; const g = c.getContext('2d');
  g.fillStyle = color; g.fillRect(0, 0, 128, 128); g.fillStyle = 'rgba(40,40,40,0.35)'; g.fillRect(0, 0, 128, 3); g.fillRect(0, 0, 3, 128);
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(rx, ry); t.colorSpace = THREE.SRGBColorSpace; stats.textures++; tilesTex.set(key, t);
  return t;
}
let planksTex = null;
function planks() {
  if (planksTex) return planksTex;
  const c = document.createElement('canvas'); c.width = 256; c.height = 256; const g = c.getContext('2d');
  for (let i = 0; i < 8; i++) { g.fillStyle = ['#6b4a32', '#76533a', '#5f422c', '#704e36'][i % 4]; g.fillRect(0, i * 32, 256, 31); g.fillStyle = 'rgba(0,0,0,0.25)'; g.fillRect(0, i * 32 + 31, 256, 1); }
  planksTex = new THREE.CanvasTexture(c); planksTex.wrapS = planksTex.wrapT = THREE.RepeatWrapping; planksTex.repeat.set(4, 3); planksTex.colorSpace = THREE.SRGBColorSpace; stats.textures++;
  return planksTex;
}
