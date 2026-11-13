// 3D props for the Review film, built in code (no model files): what the narration talks about when it is not the phone itself.
//   server    a rack of servers, LEDs blinking, a glowing firmware package rising out of the top (shot.label "One UI 9.5", shot.sublabel "New build")
//   shield    a security shield, brushed metal with a glowing check; red shards (the flaws) orbit and are caught one by one (shot.count "179")
//   calendar  a desk flip calendar: pages flip until the month and day the line names (shot.month "Nov", shot.day "late"), a ring marks it
//   apps      glossy app icons floating in a staggered grid, each drawn with its own symbol (shot.apps [{ name, icon, color }])
// Each returns a THREE.Group with userData.update(k, t) (k 0..1 through the shot, t seconds); product.mjs places it with the prop_* moves.
export const PROP_OBJECTS = ['server', 'shield', 'calendar', 'apps'];

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const ease = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const seeded = (seed) => { let s = seed >>> 0 || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };

function canvasTex(THREE, w, h, draw) {
  const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); draw(g, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function fitFont(g, text, px, maxW, weight = 800, fam = 'TMSans, sans-serif') {
  let p = px; g.font = `${weight} ${p}px ${fam}`;
  while (p > 18 && g.measureText(text).width > maxW) { p -= 4; g.font = `${weight} ${p}px ${fam}`; }
  return p;
}
function rbox(THREE, w, h, d, r, mat) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r); s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  const geo = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: true, bevelThickness: Math.min(0.02, d * 0.3), bevelSize: Math.min(0.02, r * 0.5), bevelSegments: 4, curveSegments: 10 });
  geo.translate(0, 0, -d / 2); return new THREE.Mesh(geo, mat);
}
function labelPlane(THREE, text, sub, w, h, color = '#e8eef7') {
  const tex = canvasTex(THREE, 1024, Math.round(1024 * h / w), (g, W, H) => {
    g.textAlign = 'center'; g.fillStyle = color; const t = String(text || '');
    const p = fitFont(g, t, Math.round(H * 0.5), W * 0.9); g.fillText(t, W / 2, H * (sub ? 0.52 : 0.66));
    if (sub) { g.globalAlpha = 0.75; const q = fitFont(g, String(sub).toUpperCase(), Math.round(H * 0.2), W * 0.9, 600, 'WIMono, monospace'); g.fillText(String(sub).toUpperCase(), W / 2, H * 0.52 + p * 0.25 + q); }
  });
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false, depthWrite: false }));
}

