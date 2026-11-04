// Light, sky, fog, clouds and the post pass. Each light preset (lib/director.mjs lightPreset) is data; makeAtmosphere builds the
// sky dome / sun / hemisphere / fog / blocky clouds for one scene; makePost composites two scene render targets with a grade
// and the transitions (dissolve, dip to black, cloud wipe). Scenes render into half-float targets, so tone mapping, the sRGB
// encode and the grade all happen in the composite shader.
import * as THREE from '/three/three.module.min.js';

export const PRESETS = {
  day:      { top: '#3f7fd0', hor: '#bcd8f2', sun: '#fff1d6', sunI: 3.1, el: 52, az: 35, hemiSky: '#b9d4ff', hemiGnd: '#7d8a5c', hemiI: 1.15, fog: '#c9dcee', fogN: 260, fogF: 1100, clouds: 0.55, cloudCol: '#ffffff',
            exp: 1.0, sat: 1.08, con: 1.04, tint: [1, 1, 1], vig: 0.18, water: '#3b86a8' },
  overcast: { top: '#7f8c99', hor: '#b8c0c6', sun: '#e8ecef', sunI: 1.1, el: 60, az: 20, hemiSky: '#c5ccd3', hemiGnd: '#6a6f63', hemiI: 1.55, fog: '#aab2b8', fogN: 220, fogF: 1200, clouds: 1, cloudCol: '#c8ced2',
            exp: 0.98, sat: 0.78, con: 1.08, tint: [0.97, 1, 1.03], vig: 0.24, water: '#3a6672' },
  storm:    { top: '#3b434d', hor: '#6c747a', sun: '#aeb9c4', sunI: 0.55, el: 55, az: 20, hemiSky: '#8a949e', hemiGnd: '#4c5047', hemiI: 1.3, fog: '#60686e', fogN: 90, fogF: 560, clouds: 1.3, cloudCol: '#59616a',
            exp: 0.95, sat: 0.62, con: 1.14, tint: [0.94, 0.99, 1.06], vig: 0.34, water: '#2b4650' },
  dawn:     { top: '#5a7fb0', hor: '#f3b68b', sun: '#ffc78a', sunI: 2.5, el: 11, az: 110, hemiSky: '#9fb4d6', hemiGnd: '#7a6a58', hemiI: 0.95, fog: '#e5c3a5', fogN: 160, fogF: 900, clouds: 0.7, cloudCol: '#ffd9bd',
            exp: 1.02, sat: 1.0, con: 1.08, tint: [1.04, 0.99, 0.94], vig: 0.24, water: '#4a7b92' },
  sunset:   { top: '#3d5f98', hor: '#f08e55', sun: '#ff9a52', sunI: 2.9, el: 8, az: 250, hemiSky: '#8ea3c8', hemiGnd: '#7b5f4a', hemiI: 0.9, fog: '#e7a275', fogN: 160, fogF: 900, clouds: 0.8, cloudCol: '#ffb88a',
            exp: 1.04, sat: 1.1, con: 1.1, tint: [1.06, 0.98, 0.9], vig: 0.26, water: '#4f7385' },
  dusk:     { top: '#2b3f72', hor: '#b08aa0', sun: '#ffb59a', sunI: 1.6, el: 4, az: 255, hemiSky: '#7d8cc0', hemiGnd: '#5a5058', hemiI: 1.7, fog: '#7a7499', fogN: 200, fogF: 1000, clouds: 0.8, cloudCol: '#8a7f9f',
            exp: 1.18, sat: 0.95, con: 1.1, tint: [0.98, 0.97, 1.06], vig: 0.3, water: '#2a4660' },
  night:    { top: '#0a1430', hor: '#26396a', sun: '#a9c0f0', sunI: 1.9, el: 38, az: 300, hemiSky: '#5b74b0', hemiGnd: '#2a3142', hemiI: 2.1, fog: '#1c2a4a', fogN: 80, fogF: 520, clouds: 0.4, cloudCol: '#2c3a58',
            exp: 1.15, sat: 0.85, con: 1.1, tint: [0.92, 0.98, 1.12], vig: 0.34, night: true, stars: true, water: '#142a40' },
  interior_warm:  { top: '#303030', hor: '#303030', sun: '#ffe2b0', sunI: 0.5, el: 40, az: 280, hemiSky: '#e9d9bd', hemiGnd: '#6b4a32', hemiI: 1.0, fog: '#201a14', fogN: 400, fogF: 900, clouds: 0, cloudCol: '#fff',
            exp: 1.0, sat: 1.0, con: 1.08, tint: [1.04, 1, 0.94], vig: 0.34, interior: true, lamp: '#ffcf8a', lampI: 180 },
  interior_storm: { top: '#303030', hor: '#303030', sun: '#8ea0b8', sunI: 0.3, el: 40, az: 280, hemiSky: '#9aa3b2', hemiGnd: '#5a4430', hemiI: 0.8, fog: '#15171a', fogN: 400, fogF: 900, clouds: 0, cloudCol: '#fff',
            exp: 1.0, sat: 0.85, con: 1.12, tint: [0.98, 1, 1.04], vig: 0.38, interior: true, lamp: '#ffc47a', lampI: 170 },
  map:      { top: '#6e7f93', hor: '#a9b6c4', sun: '#fff4e0', sunI: 3.0, el: 50, az: 215, hemiSky: '#cfd8e2', hemiGnd: '#8a8f86', hemiI: 1.25, fog: '#a9b6c4', fogN: 2400, fogF: 6000, clouds: 0, cloudCol: '#fff',
            exp: 1.0, sat: 1.05, con: 1.06, tint: [1, 1, 1], vig: 0.2, map: true, water: '#3f7f9f' },
};

