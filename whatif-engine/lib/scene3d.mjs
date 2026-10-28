// The 3D shots (craft, globe): three.js, drawn into a WebGL canvas that page.js copies under the graphics. Loaded only when a
// spec has such a shot. A star field, one key light from the side, a faint fill, slow orbit of the camera.
import { buildHero } from './hero.mjs';
import { buildProduct } from './product.mjs';
import { buildRoom } from './product_room.mjs';
import { buildXray } from './product_xray.mjs';
import { buildBench } from './product_bench.mjs';
import { buildFold } from './product_fold.mjs';
const rnd = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

export async function createScene3d({ W, H, loadModel, loadTexture }) {
  const THREE = await import('/three/three.module.min.js');
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(W, H, false); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  const camera = new THREE.PerspectiveCamera(34, W / H, 0.01, 1000);
  const cache = new Map();
  let anchor = null;

  // the sky behind every craft and globe: dense enough to read through the grade and the vignette (it was 1.5 px stars and a 0.05-0.16
  // band, so craft shots looked like plain black next to the reference's Milky Way photograph)
  const PX = Math.max(1, H / 1080);
  function stars(seed, n = 16000) {
    const r = rnd(seed), pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const u = r() * 2 - 1, a = r() * Math.PI * 2, rad = 300, q = Math.sqrt(1 - u * u);
      pos.set([rad * q * Math.cos(a), rad * u, rad * q * Math.sin(a)], i * 3);
      const b = 0.38 + 0.62 * r() ** 2.4, warm = r();
      col.set([b * (0.8 + 0.2 * warm), b * 0.9, b * (1 - 0.25 * warm)], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    const grp = new THREE.Group();
    grp.add(new THREE.Points(g, new THREE.PointsMaterial({ size: 1.9 * PX, vertexColors: true, sizeAttenuation: false, transparent: true, opacity: 1 })));
    // the Milky Way: a faint dust-and-starlight band along a tilted great circle, as the sky photograph behind the reference's craft shots
    const m = 60000, mp = new Float32Array(m * 3), mc = new Float32Array(m * 3), r2 = rnd(seed + 5);
    for (let i = 0; i < m; i++) {
      const a = r2() * Math.PI * 2, lat = ((r2() + r2() + r2()) / 3 - 0.5) * 0.5, ca = Math.cos(lat), x = Math.cos(a) * ca, y = Math.sin(lat), z = Math.sin(a) * ca;
      const tilt = 0.45, yy = y * Math.cos(tilt) - z * Math.sin(tilt), zz = y * Math.sin(tilt) + z * Math.cos(tilt);
      mp.set([300 * x, 300 * yy, 300 * zz], i * 3);
      const b = (0.14 + 0.26 * r2()) * (1 - Math.min(1, Math.abs(lat) * 2.2));
      mc.set([b * 1.0, b * 0.92, b * 0.86], i * 3);
    }
    const g2 = new THREE.BufferGeometry();
    g2.setAttribute('position', new THREE.BufferAttribute(mp, 3)); g2.setAttribute('color', new THREE.BufferAttribute(mc, 3));
    grp.add(new THREE.Points(g2, new THREE.PointsMaterial({ size: 3.4 * PX, vertexColors: true, sizeAttenuation: false, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })));
    return grp;
  }

  async function build(shot) {
    if (shot.kind === 'hero') return { hero: buildHero(THREE, shot, { stars }) };
    if (shot.kind === 'product') return { product: shot.object === 'lineup' ? await buildRoom(THREE, shot, { renderer, W, H }) : shot.object === 'bench' ? await buildBench(THREE, shot, { renderer, W, H }) : shot.object === 'xray' ? await buildXray(THREE, shot, { renderer, W, H }) : shot.object === 'fold' ? await buildFold(THREE, shot, { renderer, W, H }) : await buildProduct(THREE, shot, { stars, renderer, W, H }) };
    const scene = new THREE.Scene();
    scene.add(stars(7));
    const key = new THREE.DirectionalLight(0xfff3e0, shot.key ?? 3.2); key.position.set(-4, 2.5, 3); scene.add(key);
    scene.add(new THREE.HemisphereLight(0x7f9cc8, 0x10131a, shot.fill ?? 0.45));
    const rim = new THREE.DirectionalLight(0x9fd8ff, 1.1); rim.position.set(3, 1, -4); scene.add(rim);
    let radius = 1, obj;
    if (shot.kind === 'craft') {
      obj = await loadModel(shot.model);
      const box = new THREE.Box3().setFromObject(obj), size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
      const k = 2 / Math.max(size.x, size.y, size.z);
      obj.position.sub(c); const holder = new THREE.Group(); holder.add(obj); holder.scale.setScalar(k); obj = holder;
      radius = 1.6;
    } else {
      const map = await loadTexture(shot.texture);
      obj = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), new THREE.MeshStandardMaterial({ map, roughness: 1, metalness: 0 }));
      if (shot.atmosphere) {
        const halo = new THREE.Mesh(new THREE.SphereGeometry(1.035, 64, 48), new THREE.MeshBasicMaterial({ color: shot.atmosphere, transparent: true, opacity: 0.16, side: THREE.BackSide }));
        obj.add(halo);
      }
      radius = 1;
    }
    scene.add(obj);
    return { scene, obj, radius };
  }

  return {
    async draw(shot, t) {
      let e = cache.get(shot.id);
      if (!e) { e = await build(shot); cache.set(shot.id, e); }
      const k = Math.min(1, Math.max(0, (t - shot.start) / Math.max(0.5, shot.end - shot.start)));
      if (e.product) { e.product.place(camera, k, t - shot.start); e.product.render(renderer, camera, k, t - shot.start); return canvas; }
      if (e.hero) { e.hero.place(camera, k, W, H); renderer.render(e.hero.scene, camera); return canvas; }
      const c = shot.cam || {}, az = ((c.az0 ?? -24) + ((c.az1 ?? 24) - (c.az0 ?? -24)) * k) * Math.PI / 180, el = (c.el ?? 12) * Math.PI / 180;
      const dist = (c.dist ?? (shot.kind === 'globe' ? 3.9 : 3.0)) * (1 - 0.06 * k);
      camera.position.set(Math.sin(az) * Math.cos(el) * dist, Math.sin(el) * dist, Math.cos(az) * Math.cos(el) * dist);
      camera.lookAt((c.ox ?? 0), (c.oy ?? 0), 0); camera.up.set(Math.sin((c.roll ?? 0) * Math.PI / 180), 1, 0);
      if (shot.kind === 'globe') e.obj.rotation.y = ((shot.rotate_deg_s ?? 1.5) * (t - shot.start)) * Math.PI / 180 + (c.spin0 ?? 0);
      if (shot.kind === 'craft' && shot.spin_deg_s) e.obj.rotation.y = (shot.spin_deg_s * (t - shot.start)) * Math.PI / 180;
      // a text block at the left: the whole view slides right so the subject sits beside it (the reference's left-third layout)
      if (shot.frame_x) camera.setViewOffset(W, H, -shot.frame_x * W, 0, W, H); else camera.clearViewOffset();
      renderer.render(e.scene, camera);
      // where the model's centre lands on screen (for the ring marker); off-screen or behind the camera: none
      const v = new THREE.Vector3(0, 0, 0).project(camera);
      anchor = v.z < 1 && Math.abs(v.x) < 0.95 && Math.abs(v.y) < 0.95 ? { x: (v.x + 1) / 2 * W, y: (1 - v.y) / 2 * H } : null;
      return canvas;
    },
    anchor: () => anchor,
  };
}
