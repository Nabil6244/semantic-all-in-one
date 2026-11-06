// Reusable sets, built once from primitives and canvas textures (no downloaded art). buildWorld(name) -> { root, setup(scene) }.
import * as THREE from '/three/three.module.min.js';
import { part, toonMat } from './toon.js';

const SPH = new THREE.SphereGeometry(1, 24, 16), BOX = new THREE.BoxGeometry(1, 1, 1), CYL = new THREE.CylinderGeometry(1, 1, 1, 16);
const box = (c, w, h, d, o = { outline: 0.02 }) => { const m = part(BOX, c, o); m.scale.set(w, h, d); m.receiveShadow = true; return m; };

function canvasTex(w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; return t;
}
function flatMat(tex) { return new THREE.MeshToonMaterial({ map: tex, gradientMap: toonMat('#fff').gradientMap }); }

// Simple original kid drawings: crayon sun + house + hills, a rainbow with clouds, a smiling fish.
const DRAWINGS = {
  house: (g, w, h) => {
    g.fillStyle = '#bfe6ff'; g.fillRect(0, 0, w, h); g.fillStyle = '#7ed957'; g.beginPath(); g.ellipse(w * 0.3, h, w * 0.5, h * 0.35, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = '#5cc94a'; g.beginPath(); g.ellipse(w * 0.85, h, w * 0.45, h * 0.28, 0, 0, Math.PI * 2); g.fill();
    g.fillStyle = '#ffd43b'; g.beginPath(); g.arc(w * 0.8, h * 0.22, h * 0.12, 0, Math.PI * 2); g.fill();
    g.strokeStyle = '#ffb000'; g.lineWidth = 6; for (let k = 0; k < 8; k++) { const a = k * Math.PI / 4; g.beginPath(); g.moveTo(w * 0.8 + Math.cos(a) * h * 0.16, h * 0.22 + Math.sin(a) * h * 0.16); g.lineTo(w * 0.8 + Math.cos(a) * h * 0.22, h * 0.22 + Math.sin(a) * h * 0.22); g.stroke(); }
    g.fillStyle = '#ff8a65'; g.fillRect(w * 0.22, h * 0.5, w * 0.26, h * 0.3); g.fillStyle = '#e53935'; g.beginPath(); g.moveTo(w * 0.18, h * 0.52); g.lineTo(w * 0.35, h * 0.3); g.lineTo(w * 0.52, h * 0.52); g.fill();
    g.fillStyle = '#8d6e63'; g.fillRect(w * 0.32, h * 0.64, w * 0.07, h * 0.16);
  },
  rainbow: (g, w, h) => {
    g.fillStyle = '#fffaf0'; g.fillRect(0, 0, w, h);
    ['#ff5252', '#ffa726', '#ffee58', '#66bb6a', '#42a5f5', '#ab47bc'].forEach((c, k) => { g.strokeStyle = c; g.lineWidth = h * 0.06; g.beginPath(); g.arc(w / 2, h * 0.85, h * (0.6 - k * 0.065), Math.PI, 0); g.stroke(); });
    g.fillStyle = '#ffffff'; g.strokeStyle = '#90caf9'; g.lineWidth = 4;
    for (const x of [0.18, 0.82]) { g.beginPath(); g.arc(w * x, h * 0.8, h * 0.1, 0, Math.PI * 2); g.arc(w * x + h * 0.1, h * 0.82, h * 0.08, 0, Math.PI * 2); g.fill(); }
  },
  fish: (g, w, h) => {
    g.fillStyle = '#b3e5fc'; g.fillRect(0, 0, w, h); g.fillStyle = '#ff9800'; g.beginPath(); g.ellipse(w * 0.45, h * 0.5, w * 0.25, h * 0.22, 0, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.moveTo(w * 0.68, h * 0.5); g.lineTo(w * 0.86, h * 0.32); g.lineTo(w * 0.86, h * 0.68); g.fill();
    g.fillStyle = '#fff'; g.beginPath(); g.arc(w * 0.33, h * 0.44, h * 0.06, 0, Math.PI * 2); g.fill(); g.fillStyle = '#222'; g.beginPath(); g.arc(w * 0.34, h * 0.44, h * 0.03, 0, Math.PI * 2); g.fill();
    g.strokeStyle = '#222'; g.lineWidth = 4; g.beginPath(); g.arc(w * 0.3, h * 0.55, h * 0.06, 0.2, Math.PI - 0.6); g.stroke();
    g.fillStyle = '#e1f5fe'; for (const [x, y, r] of [[0.15, 0.25, 0.04], [0.2, 0.15, 0.03], [0.12, 0.1, 0.02]]) { g.beginPath(); g.arc(w * x, h * y, h * r, 0, Math.PI * 2); g.fill(); }
  },
};

function frame(name, w, h) {
  const g = new THREE.Group();
  g.add(box('#ffffff', w + 0.08, h + 0.08, 0.03));
  const pic = new THREE.Mesh(new THREE.PlaneGeometry(w, h), flatMat(canvasTex(512, Math.round(512 * h / w), DRAWINGS[name]))); pic.position.z = 0.017; g.add(pic);
  return g;
}

function playroom() {
  const root = new THREE.Group(), BACK = -2.4;
  // Floor: light wood planks.
  const wood = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#e9c99a'; g.fillRect(0, 0, w, h); for (let k = 0; k < 8; k++) { g.fillStyle = k % 2 ? '#e4c290' : '#eccfa3'; g.fillRect(0, k * 64, w, 62); g.fillStyle = '#d2ae7c'; g.fillRect(((k * 197) % 400) + 40, k * 64, 3, 62); } });
  wood.wrapS = wood.wrapT = THREE.RepeatWrapping; wood.repeat.set(3, 3);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(14, 10), flatMat(wood)); floor.rotation.x = -Math.PI / 2; floor.position.z = 1.5; floor.receiveShadow = true; root.add(floor);
  // Walls: warm cream back wall + left wall, white skirting.
  const wall = toonMat('#fbf3e4');
  const back = new THREE.Mesh(new THREE.PlaneGeometry(14, 5), wall); back.position.set(0, 2.5, BACK); back.receiveShadow = true; root.add(back);
  const left = new THREE.Mesh(new THREE.PlaneGeometry(10, 5), wall); left.rotation.y = Math.PI / 2; left.position.set(-4.2, 2.5, 1.5); left.receiveShadow = true; root.add(left);
  const skirt = box('#ffffff', 14, 0.12, 0.04, { outline: 0 }); skirt.position.set(0, 0.06, BACK + 0.02); root.add(skirt);
  // Window with soft daylight and sunny yellow curtains (vertical folds).
  const win = new THREE.Group(); win.position.set(1.35, 1.75, BACK + 0.01); root.add(win);
  const sky = canvasTex(256, 256, (g, w, h) => { const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, '#cfeaff'); gr.addColorStop(1, '#f4fbff'); g.fillStyle = gr; g.fillRect(0, 0, w, h); g.fillStyle = '#d7f0c8'; g.beginPath(); g.ellipse(w * 0.4, h * 1.02, w * 0.7, h * 0.25, 0, 0, Math.PI * 2); g.fill(); });
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), new THREE.MeshBasicMaterial({ map: sky })); win.add(glass);
  for (const [x, y, w, h] of [[0, 0.77, 1.62, 0.07], [0, -0.77, 1.62, 0.07], [-0.78, 0, 0.07, 1.6], [0.78, 0, 0.07, 1.6], [0, 0, 0.04, 1.5], [0, 0, 1.5, 0.04]]) { const b = box('#ffffff', w, h, 0.05, { outline: 0 }); b.position.set(x, y, 0.02); win.add(b); }
  const sill = box('#ffffff', 1.8, 0.06, 0.18); sill.position.set(0, -0.82, 0.08); win.add(sill);
  for (const sx of [-1, 1]) for (let k = 0; k < 5; k++) { const f = part(CYL, k % 2 ? '#ffd54f' : '#ffca28', { outline: 0 }); f.scale.set(0.075, 2.3, 0.06); f.position.set(sx * (0.98 + k * 0.11), -0.1, 0.12); f.castShadow = false; win.add(f); }
  const rod = box('#c49a6c', 2.9, 0.04, 0.04, { outline: 0 }); rod.position.set(0, 1.08, 0.14); win.add(rod);
  // Drawings on the wall.
  const d1 = frame('house', 0.62, 0.46); d1.position.set(-1.25, 1.95, BACK + 0.02); d1.rotation.z = 0.03; root.add(d1);
  const d2 = frame('rainbow', 0.5, 0.38); d2.position.set(-0.45, 2.15, BACK + 0.02); d2.rotation.z = -0.04; root.add(d2);
  const d3 = frame('fish', 0.44, 0.34); d3.position.set(-2.1, 2.2, BACK + 0.02); root.add(d3);
  // Low toy shelf with blocks, a ball, a stacking-ring toy and a plush.
  const shelf = new THREE.Group(); shelf.position.set(-1.5, 0, BACK + 0.25); root.add(shelf);
  const at = (m, x, y, z) => { m.position.set(x, y, z); shelf.add(m); return m; };
  at(box('#ffffff', 1.5, 0.05, 0.4), 0, 0.95, 0); at(box('#ffffff', 1.5, 0.05, 0.4), 0, 0.5, 0);
  for (const x of [-0.75, 0.75]) at(box('#ffffff', 0.05, 0.98, 0.4), x, 0.49, 0);
  const toyCols = ['#ff5252', '#42a5f5', '#ffd43b', '#66bb6a', '#ab47bc'];
  [[-0.55, 0.62], [-0.4, 0.62], [-0.47, 0.76]].forEach(([x, y], k) => { const b = box(toyCols[k], 0.13, 0.13, 0.13, { outline: 0.06 }); b.position.set(x, y + 0.01, 0); b.rotation.y = k * 0.3; b.castShadow = true; shelf.add(b); });
  const ball = part(SPH, '#ff7043', { outline: 0.05 }); ball.scale.setScalar(0.12); ball.position.set(0.05, 0.65, 0); shelf.add(ball);
  for (let k = 0; k < 4; k++) { const r = new THREE.Mesh(new THREE.TorusGeometry(0.1 - k * 0.018, 0.03, 10, 24), toonMat(toyCols[k])); r.rotation.x = Math.PI / 2; r.position.set(0.45, 1.0 + k * 0.05, 0); shelf.add(r); }
  const plush = new THREE.Group(); plush.position.set(-0.3, 1.0, 0.02); shelf.add(plush);
  const pb = part(SPH, '#c8a27a', { outline: 0.06 }); pb.scale.set(0.11, 0.12, 0.1); pb.position.y = 0.1; plush.add(pb);
  const ph = part(SPH, '#c8a27a', { outline: 0.06 }); ph.scale.setScalar(0.09); ph.position.y = 0.27; plush.add(ph);
  for (const sx of [-1, 1]) { const e = part(SPH, '#c8a27a', { outline: 0.1 }); e.scale.setScalar(0.035); e.position.set(sx * 0.07, 0.34, 0); plush.add(e); }
  // Round rug and a potted plant.
  const rugT = canvasTex(512, 512, (g, w) => { ['#ffe082', '#80deea', '#ffab91', '#c5e1a5', '#fff8e1'].forEach((c, k) => { g.fillStyle = c; g.beginPath(); g.arc(w / 2, w / 2, w / 2 - k * 50, 0, Math.PI * 2); g.fill(); }); });
  const rug = new THREE.Mesh(new THREE.CircleGeometry(1.6, 64), new THREE.MeshToonMaterial({ map: rugT, gradientMap: toonMat('#fff').gradientMap, transparent: true })); rug.rotation.x = -Math.PI / 2; rug.position.set(0, 0.006, 0.2); rug.receiveShadow = true; root.add(rug);
  const pot = part(CYL, '#e57373', { outline: 0.05 }); pot.scale.set(0.16, 0.3, 0.16); pot.position.set(2.75, 0.15, BACK + 0.4); root.add(pot);
  for (let k = 0; k < 6; k++) { const l = part(SPH, k % 2 ? '#43a047' : '#66bb6a', { outline: 0.06 }); l.scale.set(0.09, 0.3, 0.05); const a = k * 1.05; l.position.set(2.75 + Math.cos(a) * 0.1, 0.55, BACK + 0.4 + Math.sin(a) * 0.1); l.rotation.set(Math.sin(a) * 0.5, 0, -Math.cos(a) * 0.5); root.add(l); }
  return {
    root,
    setup(scene) {
      scene.background = new THREE.Color('#fbf3e4');
      scene.add(new THREE.HemisphereLight('#ffffff', '#e9d8c0', 1.6));
      const sun = new THREE.DirectionalLight('#fff3df', 1.6); sun.position.set(3, 5, 4); sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -5, right: 5, top: 5, bottom: -2, near: 1, far: 20 }); sun.shadow.bias = -0.0005; sun.shadow.radius = 6;
      scene.add(sun);
      const fill = new THREE.DirectionalLight('#fff0e6', 0.9); fill.position.set(0, 2, 8); scene.add(fill);
    },
  };
}

