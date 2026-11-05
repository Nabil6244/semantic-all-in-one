// The page: the block world on the GPU, then window.renderFrame(t) draws one frame (3D + HUD) and returns a base64 JPEG.
// Every frame is a function of t alone (detail tiles are chosen from the camera at t; their data is all loaded up front),
// so frames can be rendered in any order or in parallel parts.
//
// Terrain levels (lib/lod.mjs): the world grid is always drawn; detail tiles (4x and 16x finer) are meshed on demand near
// the camera, kept in a small cache, and cross-faded with a screen-door dither against the level they replace.
// Finishing: sky dome, aerial perspective and height haze, animated water, motion blur by sub-frame accumulation on fast
// moves, one colour grade.
import * as THREE from '/three/three.module.min.js';
import { makeGeo } from '/lib/geo.mjs';
import { buildCells, buildChunk, SUN } from '/lib/terrain_mesh.mjs';
import { cameraAt, placeCamera } from '/lib/camera3d.mjs';
import { tintTable, blendTables, TINT_SIZE } from '/lib/territory.mjs';
import { buildSet, particlesAt, FINE, equipmentModel, sidesFromText } from '/lib/props.mjs';
import { at } from '/lib/timeline.mjs';
import { drawHud } from '/lib/hud.mjs';
import { LEVELS, TILE_BLOCKS, wantedTiles, parentKey, sampleHeight, tileKey } from '/lib/lod.mjs';
import { makeWorldData, addTile } from '/lib/world_data.mjs';
import { buildGlobe, buildClouds, placeGlobeCamera, globeWeight } from '/lib/globe.mjs';
import { buildDiorama, dioramaWeight, DIO, SET_N as DIO_SET_N } from '/lib/diorama.mjs';
import { lightAt } from '/lib/lighting.mjs';
import { mapEffectsAt } from '/lib/map_effects.mjs';

const CHUNK = 100, MAX_PARTICLES = 6000, MESH_CACHE = 72, MAX_HOLES = 48;
const SHUTTER = 0.5; // fraction of a frame the virtual shutter is open (180 degrees)
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = (a, b, v) => { const k = clamp((v - a) / (b - a), 0, 1); return k * k * (3 - 2 * k); };

const VERT = `
attribute vec4 cf; attribute float reg; attribute float sh; attribute float top;
uniform sampler2D tint;
varying vec3 vCol; varying vec3 vW; varying float vFace; varying float vWater; varying float vMat; varying float vTop; varying float vDist; varying vec4 vTint; varying float vSh;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vW = wp.xyz; vCol = cf.rgb; float code = floor(cf.a * 255.0 + 0.5); vFace = mod(code, 8.0); vWater = mod(floor(code / 8.0), 4.0); vMat = floor(code / 32.0); vTop = top;
  vTint = reg > 0.5 ? texture2D(tint, vec2((reg + 0.5) / ${TINT_SIZE}.0, 0.5)) : vec4(0.0);
  vSh = sh;
  vec4 mv = viewMatrix * wp; vDist = -mv.z;
  gl_Position = projectionMatrix * mv;
}`;
const FRAG = `
uniform vec3 sunDir; uniform vec3 fogCol; uniform vec3 skyCol; uniform float fogDensity; uniform float uK; uniform float uFade; uniform float uTime; uniform float uTintK;
uniform vec3 uAmb; uniform vec3 uSunCol; uniform float uSunK; uniform sampler2D uMask; uniform vec2 uWorld;
uniform vec4 holes[${MAX_HOLES}]; uniform float holeFade[${MAX_HOLES}]; uniform int holeCount;
varying vec3 vCol; varying vec3 vW; varying float vFace; varying float vWater; varying float vMat; varying float vTop; varying float vDist; varying vec4 vTint; varying float vSh;
float h21(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
// Block textures, drawn per 16x16-texel face (our own procedural art, not image files). mat: 0 grass, 1 forest,
// 2 sand, 3 stone, 4 snow, 5 sea, 6 river. depth = blocks below the column's top (walls only; 0 on top faces).
vec3 blockTexture(float mat, bool topFace, vec3 base, vec2 uv, float depth) {
  vec2 id = floor(uv), tx = floor(fract(uv) * 16.0);
  float n = h21(id * 17.13 + tx), n2 = h21(id * 3.71 + tx * 1.93 + 11.0);
  vec3 dirt = vec3(0.47, 0.34, 0.23) * (0.8 + 0.32 * n) * (n2 < 0.08 ? 0.72 : 1.0);
  vec3 stone = vec3(0.48, 0.48, 0.47) * (0.74 + 0.4 * n) * (n2 < 0.1 ? 0.72 : 1.0);
  float fringe = (3.0 + floor(h21(id + vec2(tx.x, 0.0) * 0.37) * 3.0)) / 16.0; // a ragged grass or snow edge
  vec3 grass = vec3(0.36, 0.58, 0.24), leaves = vec3(0.2, 0.42, 0.18);
  float speck = (0.72 + 0.46 * n) * (n2 < 0.14 ? 0.78 : 1.0) * (n2 > 0.93 ? 1.12 : 1.0);
  if (mat < 0.5) return topFace ? base * speck : (depth < fringe ? grass * speck : dirt);
  if (mat < 1.5) {
    vec3 leaf = (topFace ? base : leaves) * (0.7 + 0.5 * n) * (n2 < 0.2 ? 0.55 : 1.0);
    return topFace ? leaf : (depth < fringe + 0.25 ? leaf : dirt);
  }
  if (mat < 2.5) return vec3(0.84, 0.77, 0.55) * (0.88 + 0.2 * n) * (n2 < 0.06 ? 0.84 : 1.0);
  if (mat < 3.5) return stone;
  if (mat < 4.5) return topFace || depth < fringe ? vec3(0.93, 0.95, 0.97) * (0.93 + 0.08 * n) : stone;
  return base * (0.94 + 0.1 * n);
}
float bayer(vec2 p) {
  int x = int(mod(p.x, 4.0)), y = int(mod(p.y, 4.0)), i = x + y * 4;
  float m[16] = float[16](0., 8., 2., 10., 12., 4., 14., 6., 3., 11., 1., 9., 15., 7., 13., 5.);
  return (m[i] + 0.5) / 16.0;
}
void main() {
  float d = bayer(gl_FragCoord.xy);
  if (d >= uFade) discard;                                  // this level fading in
  for (int i = 0; i < ${MAX_HOLES}; i++) {                  // a finer level has taken over here
    if (i >= holeCount) break;
    vec4 r = holes[i];
    if (vW.x > r.x && vW.x < r.z && vW.z > r.y && vW.z < r.w && d < holeFade[i]) discard;
  }
  vec3 n = vFace < 0.5 ? vec3(0.0, 1.0, 0.0) : vFace < 1.5 ? vec3(1.0, 0.0, 0.0) : vFace < 2.5 ? vec3(-1.0, 0.0, 0.0) : vFace < 3.5 ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 0.0, -1.0);
  vec2 uv = (vFace < 0.5 ? vW.xz : (vFace < 2.5 ? vW.zy : vW.xy)) * uK;
  if (vFace > 0.5) uv.y = -uv.y;                             // side faces: texel rows count down from the block top
  vec2 fr = fract(uv); vec2 dd = min(fr, 1.0 - fr); vec2 fw = fwidth(uv);
  // texels fade to the face's mean colour where one texel is smaller than about a pixel (no shimmer on maps)
  float texK = 1.0 - smoothstep(0.04, 0.09, max(fw.x, fw.y));
  float depth = vFace > 0.5 ? max(0.0, vTop - vW.y * uK) : 0.0;
  vec3 c = mix(vCol, blockTexture(vMat, vFace < 0.5, vCol, uv, depth), texK);
  if (vTint.a > 0.0) { float l = dot(c, vec3(0.299, 0.587, 0.114)); c = mix(c, vTint.rgb * (0.5 + 0.95 * l), vTint.a * uTintK); }
  // drawn front lines (territory polygons) over the province tint
  vec4 fm = texture2D(uMask, vec2(vW.x / uWorld.x, vW.z / uWorld.y));
  if (fm.a > 0.003 && vWater < 0.5) { float l = dot(c, vec3(0.299, 0.587, 0.114)); c = mix(c, fm.rgb / max(fm.a, 0.003) * (0.5 + 0.95 * l), fm.a * uTintK); }
  float edge = 1.0 - smoothstep(0.0, 1.5 * max(fw.x, fw.y), min(dd.x, dd.y));
  float fadeE = 1.0 - smoothstep(0.06, 0.3, max(fw.x, fw.y));
  vec3 V = normalize(cameraPosition - vW);
  if (vWater > 0.5 && vFace < 0.5) {
    // water: a moving ripple normal, sun glint, sky reflection at grazing angles, a pale band at the shore
    vec2 q = vW.xz * uK;
    vec3 wn = normalize(vec3(sin(q.x * 1.7 + uTime * 1.3) * 0.05 + sin(q.y * 2.3 - uTime * 0.9) * 0.035, 1.0, cos(q.y * 1.9 + uTime * 1.1) * 0.05 + cos(q.x * 2.9 + uTime * 0.7) * 0.03));
    // glint: tight, and weaker on the finer levels so a close shot shows sparkle, not white blotches
    float spec = pow(max(dot(reflect(-sunDir, wn), V), 0.0), 140.0);
    float fres = pow(1.0 - max(dot(V, wn), 0.0), 4.0);
    c = mix(c, skyCol, fres * 0.35) + vec3(1.0, 0.95, 0.82) * spec * (0.45 / sqrt(uK));
    if (vWater > 1.5 && vWater < 2.5) c = mix(c, vec3(0.86, 0.9, 0.9), 0.18 + 0.08 * sin(uTime * 1.4 + q.x * 0.8 + q.y * 0.6));
    c *= (0.92 + 0.08 * max(dot(wn, sunDir), 0.0)) * (0.35 + 0.65 * uAmb);
  } else {
    c *= 1.0 - 0.1 * edge * fadeE;
    float diff = max(dot(n, sunDir), 0.0);
    c *= (0.5 * uAmb + 0.62 * diff * uSunK * uSunCol) * (0.3 + 0.75 * vSh);
  }
  // aerial perspective: distance haze that desaturates, plus a low haze that settles in valleys
  float a = 1.0 - exp(-pow(vDist * fogDensity, 1.5));
  float low = exp(-max(vW.y, 0.0) * 1.6 / max(uK, 1.0)) * (1.0 - exp(-vDist * fogDensity * 0.5)) * 0.35;
  float lum = dot(c, vec3(0.299, 0.587, 0.114));
  c = mix(c, vec3(lum), a * 0.35);
  gl_FragColor = vec4(mix(c, fogCol, clamp(a + low, 0.0, 1.0)), 1.0);
}`;
const QUAD_VERT = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }';
const ACCUM_FRAG = 'uniform sampler2D src; uniform float weight; varying vec2 vUv; void main() { gl_FragColor = vec4(texture2D(src, vUv).rgb * weight, 1.0); }';
const GRADE_FRAG = `
uniform sampler2D src; uniform float uTime; varying vec2 vUv;
void main() {
  vec3 c = texture2D(src, vUv).rgb * 1.04;
  c = mix(c, c * c * (3.0 - 2.0 * c), 0.22);                       // a gentle S-curve
  float l = dot(c, vec3(0.299, 0.587, 0.114));
  c = mix(vec3(l), c, 1.08);                                        // a little more colour
  c += (l - 0.5) * vec3(0.035, 0.004, -0.03);                       // warm highlights, cool shadows
  vec2 p = vUv - 0.5; c *= 1.0 - 0.2 * pow(length(p) * 1.3, 2.4);   // vignette
  float n = fract(sin(dot(gl_FragCoord.xy + uTime, vec2(12.9898, 78.233))) * 43758.5453);
  gl_FragColor = vec4(c + (n - 0.5) / 255.0, 1.0);                  // dither against banding
}`;
const SKY_VERT = 'varying vec3 vDir; void main() { vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }';
const SKY_FRAG = `
uniform vec3 top; uniform vec3 horizon; uniform vec3 sunDir; varying vec3 vDir;
void main() { float h = vDir.y; vec3 c = mix(horizon, top, smoothstep(-0.02, 0.55, h)); c += vec3(1.0, 0.86, 0.6) * pow(max(dot(vDir, sunDir), 0.0), 12.0) * 0.28; gl_FragColor = vec4(c, 1.0); }`;

