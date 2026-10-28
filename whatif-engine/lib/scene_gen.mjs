// SCENE shots: a 3D scene generated from a small JSON spec, so every sentence can have its own scene (no model library to run out of).
//   shot: { kind: "scene", scene_spec: {
//     world:  { type: gas|rock|ice|ocean|lava|sun|haze, seed, radius, palette: [#hex x2-5], bands, storm, craters, clouds, city, atmosphere: "#hex", rings: {inner, outer, color, tilt} },
//             cutaway: { layers: [{ r: 1..0 outer->inner radius, color, label? }], wedge: octant }   (an octant removed, the layers shown on the cut faces)
//             field: { lines, color, tilt, reach }                                       (dipole magnetic field lines flowing around the world)
//     craft:  { kind: probe|capsule|lander|satellite|rocket|telescope|rover|parts, scale, parachute: bool, parts: [{shape, size, pos, rot, color, metal}] },
//     layout: planet | craft | craft_over_planet,
//     env:    { sky: space|"#top,#horizon", clouds: [{ y, color, density, scale }], haze: "#hex", particles: { mode: rain|dust|snow|embers|streaks, count, color, speed } },
//     motion: { fall: units/s (clouds and particles stream past a falling craft), spin: deg/s },
//     camera: { path: orbit|push|pullback|descend|flyby|drift, az0, az1, el, dist, d1, y0, y1 },
//     light:  { dir: [x,y,z], color, intensity, ambient } } }
// Everything is a pure function of (spec, t): the same shot always gives the same frame. Unknown values are repaired, never fatal (repairScene).
import { skyMaterial } from './hero.mjs';

export const WORLD_TYPES = ['gas', 'rock', 'ice', 'ocean', 'lava', 'sun', 'haze'];
export const CRAFT_KINDS = ['probe', 'capsule', 'lander', 'satellite', 'rocket', 'telescope', 'rover', 'parts'];
export const LAYOUTS = ['planet', 'craft', 'craft_over_planet'];
export const CAMERA_PATHS = ['orbit', 'push', 'pullback', 'descend', 'flyby', 'drift'];
export const PARTICLE_MODES = ['rain', 'dust', 'snow', 'embers', 'streaks'];
const SHAPES = ['box', 'cyl', 'sph', 'cone', 'torus', 'panel', 'dish'];
const HEX = /^#[0-9a-f]{6}$/i;
const num = (v, d, lo = -1e6, hi = 1e6) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Math.min(hi, Math.max(lo, Number(v))) : d);
const hex = (v, d) => (typeof v === 'string' && HEX.test(v) ? v : d);
const rnd = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
const DEFAULT_PALETTE = {
  gas: ['#d9b48a', '#a8683c', '#efe2c8', '#c98f5a'], rock: ['#6e5a48', '#8f7a62', '#4a3b30'], ice: ['#dce8f2', '#9fb8cf', '#f6fbff'],
  ocean: ['#1f4f86', '#3e7a3c', '#c9b98a', '#f4f4f4'], lava: ['#1a0e0a', '#c43c0e', '#ffb02e'], sun: ['#ff9a1f', '#ffd36b', '#fff2c4'], haze: ['#e8c88a', '#d0a060', '#f4e2b8'],
};

