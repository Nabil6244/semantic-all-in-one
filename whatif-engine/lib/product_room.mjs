// PRODUCT ROOM: a lineup of phones standing on a table in a code-built room, shot like a product film (the "Introducing" reference:
// four colours side by side in a loft, a gallery, a studio). No picture is needed: the walls, the window, the table and the light are
// built here, reflected in the phones, and the room is thrown out of focus so it reads as a photograph.
//   { id, start, end, kind: "product", object: "lineup", room: "loft" | "gallery" | "studio" | "terrace", phone: "galaxy s27 ultra",
//     colors: ["Black", "Sky Blue", "Pink", "White"], pose: "back" | "front" | "mixed" | "fan", push: [7.4, 6.6] (camera distance),
//     cam_y: -0.3, cam_x: [0, 0], focus: 0.0012 (depth-of-field aperture), seed, light: 1, bloom: 0.2 }
// Pure function of the time inside the shot; the same interface as buildProduct: { place(camera, k, t), render(renderer, camera) }.

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const lerp = (a, b, k) => a + (b - a) * k;
const ease = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
// camera travel inside one shot: near-constant speed (a hard cut already starts the next shot, so no slow start from rest) and a shorter move
// (the reference trailers move about a tenth as far per frame as a full smoothstep). shot.travel 0..1 scales the move (default `tr`); 1 = as authored.
const camE = (k, tr = 0.5, shot = null) => { const kk = clamp01(k), lin = 0.75 * kk + 0.25 * ease(kk), t = shot && shot.travel != null ? shot.travel : tr; return 0.5 + (lin - 0.5) * t; };
const linE = (k) => { const kk = clamp01(k); return 0.75 * kk + 0.25 * ease(kk); };
const seeded = (seed) => { let s = (seed >>> 0) || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

export const ROOMS = ['loft', 'gallery', 'studio', 'terrace', 'desk'];
export const LINEUP_POSES = ['back', 'front', 'mixed', 'fan'];

const ROOM = {
  loft: { wall: '#9a8f84', table: '#a98560', sun: 0xfff1de, sunI: 3.0, sunAt: [-5, 5, 4], fill: 0xc9d6e6, fillI: 0.6, win: 0xdfe9f6, winI: 3.2, sky: ['#b9cde2', '#e6ebf0', '#efe3d2'], city: true, mullions: true, props: ['plant_l', 'books_r', 'cup_r'] },
  gallery: { wall: '#e9e8e4', table: '#cdb695', sun: 0xfff7ec, sunI: 2.0, sunAt: [-2, 7, 4], fill: 0xffffff, fillI: 0.95, win: 0xffffff, winI: 3.5, sky: ['#f2f5f9', '#ffffff', '#eceff3'], city: false, mullions: false, props: ['vase_l', 'books_r'] },
  studio: { wall: '#202328', table: '#5a3b25', sun: 0xffdcb0, sunI: 4.6, sunAt: [5, 5, 4], fill: 0x93abd6, fillI: 0.6, win: 0xfff0dc, winI: 6, sky: ['#14171d', '#232832', '#0d0e12'], city: false, mullions: false, softboxes: true, props: [] },
  desk: { wall: '#c9672f', table: '#b88a5a', sun: 0xffe3c4, sunI: 2.6, sunAt: [-3, 6, 4], fill: 0xffd9b8, fillI: 0.8, win: 0xffd2a8, winI: 1.1, sky: ['#d9743a', '#c9672f', '#a85226'], city: false, mullions: false, pegboard: true, props: ['books_r', 'cup_l'] },
  terrace: { wall: '#cdd3d6', table: '#9f7b55', sun: 0xe9f0f8, sunI: 1.7, sunAt: [-4, 6, 4], fill: 0xd8e3ef, fillI: 0.95, win: 0xe2ecf7, winI: 4, sky: ['#a9c1d8', '#dde7f0', '#8ea8b8'], city: false, mullions: true, lake: true, props: ['plant_r', 'cup_l'] },
};

function woodTexture(THREE, base, seed) {
  const c = document.createElement('canvas'); c.width = 2048; c.height = 512; const g = c.getContext('2d'), r = seeded(seed), col = new THREE.Color(base);
  const hex = (k) => `rgb(${Math.round(255 * Math.min(1, col.r * k))},${Math.round(255 * Math.min(1, col.g * k))},${Math.round(255 * Math.min(1, col.b * k))})`;
  g.fillStyle = hex(0.92); g.fillRect(0, 0, 2048, 512);
  for (let i = 0; i < 520; i++) {                       // long grain streaks
    const y = r() * 512, k = 0.78 + r() * 0.4, len = 300 + r() * 1700, x = r() * 2048;
    g.fillStyle = hex(k); g.globalAlpha = 0.12 + r() * 0.25; g.fillRect(x, y, len, 0.8 + r() * 3.2);
  }
  g.globalAlpha = 0.55; g.strokeStyle = hex(0.7); g.lineWidth = 2;
  for (let p = 1; p < 5; p++) { g.beginPath(); g.moveTo(0, p * 102); g.lineTo(2048, p * 102); g.stroke(); }   // plank seams
  g.globalAlpha = 1;
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 8; return t;
}

function skyTexture(THREE, cfg, seed) {
  const c = document.createElement('canvas'); c.width = 2048; c.height = 1024; const g = c.getContext('2d'), r = seeded(seed);
  const gr = g.createLinearGradient(0, 0, 0, 1024); gr.addColorStop(0, cfg.sky[0]); gr.addColorStop(0.6, cfg.sky[1]); gr.addColorStop(1, cfg.sky[2]); g.fillStyle = gr; g.fillRect(0, 0, 2048, 1024);
  if (cfg.city) {                                          // a daylight skyline: layered blue-grey blocks with window glints
    for (let layer = 0; layer < 3; layer++) {
      const shade = [0.78, 0.62, 0.46][layer], base = 640 + layer * 70; let x = -20;
      while (x < 2100) { const w = 60 + r() * 130, h = 120 + r() * (260 - layer * 50);
        g.fillStyle = `rgb(${Math.round(150 * shade)},${Math.round(168 * shade)},${Math.round(195 * shade)})`; g.fillRect(x, base - h, w, h + 400);
        g.fillStyle = `rgba(255,240,210,${0.25 - layer * 0.06})`; for (let i = 0; i < w * h / 520; i++) g.fillRect(x + r() * w, base - h + r() * h, 3, 5);
        x += w + r() * 14; }
    }
  }
  if (cfg.lake) { const w = g.createLinearGradient(0, 560, 0, 1024); w.addColorStop(0, '#7e98a8'); w.addColorStop(1, '#4d6676'); g.fillStyle = w; g.fillRect(0, 560, 2048, 464);
    g.fillStyle = '#cfd8de'; g.fillRect(150, 380, 520, 190); g.fillStyle = '#9fb0bb'; g.fillRect(150, 380, 520, 14); }
  if (cfg.softboxes) { for (const [x, w] of [[300, 360], [1380, 420]]) { const s = g.createLinearGradient(x, 0, x + w, 0); s.addColorStop(0, 'rgba(255,240,220,0.05)'); s.addColorStop(0.5, 'rgba(255,244,230,1)'); s.addColorStop(1, 'rgba(255,240,220,0.05)');
    g.fillStyle = s; g.fillRect(x, 140, w, 520); } }
  if (cfg.pegboard) {                                      // a diorama desk wall: orange pegboard with a grid of pale holes
    g.fillStyle = cfg.sky[0]; g.fillRect(0, 0, 2048, 1024);
    for (let y = 40; y < 1024; y += 56) for (let x = 40; x < 2048; x += 56) { g.fillStyle = 'rgba(40,16,6,0.55)'; g.beginPath(); g.arc(x, y, 9, 0, 7); g.fill(); g.fillStyle = 'rgba(255,214,170,0.35)'; g.beginPath(); g.arc(x - 2, y - 2, 4, 0, 7); g.fill(); }
    g.fillStyle = 'rgba(255,235,205,0.9)'; g.fillRect(200, 200, 38, 120); g.fillRect(200, 200, 150, 22);      // a pale hook and a hung tool
    g.fillStyle = 'rgba(30,60,64,0.9)'; g.fillRect(1500, 260, 260, 150); g.fillStyle = 'rgba(255,255,255,0.8)'; g.fillRect(1520, 280, 220, 14);
  }
  if (cfg.mullions) { g.fillStyle = '#1c1d20'; for (let x = 0; x <= 2048; x += 256) g.fillRect(x - 6, 0, 12, 1024); for (let y = 200; y < 1024; y += 260) g.fillRect(0, y - 5, 2048, 10); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

function plasterTexture(THREE, seed) {
  const c = document.createElement('canvas'); c.width = c.height = 512; const g = c.getContext('2d'), r = seeded(seed);
  g.fillStyle = '#808080'; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 9000; i++) { const v = 100 + r() * 90 | 0; g.fillStyle = `rgba(${v},${v},${v},${0.08 + r() * 0.18})`; g.fillRect(r() * 512, r() * 512, 1 + r() * 9, 1 + r() * 9); }
  const t = new THREE.CanvasTexture(c); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(6, 3); return t;
}

function makeProps(THREE, names, tableY, seed) {
  const grp = new THREE.Group(), r = seeded(seed + 9);
  const std = (color, rough = 0.7, metal = 0) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal });
  const cast = (m) => { m.castShadow = true; m.receiveShadow = true; return m; };
  const put = (m, y) => { m.position.set(0, y, 0); return m; };
  const plant = (x, z, sc) => {
    const g = new THREE.Group(); g.position.set(x, tableY, z); g.scale.setScalar(sc);
    g.add(cast(put(new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.26, 0.5, 32), std('#d8d2c8', 0.8)), 0.25)));
    for (let i = 0; i < 16; i++) {
      const leaf = new THREE.Mesh(new THREE.SphereGeometry(1, 14, 8), std(['#3f6b3c', '#4f7d45', '#335a35'][i % 3], 0.6));
      leaf.scale.set(0.13, 0.62 + r() * 0.35, 0.035); const a = r() * Math.PI * 2, tilt = 0.25 + r() * 0.7;
      const pivot = new THREE.Group(); pivot.position.set(0, 0.5, 0); pivot.rotation.set(0, a, tilt); leaf.position.y = leaf.scale.y; pivot.add(leaf); cast(leaf); g.add(pivot);
    }
    return g;
  };
  const cup = (x, z) => {
    const g = new THREE.Group(); g.position.set(x, tableY, z);
    g.add(cast(put(new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.14, 0.24, 32), std('#f1efe9', 0.35)), 0.12)));
    const h = new THREE.Mesh(new THREE.TorusGeometry(0.07, 0.016, 12, 24), std('#f1efe9', 0.35)); h.position.set(0.19, 0.12, 0); cast(h); g.add(h);
    const l = new THREE.Mesh(new THREE.CircleGeometry(0.15, 32), std('#2a1a12', 0.25)); l.rotation.x = -Math.PI / 2; l.position.y = 0.235; g.add(l);
    return g;
  };
  const books = (x, z) => {
    const g = new THREE.Group(); g.position.set(x, tableY, z); let y = 0;
    for (const [w, h, d, c, rot] of [[0.9, 0.12, 0.62, '#6b4b3a', 0.12], [0.78, 0.1, 0.55, '#c9b28a', -0.18], [0.7, 0.14, 0.5, '#4d5a66', 0.08]]) {
      const b = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), std(c, 0.8)); b.position.y = y + h / 2; b.rotation.y = rot; cast(b); g.add(b); y += h;
    }
    return g;
  };
  const vase = (x, z) => {
    const g = new THREE.Group(); g.position.set(x, tableY, z);
    const pts = [[0, 0], [0.18, 0], [0.26, 0.2], [0.2, 0.45], [0.1, 0.6], [0.13, 0.68], [0, 0.68]].map(([rr, y]) => new THREE.Vector2(rr, y));
    g.add(cast(new THREE.Mesh(new THREE.LatheGeometry(pts, 40), std('#e9e4da', 0.3))));
    for (let i = 0; i < 5; i++) { const br = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.012, 0.9, 6), std('#5b4a3a', 0.8)); br.position.set((i - 2) * 0.05, 1.1, 0); br.rotation.z = (i - 2) * 0.14; cast(br); g.add(br); }
    return g;
  };
  for (const n of names) {
    if (n === 'plant_l') grp.add(plant(-2.95, -1.45, 1.25)); if (n === 'plant_r') grp.add(plant(2.95, -1.5, 1.15));
    if (n === 'books_r') grp.add(books(2.85, -0.9)); if (n === 'cup_r') grp.add(cup(2.7, -0.2)); if (n === 'cup_l') grp.add(cup(-2.7, -0.3));
    if (n === 'vase_l') grp.add(vase(-2.9, -1.2));
  }
  return grp;
}

