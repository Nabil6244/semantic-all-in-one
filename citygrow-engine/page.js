// The page: the low-poly city on the GPU. window.renderFrame(t) draws one frame (3D + text layer) and returns a base64
// JPEG. Every frame is a function of t alone (houses, trees, streets and landmarks are all decided by the year at t),
// so frames can be rendered in any order.
//
// Look: flat-shaded triangle ground, faceted water with a soft sun glint, instanced houses with gable roofs, faceted
// trees, soft sun shadows, light haze, then one pass for tilt-shift blur, colour grade and vignette.
import * as THREE from '/three/three.module.min.js';
import { makeTerrain } from '/lib/terrain.mjs';
import { stateAt, hudAt, cameraAt, placeCamera, eraIndexAt } from '/lib/timeline.mjs';
import { needed, riseOf, eventFactor, burningAt, hash, densityOf, noise2 } from '/lib/growth.mjs';
import { styleOf } from '/lib/styles.mjs';
import { landClassAt, LAND } from '/lib/climate.mjs';
import { buildLandmark } from '/lib/landmarks.mjs';
import { drawHud, parseFlag } from '/lib/hud.mjs';
import { buildScaffold } from '/lib/landmarks.mjs';
import { shoreDistance, shipAt, shipsFor, fieldShown, eventSeeds, FIELD_COLORS } from '/lib/fx.mjs';

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
  const landCls = cfg.world.hasLanduse ? await bin('/world/landuse_cls.u8', Uint8Array) : null;
  const lotsA = await bin('/data/lots.bin'), treesA = await bin('/data/trees.bin');
  const LS = cfg.lotStride || 11, NL = lotsA.length / LS, NT = treesA.length / 8;

  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1); renderer.setSize(W, H);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; renderer.localClippingEnabled = true;
  document.body.appendChild(renderer.domElement);
  const REAL = cfg.look === 'real';
  if (REAL) { renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.2; }
  const scene = new THREE.Scene();
  const HAZE = new THREE.Color(REAL ? (cfg.climate && cfg.climate.sand ? 0xd9d2c3 : 0xbcd0de) : 0xc4d3dc);
  scene.background = HAZE; scene.fog = REAL ? new THREE.Fog(HAZE, 1200, 7000) : new THREE.Fog(HAZE, 2000, 9000);
  const camera = new THREE.PerspectiveCamera(cfg.fov || 38, W / H, 1, 30000);

  // ---------------------------------------------------------------- light
  const hemi = new THREE.HemisphereLight(0xd6e6ff, 0x6f5f45, REAL ? 1.15 : 1.0); scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xffeccb, REAL ? 2.4 : 2.75); sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096); sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.6; sun.shadow.radius = 4;
  // contact shading: walls and tree crowns darken towards their foot (a cheap stand-in for ambient occlusion)
  const footShade = (mat, k = 0.3, lo = 0, hi = 0.55) => {
    const prev = mat.onBeforeCompile;
    mat.onBeforeCompile = (sh, r) => {
      if (prev) prev(sh, r);
      sh.vertexShader = 'varying float vFoot;\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n vFoot = position.y;');
      sh.fragmentShader = 'varying float vFoot;\n' + sh.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>\n diffuseColor.rgb *= ${(1 - k).toFixed(2)} + ${k.toFixed(2)} * smoothstep(${lo.toFixed(2)}, ${hi.toFixed(2)}, vFoot);`);
    };
    return mat;
  };
  scene.add(sun); scene.add(sun.target);
  const sunAz = ((cfg.sun?.az ?? 215) * Math.PI) / 180, sunEl = ((cfg.sun?.el ?? 38) * Math.PI) / 180;
  const sunDir = new THREE.Vector3(Math.sin(sunAz) * Math.cos(sunEl), Math.sin(sunEl), -Math.cos(sunAz) * Math.cos(sunEl));

  // ---------------------------------------------------------------- ground
  window.__stage = 'ground';
  const groundU = { uNeed: { value: 0 }, uUrban: { value: new THREE.Color(cfg.climate && cfg.climate.sand ? 0xc9bda5 : 0xb7ae9c) } };
  {
    const { M, sp, x0, hs, n } = T;
    const pos = new Float32Array(M * M * 18), col = new Float32Array(M * M * 18);
    const L = cfg.climate || {}, c = new THREE.Color(), grassA = new THREE.Color(L.grassA ?? 0x7f9f52), grassB = new THREE.Color(L.grassB ?? 0x9aae5e), dry = new THREE.Color(L.dry ?? 0xb6ad78),
      greenA = new THREE.Color(0x7f9f52), greenB = new THREE.Color(0x9aae5e), built = new THREE.Color(0xb9ae98), rock = new THREE.Color(L.rock ?? 0x9b9583), sand = new THREE.Color(L.sand ?? 0xd8c99a), wet = new THREE.Color(0x9fb9a4), deep = new THREE.Color(0x4f7f8c);
    // Ground that is (or will be) built over: the lowest house rank within ~90 m, so the ground turns urban as the city reaches it.
    // Parks (land use "green") and water stay as they are.
    // ... once the town is built up there: the ground goes pale when KTH houses stand within ~70 m, so a sparse village
    // keeps its grass and a packed town its streets of beaten earth
    const UB = 24, KTH = 7, urbanCell = new Map(), ur = new Float32Array(M * M * 6);
    if (!REAL) for (let i = 0; i < NL; i++) {
      const o = i * LS, k = Math.floor(lotsA[o] / UB) * 100003 + Math.floor(lotsA[o + 1] / UB), r = lotsA[o + 6];
      const a = urbanCell.get(k) || urbanCell.set(k, []).get(k);
      if (a.length < KTH || r < a[KTH - 1]) { a.push(r); a.sort((p, q) => p - q); if (a.length > KTH) a.pop(); }
    }
    const urbanRank = (x, z) => {
      const all = []; const ci = Math.floor(x / UB), cj = Math.floor(z / UB);
      for (let a = ci - 1; a <= ci + 1; a++) for (let b = cj - 1; b <= cj + 1; b++) { const r = urbanCell.get(a * 100003 + b); if (r) all.push(...r); }
      if (all.length < KTH) return 1e9;
      all.sort((p, q) => p - q); return all[KTH - 1];
    };
    let ut = 0;
    let p = 0;
    const put = (i, j) => { pos[p++] = x0 + i * sp; pos[p++] = hs[j * n + i]; pos[p++] = x0 + j * sp; };
    const tri = (a, b, d, k) => {
      const ya = hs[a[1] * n + a[0]], yb = hs[b[1] * n + b[0]], yd = hs[d[1] * n + d[0]], y = (ya + yb + yd) / 3;
      const slope = (Math.max(ya, yb, yd) - Math.min(ya, yb, yd)) / sp, r = hash(a[0] * 977 + k, a[1]);
      const bed = T.ls[a[1] * n + a[0]] > -1e3 || T.ls[b[1] * n + b[0]] > -1e3 || T.ls[d[1] * n + d[0]] > -1e3;
      if (y < -0.2) c.copy(wet).lerp(deep, clamp(-y / 8, 0, 1));
      else if (bed) c.copy(wet);
      else if (y < 1.6) c.copy(sand);
      else {
        // the ground's own colour comes from land use where the map has it (parks and fields green, sand and bare ground dry,
        // built-up areas pale), and from the climate where it does not
        const lc = landCls ? landClassAt(landCls, T.half, x0 + ((a[0] + b[0] + d[0]) / 3) * sp, x0 + ((a[1] + b[1] + d[1]) / 3) * sp) : 0;
        if (lc === LAND.green) c.copy(greenA).lerp(greenB, r);
        else if (lc === LAND.dry) c.copy(sand).lerp(dry, r * 0.6);
        else if (lc === LAND.built) c.copy(built).lerp(dry, r * 0.4);
        else c.copy(grassA).lerp(grassB, r).lerp(dry, clamp((y - 40) / 80, 0, 0.6));
        if (slope > 0.55) c.lerp(rock, clamp((slope - 0.55) * 1.2, 0, 0.45));
      }
      c.multiplyScalar(0.94 + r * 0.1);
      {
        const cx = x0 + ((a[0] + b[0] + d[0]) / 3) * sp, cz = x0 + ((a[1] + b[1] + d[1]) / 3) * sp;
        const lc = landCls ? landClassAt(landCls, T.half, cx, cz) : 0;
        const ok = y >= 1.6 && !bed && lc !== LAND.green;   // land only: not sea, shore sand, river bed or a park
        const rk = ok && !REAL ? urbanRank(cx, cz) : 1e9;
        ur[ut++] = rk; ur[ut++] = rk; ur[ut++] = rk;
      }
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
    if (!REAL) {
      geo.setAttribute('aUrban', new THREE.BufferAttribute(ur, 1));
      groundMat.onBeforeCompile = (sh) => {
        sh.uniforms.uNeed = groundU.uNeed; sh.uniforms.uUrban = groundU.uUrban;
        sh.vertexShader = 'attribute float aUrban; varying float vUrban;\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvUrban = aUrban;');
        sh.fragmentShader = 'uniform float uNeed; uniform vec3 uUrban; varying float vUrban;\n' + sh.fragmentShader.replace('#include <color_fragment>',
          '#include <color_fragment>\n diffuseColor.rgb = mix(diffuseColor.rgb, uUrban, 0.6 * step(vUrban, uNeed));');
      };
    }
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
  // the sea's colour follows the distance from the shore: a turquoise shallow edge with a line of foam, deep blue further out
  const shore = shoreDistance(T);
  const shoreTex = new THREE.DataTexture(shore, T.n, T.n, THREE.RedFormat, THREE.FloatType);
  shoreTex.magFilter = shoreTex.minFilter = THREE.LinearFilter; shoreTex.needsUpdate = true;
  const waterU = { uTime: { value: 0 }, uShore: { value: shoreTex }, uX0: { value: T.x0 }, uSpan: { value: T.sp * (T.n - 1) } };
  const waterMat = (amp) => {
    const mat = new THREE.MeshPhongMaterial({ color: 0xffffff, specular: 0xfff3d6, shininess: 70, flatShading: true, transparent: true, opacity: 0.9 });
    mat.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, waterU);
      s.vertexShader = 'uniform float uTime; varying vec3 vWPos;\n' + s.vertexShader.replace('#include <begin_vertex>',
        `#include <begin_vertex>
         transformed.y += ${amp.toFixed(2)} * (sin(position.x * 0.021 + uTime * 0.9) * cos(position.z * 0.017 - uTime * 0.7) + 0.55 * sin((position.x + position.z) * 0.05 + uTime * 1.3));
         vWPos = (modelMatrix * vec4(transformed, 1.0)).xyz;`);
      s.fragmentShader = 'uniform sampler2D uShore; uniform float uX0, uSpan, uTime; varying vec3 vWPos;\n' + s.fragmentShader.replace('vec4 diffuseColor = vec4( diffuse, opacity );',
        `vec2 suv = (vWPos.xz - uX0) / uSpan;
         float inside = step(0.0, suv.x) * step(suv.x, 1.0) * step(0.0, suv.y) * step(suv.y, 1.0);
         float sd = mix(5000.0, texture2D(uShore, clamp(suv, 0.0, 1.0)).r, inside);
         vec3 deep = vec3(0.16, 0.45, 0.70), mid = vec3(0.22, 0.58, 0.79), shallow = vec3(0.36, 0.76, 0.78);
         vec3 wc = mix(shallow, mid, smoothstep(10.0, 90.0, sd));
         wc = mix(wc, deep, smoothstep(140.0, 700.0, sd));
         float foam = (1.0 - smoothstep(4.0, 16.0 + 4.0 * sin(uTime * 1.4 + vWPos.x * 0.05), sd)) * inside;
         wc = mix(wc, vec3(0.93, 0.97, 0.96), foam * 0.75);
         vec4 diffuseColor = vec4(wc, opacity);`);
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
  const roadU = { uNeed: { value: 0 }, uLanes: { value: 1 }, uRoad: { value: new THREE.Color(0xc4b392) } };
  {
    const P = [], R = [], CL = [];
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
          for (const v of [q[0], q[2], q[1], q[0], q[3], q[2]]) { P.push(...v); R.push(rd.rank); CL.push(rd.c || 3); }
        }
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); geo.setAttribute('aRank', new THREE.Float32BufferAttribute(R, 1));
    geo.setAttribute('aCls', new THREE.Float32BufferAttribute(CL, 1));
    geo.computeVertexNormals();
    const mat = new THREE.MeshLambertMaterial({ color: 0xffffff, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    mat.onBeforeCompile = (s) => {
      Object.assign(s.uniforms, roadU);
      s.vertexShader = 'attribute float aRank; attribute float aCls; varying float vRank; varying float vCls;\n' + s.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\nvRank = aRank; vCls = aCls;');
      // old towns: the narrow lanes are alleys between packed houses, only the main and secondary streets are drawn
      s.fragmentShader = 'uniform float uNeed; uniform float uLanes; uniform vec3 uRoad; varying float vRank; varying float vCls;\n' + s.fragmentShader
        .replace('void main() {', 'void main() {\n if (vRank > uNeed || (vCls > 2.5 && uLanes < 0.5)) discard;')
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
  let wallMat = footShade(new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), 0.32), roofMat = houseMat;
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
  const BIG_WALLS = [0xeee6d4, 0xe3d6bb, 0xd9cbb0, 0xf2ede2];
  function updateHouses(need, year, styleA, styleB, mixK, dens = 1, prog = null, progKey = '') {
    const key = `${Math.round(need)}|${Math.round(year)}|${styleA}|${styleB}|${mixK.toFixed(2)}|${dens.toFixed(2)}|${progKey}`;
    if (key === lastKey) return; lastKey = key;
    const SA = styleOf(styleA), SB = styleOf(styleB);
    const wm = walls.instanceMatrix.array, rm = roofs.instanceMatrix.array, wc = walls.instanceColor.array, rc = roofs.instanceColor.array;
    let k = 0;
    for (let i = 0; i < NL; i++) {
      const o = i * LS, rank = lotsA[o + 6];
      if (rank >= need || (year >= lotsA[o + 8] && year < lotsA[o + 9])) continue;
      const x = lotsA[o], z = lotsA[o + 1];
      let s = riseOf(rank, need, NL), ruin = false;
      if (cfg.events.length) {
        const f = eventFactor(cfg.events, x, z, year, prog);
        // while the fire is in it, a house is a charred ruin, not a gap; it is cleared once the clock moves on
        if (f < 0.01 && s > 0.01 && burningAt(cfg.events, x, z, year, prog)) ruin = true; else s *= f;
      }
      if (s <= 0.01) continue;
      const hs = lotsA[o + 7], S = hs < mixK ? SB : SA;
      if (LS > 11 && lotsA[o + 11] > 0 && !S.dense) continue;   // block infill belongs to the packed old town only
      const rh = lotsA[o + 10];   // a real building's own height (m), or 0 for a generated house
      // variety: a few big public buildings and mansions, taller houses in the old core, district-by-district roof tones
      const big = rh === 0 && hash(i, 31) < 0.03, core = rh === 0 ? 1 + 0.55 * clamp(1 - rank / Math.max(1, need * 0.3), 0, 1) : 1;
      const flat = rh > 0 ? (rh >= 9 || hash(i, 5) < 0.55) : hash(i, 5) < S.flat;
      const hgt = rh > 0 ? rh * s : (S.h[0] + (S.h[1] - S.h[0]) * hash(i, 9)) * (flat ? 1.15 : 1) * (1 + 0.45 * (dens - 1) * (0.5 + hash(i, 13))) * core * (big ? 1.5 : 1) * s;
      const a = -lotsA[o + 2], cos = Math.cos(a), sin = Math.sin(a), fs = big ? 1.75 : 1, w = lotsA[o + 3] * fs, d = lotsA[o + 4] * fs, y = lotsA[o + 5] - 0.6;
      if (ruin) {
        writeM(wm, k * 16, cos, sin, w * 0.9, 1.2 + hgt * 0.25 * hash(i, 41), d * 0.9, x, y, z); writeM(rm, k * 16, 1, 0, 0, 0, 0, x, y, z);
        wallC.setHex(0x3b3531).multiplyScalar(0.8 + hash(i, 2) * 0.4);
        wc[k * 3] = wallC.r; wc[k * 3 + 1] = wallC.g; wc[k * 3 + 2] = wallC.b; rc[k * 3] = rc[k * 3 + 1] = rc[k * 3 + 2] = 0;
        k++; continue;
      }
      writeM(wm, k * 16, cos, sin, w, hgt + 0.6, d, x, y, z);
      if (flat) writeM(rm, k * 16, 1, 0, 0, 0, 0, x, y, z);   // a flat roof is the wall's own top: no roof piece at all
      else writeM(rm, k * 16, cos, sin, w * 1.06, Math.min(w, d) * S.roofH * s * (big ? 1.1 : 1.6), d * 1.06, x, y + hgt + 0.6, z);
      wallC.setHex(big ? BIG_WALLS[Math.floor(hash(i, 1) * 4)] : S.walls[Math.floor(hash(i, 1) * S.walls.length)]).multiplyScalar(0.86 + hash(i, 2) * 0.2);
      const ri = Math.floor(hash(i, 3) * S.roofs.length), tone = noise2(x, z, 420, 17);
      roofC.setHex(S.roofs[ri]).lerp(new THREE.Color(S.roofs[(ri + 1) % S.roofs.length]), clamp(tone * 1.4 - 0.3, 0, 1) * 0.7).multiplyScalar(0.86 + hash(i, 4) * 0.22);
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
  const treeMat = footShade(new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), 0.38, 0.6, 2.2);
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
  // a new building goes up as a construction site: it is built from the ground up inside wooden scaffolding (a clipping
  // plane rises through it), and sinks away when it is gone
  const banners = [], scaffoldMat = new THREE.MeshLambertMaterial({ color: 0x9a7448, flatShading: true });
  const marks = cfg.landmarks.map((spec) => {
    const g = buildLandmark(THREE, spec, T.heightAt);
    const banner = g.userData.banner, local = g.userData.local;
    if (banner) banners.push(banner);
    const box = new THREE.Box3().setFromObject(g);
    const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6), sPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
    g.traverse((o) => { if (o.isMesh) { o.material.clippingPlanes = [plane]; o.material.clipShadows = true; } });
    let scaffold = null;
    if (local && !spec.points) {
      const sm = scaffoldMat.clone(); sm.clippingPlanes = [sPlane]; sm.clipShadows = true;
      scaffold = buildScaffold(THREE, local, sm); scaffold.traverse((o) => { if (o.isMesh) { o.castShadow = true; } }); g.add(scaffold);
    }
    const times = tl.landmarkTimes[spec.id] || { tIn: -1e9, tDone: -1e9 + 2.2, tOut: 1e9 };
    g.userData = { spec, baseY: g.position.y, height: Math.max(4, box.max.y - box.min.y) + 2, top: box.max.y, times, plane, sPlane, scaffold };
    scene.add(g); return g;
  });
  function updateLandmarks(t) {
    for (const g of marks) {
      const { tIn, tDone, tOut } = g.userData.times, u = g.userData;
      const rise = smooth((t - tIn) / Math.max(0.5, (tDone ?? tIn + 2.2) - tIn)), gone = smooth((t - tOut) / 1.6);
      g.visible = rise > 0.002 && gone < 0.998;
      g.position.y = u.baseY - gone * u.height;
      const building = rise < 0.999 && !u.spec.points;
      u.plane.constant = building ? u.baseY - 0.3 + rise * (u.top - u.baseY + 0.5) : 1e6;
      if (u.scaffold) { u.scaffold.visible = building && rise > 0.002; u.sPlane.constant = u.plane.constant + 6; }
      if (u.spec.points && rise < 0.999) g.position.y = u.baseY - (1 - rise) * u.height;   // walls and bridges rise as before
    }
  }

  // ---------------------------------------------------------------- farm fields
  window.__stage = 'fields';
  const fields = cfg.fields || [], NF = fields.length;
  const fieldMat = new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true });
  fieldMat.onBeforeCompile = (sh) => {
    sh.vertexShader = 'attribute float aStripes; varying vec2 vFU; varying float vStr; varying float vTop;\n' + sh.vertexShader.replace('#include <begin_vertex>',
      '#include <begin_vertex>\n vFU = uv; vStr = aStripes; vTop = normal.y;');
    sh.fragmentShader = 'varying vec2 vFU; varying float vStr; varying float vTop;\n' + sh.fragmentShader.replace('#include <color_fragment>',
      `#include <color_fragment>
       float row = step(0.5, fract(vFU.x * vStr));
       float edge = step(vFU.x, 0.03) + step(0.97, vFU.x) + step(vFU.y, 0.04) + step(0.96, vFU.y);
       diffuseColor.rgb *= mix(0.9, 1.0, row * step(0.5, vTop));
       diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.33, 0.45, 0.24), clamp(edge, 0.0, 1.0) * step(0.5, vTop) * 0.85);`);
  };
  const fieldGeo = new THREE.BoxGeometry(1, 1, 1); fieldGeo.translate(0, -0.5, 0);
  fieldGeo.setAttribute('aStripes', new THREE.InstancedBufferAttribute(new Float32Array(Math.max(1, NF)), 1));
  const fieldMesh = new THREE.InstancedMesh(fieldGeo, fieldMat, Math.max(1, NF));
  fieldMesh.receiveShadow = true; fieldMesh.frustumCulled = false; fieldMesh.count = 0; scene.add(fieldMesh);
  fieldMesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(Math.max(1, NF) * 3), 3);
  let lastFieldNeed = -1;
  function updateFields(need) {
    if (!NF || Math.abs(need - lastFieldNeed) < 0.4) return; lastFieldNeed = need;
    const ramp = Math.max(25, NL * 0.012), m = fieldMesh.instanceMatrix.array, cc = new THREE.Color(), st = fieldGeo.attributes.aStripes.array;
    let k = 0;
    for (let i = 0; i < NF; i++) {
      const f = fields[i], v = fieldShown(f, need, ramp); if (v <= 0.02) continue;
      const cos = Math.cos(-f.rot), sin = Math.sin(-f.rot);
      writeM(m, k * 16, cos, sin, f.w * (0.6 + 0.4 * v), f.h, f.d * (0.6 + 0.4 * v), f.x, f.y, f.z);
      cc.setHex(FIELD_COLORS[f.c]).toArray(fieldMesh.instanceColor.array, k * 3); st[k] = f.stripes; k++;
    }
    fieldMesh.count = k; fieldMesh.instanceMatrix.needsUpdate = true; fieldMesh.instanceColor.needsUpdate = true; fieldGeo.attributes.aStripes.needsUpdate = true;
  }

  // ---------------------------------------------------------------- ships: sailing the lanes, and a fleet for a siege
  window.__stage = 'ships';
  const lanes = cfg.ships || [], fleets = cfg.events.map((e) => e.fleet || []), NS = lanes.length + fleets.reduce((n, f) => n + f.length, 0);
  const hullGeo = (() => {
    const sh = new THREE.Shape(); sh.moveTo(-0.5, -0.14); sh.lineTo(0.3, -0.14); sh.lineTo(0.5, 0); sh.lineTo(0.3, 0.14); sh.lineTo(-0.5, 0.14); sh.closePath();
    const g = new THREE.ExtrudeGeometry(sh, { depth: 0.16, bevelEnabled: false }); g.rotateX(-Math.PI / 2); return g;   // deck at y = 0.16
  })();
  const sailGeo = new THREE.BoxGeometry(0.03, 0.55, 0.42); sailGeo.translate(0, 0.16 + 0.32, 0);
  const hulls = new THREE.InstancedMesh(hullGeo, new THREE.MeshLambertMaterial({ color: 0x6e4b2e, flatShading: true }), Math.max(1, NS));
  const sails = new THREE.InstancedMesh(sailGeo, new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), Math.max(1, NS));
  sails.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(Math.max(1, NS) * 3), 3);
  for (const m of [hulls, sails]) { m.castShadow = true; m.frustumCulled = false; m.count = 0; scene.add(m); }
  function updateShips(t, pop, fxK) {
    if (!NS) return;
    const hm = hulls.instanceMatrix.array, sm = sails.instanceMatrix.array, sc = sails.instanceColor.array, active = shipsFor(pop, lanes.length);
    let k = 0;
    const put = (x, z, ang, L, r, g, b) => {
      const y = 0.15 + Math.sin(t * 1.3 + x * 0.05) * 0.15, cos = Math.cos(-ang), sin = Math.sin(-ang);
      writeM(hm, k * 16, cos, sin, L, L, L, x, y, z); writeM(sm, k * 16, cos, sin, L, L, L, x, y, z);
      sc[k * 3] = r; sc[k * 3 + 1] = g; sc[k * 3 + 2] = b; k++;
    };
    for (let i = 0; i < lanes.length; i++) {
      const v = clamp(active - i, 0, 1); if (v <= 0.02) continue;
      const p = shipAt(lanes[i], t); put(p.x, p.z, p.ang, 20 * lanes[i].size * v, 0.95, 0.93, 0.88);
    }
    fleets.forEach((fl, j) => {
      const v = fxK[j]?.camp || 0; if (v <= 0.02) return;
      fl.forEach(([x, z, ang], i) => { const hh = hash(i, 55 + j); put(x + Math.cos(ang) * 6 * Math.sin(t * 0.2 + i), z + Math.sin(ang) * 6 * Math.sin(t * 0.2 + i), ang, 26 * (0.8 + hh * 0.5) * v, 0.78 + hh * 0.15, 0.3 + hh * 0.2, 0.22); });
    });
    hulls.count = sails.count = k;
    for (const m of [hulls, sails]) m.instanceMatrix.needsUpdate = true; sails.instanceColor.needsUpdate = true;
  }

  // ---------------------------------------------------------------- events: the siege camp, fire, smoke and dust
  window.__stage = 'events';
  const camps = cfg.events.map((e) => e.camp || []), NC = camps.reduce((n, c) => n + c.length, 0);
  const tentGeo = new THREE.ConeGeometry(3.2, 4.2, 4); tentGeo.translate(0, 2.1, 0);
  const engineGeo = (() => {   // a siege engine / great gun: a timber frame with a beam
    const parts = [new THREE.BoxGeometry(9, 2.2, 6).translate(0, 1.1, 0), new THREE.BoxGeometry(1.2, 7, 1.2).translate(0, 5, -2.2), new THREE.BoxGeometry(1.2, 7, 1.2).translate(0, 5, 2.2), new THREE.BoxGeometry(12, 1, 1).rotateZ(0.5).translate(1, 7, 0)];
    const P = []; for (const q of parts) P.push(...q.toNonIndexed().attributes.position.array);
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); g.computeVertexNormals(); return g;
  })();
  const flagGeo = (() => { const a = new THREE.CylinderGeometry(0.2, 0.2, 9, 4).translate(0, 4.5, 0).toNonIndexed(), b = new THREE.BoxGeometry(4.5, 2.8, 0.15).translate(2.3, 7.4, 0).toNonIndexed(); const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute([...a.attributes.position.array, ...b.attributes.position.array], 3)); g.computeVertexNormals(); return g; })();
  const campMeshes = [[tentGeo, 0xe6dcc4], [engineGeo, 0x7a5a3c], [flagGeo, 0xb3202a]].map(([geo, c]) => {
    const m = new THREE.InstancedMesh(geo, new THREE.MeshLambertMaterial({ color: c, flatShading: true }), Math.max(1, NC)); m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false; m.count = 0; scene.add(m); return m;
  });
  function updateCamps(fxK) {
    const cnt = [0, 0, 0];
    camps.forEach((list, j) => {
      const v = fxK[j]?.camp || 0; if (v <= 0.02) return;
      for (const [x, y, z, rot, kind] of list) { const m = campMeshes[kind], s = (kind === 0 ? 1.4 + hash(cnt[kind], 9) * 0.7 : 1.9) * v; writeM(m.instanceMatrix.array, cnt[kind]++ * 16, Math.cos(rot), Math.sin(rot), s, s, s, x, y - 0.2, z); }
    });
    campMeshes.forEach((m, i) => { m.count = cnt[i]; m.instanceMatrix.needsUpdate = true; });
  }
  // soft round sprites: fire glows (added light), smoke and dust drift up and spread
  const MAXP = 9000, pointMat = (additive) => new THREE.ShaderMaterial({
    uniforms: { uScale: { value: H * 0.5 / Math.tan(((cfg.fov || 38) * Math.PI) / 360) } }, transparent: true, depthWrite: false,
    blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
    vertexShader: 'attribute float aSize; attribute vec4 aCol; uniform float uScale; varying vec4 vCol; void main(){ vCol = aCol; vec4 mv = modelViewMatrix * vec4(position, 1.0); gl_PointSize = clamp(aSize * uScale / -mv.z, 0.0, 400.0); gl_Position = projectionMatrix * mv; }',
    fragmentShader: 'varying vec4 vCol; void main(){ float d = length(gl_PointCoord - 0.5); float a = smoothstep(0.5, 0.05, d) * vCol.a; if (a < 0.01) discard; gl_FragColor = vec4(vCol.rgb, a); }',
  });
  const mkPoints = (additive) => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MAXP * 3), 3)); geo.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(MAXP), 1)); geo.setAttribute('aCol', new THREE.BufferAttribute(new Float32Array(MAXP * 4), 4));
    const p = new THREE.Points(geo, pointMat(additive)); p.frustumCulled = false; p.renderOrder = additive ? 3 : 2; scene.add(p); return p;
  };
  const smokeP = mkPoints(false), fireP = mkPoints(true);
  const seeds = cfg.events.map((e) => eventSeeds(e, e.kind === 'siege' ? 90 : 420).map((sd) => ({ ...sd, y: T.heightAt(sd.x, sd.z) })));
  function updateParticles(t, fxK) {
    const sp = smokeP.geometry.attributes, fp = fireP.geometry.attributes; let ns = 0, nf = 0;
    const smoke = (x, y, z, size, r, g, b, a) => { if (ns >= MAXP) return; sp.position.array.set([x, y, z], ns * 3); sp.aSize.array[ns] = size; sp.aCol.array.set([r, g, b, a], ns * 4); ns++; };
    const fire = (x, y, z, size, a) => { if (nf >= MAXP) return; fp.position.array.set([x, y, z], nf * 3); fp.aSize.array[nf] = size; fp.aCol.array.set([1.0, 0.45 + 0.3 * a, 0.12, a], nf * 4); nf++; };
    cfg.events.forEach((e, j) => {
      const k = fxK[j]; if (!k || k.fx <= 0.01) return;
      const siege = e.kind === 'siege', quake = e.kind === 'quake' || e.kind === 'flood', front = siege ? 2 : k.prog * 1.15;
      for (const sd of seeds[j]) {
        if (sd.f > front) continue;
        const since = front - sd.f, flick = 0.75 + 0.25 * Math.sin(t * 9 + sd.h * 40);
        if (siege) {   // shot landing on the walls and the houses behind them: a flash, then a cloud of dust and smoke
          const ph = (t / (2.6 + sd.h * 2) + sd.h * 7) % 1, a = (k.camp || 0) * (1 - ph);
          if (ph < 0.08) fire(sd.x, sd.y + 6, sd.z, 30 * (1 - ph / 0.08), a);
          if (ph < 0.6) smoke(sd.x + ph * 25, sd.y + 6 + ph * 45, sd.z, 20 + ph * 60, 0.62, 0.58, 0.52, a * 0.55);
          continue;
        }
        if (!quake) {
          const burn = k.fx * clamp(1 - since / 0.8, 0, 1);
          if (burn > 0.02) { fire(sd.x, sd.y + 6, sd.z, (30 + sd.h * 26) * flick, burn * 0.85); fire(sd.x, sd.y + 16, sd.z, (18 + sd.h * 14) * flick, burn * 0.55); }
        }
        for (let q = 0; q < (quake ? 1 : 2); q++) {   // puffs rise, grow and fade; the wind leans them into a column
          const age = (t * (quake ? 0.5 : 0.2) + sd.h * 3.7 + q * 0.5) % 1, a = k.fx * (1 - age * age) * (quake ? 0.4 : 0.6) * clamp(since * 6, 0, 1);
          if (a < 0.02) continue;
          const g = quake ? 0.72 : 0.22 + age * 0.4;
          smoke(sd.x + age * (quake ? 12 : 110), sd.y + 8 + age * (quake ? 22 : 220), sd.z - age * 40, (quake ? 34 : 40) + age * (quake ? 40 : 140), quake ? 0.76 : g, quake ? 0.68 : g * 0.98, quake ? 0.55 : g * 0.95, a);
        }
      }
      // the siege engines fire: a flash and a white puff every couple of seconds each
      for (const [x, y, z, , kind] of camps[j]) {
        if (kind !== 1) continue;
        const ph = ((t + hash(Math.round(x), Math.round(z)) * 2) / 2.2) % 1, a = (k.camp || 0) * (1 - ph);
        if (ph < 0.12) fire(x, y + 12, z, 34 * (1 - ph / 0.12), a);
        smoke(x + ph * 30, y + 14 + ph * 40, z, 24 + ph * 70, 0.94, 0.94, 0.92, a * 0.7);
      }
    });
    smokeP.geometry.setDrawRange(0, ns); fireP.geometry.setDrawRange(0, nf);
    for (const a of [sp.position, sp.aSize, sp.aCol, fp.position, fp.aSize, fp.aCol]) a.needsUpdate = true;
  }
  /** Where each event is on screen at t: prog (how far the destruction has spread, 0..1), fx (fire and smoke), camp. */
  const eventK = (t) => (tl.eventWindows || []).map((w) => ({
    prog: clamp((t - w.t0) / Math.max(0.5, (w.t1 - w.t0) * 0.75), 0, 1),
    fx: smooth((t - w.t0) / 0.6) * (1 - smooth((t - w.t1) / 2.2)),
    camp: smooth((t - w.t0 + 1.6) / 1.2) * (1 - smooth((t - w.t1) / 1.4)),
  }));

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
    const fxK = eventK(t), prog = fxK.map((k) => k.prog);
    updateHouses(need, s.year, prevStyle, curStyle, mixK, densityOf(s.pop, s.year), prog, prog.map((p) => p.toFixed(2)).join(','));
    updateTrees(need, s.year);
    updateFields(need);
    updateLandmarks(t);
    updateShips(t, s.pop, fxK);
    updateCamps(fxK);
    updateParticles(t, fxK);
    roadU.uNeed.value = need; groundU.uNeed.value = need;
    roadU.uLanes.value = (mixK < 0.5 ? styleOf(prevStyle) : styleOf(curStyle)).dense ? 0 : 1;
    // banners on walls, towers and the siege camp fly the colours of the era on screen
    const hb = hudAt(tl, t).badge, fc = hb && hb.flag ? parseFlag(hb.flag).colors?.[0] : null;
    if (fc) { const c = new THREE.Color(fc); for (const b of banners) b.color.copy(c); }
    // the besiegers fly the colours of the era that follows (the city's next masters)
    const nb = tl.badges[Math.min(tl.badges.length - 1, ei + 1)], nc = nb && nb.flag ? parseFlag(nb.flag).colors?.[0] : null;
    if (nc) campMeshes[2].material.color.set(nc);
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
  window.stats = () => ({ lots: NL, trees: NT, fields: NF, ships: NS, camp: NC, houses: walls.count, gpu: renderer.getContext().getParameter(renderer.getContext().VERSION) });
  window.__ready = true;
}

main().catch((e) => { window.__error = String(e && e.stack || e); });