/** Repair a scene spec in place and say what was repaired: -> notes. A bad value becomes a sensible default; nothing here can stop a render. */
export function repairScene(sp) {
  const notes = [];
  if (!LAYOUTS.includes(sp.layout)) {
    if (sp.layout) notes.push(`layout ${sp.layout} unknown`);
    sp.layout = sp.world && sp.craft ? 'craft_over_planet' : sp.craft ? 'craft' : 'planet';
  }
  if (sp.layout !== 'craft') {
    const w = (sp.world = sp.world || {});
    if (!WORLD_TYPES.includes(w.type)) { notes.push(`world type ${w.type} unknown; rock`); w.type = 'rock'; }
    w.seed = num(w.seed, 7, 0, 1e6); w.radius = num(w.radius, 1, 0.2, 40);
    const pal = (Array.isArray(w.palette) ? w.palette : []).filter((c) => HEX.test(c));
    w.palette = pal.length >= 2 ? pal.slice(0, 5) : DEFAULT_PALETTE[w.type];
    w.bands = num(w.bands, 9, 1, 40); w.storm = num(w.storm, 0, 0, 1); w.craters = num(w.craters, w.type === 'rock' ? 0.5 : 0, 0, 1);
    w.clouds = num(w.clouds, w.type === 'ocean' ? 0.5 : 0, 0, 1); w.city = num(w.city, 0, 0, 1);
    w.atmosphere = w.atmosphere != null ? hex(w.atmosphere, null) : null;
    if (w.cutaway) {
      const ls = (Array.isArray(w.cutaway.layers) ? w.cutaway.layers : []).filter((l) => l && Number.isFinite(Number(l.r))).map((l) => ({ r: num(l.r, 0.5, 0.02, 1), color: hex(l.color, '#c9854a'), label: typeof l.label === 'string' ? l.label.replace(/\s+/g, ' ').trim().toUpperCase().slice(0, 22) : '' }))
        .sort((a, b) => b.r - a.r).slice(0, 8);
      w.cutaway = ls.length >= 2 ? { layers: ls } : null;
    }
    if (w.field) w.field = { lines: num(w.field.lines, 10, 3, 24), color: hex(w.field.color, '#7fd0ff'), tilt: num(w.field.tilt, 10, -60, 60), reach: num(w.field.reach, 3.2, 1.6, 6) };
    if (w.rings) w.rings = { inner: num(w.rings.inner, 1.4, 1.05, 3), outer: num(w.rings.outer, 2.3, 1.2, 5), color: hex(w.rings.color, '#d8c8a0'), tilt: num(w.rings.tilt, 20, -80, 80) };
  }
  if (sp.layout !== 'planet') {
    const c = (sp.craft = sp.craft || {});
    if (!CRAFT_KINDS.includes(c.kind)) { notes.push(`craft kind ${c.kind} unknown; probe`); c.kind = 'probe'; }
    c.scale = num(c.scale, 1, 0.05, 20); c.parachute = !!c.parachute;
    c.parts = (Array.isArray(c.parts) ? c.parts : []).filter((p) => p && SHAPES.includes(p.shape)).slice(0, 40);
    if (c.kind === 'parts' && !c.parts.length) c.kind = 'probe';
  }
  const e = (sp.env = sp.env || {});
  e.sky = e.sky === 'space' || /^#[0-9a-f]{6},#[0-9a-f]{6}$/i.test(e.sky || '') ? e.sky : 'space';
  e.clouds = (Array.isArray(e.clouds) ? e.clouds : []).slice(0, 8).map((c, i) => ({ y: num(c.y, -1 - i * 1.6, -60, 60), color: hex(c.color, '#cfd6e0'), density: num(c.density, 0.6, 0.05, 1), scale: num(c.scale, 1, 0.2, 6) }));
  if (e.particles) { if (!PARTICLE_MODES.includes(e.particles.mode)) e.particles.mode = 'dust'; e.particles.count = num(e.particles.count, 600, 20, 4000); e.particles.color = hex(e.particles.color, '#ffffff'); e.particles.speed = num(e.particles.speed, 1, 0, 30); }
  e.haze = hex(e.haze, null);
  const m = (sp.motion = sp.motion || {}); m.fall = num(m.fall, 0, 0, 60); m.spin = num(m.spin, 0, -90, 90);
  const cam = (sp.camera = sp.camera || {});
  if (!CAMERA_PATHS.includes(cam.path)) cam.path = 'orbit';
  cam.az0 = num(cam.az0, -22, -180, 180); cam.az1 = num(cam.az1, 22, -180, 180); cam.el = num(cam.el, 10, -80, 85);
  cam.dist = num(cam.dist, sp.layout === 'planet' ? 3.6 : 4, 0.8, 200);
  cam.d1 = num(cam.d1, cam.path === 'push' ? cam.dist * 0.7 : cam.path === 'pullback' ? cam.dist * 1.6 : cam.dist, 0.5, 300);
  cam.y0 = num(cam.y0, 4, -100, 100); cam.y1 = num(cam.y1, -6, -100, 100);
  const l = (sp.light = sp.light || {}); l.dir = Array.isArray(l.dir) && l.dir.length === 3 ? l.dir.map((x) => num(x, 1)) : [-4, 2.5, 3];
  l.color = hex(l.color, '#fff3e0'); l.intensity = num(l.intensity, 3, 0.1, 12); l.ambient = num(l.ambient, 0.35, 0, 2);
  sp.seed = num(sp.seed, 1, 0, 1e6);
  return notes;
}

