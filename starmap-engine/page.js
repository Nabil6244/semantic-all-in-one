// StarMap page (runs in the headless browser): one three.js scene drawn with a floating origin, plus a 2D overlay.
// window.renderFrame(t) -> JPEG (base64) of the frame at narration time t: the map, any footage beat over it (lib/footage.mjs),
// and the layers that stay over footage (a channel name).
//
// Every frame: the universe clock gives the date -> the world moves every body to that date and turns it (real
// ephemerides and IAU rotation) -> the camera resolves its shot -> every body is placed RELATIVE TO THE CAMERA through the
// frame tree (world.vec from the camera's anchor body), so nothing near the camera loses precision. A logarithmic depth
// buffer covers metres to millions of light-years. Bodies bigger than a few pixels are lit spheres; smaller, a glow point.
// Everything on top of the bare universe -- labels, paths, spacecraft, markers, chips, cards -- is a LAYER from the
// registry (lib/layers.mjs, layers/*.mjs), configured by spec.layers; this file knows no mission and no place.
import * as THREE from '/three/three.module.min.js';
import { buildWorld, anchorTarget, galacticBasis } from '/lib/world.mjs';
import { createRegistry, runLayers, defaultLayers, overFootage } from '/lib/layers.mjs';
import { planFootage, clipFrameIndex, kenBurnsAt } from '/lib/footage.mjs';
import { registerBuiltins } from '/layers/index.mjs';
import { ui } from '/layers/ui.mjs';
import { createCamera } from '/lib/camera.mjs';
import { trajectoryLookup } from '/lib/paths.mjs';
import { createClock } from '/lib/clock.mjs';
import { radecToEngine, offsetOf } from '/lib/ephemeris.mjs';
import { KM_PER_LY } from '/lib/units.mjs';

const spec = await (await fetch('/spec.json')).json();
const W = spec.width, H = spec.height, FOV = spec.fov_deg || 40;
// footage beats freeze MAP time (fp.mu): the universe clock, the camera and layer animations run on it
const fp = planFootage(spec);
if (fp.problems.length) throw new Error(`footage: ${fp.problems.join('; ')}`);
const clock = createClock(fp.mapClock(spec.clock));
const world = buildWorld(spec.world, { date: clock.utc(fp.mu(0)) });
const camAt = createCamera(world, { fov_deg: FOV, aspect: W / H, ...fp.mapCamera(spec.camera) }, { trajectory: trajectoryLookup(world, spec.layers || []), dateAt: (t) => clock.utc(t) });
const storyClock = { utc: (t) => clock.utc(fp.mu(t)), met: (t) => clock.met(fp.mu(t)) };   // what layers read, by narration t
const focalPx = (H / 2) / Math.tan((FOV / 2) * Math.PI / 180);
const ramp = (v, a, b) => Math.min(1, Math.max(0, (v - a) / (b - a)));

const glCanvas = document.createElement('canvas'); glCanvas.width = W; glCanvas.height = H;
const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, preserveDrawingBuffer: true, logarithmicDepthBuffer: true });
renderer.setSize(W, H, false);
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(FOV, W / H, 1e-3, 1e21);
const out = document.createElement('canvas'); out.width = W; out.height = H;
const ctx = out.getContext('2d');

const loader = new THREE.TextureLoader();
const tex = async (name) => { const t = await loader.loadAsync(`/textures/${name}`); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; };
function glowTexture(color) {
  const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d');
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.18, color); grd.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

// ---- the sky from inside the galaxy: the real bright-star catalogue + a faint band along the galactic plane ----------------
function bvColor(bv) {   // B-V colour index -> an approximate star colour
  const t = Math.min(2, Math.max(-0.4, bv));
  const r = t < 0.4 ? 0.62 + 0.6 * (t + 0.4) : 1.0, g = t < 0.4 ? 0.75 + 0.4 * (t + 0.4) : 1.0 - 0.32 * (t - 0.4), b = t < 0.4 ? 1.0 : 1.0 - 0.55 * (t - 0.4);
  return [Math.min(1, r), Math.min(1, g), Math.max(0.35, b)];
}
const pointShader = () => new THREE.ShaderMaterial({
  uniforms: { opacity: { value: 1 } },
  vertexShader: 'attribute float size; attribute vec3 color; varying vec3 vC; void main(){ vC = color; gl_PointSize = size; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_Position.z = gl_Position.w * 0.999999; }',
  fragmentShader: 'uniform float opacity; varying vec3 vC; void main(){ vec2 p = gl_PointCoord - 0.5; float d = length(p) * 2.0; float a = smoothstep(1.0, 0.15, d); gl_FragColor = vec4(vC * a, a * opacity); }',
  transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending,   // far plane depth: hidden by bodies
});
const catalog = await (await fetch('/catalogs/bright_stars.json')).json();
const sky = (() => {
  const S = catalog.stars, N = S.length, pos = new Float32Array(N * 3), col = new Float32Array(N * 3), size = new Float32Array(N);
  S.forEach(([ra, dec, vmag, bv], i) => {
    pos.set(radecToEngine(ra, dec), i * 3);
    const lum = Math.pow(10, -0.4 * (vmag - 1.0));                // brightness relative to a magnitude-1 star
    const c = bvColor(bv), b = Math.min(1, 0.4 + 0.6 * Math.sqrt(Math.min(1, lum)));
    col.set(c.map((x) => x * b), i * 3);
    size[i] = Math.min(10, 2.2 + 3.4 * Math.sqrt(lum));
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3)); geo.setAttribute('size', new THREE.BufferAttribute(size, 1));
  const pts = new THREE.Points(geo, pointShader()); pts.renderOrder = -9; pts.frustumCulled = false; scene.add(pts); return pts;
})();
const band = (() => {
  // unresolved Milky Way light: many faint points concentrated on the galactic plane, densest towards the centre
  const B = galacticBasis(), N = 40000, pos = new Float32Array(N * 3), col = new Float32Array(N * 3), size = new Float32Array(N);
  let s = 3; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const gauss = () => { let u = 0; for (let k = 0; k < 4; k++) u += rnd(); return (u - 2) / 2; };
  for (let i = 0; i < N; i++) {
    const towardCentre = rnd() < 0.45;
    const l = towardCentre ? gauss() * 0.9 : rnd() * Math.PI * 2;            // galactic longitude (0 = the centre)
    const b = gauss() * (towardCentre ? 0.16 : 0.07);                        // galactic latitude
    // local galactic axes: -z points at the centre (the Sun is at +z), y = north
    const v = [Math.sin(l) * Math.cos(b), Math.sin(b), -Math.cos(l) * Math.cos(b)];
    pos.set([0, 1, 2].map((k) => B.x[k] * v[0] + B.y[k] * v[1] + B.z[k] * v[2]), i * 3);
    const warm = towardCentre ? 0.8 : 0.35, a = 0.018 + 0.03 * rnd();
    col.set([a * (0.85 + 0.15 * warm), a * (0.82 + 0.08 * warm), a * (1 - 0.3 * warm)], i * 3);
    size[i] = 3 + 4 * rnd();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3)); geo.setAttribute('size', new THREE.BufferAttribute(size, 1));
  const pts = new THREE.Points(geo, pointShader()); pts.renderOrder = -10; pts.frustumCulled = false; scene.add(pts); return pts;
})();