// ---- server rack + firmware package -------------------------------------------------------------------------------------------
function buildServer(THREE, shot, envMap) {
  const grp = new THREE.Group(), glow = new THREE.Color(shot.glow || '#3ac8ff'), rs = seeded(shot.seed ?? 7);
  const metal = new THREE.MeshPhysicalMaterial({ color: '#2a2f38', metalness: 0.85, roughness: 0.38, envMap, envMapIntensity: 1.0 });
  const face = new THREE.MeshPhysicalMaterial({ color: '#14181f', metalness: 0.6, roughness: 0.5, envMap, envMapIntensity: 0.7 });
  const grill = canvasTex(THREE, 512, 128, (g, W, H) => { g.fillStyle = '#0a0c10'; g.fillRect(0, 0, W, H); g.fillStyle = '#262c36'; for (let x = 8; x < W * 0.62; x += 14) for (let y = 14; y < H - 10; y += 14) { g.beginPath(); g.arc(x, y, 4, 0, Math.PI * 2); g.fill(); } });
  const N = 6, uH = 0.2, leds = [];
  const frame = rbox(THREE, 1.5, N * uH + 0.16, 0.9, 0.05, metal); grp.add(frame);
  for (let i = 0; i < N; i++) {
    const y = (i - (N - 1) / 2) * uH, blade = rbox(THREE, 1.38, uH * 0.84, 0.06, 0.02, face); blade.position.set(0, y, 0.47); grp.add(blade);
    const gm = new THREE.Mesh(new THREE.PlaneGeometry(1.3, uH * 0.7), new THREE.MeshStandardMaterial({ map: grill, roughness: 0.8, metalness: 0.2 })); gm.position.set(0, y, 0.522); grp.add(gm);
    for (let j = 0; j < 4; j++) {
      const m = new THREE.MeshBasicMaterial({ color: j === 0 ? '#2ee6a8' : glow, toneMapped: false, transparent: true });
      const led = new THREE.Mesh(new THREE.CircleGeometry(0.014, 12), m); led.position.set(0.36 + j * 0.07, y, 0.525); grp.add(led);
      leds.push({ m, ph: rs() * 6.28, sp: 2 + rs() * 7 });
    }
  }
  // the firmware package: a glass-edged cube with the build's name, rising out of the top and turning
  const pkg = new THREE.Group();
  const glass = new THREE.MeshPhysicalMaterial({ color: glow, metalness: 0, roughness: 0.08, transmission: 0.6, thickness: 0.3, transparent: true, opacity: 0.55, envMap, emissive: glow, emissiveIntensity: 0.35 });
  const cube = rbox(THREE, 0.62, 0.62, 0.62, 0.08, glass); pkg.add(cube);
  const core = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), new THREE.MeshBasicMaterial({ color: glow, toneMapped: false })); core.rotation.set(0.6, 0.6, 0); pkg.add(core);
  const lab = labelPlane(THREE, shot.label || 'New build', shot.sublabel || '', 1.5, 0.42); lab.position.set(0, 0.62, 0); pkg.add(lab);
  pkg.position.set(0, N * uH / 2 + 0.5, 0.1); grp.add(pkg);
  const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.3, 0.6, 24, 1, true), new THREE.MeshBasicMaterial({ color: glow, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, toneMapped: false }));
  beam.position.set(0, N * uH / 2 + 0.25, 0.1); grp.add(beam);
  grp.position.y = -0.25;
  grp.userData.update = (k, t) => {
    for (const l of leds) l.m.opacity = 0.35 + 0.65 * (Math.sin(t * l.sp + l.ph) > 0.2 ? 1 : 0.2);
    const r = ease(k * 1.8);
    pkg.position.y = N * uH / 2 + 0.2 + 0.45 * r + Math.sin(t * 1.4) * 0.025; cube.rotation.y = t * 0.6; core.rotation.y = -t * 1.1;
    pkg.scale.setScalar(0.6 + 0.4 * r); lab.material.opacity = clamp01((k - 0.25) / 0.2);
    beam.material.opacity = 0.3 * (1 - r * 0.6);
  };
  return grp;
}

