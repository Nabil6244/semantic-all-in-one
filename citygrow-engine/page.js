// The page: the low-poly city on the GPU. window.renderFrame(t) draws one frame (3D + text layer) and returns a base64
// JPEG. Every frame is a function of t alone (houses, trees, streets and landmarks are all decided by the year at t),
// so frames can be rendered in any order.
//
// Look: flat-shaded triangle ground, faceted water with a soft sun glint, instanced houses with gable roofs, faceted
// trees, soft sun shadows, light haze, then one pass for tilt-shift blur, colour grade and vignette.
import * as THREE from '/three/three.module.min.js';
import { makeTerrain } from '/lib/terrain.mjs';
import { stateAt, hudAt, cameraAt, placeCamera, eraIndexAt } from '/lib/timeline.mjs';
import { needed, riseOf, eventFactor, hash, densityOf } from '/lib/growth.mjs';
import { styleOf } from '/lib/styles.mjs';
import { buildLandmark } from '/lib/landmarks.mjs';
import { drawHud } from '/lib/hud.mjs';

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (k) => { k = clamp(k, 0, 1); return k * k * (3 - 2 * k); };
window.__stage = 'start';

async function bin(url, Type = Float32Array) { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return new Type(await r.arrayBuffer()); }

async function main() {
  const cfg = await (await fetch('/config.json')).json();
  const { W, H, tl } = cfg;
  window.__stage = 'world';
  const heights = await bin('/world/height.f32');
  const water = await bin('/world/water.u8', Uint8Array);
  const level = cfg.world.hasLevel ? await bin('/world/water_level.f32') : null;
  const T = makeTerrain(heights, cfg.world.w, cfg.world.h, cfg.world.cell, { step: cfg.terrainStep, water, level });
  const lotsA = await bin('/data/lots.bin'), treesA = await bin('/data/trees.bin');
  const NL = lotsA.length / 11, NT = treesA.length / 8;

  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1); renderer.setSize(W, H);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  document.body.appendChild(renderer.domElement);
  const REAL = cfg.look === 'real';
  if (REAL) { renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.2; }
  const scene = new THREE.Scene();
  const HAZE = new THREE.Color(REAL ? (cfg.climate && cfg.climate.sand ? 0xd9d2c3 : 0xbcd0de) : 0xc4d3dc);
  scene.background = HAZE; scene.fog = REAL ? new THREE.Fog(HAZE, 1200, 7000) : new THREE.Fog(HAZE, 2000, 9000);
  const camera = new THREE.PerspectiveCamera(cfg.fov || 38, W / H, 1, 30000);

  // ---------------------------------------------------------------- light
  const hemi = new THREE.HemisphereLight(0xdfeaff, 0x7a6a4c, 1.15); scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff0d2, 2.4); sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096); sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.6; sun.shadow.radius = 3;
  scene.add(sun); scene.add(sun.target);
  const sunAz = ((cfg.sun?.az ?? 215) * Math.PI) / 180, sunEl = ((cfg.sun?.el ?? 38) * Math.PI) / 180;
  const sunDir = new THREE.Vector3(Math.sin(sunAz) * Math.cos(sunEl), Math.sin(sunEl), -Math.cos(sunAz) * Math.cos(sunEl));

  // ---------------------------------------------------------------- ground
  window.__stage = 'ground';
  {
    const { M, sp, x0, hs, n } = T;
    const pos = new Float32Array(M * M * 18), col = new Float32Array(M * M * 18);
    const L = cfg.climate || {}, c = new THREE.Color(), grassA = new THREE.Color(L.grassA ?? 0x7f9f52), grassB = new THREE.Color(L.grassB ?? 0x9aae5e), dry = new THREE.Color(L.dry ?? 0xb6ad78),
      rock = new THREE.Color(L.rock ?? 0x9b9583), sand = new THREE.Color(L.sand ?? 0xd8c99a), wet = new THREE.Color(0x9fb9a4), deep = new THREE.Color(0x4f7f8c);
    let p = 0;
    const put = (i, j) => { pos[p++] = x0 + i * sp; pos[p++] = hs[j * n + i]; pos[p++] = x0 + j * sp; };
    const tri = (a, b, d, k) => {
      const ya = hs[a[1] * n + a[0]], yb = hs[b[1] * n + b[0]], yd = hs[d[1] * n + d[0]], y = (ya + yb + yd) / 3;
      const slope = (Math.max(ya, yb, yd) - Math.min(ya, yb, yd)) / sp, r = hash(a[0] * 977 + k, a[1]);
      const bed = T.ls[a[1] * n + a[0]] > -1e3 || T.ls[b[1] * n + b[0]] > -1e3 || T.ls[d[1] * n + d[0]] > -1e3;
      if (y < -0.2) c.copy(wet).lerp(deep, clamp(-y / 8, 0, 1));
      else if (bed) c.copy(wet);
      else if (y < 1.6) c.copy(sand);
      else { c.copy(grassA).lerp(grassB, r).lerp(dry, clamp((y - 40) / 80, 0, 0.6)); if (slope > 0.55) c.lerp(rock, clamp((slope - 0.55) * 1.2, 0, 0.45)); }
      c.multiplyScalar(0.94 + r * 0.1);
      for (let v = 0; v < 3; v++) { col[p - 9 + v * 3] = c.r; col[p - 8 + v * 3] = c.g; col[p - 7 + v * 3] = c.b; }
    };
    for (let j = 0; j < M; j++) for (let i = 0; i < M; i++) {
      // the same diagonal as heightAt: (a, b, d) and (a, d, c), wound for an upward face
      put(i, j); put(i + 1, j + 1); put(i + 1, j); tri([i, j], [i + 1, j + 1], [i + 1, j], 0);
      put(i, j); put(i, j + 1); put(i + 1, j + 1); tri([i, j], [i, j + 1], [i + 1, j + 1], 1);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    geo.computeVertexNormals();
    let groundMat = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
    if (REAL) {
      // smooth shaded ground. With a ground picture (landuse colours over the dry/green base, or a satellite photo) the
      // picture colours the land; the vertex colours only keep the sea bed and the sand line
      const uv = new Float32Array(M * M * 12); let q = 0;
      for (let j = 0; j < M; j++) for (let i = 0; i < M; i++) for (const [a, b] of [[0, 0], [1, 1], [1, 0], [0, 0], [0, 1], [1, 1]]) { uv[q++] = (i + a) / M; uv[q++] = (j + b) / M; }
      geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
      let map = null;
      if (cfg.ground) {
        const img = new Image(); img.src = '/world/ground.img'; await img.decode();
        const cv = document.createElement('canvas'); cv.width = cv.height = 2048; const cx = cv.getContext('2d');
        if (cfg.ground === 'landuse') {
          cx.fillStyle = '#' + new THREE.Color(L.grassA ?? 0x7f9f52).getHexString(); cx.fillRect(0, 0, 2048, 2048);
          cx.drawImage(img, 0, 0, 2048, 2048);
        } else cx.drawImage(img, 0, 0, 2048, 2048);
        map = new THREE.CanvasTexture(cv); map.flipY = false; map.colorSpace = THREE.SRGBColorSpace; map.anisotropy = 8;
      }
      // land vertices go white so the picture shows as it is; sea bed / river bed keep their tint
      const cols = geo.getAttribute('color'), ptsN = cols.count;
      for (let v = 0; v < ptsN; v++) {
        const x = pos[v * 3], z = pos[v * 3 + 2], yv = pos[v * 3 + 1];
        const i = Math.round((x - x0) / sp), j = Math.round((z - x0) / sp), wetBed = T.ls[Math.min(n - 1, j) * n + Math.min(n - 1, i)] > -1e3;
        if (map && yv >= -0.2 && !wetBed) cols.setXYZ(v, 1, 1, 1);
      }
      cols.needsUpdate = true;
      groundMat = new THREE.MeshStandardMaterial({ vertexColors: true, map, roughness: 0.96, metalness: 0 });
      geo.computeVertexNormals();
      if (cfg.ground === 'satellite') {   // the photo already carries its own shading: keep the terrain's own light gentle
        const nrm = geo.getAttribute('normal');
        for (let v = 0; v < nrm.count; v++) { const nx = nrm.getX(v) * 0.3, ny = nrm.getY(v) * 0.3 + 0.7, nz = nrm.getZ(v) * 0.3, l = Math.hypot(nx, ny, nz); nrm.setXYZ(v, nx / l, ny / l, nz / l); }
      }
    }
    const ground = new THREE.Mesh(geo, groundMat);
    ground.receiveShadow = true; scene.add(ground);
    // land past the world's edge: a low skirt at the border's height, so wide shots never show the void
    let edge = 0, ne = 0; for (let i = 0; i < n; i++) for (const v of [hs[i], hs[(n - 1) * n + i], hs[i * n], hs[i * n + n - 1]]) if (v > 0) { edge += v; ne++; }
    // a ring round the world only (a plane would cover a city lower than its edges)
    const R0 = T.size * 3, r0 = -x0 - sp * 0.5, ring = new THREE.Shape([[-R0, -R0], [R0, -R0], [R0, R0], [-R0, R0]].map(([a, b]) => new THREE.Vector2(a, b)));
    ring.holes.push(new THREE.Path([[-r0, -r0], [-r0, r0], [r0, r0], [r0, -r0]].map(([a, b]) => new THREE.Vector2(a, b))));
    const skirt = new THREE.Mesh(new THREE.ShapeGeometry(ring), new THREE.MeshLambertMaterial({ color: 0x86a05e }));
    skirt.rotation.x = -Math.PI / 2; skirt.position.y = cfg.world.borderWater > 0.05 ? -6 : (ne ? edge / ne : 0) - 1.5; scene.add(skirt);
  }

  // ---------------------------------------------------------------- water: the sea (a plane at 0) and rivers and lakes (their own surface)
  const waterU = { uTime: { value: 0 } };
  const waterMat = (amp) => {
    const mat = new THREE.MeshPhongMaterial({ color: 0x3f8fc2, specular: 0xfff3d6, shininess: 70, flatShading: true, transparent: true, opacity: 0.88 });
    mat.onBeforeCompile = (s) => {
      s.uniforms.uTime = waterU.uTime;
      s.vertexShader = 'uniform float uTime;\n' + s.vertexShader.replace('#include <begin_vertex>',
        `#include <begin_vertex>
         transformed.y += ${amp.toFixed(2)} * (sin(position.x * 0.021 + uTime * 0.9) * cos(position.z * 0.017 - uTime * 0.7) + 0.55 * sin((position.x + position.z) * 0.05 + uTime * 1.3));`);
    };
    return mat;
  };
  if (cfg.world.borderWater > 0.05 || T.hs.some((v) => v < -0.5)) {
    const geo = new THREE.PlaneGeometry(T.size * 6, T.size * 6, 220, 220); geo.rotateX(-Math.PI / 2);
    const sea = new THREE.Mesh(geo, waterMat(0.55)); sea.position.y = 0.05; sea.receiveShadow = true; scene.add(sea);
  }
  {
    const { M, sp, x0, hs, ls, n } = T, P = [];
    const yAt = (i, j) => (ls[j * n + i] > -1e3 ? ls[j * n + i] : hs[j * n + i] - 2.5);
    for (let j = 0; j < M; j++) for (let i = 0; i < M; i++) {
      for (const tri of [[[i, j], [i + 1, j + 1], [i + 1, j]], [[i, j], [i, j + 1], [i + 1, j + 1]]]) {
        if (!tri.some(([a, b]) => ls[b * n + a] > -1e3)) continue;
        for (const [a, b] of tri) P.push(x0 + a * sp, yAt(a, b), x0 + b * sp);
      }
    }
    if (P.length) {
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); geo.computeVertexNormals();
      const river = new THREE.Mesh(geo, waterMat(0.12)); river.receiveShadow = true; scene.add(river);
    }
  }

  // ---------------------------------------------------------------- streets
  const roadU = { uNeed: { value: 0 }, uRoad: { value: new THREE.Color(0xc4b392) } };
  {
    const P = [], R = [];
    const HALF = { 1: 6.5, 2: 4.5, 3: 2.6 };
    for (const rd of cfg.roads) {
      if (!Number.isFinite(rd.rank)) continue;
      const hw = HALF[rd.c] || 2.6;
      for (let k = 0; k + 1 < rd.p.length; k++) {
        const [ax, az] = rd.p[k], [bx, bz] = rd.p[k + 1], len = Math.hypot(bx - ax, bz - az); if (len < 0.5) continue;
        const nx = -(bz - az) / len * hw, nz = (bx - ax) / len * hw, n = Math.max(1, Math.ceil(len / 8));
        for (let s = 0; s < n; s++) {
          const x1 = ax + (bx - ax) * s / n, z1 = az + (bz - az) * s / n, x2 = ax + (bx - ax) * (s + 1) / n, z2 = az + (bz - az) * (s + 1) / n;
          const q = [[x1 - nx, z1 - nz], [x1 + nx, z1 + nz], [x2 + nx, z2 + nz], [x2 - nx, z2 - nz]].map(([x, z]) => [x, T.heightAt(x, z) + 0.3, z]);
          for (const v of [q[0], q[2], q[1], q[0], q[3], q[2]]) { P.push(...v); R.push(rd.rank); }
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); geo.setAttribute('aRank', new THREE.Float32BufferAttribute(R, 1));
    geo.computeVertexNormals();
    const mat = new THREE.MeshLambertMaterial({ color: 0xffffff, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    mat.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, roadU);
      s.vertexShader = 'attribute float aRank; varying float vRank;\n' + s.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvRank = aRank;');
      s.fragmentShader = 'uniform float uNeed; uniform vec3 uRoad; varying float vRank;\n' + s.fragmentShader
        .replace('void main() {', 'void main() {\n if (vRank > uNeed) discard;')
        .replace('vec4 diffuseColor = vec4( diffuse, opacity );', 'vec4 diffuseColor = vec4( uRoad, opacity );');
    };
    const roads = new THREE.Mesh(geo, mat); roads.receiveShadow = true; scene.add(roads);
  }

  // ---------------------------------------------------------------- houses
  window.__stage = 'houses';
  const wallGeo = new THREE.BoxGeometry(1, 1, 1); wallGeo.translate(0, 0.5, 0);
  const roofGeo = (() => {
    const s = new THREE.Shape(); s.moveTo(-0.5, 0); s.lineTo(0.5, 0); s.lineTo(0, 1); s.closePath();
    const g = new THREE.ExtrudeGeometry(s, { depth: 1, bevelEnabled: false }); g.translate(0, 0, -0.5); g.rotateY(Math.PI / 2); return g;   // ridge along x
  })();
  const houseMat = new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
  let wallMat = houseMat, roofMat = houseMat;
  if (REAL) {
    // real look: smooth standard materials; the walls get a floor-by-floor window grid drawn from world position
    roofMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, metalness: 0 });
    wallMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.8, metalness: 0.05 });
    wallMat.onBeforeCompile = (sh) => {
      sh.vertexShader = 'varying vec3 vWP; varying vec3 vWN;\n' + sh.vertexShader.replace('#include <begin_vertex>',
        '#include <begin_vertex>\n vWP = (modelMatrix * instanceMatrix * vec4(position, 1.0)).xyz; vWN = normalize(mat3(instanceMatrix) * normal);');
      sh.fragmentShader = 'varying vec3 vWP; varying vec3 vWN;\nfloat h21(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }\n' + sh.fragmentShader.replace(
        'vec4 diffuseColor = vec4( diffuse, opacity );',
        `vec4 diffuseColor = vec4( diffuse, opacity );
         float side = 1.0 - step(0.5, abs(vWN.y));
         float f = abs(vWN.x) > abs(vWN.z) ? vWP.z : vWP.x;
         vec2 g = vec2(f / 3.6, vWP.y / 3.3), cell = fract(g);
         float win = step(0.2, cell.x) * step(cell.x, 0.8) * step(0.26, cell.y) * step(cell.y, 0.74) * step(2.4, vWP.y);
         vec3 glass = vec3(0.13, 0.17, 0.22) * (0.75 + 0.5 * h21(floor(g)));
         diffuseColor.rgb = mix(diffuseColor.rgb, glass, win * side * 0.88);`);
    };
  }
  const walls = new THREE.InstancedMesh(wallGeo, wallMat, NL), roofs = new THREE.InstancedMesh(roofGeo, roofMat, NL);
  for (const m of [walls, roofs]) {
    m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false;
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(NL * 3), 3); scene.add(m);
  }
  const wallC = new THREE.Color(), roofC = new THREE.Color();
  const writeM = (a, o, cos, sin, sx, sy, sz, x, y, z) => {
    a[o] = cos * sx; a[o + 1] = 0; a[o + 2] = -sin * sx; a[o + 3] = 0;
    a[o + 4] = 0; a[o + 5] = sy; a[o + 6] = 0; a[o + 7] = 0;
    a[o + 8] = sin * sz; a[o + 9] = 0; a[o + 10] = cos * sz; a[o + 11] = 0;
    a[o + 12] = x; a[o + 13] = y; a[o + 14] = z; a[o + 15] = 1;
  };
  let lastKey = '';
  function updateHouses(need, year, styleA, styleB, mixK, dens = 1) {
    const key = `${Math.round(need)}|${Math.round(year)}|${styleA}|${styleB}|${mixK.toFixed(2)}|${dens.toFixed(2)}`;
    if (key === lastKey) return; lastKey = key;
    const SA = styleOf(styleA), SB = styleOf(styleB);
    const wm = walls.instanceMatrix.array, rm = roofs.instanceMatrix.array, wc = walls.instanceColor.array, rc = roofs.instanceColor.array;
    let k = 0;
    for (let i = 0; i < NL; i++) {
      const o = i * 11, rank = lotsA[o + 6];
      if (rank >= need || (year >= lotsA[o + 8] && year < lotsA[o + 9])) continue;
      const x = lotsA[o], z = lotsA[o + 1];
      let s = riseOf(rank, need, NL);
      if (cfg.events.length) s *= eventFactor(cfg.events, x, z, year);
      if (s <= 0.01) continue;
      const hs = lotsA[o + 7], S = hs < mixK ? SB : SA;
      const rh = lotsA[o + 10];   // a real building's own height (m), or 0 for a generated house
      const flat = rh > 0 ? (rh >= 9 || hash(i, 5) < 0.55) : hash(i, 5) < S.flat;
      const hgt = rh > 0 ? rh * s : (S.h[0] + (S.h[1] - S.h[0]) * hash(i, 9)) * (flat ? 1.15 : 1) * (1 + 0.45 * (dens - 1) * (0.5 + hash(i, 13))) * s;
      const a = -lotsA[o + 2], cos = Math.cos(a), sin = Math.sin(a), w = lotsA[o + 3], d = lotsA[o + 4], y = lotsA[o + 5] - 0.6;
      writeM(wm, k * 16, cos, sin, w, hgt + 0.6, d, x, y, z);
      if (flat) writeM(rm, k * 16, 1, 0, 0, 0, 0, x, y, z);   // a flat roof is the wall's own top: no roof piece at all
      else writeM(rm, k * 16, cos, sin, w * 1.06, Math.min(w, d) * S.roofH * s * 1.6, d * 1.06, x, y + hgt + 0.6, z);
      wallC.setHex(S.walls[Math.floor(hash(i, 1) * S.walls.length)]).multiplyScalar(0.92 + hash(i, 2) * 0.12);
      roofC.setHex(S.roofs[Math.floor(hash(i, 3) * S.roofs.length)]).multiplyScalar(0.9 + hash(i, 4) * 0.15);
      wc[k * 3] = wallC.r; wc[k * 3 + 1] = wallC.g; wc[k * 3 + 2] = wallC.b;
      rc[k * 3] = roofC.r; rc[k * 3 + 1] = roofC.g; rc[k * 3 + 2] = roofC.b;
      k++;
    }
    walls.count = roofs.count = k;
    for (const m of [walls, roofs]) { m.instanceMatrix.needsUpdate = true; m.instanceColor.needsUpdate = true; }
  }

  // ---------------------------------------------------------------- trees
  window.__stage = 'trees';
  const treeGeos = [new THREE.IcosahedronGeometry(1, 0), new THREE.ConeGeometry(1, 2.4, 6), new THREE.ConeGeometry(0.55, 3.2, 6)];
  treeGeos[0].scale(1, 0.9, 1); treeGeos[0].translate(0, 1.6, 0); treeGeos[1].translate(0, 1.9, 0); treeGeos[2].translate(0, 2.2, 0);
  const treeMat = new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
  const byKind = [[], [], []];
  for (let i = 0; i < NT; i++) byKind[treesA[i * 8 + 3] | 0].push(i);
  const treeMeshes = byKind.map((list, kind) => {
    const m = new THREE.InstancedMesh(treeGeos[kind], treeMat, Math.max(1, list.length));
    m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false; m.userData.list = list;
    m.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(Math.max(1, list.length) * 3), 3);
    const cc = new THREE.Color(), greens = cfg.climate?.trees || [0x4f7a3a, 0x5d8a40, 0x3f6b35, 0x6c9447, 0x587d3c];
    list.forEach((ti, j) => { cc.setHex(greens[Math.floor(hash(ti, 21) * greens.length)]).multiplyScalar(0.85 + hash(ti, 22) * 0.25); cc.toArray(m.instanceColor.array, j * 3); });
    scene.add(m); return m;
  });
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.22, 0.3, 1.4, 5).translate(0, 0.7, 0), new THREE.MeshLambertMaterial({ color: 0x6b4f35, flatShading: true }), Math.max(1, NT));
  trunk.frustumCulled = false; scene.add(trunk);
  let lastTreeNeed = -1;
  function updateTrees(need, year) {
    const key = need + year * 1e-3; if (Math.abs(key - lastTreeNeed) < 0.4) return; lastTreeNeed = key;
    const ramp = Math.max(25, NL * 0.012), ta = trunk.instanceMatrix.array; let tk = 0;
    for (const m of treeMeshes) {
      const a = m.instanceMatrix.array, list = m.userData.list; let k = 0;
      for (const ti of list) {
        const o = ti * 8; if (year >= treesA[o + 6] && year < treesA[o + 7]) continue;
        const s = clamp((treesA[o + 5] - need) / ramp, 0, 1); if (s <= 0.02) continue;
        const sc = treesA[o + 4] * 5.2 * s, y = treesA[o + 2] - 0.3;
        writeM(a, k * 16, 1, 0, sc, sc, sc, treesA[o], y + sc * 0.35, treesA[o + 1]); k++;
        writeM(ta, tk * 16, 1, 0, sc * 0.6, sc * 0.5, sc * 0.6, treesA[o], y, treesA[o + 1]); tk++;
      }
      m.count = k; m.instanceMatrix.needsUpdate = true;
    }
    trunk.count = tk; trunk.instanceMatrix.needsUpdate = true;
  }

  // ---------------------------------------------------------------- landmarks
  window.__stage = 'landmarks';
  const marks = cfg.landmarks.map((spec) => {
    const g = buildLandmark(THREE, spec, T.heightAt);
    const box = new THREE.Box3().setFromObject(g);
    g.userData = { spec, baseY: g.position.y, height: Math.max(4, box.max.y - box.min.y) + 2, times: tl.landmarkTimes[spec.id] || { tIn: -1e9, tOut: 1e9 } };
    scene.add(g); return g;
  });
  function updateLandmarks(t) {
    for (const g of marks) {
      const { tIn, tOut } = g.userData.times;
      const k = smooth((t - tIn) / 2.2) * (1 - smooth((t - tOut) / 1.6));
      g.visible = k > 0.002;
      g.position.y = g.userData.baseY - (1 - k) * g.userData.height;
    }
  }

  // ---------------------------------------------------------------- post: tilt-shift, grade, vignette
  const rt = new THREE.WebGLRenderTarget(W, H, { samples: 4, type: THREE.HalfFloatType });
  const post = new THREE.ShaderMaterial({
    uniforms: { tDiffuse: { value: rt.texture }, uRes: { value: new THREE.Vector2(W, H) }, uBlur: { value: (cfg.tiltShift ?? 1) * 4.5 * (H / 1080) } },
    vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }',
    fragmentShader: `
      uniform sampler2D tDiffuse; uniform vec2 uRes; uniform float uBlur; varying vec2 vUv;
      void main() {
        float band = smoothstep(0.16, 0.5, abs(vUv.y - 0.47));
        float r = uBlur * band;
        vec3 acc = texture2D(tDiffuse, vUv).rgb; float wsum = 1.0;
        for (int i = 0; i < 16; i++) {
          float a = float(i) * 2.39996, rr = sqrt((float(i) + 0.5) / 16.0) * r;
          vec2 o = vec2(cos(a), sin(a)) * rr / uRes;
          acc += texture2D(tDiffuse, vUv + o).rgb; wsum += 1.0;
        }
        vec3 c = acc / wsum;
        c = mix(vec3(dot(c, vec3(0.299, 0.587, 0.114))), c, 1.12);         // a touch more colour
        c = pow(max(c, 0.0), vec3(0.97)) * vec3(1.02, 1.0, 0.97);          // warm
        c = c * (1.0 + 0.12 * (c - 0.5));                                   // gentle S-curve
        vec2 q = vUv - 0.5; c *= 1.0 - 0.38 * dot(q, q) * 1.6;              // vignette
        gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
        #include <colorspace_fragment>
      }`,
  });
  const postScene = new THREE.Scene(); postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), post));
  const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  const out = document.createElement('canvas'); out.width = W; out.height = H;
  const g2 = out.getContext('2d');
  await Promise.all([document.fonts.load('800 40px CityNum'), document.fonts.load('500 40px CityNum'), document.fonts.load('500 40px CitySerif')]);

  window.renderFrame = (t) => {
    const s = stateAt(tl, t), ei = eraIndexAt(tl, t), hold = tl.holds[ei];
    const prevStyle = tl.holds[Math.max(0, ei - 1)].style, curStyle = hold.style;
    const mixK = ei === 0 ? 1 : smooth((t - hold.tr0) / Math.max(0.1, hold.tr1 - hold.tr0));
    // a style's own people per lot, blended through the skip so no houses vanish at once when the style changes
    const pa = styleOf(prevStyle).pph, pb = styleOf(curStyle).pph;
    const need = pa || pb ? (1 - mixK) * needed(s.pop, s.year, NL, pa) + mixK * needed(s.pop, s.year, NL, pb) : needed(s.pop, s.year, NL);
    updateHouses(need, s.year, prevStyle, curStyle, mixK, densityOf(s.pop, s.year));
    updateTrees(need, s.year);
    updateLandmarks(t);
    roadU.uNeed.value = need;
    const ra = styleOf(prevStyle).road, rb = styleOf(curStyle).road;
    roadU.uRoad.value.setHex(ra).lerp(new THREE.Color(rb), mixK);
    waterU.uTime.value = t;

    const c = cameraAt(tl.camera, t), pl = placeCamera(c, T.heightAt);
    camera.position.set(pl.pos.x, pl.pos.y, pl.pos.z); camera.lookAt(pl.target.x, pl.target.y, pl.target.z);
    camera.near = Math.max(1, c.dist * 0.02); camera.far = c.dist * 12 + 6000; camera.updateProjectionMatrix();
    scene.fog.near = c.dist * 1.7; scene.fog.far = c.dist * 7 + 2500;
    // shadows follow the view: a box around the focus sized to what is on screen
    const ext = clamp(c.dist * 1.25, 160, 6000);
    sun.position.set(pl.target.x + sunDir.x * 8000, pl.target.y + sunDir.y * 8000, pl.target.z + sunDir.z * 8000);
    sun.target.position.set(pl.target.x, pl.target.y, pl.target.z);
    const sc = sun.shadow.camera; sc.left = -ext; sc.right = ext; sc.top = ext; sc.bottom = -ext; sc.near = 100; sc.far = 16000; sc.updateProjectionMatrix();
    sun.shadow.normalBias = 0.3 + ext / 1500;

    renderer.setRenderTarget(rt); renderer.render(scene, camera);
    renderer.setRenderTarget(null); renderer.render(postScene, postCam);
    g2.drawImage(renderer.domElement, 0, 0);
    drawHud(g2, W, H, hudAt(tl, t));
    return out.toDataURL('image/jpeg', 0.92).split(',')[1];
  };
  window.stats = () => ({ lots: NL, trees: NT, houses: walls.count, gpu: renderer.getContext().getParameter(renderer.getContext().VERSION) });
  window.__ready = true;
}

main().catch((e) => { window.__error = String(e && e.stack || e); });