// ---- the universe at large: galaxies by the thousand, in clumps, out to where light has had 13.8 billion years to come from;
// seen only once the camera is tens of millions of light-years out (positions are illustrative, the scale is real) ----------
const COSMOS_LY = 13.8e9;
const cosmos = (() => {
  const N = 16000, pos = new Float32Array(N * 3), col = new Float32Array(N * 3), size = new Float32Array(N);
  let s = 11; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  const inBall = () => { for (;;) { const v = [rnd() * 2 - 1, rnd() * 2 - 1, rnd() * 2 - 1]; if (Math.hypot(...v) <= 1) return v; } };
  const clumps = Array.from({ length: 420 }, () => inBall().map((c) => c * COSMOS_LY));
  for (let i = 0; i < N; i++) {
    let v;
    if (rnd() < 0.7) { const c = clumps[Math.floor(rnd() * clumps.length)], sp = 0.035 * COSMOS_LY; v = c.map((x) => x + (rnd() + rnd() + rnd() - 1.5) * sp); }
    else v = inBall().map((c) => c * COSMOS_LY);
    pos.set(v.map((c) => c * KM_PER_LY), i * 3);
    const warm = rnd(), a = 0.35 + 0.65 * rnd();
    col.set([a * (0.75 + 0.25 * warm), a * (0.78 + 0.1 * warm), a * (1 - 0.35 * warm)], i * 3);
    size[i] = 1.6 + 2.6 * rnd() * rnd();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); geo.setAttribute('color', new THREE.BufferAttribute(col, 3)); geo.setAttribute('size', new THREE.BufferAttribute(size, 1));
  const pts = new THREE.Points(geo, pointShader()); pts.renderOrder = -8; pts.frustumCulled = false; pts.visible = false; scene.add(pts); return pts;
})();

// ---- bodies ------------------------------------------------------------------------------------------------------------
const sunLight = new THREE.PointLight(0xffffff, 3.2, 0, 0); scene.add(sunLight);
scene.add(new THREE.AmbientLight(0xffffff, 0.03));
const bodies = [];
const basisQuat = (B) => new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(new THREE.Vector3(...B.x), new THREE.Vector3(...B.y), new THREE.Vector3(...B.z)));
for (const n of world.nodes.values()) {
  const g = new THREE.Group(); scene.add(g);
  const b = { n, g, mesh: null, point: null, orbit: null };
  if (n.kind === 'body' || n.kind === 'star') {
    const map = n.texture ? await tex(n.texture) : null;
    const mat = n.kind === 'star' ? new THREE.MeshBasicMaterial({ map, color: map ? 0xffffff : (n.color || '#fff4d6') })
      : new THREE.MeshStandardMaterial({ map, color: map ? 0xffffff : (n.color || '#aaaaaa'), roughness: 1, metalness: 0,
          // relief from an elevation map (craters show their shape under a low Sun), and a faint fill so a night or
          // low-Sun side still reads on screen ("min_light", a documentary choice, 0 = physically dark)
          bumpMap: n.bump ? await tex(n.bump) : null, bumpScale: n.bump_scale ?? 1,
          emissiveMap: map && n.min_light ? map : null, emissive: n.min_light ? 0xffffff : 0x000000, emissiveIntensity: n.min_light || 0 });
    if (n.night && n.kind === 'body') {
      // city lights on the NIGHT side only: the emissive map is masked by the real Sun direction (a soft band at the terminator)
      mat.emissiveMap = await tex(n.night); mat.emissive = new THREE.Color(n.night_color || '#ffd8a0');
      mat.emissiveIntensity = n.night_intensity ?? 1.6;
      b.sunView = { value: new THREE.Vector3(1, 0, 0) };
      mat.onBeforeCompile = (sh) => {
        sh.uniforms.uSunView = b.sunView;
        sh.fragmentShader = 'uniform vec3 uSunView;\n' + sh.fragmentShader.replace('#include <emissivemap_fragment>',
          '#ifdef USE_EMISSIVEMAP\n  vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );\n'
          + '  totalEmissiveRadiance *= emissiveColor.rgb * smoothstep( 0.12, -0.2, dot( normal, normalize( uSunView ) ) );\n#endif');
      };
    }
    b.mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64), mat); b.mesh.scale.setScalar(n.radiusKm); g.add(b.mesh);
    if (n.clouds) {
      // a cloud shell just above the surface, turning with the body (its brightness is its opacity)
      const ct = await tex(n.clouds); ct.colorSpace = THREE.NoColorSpace;
      b.clouds = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 48), new THREE.MeshStandardMaterial({ color: 0xffffff, alphaMap: ct, transparent: true, depthWrite: false, roughness: 1, metalness: 0 }));
      b.clouds.scale.setScalar(n.radiusKm * 1.006); g.add(b.clouds);
    }
    if (n.rings) {     // a ring in the body's equatorial plane, its texture running from the inner to the outer edge
      const inner = n.radiusKm * n.rings.inner, outer = n.radiusKm * n.rings.outer;
      const geo = new THREE.RingGeometry(inner, outer, 256, 1);
      const p = geo.attributes.position, uv = geo.attributes.uv;
      for (let i = 0; i < p.count; i++) uv.setXY(i, (Math.hypot(p.getX(i), p.getY(i)) - inner) / (outer - inner), 0.5);
      b.ring = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: await tex(n.rings.texture), transparent: true, side: THREE.DoubleSide, roughness: 1, depthWrite: false }));
      g.add(b.ring);
    }
    b.point = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(n.glow || n.color || '#cfd8ff'), sizeAttenuation: false, depthWrite: false, transparent: true, blending: THREE.AdditiveBlending }));
    if (n.kind === 'star') {     // a soft corona its own size round every star: the Sun glows, it is not a hard disk on black
      b.corona = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(n.glow || '#ffcf70'), depthWrite: false, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending }));
      b.corona.scale.setScalar(n.radiusKm * 7); g.add(b.corona);
    }
    g.add(b.point);
  }
  if (n.kind === 'galaxy' && !n.texture) {
    // a small galaxy without a picture of its own (the Magellanic Clouds, Triangulum): a soft glow its real size
    b.mesh = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(n.glow || '#c9d4ff'), transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    b.mesh.scale.setScalar(2.2 * n.radiusKm); g.add(b.mesh);
  } else if (n.kind === 'galaxy') {
    // the face-on disk: a NASA/JPL-Caltech illustration in the galactic plane, its Sun side (image bottom) towards the real Sun
    const half = n.image_half_width ? n.image_half_width.ly * KM_PER_LY : n.radiusKm;
    const disk = new THREE.Mesh(new THREE.PlaneGeometry(2 * half, 2 * half), new THREE.MeshBasicMaterial({ map: await tex(n.texture), transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    disk.rotation.x = -Math.PI / 2;                                 // image bottom -> +z (the Sun's side)
    if (n.image_turn_deg) disk.rotation.z = (n.image_turn_deg * Math.PI) / 180;
    b.mesh = disk; g.add(disk);
  }
  if (n.parent && n.show_orbit) {
    if (!n.orbit_normal && n.offset && n.offset.ephemeris) {
      const d0 = clock.utc(fp.mu(0)), d1 = new Date(+d0 + (n.parent === 'sun' ? 20 : 1) * 86400e3);
      const a = offsetOf(n.offset.ephemeris, d0), c = offsetOf(n.offset.ephemeris, d1);
      b.orbitNormal = [a[1] * c[2] - a[2] * c[1], a[2] * c[0] - a[0] * c[2], a[0] * c[1] - a[1] * c[0]];
    }
    const pts = []; for (let k = 0; k <= 256; k++) { const a = (k / 256) * Math.PI * 2; pts.push(new THREE.Vector3(Math.cos(a), 0, Math.sin(a))); }
    b.orbit = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x9fb4d8, transparent: true, opacity: 0.35, depthWrite: false }));
    scene.add(b.orbit);
  }
  bodies.push(b);
}

