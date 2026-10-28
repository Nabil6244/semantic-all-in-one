// A real phone model (GLB) in place of the code-built one. Files live in whatif-engine/assets/models/phones/<preset id>.glb
// (ids from data/phones.json, e.g. galaxy_s25_ultra.glb); no file -> null and product.mjs builds the phone in code.
// A downloaded model can lie any way round, so it is turned to the code-built phone's frame: 2 units tall along +y, screen to +z,
// camera bump to -z, camera at the top, centred. Guessed from the shape (longest side = height, thinnest = depth, the side the bump
// sticks out of = back). A sidecar <id>.json corrects a wrong guess:
//   { "rotate": [x, y, z] (degrees, replaces the guess), "flip_front": true, "flip_up": true, "screen_mesh": "Screen", "env": 0.8 }
// screen_mesh (or a mesh named Screen / Display) gets the trailer's lock-screen picture, when the shot has one.
const cache = new Map();

async function exists(url) {
  try { return (await fetch(url, { method: 'HEAD' })).ok; } catch { return false; }
}

async function loadGltf(url) {
  if (!cache.has(url)) {
    cache.set(url, (async () => {
      const { GLTFLoader } = await import('/three/addons/loaders/GLTFLoader.js');
      const { DRACOLoader } = await import('/three/addons/loaders/DRACOLoader.js');
      const draco = new DRACOLoader().setDecoderPath('/three/addons/libs/draco/gltf/');
      return (await new GLTFLoader().setDRACOLoader(draco).loadAsync(url)).scene;
    })());
  }
  return (await cache.get(url)).clone(true);
}

// up to ~20k world-space vertex positions, for the shape guesses
function samplePoints(THREE, root) {
  const pts = [], v = new THREE.Vector3();
  root.updateMatrixWorld(true);
  root.traverse((o) => {
    const pos = o.isMesh && o.geometry?.attributes?.position;
    if (!pos) return;
    const step = Math.max(1, Math.floor(pos.count / 4000));
    for (let i = 0; i < pos.count; i += step) pts.push(v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld).clone());
  });
  return pts;
}
const median = (a) => { const s = [...a].sort((x, y) => x - y); return s[s.length >> 1] ?? 0; };

export async function loadPhoneGlb(THREE, id, { envMap = null, screenMap = null, file = null } = {}) {
  const name = file || (id ? `${id}.glb` : null);
  if (!name) return null;
  const url = `/models/phones/${name}`;
  if (!(await exists(url))) return null;
  let cfg = {};
  try { const r = await fetch(url.replace(/\.gl(b|tf)$/i, '.json')); if (r.ok) cfg = await r.json(); } catch { cfg = {}; }

  const model = await loadGltf(url);
  const turn = new THREE.Group(); turn.add(model);
  if (Array.isArray(cfg.rotate)) {
    turn.rotation.set(...cfg.rotate.map((d) => (d * Math.PI) / 180));
  } else {   // longest side -> y (height), thinnest -> z (depth), the middle one -> x
    const size = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3()).toArray();
    const [T, M, L] = [0, 1, 2].sort((a, b) => size[a] - size[b]);
    const e = (i) => new THREE.Vector3(...[0, 1, 2].map((k) => (k === i ? 1 : 0)));
    const rx = e(M), ry = e(L), rz = e(T);
    if (rx.clone().cross(ry).dot(rz) < 0) rx.negate();   // keep it a rotation, never a mirror
    turn.setRotationFromMatrix(new THREE.Matrix4().makeBasis(rx, ry, rz).transpose());
    // the back is the side the camera bump sticks out of: the outermost points there cover a small patch, while the screen side's
    // cover the whole face. The back must face -z, with the bump at the top.
    const outer = (pts, sign) => {
      const zs = pts.map((p) => p.z * sign), top = Math.max(...zs), span = top - Math.min(...zs);
      return pts.filter((p) => p.z * sign > top - span * 0.12);
    };
    const area = (ps) => { const xs = ps.map((p) => p.x), ys = ps.map((p) => p.y); return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys)); };
    const pts = samplePoints(THREE, turn);
    if (area(outer(pts, 1)) < area(outer(pts, -1))) turn.rotateY(Math.PI);   // the bump faces +z: turn it round
    const back = samplePoints(THREE, turn), bump = outer(back, -1);
    const ys = back.map((p) => p.y), cy = (Math.max(...ys) + Math.min(...ys)) / 2;
    if (bump.length && bump.reduce((s, p) => s + p.y, 0) / bump.length < cy) turn.rotateZ(Math.PI);
  }
  if (cfg.flip_front) turn.rotateY(Math.PI);
  if (cfg.flip_up) turn.rotateZ(Math.PI);

  // centre on the slab (not the bump) and scale to 2 units tall, like the code-built phone
  const grp = new THREE.Group(); grp.add(turn);
  const box = new THREE.Box3().setFromObject(turn), size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  c.z = median(samplePoints(THREE, turn).map((p) => p.z));
  turn.position.sub(c);
  const s = 2 / Math.max(1e-6, size.y);
  grp.scale.setScalar(s);

  const screenRe = cfg.screen_mesh ? null : /^(screen|display)$/i;
  model.traverse((o) => {
    if (!o.isMesh) return;
    const isScreen = cfg.screen_mesh ? o.name === cfg.screen_mesh || o.material?.name === cfg.screen_mesh : screenRe.test(o.name) || screenRe.test(o.material?.name || '');
    if (isScreen && screenMap) { o.material = new THREE.MeshBasicMaterial({ map: screenMap, toneMapped: false }); return; }
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (!m || !('envMap' in m)) continue;
      m.envMap = envMap; m.envMapIntensity = cfg.env ?? 0.8; m.needsUpdate = true;
    }
  });
  grp.userData = { W: size.x * s, H: 2, D: size.z * s, glb: name };
  return grp;
}