/** Set blocks get the same texel treatment as the terrain: 16 texels per set block (1/48 cell), sized in world space so a
 *  big building and a small crate share one texel size; edges darken a little. Injected into three's Lambert shader. */
function blockTextured(mat, scale = FINE) {
  mat.userData.fade = { value: 1 }; // screen-door fade, the same dither as the terrain levels
  mat.onBeforeCompile = (sh) => {
    sh.uniforms.uFade = mat.userData.fade;
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vTp; varying vec3 vTn;')
      .replace('#include <project_vertex>', '#include <project_vertex>\n  vec4 tpw = modelMatrix * instanceMatrix * vec4(transformed, 1.0); vTp = tpw.xyz;\n  vTn = normalize(mat3(modelMatrix * instanceMatrix) * objectNormal);');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vTp; varying vec3 vTn; uniform float uFade;\nfloat bh(vec2 p) { p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }\nfloat bayer4(vec2 p) { int x = int(mod(p.x, 4.0)), y = int(mod(p.y, 4.0)), i = x + y * 4; float m[16] = float[16](0., 8., 2., 10., 12., 4., 14., 6., 3., 11., 1., 9., 15., 7., 13., 5.); return (m[i] + 0.5) / 16.0; }')
      .replace('void main() {', 'void main() {\n  if (bayer4(gl_FragCoord.xy) >= uFade) discard;')
      .replace('#include <color_fragment>', `#include <color_fragment>
  {
    vec3 an = abs(vTn); vec2 uv = (an.y > 0.5 ? vTp.xz : (an.x > 0.5 ? vTp.zy : vTp.xy)) * ${scale.toFixed(4)};
    vec2 fw = fwidth(uv); float k = 1.0 - smoothstep(0.04, 0.09, max(fw.x, fw.y));
    vec2 tx = floor(fract(uv) * 16.0), id = floor(uv);
    float n = bh(id * 17.13 + tx), e = min(min(fract(uv.x), 1.0 - fract(uv.x)), min(fract(uv.y), 1.0 - fract(uv.y)));
    diffuseColor.rgb *= mix(1.0, (0.84 + 0.3 * n) * (e < 0.07 ? 0.82 : 1.0), k);
  }`);
  };
  return mat;
}