// ---- layers ----------------------------------------------------------------------------------------------------------------
await document.fonts.load('800 30px StarMapSans');
const u = ui(ctx, W);
const imageCache = new Map();
const modelCache = new Map();
let sharedDraco = null;
const layerCtx = {
  THREE, scene, world, spec, clock: storyClock, W, H, focalPx,
  tex,
  /** The sphere mesh of a body (turns with its surface): surface layers attach to it. */
  bodyMesh(id) { const b = bodies.find((x) => x.n.id === id); if (!b || !b.mesh) throw new Error(`no body mesh for ${id}`); return b.mesh; },
  /** An image from the spec's media folder (content, not engine assets). */
  loadImage(name) {
    if (!imageCache.has(name)) imageCache.set(name, new Promise((ok, fail) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => fail(new Error(`image ${name} not found in media`)); im.src = `/media/${encodeURIComponent(name)}`; }));
    return imageCache.get(name);
  },
  /** A glTF/GLB model from the media folder (three.js GLTFLoader, loaded only when a spec asks for a model). */
  async loadModel(name) {
    // each model file is loaded (and decoded) once and cloned for every craft that uses it: one Draco decoder for all, so a
    // video with dozens of craft appearances never runs the page out of memory (33 Voyager rows did)
    if (!modelCache.has(name)) modelCache.set(name, (async () => {
      const { GLTFLoader } = await import('/three/addons/loaders/GLTFLoader.js');
      // "wi:voyager.glb": one of the NASA 3D models shipped with the What If engine (Cinema mode's hero shots)
      const wi = String(name).startsWith('wi:');
      const url = wi ? `/wi-models/${encodeURIComponent(name.slice(3))}` : `/media/${encodeURIComponent(name)}`;
      const loader = new GLTFLoader();
      if (wi) {   // NASA's models are Draco-compressed
        if (!sharedDraco) {
          const { DRACOLoader } = await import('/three/addons/loaders/DRACOLoader.js');
          sharedDraco = new DRACOLoader().setDecoderPath('/three/addons/libs/draco/gltf/');
        }
        loader.setDRACOLoader(sharedDraco);
      }
      return (await loader.loadAsync(url)).scene;
    })());
    return (await modelCache.get(name)).clone(true);
  },
};
const registry = registerBuiltins(createRegistry());
// Cinema mode (spec.cinema): the What If engine's diagram plates, type moments and citation line, its fonts, and a slate plate
// behind a diagram. Classic StarMap (no spec.cinema) loads none of it.
if (spec.cinema) {
  for (const [family, file, weight] of [['TMSans', 'Inter-SemiBold.ttf', '600'], ['TMSans', 'Inter-Bold.ttf', '700'], ['WIMono', 'JetBrainsMono-SemiBold.ttf', '600'], ['WIMono', 'JetBrainsMono-Bold.ttf', '700']]) {
    try { const ff = new FontFace(family, `url(/wi-fonts/${file})`, { weight }); await ff.load(); document.fonts.add(ff); } catch (e) { console.warn(`cinema font ${file}: ${e.message}`); }
  }
  // every What If layer: plates (timeline, light-time axis, cross-section, comparisons, bars, curves, composition, orbit map,
  // phase, waveform, grid, disc map, dials), instruments (survival clock, clocks, gauge), type, captions, titles, fades, citations,
  // the template library (whatif-engine/templates: fact blocks, mission intros, before/after ...) and the mission card
  for (const name of ['tm_metric', 'tm_cite', 'tm_timeline', 'tm_logaxis', 'tm_section', 'tm_compare', 'tm_dial', 'tm_title', 'tm_annotate',
    'tm_bars', 'tm_caption', 'tm_clock', 'tm_composition', 'tm_curve', 'tm_discmap', 'tm_fade', 'tm_gauge', 'tm_grid', 'tm_orbitmap',
    'tm_phase', 'tm_survival', 'tm_wave', 'tm_template', 'tm_mission']) {
    registry.register((await import(`/wi/layers/${name}.mjs`)).default);
  }
  // this video's information colour (whatif/variety.py pick_look): what the templates call cyan / info
  if (spec.cinema_look?.accent) {
    (await import('/wi/layers/tm_theme.mjs')).colourSet(spec.cinema_look.accent);
    (await import('/wi/lib/tpl.mjs')).setAccent(spec.cinema_look.accent);
  }
  // a What If hero scene (a lander on the plain, a descent under a parachute, an airship over clouds, a ship with engines): its own
  // composed 3D scene, rendered full-frame over the map for its window
  const { buildHero } = await import('/wi/lib/hero.mjs');
  registry.register({
    type: 'cinema_hero', space: 'screen',
    create: (def) => ({ def, hero: buildHero(THREE, { kind: 'hero', scene: def.scene, cam: def.cam || {}, start: def.start, end: def.end }),
      cam: new THREE.PerspectiveCamera(30, W / H, 0.05, 2000) }),
    draw(inst, f) {
      const d = inst.def, k = Math.min(1, Math.max(0, (f.t - d.start) / Math.max(0.1, d.end - d.start)));
      inst.hero.place(inst.cam, k, W, H);
      renderer.render(inst.hero.scene, inst.cam);
      f.g.save(); f.g.globalAlpha = f.alpha; f.g.drawImage(glCanvas, 0, 0); f.g.restore();
    },
  });
  // What If's deep-space craft shot: the craft's NASA model over a dense Milky Way sky, lit from one side, the camera
  // slowly orbiting and closing in -- its own scene, full frame, independent of the map's camera (shot type A2 of the references)
  const rndS = (seed) => { let x = seed >>> 0 || 1; return () => ((x = (x * 1664525 + 1013904223) >>> 0) / 4294967296); };
  const deepSky = (seed) => {
    const grp = new THREE.Group(), r = rndS(seed), n = 9000, pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const u = r() * 2 - 1, a = r() * Math.PI * 2, q = Math.sqrt(1 - u * u), b = 0.25 + 0.75 * r() ** 3, w = r();
      pos.set([300 * q * Math.cos(a), 300 * u, 300 * q * Math.sin(a)], i * 3); col.set([b * (0.8 + 0.2 * w), b * 0.9, b * (1 - 0.25 * w)], i * 3);
    }
    const g1 = new THREE.BufferGeometry(); g1.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g1.setAttribute('color', new THREE.BufferAttribute(col, 3));
    grp.add(new THREE.Points(g1, new THREE.PointsMaterial({ size: 1.5 * H / 1080, vertexColors: true, sizeAttenuation: false, transparent: true, opacity: 0.95 })));
    const m = 26000, mp = new Float32Array(m * 3), mc = new Float32Array(m * 3), r2 = rndS(seed + 5);
    for (let i = 0; i < m; i++) {
      const a = r2() * Math.PI * 2, lat = ((r2() + r2() + r2()) / 3 - 0.5) * 0.5, ca = Math.cos(lat), x = Math.cos(a) * ca, y = Math.sin(lat), z = Math.sin(a) * ca;
      const tl = 0.45, yy = y * Math.cos(tl) - z * Math.sin(tl), zz = y * Math.sin(tl) + z * Math.cos(tl), b = (0.05 + 0.11 * r2()) * (1 - Math.min(1, Math.abs(lat) * 2.2));
      mp.set([300 * x, 300 * yy, 300 * zz], i * 3); mc.set([b, b * 0.92, b * 0.86], i * 3);
    }
    const g2 = new THREE.BufferGeometry(); g2.setAttribute('position', new THREE.BufferAttribute(mp, 3)); g2.setAttribute('color', new THREE.BufferAttribute(mc, 3));
    grp.add(new THREE.Points(g2, new THREE.PointsMaterial({ size: 3 * H / 1080, vertexColors: true, sizeAttenuation: false, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })));
    return grp;
  };
  registry.register({
    type: 'cinema_craft', space: 'screen',
    async create(def, ctx) {
      const scene = new THREE.Scene(); scene.background = new THREE.Color(0x020306);
      scene.add(deepSky(def.seed ?? 7));
      const key = new THREE.DirectionalLight(0xfff3e0, 2.6); key.position.set(-5, 2.5, 4); scene.add(key);
      scene.add(new THREE.AmbientLight(0x8899aa, 0.12));
      if (!def.model) throw new Error('cinema_craft: "model" is required (the compiler names the craft\'s model)');
      const model = await ctx.loadModel(def.model);
      // its own materials: the map's spacecraft layer fades the shared ones out when the craft is far away
      model.traverse((o) => {
        if (!o.material) return;
        o.material = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone();
        for (const m of [].concat(o.material)) { m.transparent = false; m.opacity = 1; m.depthWrite = true; m.needsUpdate = true; }
      });
      const box = new THREE.Box3().setFromObject(model), size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
      model.position.sub(c); const holder = new THREE.Group(); holder.add(model); holder.scale.setScalar(2 / Math.max(size.x, size.y, size.z, 1e-6));
      scene.add(holder);
      // never a craft alone on black: the planet the beat is about under it (its limb, lit by the same Sun, with an atmosphere rim),
      // or, in deep space, the Sun itself as a bright flare in the sky. The camera's orbit round the craft then sweeps the limb
      // and the Sun across the frame.
      const bd = def.backdrop;
      if (bd && bd.colors) {
        const cv = document.createElement('canvas'); cv.width = 512; cv.height = 256; const cg = cv.getContext('2d'), rr = rndS((def.seed ?? 7) + 11);
        const bands = bd.bands ?? 0.6, cols = bd.colors;
        for (let y = 0; y < 256; y++) {
          const k = y / 255, w = Math.sin(k * 23 + rr() * 0.4) * 0.5 + 0.5, ci = Math.min(cols.length - 1, Math.floor(((k * 5 * bands + w * bands) % 1) * cols.length));
          cg.fillStyle = cols[ci]; cg.fillRect(0, y, 512, 1);
        }
        for (let i = 0; i < 900; i++) { cg.fillStyle = `rgba(255,255,255,${0.02 + 0.03 * rr()})`; cg.fillRect(rr() * 512, rr() * 256, 2 + 40 * rr(), 1 + 2 * rr()); }
        const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
        const R = 90, planet = new THREE.Mesh(new THREE.SphereGeometry(R, 96, 64), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95, metalness: 0 }));
        planet.position.set(bd.dx ?? 0, -(R + (bd.drop ?? 2.6)), bd.dz ?? -4); scene.add(planet);
        const rim = new THREE.Mesh(new THREE.SphereGeometry(R * 1.012, 96, 64), new THREE.ShaderMaterial({
          uniforms: { c: { value: new THREE.Color(bd.rim || '#6fb4ff') } },
          vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }',
          fragmentShader: 'uniform vec3 c; varying vec3 vN; varying vec3 vV; void main(){ float r = pow(1.0 - abs(dot(vN, vV)), 3.0); gl_FragColor = vec4(c * r, r * 0.9); }',
          transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.FrontSide }));
        rim.position.copy(planet.position); scene.add(rim);
        key.intensity = 3.2;
      } else {
        const cv = document.createElement('canvas'); cv.width = cv.height = 256; const cg = cv.getContext('2d'), gr = cg.createRadialGradient(128, 128, 0, 128, 128, 128);
        gr.addColorStop(0, 'rgba(255,250,235,1)'); gr.addColorStop(0.08, 'rgba(255,240,205,0.9)'); gr.addColorStop(0.3, 'rgba(255,215,150,0.22)'); gr.addColorStop(1, 'rgba(255,200,120,0)');
        cg.fillStyle = gr; cg.fillRect(0, 0, 256, 256);
        const sun = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(cv), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
        sun.position.copy(key.position).normalize().multiplyScalar(120); sun.scale.setScalar(bd?.sun ?? 46); scene.add(sun);
      }
      return { def, scene, holder, cam: new THREE.PerspectiveCamera(34, W / H, 0.01, 1000) };
    },
    draw(inst, f) {
      const d = inst.def, k = Math.min(1, Math.max(0, (f.t - d.start) / Math.max(0.1, d.end - d.start)));
      // a few seconds on screen: a clear orbit round the craft and a push in, so the shot never reads as still
      const az = ((d.az ?? 28) + (d.turn ?? 40) * k) * Math.PI / 180, el = (d.el ?? 8 + 6 * k) * Math.PI / 180, D = (d.from ?? 4.6) + ((d.to ?? 3.3) - (d.from ?? 4.6)) * k;
      inst.holder.rotation.y = 0.15 * k;
      inst.cam.position.set(Math.sin(az) * Math.cos(el) * D, Math.sin(el) * D, Math.cos(az) * Math.cos(el) * D); inst.cam.lookAt(0, 0, 0);
      // composed as the references: the craft a little low and to one side of the frame, the sky above it
      inst.cam.setViewOffset(W, H, (0.5 - (d.x ?? 0.56)) * W, (0.5 - (d.y ?? 0.56)) * H, W, H);
      renderer.render(inst.scene, inst.cam);
      f.g.save(); f.g.globalAlpha = f.alpha; f.g.drawImage(glCanvas, 0, 0); f.g.restore();
    },
  });
  // a textured world as its own full-frame 3D shot (Cinema variety): the planet, moon or Sun with its real map, lit from one side,
  // an atmosphere rim, Saturn with its rings; the camera slowly orbits and closes in over the deep sky
  registry.register({
    type: 'cinema_globe', space: 'screen',
    async create(def, ctx) {
      if (!def.texture) throw new Error('cinema_globe: "texture" is required');
      const scene = new THREE.Scene(); scene.background = new THREE.Color(0x020306);
      scene.add(deepSky(def.seed ?? 11));
      const key = new THREE.DirectionalLight(0xfff3e0, def.sun ? 0 : 3.1); key.position.set(-5, 2.2, 3.5); scene.add(key);
      scene.add(new THREE.AmbientLight(0x8899aa, def.sun ? 0 : 0.16));
      const map = await tex(def.texture);
      const holder = new THREE.Group(); scene.add(holder);
      const body = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96),
        def.sun ? new THREE.MeshBasicMaterial({ map, color: 0xffe2b0 }) : new THREE.MeshStandardMaterial({ map, roughness: 0.92, metalness: 0 }));
      body.rotation.z = (def.tilt ?? 6) * Math.PI / 180; holder.add(body);
      if (def.rings) {
        const rmap = await tex('2k_saturn_ring_alpha.png'), geo = new THREE.RingGeometry(1.28, 2.35, 192, 1), pos = geo.attributes.position, uv = geo.attributes.uv;
        for (let i = 0; i < pos.count; i++) { const r = Math.hypot(pos.getX(i), pos.getY(i)); uv.setXY(i, (r - 1.28) / (2.35 - 1.28), 0.5); }
        const ring = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: rmap, side: THREE.DoubleSide, transparent: true, depthWrite: false, opacity: 0.95 }));
        ring.rotation.x = Math.PI / 2 - 0.2; ring.rotation.y = 0.1; holder.add(ring);
      }
      const rim = new THREE.Mesh(new THREE.SphereGeometry(1.03, 96, 64), new THREE.ShaderMaterial({
        uniforms: { c: { value: new THREE.Color(def.rim || '#6fb4ff') } },
        vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }',
        fragmentShader: 'uniform vec3 c; varying vec3 vN; varying vec3 vV; void main(){ float r = pow(1.0 - abs(dot(vN, vV)), 3.2); gl_FragColor = vec4(c * r, r * 0.8); }',
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.FrontSide }));
      if (def.rim !== false) holder.add(rim);
      return { def, scene, holder, body, cam: new THREE.PerspectiveCamera(34, W / H, 0.01, 1000) };
    },
    draw(inst, f) {
      const d = inst.def, k = Math.min(1, Math.max(0, (f.t - d.start) / Math.max(0.1, d.end - d.start)));
      const az = ((d.az ?? 24) + (d.turn ?? 28) * k) * Math.PI / 180, el = (d.el ?? 10 + 5 * k) * Math.PI / 180, D = (d.from ?? (d.rings ? 6.6 : 5.6)) + ((d.to ?? (d.rings ? 5.2 : 4.1)) - (d.from ?? (d.rings ? 6.6 : 5.6))) * k;
      inst.body.rotation.y = (d.spin ?? 0.35) * (f.t - d.start);
      inst.cam.position.set(Math.sin(az) * Math.cos(el) * D, Math.sin(el) * D, Math.cos(az) * Math.cos(el) * D); inst.cam.lookAt(0, 0, 0);
      inst.cam.setViewOffset(W, H, (0.5 - (d.x ?? 0.5)) * W, (0.5 - (d.y ?? 0.5)) * H, W, H);
      renderer.render(inst.scene, inst.cam);
      f.g.save(); f.g.globalAlpha = f.alpha; f.g.drawImage(glCanvas, 0, 0); f.g.restore();
    },
  });
  // a 3D scene generated from a sentence (whatif-engine/lib/scene_gen.mjs, the What If engine's `scene` shot): any world, craft, clouds, cutaway or field,
  // full frame over the footage for its window
  const { buildScene } = await import('/wi/lib/scene_gen.mjs');
  registry.register({
    type: 'cinema_scene', space: 'screen',
    create: (def) => ({ def, gen: buildScene(THREE, { scene_spec: def.scene_spec || {} }, { stars: deepSky }), cam: new THREE.PerspectiveCamera(34, W / H, 0.01, 1000) }),
    draw(inst, f) {
      const d = inst.def, k = Math.min(1, Math.max(0, (f.t - d.start) / Math.max(0.1, d.end - d.start)));
      inst.gen.place(inst.cam, k, f.t - d.start);
      renderer.render(inst.gen.scene, inst.cam);
      f.g.save(); f.g.globalAlpha = f.alpha; f.g.drawImage(glCanvas, 0, 0); f.g.restore();
    },
  });
  // the heliosphere as the references draw it: a bubble round the Sun that glows at its rim (a fresnel shell, additive)
  registry.register({
    type: 'cinema_bubble', space: 'world',
    create(def, ctx) {
      const mat = new THREE.ShaderMaterial({
        uniforms: { color: { value: new THREE.Color(def.color || '#3fd6ff') }, opacity: { value: 0 } },
        vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }',
        fragmentShader: 'uniform vec3 color; uniform float opacity; varying vec3 vN; varying vec3 vV; void main(){ float r = pow(1.0 - abs(dot(vN, vV)), 2.6); gl_FragColor = vec4(color * r, r * opacity); }',
        transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), mat);
      mesh.scale.set(1, 0.92, 1.08);       // not a perfect sphere: the Sun's motion through the galaxy squeezes it (illustrative)
      mesh.visible = false; ctx.scene.add(mesh);
      return { def, mesh, mat };
    },
    update(inst, f) {
      const p = f.toCam(inst.def.around || 'sun', [0, 0, 0]), R = (inst.def.radius_au || 122) * 1.495978707e8;
      inst.mesh.position.set(p[0], p[1], p[2]); inst.mesh.scale.set(R, R * 0.92, R * 1.08);
      inst.mat.uniforms.opacity.value = 0.55 * f.alpha; inst.mesh.visible = f.alpha > 0.002;
    },
    draw() {},
  });
  registry.register({
    type: 'cinema_plate', space: 'screen', create: (def) => ({ def }),
    draw(inst, f) {   // a near-black slate plate over the map while a diagram explains (soft centre light, faint grid, vignette)
      const { g, W, H } = f;
      g.save(); g.globalAlpha = f.alpha;
      const grd = g.createRadialGradient(W / 2, H * 0.45, H * 0.05, W / 2, H / 2, H);
      grd.addColorStop(0, '#121821'); grd.addColorStop(1, '#05070B');
      g.fillStyle = grd; g.fillRect(0, 0, W, H);
      g.strokeStyle = 'rgba(142,153,168,0.06)'; g.lineWidth = 1;
      for (let x = 0; x <= W; x += W / 24) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
      for (let y = 0; y <= H; y += W / 24) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
      g.restore();
    },
  });
}
const layerDefs = defaultLayers(spec).map((d) => ((d.over_footage ?? registry.get(d.type)?.over_footage) ? d : fp.adjustLayer(d)));
const layers = await registry.instantiate(layerDefs, layerCtx);
const layerById = new Map(layers.filter((L) => L.def.id).map((L) => [L.def.id, L]));

