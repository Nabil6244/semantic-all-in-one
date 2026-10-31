// Atmosphere for Health Cinema 3D scenes: a graded backdrop instead of flat black, depth fog, slow floating motes (marine-snow style bokeh) and a trace of camera drift.
// Deterministic (a function of the scene time only). Palette per spec.theme: blood (arteries, clots), cell (inside a cell), organ (anatomy, default).
const THEMES = {
  blood: { c: [150, 34, 44], m: [58, 12, 24], e: [9, 3, 7], fog: [0.07, 0.02, 0.035], mote: [255, 170, 140] },
  cell: { c: [34, 122, 150], m: [12, 42, 78], e: [3, 8, 22], fog: [0.02, 0.06, 0.11], mote: [170, 235, 255] },
  organ: { c: [40, 70, 120], m: [14, 26, 56], e: [3, 6, 14], fog: [0.015, 0.03, 0.065], mote: [170, 200, 255] },
  // moods the variety director (health_cinema/variety.py) picks per scene via spec.palette
  teal: { c: [24, 104, 108], m: [8, 38, 46], e: [2, 9, 12], fog: [0.01, 0.05, 0.055], mote: [160, 255, 236] },
  violet: { c: [78, 52, 128], m: [28, 18, 56], e: [7, 4, 16], fog: [0.035, 0.022, 0.07], mote: [215, 190, 255] },
  amber: { c: [122, 72, 34], m: [46, 24, 14], e: [12, 6, 4], fog: [0.06, 0.03, 0.015], mote: [255, 214, 160] },
  crimson: { c: [118, 30, 44], m: [44, 10, 20], e: [11, 3, 6], fog: [0.06, 0.012, 0.025], mote: [255, 176, 176] },
  steel: { c: [70, 84, 100], m: [26, 32, 42], e: [6, 8, 11], fog: [0.03, 0.036, 0.046], mote: [212, 226, 245] },
  emerald: { c: [30, 100, 64], m: [10, 38, 26], e: [3, 10, 7], fog: [0.012, 0.05, 0.03], mote: [180, 255, 210] },
  ocean: { c: [22, 80, 140], m: [8, 28, 62], e: [2, 7, 18], fog: [0.008, 0.035, 0.08], mote: [150, 215, 255] },
};
export function build(THREE, scene, spec, dist0) {
  const T = THEMES[spec.palette] || THEMES[spec.theme] || THEMES.organ; const rgb = (a, k = 1) => `rgb(${a.map((v) => Math.round(v * k)).join(',')})`;
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
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3)); const fade = new Float32Array(N * 3).fill(1); geo.setAttribute('color', new THREE.BufferAttribute(fade, 3));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({ vertexColors: true, size: dist0 * 0.03, map: new THREE.CanvasTexture(sp), color: new THREE.Color(T.mote[0] / 255, T.mote[1] / 255, T.mote[2] / 255), transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true, fog: false }));
  pts.frustumCulled = false; pts.renderOrder = 1; scene.add(pts);
  return { update(f, look, cam = null) {
    const t = f.t; pts.position.set(look.x, look.y, look.z);
    for (let i = 0; i < N; i++) { pos[i * 3] = base[i * 3] + Math.sin(t * 0.21 + ph[i * 3]) * 0.06 * span; pos[i * 3 + 1] = base[i * 3 + 1] + ((t * 0.018 * span + ph[i * 3 + 1]) % 1) * 0.0 + Math.sin(t * 0.17 + ph[i * 3 + 1]) * 0.07 * span; pos[i * 3 + 2] = base[i * 3 + 2] + Math.cos(t * 0.19 + ph[i * 3 + 2]) * 0.06 * span; }
    if (cam) {      // a mote drifting close to the lens would be drawn as a huge soft blob: it fades out (additive blending, so a darker colour is a fainter mote) as it nears the camera
      const cx = cam.x - look.x, cy = cam.y - look.y, cz = cam.z - look.z, cd = Math.hypot(cx, cy, cz), a = cd * 0.3, b = cd * 0.6;
      for (let i = 0; i < N; i++) { const d = Math.hypot(pos[i * 3] - cx, pos[i * 3 + 1] - cy, pos[i * 3 + 2] - cz); const x = Math.min(1, Math.max(0, (d - a) / (b - a))); fade[i * 3] = fade[i * 3 + 1] = fade[i * 3 + 2] = x * x * (3 - 2 * x); }
      geo.attributes.color.needsUpdate = true;
    }
    geo.attributes.position.needsUpdate = true;
  } };
}