async function main() {
  const cfg = await (await fetch('/config.json')).json();
  const { W, H, fps, timeline: tl, story } = cfg;
  const t0 = performance.now();
  const meta = await (await fetch('/world/meta.json')).json();
  const buf = async (n) => (await fetch(`/world/${n}`)).arrayBuffer();
  const coarse = { elev: new Int16Array(await buf('height.i16')), land: new Uint8Array(await buf('land.u8')), region: new Uint16Array(await buf('region.u16')) };
  const data = makeWorldData(meta, coarse);
  for (const t of cfg.tiles) addTile(data, { ...t, buf: await buf(`L${t.level}/${t.tx}_${t.tz}.bin`) });
  window.__stage = 'tiles loaded';
  const tLoad = performance.now() - t0;
  const geo = makeGeo(meta), { w, h } = meta, [, , , lat1] = meta.bbox;
  const ground = (x, z) => sampleHeight(data, x, z);

  const glc = document.createElement('canvas'); glc.width = W; glc.height = H;
  const renderer = new THREE.WebGLRenderer({ canvas: glc, antialias: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setSize(W, H, false); renderer.outputColorSpace = THREE.LinearSRGBColorSpace; renderer.autoClear = false;
  const out = document.createElement('canvas'); out.width = W; out.height = H; document.body.appendChild(out);
  const g2 = out.getContext('2d');
  const rtScene = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 });
  const rtAccum = new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType });

  const scene = new THREE.Scene();
  const FOG = new THREE.Color(0.74, 0.81, 0.87), SKY_TOP = new THREE.Color(0.33, 0.52, 0.78);
  scene.fog = new THREE.FogExp2(FOG, 0.002);
  const camera = new THREE.PerspectiveCamera(40, W / H, 0.05, 5000);
  const sun = new THREE.Vector3(...SUN).normalize();
  // set lighting matched to the terrain shader; three's Lambert divides by pi, hence the larger values
  const hemi = new THREE.HemisphereLight(0xe8eef4, 0x8a7a60, 1.9); scene.add(hemi);
  const dl = new THREE.DirectionalLight(0xfff0d8, 1.8); dl.position.copy(sun); scene.add(dl);
  const sky = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.ShaderMaterial({ vertexShader: SKY_VERT, fragmentShader: SKY_FRAG, side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { top: { value: SKY_TOP }, horizon: { value: FOG }, sunDir: { value: sun } } }));
  sky.renderOrder = -10; sky.frustumCulled = false; scene.add(sky);

  // territory tint: one TINT_SIZE x 1 texture, rewritten when the state changes
  const tables = Object.fromEntries(story.territories.map((s) => [s.key, tintTable(meta.regions, s)]));
  const empty = new Uint8Array(TINT_SIZE * 4);
  const tintTex = new THREE.DataTexture(new Uint8Array(TINT_SIZE * 4), TINT_SIZE, 1, THREE.RGBAFormat); tintTex.needsUpdate = true;
  const shared = { tint: { value: tintTex }, sunDir: { value: sun }, fogCol: { value: FOG }, skyCol: { value: SKY_TOP }, fogDensity: { value: 0.002 }, uTime: { value: 0 }, uTintK: { value: 1 },
    uAmb: { value: new THREE.Vector3(1, 1, 1) }, uSunCol: { value: new THREE.Vector3(1, 1, 1) }, uSunK: { value: 1 }, uMask: { value: null }, uWorld: { value: new THREE.Vector2(meta.w, meta.h) } };
  // front lines: territory states with polygon rules are painted into a world-sized mask, blended between states
  const maskCanvas = document.createElement('canvas'); maskCanvas.width = meta.w; maskCanvas.height = meta.h;
  const maskG = maskCanvas.getContext('2d'), maskTex = new THREE.CanvasTexture(maskCanvas); maskTex.flipY = false; shared.uMask.value = maskTex;
  const polyStates = Object.fromEntries(story.territories.map((st) => [st.key, (st.rules || []).filter((r) => r.polygon)]));
  const paintPolys = (rules, alpha) => { for (const r of rules) {
    const [cr, cg, cb] = [1, 3, 5].map((o) => parseInt(r.color.slice(o, o + 2), 16)); maskG.globalAlpha = alpha * (r.strength ?? 0.72); maskG.fillStyle = `rgb(${cr},${cg},${cb})`;
    maskG.beginPath(); r.polygon.forEach(([lo, la], i) => { const q = geo.toWorld(lo, la); i ? maskG.lineTo(q.x, q.z) : maskG.moveTo(q.x, q.z); }); maskG.closePath(); maskG.fill();
  } maskG.globalAlpha = 1; };
  let lastMask = '';
  const holeSets = { 0: { holes: { value: Array.from({ length: MAX_HOLES }, () => new THREE.Vector4()) }, holeFade: { value: new Float32Array(MAX_HOLES) }, holeCount: { value: 0 } } };
  holeSets[1] = { holes: { value: Array.from({ length: MAX_HOLES }, () => new THREE.Vector4()) }, holeFade: { value: new Float32Array(MAX_HOLES) }, holeCount: { value: 0 } };
  holeSets[2] = { holes: { value: [] }, holeFade: { value: new Float32Array(MAX_HOLES) }, holeCount: { value: 0 } };
  holeSets[2].holes.value = holeSets[0].holes.value.map(() => new THREE.Vector4());
  holeSets[3] = { holes: { value: holeSets[0].holes.value.map(() => new THREE.Vector4()) }, holeFade: { value: new Float32Array(MAX_HOLES) }, holeCount: { value: 0 } }; // dioramas: nothing finer cuts into them
  const terrainMat = (k, level) => new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: FRAG, uniforms: { ...shared, ...holeSets[level], uK: { value: k }, uFade: { value: 1 } } });

  const geometryOf = (c) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(c.pos, 3));
    g.setAttribute('cf', new THREE.BufferAttribute(c.col, 4, true));
    g.setAttribute('reg', new THREE.BufferAttribute(c.reg, 1));
    g.setAttribute('sh', new THREE.BufferAttribute(c.sh, 1, true));
    g.setAttribute('top', new THREE.BufferAttribute(c.top, 1));
    g.setIndex(new THREE.BufferAttribute(c.index, 1));
    return g;
  };
  const gpuBytes = (c) => c.pos.byteLength + c.col.byteLength + c.reg.byteLength + c.sh.byteLength + c.top.byteLength + c.index.byteLength;

  // level 0: the whole world, always present
  const latOf0 = (z) => lat1 - (z + 0.5) * meta.res;
  const cells0 = buildCells(coarse.elev, coarse.land, w, h, { k: 1, latOf: latOf0 });
  window.__stage = 'world cells built';
  const mat0 = terrainMat(1, 0);
  let quads0 = 0, bytes0 = 0;
  for (let z0 = 0; z0 < h; z0 += CHUNK) for (let x0 = 0; x0 < w; x0 += CHUNK) {
    const c = buildChunk(cells0, coarse.region, w, h, x0, z0, Math.min(w, x0 + CHUNK), Math.min(h, z0 + CHUNK));
    if (!c.quads) continue;
    quads0 += c.quads; bytes0 += gpuBytes(c);
    const g = geometryOf(c); g.boundingSphere = new THREE.Sphere(new THREE.Vector3(x0 + CHUNK / 2, 10, z0 + CHUNK / 2), CHUNK * 0.75 + 40);
    scene.add(new THREE.Mesh(g, mat0));
  }
  // the sea beyond the world's edge: one quad of deep water drawn by the terrain shader itself, so it shades like the world's
  const E = 12000, seaGeo = geometryOf({ pos: Float32Array.from([-E, -3.01, -E, w + E, -3.01, -E, w + E, -3.01, h + E, -E, -3.01, h + E]),
    col: Uint8Array.from([28, 74, 132, 168, 28, 74, 132, 168, 28, 74, 132, 168, 28, 74, 132, 168]), reg: new Uint16Array(4), sh: Uint8Array.from([255, 255, 255, 255]), top: new Int16Array(4), index: Uint32Array.from([0, 2, 1, 0, 3, 2]) });
  const sea = new THREE.Mesh(seaGeo, mat0); sea.frustumCulled = false; scene.add(sea);

  // detail tiles: cells built once per tile (sets and meshes share them); meshes on demand, least recently used dropped
  const cellCache = new Map(), meshes = new Map(), stats = { initMs: 0, loadMs: Math.round(tLoad), quads0, gpu: '', frames: 0, frameMs: [], tileBuilds: 0, tileBuildMs: 0, maxActive: { 1: 0, 2: 0 }, subframes: [] };
  const cellsOf = (key) => {
    let c = cellCache.get(key); if (c) return c;
    const t = data.tiles.get(key), L = LEVELS.find((x) => x.level === t.level), res = meta.res / L.k;
    const tlat = lat1 - t.tz * L.tileCells * meta.res;
    c = buildCells(t.elev, t.land, TILE_BLOCKS, TILE_BLOCKS, { k: L.k, latOf: (z) => tlat - (z + 0.5) * res, gx: t.tx * TILE_BLOCKS, gz: t.tz * TILE_BLOCKS });
    cellCache.set(key, c); return c;
  };
  function meshOf(key) {
    let m = meshes.get(key);
    if (m) return m;
    const b0 = performance.now(), t = data.tiles.get(key), L = LEVELS.find((x) => x.level === t.level);
    const c = buildChunk(cellsOf(key), t.region, TILE_BLOCKS, TILE_BLOCKS, 0, 0, TILE_BLOCKS, TILE_BLOCKS, -4 * L.k);
    const g = geometryOf(c);
    const mesh = new THREE.Mesh(g, terrainMat(L.k, L.level));
    mesh.scale.setScalar(1 / L.k); mesh.position.set(t.tx * L.tileCells, 0, t.tz * L.tileCells);
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(TILE_BLOCKS / 2, 20 * L.k, TILE_BLOCKS / 2), TILE_BLOCKS * 0.75 + 40 * L.k);
    mesh.visible = false; scene.add(mesh);
    m = { mesh, bytes: gpuBytes(c), used: 0, level: L.level, rect: [t.tx * L.tileCells, t.tz * L.tileCells, (t.tx + 1) * L.tileCells, (t.tz + 1) * L.tileCells] };
    meshes.set(key, m); stats.tileBuilds++; stats.tileBuildMs += performance.now() - b0;
    m.used = useTick;
    return m;
  }
  /** Drop least recently used meshes beyond the cache size, never one this frame uses. */
  function trimCache() {
    if (meshes.size <= MESH_CACHE) return;
    const old = [...meshes.entries()].filter(([, v]) => v.used < useTick).sort((a, b) => a[1].used - b[1].used);
    for (const [key, v] of old.slice(0, meshes.size - MESH_CACHE)) { scene.remove(v.mesh); v.mesh.geometry.dispose(); v.mesh.material.dispose(); meshes.delete(key); }
  }
  let useTick = 0;
  function updateLod(camPos, extra = []) {
    useTick++;
    const want = wantedTiles(camPos, w, h).filter((x) => data.tiles.has(x.key));
    const keys = new Set(want.map((x) => x.key));
    const active = want.filter((x) => x.level === 1 || (keys.has(parentKey(x.level, x.tx, x.tz))));
    for (const m of meshes.values()) m.mesh.visible = false;
    for (const x of active) { const m = meshes.get(x.key); if (m) m.used = useTick; }
    const holes = { 0: [...extra], 1: [...extra], 2: [...extra] };
    for (const x of active) {
      const m = meshOf(x.key); m.mesh.visible = true; m.used = useTick; m.mesh.material.uniforms.uFade.value = x.fade;
      holes[x.level - 1].push([m.rect, x.fade]);
    }
    for (const lvl of [0, 1, 2]) {
      const hs = holeSets[lvl], list = holes[lvl].slice(0, MAX_HOLES);
      list.forEach(([r, f], i) => { hs.holes.value[i].set(r[0], r[1], r[2], r[3]); hs.holeFade.value[i] = f; });
      hs.holeCount.value = list.length;
    }
    trimCache();
    const n1 = holes[0].length - extra.length, n2 = holes[1].length - extra.length;
    stats.maxActive[1] = Math.max(stats.maxActive[1], n1); stats.maxActive[2] = Math.max(stats.maxActive[2], n2);
    return { L1: n1, L2: n2 };
  }

  // ground scenes: each one is a human-scale diorama (lib/diorama.mjs) with its recipe's blocks standing on it
  const unit = new THREE.BoxGeometry(1, 1, 1); unit.translate(0, 0.5, 0); // centred on x/z, base at y = 0
  window.__stage = 'world meshes built';
  await document.fonts.load('700 20px "HudFont"'); await document.fonts.load('400 20px "HudFont"'); // signs are drawn in it
  const sites = [];
  const m4 = new THREE.Matrix4(), col = new THREE.Color(), q = new THREE.Quaternion(), yAxis = new THREE.Vector3(0, 1, 0), vp = new THREE.Vector3(), vs = new THREE.Vector3();
  const signTexture = (text) => {
    const cv = document.createElement('canvas'); cv.width = 512; cv.height = 128; const g = cv.getContext('2d');
    g.fillStyle = '#efefe8'; g.fillRect(0, 0, 512, 128); g.fillStyle = '#9a9a92'; g.fillRect(0, 0, 512, 8); g.fillRect(0, 120, 512, 8);
    g.font = '700 64px "HudFont"'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#8c1f1a'; g.fillText(text.toUpperCase(), 256, 68, 480);
    const tx = new THREE.CanvasTexture(cv); tx.magFilter = THREE.NearestFilter; return tx;
  };
  for (const b of tl.beats) {
    if (!b.site) continue;
    window.__stage = `set ${b.id}`;
    const p = geo.toWorld(b.lon, b.lat), sb = story.beats[b.i];
    const dio = buildDiorama(data, p.x, p.z, b.seed);
    const dc = buildChunk(dio.cells, new Uint16Array(dio.N * dio.N), dio.N, dio.N, 0, 0, dio.N, dio.N, dio.edgeFloor);
    const dg = geometryOf(dc); dg.boundingSphere = new THREE.Sphere(new THREE.Vector3(dio.N / 2, 0, dio.N / 2), dio.N);
    const dmesh = new THREE.Mesh(dg, terrainMat(DIO, 3)); dmesh.scale.setScalar(1 / DIO); dmesh.position.set(dio.x0, dio.meshY, dio.z0); dmesh.visible = false; scene.add(dmesh);
    // the outer ring: the same real relief at 4x coarser blocks, ~7 km across, a hair below the inner diorama, so the
    // descent always passes over continuous ground while the detail levels hand over
    const OU = DIO / 4, outer = buildDiorama(data, p.x, p.z, b.seed, { units: OU, n: 0, margin: 200, eRef: dio.eRef, meshY: dio.meshY - 0.7 / DIO });
    const oc = buildChunk(outer.cells, new Uint16Array(outer.N * outer.N), outer.N, outer.N, 0, 0, outer.N, outer.N, outer.edgeFloor);
    const og = geometryOf(oc); og.boundingSphere = new THREE.Sphere(new THREE.Vector3(outer.N / 2, 0, outer.N / 2), outer.N * 4);
    const omesh = new THREE.Mesh(og, terrainMat(OU, 3)); omesh.scale.set(1 / OU, 1 / DIO, 1 / OU); omesh.position.set(outer.x0, outer.meshY, outer.z0); omesh.visible = false; scene.add(omesh);
    // before firearms (a story year before 1800): Roman-era armies and kit; the two sides from the place and narration
    const year = Number(String(sb.date || '').slice(0, -3)), era = Number.isFinite(year) && year < 1800 ? 'ancient' : undefined;
    const ctx = { ground: dio.ground, factions: sb.factions || undefined, names: sb.names || [], signs: sb.signs || [], era, landmark: sb.landmark || undefined,
      sides: era ? sidesFromText(`${sb.place || ''} ${(sb.sentences || []).join(' ')}`) || undefined : undefined };
    const set = buildSet(b.site, b.seed, DIO_SET_N, ctx);
    const smat = blockTextured(new THREE.MeshLambertMaterial(), DIO);
    const mesh = new THREE.InstancedMesh(unit, smat, Math.max(1, set.boxes.length));
    set.boxes.forEach((bx, i) => {
      const wp = dio.toWorld(bx.x, bx.y, bx.z);
      vp.set(wp.x, wp.y, wp.z); vs.set(bx.sx / DIO, bx.sy / DIO, bx.sz / DIO); q.setFromAxisAngle(yAxis, bx.rot || 0);
      mesh.setMatrixAt(i, m4.compose(vp, q, vs)); mesh.setColorAt(i, col.setRGB(bx.c[0] / 255, bx.c[1] / 255, bx.c[2] / 255));
    });
    mesh.visible = false; scene.add(mesh);
    const signs = new THREE.Group();
    for (const sg of set.signs || []) {
      const pm = new THREE.Mesh(new THREE.PlaneGeometry(sg.w / DIO, sg.h / DIO), new THREE.MeshLambertMaterial({ map: signTexture(sg.text), side: THREE.DoubleSide }));
      const wp = dio.toWorld(sg.x, sg.y, sg.z); pm.position.set(wp.x, wp.y, wp.z); pm.rotation.y = sg.rot || 0; signs.add(pm);
    }
    signs.visible = false; scene.add(signs);
    const ch = dio.heightAt(p.x, p.z) ?? ground(p.x, p.z);
    // the tallest block over each diorama cell (buildings, trees, vehicles): the camera keeps clear of these, not just the ground
    const tops = new Float32Array(dio.N * dio.N).fill(-1e9);
    for (const bx of set.boxes) {
      const top = bx.y + bx.sy, r = Math.max(bx.sx, bx.sz) / 2;
      for (let zz = Math.floor(bx.z - r); zz <= Math.ceil(bx.z + r); zz++) for (let xx = Math.floor(bx.x - r); xx <= Math.ceil(bx.x + r); xx++) {
        const i = xx + dio.M, j = zz + dio.M; if (i >= 0 && j >= 0 && i < dio.N && j < dio.N) tops[j * dio.N + i] = Math.max(tops[j * dio.N + i], top);
      }
    }
    const clearAt = (x, z) => {
      const hgt = dio.heightAt(x, z); if (hgt == null) return null;
      const i = Math.floor((x - dio.x0) * DIO), j = Math.floor((z - dio.z0) * DIO), tp = tops[j * dio.N + i];
      return tp > -1e8 ? Math.max(hgt, dio.meshY + tp / DIO) : hgt;
    };
    // where the set's action is (its focus: the clash, the market, the landmark, the room), as an offset from the diorama centre
    const fw = set.focus ? dio.toWorld(set.focus[0], 0, set.focus[1]) : null, focusOff = fw ? { x: fw.x - p.x, z: fw.z - p.z } : { x: 0, z: 0 };
    sites.push({ beat: b, set, dio, outer, dmesh, omesh, mesh, smat, signs, clearAt, labels: set.labels || [], center: new THREE.Vector3(p.x, ch, p.z), dk: 0, focusOff });
  }
  stats.dioramas = sites.length;
  window.__stage = 'sets built';
  // the block globe (only when the story opens, travels or ends on it): one voxel per instanced cube, block clouds above
  let globe = null;
  if (story.beats.some((b) => b.rung === 'globe')) {
    const gm = await (await fetch('/globe/meta.json')).json();
    const gb = async (n) => (await fetch(`/globe/${n}`)).arrayBuffer();
    const gv = buildGlobe(gm, new Int16Array(await gb('height.i16')), new Uint8Array(await gb('land.u8')), new Uint8Array(await gb('surf.u8')));
    const gScene = new THREE.Scene(); gScene.background = new THREE.Color(0.11, 0.13, 0.19);
    gScene.add(new THREE.HemisphereLight(0xdfe6f0, 0x30343c, 1.6)); const gl2 = new THREE.DirectionalLight(0xfff2dc, 2.2); gl2.position.set(0.7, 0.45, 0.6); gScene.add(gl2);
    const cube = new THREE.BoxGeometry(1, 1, 1);
    const vox = new THREE.InstancedMesh(cube, blockTextured(new THREE.MeshLambertMaterial(), 1), gv.count);
    const gm4 = new THREE.Matrix4(), gc = new THREE.Color();
    for (let i = 0; i < gv.count; i++) { gm4.makeTranslation(gv.pos[i * 3], gv.pos[i * 3 + 1], gv.pos[i * 3 + 2]); vox.setMatrixAt(i, gm4); vox.setColorAt(i, gc.setRGB(gv.col[i * 3] / 255, gv.col[i * 3 + 1] / 255, gv.col[i * 3 + 2] / 255)); }
    gScene.add(vox);
    const cl = buildClouds(), clouds = new THREE.InstancedMesh(cube, new THREE.MeshLambertMaterial({ color: 0xf4f6f8 }), cl.length);
    cl.forEach((p, i) => { gm4.makeTranslation(p.x, p.y, p.z); clouds.setMatrixAt(i, gm4); });
    const cloudGroup = new THREE.Group(); cloudGroup.add(clouds); gScene.add(cloudGroup);
    const gCam = new THREE.PerspectiveCamera(40, W / H, 1, 4000);
    globe = { scene: gScene, cam: gCam, clouds: cloudGroup, voxels: gv.count };
    stats.globeVoxels = gv.count;
  }
  function drawGlobe(t) {
    const c = cameraAt(tl.camera, t), g = placeGlobeCamera(c);
    globe.cam.position.set(g.pos.x, g.pos.y, g.pos.z); globe.cam.up.set(g.up.x, g.up.y, g.up.z); globe.cam.near = g.near; globe.cam.far = g.far;
    globe.cam.updateProjectionMatrix(); globe.cam.lookAt(0, 0, 0);
    globe.clouds.rotation.y = t * 0.012; // clouds drift slowly around the planet
    renderer.setRenderTarget(rtScene); renderer.setClearColor(globe.scene.background); renderer.clear(); renderer.render(globe.scene, globe.cam);
  }
  // photo cards: every picture is loaded before the first frame (a card with no readable picture is simply not shown)
  const cardImgs = new Map();
  for (const c of tl.cards || []) {
    if (!c.url) continue;
    try { const r = await fetch(c.url); if (r.ok) cardImgs.set(c.id, await createImageBitmap(await r.blob())); } catch { /* the card is skipped */ }
  }
  const cardTilt = (id) => { let h = 7; for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) | 0; return ((Math.abs(h) % 5) - 2) * 0.6; };
  // museum objects: each one turns on a plinth in its own small scene, drawn into the HUD inset; a still of each is its
  // item-bar icon
  const museum = [];
  if ((tl.museum || []).length) {
    const MS = 256, rtM = new THREE.WebGLRenderTarget(MS, MS), px = new Uint8Array(MS * MS * 4);
    for (const m of tl.museum) {
      const model = equipmentModel(m.item, 7);
      const ms = new THREE.Scene(); ms.background = new THREE.Color(0.78, 0.78, 0.76);
      ms.add(new THREE.HemisphereLight(0xffffff, 0x707070, 2.2)); const ml = new THREE.DirectionalLight(0xffffff, 1.6); ml.position.set(1, 1.4, 0.8); ms.add(ml);
      const grp = new THREE.Group(), cube = new THREE.BoxGeometry(1, 1, 1); cube.translate(0, 0.5, 0);
      const pmat = blockTextured(new THREE.MeshLambertMaterial(), 16);
      const size = model ? Math.max(model.w || 2, model.d || 2, model.h || 1) : 2;
      const plinth = new THREE.Mesh(cube, new THREE.MeshLambertMaterial({ color: 0xf2f2ee })); plinth.scale.set(size * 1.2, size * 0.12, size * 1.2); plinth.position.y = -size * 0.12; grp.add(plinth);
      for (const pt of model ? model.parts : []) {
        const mesh = new THREE.Mesh(cube, pmat.clone()); mesh.material.color.setRGB(pt.c[0] / 255, pt.c[1] / 255, pt.c[2] / 255);
        mesh.scale.set(pt.sx, pt.sy, pt.sz); mesh.position.set(pt.x, pt.y, pt.z); mesh.rotation.y = pt.rot || 0; grp.add(mesh);
      }
      ms.add(grp);
      const mc = new THREE.PerspectiveCamera(30, 1, 0.05, 200); mc.position.set(size * 1.6, size * 1.1, size * 1.6); mc.lookAt(0, size * 0.2, 0);
      const cv = document.createElement('canvas'); cv.width = MS; cv.height = MS; const cg = cv.getContext('2d'), img = cg.createImageData(MS, MS);
      const shoot = (angle) => {
        grp.rotation.y = angle; renderer.setRenderTarget(rtM); renderer.setClearColor(ms.background); renderer.clear(); renderer.render(ms, mc);
        renderer.readRenderTargetPixels(rtM, 0, 0, MS, MS, px);
        for (let y = 0; y < MS; y++) img.data.set(px.subarray((MS - 1 - y) * MS * 4, (MS - y) * MS * 4), y * MS * 4); // the target is bottom-up
        cg.putImageData(img, 0, 0);
      };
      shoot(0.7);
      const icon = document.createElement('canvas'); icon.width = icon.height = 64; icon.getContext('2d').drawImage(cv, 0, 0, 64, 64);
      museum.push({ ...m, shoot, canvas: cv, icon });
    }
  }
  const parts = new THREE.InstancedMesh(unit, new THREE.MeshBasicMaterial({ fog: true }), MAX_PARTICLES); // unlit: fire glows at night
  parts.count = 0; parts.frustumCulled = false; scene.add(parts);

  // place tags: story labels plus set names
  const tagPts = story.labels.map((l) => { const p = geo.toWorld(l.lon, l.lat); return { ...l, v: new THREE.Vector3(p.x, ground(p.x, p.z) + 0.6, p.z) }; });
  for (const s of sites) {
    tagPts.push({ site: s, name: story.beats[s.beat.i].place, kind: 'site', min_alt: 0, max_alt: 40, v: new THREE.Vector3(s.center.x, s.center.y + 40 / DIO, s.center.z - 60 / DIO) });
    for (const l of s.labels) { const wp = s.dio.toWorld(l.x, l.y, l.z); tagPts.push({ site: s, name: l.text, kind: 'person', min_alt: 0, max_alt: 0.6, v: new THREE.Vector3(wp.x, wp.y, wp.z) }); }
  }

  const legendAt = (t) => { const s = at(tl.territory, t); const st = s && story.territories.find((x) => x.key === s.key); return st ? st.legend : []; };
  let lastTint = '';
  function setTint(t) {
    const cur = at(tl.territory, t); if (!cur) { if (lastTint !== 'none') { tintTex.image.data.set(empty); tintTex.needsUpdate = true; lastTint = 'none'; } return; }
    const idx = tl.territory.indexOf(cur), prev = idx > 0 ? tables[tl.territory[idx - 1].key] : empty;
    const k = clamp((t - cur.t) / 1.4, 0, 1), sig = `${cur.key}:${k.toFixed(3)}`;
    if (sig === lastTint) return;
    tintTex.image.data.set(k >= 1 ? tables[cur.key] || empty : blendTables(prev, tables[cur.key] || empty, k)); tintTex.needsUpdate = true; lastTint = sig;
  }
  const clr = cfg.clearance;
  const clearanceAt = (t) => { if (!clr) return 0; const f = clamp(t / clr.dt, 0, clr.values.length - 1), i = Math.floor(f), j = Math.min(i + 1, clr.values.length - 1); return clr.values[i] + (clr.values[j] - clr.values[i]) * (f - i); };

  const aim = cfg.aimGround;
  const aimAt = (t) => { if (!aim) return null; const f = clamp(t / aim.dt, 0, aim.values.length - 1), i = Math.floor(f), j = Math.min(i + 1, aim.values.length - 1); return aim.values[i] + (aim.values[j] - aim.values[i]) * (f - i); };
  /** The diorama a camera state is over, and how far it has taken over (0..1). */
  function currentBeat(t) { let cur = -1; for (const b of tl.beats) if ((b.travelT0 + b.travelT1) / 2 <= t) cur = b.i; else break; return cur; }
  function dioramaAt(c, t) {
    const tw = geo.toWorld(c.lon, c.lat);
    // several scenes can stand on one spot (a story set in one city): the story's current beat decides which one shows. It changes
    // half-way through the move into a beat, at the top of the arc, where no diorama is drawn.
    const cur = currentBeat(t);
    let best = null, k = 0, bestRank = -1e9;
    for (const s of sites) {
      const d = Math.hypot(s.center.x - tw.x, s.center.z - tw.z), kk = dioramaWeight(c.alt) * (1 - smooth(0.45, 1.4, d));
      if (kk <= 0) continue;
      // the current beat's own set first; then the latest one already passed; then the next ones in order
      const rank = s.beat.i === cur ? 1e6 : s.beat.i < cur ? s.beat.i : -s.beat.i;
      if (rank > bestRank) { bestRank = rank; k = kk; best = s; }
    }
    return { site: best, k };
  }
  function placeAt(t) {
    // the camera aims at the smoothed ground of render.mjs's table (never at a raw block height, which steps); over a
    // diorama it aims at, and keeps clear of, the diorama's own surface
    const c = cameraAt(tl.camera, t), dz0 = dioramaAt(c, t), g = aimAt(t);
    // over a diorama the whole framing slides onto the set's focus, as far as the diorama has taken over (the director only
    // knows the beat's point; the set decides where its action stands)
    const fo = dz0.site ? dz0.site.focusOff : { x: 0, z: 0 }, ox = fo.x * dz0.k, oz = fo.z * dz0.k;
    const tw0 = geo.toWorld(c.lon, c.lat), tw = { x: tw0.x + ox, z: tw0.z + oz }, dioH = dz0.site ? dz0.site.dio.heightAt(tw.x, tw.z) : null;
    const aimY = (g == null ? ground(tw.x, tw.z) : g) * (1 - dz0.k) + (dioH ?? g ?? 0) * dz0.k;
    const pl = placeCamera(c, geo, () => aimY);
    pl.pos.x += ox; pl.pos.z += oz; pl.target.x += ox; pl.target.z += oz;
    let near = 0;
    for (let dz = -1; dz <= 1; dz++) for (let dx = -1; dx <= 1; dx++) near = Math.max(near, ground(pl.pos.x + dx * 0.15, pl.pos.z + dz * 0.15));
    // the coarse terrain's own floor fades out as a diorama takes over (render.mjs's table already does the same)
    let floor = Math.max(clearanceAt(t) + (0.12 + pl.distance * 0.12) * (1 - dz0.k), (near + 0.05) * (1 - dz0.k) - 1e3 * dz0.k);
    if (dz0.site) {
      let dm = -1e9;
      for (let k = 0; k <= 4; k++) for (let dz = -1; dz <= 1; dz++) for (let dx = -1; dx <= 1; dx++) {
        const px = pl.pos.x + (pl.target.x - pl.pos.x) * k / 4 + dx * 12 / DIO, pz = pl.pos.z + (pl.target.z - pl.pos.z) * k / 4 + dz * 12 / DIO, hh = dz0.site.clearAt(px, pz);
        if (hh != null) dm = Math.max(dm, hh);
      }
      const dioFloor = dm > -1e9 ? dm + 6 / DIO + pl.distance * 0.1 : floor;
      if (dz0.k > 0.02) floor = Math.max(floor, dioFloor);
      // the diorama's ground and its buildings hold from the moment it starts to appear
    }
    pl.pos.y = Math.max(pl.pos.y, floor);
    // the camera's real distance to what it looks at (after any lift), for fog and depth range
    pl.distance = Math.max(0.004, Math.hypot(pl.pos.x - pl.target.x, pl.pos.y - pl.target.y, pl.pos.z - pl.target.z));
    pl.far = Math.max(pl.far, pl.distance * 8 + 400);
    return { c, pl, dio: dz0 };
  }
  function drawScene(t) {
    const { c, pl, dio } = placeAt(t);
    camera.position.set(pl.pos.x, pl.pos.y, pl.pos.z); camera.up.set(pl.up.x, pl.up.y, pl.up.z);
    camera.near = pl.near; camera.far = pl.far; camera.updateProjectionMatrix(); camera.lookAt(pl.target.x, pl.target.y, pl.target.z);
    sky.position.copy(camera.position); sky.scale.setScalar(pl.far * 0.9);
    // over a diorama the haze thickens, so its edges (and the coarser world beyond) sink into it
    const dens = (0.14 / pl.distance) * (1 + 1.0 * dio.k); shared.fogDensity.value = dens; scene.fog.density = dens * 0.8; shared.uTime.value = t;
    shared.uTintK.value = smooth(12, 60, c.alt); // faction colour is a map device: ground scenes keep their natural colours
    // light preset (day, dawn, sunset, night, fog), blended between beats
    const L = lightAt(tl.lights, t);
    shared.uAmb.value.set(...L.amb); shared.uSunCol.value.set(...L.sun); shared.uSunK.value = L.sunK;
    FOG.setRGB(...L.fog); SKY_TOP.setRGB(...L.sky); shared.fogDensity.value *= L.haze; scene.fog.density *= L.haze;
    hemi.intensity = L.hemi; dl.intensity = L.dir; dl.color.setRGB(...L.sun);
    const ambLum = 0.3 * L.amb[0] + 0.59 * L.amb[1] + 0.11 * L.amb[2];
    // front-line mask for the current territory state (only redrawn when it changes)
    {
      const cur = at(tl.territory, t), idx = cur ? tl.territory.indexOf(cur) : -1, k = cur ? clamp((t - cur.t) / 1.4, 0, 1) : 0;
      const prevKey = idx > 0 ? tl.territory[idx - 1].key : null, sig = `${prevKey}|${cur ? cur.key : ''}|${k.toFixed(2)}`;
      if (sig !== lastMask && (cur && (polyStates[cur.key]?.length || (prevKey && polyStates[prevKey]?.length)) || lastMask)) {
        maskG.clearRect(0, 0, meta.w, meta.h);
        if (prevKey && k < 1) paintPolys(polyStates[prevKey] || [], 1 - k);
        if (cur) paintPolys(polyStates[cur.key] || [], k);
        maskTex.needsUpdate = true; lastMask = sig;
      }
    }
    setTint(t);
    const holes = [];
    for (const s of sites) {
      const k = s === dio.site ? dio.k : 0;
      s.dk = k; s.dmesh.visible = s.omesh.visible = s.mesh.visible = s.signs.visible = k > 0.001;
      s.dmesh.material.uniforms.uFade.value = k; s.omesh.material.uniforms.uFade.value = k; s.smat.userData.fade.value = k;
      // the cut-out widens as the diorama takes over: the coarser world (taller, by its height exaggeration) leaves the frame
      // ...but never past the outer ring, so there is always ground under the camera
      if (k > 0.001) holes.push([s.outer.rect, k]);
    }
    const lod = updateLod(camera.position, holes);
    let n = 0;
    for (const s of sites) {
      if (s.dk <= 0.001) continue;
      for (const p of particlesAt(s.set, t)) {
        if (n >= MAX_PARTICLES) break;
        // a cube particle shrinks to nothing as it fades (no solid box vanishing in one frame); a shaped one follows g
        const k = (p.sx ? 1 : Math.sqrt(Math.max(0, p.a ?? 1))) * (p.g ?? 1);
        if (k <= 0.001) continue;
        const sx = (p.sx ?? p.s) * k, sy = (p.sy ?? p.s) * k, sz = (p.sz ?? p.s) * k;
        const wp = s.dio.toWorld(p.x, p.y, p.z); vp.set(wp.x, wp.y, wp.z); vs.set(sx / DIO, sy / DIO, sz / DIO); q.setFromAxisAngle(yAxis, p.rot || 0);
        const glow = p.c[0] > 200 && p.c[1] > 60 && p.c[2] < 140 ? 1 : ambLum; // fire stays bright, everything else follows the light
        parts.setMatrixAt(n, m4.compose(vp, q, vs)); parts.setColorAt(n, col.setRGB(p.c[0] / 255 * glow, p.c[1] / 255 * glow, p.c[2] / 255 * glow)); n++;
      }
    }
    // map-scale effects (fire puffs, smoke, aircraft) for the map and oblique views
    const mapK = smooth(2, 8, c.alt); // map-scale effects belong to map views: they fade out as the camera gets low
    for (const p of mapK > 0.001 ? mapEffectsAt(tl.effects || [], t, geo, ground, pl.distance) : []) {
      if (n >= MAX_PARTICLES) break;
      const k = (p.sx ? Math.max(0, p.a ?? 1) : Math.sqrt(Math.max(0, p.a ?? 1))) * mapK;
      if (k <= 0.001) continue;
      vp.set(p.x, p.y, p.z); vs.set((p.sx ?? p.s) * k, (p.sy ?? p.s) * k, (p.sz ?? p.s) * k); q.setFromAxisAngle(yAxis, p.rot || 0);
      const glow = p.c[0] > 200 && p.c[1] > 60 && p.c[2] < 140 ? 1 : ambLum;
      parts.setMatrixAt(n, m4.compose(vp, q, vs)); parts.setColorAt(n, col.setRGB(p.c[0] / 255 * glow, p.c[1] / 255 * glow, p.c[2] / 255 * glow)); n++;
    }
    parts.count = n; parts.instanceMatrix.needsUpdate = true; if (parts.instanceColor) parts.instanceColor.needsUpdate = true;
    renderer.setRenderTarget(rtScene); renderer.setClearColor(FOG); renderer.clear(); renderer.render(scene, camera);
    return { c, pl, lod };
  }

  // full-screen passes
  const quadCam = new THREE.Camera();
  const accumMat = new THREE.ShaderMaterial({ vertexShader: QUAD_VERT, fragmentShader: ACCUM_FRAG, uniforms: { src: { value: rtScene.texture }, weight: { value: 1 } }, blending: THREE.AdditiveBlending, transparent: true, depthTest: false, depthWrite: false });
  const gradeMat = new THREE.ShaderMaterial({ vertexShader: QUAD_VERT, fragmentShader: GRADE_FRAG, uniforms: { src: { value: rtAccum.texture }, uTime: { value: 0 } }, depthTest: false, depthWrite: false });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), accumMat); quad.frustumCulled = false;
  const quadScene = new THREE.Scene(); quadScene.add(quad);

  /** Sub-frames for motion blur: enough that a fast move's streak is sampled every ~3 px; a still frame takes one. */
  function subframesAt(t) {
    if (!cfg.blur) return 1;
    const a = placeAt(t - 0.5 / fps), b = placeAt(t + 0.5 / fps);
    const m = Math.hypot(b.pl.pos.x - a.pl.pos.x, b.pl.pos.y - a.pl.pos.y, b.pl.pos.z - a.pl.pos.z) / Math.max(0.3, a.pl.distance)
      + Math.abs(((b.c.heading - a.c.heading + 540) % 360) - 180) * Math.PI / 180 * 1.2;
    return clamp(Math.ceil(SHUTTER * m * (H / 0.728) / 3), 1, 8);
  }

  const dbg = renderer.getContext().getExtension('WEBGL_debug_renderer_info');
  stats.gpu = dbg ? renderer.getContext().getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'unknown';

  window.renderFrame = (t) => {
    const f0 = performance.now();
    const S = subframesAt(t);
    renderer.setRenderTarget(rtAccum); renderer.setClearColor(0x000000); renderer.clear();
    let info = null;
    for (let i = 0; i < S; i++) {
      const ts = S === 1 ? t : t + ((i + 0.5) / S - 0.5) * SHUTTER / fps;
      // high up the globe takes over: both are drawn in the hand-over band and blended, so the descent never cuts
      const gk = globe ? globeWeight(cameraAt(tl.camera, ts).alt) : 0;
      if (gk < 1) {
        info = drawScene(ts);
        renderer.setRenderTarget(rtAccum); quad.material = accumMat; accumMat.uniforms.weight.value = (1 - gk) / S; renderer.render(quadScene, quadCam);
      }
      if (gk > 0) {
        drawGlobe(ts);
        renderer.setRenderTarget(rtAccum); quad.material = accumMat; accumMat.uniforms.weight.value = gk / S; renderer.render(quadScene, quadCam);
        if (!info) info = { c: cameraAt(tl.camera, ts), pl: placeAt(ts).pl, lod: { L1: 0, L2: 0 } };
      }
    }
    renderer.setRenderTarget(null); quad.material = gradeMat; gradeMat.uniforms.uTime.value = t; renderer.clear(); renderer.render(quadScene, quadCam);

    // HUD at the frame's own moment
    const { c, pl } = S === 1 && info.pl ? info : placeAt(t);
    if (S !== 1) { camera.position.set(pl.pos.x, pl.pos.y, pl.pos.z); camera.up.set(pl.up.x, pl.up.y, pl.up.z); camera.updateProjectionMatrix(); camera.lookAt(pl.target.x, pl.target.y, pl.target.z); camera.updateMatrixWorld(); }
    g2.drawImage(glc, 0, 0);
    const v = new THREE.Vector3();
    const curB = currentBeat(t);
    const tags = tagPts.map((l) => {
      v.copy(l.v).project(camera);
      const inView = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
      // scenes sharing a spot share a name tag's place: only the current beat's name shows
      const hidden = l.site && l.site.beat.i !== curB && sites.some((o) => o !== l.site && Math.hypot(o.center.x - l.site.center.x, o.center.z - l.site.center.z) < 1.4);
      const a = inView && !hidden ? smooth(l.min_alt * 0.7, l.min_alt, c.alt) * (1 - smooth(l.max_alt, l.max_alt * 1.4, c.alt)) : 0;
      return { name: l.name, kind: l.kind, x: (v.x * 0.5 + 0.5) * W, y: (-v.y * 0.5 + 0.5) * H, a };
    });
    // museum inset: the object turns slowly while its beat is spoken
    const mNow = museum.find((m) => t >= m.t0 && t <= m.t1);
    if (mNow) mNow.shoot(0.7 + (t - mNow.t0) * 0.35);
    const items = museum.filter((m) => t >= m.t0).map((m) => ({ icon: m.icon, name: m.name, current: m === mNow }));
    const cards = (tl.cards || []).filter((cd) => t >= cd.t0 - 0.1 && t <= cd.t1 && cardImgs.has(cd.id)).map((cd) => {
      let lead = null;
      if (cd.lon != null && cd.lat != null && c.alt >= 20) { const q = geo.toWorld(cd.lon, cd.lat); v.set(q.x, ground(q.x, q.z) + 0.6, q.z).project(camera);   // a leader line only at map scale; a ground set has its own scale
        if (v.z < 1 && Math.abs(v.x) < 1 && Math.abs(v.y) < 1) lead = { x: (v.x * 0.5 + 0.5) * W, y: (-v.y * 0.5 + 0.5) * H }; }
      return { img: cardImgs.get(cd.id), label: cd.label, kind: cd.kind, anchor: cd.anchor, lead, tilt: cardTilt(cd.id), p: (t - cd.t0) / Math.max(0.1, cd.t1 - cd.t0),
        a: Math.min(smooth(cd.t0, cd.t0 + 0.7, t), 1 - smooth(cd.t1 - 0.6, cd.t1, t)) };
    });
    drawHud(g2, W, H, tl, legendAt, t, { tags, cards, letterbox: 1 - smooth(9, 22, c.alt), noDate: c.alt > 4500,
      museum: mNow ? { image: mNow.canvas, name: mNow.name || mNow.item, note: mNow.note || '', a: smooth(mNow.t0, mNow.t0 + 0.6, t) * (1 - smooth(mNow.t1 - 0.6, mNow.t1, t)) } : null, items });
    stats.frames++; stats.frameMs.push(performance.now() - f0); stats.subframes.push(S);
    stats.last = { t, alt: +c.alt.toFixed(2), L1: info.lod.L1, L2: info.lod.L2, S };
    return out.toDataURL('image/jpeg', 0.92).split(',')[1];
  };
  window.stats = () => {
    let detailBytes = 0; for (const m of meshes.values()) detailBytes += m.bytes;
    return { ...stats, meshesCached: meshes.size, gpuTerrainMB: +((bytes0 + detailBytes) / 1048576).toFixed(1), worldTiles: data.tiles.size,
      jsHeapMB: performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(1) : null, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures };
  };
  stats.initMs = Math.round(performance.now() - t0);
  await document.fonts.load('700 20px "HudFont"'); await document.fonts.load('400 20px "HudFont"');
  window.__ready = true;
}

main().catch((e) => { window.__error = String(e && e.stack || e); });