const sunId = [...world.nodes.values()].find((n) => n.kind === 'star')?.id;
// in front of the camera, from camera space (the projected depth rounds to exactly 1 beyond a few light-years)
const inFront = (p) => { const e = camera.matrixWorldInverse.elements; return e[2] * p[0] + e[6] * p[1] + e[10] * p[2] + e[14] < 0; };
const Y = new THREE.Vector3(0, 1, 0), X = new THREE.Vector3(1, 0, 0);
const screenFrame = (t, date) => ({ t, date, clock: storyClock, mu: fp.mu, spec, W, H, focalPx, THREE, g: ctx, u, claims: [],
  place: (x, y) => y, placeAny: (xs, y) => ({ x: xs[0], y }), claim() {}, locate: () => null, bodies: [], world });

/** The universe and its layers at narration t (map time fp.mu(t)), onto the overlay canvas: everything except the layers
 *  that stay over footage. Returns the frame for those. */
function drawMap(t, date) {
  world.setTime(date);
  const c = camAt(fp.mu(t)), cp = c.position;
  // everything relative to the camera, via the frame tree from the camera's anchor body (never through the root)
  const relBody = (id) => { const v = world.vec(c.anchor, id); return [v[0] - cp[0], v[1] - cp[1], v[2] - cp[2]]; };
  camera.position.set(0, 0, 0);
  const tg = c.target.map((v, i) => v - cp[i]); camera.up.set(...c.up); camera.lookAt(tg[0], tg[1], tg[2]); camera.updateMatrixWorld();
  sky.scale.setScalar(1e20); band.scale.setScalar(1e20);
  const fromSun = sunId ? Math.hypot(...relBody(sunId)) / KM_PER_LY : 0;
  const inside = 1 - ramp(fromSun, 800, 8000);                            // leaving the galaxy: the inside-view sky fades away
  sky.material.uniforms.opacity.value = inside; band.material.uniforms.opacity.value = inside;
  const deep = ramp(fromSun, 2e7, 2e8);
  cosmos.visible = deep > 0.002; cosmos.material.uniforms.opacity.value = deep;
  if (cosmos.visible && sunId) { const sp = relBody(sunId); cosmos.position.set(sp[0], sp[1], sp[2]); }
  const info = [];                                                        // per body, for layers: where, how big, on screen?
  for (const b of bodies) {
    const p = relBody(b.n.id); b.g.position.set(p[0], p[1], p[2]);
    const dist = Math.hypot(p[0], p[1], p[2]);
    const B = world.orientation(b.n.id);
    if (b.n.kind === 'galaxy') {
      b.g.quaternion.copy(basisQuat(B));
      // the face-on view arrives as the inside view leaves, and only once the camera is far enough from the disk that the
      // illustration is not magnified into a blur (a fast flight can pass close to its plane)
      const half = b.n.image_half_width ? b.n.image_half_width.ly * KM_PER_LY : b.n.radiusKm;
      b.mesh.material.opacity = 0.95 * ramp(fromSun, 500, 6000) * ramp(dist / half, 0.55, 1.0);
      {   // a galaxy seen from outside can carry a label (the body_labels layer decides)
        const v = new THREE.Vector3(p[0], p[1], p[2]).project(camera), px = (b.n.radiusKm / Math.max(dist, 1e-9)) * focalPx;
        info.push({ id: b.n.id, n: b.n, p, dist, px, solid: false, ndc: [v.x, v.y], front: inFront(p), sx: (v.x + 1) / 2 * W, sy: (1 - v.y) / 2 * H });
      }
      continue;
    }
    if (b.n.id === sunId) sunLight.position.set(p[0], p[1], p[2]);       // the light comes from THE Sun, not any other star in the world
    if (b.mesh) {
      // the body's real orientation: its axes, then the prime meridian turned by W about its own north
      const q = basisQuat(B);
      b.mesh.quaternion.copy(q).multiply(new THREE.Quaternion().setFromAxisAngle(Y, (B.w * Math.PI) / 180));
      if (b.ring) b.ring.quaternion.copy(q).multiply(new THREE.Quaternion().setFromAxisAngle(X, -Math.PI / 2));
      if (b.clouds) b.clouds.quaternion.copy(b.mesh.quaternion);
      if (b.sunView && sunId) {
        const sp = relBody(sunId);
        b.sunView.value.set(sp[0] - p[0], sp[1] - p[1], sp[2] - p[2]).normalize().transformDirection(camera.matrixWorldInverse);
      }
      const px = (b.n.radiusKm / Math.max(dist, 1e-9)) * focalPx;          // apparent radius in pixels
      b.mesh.visible = px >= 1.5; if (b.ring) b.ring.visible = px >= 1.5;
      b.point.visible = px < 6 && inside > 0.02;
      b.point.scale.setScalar((b.n.kind === 'star' ? 22 : 9) / H);
      const away = b.n.show_from_ly ? ramp(fromSun, b.n.show_from_ly, b.n.show_from_ly * 4) : 1;   // a neighbour star: only from outside the solar system
      b.point.material.opacity = (1 - ramp(px, 3, 6)) * (b.n.kind === 'star' ? 1 : 0.9) * inside * away;
      b.point.visible = b.point.visible && away > 0.01; b.mesh.visible = b.mesh.visible && away > 0.01;
      if (b.clouds) b.clouds.visible = b.mesh.visible;
      if (b.corona) b.corona.visible = away > 0.01 && px > 0.4;
      const v = new THREE.Vector3(p[0], p[1], p[2]).project(camera);
      info.push({ id: b.n.id, n: b.n, p, dist, px, solid: b.mesh.visible, ndc: [v.x, v.y], front: inFront(p), sx: (v.x + 1) / 2 * W, sy: (1 - v.y) / 2 * H, away });
    }
    if (b.orbit) {
      // the orbit drawn as a circle through the body's current position, in the plane given by orbit_normal (Phase 1)
      const op = relBody(b.n.parent); b.orbit.position.set(op[0], op[1], op[2]);
      const r = Math.hypot(...world.vec(b.n.parent, b.n.id));
      b.orbit.scale.setScalar(r);
      b.orbit.quaternion.setFromUnitVectors(Y, new THREE.Vector3(...(b.orbitNormal || b.n.orbit_normal || [0, 1, 0])).normalize());
      const ratio = c.distance / r;
      b.orbit.material.opacity = 0.3 * ramp(ratio, 0.15, 0.6) * (1 - ramp(ratio, 40, 120)) * inside;
      b.orbit.visible = b.orbit.material.opacity > 0.01;
    }
  }
  camera.updateMatrixWorld();
  const view = camera.matrixWorldInverse.elements;
  const frame = {
    t, date, cam: c, world, clock: storyClock, mu: fp.mu, spec, W, H, focalPx, THREE, camera, inside, g: ctx, u, bodies: info,
    /** A point given relative to a body -> km relative to the camera (precise: through the frame tree). */
    toCam(anchor, local) { const v = world.vec(c.anchor, anchor); return [v[0] + local[0] - cp[0], v[1] + local[1] - cp[1], v[2] + local[2] - cp[2]]; },
    /** Camera-relative km -> screen pixels; front = in front of the camera. */
    project(p) {
      const vz = view[2] * p[0] + view[6] * p[1] + view[10] * p[2];
      const q = new THREE.Vector3(p[0], p[1], p[2]).project(camera);
      return { x: (q.x + 1) / 2 * W, y: (1 - q.y) / 2 * H, front: vz < 0 };
    },
    /** Is a camera-relative point hidden behind a solid body (including the far side of the body it sits on)? */
    hidden(p) {
      const L = Math.hypot(p[0], p[1], p[2]); if (L === 0) return false;
      const d = [p[0] / L, p[1] / L, p[2] / L];
      for (const b of info) {
        if (!b.solid) continue;
        const R = b.n.radiusKm, tc = d[0] * b.p[0] + d[1] * b.p[1] + d[2] * b.p[2];
        if (tc <= 0) continue;
        const b2 = b.dist * b.dist - tc * tc;
        if (b2 >= R * R) continue;
        const near = tc - Math.sqrt(R * R - b2);
        if (near < L - Math.max(1e-3, 2e-3 * R)) return true;
      }
      return false;
    },
    /** Screen space for labels: a layer asks for a w x h box at (x, y) and gets the nearest free y (above or below), so
     *  chips from different layers never cover each other. First come, first served (layer order). */
    // corner instruments the templates' text keeps clear of (fractions of the frame: x0, y0, x1, y1): the light clock, top left
    reserved: layers.some((L) => L.def.type === 'tm_clock' && L.def.mode === 'light' && t >= (L.def.start ?? 0) && t <= (L.def.end ?? 1e9)) ? [[0.02, 0.03, 0.225, 0.14]] : [],
    claims: [],
    place(x, y, w, h, pad = 6) { return frame.placeAny([x], y, w, h, pad).y; },
    /** As place, trying each candidate x (e.g. right of a pin, then left of it) before moving further up or down. */
    placeAny(xs, y, w, h, pad = 6) {
      const hit = (xx, yy) => frame.claims.some((o) => xx < o.x + o.w && xx + w > o.x && yy < o.y + o.h && yy + h > o.y);
      let pick = { x: xs[0], y };
      search: for (let k = 0; k < 12; k++) {
        const yy = y + (k % 2 ? -1 : 1) * Math.ceil(k / 2) * (h + pad);
        for (const xx of xs) if (!hit(xx, yy)) { pick = { x: xx, y: yy }; break search; }
      }
      frame.claims.push({ x: pick.x, y: pick.y, w, h });
      return pick;
    },
    claim(x, y, w, h) { frame.claims.push({ x, y, w, h }); },
    /** Unit vector from a body towards the Sun. */
    sunFrom(id) { if (!sunId) return null; const v = world.vec(id, sunId), l = Math.hypot(...v) || 1; return v.map((x) => x / l); },
    /** Camera-relative position of a body ("earth"), surface point ("moon@lon,lat") or a layer with a position (a craft). */
    locate(ref) {
      if (world.get(ref) || String(ref).includes('@') || String(ref).includes('+')) { const a = anchorTarget(world, ref); return frame.toCam(a.anchor, a.local); }
      const L = layerById.get(ref);
      return L && L.impl.locate ? L.impl.locate(L.inst, frame) : null;
    },
  };
  window.__lastInfo = info.map((b) => ({ id: b.id, sx: Math.round(b.sx), sy: Math.round(b.sy), px: +b.px.toFixed(2), front: b.front, ly: +(b.dist / 9.4607e12).toFixed(3) }));
  runLayers(layers, frame, 'pins');     // every pin takes its box first, whatever order the labels are then drawn in
  runLayers(layers, frame, 'update');
  renderer.render(scene, camera);
  ctx.drawImage(glCanvas, 0, 0);
  if (look.glow) {
    // a soft glow round bright things (the Sun, lit limbs, glowing trails): the picture's highlights, blurred, added back
    ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = look.glow;
    ctx.filter = `contrast(2.4) brightness(0.55) blur(${Math.round(14 * H / 1080)}px)`;
    ctx.drawImage(glCanvas, 0, 0); ctx.restore();
  }
  runLayers(layers, frame, 'draw', (L) => !overFootage(L));
  return frame;
}