// ---- the world: one shader, any planet from parameters ------------------------------------------------------------------------------------
const NOISE = `
float h31(vec3 p){ p = fract(p * 0.3183099 + .1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vn(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(h31(i), h31(i + vec3(1,0,0)), f.x), mix(h31(i + vec3(0,1,0)), h31(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(h31(i + vec3(0,0,1)), h31(i + vec3(1,0,1)), f.x), mix(h31(i + vec3(0,1,1)), h31(i + vec3(1,1,1)), f.x), f.y), f.z); }
float fbm(vec3 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 5; i++){ s += a * vn(p); p = p * 2.02 + 7.3; a *= 0.5; } return s; }
vec2 cell(vec3 p){ vec3 i = floor(p), f = fract(p); float d = 9.0, d2 = 9.0;
  for (int x = -1; x <= 1; x++) for (int y = -1; y <= 1; y++) for (int z = -1; z <= 1; z++){
    vec3 g = vec3(float(x), float(y), float(z)); vec3 o = vec3(h31(i + g), h31(i + g + 3.1), h31(i + g + 6.7));
    float dd = length(g + o - f); if (dd < d){ d2 = d; d = dd; } else if (dd < d2) d2 = dd; }
  return vec2(d, d2); }
`;
const PLANET_VS = 'varying vec3 vP; varying vec3 vN; varying vec3 vW; void main(){ vP = position; vN = normalize(mat3(modelMatrix) * normal); vec4 w = modelMatrix * vec4(position,1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }';
const PLANET_FS = `
uniform int uType; uniform float uSeed; uniform vec3 uP0; uniform vec3 uP1; uniform vec3 uP2; uniform vec3 uP3; uniform float uBands; uniform float uStorm;
uniform float uCut; uniform float uCraters; uniform float uClouds; uniform float uCity; uniform vec3 uL; uniform vec3 uLc; uniform float uAmb; uniform float uTime; uniform vec3 uAtm; uniform float uAtmOn;
varying vec3 vP; varying vec3 vN; varying vec3 vW;
${NOISE}
void main(){
  if (uCut > 0.5 && vP.x > 0.0 && vP.y > 0.0 && vP.z > 0.0) discard;
  vec3 p = normalize(vP); vec3 q = p * 2.2 + uSeed * 1.7; vec3 col; float emis = 0.0; float night = 0.0;
  if (uType == 0 || uType == 6){
    float w = fbm(q * 1.6 + vec3(0.0, uTime * 0.01, 0.0));
    float lat = p.y * uBands + (w - 0.5) * (uType == 6 ? 1.2 : 2.6) + fbm(q * 5.0) * 0.5;
    float b = 0.5 + 0.5 * sin(lat * 3.14159); float c2 = fbm(vec3(p.x * 6.0, lat * 1.5, p.z * 6.0) + uSeed);
    col = mix(mix(uP0, uP1, b), mix(uP2, uP3, c2), 0.45 + 0.35 * sin(lat * 1.7 + uSeed));
    if (uStorm > 0.0){ vec3 sc = normalize(vec3(cos(uSeed), -0.32, sin(uSeed))); float d = distance(p, sc); float sw = fbm(q * 4.0 + atan(p.y + 0.32, p.x - sc.x) * 2.0);
      float spot = smoothstep(0.34 * uStorm + 0.05, 0.05, d * (1.0 + 0.4 * sw)); col = mix(col, mix(uP1, uP3, 0.6) * 0.9, spot * 0.85); col += spot * 0.08 * sin(d * 60.0 - sw * 8.0); }
    col *= 0.9 + 0.2 * fbm(q * 14.0);
  } else if (uType == 1){
    float h = fbm(q * 1.3); col = mix(mix(uP0, uP1, smoothstep(0.3, 0.7, h)), uP2, smoothstep(0.62, 0.9, fbm(q * 3.0)) * 0.5);
    if (uCraters > 0.0){ vec2 cl = cell(p * (6.0 + 10.0 * uCraters) + uSeed); float rim = smoothstep(0.30, 0.22, cl.x) * 0.5 - smoothstep(0.22, 0.10, cl.x) * 0.35; col *= 1.0 + rim * uCraters * 1.2; }
    col *= 0.85 + 0.3 * fbm(q * 10.0);
  } else if (uType == 2){
    float h = fbm(q * 1.2); col = mix(uP0, uP1, smoothstep(0.35, 0.75, h)) * 0.8; float cr = 1.0 - abs(fbm(q * 3.5) * 2.0 - 1.0); col = mix(col, uP1 * 0.55, smoothstep(0.86, 0.97, cr) * 0.8);
    col = mix(col, uP2, smoothstep(0.7, 0.95, abs(p.y))); col *= 0.92 + 0.16 * fbm(q * 12.0);
  } else if (uType == 3){
    float h = fbm(q * 0.9); float land = smoothstep(0.52, 0.56, h); float sea = fbm(q * 4.0);
    col = mix(mix(uP0 * 0.8, uP0 * 1.15, sea), mix(uP1, uP2, smoothstep(0.55, 0.8, fbm(q * 2.5))), land);
    col = mix(col, uP3, smoothstep(0.78, 0.92, abs(p.y) + (h - 0.5) * 0.2));
    float cl = smoothstep(0.5, 0.78, fbm(q * 2.6 + vec3(uTime * 0.01, 0.0, 0.0))) * uClouds; col = mix(col, vec3(1.0), cl * 0.9);
    night = uCity * smoothstep(0.55, 0.7, h) * step(0.62, fbm(q * 14.0)) * (1.0 - cl);
  } else if (uType == 4){
    float cr = 1.0 - abs(fbm(q * 2.2) * 2.0 - 1.0); float crack = smoothstep(0.90, 0.985, cr);
    col = mix(uP0 * (0.7 + 0.5 * fbm(q * 8.0)), uP1, crack * 0.6); emis = crack * (0.8 + 0.4 * fbm(q * 5.0 + uTime * 0.05)); col = mix(col, uP2, crack * 0.6);
  } else {
    float g = fbm(q * 6.0 + uTime * 0.04); float g2 = fbm(q * 18.0 - uTime * 0.07); col = mix(mix(uP0, uP1, g), uP2, smoothstep(0.55, 0.9, g2) * 0.6); emis = 1.0;
  }
  vec3 n = normalize(vN); float ndl = dot(n, normalize(uL)); float lit = smoothstep(-0.08, 0.35, ndl);
  vec3 shaded = uType == 5 ? col : col * (uAmb + lit * uLc * 0.8);
  shaded += (uType == 4 ? emis * uP2 * 1.4 : vec3(0.0)) + night * vec3(1.0, 0.78, 0.45) * (1.0 - lit) * 1.6;
  vec3 v = normalize(cameraPosition - vW); float fr = pow(1.0 - max(dot(n, v), 0.0), 3.0);
  shaded += uAtm * fr * uAtmOn * (0.25 + 0.9 * lit);
  gl_FragColor = vec4(shaded, 1.0);
}`;

