// Atmosphere for Health Cinema 3D scenes: a graded backdrop instead of flat black, depth fog, slow floating motes (marine-snow style bokeh) and a trace of camera drift.
// Deterministic (a function of the scene time only). Palette per spec.theme: blood (arteries, clots), cell (inside a cell), organ (anatomy, default).
const THEMES = {
  blood: { c: [150, 34, 44], m: [58, 12, 24], e: [9, 3, 7], fog: [0.07, 0.02, 0.035], mote: [255, 170, 140] },
  cell: { c: [34, 122, 150], m: [12, 42, 78], e: [3, 8, 22], fog: [0.02, 0.06, 0.11], mote: [170, 235, 255] },
  organ: { c: [40, 70, 120], m: [14, 26, 56], e: [3, 6, 14], fog: [0.015, 0.03, 0.065], mote: [170, 200, 255] },
};
export function build(THREE, scene, spec, dist0) {
  const T = THEMES[spec.theme] || THEMES.organ; const rgb = (a, k = 1) => `rgb(${a.map((v) => Math.round(v * k)).join(',')})`;
  const cv = document.createElement('canvas'); cv.width = 1280; cv.height = 720; const g = cv.getContext('2d');
  const grad = g.createRadialGradient(640, 330, 10, 640, 360, 820); grad.addColorStop(0, rgb(T.c)); grad.addColorStop(0.42, rgb(T.m)); grad.addColorStop(1, rgb(T.e)); g.fillStyle = grad; g.fillRect(0, 0, 1280, 720);
  const streak = g.createLinearGradient(0, 120, 1280, 560); streak.addColorStop(0, 'rgba(255,255,255,0)'); streak.addColorStop(0.5, 'rgba(255,255,255,0.045)'); streak.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = streak; g.fillRect(0, 0, 1280, 720);   // a faint diagonal light wash
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; scene.background = tex;
  if (spec.fog !== false) scene.fog = new THREE.FogExp2(new THREE.Color(...T.fog), (spec.fog_density ?? 0.5) / Math.max(0.05, dist0));
  const N = spec.motes ?? 260, span = dist0 * 1.1, base = new Float32Array(N * 3), ph = new Float32Array(N * 3), pos = new Float32Array(N * 3); let s = 12345;
  const r = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
  for (let i = 0; i < N; i++) { base[i * 3] = (r() - 0.5) * 2 * span; base[i * 3 + 1] = (r() - 0.5) * 1.3 * span; base[i * 3 + 2] = (r() - 0.5) * 2 * span; ph[i * 3] = r() * 6.28; ph[i * 3 + 1] = r() * 6.28; ph[i * 3 + 2] = r() * 6.28; }
  const sp = document.createElement('canvas'); sp.width = sp.height = 64; const sg = sp.getContext('2d'), rg = sg.createRadialGradient(32, 32, 0, 32, 32, 32);
  rg.addColorStop(0, 'rgba(255,255,255,0.9)'); rg.addColorStop(0.4, 'rgba(255,255,255,0.25)'); rg.addColorStop(1, 'rgba(255,255,255,0)'); sg.fillStyle = rg; sg.fillRect(0, 0, 64, 64);
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({ size: dist0 * 0.03, map: new THREE.CanvasTexture(sp), color: new THREE.Color(T.mote[0] / 255, T.mote[1] / 255, T.mote[2] / 255), transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true, fog: false }));
  pts.frustumCulled = false; pts.renderOrder = 1; scene.add(pts);
  return { update(f, look) {
    const t = f.t; pts.position.set(look.x, look.y, look.z);
    for (let i = 0; i < N; i++) { pos[i * 3] = base[i * 3] + Math.sin(t * 0.21 + ph[i * 3]) * 0.06 * span; pos[i * 3 + 1] = base[i * 3 + 1] + ((t * 0.018 * span + ph[i * 3 + 1]) % 1) * 0.0 + Math.sin(t * 0.17 + ph[i * 3 + 1]) * 0.07 * span; pos[i * 3 + 2] = base[i * 3 + 2] + Math.cos(t * 0.19 + ph[i * 3 + 2]) * 0.06 * span; }
    geo.attributes.position.needsUpdate = true;
  } };
}