// ---- footage -----------------------------------------------------------------------------------------------------------------
/** One beat's picture at narration t: a frame the Node renderer cut from the clip, or a still with a slow Ken Burns. */
async function drawFootage(b, t, alpha) {
  ctx.save(); ctx.globalAlpha = alpha;
  if (b.kind === 'video') {
    const res = await fetch(`/footage/${b.i}/${clipFrameIndex(b, t, spec.fps)}.jpg`);
    if (!res.ok) throw new Error(`footage ${b.id}: frame missing at ${t.toFixed(2)} s`);
    const bmp = await createImageBitmap(await res.blob());
    ctx.drawImage(bmp, 0, 0, W, H); bmp.close();
  } else if (spec.cinema?.photos && b.compose === 'card_right') {
    // What If's photo card (V3 1:46): the whole picture framed on the right half over a dark blur of itself, a type block at the left
    const img = await layerCtx.loadImage(b.file), [, , zoom] = kenBurnsAt(b, t);
    const cover = Math.max(W / img.width, H / img.height) * 1.12;
    ctx.save(); ctx.filter = `blur(${Math.round(30 * H / 1080)}px) brightness(0.28) saturate(0.6)`;
    ctx.drawImage(img, (W - img.width * cover) / 2, (H - img.height * cover) / 2, img.width * cover, img.height * cover); ctx.restore();
    const fit = Math.min(W * 0.42 / img.width, H * 0.7 / img.height) * Math.min(1.04, Math.max(1, zoom));
    const dw = img.width * fit, dh = img.height * fit, x = W * 0.73 - dw / 2, y = H * 0.5 - dh / 2;
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 30 * H / 1080; ctx.drawImage(img, x, y, dw, dh); ctx.restore();
    ctx.strokeStyle = 'rgba(255,255,255,0.22)'; ctx.lineWidth = 1.5 * H / 1080; ctx.strokeRect(x, y, dw, dh);
  } else if (spec.cinema?.photos) {
    // a documentary still: the photo whole across the frame (letterboxed), over a blurred, darkened copy of itself
    const img = await layerCtx.loadImage(b.file), [, , zoom] = kenBurnsAt(b, t);
    const cover = Math.max(W / img.width, H / img.height) * 1.08;
    ctx.save(); ctx.filter = `blur(${Math.round(28 * H / 1080)}px) brightness(0.42) saturate(0.8)`;
    ctx.drawImage(img, (W - img.width * cover) / 2, (H - img.height * cover) / 2, img.width * cover, img.height * cover); ctx.restore();
    const fit = Math.min(W / img.width, (H * 0.78) / img.height) * Math.min(1.04, Math.max(1, zoom));
    const dw = img.width * fit, dh = img.height * fit;
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,0.6)'; ctx.shadowBlur = 30 * H / 1080;
    ctx.drawImage(img, (W - dw) / 2, (H - dh) / 2 - H * 0.03, dw, dh); ctx.restore();
  } else {
    const img = await layerCtx.loadImage(b.file), [cx, cy, zoom] = kenBurnsAt(b, t);
    const fit = b.fit === 'contain' ? Math.min(W / img.width, H / img.height) : Math.max(W / img.width, H / img.height);
    const s = fit * Math.max(1, zoom), sw = Math.min(img.width, W / s), sh = Math.min(img.height, H / s);
    const sx = Math.min(img.width - sw, Math.max(0, cx * img.width - sw / 2)), sy = Math.min(img.height - sh, Math.max(0, cy * img.height - sh / 2));
    if (b.fit === 'contain') { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); }
    const dw = sw * s, dh = sh * s;
    ctx.drawImage(img, sx, sy, sw, sh, (W - dw) / 2, (H - dh) / 2, dw, dh);
  }
  if (b.credit) {
    ctx.font = u.font(16, 700); ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
    u.shadow(4, 0.8); ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.fillText(b.credit, 36 * u.S, H - 36 * u.S); u.noShadow();
  }
  ctx.restore();
}