function planet(THREE, w, light) {
  const g = new THREE.Group(), pal = w.palette.map((c) => new THREE.Color(c)), p = (i) => pal[Math.min(i, pal.length - 1)];
  const typeId = { gas: 0, rock: 1, ice: 2, ocean: 3, lava: 4, sun: 5, haze: 6 }[w.type];
  const mat = new THREE.ShaderMaterial({
    vertexShader: PLANET_VS, fragmentShader: PLANET_FS,
    uniforms: {
      uType: { value: typeId }, uSeed: { value: w.seed }, uP0: { value: p(0) }, uP1: { value: p(1) }, uP2: { value: p(2) }, uP3: { value: p(3) }, uBands: { value: w.bands },
      uStorm: { value: w.storm }, uCut: { value: w.cutaway ? 1 : 0 }, uCraters: { value: w.craters }, uClouds: { value: w.clouds }, uCity: { value: w.city },
      uL: { value: new THREE.Vector3(...light.dir).normalize() }, uLc: { value: new THREE.Color(light.color).multiplyScalar(light.intensity / 3) }, uAmb: { value: light.ambient * 0.25 },
      uTime: { value: 0 }, uAtm: { value: new THREE.Color(w.atmosphere || '#000000') }, uAtmOn: { value: w.atmosphere ? 1 : 0 },
    },
  });
  g.add(new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96), mat));
  if (w.atmosphere) {
    g.add(new THREE.Mesh(new THREE.SphereGeometry(1.06, 64, 48), new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, side: THREE.BackSide, blending: THREE.AdditiveBlending, uniforms: { c: { value: new THREE.Color(w.atmosphere) } },
      vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vN = normalize(normalMatrix * normal); vec4 m = modelViewMatrix * vec4(position,1.0); vV = normalize(-m.xyz); gl_Position = projectionMatrix * m; }',
      fragmentShader: 'uniform vec3 c; varying vec3 vN; varying vec3 vV; void main(){ float a = pow(max(0.0, 0.62 - dot(vN, vV)), 2.2) * 1.5; gl_FragColor = vec4(c * a, a); }',
    })));
  }
  if (w.rings) {
    const r = w.rings, ring = new THREE.Mesh(new THREE.RingGeometry(r.inner, r.outer, 128, 1), new THREE.ShaderMaterial({
      transparent: true, side: THREE.DoubleSide, depthWrite: false, uniforms: { c: { value: new THREE.Color(r.color) }, a: { value: r.inner }, b: { value: r.outer }, s: { value: w.seed } },
      vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform vec3 c; uniform float a; uniform float b; uniform float s; varying vec3 vP; ${NOISE}
        void main(){ float t = (length(vP.xy) - a) / (b - a); float band = 0.35 + 0.65 * fbm(vec3(t * 40.0, s, 0.0)); float gap = smoothstep(0.0, 0.05, t) * smoothstep(1.0, 0.9, t) * (1.0 - 0.8 * smoothstep(0.6, 0.62, t) * smoothstep(0.66, 0.64, t));
          gl_FragColor = vec4(c * band, gap * band * 0.9); }`,
    }));
    ring.rotation.x = Math.PI / 2 + (r.tilt * Math.PI) / 180; g.add(ring);
  }
  let labels = [];
  if (w.cutaway) {
    const L = w.cutaway.layers, N = 8, rs = L.map((l) => l.r), cs = L.map((l) => new THREE.Color(l.color));
    const fmat = new THREE.ShaderMaterial({
      side: THREE.DoubleSide, uniforms: { rs: { value: [...rs, ...Array(N - rs.length).fill(0)] }, n: { value: rs.length }, cols: { value: [...cs, ...Array(N - cs.length).fill(new THREE.Color(0))] }, amb: { value: 0.75 } },
      vertexShader: 'varying vec2 vU; void main(){ vU = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform float rs[8]; uniform vec3 cols[8]; uniform int n; uniform float amb; varying vec2 vU; ${NOISE}
        void main(){ float r = length(vU); vec3 c = cols[0]; float edge = 0.0;
          for (int i = 0; i < 8; i++){ if (i < n){ if (r <= rs[i]) { c = cols[i]; } if (i > 0 && abs(r - rs[i - 1]) < 0.006) edge = 1.0; } }
          c *= 0.85 + 0.3 * fbm(vec3(vU * 9.0, 2.0)); c = mix(c, vec3(1.0), edge * 0.5);
          if (r > 1.0) discard; float core = smoothstep(rs[n - 1] + 0.12, 0.0, r); c += cols[n - 1] * core * 0.5; gl_FragColor = vec4(c * amb, 1.0); }`,
    });
    const quarter = () => new THREE.Mesh(new THREE.CircleGeometry(1, 64, 0, Math.PI / 2), fmat);
    const fx = quarter(); fx.rotation.y = -Math.PI / 2; g.add(fx);                 // plane x = 0, spans y,z > 0
    const fy = quarter(); fy.rotation.x = Math.PI / 2; g.add(fy);                  // plane y = 0, spans x,z > 0  (circle x,y -> x,z)
    const fz = quarter(); g.add(fz);                                               // plane z = 0, spans x,y > 0
    // labels: a camera-facing sprite in a column at the right of the frame, a thin leader to the layer's band on the z = 0 cut face; each fades in on its
    // own beat. Positions are set every frame from the camera (lib place()), so they stay on screen whatever the orbit does.
    L.forEach((l, i) => {
      if (!l.label) return;
      const inner = i + 1 < L.length ? L[i + 1].r : 0, mid = inner + (l.r - inner) * (i + 1 < L.length ? 0.5 : 0.45);
      const ang = (66 - 42 * (L.length > 1 ? i / (L.length - 1) : 0)) * Math.PI / 180, anchor = new THREE.Vector3(Math.cos(ang) * mid, Math.sin(ang) * mid, 0);
      const cv = document.createElement('canvas'); cv.width = 768; cv.height = 96; const cx = cv.getContext('2d');
      let px = 48; cx.font = `700 ${px}px Inter, Helvetica, Arial, sans-serif`; while (cx.measureText(l.label).width > 740 && px > 20) { px -= 2; cx.font = `700 ${px}px Inter, Helvetica, Arial, sans-serif`; }
      cx.textBaseline = 'middle'; cx.lineJoin = 'round'; cx.lineWidth = 9; cx.strokeStyle = 'rgba(0,0,0,0.85)'; cx.strokeText(l.label, 10, 50); cx.fillStyle = '#ffffff'; cx.fillText(l.label, 10, 50);
      const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, opacity: 0 })); sprite.renderOrder = 10;
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([anchor.clone(), anchor.clone()]), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthTest: false })); line.renderOrder = 9;
      const dot = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, depthTest: false })); dot.renderOrder = 9;
      labels.push({ sprite, line, dot, anchor, i: labels.length });
    });
  }
  let field = null;
  if (w.field) {
    const F = w.field, grp = new THREE.Group(), segs = 60;
    for (let i = 0; i < F.lines; i++) {
      const phi = (i / F.lines) * Math.PI * 2, Lr = 1.45 + (F.reach - 1.45) * ((i % 4) / 3), pts = [];
      for (let k = 0; k <= segs; k++) {
        const th = 0.18 + (Math.PI - 0.36) * (k / segs), r = Lr * Math.sin(th) ** 2 + 0.0, rr = Math.max(r, 1.02);
        pts.push(new THREE.Vector3(rr * Math.sin(th) * Math.cos(phi), rr * Math.cos(th), rr * Math.sin(th) * Math.sin(phi)));
      }
      const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 90, 0.014, 6, false);
      grp.add(new THREE.Mesh(geo, new THREE.ShaderMaterial({
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { c: { value: new THREE.Color(F.color) }, t: { value: 0 }, off: { value: i * 0.37 } },
        vertexShader: 'varying float vS; void main(){ vS = uv.x; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
        fragmentShader: 'uniform vec3 c; uniform float t; uniform float off; varying float vS; void main(){ float pulse = pow(0.5 + 0.5 * sin((vS * 3.0 - t * 0.35 + off) * 6.28318), 3.0); float a = (0.35 + 0.65 * pulse) * smoothstep(0.0, 0.1, vS) * smoothstep(1.0, 0.9, vS); gl_FragColor = vec4(c * a * 1.4, a); }',
      })));
    }
    grp.rotation.z = (F.tilt * Math.PI) / 180; g.add(grp); field = grp;
  }
  return { group: g, mat, field, labels };
}