// ---- security shield ----------------------------------------------------------------------------------------------------------
function buildShield(THREE, shot, envMap) {
  const grp = new THREE.Group(), rs = seeded(shot.seed ?? 9), good = new THREE.Color('#2ee6a8'), bad = new THREE.Color('#ff4b5c');
  const s = new THREE.Shape(); s.moveTo(0, 0.95); s.bezierCurveTo(0.35, 0.82, 0.62, 0.8, 0.8, 0.78); s.bezierCurveTo(0.8, 0.1, 0.62, -0.55, 0, -1.0);
  s.bezierCurveTo(-0.62, -0.55, -0.8, 0.1, -0.8, 0.78); s.bezierCurveTo(-0.62, 0.8, -0.35, 0.82, 0, 0.95);
  const geo = new THREE.ExtrudeGeometry(s, { depth: 0.16, bevelEnabled: true, bevelThickness: 0.06, bevelSize: 0.05, bevelSegments: 6, curveSegments: 32 }); geo.translate(0, 0, -0.08);
  const metal = new THREE.MeshPhysicalMaterial({ color: '#9aa6b8', metalness: 1, roughness: 0.25, clearcoat: 0.6, envMap, envMapIntensity: 1.3 });
  const body = new THREE.Mesh(geo, metal); grp.add(body);
  const inner = new THREE.Mesh(new THREE.ShapeGeometry(s, 32), new THREE.MeshPhysicalMaterial({ color: '#1a2230', metalness: 0.7, roughness: 0.4, envMap })); inner.scale.setScalar(0.82); inner.position.z = 0.145; grp.add(inner);
  // the check, as a glowing tube drawn on over the shot
  const path = new THREE.CatmullRomCurve3([new THREE.Vector3(-0.32, 0.02, 0.17), new THREE.Vector3(-0.08, -0.24, 0.17), new THREE.Vector3(0.36, 0.3, 0.17)], false, 'catmullrom', 0.0);
  const checkMat = new THREE.MeshBasicMaterial({ color: good, toneMapped: false });
  const tube = new THREE.Mesh(new THREE.TubeGeometry(path, 64, 0.045, 12, false), checkMat); grp.add(tube);
  const total = tube.geometry.index.count;
  const lab = labelPlane(THREE, shot.label || '', shot.sublabel || '', 1.9, 0.5); lab.position.set(0, -1.35, 0.1); if (shot.label) grp.add(lab);
  // the flaws: red shards orbiting, each pulled in and turned green in turn
  const shards = [], n = 26, sg = new THREE.TetrahedronGeometry(0.06);
  for (let i = 0; i < n; i++) {
    const m = new THREE.MeshPhysicalMaterial({ color: bad, emissive: bad, emissiveIntensity: 0.9, metalness: 0.2, roughness: 0.3 });
    const sh = new THREE.Mesh(sg, m); grp.add(sh); shards.push({ sh, m, a: rs() * 6.28, r: 1.25 + rs() * 0.5, y: (rs() - 0.5) * 1.6, sp: 0.4 + rs() * 0.5, at: 0.15 + 0.7 * (i / n) });
  }
  grp.userData.update = (k, t) => {
    tube.geometry.setDrawRange(0, Math.floor(total * ease((k - 0.45) / 0.35) / 3) * 3);
    body.rotation.y = Math.sin(t * 0.5) * 0.08;
    for (const s0 of shards) {
      const c = ease((k - s0.at) / 0.12), a = s0.a + t * s0.sp, r = s0.r * (1 - 0.75 * c);
      s0.sh.position.set(Math.cos(a) * r, s0.y * (1 - c), Math.sin(a) * r * 0.6 + 0.1); s0.sh.rotation.set(t * 2 + s0.a, t * 1.5, 0);
      s0.m.color.copy(bad).lerp(good, c); s0.m.emissive.copy(bad).lerp(good, c); s0.sh.scale.setScalar(1 - c * 0.9);
    }
    lab.material.opacity = clamp01((k - 0.3) / 0.2);
  };
  return grp;
}

