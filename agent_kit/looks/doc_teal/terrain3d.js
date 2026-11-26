// REAL 3D TERRAIN: land and seafloor from the kit's `terrain` tool, with a water level you can move.
//   const T = await makeTerrain(canvas, '/@scene/med_dem', { exaggeration: 35 });
//   T.render({ water: 0, cam: { lon: 15, lat: 38, dist: 3.2, tilt: 50, heading: 0 } });   // every frame
//   const [x, y, visible] = T.screen(lon, lat);                                            // pin positions in px
// water: the sea level in metres (0 = today; -2500 = the Mediterranean drained 2.5 km). Exposed old seafloor turns to
// salt-white below `saltBelow` metres. cam: the point looked at, distance (scene units, the map is 4 wide), tilt in
// degrees from straight down, heading in degrees (0 = north up).
import * as THREE from '/agent_kit/lib/three.module.js';

const tileX = (lon) => (lon + 180) / 360;
const tileY = (lat) => { const r = lat * Math.PI / 180; return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2; };

export async function makeTerrain(canvas, base, { exaggeration = 22, saltBelow = -1200, segments = 640, background = 0x04141a } = {}) {
  const meta = await (await fetch(base + '.json')).json();
  const tex = await new THREE.TextureLoader().loadAsync(base + '.png');
  tex.colorSpace = THREE.NoColorSpace; tex.magFilter = THREE.LinearFilter; tex.minFilter = THREE.LinearFilter; tex.generateMipmaps = false;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true, alpha: false });
  renderer.setPixelRatio(1); renderer.setSize(canvas.width, canvas.height, false); renderer.setClearColor(background);
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(background, 3, 6);
  const camera = new THREE.PerspectiveCamera(35, canvas.width / canvas.height, 0.01, 50);
  const Wd = 4, Hd = 4 * meta.height / meta.width;
  const midLat = (meta.north + meta.south) / 2;
  const metresWide = (meta.east - meta.west) * 111320 * Math.cos(midLat * Math.PI / 180);
  const vScale = exaggeration * Wd / metresWide;
  const geo = new THREE.PlaneGeometry(Wd, Hd, segments, Math.round(segments * Hd / Wd));
  geo.rotateX(-Math.PI / 2);
  const uni = {
    dem: { value: tex }, vScale: { value: vScale }, texel: { value: new THREE.Vector2(1 / meta.width, 1 / meta.height) },
    water: { value: 0 }, water2: { value: 0 }, splitU: { value: -1 }, saltBelow: { value: saltBelow }, sun: { value: new THREE.Vector3(-0.5, 0.75, 0.45).normalize() },
    fogColor: { value: new THREE.Color(background) }, fogNear: { value: 3 }, fogFar: { value: 6 }, salt: { value: 1 },
  };
  const decode = `float elev(vec2 uv){ vec3 c = texture2D(dem, uv).rgb * 255.0; return c.r * 256.0 + c.g + c.b / 256.0 - 32768.0; }`;
  const mat = new THREE.ShaderMaterial({
    uniforms: uni,
    vertexShader: `uniform sampler2D dem; uniform float vScale; uniform vec2 texel; varying float vE; varying vec3 vN; varying vec3 vW; varying vec2 vUv;
      ${decode}
      void main(){
        vUv = uv; float e = elev(uv); vE = e;
        float ex = elev(uv + vec2(texel.x, 0.)) - elev(uv - vec2(texel.x, 0.));
        float ey = elev(uv + vec2(0., texel.y)) - elev(uv - vec2(0., texel.y));
        vN = normalize(vec3(-ex * vScale / (2.0 * texel.x * ${Wd.toFixed(3)}), 1.0, ey * vScale / (2.0 * texel.y * ${Hd.toFixed(3)})));
        vec3 p = position; p.y = max(e, -6000.0) * vScale;
        vec4 w = modelMatrix * vec4(p, 1.0); vW = w.xyz;
        gl_Position = projectionMatrix * viewMatrix * w;
      }`,
    fragmentShader: `uniform float water; uniform float water2; uniform float splitU; uniform float saltBelow; uniform float salt; uniform vec3 sun; uniform vec3 fogColor; uniform float fogNear; uniform float fogFar;
      varying float vE; varying vec3 vN; varying vec3 vW; varying vec2 vUv;
      float h(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
      void main(){
        float e = vE;
        float wl = vUv.x < splitU ? water2 : water;      // a second sea level west of splitU (e.g. the Atlantic)
        vec3 land;
        if (e > 0.0) {                                   // today's land: lowland olive -> tan -> rock -> snow
          land = mix(vec3(.30,.36,.22), vec3(.55,.48,.34), smoothstep(0., 900., e));
          land = mix(land, vec3(.45,.40,.36), smoothstep(900., 2200., e));
          land = mix(land, vec3(.92,.93,.95), smoothstep(2600., 3600., e));
        } else {                                         // seafloor: grey-brown slopes, salt-white deep basins when dry
          land = mix(vec3(.46,.42,.36), vec3(.34,.31,.28), smoothstep(0., -1500., e));
          float s = smoothstep(saltBelow + 300., saltBelow - 300., e) * salt;
          vec3 saltc = vec3(.93,.90,.82) * (.94 + .06 * h(floor(vUv * 900.)));
          land = mix(land, saltc, s);
        }
        float l = .28 + .8 * max(dot(normalize(vN), sun), 0.);
        vec3 col = land * l * .85;
        if (e < wl) {                                 // under water: teal shallows to deep navy, relief faintly visible
          float d = wl - e;
          vec3 wc = mix(vec3(.06,.38,.46), vec3(.015,.08,.13), smoothstep(0., 2500., d));
          col = mix(col, wc, .82 + .16 * smoothstep(0., 1500., d));
          col += vec3(.08,.12,.12) * smoothstep(120., 0., d);   // a bright rim where water meets the shore
        }
        float f = smoothstep(fogNear, fogFar, length(vW - cameraPosition));
        gl_FragColor = vec4(mix(col, fogColor, f), 1.0);
        #include <colorspace_fragment>
      }`,
  });
  scene.add(new THREE.Mesh(geo, mat));
  const pos = (lon, lat, e = 0) => {
    const u = (tileX(lon) * 2 ** meta.zoom - meta.mx0) / (meta.mx1 - meta.mx0);
    const v = (tileY(lat) * 2 ** meta.zoom - meta.my0) / (meta.my1 - meta.my0);
    return new THREE.Vector3((u - 0.5) * Wd, e * vScale, (v - 0.5) * Hd);
  };
  const api = {
    meta, scene, camera, renderer, THREE, pos, vScale,
    render({ water = 0, cam = {}, salt = 1, fog = [2.6, 5.2], west = null } = {}) {
      // west: { lon, water } gives everything west of lon its own sea level (an ocean outside a closed strait)
      uni.water.value = water; uni.water2.value = west ? west.water : water;
      uni.splitU.value = west ? (tileX(west.lon) * 2 ** meta.zoom - meta.mx0) / (meta.mx1 - meta.mx0) : -1; uni.salt.value = salt; uni.fogNear.value = fog[0]; uni.fogFar.value = fog[1];
      scene.fog.near = fog[0]; scene.fog.far = fog[1];
      const c = { lon: (meta.west + meta.east) / 2, lat: (meta.south + meta.north) / 2, dist: 3.6, tilt: 45, heading: 0, ...cam };
      const target = pos(c.lon, c.lat, c.alt || 0);
      const tl = c.tilt * Math.PI / 180, hd = c.heading * Math.PI / 180;
      camera.position.set(target.x - Math.sin(hd) * Math.sin(tl) * c.dist, target.y + Math.cos(tl) * c.dist, target.z + Math.cos(hd) * Math.sin(tl) * c.dist);
      camera.lookAt(target);
      renderer.render(scene, camera);
    },
    /** [x, y, inFront] in canvas px for a place (after render). */
    screen(lon, lat, e = 0) {
      const p = pos(lon, lat, e).project(camera);
      return [(p.x + 1) / 2 * canvas.width, (1 - p.y) / 2 * canvas.height, p.z < 1];
    },
  };
  return api;
}
