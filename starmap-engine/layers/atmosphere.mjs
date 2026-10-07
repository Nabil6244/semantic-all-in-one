// ATMOSPHERE: a thin glowing shell for any body with air (Earth, Mars, Venus, Titan...). For every pixel it measures how
// close the line of sight passes to the body, so the glow is strongest along the limb and fades outward over the
// atmosphere's height; it is lit only where the real Sun lights it (a little past the terminator, as twilight is), and
// over the disk it is faint, so the terminator and the surface stay as they are. Off when the body is a few pixels.
//   { "type": "atmosphere", "body": "earth", "height_km": 110, "color": "#6fa8ff", "intensity": 1.0, "min_px": 10 }
const VERT = `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vP;
void main() {
  vec4 wp = modelMatrix * vec4(position, 1.0);
  vP = wp.xyz;
  gl_Position = projectionMatrix * viewMatrix * wp;
  #include <logdepthbuf_vertex>
}`;
const FRAG = `
#include <common>
#include <logdepthbuf_pars_fragment>
uniform vec3 uCentre; uniform vec3 uSun; uniform vec3 uColor; uniform float uR; uniform float uH; uniform float uI; uniform float uDisk;
varying vec3 vP;
void main() {
  #include <logdepthbuf_fragment>
  vec3 v = normalize(vP - cameraPosition);
  vec3 c = uCentre - cameraPosition;
  float tc = dot(c, v);
  vec3 closest = v * tc - c;
  float b = length(closest);
  float glow; vec3 n;
  if (b >= uR) {                                    // the line of sight misses the body: air only, thinning with height
    float x = (b - uR) / uH;
    glow = exp(-4.0 * x) * (1.0 - smoothstep(0.75, 1.0, x));
    n = closest / max(b, 1e-6);
  } else {                                          // over the disk: the air in front of the ground, thicker towards the limb
    float mu = sqrt(max(0.0, 1.0 - (b * b) / (uR * uR)));
    glow = uDisk * 0.12 / (mu + 0.12);
    vec3 hit = v * (tc - sqrt(max(0.0, uR * uR - b * b))) - c;
    n = normalize(hit);
  }
  float lit = smoothstep(-0.18, 0.28, dot(n, uSun));
  float a = clamp(glow * lit * uI, 0.0, 1.0);
  gl_FragColor = vec4(uColor * a, a);
}`;

export default {
  type: 'atmosphere',
  space: 'world',
  create(def, ctx) {
    const { THREE, world } = ctx;
    const body = world.get(def.body);
    if (!body) throw new Error(`atmosphere: unknown body ${def.body}`);
    const H = def.height_km || body.radiusKm * 0.02;
    const mat = new THREE.ShaderMaterial({
      uniforms: { uCentre: { value: new THREE.Vector3() }, uSun: { value: new THREE.Vector3(1, 0, 0) }, uColor: { value: new THREE.Color(def.color || '#6fa8ff') },
        uR: { value: body.radiusKm }, uH: { value: H }, uI: { value: 0 }, uDisk: { value: def.disk ?? 1 } },
      vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    const shell = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 48), mat);
    shell.scale.setScalar(body.radiusKm + H); shell.visible = false; shell.renderOrder = 3; ctx.scene.add(shell);
    return { def, body, shell, mat };
  },
  update(inst, f) {
    const b = f.bodies.find((x) => x.id === inst.def.body);
    const k = b ? Math.min(1, Math.max(0, (b.px - (inst.def.min_px ?? 10)) / 10)) : 0;
    inst.shell.visible = f.alpha * k > 0.002 && !!b;
    if (!inst.shell.visible) return;
    inst.shell.position.set(...b.p);
    inst.mat.uniforms.uCentre.value.set(...b.p);
    const s = f.sunFrom(inst.def.body);
    if (s) inst.mat.uniforms.uSun.value.set(...s);
    inst.mat.uniforms.uI.value = (inst.def.intensity ?? 1) * f.alpha * k;
  },
};