// ---- craft from parts ------------------------------------------------------------------------------------------------------------------------
const metal = (THREE, color, m = 0.6, r = 0.45) => new THREE.MeshStandardMaterial({ color, metalness: m, roughness: r });
function part(THREE, p) {
  const s = p.size || [1, 1, 1], mat = metal(THREE, p.color || '#b9bfc8', p.metal ?? 0.6);
  let geo;
  switch (p.shape) {
    case 'box': geo = new THREE.BoxGeometry(s[0], s[1] ?? s[0], s[2] ?? s[0]); break;
    case 'cyl': geo = new THREE.CylinderGeometry(s[0], s[1] ?? s[0], s[2] ?? 1, 32); break;
    case 'sph': geo = new THREE.SphereGeometry(s[0], 32, 24); break;
    case 'cone': geo = new THREE.ConeGeometry(s[0], s[1] ?? 1, 32); break;
    case 'torus': geo = new THREE.TorusGeometry(s[0], s[1] ?? 0.05, 12, 48); break;
    case 'panel': geo = new THREE.BoxGeometry(s[0], 0.03, s[1] ?? s[0]); mat.color.set(p.color || '#1c3c78'); mat.metalness = 0.3; mat.roughness = 0.25; break;
    default: geo = new THREE.SphereGeometry(s[0], 40, 12, 0, Math.PI * 2, 0, Math.PI / 3); mat.side = THREE.DoubleSide;
  }
  const m = new THREE.Mesh(geo, mat); m.position.set(...(p.pos || [0, 0, 0])); if (p.shape === 'dish') { m.rotation.x = Math.PI; m.position.y += s[0] * 0.5; } if (p.rot) m.rotation.set(...p.rot.map((d) => (d * Math.PI) / 180)); return m;
}
const PRESETS = {
  probe: [{ shape: 'cyl', size: [0.45, 0.45, 0.5], pos: [0, 0, 0], color: '#c9a24a', metal: 0.8 }, { shape: 'dish', size: [1.1], pos: [0, 0.7, 0], color: '#e8e8e8' },
    { shape: 'cyl', size: [0.02, 0.02, 1.2], pos: [0, 1.15, 0], color: '#cccccc' }, { shape: 'panel', size: [1.8, 0.6], pos: [-1.5, 0, 0] }, { shape: 'panel', size: [1.8, 0.6], pos: [1.5, 0, 0] },
    { shape: 'cyl', size: [0.025, 0.025, 1.8], pos: [0, -0.2, 0.55], rot: [90, 0, 0], color: '#888888' }],
  capsule: [{ shape: 'cone', size: [0.9, 1.1], pos: [0, 0.3, 0], color: '#d9d4cc', metal: 0.3 }, { shape: 'cyl', size: [0.92, 0.95, 0.12], pos: [0, -0.3, 0], color: '#2a2320', metal: 0.1 },
    { shape: 'cyl', size: [0.25, 0.25, 0.2], pos: [0, 0.95, 0], color: '#555555' }],
  lander: [{ shape: 'cyl', size: [0.7, 0.8, 0.6], pos: [0, 0.5, 0], color: '#c8b890', metal: 0.5 }, { shape: 'cyl', size: [0.05, 0.05, 1.0], pos: [0.8, 0, 0.8], rot: [0, 0, 20], color: '#999999' },
    { shape: 'cyl', size: [0.05, 0.05, 1.0], pos: [-0.8, 0, 0.8], rot: [0, 0, -20], color: '#999999' }, { shape: 'cyl', size: [0.05, 0.05, 1.0], pos: [0.8, 0, -0.8], rot: [0, 0, 20], color: '#999999' },
    { shape: 'cyl', size: [0.05, 0.05, 1.0], pos: [-0.8, 0, -0.8], rot: [0, 0, -20], color: '#999999' }, { shape: 'dish', size: [0.5], pos: [0, 1.0, 0], color: '#eeeeee' }],
  satellite: [{ shape: 'box', size: [0.9, 0.9, 1.1], color: '#c0a060', metal: 0.7 }, { shape: 'panel', size: [2.0, 0.8], pos: [-1.6, 0, 0] }, { shape: 'panel', size: [2.0, 0.8], pos: [1.6, 0, 0] },
    { shape: 'dish', size: [0.55], pos: [0, 0.75, 0], color: '#eeeeee' }],
  rocket: [{ shape: 'cyl', size: [0.4, 0.4, 2.2], color: '#f0f0f0', metal: 0.2 }, { shape: 'cone', size: [0.4, 0.8], pos: [0, 1.5, 0], color: '#d8d8d8', metal: 0.3 },
    { shape: 'cyl', size: [0.3, 0.2, 0.3], pos: [0, -1.25, 0], color: '#333333' }, { shape: 'box', size: [0.05, 0.6, 0.5], pos: [0.5, -0.8, 0], color: '#bbbbbb' }, { shape: 'box', size: [0.05, 0.6, 0.5], pos: [-0.5, -0.8, 0], color: '#bbbbbb' }],
  telescope: [{ shape: 'cyl', size: [0.5, 0.5, 2.0], rot: [90, 0, 0], color: '#cfcfcf', metal: 0.5 }, { shape: 'panel', size: [1.6, 0.7], pos: [0, 0.1, 0], rot: [0, 90, 0] }, { shape: 'torus', size: [0.5, 0.04], pos: [0, 0, 1.0], color: '#f5d060' }],
  rover: [{ shape: 'box', size: [1.4, 0.4, 0.9], pos: [0, 0.5, 0], color: '#d8d4cc', metal: 0.4 }, { shape: 'cyl', size: [0.025, 0.025, 1.0], pos: [0.5, 1.1, 0.2], color: '#aaaaaa' }, { shape: 'box', size: [0.25, 0.2, 0.2], pos: [0.5, 1.65, 0.2], color: '#444444' },
    ...[[-0.6, 0.45], [0, 0.5], [0.6, 0.45]].flatMap(([x, z]) => [{ shape: 'cyl', size: [0.22, 0.22, 0.18], pos: [x, 0.2, z], rot: [90, 0, 0], color: '#222222', metal: 0.1 }, { shape: 'cyl', size: [0.22, 0.22, 0.18], pos: [x, 0.2, -z], rot: [90, 0, 0], color: '#222222', metal: 0.1 }])],
};