function park() {
  const root = new THREE.Group();
  const ground = new THREE.Mesh(new THREE.CircleGeometry(60, 64), toonMat('#7ed957')); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; root.add(ground);
  const path = new THREE.Mesh(new THREE.CircleGeometry(2.2, 48), toonMat('#f3d9a4')); path.rotation.x = -Math.PI / 2; path.position.y = 0.005; path.scale.y = 0.7; path.receiveShadow = true; root.add(path);
  const tree = (x, z, s, col) => {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.scale.setScalar(s);
    const trunk = part(CYL, '#9b6a3c', { outline: 0.08 }); trunk.scale.set(0.16, 1.2, 0.16); trunk.position.y = 0.6; g.add(trunk);
    for (const [dx, dy, r] of [[0, 1.6, 0.8], [-0.45, 1.35, 0.55], [0.5, 1.4, 0.55], [0.1, 2.1, 0.55]]) { const b = part(SPH, col, { outline: 0.05 }); b.scale.setScalar(r); b.position.set(dx, dy, 0); g.add(b); }
    root.add(g);
  };
  tree(-3.2, -2.5, 1.2, '#4cc35a'); tree(3.6, -3.4, 1.4, '#3fb54f'); tree(-6, -7, 1.6, '#5ccf6a'); tree(7, -8, 1.8, '#4cc35a'); tree(1.5, -10, 1.5, '#3fb54f');
  const bush = (x, z, s) => { const b = part(SPH, '#46b852', { outline: 0.05 }); b.scale.set(s, s * 0.7, s); b.position.set(x, s * 0.3, z); root.add(b); };
  bush(-1.9, -1.2, 0.45); bush(2.3, -1.6, 0.55); bush(-4.5, -3.6, 0.6);
  const cols = ['#ff6b6b', '#ffd43b', '#ff8fd0', '#ffffff', '#a78bfa'];
  for (let i = 0; i < 26; i++) {
    const a = i * 2.39996, r = 1.6 + (i % 7) * 0.45, x = Math.cos(a) * r, z = Math.sin(a) * r * 0.6 - 0.8;
    const st = part(CYL, '#2f9e44', { outline: 0 }); st.scale.set(0.015, 0.22, 0.015); st.position.set(x, 0.11, z); root.add(st);
    const h = part(SPH, cols[i % cols.length], { outline: 0.15 }); h.scale.setScalar(0.06); h.position.set(x, 0.24, z); root.add(h);
  }
  const clouds = new THREE.Group(); clouds.name = 'clouds';
  for (const [x, y, z, s] of [[-9, 7.5, -20, 1.6], [6, 9, -24, 2], [16, 7, -22, 1.4]]) {
    const c = new THREE.Group(); c.position.set(x, y, z); c.scale.setScalar(s);
    for (const [dx, dy, r] of [[0, 0, 1], [-1, -0.2, 0.75], [1.05, -0.15, 0.8], [0.4, 0.45, 0.7]]) { const b = new THREE.Mesh(SPH, toonMat('#ffffff')); b.scale.setScalar(r); b.position.set(dx, dy, 0); c.add(b); }
    clouds.add(c);
  }
  root.add(clouds);
  return {
    root,
    setup(scene) {
      const sky = canvasTex(4, 256, (g) => { const gr = g.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, '#5bb8ff'); gr.addColorStop(0.6, '#a9dcff'); gr.addColorStop(1, '#e9f7ff'); g.fillStyle = gr; g.fillRect(0, 0, 4, 256); });
      scene.background = sky; scene.fog = new THREE.Fog('#d8f0ff', 18, 45);
      scene.add(new THREE.HemisphereLight('#ffffff', '#8fd47a', 1.4));
      const sun = new THREE.DirectionalLight('#fff4dc', 2.2); sun.position.set(4, 9, 6); sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: 1, far: 30 }); sun.shadow.bias = -0.0005; sun.shadow.radius = 4;
      scene.add(sun);
      const fill = new THREE.DirectionalLight('#fff0e6', 0.9); fill.position.set(0, 2, 8); scene.add(fill);
    },
  };
}

