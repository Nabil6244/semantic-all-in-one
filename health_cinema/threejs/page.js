// Three.js journey renderer: loads chest.glb (Layer_* empties keep Z-Anatomy object names), applies frames.json per frame.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
const q = new URLSearchParams(location.search); const W = +q.get('w'), H = +q.get('h');
try {
  const data = await (await fetch('/frames.json')).json(); const spec = data.spec;
  const canvas = document.getElementById('c'); canvas.width = W; canvas.height = H;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(W, H, false); renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = spec.exposure ?? 1.0;
  window.__gl = renderer.getContext().getParameter(renderer.getContext().VERSION) + ' | ' + (renderer.getContext().getExtension('WEBGL_debug_renderer_info') ? renderer.getContext().getParameter(renderer.getContext().getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL) : '?');
  const scene = new THREE.Scene(); scene.background = new THREE.Color().setRGB(...spec.background, THREE.LinearSRGBColorSpace);
  const gltf = spec.no_model ? null : await new GLTFLoader().loadAsync('/chest.glb'); if (gltf) scene.add(gltf.scene);      // procedural scenes (micro:*) have no model
  const proc = spec.procedural ? (await import('/procedural.js')).build(THREE, scene, spec) : null;
  const layers = {}; if (gltf) gltf.scene.traverse((o) => { if (o.name.startsWith('Layer_')) layers[o.name] = o; });
  // Translucent layers: inner layers draw first, and every translucent mesh gets a colour-less depth pre-pass, so each layer shows only its
  // nearest surface (no milky stacking of a layer's own far side or lobes) while layers in front still blend over the ones behind.
  // Layer order is the compositing order (innermost first). A layer that fades out over another (Heart over its cut-away) must come LATER in the order,
  // otherwise its depth pre-pass would hide the layer behind it until it disappears.
  // A layer below prepass_min_alpha draws without its depth pre-pass: a faint layer must not hide the geometry behind it (that popped the back ribs
  // out the moment the lungs became visible); prepass_always lists outer layers (nothing is drawn behind them, so they can never hide anything);
  // above the threshold the pre-pass keeps the layer clean (single nearest surface).
  const named = (spec.layer_order || []).filter((n) => layers[n]); const order = [...named, ...Object.keys(layers).filter((n) => !named.includes(n))];   // layers the template does not mention stay hidden (alpha 0)
  const layerMats = {}, layerPre = {}, rimU = {};   // rimU[layer] = {color, strength, power} uniforms shared by the layer's materials
  const rimPatch = (m, u) => {   // fresnel rim added to the emissive term: the glow hugs the organ's own silhouette
    m.onBeforeCompile = (sh) => {
      sh.uniforms.rimColor = u.color; sh.uniforms.rimStrength = u.strength; sh.uniforms.rimPower = u.power;
      sh.fragmentShader = 'uniform vec3 rimColor; uniform float rimStrength; uniform float rimPower;\n' + sh.fragmentShader.replace('#include <emissivemap_fragment>',
        '#include <emissivemap_fragment>\n float rimF = pow(1.0 - clamp(abs(dot(normalize(normal), normalize(vViewPosition))), 0.0, 1.0), rimPower);\n totalEmissiveRadiance += rimColor * rimF * rimStrength;');
    };
    m.customProgramCacheKey = () => 'hc-rim';
  };
  const preMat = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, transparent: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  order.forEach((ln, idx) => {
    layerMats[ln] = new Set(); layerPre[ln] = []; const pres = [];
    layers[ln].traverse((o) => { if (o.isMesh) {
      o.material = o.material.clone(); o.material.transparent = true; o.material.depthWrite = false; o.material.side = (spec.double_sided || []).includes(ln) ? THREE.DoubleSide : THREE.FrontSide; o.renderOrder = 10 + idx * 3 + 1;
      o.material.envMapIntensity = 0; o.material.roughness = Math.max(o.material.roughness, 0.62); layerMats[ln].add(o.material); pres.push(o); rimPatch(o.material, rimU[ln] ??= { color: { value: new THREE.Color(1, 1, 1) }, strength: { value: 0 }, power: { value: 2.5 } }); } });
    for (const o of pres) { const pre = new THREE.Mesh(o.geometry, preMat); pre.position.copy(o.position); pre.quaternion.copy(o.quaternion); pre.scale.copy(o.scale);
      pre.renderOrder = 10 + idx * 3; pre.matrixAutoUpdate = true; o.parent.add(pre); layerPre[ln].push(pre); }
  });
  const tb = (p) => new THREE.Vector3(p[0], p[2], -p[1]);   // Blender (Z up, front -Y) -> three (Y up)
  const hl = {};
  for (const h of spec.highlights || []) {
    const c = data.anchors[h.anchor].center; const m = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), new THREE.MeshBasicMaterial({ color: new THREE.Color(...h.color), transparent: true, opacity: 0, depthWrite: false, blending: THREE.NormalBlending }));
    m.position.copy(tb([c[0] + h.offset[0], c[1] + h.offset[1], c[2] + h.offset[2]])); m.scale.set(h.scale[0], h.scale[2], h.scale[1]); m.renderOrder = 99; scene.add(m); hl[h.id] = m;
  }
  const cam = new THREE.PerspectiveCamera(30, W / H, 0.02, 30);
  // Glow: emissive layers + a restrained bloom (high threshold, so only emissive parts bloom).
  const composer = new EffectComposer(renderer); composer.setSize(W, H); composer.addPass(new RenderPass(scene, cam));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), spec.bloom?.strength ?? 0.55, spec.bloom?.radius ?? 0.6, spec.bloom?.threshold ?? 0.82)); composer.addPass(new OutputPass());
  const glowCfg = Object.fromEntries((spec.glow || []).map((g) => [g.id, g]));
  const sun = [['key', 3.0, [0.9, 0.7, 0.9]], ['fill', 0.9, [-1, 0.2, 0.7]], ['rim', 2.2, [0, 0.5, -1]]].map(([n, e, d]) => { const l = new THREE.DirectionalLight(0xffffff, e); scene.add(l); scene.add(l.target); return { l, d: new THREE.Vector3(...d).normalize() }; });
  scene.add(new THREE.HemisphereLight(0x8899bb, 0x221111, 0.45));
  window.renderFrame = (i) => {
    const f = data.frames[i]; cam.fov = f.fov; cam.updateProjectionMatrix(); cam.position.copy(tb(f.cam)); cam.lookAt(tb(f.look)); cam.updateMatrixWorld();
    const qn = cam.quaternion; sun.forEach(({ l, d }) => { l.position.copy(cam.position).add(d.clone().applyQuaternion(qn).multiplyScalar(3)); l.target.position.copy(tb(f.look)); });
    for (const [ln, node] of Object.entries(layers)) { const a = f.alpha[ln] ?? 0; node.visible = a >= 0.01; layerPre[ln].forEach((pm) => { pm.visible = a < 0.99 && (a >= (spec.prepass_min_alpha ?? 0.5) || (spec.prepass_always || []).includes(ln)); }); layerMats[ln].forEach((m) => { m.opacity = a; const solid = a >= 0.99; if (m.transparent === solid) { m.transparent = !solid; m.depthWrite = solid; m.needsUpdate = true; } }); }
    for (const [id, m] of Object.entries(hl)) { const s = f.highlight[id] ?? 0; m.visible = s >= 0.01; m.material.opacity = (spec.highlight_opacity ?? 0.3) * s; }
    for (const g of Object.values(glowCfg)) { const u = rimU[g.layer]; if (!u) continue; const v = f.glow?.[g.id] ?? 0; u.color.value.setRGB(...g.color); u.strength.value = v * (g.rim ?? 2.0); u.power.value = g.power ?? 2.5;
      layerMats[g.layer]?.forEach((m) => { if (m.emissive) { m.emissive.setRGB(...g.color); m.emissiveIntensity = v * (g.fill ?? 0.0); } }); }
    // pathology tint: [layer or 'Layer:Object'] -> colour, per frame (an object whose name starts with the part after the colon)
    for (const [key, rgb] of Object.entries(f.tint || {})) { const [ln, on] = key.split(':'); layers[ln]?.traverse((o) => { if (o.isMesh && (!on || o.name.startsWith(on))) o.material.color.setRGB(...rgb); }); }
    proc?.update(f);
    composer.render(); return canvas.toDataURL('image/png');
  };
  window.__ready = true;
} catch (e) { window.__error = String(e && e.stack || e); }