// ---- desk flip calendar -------------------------------------------------------------------------------------------------------
function pageTex(THREE, month, day, accent) {
  return canvasTex(THREE, 512, 600, (g, W, H) => {
    g.fillStyle = '#f4f5f7'; g.fillRect(0, 0, W, H); g.fillStyle = accent; g.fillRect(0, 0, W, 150);
    g.fillStyle = '#fff'; g.textAlign = 'center'; fitFont(g, String(month).toUpperCase(), 96, W * 0.85); g.fillText(String(month).toUpperCase(), W / 2, 112);
    g.fillStyle = '#16191e';
    if (String(day || '').trim()) { const big = /^\d+$/.test(String(day)); fitFont(g, String(day), big ? 300 : 150, W * 0.85, 900, 'StarMapSans, sans-serif'); g.fillText(String(day), W / 2, big ? 470 : 420); }
    else { fitFont(g, String(month).toUpperCase(), 170, W * 0.85, 900, 'StarMapSans, sans-serif'); g.fillText(String(month).toUpperCase(), W / 2, 420); }
  });
}
function buildCalendar(THREE, shot, envMap) {
  const grp = new THREE.Group(), accent = shot.glow || '#e63946';
  const months = (shot.pages && shot.pages.length ? shot.pages : [{ month: shot.month || 'Nov', day: shot.day || '' }]).slice(0, 4);
  const base = rbox(THREE, 1.5, 0.22, 0.7, 0.05, new THREE.MeshPhysicalMaterial({ color: '#23272f', metalness: 0.5, roughness: 0.4, envMap })); base.position.set(0, -0.95, 0); grp.add(base);
  const back = rbox(THREE, 1.3, 1.6, 0.06, 0.06, new THREE.MeshPhysicalMaterial({ color: '#2b3039', metalness: 0.4, roughness: 0.5, envMap })); back.position.set(0, 0, -0.08); back.rotation.x = -0.12; grp.add(back);
  const rings = [];
  for (const x of [-0.4, 0, 0.4]) { const r = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.014, 10, 24), new THREE.MeshPhysicalMaterial({ color: '#c8ced8', metalness: 1, roughness: 0.2, envMap })); r.position.set(x, 0.8, 0); r.rotation.y = Math.PI / 2; grp.add(r); rings.push(r); }
  // pages: matte and below white, so a page facing the key light never blooms out
  const pages = months.map((p, i) => {
    const hinge = new THREE.Group(); hinge.position.set(0, 0.8, 0.01 + (months.length - i) * 0.004); hinge.rotation.x = -0.12;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.5), new THREE.MeshStandardMaterial({ map: pageTex(THREE, p.month, p.day, accent), color: '#b9bec7', roughness: 1, metalness: 0, envMapIntensity: 0.25, side: THREE.DoubleSide }));
    m.position.y = -0.75; hinge.add(m); grp.add(hinge); return hinge;
  });
  const mark = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.02, 10, 64), new THREE.MeshBasicMaterial({ color: accent, toneMapped: false, transparent: true }));
  mark.position.set(0, -0.32, 0.06); mark.rotation.x = -0.12; grp.add(mark);
  grp.userData.update = (k, t) => {
    const steps = pages.length - 1;
    pages.forEach((h, i) => { if (i === steps) { h.rotation.x = -0.12; return; } const fk = ease((k * 1.6 - i * 0.28) / 0.3); h.rotation.x = -0.12 - fk * 2.9; h.visible = fk < 0.99; });
    const mk = ease((k - 0.55) / 0.25); mark.material.opacity = mk; mark.scale.setScalar(0.6 + 0.4 * mk); mark.rotation.z = t * 0.4;
  };
  return grp;
}

