// 3D GEOLOGY BLOCK: a cut-away slab of ground with rock layers, a carved surface (valleys, canyons, trenches), water
// and fill (sediment), seen from an orbiting camera. For cross-sections: seafloors, buried canyons, river profiles.
//   const B = await makeBlock(canvas, {
//     layers: [{ top: 0.0, color: '#8a7a5c' }, { top: -0.5, color: '#efe9da' }, { top: -0.9, color: '#5b5552' }],  // tops, high -> low
//     bottom: -1.6, surface: (x, p) => -0.2 * Math.exp(-x * x * 8) * p.carve,  // ground height at x (-2..2); p = your params
//     water: (p) => p.sea,                    // water level (or null), fill: { level: (p) => ..., color } sediment in hollows
//   });
//   B.render({ carve: 1, sea: 0.3 }, { yaw: -30, pitch: 20, dist: 6 });   // each frame; B.screen(x, y, z) -> px
import * as THREE from '/agent_kit/lib/three.module.js';

export async function makeBlock(canvas, { layers, bottom = -1.6, surface = () => 0, water = null, fill = null, width = 4,
  depth = 1.8, samples = 220, background = 0x04141a } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(canvas.width, canvas.height, false); renderer.setClearColor(background);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, canvas.width / canvas.height, 0.05, 100);
  scene.add(new THREE.HemisphereLight(0xdff3f5, 0x1a1410, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(-3, 5, 4); scene.add(sun);
  const group = new THREE.Group(); scene.add(group);
  const mats = layers.map((l) => new THREE.MeshStandardMaterial({ color: l.color, roughness: 0.92, flatShading: false }));
  const waterMat = new THREE.MeshStandardMaterial({ color: 0x1a8fab, transparent: true, opacity: 0.72, roughness: 0.15, metalness: 0.1 });
  const fillMat = new THREE.MeshStandardMaterial({ color: (fill && fill.color) || '#c9a86a', roughness: 0.95 });
  const xs = Array.from({ length: samples + 1 }, (_, i) => -width / 2 + (width * i) / samples);

  function slab(topF, botF, mat) {                     // a 2D band between two height functions, extruded along z
    const shape = new THREE.Shape();
    xs.forEach((x, i) => (i ? shape.lineTo(x, topF(x)) : shape.moveTo(x, topF(x))));
    for (let i = xs.length - 1; i >= 0; i--) shape.lineTo(xs[i], Math.min(botF(xs[i]), topF(xs[i]) - 1e-4));
    const g = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: false, steps: 1 });
    g.translate(0, 0, -depth / 2);
    return new THREE.Mesh(g, mat);
  }
  function build(p) {
    group.children.forEach((m) => m.geometry.dispose()); group.clear();
    const S = (x) => surface(x, p);
    layers.forEach((l, i) => {
      const top = (x) => Math.min(l.top, S(x)), bot = (x) => Math.min(i + 1 < layers.length ? layers[i + 1].top : bottom, S(x));
      group.add(slab(top, bot, mats[i]));
    });
    if (fill) { const lv = fill.level(p); group.add(slab((x) => Math.max(S(x), Math.min(lv, 99)), S, fillMat)); }
    const wl = water ? water(p) : null;
    if (wl !== null && wl !== undefined) {
      const top = (x) => Math.max(S(x), wl), floor = (x) => S(x);    // water only where the ground is below the level
      group.add(slab(top, floor, waterMat));
    }
  }
  let last = '';
  return {
    scene, camera, THREE, group,
    render(p = {}, cam = {}) {
      const key = JSON.stringify(p);
      if (key !== last) { build(p); last = key; }
      const c = { yaw: -28, pitch: 18, dist: 6.2, tx: 0, ty: -0.5, ...cam };
      const yw = c.yaw * Math.PI / 180, pt = c.pitch * Math.PI / 180;
      camera.position.set(c.tx + Math.sin(yw) * Math.cos(pt) * c.dist, c.ty + Math.sin(pt) * c.dist, Math.cos(yw) * Math.cos(pt) * c.dist);
      camera.lookAt(c.tx, c.ty, 0);
      renderer.render(scene, camera);
    },
    /** [x, y] in px of a point on the front face (z = depth/2) or anywhere. */
    screen(x, y, z = depth / 2) { const v = new THREE.Vector3(x, y, z).project(camera); return [(v.x + 1) / 2 * canvas.width, (1 - v.y) / 2 * canvas.height]; },
  };
}
