// BLACK HOLE hero scenes (V4 "What If You Explored a Black Hole"): a ray-traced black hole drawn by one fragment shader -- light rays
// bent by gravity step by step (Schwarzschild, the edge's radius = 1), a thin hot disc with the bright approaching side, and a star field
// with the Milky Way lensed round the shadow. Procedural and deterministic: no textures, no generated pictures, the same frame every time.
//   blackhole_disc     the classic edge-on view, the disc wrapped over and under the shadow (V4 0:30, 0:45)
//   blackhole_top      seen from above at 55 degrees (V4 4:00)
//   blackhole_ring     close in: the bright ring fills the frame (V4 3:05 "THE BRIGHT EDGE")
//   blackhole_lensing  no disc: the star field bent round a black hole ("Gaia" views, V4 1:30, 7:50)
//   blackhole_horizon  hovering just above the edge: a black frame with a thin curve of light (V4 3:00)
//   shot.cam: { dist, el (deg), az (deg), fov (deg), roll (deg), push (0..1 closer over the shot), orbit (deg over the shot), x (0..1 frame
//               position), bright, disc_in, disc_out, stars, steps }
export const BLACKHOLE_SCENES = ['blackhole_disc', 'blackhole_top', 'blackhole_ring', 'blackhole_lensing', 'blackhole_horizon'];

const PRESETS = {
  blackhole_disc: { dist: 24, el: 5, az: 0, fov: 38, roll: -4, disc: 1 },
  blackhole_top: { dist: 28, el: 55, az: 20, fov: 36, roll: 0, disc: 1 },
  blackhole_ring: { dist: 7.5, el: 3, az: 0, fov: 64, roll: -3, disc: 1, bright: 1.25 },
  blackhole_lensing: { dist: 18, el: 2, az: 0, fov: 50, roll: 0, disc: 0, stars: 1.4 },
  blackhole_horizon: { dist: 2.6, el: 12, az: 0, fov: 75, roll: 0, disc: 1, bright: 0.8, look_up: 1.2, push: 0.03 },   // inside 2.0 the shadow fills the frame (black)
};

const VERT = 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }';
const FRAG = `
precision highp float;
uniform vec2 uRes; uniform float uTime; uniform vec3 uCamPos; uniform mat3 uCamRot; uniform float uFov; uniform vec2 uShift;
uniform float uDisc; uniform float uIn; uniform float uOut; uniform float uBright; uniform float uStars; uniform float uSteps;
varying vec2 vUv;
float hash(vec3 p){ p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  float a = hash(vec3(i, 1.0)), b = hash(vec3(i + vec2(1.0, 0.0), 1.0)), c = hash(vec3(i + vec2(0.0, 1.0), 1.0)), d = hash(vec3(i + vec2(1.0, 1.0), 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y); }
vec3 sky(vec3 d){
  vec3 col = vec3(0.0);
  for (int l = 0; l < 2; l++) {
    float sc = l == 0 ? 160.0 : 380.0; vec3 p = d * sc; vec3 id = floor(p); vec3 f = fract(p) - 0.5;
    float h = hash(id + float(l) * 7.13);
    if (h > 0.982) { float br = (h - 0.982) / 0.018; float s = smoothstep(0.14, 0.0, length(f));
      col += s * br * mix(vec3(1.0, 0.86, 0.7), vec3(0.72, 0.84, 1.0), hash(id * 1.7)) * (l == 0 ? 1.8 : 1.0); }
  }
  vec3 n = normalize(vec3(0.3, 1.0, 0.4)); float b = 1.0 - abs(dot(d, n)); float band = pow(max(b, 0.0), 8.0);
  float lon = atan(d.z, d.x);
  float dust = noise(vec2(lon * 7.0, d.y * 15.0)) * (0.5 + 0.5 * noise(vec2(lon * 23.0, d.y * 40.0)));
  float lanes = smoothstep(0.35, 0.65, noise(vec2(lon * 12.0 + 3.0, d.y * 26.0)));
  col += band * vec3(0.62, 0.55, 0.47) * 0.55 * (0.35 + dust) * (1.0 - 0.6 * lanes);
  return col * uStars;
}
void main(){
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y - uShift;
  vec3 rd = normalize(uCamRot * vec3(uv * tan(uFov * 0.5) * 2.0, -1.0));
  vec3 pos = uCamPos; vec3 vel = rd;
  vec3 hv = cross(pos, vel); float h2 = dot(hv, hv);
  vec3 col = vec3(0.0); float alpha = 0.0; bool fell = false;
  for (int i = 0; i < 420; i++) {
    if (float(i) > uSteps) break;
    float r2 = dot(pos, pos); float r = sqrt(r2);
    float dt = clamp(0.05 * r, 0.012, 1.2);
    vec3 prev = pos;
    vel += -1.5 * h2 * pos / (r2 * r2 * r) * dt;
    pos += vel * dt;
    if (dot(pos, pos) < 1.0) { fell = true; break; }
    if (uDisc > 0.5 && prev.y * pos.y < 0.0) {
      vec3 p = mix(prev, pos, prev.y / (prev.y - pos.y)); float rr = length(p.xz);
      if (rr > uIn && rr < uOut) {
        float ang = atan(p.z, p.x), t = (rr - uIn) / (uOut - uIn);
        float temp = pow(uIn / rr, 1.5);
        float spin = uTime * 1.6 / pow(rr, 1.5);
        float streak = 0.55 + 0.45 * noise(vec2(rr * 2.6, (ang - spin) * 7.0)) * (0.6 + 0.4 * noise(vec2(rr * 11.0, (ang - spin) * 24.0)));
        vec3 tangent = normalize(vec3(-p.z, 0.0, p.x));
        float v = sqrt(0.5 / rr);
        float dop = 1.0 / max(0.2, 1.0 - v * dot(tangent, -normalize(vel)));
        vec3 c = mix(vec3(1.0, 0.46, 0.12), vec3(1.0, 0.84, 0.58), clamp(temp * 1.2, 0.0, 1.0)) * temp * streak * pow(dop, 3.0) * uBright * 1.6;   // V4's gold, cream where hottest
        float a = clamp(smoothstep(0.0, 0.06, t) * smoothstep(1.0, 0.55, t) * 0.92, 0.0, 1.0);
        col += (1.0 - alpha) * c * a; alpha += (1.0 - alpha) * a;
        if (alpha > 0.985) break;
      }
    }
    if (r > 80.0 && dot(pos, vel) > 0.0) break;
  }
  if (!fell) col += (1.0 - alpha) * sky(normalize(vel));
  col = 1.0 - exp(-col * 1.5);
  gl_FragColor = vec4(pow(col, vec3(1.0 / 2.2)), 1.0);
}`;