// a concentric ripple wallpaper in a colour: the "water drop" wallpaper of the reference's four phones
function rippleWallpaper(THREE, tint, seed) {
  const c = document.createElement('canvas'); c.width = 540; c.height = 1170; const g = c.getContext('2d'), col = new THREE.Color(tint);
  const rgb = (k, a = 1) => `rgba(${Math.round(255 * Math.min(1, col.r * k))},${Math.round(255 * Math.min(1, col.g * k))},${Math.round(255 * Math.min(1, col.b * k))},${a})`;
  const bg = g.createLinearGradient(0, 0, 0, 1170); bg.addColorStop(0, rgb(0.55)); bg.addColorStop(1, rgb(0.9)); g.fillStyle = bg; g.fillRect(0, 0, 540, 1170);
  const r = seeded(seed), cx = 200 + r() * 140, cy = 520 + r() * 160;
  for (let i = 0; i < 26; i++) {
    const rad = 18 + i * 22, w = 0.5 + 0.5 * Math.sin(i * 0.9);
    g.strokeStyle = i % 2 ? rgb(1.2, 0.4 + 0.2 * w) : rgb(0.5, 0.4 + 0.25 * w); g.lineWidth = 9 + 5 * w;
    g.beginPath(); g.ellipse(cx, cy, rad * 1.05, rad * 0.8, -0.3, 0, Math.PI * 2); g.stroke();
  }
  const v = g.createRadialGradient(270, 585, 150, 270, 585, 760); v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.5)'); g.fillStyle = v; g.fillRect(0, 0, 540, 1170);
  g.fillStyle = '#05070a'; g.beginPath(); g.arc(270, 44, 13, 0, Math.PI * 2); g.fill();
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}