const skyVS = 'varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); gl_Position.z = gl_Position.w; }';
const skyFS = `varying vec3 vDir; uniform vec3 uTop, uHor, uSun; uniform vec3 uSunDir; uniform float uStars;
float h(vec3 p){ p = fract(p*0.3183099+.1); p *= 17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
void main(){
  float up = clamp(vDir.y, -0.2, 1.0);
  vec3 c = mix(uHor, uTop, pow(clamp(up,0.,1.), 0.55));
  c = mix(c, uHor*0.8, smoothstep(0.0,-0.2, vDir.y));
  float s = max(dot(vDir, uSunDir), 0.0);
  c += uSun * (pow(s, 600.0)*2.2 + pow(s, 14.0)*0.22 + pow(s,3.0)*0.07);
  if (uStars > 0.5 && vDir.y > 0.05) { vec3 q = floor(vDir*220.0); float r = h(q); c += vec3(step(0.9972, r)) * (0.5+0.5*h(q+3.1)) * smoothstep(0.05,0.4,vDir.y); }
  gl_FragColor = vec4(c, 1.0);
}`;

const C = (hex) => new THREE.Color(hex);

/** Everything atmospheric for one scene. update(t, camera, focus) moves the sky with the camera, the sun's shadow window with
 *  the action, and drifts the clouds (a pure function of t). */