function parachute(THREE) {
  const g = new THREE.Group(), c = document.createElement('canvas'); c.width = 256; c.height = 8; const x = c.getContext('2d');
  for (let i = 0; i < 16; i++) { x.fillStyle = i % 2 ? '#f2efe8' : '#e0622a'; x.fillRect(i * 16, 0, 16, 8); }
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.wrapS = THREE.RepeatWrapping;
  const canopy = new THREE.Mesh(new THREE.SphereGeometry(1.5, 48, 16, 0, Math.PI * 2, 0, Math.PI * 0.46), new THREE.MeshStandardMaterial({ map: tex, side: THREE.DoubleSide, roughness: 0.8 }));
  canopy.scale.y = 0.75; canopy.position.y = 3.4; g.add(canopy);
  const pts = [], rim = 1.5 * Math.sin(Math.PI * 0.46), rimY = 3.4 + 1.5 * 0.75 * Math.cos(Math.PI * 0.46);
  for (let i = 0; i < 16; i++) { const a = (i / 16) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a) * rim, rimY, Math.sin(a) * rim), new THREE.Vector3(0, 0.55, 0)); }
  g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xe8e0d0, transparent: true, opacity: 0.8 })));
  return g;
}

export function craft(THREE, c) {
  const g = new THREE.Group();
  for (const p of (c.kind === 'parts' ? c.parts : PRESETS[c.kind])) g.add(part(THREE, p));
  if (c.parachute) g.add(parachute(THREE));
  const holder = new THREE.Group(); holder.add(g); holder.scale.setScalar(c.scale * 0.85); return holder;
}