const WALLPAPER = { black: '#5d6672', navy: '#5278a6', 'sky blue': '#4e9fc7', blue: '#4e9fc7', pink: '#e2a3b3', white: '#bfc5cc', silver: '#bfc5cc' };

export async function buildRoom(THREE, shot, { renderer, W, H }) {
  const cfg = ROOM[shot.room] || ROOM.loft, seed = shot.seed ?? 11, R = seeded(seed);
  const scene = new THREE.Scene(); scene.background = new THREE.Color('#0b0b0d');
  const lightK = shot.light ?? 1;
  // ---- the room ---------------------------------------------------------------------------------------------------------------
  const TABLE_Y = -1.0;
  const plaster = plasterTexture(THREE, seed + 5);
  const wallMat = new THREE.MeshStandardMaterial({ color: cfg.wall, roughness: 0.95, metalness: 0, bumpMap: plaster, bumpScale: 1.2 });
  const back = new THREE.Mesh(new THREE.PlaneGeometry(40, 16), wallMat); back.position.set(0, 3, -9); scene.add(back);
  const left = new THREE.Mesh(new THREE.PlaneGeometry(30, 16), wallMat); left.rotation.y = Math.PI / 2; left.position.set(-12, 3, -3); scene.add(left);
  const winTex = skyTexture(THREE, cfg, seed);
  const win = new THREE.Mesh(new THREE.PlaneGeometry(cfg.softboxes ? 24 : 17, cfg.softboxes ? 9 : 7.5), new THREE.MeshBasicMaterial({ map: winTex, toneMapped: false, color: new THREE.Color(1, 1, 1).multiplyScalar(cfg.softboxes ? 1.4 : 1.15) }));
  win.position.set(cfg.softboxes ? 0 : 2.5, 2.2, -8.9); scene.add(win);
  if (cfg.mullions) {   // a real steel window frame in front of the sky: depth, a sill and a lintel
    const steel = new THREE.MeshStandardMaterial({ color: '#1d1f22', roughness: 0.45, metalness: 0.6 }), wx = 2.5, ww = 17, wh = 7.5, wy = 2.2;
    for (let i = 0; i <= 6; i++) { const m = new THREE.Mesh(new THREE.BoxGeometry(0.14, wh, 0.22), steel); m.position.set(wx - ww / 2 + i * (ww / 6), wy, -8.7); m.castShadow = true; scene.add(m); }
    for (let j = 0; j <= 3; j++) { const m = new THREE.Mesh(new THREE.BoxGeometry(ww, 0.14, 0.22), steel); m.position.set(wx, wy - wh / 2 + j * (wh / 3), -8.7); scene.add(m); }
    const sill = new THREE.Mesh(new THREE.BoxGeometry(ww + 0.6, 0.18, 0.8), new THREE.MeshStandardMaterial({ color: cfg.wall, roughness: 0.9 })); sill.position.set(wx, wy - wh / 2 - 0.1, -8.5); scene.add(sill);
  }
  const ceil = new THREE.Mesh(new THREE.PlaneGeometry(40, 30), new THREE.MeshBasicMaterial({ color: new THREE.Color(cfg.softboxes ? '#0a0a0c' : '#f2f2f0').multiplyScalar(cfg.softboxes ? 1 : 0.85) })); ceil.rotation.x = Math.PI / 2; ceil.position.set(0, 9, -2); scene.add(ceil);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 30), new THREE.MeshStandardMaterial({ color: cfg.softboxes ? '#1b1b1e' : '#8f8a82', roughness: 0.7 })); floor.rotation.x = -Math.PI / 2; floor.position.set(0, -3.4, -2); scene.add(floor);
  if (cfg.softboxes) {   // a cine camera on a stand in the blur, and two panel lights: the studio reference's props, as dark shapes
    const dark = new THREE.MeshStandardMaterial({ color: '#0e0f12', roughness: 0.5, metalness: 0.6 });
    const body = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.0, 2.2), dark); body.position.set(3.2, 0.6, -6); scene.add(body);
    const lensM = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.45, 1.2, 32), dark); lensM.rotation.x = Math.PI / 2; lensM.position.set(3.2, 0.6, -4.7); scene.add(lensM);
    const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 4, 12), dark); stand.position.set(3.2, -1.4, -6); scene.add(stand);
  }
  // the table: a thick slab with a wood top
  const wood = woodTexture(THREE, cfg.table, seed + 3); wood.repeat.set(2.2, 1);
  const woodMat = (extra = {}) => new THREE.MeshPhysicalMaterial({ map: wood, bumpMap: wood, bumpScale: 0.6, roughness: 0.42, clearcoat: 0.45, clearcoatRoughness: 0.28, metalness: 0, envMapIntensity: 0.6, ...extra });
  const topMat = woodMat({ transparent: true, opacity: 0.85, depthWrite: false, color: new THREE.Color('#9a9086'), roughness: 0.38 }), sideMat = woodMat();
  const top = new THREE.Mesh(new THREE.BoxGeometry(11, 3.2, 4.6), [sideMat, sideMat, topMat, sideMat, sideMat, sideMat]);
  top.position.set(0, TABLE_Y - 1.6, -0.2); top.receiveShadow = true; scene.add(top);
  scene.add(makeProps(THREE, cfg.props || [], TABLE_Y, seed));
  // ---- the room's light reflected in the phones --------------------------------------------------------------------------------
  const pm = new THREE.PMREMGenerator(renderer);
  const envRT = pm.fromScene(scene, 0.015, 0.1, 100); pm.dispose();
  scene.environment = envRT.texture; scene.environmentIntensity = 0.65 * lightK;
  // ---- the lineup --------------------------------------------------------------------------------------------------------------
  const pmx = await import('./phone_models.mjs');
  const colors = Array.isArray(shot.colors) && shot.colors.length ? shot.colors.slice(0, 5) : ['Black', 'Sky Blue', 'Pink', 'White'];
  const holder = new THREE.Group(); scene.add(holder);
  const phones = [];
  const SPACE = shot.spacing ?? 1.32, n = colors.length;
  for (let i = 0; i < n; i++) {
    const spec = pmx.resolvePhone({ preset: shot.phone || 'galaxy s27 ultra', color: colors[i], wordmark: shot.wordmark });   // wordmark "" = none on the back
    const tint = WALLPAPER[String(colors[i]).toLowerCase()] || WALLPAPER.blue;
    const model = pmx.buildPhoneModel(THREE, spec, { envMap: envRT.texture, shot: { ...shot, object: 'phone' }, screenMap: rippleWallpaper(THREE, tint, seed + i * 7) });
    model.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = false; } });
    const g = new THREE.Group(); g.add(model);
    const x = (i - (n - 1) / 2) * SPACE;
    g.position.set(x, TABLE_Y + 1.0, [0, 0.22, 0.22, 0][i % 4] * (shot.stagger ?? 1) - 0.1);
    holder.add(g);
    const mir = g.clone(true); mir.scale.y = -1; mir.position.set(x, 2 * TABLE_Y - g.position.y, g.position.z); mir.traverse((o) => { if (o.isMesh) { o.castShadow = false; } }); holder.add(mir);
    phones.push({ g, mir, i, x });
    const cs = document.createElement('canvas'); cs.width = cs.height = 128; const cg = cs.getContext('2d'); const gr = cg.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, 'rgba(0,0,0,0.85)'); gr.addColorStop(0.5, 'rgba(0,0,0,0.35)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); cg.fillStyle = gr; cg.fillRect(0, 0, 128, 128);
    const dec = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 0.55), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(cs), transparent: true, depthWrite: false, opacity: 0.7 }));
    dec.rotation.x = -Math.PI / 2; dec.position.set(x, TABLE_Y + 0.004, g.position.z); scene.add(dec);
  }
  // ---- light -------------------------------------------------------------------------------------------------------------------
  const sun = new THREE.DirectionalLight(cfg.sun, cfg.sunI * lightK); sun.position.set(...cfg.sunAt); sun.target.position.set(0, -0.5, 0);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.radius = 16; sun.shadow.blurSamples = 25; sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.02;
  Object.assign(sun.shadow.camera, { left: -8, right: 8, top: 5, bottom: -5, near: 0.5, far: 30 });
  scene.add(sun, sun.target);
  try {
    const { RectAreaLightUniformsLib } = await import('/three/addons/lights/RectAreaLightUniformsLib.js'); RectAreaLightUniformsLib.init();
    const rl = new THREE.RectAreaLight(cfg.win, cfg.winI * lightK, cfg.softboxes ? 8 : 14, 6); rl.position.set(cfg.softboxes ? -6 : 1, 2.6, -8.2); rl.lookAt(0, -0.3, 0); scene.add(rl);   // the window as a soft light
  } catch (err) { console.warn(`room: window light not used (${err && err.message})`); }
  scene.add(new THREE.HemisphereLight(cfg.fill, '#2a2420', cfg.fillI * lightK));
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.VSMShadowMap;
  // ---- post: depth of field, a light bloom, tone mapping ----------------------------------------------------------------------
  const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { BokehPass }, { OutputPass }] = await Promise.all([
    import('/three/addons/postprocessing/EffectComposer.js'), import('/three/addons/postprocessing/RenderPass.js'), import('/three/addons/postprocessing/UnrealBloomPass.js'),
    import('/three/addons/postprocessing/BokehPass.js'), import('/three/addons/postprocessing/OutputPass.js')]);
  let composer = null, dof = null, focusAt = 7;
  const pose = (ph, k, t) => {
    const e = ease(k), mode = shot.pose || 'back', i = ph.i;
    const sway = Math.sin(t * 0.6 + i) * 0.006;
    let ry = Math.PI + (i - (n - 1) / 2) * 0.05 + sway;                                   // backs to camera, a hair of fan
    if (mode === 'front') ry = (i - (n - 1) / 2) * -0.05 + sway;
    else if (mode === 'mixed') ry = i % 2 ? (i - (n - 1) / 2) * -0.05 : Math.PI + (i - (n - 1) / 2) * 0.05;
    else if (mode === 'fan') ry = Math.PI + (i - (n - 1) / 2) * 0.28 * (0.5 + 0.5 * e);
    if (shot.turn) { const a = clamp01((k - (shot.turn[0] ?? 0.3)) / Math.max(0.05, shot.turn[1] - shot.turn[0])); ry += ease(a) * Math.PI * (i % 2 ? 1 : -1) * 1; }   // a half turn back to front
    return ry;
  };
  return {
    scene,
    place(camera, k, t) {
      const e = camE(k, 0.85, shot), push = shot.push || [7.9, 6.3], cx = shot.cam_x || [-0.45, 0.45];
      camera.fov = shot.fov ?? 30; camera.aspect = W / H; camera.near = 0.1; camera.far = 120; camera.updateProjectionMatrix();
      camera.position.set(lerp(cx[0], cx[1], e), shot.cam_y ?? -0.25, lerp(push[0], push[1], e));
      camera.up.set(0, 1, 0); camera.lookAt(lerp(cx[0], cx[1], e) * 0.4, shot.look_y ?? -0.15, 0); camera.updateMatrixWorld(true);
      focusAt = camera.position.distanceTo(new THREE.Vector3(0, 0, 0));
      for (const ph of phones) { ph.g.rotation.y = pose(ph, k, t); ph.mir.rotation.y = ph.g.rotation.y; }
    },
    render(rend, camera) {
      if (!composer) {
        const rt = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 });
        composer = new EffectComposer(rend, rt); composer.setPixelRatio(1); composer.setSize(W, H);
        composer.addPass(new RenderPass(scene, camera));
        if (shot.dof !== false) { dof = new BokehPass(scene, camera, { focus: focusAt, aperture: shot.focus ?? 0.0014, maxblur: shot.maxblur ?? 0.007 }); composer.addPass(dof); }
        composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), shot.bloom ?? 0.18, 0.5, 0.92));
        composer.addPass(new OutputPass());
      }
      if (dof) dof.uniforms.focus.value = focusAt;
      composer.render();
    },
  };
}