// ---- more sets (added for scene changes): same rules: primitives and canvas textures only, the host at x≈-0.5, props stage right
const daySky = (top, mid, low) => canvasTex(4, 256, (g) => { const gr = g.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, top); gr.addColorStop(0.6, mid); gr.addColorStop(1, low); g.fillStyle = gr; g.fillRect(0, 0, 4, 256); });
function sunLight(scene, col, inten, pos, box = 6) {
  const sun = new THREE.DirectionalLight(col, inten); sun.position.set(...pos); sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048); Object.assign(sun.shadow.camera, { left: -box, right: box, top: box, bottom: -box, near: 1, far: 30 }); sun.shadow.bias = -0.0005; sun.shadow.radius = 4;
  scene.add(sun); const fill = new THREE.DirectionalLight('#fff0e6', 0.9); fill.position.set(0, 2, 8); scene.add(fill);
}

function farm() {
  const root = new THREE.Group();
  const ground = new THREE.Mesh(new THREE.CircleGeometry(60, 64), toonMat('#8bd65e')); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; root.add(ground);
  const dirt = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 30), toonMat('#d9b27c')); dirt.rotation.x = -Math.PI / 2; dirt.rotation.z = 0.35; dirt.position.set(3.2, 0.004, -8); dirt.receiveShadow = true; root.add(dirt);
  // Red barn with white trim, a round silo and a wooden fence across the field.
  const barn = new THREE.Group(); barn.position.set(-3.4, 0, -5.5); root.add(barn);
  const body = box('#d64545', 3.2, 2.2, 2.4, { outline: 0.03 }); body.position.y = 1.1; body.castShadow = true; barn.add(body);
  for (const sx of [-1, 1]) { const r = box('#8e3b3b', 1.95, 0.14, 2.6, { outline: 0.03 }); r.rotation.z = sx * -0.62; r.position.set(sx * 0.78, 2.72, 0); r.castShadow = true; barn.add(r); }
  const gable = new THREE.Mesh(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-1.6, 2.2, 1.2), new THREE.Vector3(1.6, 2.2, 1.2), new THREE.Vector3(0, 3.3, 1.2)]), toonMat('#d64545')); gable.geometry.computeVertexNormals(); barn.add(gable);
  const door = box('#ffffff', 1.1, 1.4, 0.05, { outline: 0 }); door.position.set(0, 0.7, 1.22); barn.add(door);
  const doorIn = box('#b83a3a', 0.96, 1.26, 0.06, { outline: 0 }); doorIn.position.set(0, 0.7, 1.23); barn.add(doorIn);
  for (const r of [0.6, -0.6]) { const x = box('#ffffff', 1.5, 0.06, 0.07, { outline: 0 }); x.rotation.z = r; x.position.set(0, 0.7, 1.27); barn.add(x); }
  const silo = part(CYL, '#cfd8dc', { outline: 0.03 }); silo.scale.set(0.7, 3.2, 0.7); silo.position.set(-1.0, 1.6, -5.9); root.add(silo);
  const cap = part(SPH, '#90a4ae', { outline: 0.03 }); cap.scale.set(0.7, 0.45, 0.7); cap.position.set(-1.0, 3.2, -5.9); root.add(cap);
  for (let k = -6; k <= 6; k++) { const p = box('#c8955f', 0.1, 0.8, 0.1); p.position.set(k * 1.1 + 0.4, 0.4, -2.6); p.castShadow = true; root.add(p); }
  for (const y of [0.32, 0.62]) { const r = box('#c8955f', 14, 0.08, 0.06); r.position.set(0.4, y, -2.6); root.add(r); }
  // Hay bales and far hills.
  for (const [x, z] of [[2.6, -4.2], [3.4, -4.6], [3.0, -4.2]]) { const h = part(CYL, '#f2c94c', { outline: 0.05 }); h.scale.set(0.45, 0.6, 0.45); h.rotation.z = Math.PI / 2; h.position.set(x, 0.45, z); h.castShadow = true; root.add(h); }
  for (const [x, z, s, c] of [[-14, -26, 9, '#74c95a'], [6, -30, 12, '#69bf52'], [22, -26, 8, '#7ed06a']]) { const m = part(SPH, c, { outline: 0 }); m.scale.set(s, s * 0.35, s * 0.6); m.position.set(x, 0, z); root.add(m); }
  return { root, setup(scene) { scene.background = daySky('#62bdfc', '#b5e2ff', '#eef9ff'); scene.fog = new THREE.Fog('#dff3ff', 20, 50); scene.add(new THREE.HemisphereLight('#ffffff', '#9edb7c', 1.4)); sunLight(scene, '#fff1d6', 2.1, [5, 9, 6]); } };
}