// ---- floating app icons -------------------------------------------------------------------------------------------------------
function glyph(g, kind, W, H) {
  g.strokeStyle = '#fff'; g.fillStyle = '#fff'; g.lineWidth = W * 0.06; g.lineCap = 'round'; g.lineJoin = 'round';
  const c = W / 2, s = W * 0.28;
  switch (kind) {
    case 'calendar': g.strokeRect(c - s, c - s * 0.8, s * 2, s * 1.8); g.fillRect(c - s, c - s * 0.8, s * 2, s * 0.45); for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) g.fillRect(c - s * 0.7 + i * s * 0.55, c + j * s * 0.45, s * 0.3, s * 0.25); break;
    case 'heart': g.beginPath(); g.moveTo(c, c + s * 0.9); g.bezierCurveTo(c - s * 1.6, c - s * 0.1, c - s * 0.7, c - s * 1.2, c, c - s * 0.4); g.bezierCurveTo(c + s * 0.7, c - s * 1.2, c + s * 1.6, c - s * 0.1, c, c + s * 0.9); g.fill(); break;
    case 'memory': g.beginPath(); g.arc(c, c, s, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.moveTo(c, c - s * 0.6); g.lineTo(c, c); g.lineTo(c + s * 0.45, c + s * 0.3); g.stroke(); g.beginPath(); g.arc(c, c, s * 1.35, -2.4, -0.6); g.stroke(); break;
    case 'note': g.strokeRect(c - s * 0.8, c - s, s * 1.6, s * 2); for (let i = 0; i < 3; i++) { g.beginPath(); g.moveTo(c - s * 0.5, c - s * 0.45 + i * s * 0.45); g.lineTo(c + s * 0.5, c - s * 0.45 + i * s * 0.45); g.stroke(); } break;
    case 'gear': g.beginPath(); g.arc(c, c, s * 0.75, 0, Math.PI * 2); g.stroke(); for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4; g.beginPath(); g.moveTo(c + Math.cos(a) * s * 0.8, c + Math.sin(a) * s * 0.8); g.lineTo(c + Math.cos(a) * s * 1.15, c + Math.sin(a) * s * 1.15); g.stroke(); } g.beginPath(); g.arc(c, c, s * 0.28, 0, Math.PI * 2); g.fill(); break;
    case 'cloud': g.beginPath(); g.arc(c - s * 0.45, c + s * 0.1, s * 0.5, Math.PI * 0.5, Math.PI * 1.5); g.arc(c, c - s * 0.25, s * 0.6, Math.PI, 0); g.arc(c + s * 0.55, c + s * 0.15, s * 0.45, Math.PI * 1.5, Math.PI * 0.5); g.closePath(); g.fill(); break;
    case 'people': g.beginPath(); g.arc(c - s * 0.4, c - s * 0.35, s * 0.32, 0, 7); g.arc(c + s * 0.45, c - s * 0.3, s * 0.28, 0, 7); g.fill(); g.beginPath(); g.ellipse(c - s * 0.4, c + s * 0.6, s * 0.6, s * 0.45, 0, Math.PI, 0); g.fill(); break;
    default: g.beginPath(); g.arc(c, c, s * 0.9, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.moveTo(c - s * 0.3, c); g.lineTo(c + s * 0.3, c); g.moveTo(c, c - s * 0.3); g.lineTo(c, c + s * 0.3); g.stroke();
  }
}
function buildApps(THREE, shot, envMap) {
  const grp = new THREE.Group(), apps = (shot.apps && shot.apps.length ? shot.apps : [{ name: 'App', icon: 'gear', color: '#3a7bff' }]).slice(0, 6), rs = seeded(shot.seed ?? 5);
  const n = apps.length, cols = n <= 3 ? n : Math.ceil(n / 2), items = [];
  apps.forEach((a, i) => {
    const col = new THREE.Color(a.color || '#3a7bff');
    const tex = canvasTex(THREE, 512, 512, (g, W, H) => { const gr = g.createLinearGradient(0, 0, W, H); gr.addColorStop(0, '#' + col.clone().offsetHSL(0, 0, 0.12).getHexString()); gr.addColorStop(1, '#' + col.clone().offsetHSL(0, 0, -0.12).getHexString()); g.fillStyle = gr; g.fillRect(0, 0, W, H); glyph(g, a.icon, W, H); });
    const mat = new THREE.MeshPhysicalMaterial({ map: tex, roughness: 0.18, metalness: 0.0, clearcoat: 1, clearcoatRoughness: 0.08, envMap, envMapIntensity: 0.9 });
    const side = new THREE.MeshPhysicalMaterial({ color: col, roughness: 0.25, clearcoat: 1, envMap });
    const icon = rbox(THREE, 0.62, 0.62, 0.12, 0.16, [mat, side]);
    // the extruded cap faces carry UVs in shape space (-0.31..0.31): map them to 0..1
    const uv = icon.geometry.attributes.uv; for (let j = 0; j < uv.count; j++) uv.setXY(j, uv.getX(j) / 0.62 + 0.5, uv.getY(j) / 0.62 + 0.5); uv.needsUpdate = true;
    const r = Math.floor(i / cols), c = i % cols, rowN = Math.min(cols, n - r * cols);
    const holder = new THREE.Group(); holder.add(icon);
    const lab = labelPlane(THREE, a.name, '', 1.0, 0.2); lab.position.set(0, -0.48, 0.05); holder.add(lab);
    holder.userData.home = new THREE.Vector3((c - (rowN - 1) / 2) * 0.95, (n > cols ? (r === 0 ? 0.55 : -0.6) : 0), 0);
    grp.add(holder); items.push({ holder, icon, lab, at: 0.08 + 0.55 * (i / Math.max(1, n)), ph: rs() * 6.28 });
  });
  grp.userData.update = (k, t) => {
    for (const it of items) {
      const p = ease((k - it.at) / 0.18), h = it.holder.userData.home;
      it.holder.position.set(h.x, h.y + Math.sin(t * 1.2 + it.ph) * 0.03 - (1 - p) * 0.5, h.z + (1 - p) * 1.2);
      it.holder.scale.setScalar(0.001 + p); it.icon.rotation.y = (1 - p) * 1.6 + Math.sin(t * 0.8 + it.ph) * 0.12; it.lab.material.opacity = clamp01((k - it.at - 0.1) / 0.12);
    }
  };
  return grp;
}

