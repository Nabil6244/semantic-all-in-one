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
  const proc = spec.procedural ? (await import(spec.procedural.kind === 'bodymap' ? '/bodymap.js' : spec.procedural.kit === 'conditions' ? '/conditions.js' : '/procedural.js')).build(THREE, scene, spec) : null;
  const layers = {}; if (gltf) gltf.scene.traverse((o) => { if (o.name.startsWith('Layer_')) layers[o.name] = o; });
  // Translucent layers: inner layers draw first, and every translucent mesh gets a colour-less depth pre-pass, so each layer shows only its
  // nearest surface (no milky stacking of a layer's own far side or lobes) while layers in front still blend over the ones behind.
  // Layer order is the compositing order (innermost first). A layer that fades out over another (Heart over its cut-away) must come LATER in the order,
  // otherwise its depth pre-pass would hide the layer behind it until it disappears.
  // A layer below prepass_min_alpha draws without its depth pre-pass: a faint layer must not hide the geometry behind it (that popped the back ribs
  // out the moment the lungs became visible); prepass_always lists outer layers (nothing is drawn behind them, so they can never hide anything);
  // above the threshold the pre-pass keeps the layer clean (single nearest surface).
  const named = (spec.layer_order || []).filter((n) => layers[n]); const order = [...named, ...Object.keys(layers).filter((n) => !named.includes(n))];   // layers the template does not mention stay hidden (alpha 0)
  const preOf = new Map();      // mesh -> its depth pre-pass twin (a per-object pulse moves both)
  const layerMats = {}, layerPre = {}, rimU = {}, flowU = {};   // rimU[layer] = {color, strength, power}; flowU[layer] = blood-flow wave uniforms; both shared by the layer's materials
  const hcTime = { value: 0 };
  const newFlow = () => ({ origin: { value: new THREE.Vector3() }, color: { value: new THREE.Color(1, 0.2, 0.15) }, strength: { value: 0 }, rate: { value: 60 }, speed: { value: 0.3 }, sharp: { value: 6 }, reach: { value: 1e3 }, inner: { value: 0 } });
  // fresnel rim added to the emissive term (the glow hugs the organ's own silhouette), and a blood-flow wave: a band that leaves `origin` once per beat and travels
  // outward at `speed` (m/s) along whatever surface the layer has, fading past `reach` metres.
  const rimPatch = (m, u, fu) => {
    m.onBeforeCompile = (sh) => {
      sh.uniforms.rimColor = u.color; sh.uniforms.rimStrength = u.strength; sh.uniforms.rimPower = u.power; sh.uniforms.hcTime = hcTime;
      for (const [k, v] of Object.entries(fu)) sh.uniforms['flow' + k[0].toUpperCase() + k.slice(1)] = v;
      sh.vertexShader = 'varying vec3 vHcWorld;\n' + sh.vertexShader.replace('#include <project_vertex>', '#include <project_vertex>\n vHcWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      sh.fragmentShader = 'uniform vec3 rimColor; uniform float rimStrength; uniform float rimPower; uniform float hcTime; varying vec3 vHcWorld;\n' +
        'uniform vec3 flowOrigin; uniform vec3 flowColor; uniform float flowStrength; uniform float flowRate; uniform float flowSpeed; uniform float flowSharp; uniform float flowReach; uniform float flowInner;\n' + sh.fragmentShader.replace('#include <emissivemap_fragment>',
        '#include <emissivemap_fragment>\n float rimF = pow(1.0 - clamp(abs(dot(normalize(normal), normalize(vViewPosition))), 0.0, 1.0), rimPower);\n totalEmissiveRadiance += rimColor * rimF * rimStrength;\n' +
        ' if (flowStrength > 0.0) { float hcD = distance(vHcWorld, flowOrigin); float hcW = flowSpeed * 60.0 / max(1.0, flowRate);\n' +
        '   float hcB = pow(0.5 + 0.5 * cos(6.2831853 * (hcTime * flowRate / 60.0 - hcD / hcW)), flowSharp) * exp(-hcD / flowReach) * smoothstep(flowInner, flowInner * 2.0 + 1e-4, hcD);\n' +
        '   totalEmissiveRadiance += flowColor * hcB * flowStrength; }');
    };
    m.customProgramCacheKey = () => 'hc-rim-flow';
  };
  // spec.lighting === 'tissue' (Health Cinema's own scenes; other users of this page, such as Rep Theory, keep the classic look): soft image-based light from a
  // procedural studio room, wet soft tissue (a thin clearcoat and a soft sheen over the organ's colour) and matte bone, a warm key and a cool back rim.
  const tissue = spec.lighting === 'tissue';
  const MATTE = /Skelet|Skull|Bone|Disc|Menisc|Ligament|Cartilage/i;
  const tissueMaterial = (m, ln) => {
    if (!m.isMeshStandardMaterial) return m;
    const p = new THREE.MeshPhysicalMaterial(); THREE.MeshStandardMaterial.prototype.copy.call(p, m); p.defines = { STANDARD: '', PHYSICAL: '' };
    p.metalness = 0;
    if (MATTE.test(ln)) { p.roughness = Math.max(m.roughness, 0.72); }
    else { p.roughness = Math.max(m.roughness, 0.5); p.clearcoat = spec.wet ?? 0.22; p.clearcoatRoughness = 0.42; p.sheen = spec.sheen ?? 0.2; p.sheenRoughness = 0.55; p.sheenColor = m.color.clone().lerp(new THREE.Color(1, 0.92, 0.88), 0.5); }
    return p;
  };
  if (tissue) renderer.toneMappingExposure = (spec.exposure ?? 1.0) * (spec.tissue_exposure ?? 0.92);      // the room light adds to the lamps: bring the whole picture down so highlights do not clip into bloom
  if (tissue && spec.env !== false) { const { RoomEnvironment } = await import('three/addons/environments/RoomEnvironment.js'); const pm = new THREE.PMREMGenerator(renderer); scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; scene.environmentIntensity = spec.env_intensity ?? 0.25; pm.dispose(); }      // scene-wide: a material's envMapIntensity does not scale scene.environment
  const preMat = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, transparent: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  order.forEach((ln, idx) => {
    layerMats[ln] = new Set(); layerPre[ln] = []; const pres = [];
    layers[ln].traverse((o) => { if (o.isMesh) {
      o.material = o.material.clone(); o.material.transparent = true; o.material.depthWrite = false; o.material.side = (spec.double_sided || []).includes(ln) ? THREE.DoubleSide : THREE.FrontSide; o.renderOrder = 10 + idx * 3 + 1;
      if (tissue) o.material = tissueMaterial(o.material, ln); else { o.material.envMapIntensity = 0; o.material.roughness = Math.max(o.material.roughness, 0.62); } layerMats[ln].add(o.material); pres.push(o); rimPatch(o.material, rimU[ln] ??= { color: { value: new THREE.Color(1, 1, 1) }, strength: { value: 0 }, power: { value: 2.5 } }, flowU[ln] ??= newFlow()); } });
    for (const o of pres) { const pre = new THREE.Mesh(o.geometry, preMat); preOf.set(o, pre); pre.position.copy(o.position); pre.quaternion.copy(o.quaternion); pre.scale.copy(o.scale);
      pre.renderOrder = 10 + idx * 3; pre.matrixAutoUpdate = true; o.parent.add(pre); layerPre[ln].push(pre); }
  });
  const tb = (p) => new THREE.Vector3(p[0], p[2], -p[1]);   // Blender (Z up, front -Y) -> three (Y up)
  // heartbeat / breathing: a layer is scaled about its pulse anchor (journey.pulse_scales gives the factor per frame); blood flow: per-layer wave settings
  if (gltf) gltf.scene.updateMatrixWorld(true);
  const pulseCfg = {};
  for (const p of spec.pulse || []) { const c = tb(data.anchors[p.anchor].center);
    for (const ln of p.layers) { const n = layers[ln]; if (!n || pulseCfg[ln]) continue;
      if (p.per_object) { const parts = []; n.traverse((o) => { if (!o.isMesh || !preOf.has(o)) return; o.geometry.computeBoundingBox(); const cc = o.geometry.boundingBox.getCenter(new THREE.Vector3()).applyMatrix4(o.matrix);
          parts.push({ n: o, pre: preOf.get(o), p0: o.position.clone(), s0: o.scale.clone(), c: cc }); }); pulseCfg[ln] = { parts }; }
      else pulseCfg[ln] = { parts: [{ n, p0: n.position.clone(), s0: n.scale.clone(), c: n.parent.worldToLocal(c.clone()) }] }; } }
  const origins = (o) => [].concat(o).filter((r) => data.anchors[r]);      // a flow can leave from one anchor or from the middle of several (both carotids)
  const flowCfg = (spec.flow || []).filter((fl) => flowU[fl.layer] && origins(fl.origin).length);
  for (const fl of flowCfg) { const u = flowU[fl.layer]; const os = origins(fl.origin); u.origin.value.set(0, 0, 0); os.forEach((r) => u.origin.value.add(tb(data.anchors[r].center))); u.origin.value.multiplyScalar(1 / os.length); u.color.value.setRGB(...(fl.color || [1, 0.2, 0.15]));
    u.rate.value = fl.rate ?? 60; u.speed.value = fl.speed ?? 0.3; u.sharp.value = fl.sharp ?? 6; u.reach.value = fl.reach ?? 1e3; u.inner.value = fl.inner ?? 0; }      // inner: the wave starts this far out, so it does not light a whole organ around its origin at once
  const hl = {};
  for (const h of spec.highlights || []) {
    const c = data.anchors[h.anchor].center; const m = new THREE.Mesh(new THREE.SphereGeometry(1, 48, 24), new THREE.MeshBasicMaterial({ color: new THREE.Color(...h.color), transparent: true, opacity: 0, depthWrite: false, blending: spec.highlight_additive ? THREE.AdditiveBlending : THREE.NormalBlending }));
    m.position.copy(tb([c[0] + h.offset[0], c[1] + h.offset[1], c[2] + h.offset[2]])); m.scale.set(h.scale[0], h.scale[2], h.scale[1]); m.renderOrder = 99; scene.add(m); hl[h.id] = m;
  }
  const cam = new THREE.PerspectiveCamera(30, W / H, 0.02, 60);
  const d0 = (() => { const a = data.frames[0]; return Math.hypot(a.cam[0] - a.look[0], a.cam[1] - a.look[1], a.cam[2] - a.look[2]) || 1; })();
  const atmo = spec.atmosphere === false ? null : (await import('/atmosphere.js')).build(THREE, scene, spec, d0);      // graded backdrop + depth fog + floating motes (atmosphere.js)
  // Glow: emissive layers + a restrained bloom (high threshold, so only emissive parts bloom).
  const composer = new EffectComposer(renderer); composer.setSize(W, H); composer.addPass(new RenderPass(scene, cam));
  composer.addPass(new UnrealBloomPass(new THREE.Vector2(W, H), spec.bloom?.strength ?? 0.55, spec.bloom?.radius ?? 0.6, spec.bloom?.threshold ?? 0.82)); composer.addPass(new OutputPass());
  const glowCfg = Object.fromEntries((spec.glow || []).map((g) => [g.id, g]));
  const rig = tissue ? [['key', 2.1, [0.85, 0.75, 0.9], 0xfff0dc], ['fill', 0.45, [-1, 0.0, 0.6], 0xc8d8ff], ['rim', 2.4, [-0.3, 0.6, -1], 0xa8d0ff], ['kick', 0.9, [1, -0.2, -0.7], 0xffd6c8]]
                    : [['key', 3.0, [0.9, 0.7, 0.9], 0xffffff], ['fill', 0.9, [-1, 0.2, 0.7], 0xffffff], ['rim', 2.2, [0, 0.5, -1], 0xffffff]];
  const kr = (spec.key_rot ?? 0) * Math.PI / 180;      // the variety director turns the whole rig about the view axis: the key comes from another side in another mood
  const sun = rig.map(([n, e, d, c]) => { const l = new THREE.DirectionalLight(c, e); scene.add(l); scene.add(l.target); return { l, d: new THREE.Vector3(d[0] * Math.cos(kr) - d[1] * Math.sin(kr), d[0] * Math.sin(kr) + d[1] * Math.cos(kr), d[2]).normalize() }; });
  scene.add(tissue ? new THREE.HemisphereLight(0x8899bb, 0x221111, 0.2) : new THREE.HemisphereLight(0x8899bb, 0x221111, 0.45));
  window.renderFrame = (i) => {
    const f = data.frames[i]; cam.fov = f.fov; cam.updateProjectionMatrix(); cam.position.copy(tb(f.cam)); const lk = tb(f.look);
    const dd = cam.position.distanceTo(lk) * (spec.sway ?? 0.012); cam.position.add(new THREE.Vector3(Math.sin(f.t * 0.7) * dd, Math.sin(f.t * 0.93 + 1.3) * dd * 0.7, Math.sin(f.t * 0.51 + 2.1) * dd));      // a trace of handheld drift
    cam.lookAt(lk); cam.updateMatrixWorld(); atmo?.update(f, lk, tissue ? cam.position : null);
    const qn = cam.quaternion; sun.forEach(({ l, d }) => { l.position.copy(cam.position).add(d.clone().applyQuaternion(qn).multiplyScalar(3)); l.target.position.copy(tb(f.look)); });
    for (const [ln, node] of Object.entries(layers)) { const a = f.alpha[ln] ?? 0; node.visible = a >= 0.01; layerPre[ln].forEach((pm) => { pm.visible = a < 0.99 && (a >= (spec.prepass_min_alpha ?? 0.5) || (spec.prepass_always || []).includes(ln)); }); layerMats[ln].forEach((m) => { m.opacity = a; const solid = a >= 0.99; if (m.transparent === solid) { m.transparent = !solid; m.depthWrite = solid; m.needsUpdate = true; } }); }
    for (const [id, m] of Object.entries(hl)) { const s = f.highlight[id] ?? 0; m.visible = s >= 0.01; m.material.opacity = (spec.highlight_opacity ?? 0.3) * s; }
    for (const g of Object.values(glowCfg)) { const u = rimU[g.layer]; if (!u) continue; const v = f.glow?.[g.id] ?? 0; u.color.value.setRGB(...g.color); u.strength.value = v * (g.rim ?? 2.0); u.power.value = g.power ?? 2.5;
      layerMats[g.layer]?.forEach((m) => { if (m.emissive) { m.emissive.setRGB(...g.color); m.emissiveIntensity = v * (g.fill ?? 0.0); } }); }
    // pathology tint: [layer or 'Layer:Object'] -> colour, per frame (an object whose name starts with the part after the colon)
    for (const [key, rgb] of Object.entries(f.tint || {})) { const [ln, on] = key.split(':'); layers[ln]?.traverse((o) => { if (o.isMesh && (!on || o.name.startsWith(on))) o.material.color.setRGB(...rgb); }); }
    hcTime.value = f.t;
    for (const [ln, cfg] of Object.entries(pulseCfg)) { const k = f.pulse?.[ln] ?? 1;
      for (const c of cfg.parts) { c.n.scale.copy(c.s0).multiplyScalar(k); c.n.position.copy(c.c).add(c.p0.clone().sub(c.c).multiplyScalar(k)); if (c.pre) { c.pre.scale.copy(c.n.scale); c.pre.position.copy(c.n.position); } } }
    for (const fl of flowCfg) flowU[fl.layer].strength.value = (f.flow?.[fl.id] ?? 0) * (fl.gain ?? 1);
    proc?.update(f);
    composer.render(); return canvas.toDataURL('image/png');
  };
  window.__ready = true;
} catch (e) { window.__error = String(e && e.stack || e); }