function beach() {
  const root = new THREE.Group();
  const sand = new THREE.Mesh(new THREE.PlaneGeometry(80, 14), toonMat('#f6dfa6')); sand.rotation.x = -Math.PI / 2; sand.position.z = 2; sand.receiveShadow = true; root.add(sand);
  const wet = new THREE.Mesh(new THREE.PlaneGeometry(80, 1.2), toonMat('#e7c98a')); wet.rotation.x = -Math.PI / 2; wet.position.set(0, 0.003, -4.4); root.add(wet);
  const sea = new THREE.Mesh(new THREE.PlaneGeometry(120, 60), toonMat('#3db4e8')); sea.rotation.x = -Math.PI / 2; sea.position.set(0, -0.02, -35); root.add(sea);
  for (let k = 0; k < 3; k++) { const f = new THREE.Mesh(new THREE.PlaneGeometry(80, 0.18), toonMat('#ffffff')); f.rotation.x = -Math.PI / 2; f.position.set(0, 0.006, -5.0 - k * 1.6); f.name = `foam${k}`; root.add(f); }
  // Striped umbrella, a bucket and spade, shells, a palm tree.
  const um = new THREE.Group(); um.position.set(2.8, 0, -1.8); root.add(um);
  const pole = part(CYL, '#ffffff', { outline: 0.05 }); pole.scale.set(0.04, 2.2, 0.04); pole.position.y = 1.1; um.add(pole);
  const canopy = new THREE.Mesh(new THREE.ConeGeometry(1.3, 0.55, 12, 1, true), new THREE.MeshToonMaterial({ map: canvasTex(256, 32, (g, w, h) => { for (let k = 0; k < 12; k++) { g.fillStyle = k % 2 ? '#ffffff' : '#ff5a5f'; g.fillRect(k * w / 12, 0, w / 12 + 1, h); } }), gradientMap: toonMat('#fff').gradientMap, side: THREE.DoubleSide }));
  canopy.position.y = 2.35; canopy.castShadow = true; um.add(canopy);
  const bucket = part(CYL, '#ffd43b', { outline: 0.06 }); bucket.scale.set(0.16, 0.24, 0.16); bucket.position.set(2.1, 0.12, -0.6); root.add(bucket);
  for (const [x, z, c] of [[1.4, 0.4, '#ffb4a2'], [-2.6, 0.8, '#ffe0b2'], [0.6, 1.2, '#f8bbd0']]) { const s = part(SPH, c, { outline: 0.08 }); s.scale.set(0.09, 0.04, 0.07); s.position.set(x, 0.03, z); root.add(s); }
  const palm = new THREE.Group(); palm.position.set(-3.6, 0, -2.6); root.add(palm);
  for (let k = 0; k < 6; k++) { const seg = part(CYL, '#b07a45', { outline: 0.06 }); seg.scale.set(0.16 - k * 0.012, 0.5, 0.16 - k * 0.012); seg.position.set(k * 0.06, 0.25 + k * 0.48, 0); seg.rotation.z = -0.06; palm.add(seg); }
  for (let k = 0; k < 7; k++) { const a = (k / 7) * Math.PI * 2, l = part(SPH, k % 2 ? '#2fa84f' : '#43c264', { outline: 0.04 }); l.scale.set(1.0, 0.07, 0.24); l.position.set(0.36 + Math.cos(a) * 0.75, 3.0 - 0.15, Math.sin(a) * 0.75); l.rotation.set(0, -a, -0.35); palm.add(l); }
  return { root, setup(scene) { scene.background = daySky('#3fb0ff', '#9fdcff', '#e8f8ff'); scene.fog = new THREE.Fog('#d8f2ff', 25, 70); scene.add(new THREE.HemisphereLight('#ffffff', '#f3e1b0', 1.5)); sunLight(scene, '#fff3dc', 2.2, [4, 9, 6]); } };
}