const FIT = { server: [0.72, -0.2], shield: [0.8, 0.12], calendar: [0.8, 0.12], apps: [0.82, 0.05] };   // scale and lift so the whole prop and its label sit in frame
export function buildProp(THREE, shot, envMap) {
  const inner = { server: buildServer, shield: buildShield, calendar: buildCalendar, apps: buildApps }[shot.object];
  if (!inner) throw new Error(`props3d: unknown prop ${shot.object}`);
  const g = inner(THREE, shot, envMap), outer = new THREE.Group(), [sc, dy] = FIT[shot.object];
  g.scale.multiplyScalar(sc); g.position.y = g.position.y * sc + dy; outer.add(g);
  outer.userData.update = (k, t) => g.userData.update && g.userData.update(k, t);
  return outer;
}

/** Camera for a prop (the prop sits at the origin, about 2 units tall): k 0..1 through the shot, t seconds, e the eased k. */
export function propPlacement(THREE, shot, k, t, e, lerp) {
  const eul = (x, y, z) => new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z, 'YXZ')), fl = Math.sin(t * 0.9) * 0.015;
  switch (shot.move) {
    case 'prop_low': return { q: eul(0, lerp(0.5, -0.25, e), 0), pos: new THREE.Vector3(lerp(-0.6, 0.4, e), lerp(-0.7, -0.4, e), lerp(4.4, 3.7, e)), at: new THREE.Vector3(0, 0.15, 0), fov: 34, roll: lerp(0.05, -0.02, e), phone: new THREE.Vector3(0, fl, 0) };
    case 'prop_top': return { q: eul(0, lerp(-0.45, 0.3, e), 0), pos: new THREE.Vector3(lerp(0.8, -0.3, e), lerp(1.5, 1.0, e), lerp(4.2, 3.6, e)), at: new THREE.Vector3(0, 0, 0), fov: 34, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    case 'prop_push': return { q: eul(0, lerp(-0.12, 0.12, e), 0), pos: new THREE.Vector3(0, 0.1, lerp(5.2, 3.3, e)), at: new THREE.Vector3(0, 0.05, 0), fov: 32, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
    default: return { q: eul(0, lerp(-0.7, 0.55, e), 0), pos: new THREE.Vector3(0, 0.2, lerp(4.6, 3.9, e)), at: new THREE.Vector3(0, 0.05, 0), fov: 34, roll: 0, phone: new THREE.Vector3(0, fl, 0) };
  }
}
export const PROP_MOVES = ['prop_turn', 'prop_low', 'prop_top', 'prop_push'];