export function makeAtmosphere(scene, presetName, weather, opts = {}) {
  const P = PRESETS[presetName] || PRESETS.day, out = { preset: P, name: presetName };
  const az = P.az * Math.PI / 180, el = P.el * Math.PI / 180;
  const sunDir = new THREE.Vector3(Math.cos(el) * Math.sin(az), Math.sin(el), Math.cos(el) * Math.cos(az)).normalize();
  const fogMul = weather === 'fog' ? 0.35 : weather === 'rain' ? 0.8 : weather === 'snow' ? 0.6 : 1;
  const fs = (opts.fogScale || 1) * fogMul; scene.fog = new THREE.Fog(C(P.fog), P.fogN * fs, P.fogF * fs);
  scene.background = C(P.hor);
  if (!P.interior) {
    const dome = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.ShaderMaterial({ vertexShader: skyVS, fragmentShader: skyFS, side: THREE.BackSide, depthWrite: false, fog: false,
      uniforms: { uTop: { value: C(P.top) }, uHor: { value: C(P.hor) }, uSun: { value: C(P.sun) }, uSunDir: { value: sunDir }, uStars: { value: P.stars ? 1 : 0 } } }));
    dome.scale.setScalar(3000); dome.frustumCulled = false; dome.renderOrder = -10; scene.add(dome); out.dome = dome;
  }
  const hemi = new THREE.HemisphereLight(C(P.hemiSky), C(P.hemiGnd), P.hemiI); scene.add(hemi);
  const sun = new THREE.DirectionalLight(C(P.sun), P.sunI);
  sun.castShadow = true; sun.shadow.mapSize.set(opts.shadowSize || 2048, opts.shadowSize || 2048);
  const R = P.map ? 700 : P.interior ? 40 : 120; Object.assign(sun.shadow.camera, { left: -R, right: R, top: R, bottom: -R, near: 1, far: 900 });
  sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.5; scene.add(sun, sun.target);
  out.sun = sun; out.sunDir = sunDir; out.shadowR = R;
  if (P.interior) { const lamp = new THREE.PointLight(C(P.lamp), P.lampI, 60, 1.6); lamp.position.set(0, 12, 0); lamp.castShadow = false; scene.add(lamp); out.lamp = lamp; }
  // blocky clouds: a few chunky boxes per cloud, one instanced mesh, drifting with time
  const amount = Math.round(18 * (P.clouds || 0) * (weather === 'clear' ? 0.9 : 1.2));
  if (amount > 0 && !P.interior) {
    const g = new THREE.BoxGeometry(1, 1, 1), mat = new THREE.MeshBasicMaterial({ color: C(P.cloudCol), fog: false, transparent: true, opacity: 0.94 });
    const list = []; let s = 1234567; const rnd = () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
    for (let i = 0; i < amount; i++) {
      const cx = (rnd() - 0.5) * 1900, cz = (rnd() - 0.5) * 1900, cy = 210 + rnd() * 90, n = 4 + Math.floor(rnd() * 4);
      for (let k = 0; k < n; k++) list.push({ x: cx + (k - n / 2) * 26 + rnd() * 10, y: cy + rnd() * 8, z: cz + (rnd() - 0.5) * 26, sx: 44 + rnd() * 30, sy: 14 + rnd() * 10, sz: 34 + rnd() * 20 });
    }
    const im = new THREE.InstancedMesh(g, mat, list.length); im.frustumCulled = false; scene.add(im); out.clouds = { im, list };
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), p = new THREE.Vector3(), sc = new THREE.Vector3();
    out.driftClouds = (t, cam) => {
      const wrap = 1000, dx = t * 3.2, dz = t * 0.8;
      list.forEach((c, i) => {
        let x = c.x + dx - cam.x, z = c.z + dz - cam.z;
        x = ((x + wrap) % (wrap * 2) + wrap * 2) % (wrap * 2) - wrap; z = ((z + wrap) % (wrap * 2) + wrap * 2) % (wrap * 2) - wrap;
        p.set(cam.x + x, c.y, cam.z + z); sc.set(c.sx, c.sy, c.sz); m4.compose(p, q, sc); im.setMatrixAt(i, m4);
      });
      im.instanceMatrix.needsUpdate = true;
    };
  }
  out.update = (t, camPos, focus) => {
    if (out.dome) out.dome.position.copy(camPos);
    if (out.driftClouds) out.driftClouds(t, camPos);
    const f = focus || camPos, q = P.map ? 4 : 0.5;
    const fx = Math.round(f.x / q) * q, fy = Math.round(f.y / q) * q, fz = Math.round(f.z / q) * q;
    sun.target.position.set(fx, fy, fz); sun.position.set(fx + sunDir.x * 300, fy + sunDir.y * 300, fz + sunDir.z * 300);
    sun.target.updateMatrixWorld();
  };
  return out;
}