// ---- environment: cloud sea, particles -----------------------------------------------------------------------------------------------------------
function cloudLayer(THREE, L, seed) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(60, 60, 1, 1), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, uniforms: { c: { value: new THREE.Color(L.color) }, d: { value: L.density }, s: { value: L.scale }, seed: { value: seed }, t: { value: 0 }, fade: { value: 1 } },
    vertexShader: 'varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
    fragmentShader: `uniform vec3 c; uniform float d; uniform float s; uniform float seed; uniform float t; uniform float fade; varying vec3 vP; ${NOISE}
      void main(){ vec3 q = vec3(vP.xy * 0.09 * s + vec2(t * 0.01, 0.0), seed); float n = fbm(q) * 0.7 + fbm(q * 3.0 + 4.0) * 0.3; float a = smoothstep(0.62 - d * 0.35, 0.82, n) * smoothstep(30.0, 8.0, length(vP.xy)) * fade;
        gl_FragColor = vec4(c * (0.75 + 0.35 * n), a); }`,
  }));
  m.rotation.x = -Math.PI / 2; m.position.y = L.y; return m;
}

function particles(THREE, P, seed) {
  const r = rnd(seed + 99), n = P.count, base = new Float32Array(n * 3), pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) base.set([(r() - 0.5) * 24, r(), (r() - 0.5) * 24], i * 3);
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const pts = new THREE.Points(g, new THREE.PointsMaterial({ color: P.color, size: P.mode === 'streaks' ? 1.4 : 2.2, sizeAttenuation: false, transparent: true, opacity: P.mode === 'dust' ? 0.5 : 0.8, depthWrite: false }));
  const H = 16, dir = P.mode === 'embers' ? 1 : -1;
  pts.userData.update = (t, fallSpeed) => {
    for (let i = 0; i < n; i++) {
      const sp = (P.speed + fallSpeed * 0.4) * (P.mode === 'dust' ? 0.15 : 1) * (0.6 + 0.8 * base[i * 3 + 1]);
      const y = ((base[i * 3 + 1] + (-dir) * sp * t / H) % 1 + 1) % 1;
      pos[i * 3] = base[i * 3] + (P.mode === 'dust' || P.mode === 'embers' ? Math.sin(t * 0.5 + i) * 0.4 : 0); pos[i * 3 + 1] = (y - 0.5) * H; pos[i * 3 + 2] = base[i * 3 + 2];
    }
    g.attributes.position.needsUpdate = true;
  };
  pts.frustumCulled = false; return pts;
}