/** -> { scene, place(camera, k, W, H) } like every hero scene (lib/hero.mjs). */
export function blackholeScene(THREE, shot) {
  const cam = { ...(PRESETS[shot.scene] || PRESETS.blackhole_disc), ...(shot.cam || {}) };
  const uniforms = {
    uRes: { value: new THREE.Vector2(1280, 720) }, uTime: { value: 0 }, uCamPos: { value: new THREE.Vector3() }, uCamRot: { value: new THREE.Matrix3() },
    uFov: { value: (cam.fov * Math.PI) / 180 }, uShift: { value: new THREE.Vector2(0, 0) }, uDisc: { value: cam.disc ? 1 : 0 },
    uIn: { value: cam.disc_in ?? 3.0 }, uOut: { value: cam.disc_out ?? 14.0 }, uBright: { value: cam.bright ?? 1.0 }, uStars: { value: cam.stars ?? 1.0 },
    uSteps: { value: cam.steps ?? 400 },
  };
  const mat = new THREE.ShaderMaterial({ uniforms, vertexShader: VERT, fragmentShader: FRAG, depthTest: false, depthWrite: false, toneMapped: false });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat); quad.frustumCulled = false;
  const scene = new THREE.Scene(); scene.add(quad);
  return {
    scene,
    place(camera, k, W, H) {
      const t = k * (shot.end - shot.start);
      const dist = cam.dist * (1 - (cam.push ?? 0.06) * k), el = ((cam.el + (cam.rise ?? 0) * k) * Math.PI) / 180, az = ((cam.az + (cam.orbit ?? 6) * k) * Math.PI) / 180;
      const p = new THREE.Vector3(Math.sin(az) * Math.cos(el) * dist, Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist);
      const target = new THREE.Vector3(0, (cam.look_up ?? 0) * dist * 0.4, 0);
      const fwd = target.clone().sub(p).normalize(), worldUp = new THREE.Vector3(0, 1, 0);
      let right = new THREE.Vector3().crossVectors(fwd, worldUp).normalize();
      let upv = new THREE.Vector3().crossVectors(right, fwd).normalize();
      const roll = ((cam.roll ?? 0) * Math.PI) / 180, cr = Math.cos(roll), sr = Math.sin(roll);
      const r2 = right.clone().multiplyScalar(cr).add(upv.clone().multiplyScalar(sr)), u2 = upv.clone().multiplyScalar(cr).sub(right.clone().multiplyScalar(sr));
      right = r2; upv = u2;
      const back = fwd.clone().negate();
      uniforms.uCamRot.value.set(right.x, upv.x, back.x, right.y, upv.y, back.y, right.z, upv.z, back.z);
      uniforms.uCamPos.value.copy(p);
      uniforms.uRes.value.set(W, H);
      uniforms.uTime.value = t + (cam.t0 ?? 0);
      uniforms.uShift.value.set(((cam.x ?? 0.5) - 0.5) * (W / H), 0);
      camera.aspect = W / H; camera.updateProjectionMatrix();
    },
  };
}