function bedroom() {
  const root = new THREE.Group(), BACK = -2.4;
  const carpet = new THREE.Mesh(new THREE.PlaneGeometry(14, 10), toonMat('#c9b8e8')); carpet.rotation.x = -Math.PI / 2; carpet.position.z = 1.5; carpet.receiveShadow = true; root.add(carpet);
  const paper = canvasTex(256, 256, (g, w, h) => { g.fillStyle = '#e8eaf6'; g.fillRect(0, 0, w, h); g.fillStyle = '#ffffff'; for (let k = 0; k < 18; k++) { const x = (k * 97) % w, y = (k * 53) % h; g.beginPath(); g.arc(x, y, 5, 0, Math.PI * 2); g.fill(); } });
  paper.wrapS = paper.wrapT = THREE.RepeatWrapping; paper.repeat.set(6, 2);
  const back = new THREE.Mesh(new THREE.PlaneGeometry(14, 5), flatMat(paper)); back.position.set(0, 2.5, BACK); back.receiveShadow = true; root.add(back);
  // Bed with a quilt and pillow, a moon-and-stars window, a night lamp.
  const bed = new THREE.Group(); bed.position.set(2.2, 0, BACK + 1.0); root.add(bed);
  const frameB = box('#b48a64', 1.5, 0.35, 2.2); frameB.position.y = 0.3; bed.add(frameB);
  const quilt = box('#7e9cf5', 1.45, 0.16, 1.6, { outline: 0.03 }); quilt.position.set(0, 0.55, 0.25); bed.add(quilt);
  const pillow = box('#ffffff', 0.9, 0.18, 0.45, { outline: 0.04 }); pillow.position.set(0, 0.6, -0.75); bed.add(pillow);
  const head = box('#b48a64', 1.6, 1.1, 0.12); head.position.set(0, 0.6, -1.12); bed.add(head);
  const win = new THREE.Group(); win.position.set(-1.0, 1.9, BACK + 0.01); root.add(win);
  const night = canvasTex(256, 256, (g, w, h) => { g.fillStyle = '#1a2366'; g.fillRect(0, 0, w, h); g.fillStyle = '#fff6c2'; g.beginPath(); g.arc(w * 0.68, h * 0.32, 34, 0, Math.PI * 2); g.fill(); g.fillStyle = '#1a2366'; g.beginPath(); g.arc(w * 0.6, h * 0.27, 30, 0, Math.PI * 2); g.fill(); g.fillStyle = '#ffffff'; for (const [x, y] of [[0.2, 0.2], [0.35, 0.55], [0.15, 0.7], [0.82, 0.75], [0.5, 0.15]]) { g.beginPath(); g.arc(w * x, h * y, 3, 0, Math.PI * 2); g.fill(); } });
  win.add(new THREE.Mesh(new THREE.PlaneGeometry(1.3, 1.1), new THREE.MeshBasicMaterial({ map: night })));
  for (const [x, y, w, h] of [[0, 0.58, 1.42, 0.07], [0, -0.58, 1.42, 0.07], [-0.68, 0, 0.07, 1.2], [0.68, 0, 0.07, 1.2], [0, 0, 0.04, 1.1]]) { const b = box('#ffffff', w, h, 0.05, { outline: 0 }); b.position.set(x, y, 0.02); win.add(b); }
  const lamp = new THREE.Group(); lamp.position.set(-2.4, 0, BACK + 0.5); root.add(lamp);
  const table = box('#d7b48e', 0.6, 0.6, 0.5); table.position.y = 0.3; lamp.add(table);
  const shade = part(new THREE.CylinderGeometry(0.6, 1, 1, 16), '#ffe9a8', { outline: 0.05 }); shade.scale.set(0.22, 0.28, 0.22); shade.position.y = 0.95; lamp.add(shade);
  const glow = new THREE.PointLight('#ffd27a', 1.4, 4, 2); glow.position.set(-2.4, 1.0, BACK + 0.6); root.add(glow);
  return { root, setup(scene) { scene.background = new THREE.Color('#e8eaf6'); scene.add(new THREE.HemisphereLight('#e6e8ff', '#b9a8d8', 1.25)); const k = new THREE.DirectionalLight('#ffe8c4', 1.2); k.position.set(3, 5, 4); k.castShadow = true; k.shadow.mapSize.set(2048, 2048); Object.assign(k.shadow.camera, { left: -5, right: 5, top: 5, bottom: -2, near: 1, far: 20 }); k.shadow.bias = -0.0005; k.shadow.radius = 6; scene.add(k); const f = new THREE.DirectionalLight('#dfe4ff', 0.8); f.position.set(0, 2, 8); scene.add(f); } };
}