const postVS = 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }';
const postFS = `varying vec2 vUv; uniform sampler2D tCur, tPrev; uniform int uMode; uniform float uP;
uniform vec4 gC, gP;      // exposure, saturation, contrast, vignette
uniform vec3 tC, tP;      // tint
uniform vec2 uRes;
float hash(vec2 p){ p = fract(p*vec2(123.34, 456.21)); p += dot(p, p+45.32); return fract(p.x*p.y); }
float vn(vec2 p){ vec2 i = floor(p), f = fract(p); f = f*f*(3.-2.*f); return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ return vn(p)*.5 + vn(p*2.03)*.25 + vn(p*4.1)*.125 + vn(p*8.3)*.0625; }
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14), 0.0, 1.0); }
vec3 srgb(vec3 c){ return mix(c*12.92, 1.055*pow(c, vec3(1.0/2.4)) - 0.055, step(0.0031308, c)); }
vec3 shade(sampler2D tex, vec4 g, vec3 tint){
  vec3 c = texture2D(tex, vUv).rgb * g.x;
  c = srgb(aces(c));
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(l), c, g.y);
  c = (c - 0.5) * g.z + 0.5;
  c *= tint;
  vec2 d = vUv - 0.5; d.x *= uRes.x/uRes.y;
  c *= 1.0 - g.w * smoothstep(0.25, 0.95, length(d)*1.25);
  return clamp(c, 0.0, 1.0);
}
void main(){
  vec3 a = shade(tCur, gC, tC), o = a;
  if (uMode > 0) {
    vec3 b = shade(tPrev, gP, tP);
    if (uMode == 1) o = mix(b, a, uP);
    else if (uMode == 2) o = uP < 0.5 ? b * (1.0 - uP*2.0) : a * (uP*2.0 - 1.0);
    else {
      float n = fbm(vUv*vec2(3.5, 2.2) + vec2(uP*0.8, 0.0)), k = 1.25 - abs(2.0*uP - 1.0)*1.25;
      float cover = smoothstep(n-0.15, n+0.15, k) * smoothstep(0.0, 0.12, uP) * smoothstep(0.0, 0.12, 1.0-uP);
      vec3 base = uP < 0.5 ? b : a;
      vec3 cloud = mix(vec3(0.80,0.84,0.90), vec3(1.0), fbm(vUv*6.0));
      o = mix(base, cloud, cover);
    }
  }
  gl_FragColor = vec4(o, 1.0);
}`;

/** The compositor. render(curTarget, prevTarget|null, mode, p, gradeCur, gradePrev) draws to the canvas. */
export function makePost(renderer, W, H) {
  const mk = () => new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4, depthBuffer: true, colorSpace: THREE.LinearSRGBColorSpace });
  const targets = [mk(), mk()];
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
  geom.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([0, 0, 2, 0, 0, 2]), 2));
  const u = { tCur: { value: null }, tPrev: { value: null }, uMode: { value: 0 }, uP: { value: 0 }, gC: { value: new THREE.Vector4(1, 1, 1, 0) }, gP: { value: new THREE.Vector4(1, 1, 1, 0) },
    tC: { value: new THREE.Vector3(1, 1, 1) }, tP: { value: new THREE.Vector3(1, 1, 1) }, uRes: { value: new THREE.Vector2(W, H) } };
  const mat = new THREE.ShaderMaterial({ vertexShader: postVS, fragmentShader: postFS, uniforms: u, depthTest: false, depthWrite: false });
  const quad = new THREE.Mesh(geom, mat); quad.frustumCulled = false;
  const sc = new THREE.Scene(); sc.add(quad);
  const cam = new THREE.Camera();
  const setGrade = (v, t, P) => { v.set(P.exp, P.sat, P.con, P.vig); t.set(...P.tint); };
  return {
    targets,
    composite(cur, prev, mode, p, Pcur, Pprev) {
      u.tCur.value = cur.texture; u.tPrev.value = prev ? prev.texture : cur.texture; u.uMode.value = mode; u.uP.value = p;
      setGrade(u.gC.value, u.tC.value, Pcur); setGrade(u.gP.value, u.tP.value, Pprev || Pcur);
      renderer.setRenderTarget(null); renderer.render(sc, cam);
    },
    dispose() { targets.forEach((t) => t.dispose()); mat.dispose(); },
  };
}