// ---- the scene -------------------------------------------------------------------------------------------------------------------------------------
export function buildScene(THREE, shot, { stars }) {
  const sp = shot.scene_spec || {}; repairScene(sp);
  const scene = new THREE.Scene(), root = new THREE.Group(); scene.add(root);
  const sky = sp.env.sky;
  if (sky === 'space') scene.add(stars(sp.seed + 3));
  else { const [top, hor] = sky.split(','); scene.add(new THREE.Mesh(new THREE.SphereGeometry(200, 32, 16), skyMaterial(THREE, top, hor))); }
  if (sp.env.haze) scene.fog = new THREE.Fog(sp.env.haze, 8, 60);
  const L = sp.light, dirLight = new THREE.DirectionalLight(L.color, L.intensity); dirLight.position.set(...L.dir); scene.add(dirLight);
  scene.add(new THREE.AmbientLight(0xffffff, L.ambient * 0.5), new THREE.HemisphereLight(0x8aa4d0, 0x15181f, L.ambient));
  let pl = null, cr = null;
  if (sp.layout !== 'craft') {
    pl = planet(THREE, sp.world, L); const R = sp.world.radius;
    pl.group.scale.setScalar(R);
    pl.group.position.set(0, sp.layout === 'craft_over_planet' ? -R - 1.5 : 0, sp.layout === 'craft_over_planet' ? -2 : 0);
    root.add(pl.group);
    pl.labels.forEach((lb) => root.add(lb.sprite, lb.line, lb.dot));
  }
  if (sp.layout !== 'planet') { cr = craft(THREE, sp.craft); root.add(cr); }
  const clouds = sp.env.clouds.map((c) => { const m = cloudLayer(THREE, c, sp.seed); root.add(m); return m; });
  const parts = sp.env.particles ? particles(THREE, sp.env.particles, sp.seed) : null; if (parts) scene.add(parts);

  function place(camera, k, t) {
    const c = sp.camera, ease = k * k * (3 - 2 * k), at = new THREE.Vector3(0, 0, 0);
    const az = (c.az0 + (c.az1 - c.az0) * k) * Math.PI / 180, el = c.el * Math.PI / 180;
    let dist = c.dist;
    if (c.path === 'push' || c.path === 'pullback') dist = c.dist + (c.d1 - c.dist) * ease;
    else if (c.path === 'drift') dist = c.dist * (1 - 0.05 * k);
    if (c.path === 'descend') {
      const y = c.y0 + (c.y1 - c.y0) * ease;
      camera.position.set(Math.sin(az) * c.dist, y, Math.cos(az) * c.dist); at.set(0, y * 0.4, 0);
    } else if (c.path === 'flyby') {
      camera.position.set(-c.dist * 1.2 + 2.4 * c.dist * 1.2 * ease, Math.sin(el) * c.dist * 0.6, Math.cos(el) * c.dist);
    } else camera.position.set(Math.sin(az) * Math.cos(el) * dist, Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist);
    if (cr && sp.craft.parachute) at.set(0, 1.5 * sp.craft.scale, 0);        // frame the canopy with the craft
    camera.lookAt(sp.layout === 'craft_over_planet' && c.path !== 'descend' ? new THREE.Vector3(0, -0.35, 0) : at);
    if (cr) cr.rotation.y = (sp.motion.spin * t * Math.PI) / 180;
    if (pl) { pl.group.rotation.y = pl.field || sp.world.cutaway ? 0 : 0.02 * t; pl.mat.uniforms.uTime.value = t; if (pl.field) pl.field.children.forEach((l) => { l.material.uniforms.t.value = t; }); }
    if (pl && pl.labels.length) {
      pl.group.updateMatrixWorld(true); camera.updateMatrixWorld(true);
      const fwd = new THREE.Vector3(); camera.getWorldDirection(fwd);
      const dist = Math.max(0.5, new THREE.Vector3().subVectors(pl.group.position, camera.position).dot(fwd)), halfH = Math.tan(camera.fov * Math.PI / 360) * dist, halfW = halfH * camera.aspect;
      const items = pl.labels.map((lb) => ({ lb, aw: lb.anchor.clone().applyMatrix4(pl.group.matrixWorld) })).map((o) => ({ ...o, ndc: o.aw.clone().project(camera) }));
      if (items.length > 1 && items[0].ndc.y < items[items.length - 1].ndc.y) items.reverse();      // the camera is below the cut: the stack flips, so the leaders still do not cross
      const n = items.length, colX = 0.58, wNdc = 0.38, top = 0.52, step = n > 1 ? 0.62 / (n - 1) : 0;
      items.forEach((o, slot) => {                              // labels stacked top-down in layer order (outermost first); flipped only when the camera sees the cut from below
        const lb = o.lb, yN = top - step * slot, xN = colX + wNdc / 2;
        const ray = new THREE.Vector3(xN, yN, 0.5).unproject(camera).sub(camera.position).normalize(); ray.multiplyScalar(dist / Math.max(0.2, ray.dot(fwd)));
        lb.sprite.position.copy(camera.position).add(ray); lb.sprite.scale.set(wNdc * halfW * 2, wNdc * halfW * 2 * 96 / 768, 1);
        const left = new THREE.Vector3(colX - 0.01, yN, 0.5).unproject(camera).sub(camera.position).normalize(); left.multiplyScalar(dist / Math.max(0.2, left.dot(fwd)));
        const lp = lb.line.geometry.attributes.position; lp.setXYZ(0, o.aw.x, o.aw.y, o.aw.z); lp.setXYZ(1, camera.position.x + left.x, camera.position.y + left.y, camera.position.z + left.z); lp.needsUpdate = true;
        lb.dot.position.copy(o.aw); lb.dot.scale.setScalar(0.0055 * dist);
        const a = Math.min(1, Math.max(0, (k - (0.12 + 0.11 * lb.i)) / 0.07)) * Math.min(1, Math.max(0, (1 - k) / 0.05));       // in one by one, out at the cut
        lb.sprite.material.opacity = a; lb.line.material.opacity = 0.7 * a; lb.dot.material.opacity = a;
      });
    }
    const fall = sp.motion.fall * t;       // a falling craft: the world streams upward past it
    clouds.forEach((m, i) => {
      const y0 = sp.env.clouds[i].y + fall, span = 70;
      m.position.y = ((y0 + 40) % span + span) % span - 40; m.material.uniforms.t.value = t;
      m.material.uniforms.fade.value = Math.min(1, Math.abs(camera.position.y - m.position.y) / 1.2);       // a layer fades as the camera passes through it
    });
    if (parts) parts.userData.update(t, sp.motion.fall);
  }
  return { scene, place };
}