function space() {
  const root = new THREE.Group();
  const moonT = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#d6d9e6'; g.fillRect(0, 0, w, h); g.fillStyle = '#c3c7d8'; for (let k = 0; k < 26; k++) { const x = (k * 151) % w, y = (k * 89) % h, r = 10 + (k * 37) % 40; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); } });
  moonT.wrapS = moonT.wrapT = THREE.RepeatWrapping; moonT.repeat.set(4, 4);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(40, 64), flatMat(moonT)); ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; root.add(ground);
  // A friendly rocket, a ringed planet, the Earth and lots of stars.
  const rk = new THREE.Group(); rk.position.set(1.7, 0, -3.6); root.add(rk);
  const hull = part(CYL, '#f5f5f5', { outline: 0.04 }); hull.scale.set(0.45, 2.2, 0.45); hull.position.y = 1.5; hull.castShadow = true; rk.add(hull);
  const nose = part(new THREE.ConeGeometry(1, 1, 16), '#ff5a5f', { outline: 0.04 }); nose.scale.set(0.45, 0.8, 0.45); nose.position.y = 3.0; rk.add(nose);
  for (const a of [0, 2.09, 4.19]) { const fin = box('#ff5a5f', 0.08, 0.6, 0.5, { outline: 0.04 }); fin.position.set(Math.cos(a) * 0.45, 0.55, Math.sin(a) * 0.45); fin.rotation.y = -a; rk.add(fin); }
  const port = part(SPH, '#7fd3ff', { outline: 0.06 }); port.scale.set(0.18, 0.18, 0.05); port.position.set(0, 2.0, 0.44); rk.add(port);
  const planet = part(SPH, '#ffb86b', { outline: 0 }); planet.scale.setScalar(2.4); planet.position.set(-9, 7, -26); root.add(planet);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(3.6, 0.25, 8, 48), toonMat('#ffe3a3')); ring.rotation.set(1.2, 0, 0.3); ring.position.copy(planet.position); root.add(ring);
  const earth = new THREE.Mesh(SPH, new THREE.MeshToonMaterial({ map: canvasTex(256, 128, (g, w, h) => { g.fillStyle = '#2f8ef0'; g.fillRect(0, 0, w, h); g.fillStyle = '#4ccf6a'; for (const [x, y, r] of [[0.2, 0.4, 26], [0.55, 0.55, 34], [0.8, 0.3, 20]]) { g.beginPath(); g.arc(w * x, h * y, r, 0, Math.PI * 2); g.fill(); } }), gradientMap: toonMat('#fff').gradientMap }));
  earth.scale.setScalar(1.6); earth.position.set(10, 9, -28); root.add(earth);
  const stars = new THREE.Group(); stars.name = 'stars';
  for (let k = 0; k < 160; k++) { const s = new THREE.Mesh(SPH, new THREE.MeshBasicMaterial({ color: k % 9 ? '#ffffff' : '#ffe08a' })); const a = k * 2.399, r = 30 + (k % 13) * 2; s.scale.setScalar(0.06 + (k % 5) * 0.03); s.position.set(Math.cos(a) * r, 3 + ((k * 37) % 22), -20 - Math.abs(Math.sin(a)) * 20); stars.add(s); }
  root.add(stars);
  return { root, setup(scene) { scene.background = new THREE.Color('#14193d'); scene.add(new THREE.HemisphereLight('#c7d2ff', '#4b4f72', 1.1)); sunLight(scene, '#ffffff', 1.9, [5, 8, 6]); } };
}

export const WORLDS = { playroom, park, farm, beach, bedroom, space };
export function buildWorld(name) { return (WORLDS[name] || playroom)(); }