// photo cards that play a video: before each frame, the card gets the clip's frame for this moment (cut by the renderer)
const videoCards = layers.filter((L) => L.def.type === 'photo_card' && L.def.video && L.def.video_frames);
async function feedVideoCards(t) {
  for (const L of videoCards) {
    const s = L.def.start ?? 0, e = L.def.end ?? s;
    if (t < s - 0.05 || t > e + 1) continue;
    const k = Math.max(0, Math.min(L.def.video_frames - 1, Math.round((t - s) * spec.fps)));
    if (L.inst.k === k) continue;
    L.inst.img = await new Promise((ok, fail) => {
      const im = new Image();
      im.onload = () => ok(im);
      im.onerror = () => fail(new Error(`photo card video: frame ${k} of ${L.def.video} is missing`));
      im.src = `/cardframe/${L.def.card_index}/${k}.jpg`;
    });
    L.inst.k = k;
  }
}

// ---- the cinematic finish (spec.look: { glow, vignette, grain }; on by default, 0 turns one off) ----------------------------
const look = { glow: 0.28, vignette: 0.32, grain: 0.05, ...(spec.look || {}) };
const grainTile = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d'), im = g.createImageData(256, 256);
  let s = 7; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let i = 0; i < im.data.length; i += 4) { const v = 128 + (rnd() - 0.5) * 255; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 255; }
  g.putImageData(im, 0, 0); return c;
})();
function finishLook(t) {
  if (spec.cinema?.grade) {
    // the references' grade: a little less saturated, blacks lifted towards slate (drawn over itself through a filter)
    ctx.save(); ctx.filter = `saturate(${spec.cinema_look?.saturate ?? 0.86}) contrast(0.95) brightness(1.03)`; ctx.drawImage(out, 0, 0); ctx.restore();
  }
  if (look.vignette) {
    const grd = ctx.createRadialGradient(W / 2, H / 2, H * 0.45, W / 2, H / 2, H * 1.05);
    grd.addColorStop(0, 'rgba(0,0,0,0)'); grd.addColorStop(1, `rgba(0,0,0,${look.vignette})`);
    ctx.save(); ctx.fillStyle = grd; ctx.fillRect(0, 0, W, H); ctx.restore();
  }
  if (look.grain) {
    // fine film grain, the same for the same frame (a re-render of a chunk is identical)
    const f = Math.round(t * (spec.fps || 30)), ox = (f * 73) % 256, oy = (f * 151) % 256;
    ctx.save(); ctx.globalCompositeOperation = 'overlay'; ctx.globalAlpha = look.grain;
    ctx.fillStyle = ctx.createPattern(grainTile, 'repeat'); ctx.translate(-ox, -oy); ctx.fillRect(ox, oy, W, H); ctx.restore();
  }
}

window.renderFrame = async (t) => {
  const date = storyClock.utc(t);
  await feedVideoCards(t);
  // the map only when some of it shows (under full-screen footage the 3D render is skipped: those frames are cheap)
  const frame = fp.mapAlpha(t) > 0.001 ? drawMap(t, date) : (ctx.fillStyle = '#000', ctx.fillRect(0, 0, W, H), screenFrame(t, date));
  for (const { beat, alpha } of fp.coverage(t)) await drawFootage(beat, t, alpha);
  runLayers(layers, frame, 'draw', overFootage);
  finishLook(t);
  return out.toDataURL('image/jpeg', 0.92).slice('data:image/jpeg;base64,'.length);
};
window.__starmap = { layers, world, camAt, footage: fp, lastInfo: () => window.__lastInfo };     // for inspection tools and tests
window.__ready = true;
