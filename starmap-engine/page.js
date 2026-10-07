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
import { createClock } from '/lib/clock.mjs';
import { radecToEngine } from '/lib/ephemeris.mjs';
import { KM_PER_LY } from '/lib/units.mjs';

const spec = await (await fetch('/spec.json')).json();
const W = spec.width, H = spec.height, FOV = spec.fov_deg || 40;
// footage beats freeze MAP time (fp.mu): the universe clock, the camera and layer animations run on it
const fp = planFootage(spec);
if (fp.problems.length) throw new Error(`footage: ${fp.problems.join('; ')}`);
const clock = createClock(fp.mapClock(spec.clock));
const world = buildWorld(spec.world, { date: clock.utc(fp.mu(0)) });
const camAt = createCamera(world, { fov_deg: FOV, ...fp.mapCamera(spec.camera) });
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
    b.mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 64), mat); b.mesh.scale.setScalar(n.radiusKm); g.add(b.mesh);
    if (n.rings) {     // a ring in the body's equatorial plane, its texture running from the inner to the outer edge
      const inner = n.radiusKm * n.rings.inner, outer = n.radiusKm * n.rings.outer;
      const geo = new THREE.RingGeometry(inner, outer, 256, 1);
      const p = geo.attributes.position, uv = geo.attributes.uv;
      for (let i = 0; i < p.count; i++) uv.setXY(i, (Math.hypot(p.getX(i), p.getY(i)) - inner) / (outer - inner), 0.5);
      b.ring = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: await tex(n.rings.texture), transparent: true, side: THREE.DoubleSide, roughness: 1, depthWrite: false }));
      g.add(b.ring);
    }
    b.point = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(n.glow || n.color || '#cfd8ff'), sizeAttenuation: false, depthWrite: false, transparent: true, blending: THREE.AdditiveBlending }));
    g.add(b.point);
  }
  if (n.kind === 'galaxy') {
    // the face-on disk: a NASA/JPL-Caltech illustration in the galactic plane, its Sun side (image bottom) towards the real Sun
    const half = n.image_half_width ? n.image_half_width.ly * KM_PER_LY : n.radiusKm;
    const disk = new THREE.Mesh(new THREE.PlaneGeometry(2 * half, 2 * half), new THREE.MeshBasicMaterial({ map: await tex(n.texture), transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    disk.rotation.x = -Math.PI / 2;                                 // image bottom -> +z (the Sun's side)
    if (n.image_turn_deg) disk.rotation.z = (n.image_turn_deg * Math.PI) / 180;
    b.mesh = disk; g.add(disk);
  }
  if (n.parent && n.show_orbit) {
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
    const { GLTFLoader } = await import('/three/addons/loaders/GLTFLoader.js');
    const gltf = await new GLTFLoader().loadAsync(`/media/${encodeURIComponent(name)}`);
    return gltf.scene;
  },
};
const registry = registerBuiltins(createRegistry());
const layerDefs = defaultLayers(spec).map((d) => ((d.over_footage ?? registry.get(d.type)?.over_footage) ? d : fp.adjustLayer(d)));
const layers = await registry.instantiate(layerDefs, layerCtx);
const layerById = new Map(layers.filter((L) => L.def.id).map((L) => [L.def.id, L]));

const sunId = [...world.nodes.values()].find((n) => n.kind === 'star')?.id;
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
  const info = [];                                                        // per body, for layers: where, how big, on screen?
  for (const b of bodies) {
    const p = relBody(b.n.id); b.g.position.set(p[0], p[1], p[2]);
    const dist = Math.hypot(p[0], p[1], p[2]);
    const B = world.orientation(b.n.id);
    if (b.n.kind === 'galaxy') {
      b.g.quaternion.copy(basisQuat(B));
      b.mesh.material.opacity = 0.95 * ramp(fromSun, 500, 6000);           // the face-on view arrives as the inside view leaves
      continue;
    }
    if (b.n.kind === 'star') sunLight.position.set(p[0], p[1], p[2]);
    if (b.mesh) {
      // the body's real orientation: its axes, then the prime meridian turned by W about its own north
      const q = basisQuat(B);
      b.mesh.quaternion.copy(q).multiply(new THREE.Quaternion().setFromAxisAngle(Y, (B.w * Math.PI) / 180));
      if (b.ring) b.ring.quaternion.copy(q).multiply(new THREE.Quaternion().setFromAxisAngle(X, -Math.PI / 2));
      const px = (b.n.radiusKm / Math.max(dist, 1e-9)) * focalPx;          // apparent radius in pixels
      b.mesh.visible = px >= 1.5; if (b.ring) b.ring.visible = px >= 1.5;
      b.point.visible = px < 6 && inside > 0.02;
      b.point.scale.setScalar((b.n.kind === 'star' ? 22 : 9) / H);
      b.point.material.opacity = (1 - ramp(px, 3, 6)) * (b.n.kind === 'star' ? 1 : 0.9) * inside;
      const v = new THREE.Vector3(p[0], p[1], p[2]).project(camera);
      info.push({ id: b.n.id, n: b.n, p, dist, px, solid: b.mesh.visible, ndc: [v.x, v.y], front: v.z < 1, sx: (v.x + 1) / 2 * W, sy: (1 - v.y) / 2 * H });
    }
    if (b.orbit) {
      // the orbit drawn as a circle through the body's current position, in the plane given by orbit_normal (Phase 1)
      const op = relBody(b.n.parent); b.orbit.position.set(op[0], op[1], op[2]);
      const r = Math.hypot(...world.vec(b.n.parent, b.n.id));
      b.orbit.scale.setScalar(r);
      b.orbit.quaternion.setFromUnitVectors(Y, new THREE.Vector3(...(b.n.orbit_normal || [0, 1, 0])).normalize());
      const ratio = c.distance / r;
      b.orbit.material.opacity = 0.35 * ramp(ratio, 0.15, 0.6) * (1 - ramp(ratio, 40, 120)) * inside;
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
  runLayers(layers, frame, 'update');
  renderer.render(scene, camera);
  ctx.drawImage(glCanvas, 0, 0);
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

window.renderFrame = async (t) => {
  const date = storyClock.utc(t);
  // the map only when some of it shows (under full-screen footage the 3D render is skipped: those frames are cheap)
  const frame = fp.mapAlpha(t) > 0.001 ? drawMap(t, date) : (ctx.fillStyle = '#000', ctx.fillRect(0, 0, W, H), screenFrame(t, date));
  for (const { beat, alpha } of fp.coverage(t)) await drawFootage(beat, t, alpha);
  runLayers(layers, frame, 'draw', overFootage);
  return out.toDataURL('image/jpeg', 0.92).slice('data:image/jpeg;base64,'.length);
};
window.__starmap = { layers, world, camAt, footage: fp };     // for inspection tools and tests
window.__ready = true;
