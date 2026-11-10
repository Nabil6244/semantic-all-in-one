// A 2D puppet host made from one drawn picture (assets/puppets/<name>): unlit planes, so her colours stay exactly as drawn.
// Body and head are separate layers; the head pivots at the neck over a stub of her own neck. Her sleeves, arms, hands, legs and shoes are drawn
// in colours sampled from the picture, because in the picture her arms are fixed, she has no visible hands and she stops at the waist. Between lines the picture's own
// smile shows; while she speaks a clean patch of her own skin hides it and a mouth in her sampled colours follows the voice.
// loadPuppet2D(name) -> Group; posePuppet2D(host, t, state, plan).
import * as THREE from '/three/three.module.min.js';
import { blinkAt } from './toon.js';
import { visemeWeights, mouthShape, speakingAmount, puppetMotion, armPose, signAt, withSign, sleeveShape, performance, ponySwing } from './puppet_rules.mjs';

const canvasOf = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
const polygon = (ctx, pts) => { ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); };
const css = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;

// Her pixels go to the screen untouched: no lights, no tone mapping and no colour conversion. Blending in the picture's own colour space (with
// premultiplied edges) keeps soft edges and patches from going pale or dark, and matches how the drawing was composited.
const VERT = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }';
const FRAG = 'uniform sampler2D map; varying vec2 vUv; void main() { gl_FragColor = texture2D(map, vUv); }';
// Her head layer bends instead of being cut: the ponytail swings as one piece from its root and the brows lift with the skin around them, so nothing can tear or leave a hole.
const HEAD_VERT = `uniform vec2 uSize; uniform float uK; uniform vec2 uAnchor; uniform vec2 uPonyY; uniform vec2 uPonyX; uniform float uSwing; uniform vec2 uBrowA; uniform vec2 uBrowB; uniform vec2 uBrowR; uniform float uBrow;
varying vec2 vUv;
void main() {
  vUv = uv;
  vec2 p = vec2(uv.x * uSize.x, (1.0 - uv.y) * uSize.y), o = p;
  float w = smoothstep(uPonyY.x, uPonyY.y, p.y) * (1.0 - smoothstep(uPonyX.x, uPonyX.y, p.x));
  float a = uSwing * w, c = cos(a), s = sin(a);
  vec2 d = p - uAnchor;
  p = uAnchor + vec2(c * d.x - s * d.y, s * d.x + c * d.y);
  vec2 g0 = (o - uBrowA) / uBrowR, g1 = (o - uBrowB) / uBrowR;
  p.y -= uBrow * (exp(-dot(g0, g0)) + exp(-dot(g1, g1)));
  vec3 q = position + vec3((p.x - o.x) * uK, -(p.y - o.y) * uK, 0.0);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(q, 1.0);
}`;
function headPlane(canvas, spec, k, order) {
  const m = plane(canvas, 0, 0, spec, k, order), W = spec.warp, u = m.material.uniforms;
  m.geometry.dispose(); m.geometry = new THREE.PlaneGeometry(canvas.width * k, canvas.height * k, 70, 100);
  Object.assign(u, { uSize: { value: new THREE.Vector2(canvas.width, canvas.height) }, uK: { value: k }, uAnchor: { value: new THREE.Vector2(...W.pony.anchor) }, uPonyY: { value: new THREE.Vector2(...W.pony.y) }, uPonyX: { value: new THREE.Vector2(...W.pony.x) }, uSwing: { value: 0 },
    uBrowA: { value: new THREE.Vector2(...W.brows[0]) }, uBrowB: { value: new THREE.Vector2(...W.brows[1]) }, uBrowR: { value: new THREE.Vector2(...W.browRadius) }, uBrow: { value: 0 } });
  m.material.vertexShader = HEAD_VERT; m.material.needsUpdate = true;
  return m;
}

function plane(canvas, x0, y0, spec, k, order, res = 1) {
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.NoColorSpace; tex.premultiplyAlpha = true;
  const mat = new THREE.ShaderMaterial({ uniforms: { map: { value: tex } }, vertexShader: VERT, fragmentShader: FRAG, transparent: true, depthWrite: false, fog: false,
    blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor, blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor, blendEquation: THREE.AddEquation });
  const w = (canvas.width / res) * k, h = (canvas.height / res) * k, m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
  m.renderOrder = order; m.frustumCulled = false;
  m.userData.origin = [x0 * k + w / 2, -y0 * k - h / 2];                    // from the picture's top-left, y up
  m.userData.tex = tex;
  return m;
}

// Everything above the cut line belongs to the head, the whole ponytail included.
function headRegion(ctx, spec, W) { polygon(ctx, [[0, 0], [W, 0], ...[...spec.head.cut].reverse()]); }

function buildLayers(img, spec, C) {
  const W = img.width, N = spec.head, A = spec.arms, L = spec.legs, H = L.hipBottom + 8, cxm = spec.anchorX;
  const body = canvasOf(W, H), b = body.getContext('2d');
  // Below the picture: the overalls carry on to the hips, in the picture's own last row of colours.
  const hip = (x) => { x.beginPath(); x.moveTo(400, 1500); x.bezierCurveTo(384, 1560, 374, 1620, 372, L.hipBottom); x.lineTo(cxm - 16, L.hipBottom); x.quadraticCurveTo(cxm, L.hipBottom - 40, cxm + 16, L.hipBottom); x.lineTo(880, L.hipBottom); x.bezierCurveTo(878, 1620, 868, 1560, 852, 1500); x.closePath(); };
  b.save(); hip(b); b.clip(); b.fillStyle = css(C.denim); b.fillRect(0, 1490, W, 300); b.drawImage(img, 0, 1506, W, 1, 0, 1500, W, 60);
  const fade = b.createLinearGradient(0, 1540, 0, 1600); fade.addColorStop(0, `rgba(${C.denim},0)`); fade.addColorStop(1, `rgba(${C.denim},1)`); b.fillStyle = fade; b.fillRect(0, 1540, W, 60); b.restore();
  b.strokeStyle = css(C.navy); b.lineWidth = 6; b.lineCap = 'round'; b.beginPath(); b.moveTo(399, 1508); b.bezierCurveTo(384, 1560, 374, 1620, 372, L.hipBottom); b.moveTo(853, 1508); b.bezierCurveTo(868, 1560, 878, 1620, 880, L.hipBottom); b.moveTo(cxm, 1575); b.lineTo(cxm, L.hipBottom - 34); b.stroke();
  b.drawImage(img, 0, 0);
  // Neck stub behind the head: one row of her neck repeated upward, so tilting the head never opens a gap.
  const [sx0, sx1] = N.neckStub.x, stub = canvasOf(sx1 - sx0, 1); stub.getContext('2d').drawImage(img, sx0, N.neckStub.row, sx1 - sx0, 1, 0, 0, sx1 - sx0, 1);
  b.save(); headRegion(b, spec, W); b.globalCompositeOperation = 'destination-out'; b.fill(); b.restore();
  b.drawImage(stub, sx0, N.neckStub.top, sx1 - sx0, N.neckStub.row - N.neckStub.top + 1);
  // The drawn-on arms and sleeves leave the torso; they come back as moving parts.
  b.save(); b.globalCompositeOperation = 'destination-out'; for (const sd of [A.left, A.right]) { polygon(b, sd.erase); b.fill(); } b.restore();
  // Her shoulders stay on the torso as a permanent rounded cap, so an arm has something to turn on at any angle.
  for (const sd of [A.left, A.right]) { b.beginPath(); b.arc(sd.pivot[0], sd.pivot[1], A.sleeve.capRadius, 0, Math.PI * 2); b.fillStyle = css(C.pink); b.fill(); }
  const head = canvasOf(W, img.height), h = head.getContext('2d');
  h.save(); headRegion(h, spec, W); h.clip(); h.drawImage(img, 0, 0); h.restore();
  // Soft end of the head layer's neck, so its edge never shows as a line.
  const [fy0, fy1] = N.neckFeather.y, g = h.createLinearGradient(0, fy0, 0, fy1); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, 'rgba(0,0,0,1)');
  h.save(); h.globalCompositeOperation = 'destination-out'; h.fillStyle = g; h.fillRect(N.neckFeather.x[0], fy0, N.neckFeather.x[1] - N.neckFeather.x[0], fy1 - fy0); h.restore();
  return { body, head };
}

// One leg, hip to shoe, drawn in her colours. side -1 = screen left.
function legCanvas(spec, side, C) {
  const L = spec.legs, W = 420, top = L.hipBottom - 70, c = canvasOf(W, L.foot - top + 8), x = c.getContext('2d');
  const X = (d) => (side < 0 ? W - d : d), Y = (y) => y - top;                       // d = distance out from her centre line
  const pants = () => { x.beginPath(); x.moveTo(X(6), Y(top)); x.lineTo(X(254), Y(top)); x.lineTo(X(238), Y(L.cuff)); x.lineTo(X(30), Y(L.cuff)); x.closePath(); };
  x.lineJoin = 'round'; x.lineCap = 'round';
  // ankle + sock
  x.fillStyle = css(C.teeth); x.strokeStyle = css(C.line); x.lineWidth = 5; x.beginPath(); x.rect(side < 0 ? X(190) : X(78), Y(L.cuff + 30), 112, 95); x.fill(); x.stroke();
  // shoe, toes out
  x.beginPath(); x.moveTo(X(70), Y(L.foot - 4)); x.quadraticCurveTo(X(62), Y(L.foot - 92), X(120), Y(L.foot - 100)); x.lineTo(X(190), Y(L.foot - 104)); x.quadraticCurveTo(X(330), Y(L.foot - 92), X(345), Y(L.foot - 22)); x.quadraticCurveTo(X(348), Y(L.foot - 4), X(325), Y(L.foot - 4)); x.closePath(); x.fillStyle = css(C.pink); x.fill(); x.strokeStyle = css(C.navy); x.lineWidth = 6; x.stroke();
  x.fillStyle = css(C.teeth); x.beginPath(); x.rect(side < 0 ? X(345) : X(70), Y(L.foot - 26), 275, 20); x.fill(); x.stroke();
  x.strokeStyle = css(C.teeth); x.lineWidth = 7; for (const d of [150, 180]) { x.beginPath(); x.moveTo(X(d), Y(L.foot - 98)); x.lineTo(X(d + 24), Y(L.foot - 74)); x.stroke(); }
  // trousers
  x.fillStyle = css(C.denim); pants(); x.fill();
  x.save(); pants(); x.clip(); const sh = x.createLinearGradient(X(6), 0, X(90), 0); sh.addColorStop(0, `rgba(${C.navy},.28)`); sh.addColorStop(1, `rgba(${C.navy},0)`); x.fillStyle = sh; x.fillRect(0, 0, W, c.height); x.restore();
  x.strokeStyle = css(C.navy); x.lineWidth = 6; pants(); x.stroke();
  // rolled cuff
  x.fillStyle = css(C.denim.map((v) => Math.min(255, v + 34))); x.beginPath(); x.moveTo(X(26), Y(L.cuff - 34)); x.lineTo(X(242), Y(L.cuff - 34)); x.lineTo(X(240), Y(L.cuff + 14)); x.lineTo(X(28), Y(L.cuff + 14)); x.closePath(); x.fill(); x.stroke();
  return c;
}

// Arms, sleeves and hands are drawn fresh each frame, in the picture's own colours.
const ARM_RES = 0.75, ARM_REACH = 700;
function capsule(x, a, b, ra, rb, grow) {
  const n = Math.max(2, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 6));
  x.beginPath();
  for (let i = 0; i <= n; i++) { const t = i / n, r = ra + (rb - ra) * t + grow, px = a[0] + (b[0] - a[0]) * t, py = a[1] + (b[1] - a[1]) * t; x.moveTo(px + r, py); x.arc(px, py, r, 0, Math.PI * 2); }
  x.fill();
}
// A limb part: outline, skin, and a shade along its underside like the arms in her picture.
function limb(x, a, b, ra, rb, C) {
  x.fillStyle = css(C.line); capsule(x, a, b, ra, rb, 4);
  x.fillStyle = css(C.armShade); capsule(x, a, b, ra, rb, 0);
  const lift = Math.max(5, Math.min(ra, rb) * 0.26); x.fillStyle = css(C.armSkin); capsule(x, [a[0], a[1] - lift], [b[0], b[1] - lift], ra * 0.92, rb * 0.92, 0);
}
function drawSleeve(x, sd, E, rig, C) {
  const S = sleeveShape(sd.pivot, E, rig.sleeve), P = sd.pivot, { d, n, H, half, cap } = S, at = (o, u, v) => [o[0] + d[0] * u + n[0] * v, o[1] + d[1] * u + n[1] * v];
  // the cap and the tube are one shape, so it can never open up at the shoulder
  const path = () => {
    const a = at(P, 0, cap), b0 = at(H, -14, half), b1 = at(H, 0, half), b2 = at(H, 0, half - 14), c0 = at(H, 0, -half + 14), c1 = at(H, 0, -half), c2 = at(H, -14, -half), e = at(P, 0, -cap), ang = Math.atan2(n[1], n[0]);
    x.beginPath(); x.moveTo(...a); x.lineTo(...b0); x.quadraticCurveTo(...b1, ...b2); x.lineTo(...c0); x.quadraticCurveTo(...c1, ...c2); x.lineTo(...e); x.arc(P[0], P[1], cap, ang + Math.PI, ang, true); x.closePath();
  };
  const down = n[1] >= 0 ? 1 : -1, lo = at(H, 0, down * half), hi = at(H, 0, -down * half), g = x.createLinearGradient(hi[0], hi[1], lo[0], lo[1]);
  g.addColorStop(0, css(C.pink.map((v) => Math.min(255, v + 12)))); g.addColorStop(0.55, css(C.pink)); g.addColorStop(1, css(C.pinkShade));
  x.save(); x.fillStyle = g; x.strokeStyle = css(C.pinkShade.map((v) => Math.round(v * 0.86))); x.lineWidth = 4; x.lineJoin = 'round'; path(); x.fill(); x.stroke();
  // hem stitches, as in her picture
  x.strokeStyle = 'rgba(255,255,255,.75)'; x.lineWidth = 4; x.setLineDash([16, 13]); x.lineCap = 'round'; const s0 = at(H, -13, -half + 12), s1 = at(H, -13, half - 12); x.beginPath(); x.moveTo(...s0); x.lineTo(...s1); x.stroke(); x.setLineDash([]);
  x.restore();
  return S;
}
// A child's hand, drawn finger by finger so each keeps its own outline. Local drawing: wrist at 0, fingers toward +y, `th` = the thumb's side.
function drawHand(x, W, dir, side, kind, phase, C) {
  x.save(); x.translate(W[0], W[1]); x.rotate(-side * dir); x.lineCap = 'round'; x.lineJoin = 'round';
  // The thumb sits where a real one would: body side on a hanging hand, top side on a held-out hand, inner side
  // on a raised hand. It slides across behind the palm as the arm lifts, so it never jumps.
  const th = -side * Math.max(-1, Math.min(1, (Math.cos(dir) - 0.35) * 3));
  const finger = (fx, fy, len, ang, r = 12.5) => { const tx = fx + Math.sin(ang) * len, ty = fy + Math.cos(ang) * len; x.strokeStyle = css(C.line); x.lineWidth = r * 2 + 6; x.beginPath(); x.moveTo(fx, fy); x.lineTo(tx, ty); x.stroke(); x.strokeStyle = css(C.armSkin); x.lineWidth = r * 2; x.beginPath(); x.moveTo(fx, fy); x.lineTo(tx, ty); x.stroke(); };
  const palm = (h = 66) => { x.beginPath(); x.roundRect(-40, -8, 80, h + 8, 30); x.fillStyle = css(C.line); x.save(); x.lineWidth = 6; x.strokeStyle = css(C.line); x.stroke(); x.restore(); x.fillStyle = css(C.armSkin); x.fill(); };
  const curled = () => { palm(62); x.strokeStyle = css(C.line); x.lineWidth = 3; for (const v of [-13, 7, 26]) { x.beginPath(); x.moveTo(v, 62); x.lineTo(v, 44); x.stroke(); } };
  if (kind === 'fist') { curled(); finger(th * 30, 18, 34, -th * 0.9, 12); }
  else if (kind === 'point') { finger(-th * 20, 54, 62, -th * 0.04); curled(); finger(th * 32, 22, 26, -th * 0.5, 12); }
  else if (kind === 'walk') { const q = Math.sin(phase * 12) * 11; finger(-12, 56, 44 + q, -0.06); finger(12, 56, 44 - q, 0.06); curled(); finger(th * 33, 20, 28, th * 0.7, 12); }
  else if (kind === 'pinch') { const q = -th * 18; finger(-th * 8, 54, 34, th * 0.35); finger(th * 36, 18, 44, -th * 0.42, 12); curled(); void q; x.fillStyle = css(C.line); }
  else {
    // open hands: spread and wiggle fan out, flat stays together
    const flat = kind === 'flat', fan = flat ? 0.05 : kind === 'open' ? 0.2 : 0.3, big = kind === 'spread' || kind === 'wiggle' ? 1.08 : 1;
    [[-29, 42], [-10, 52], [10, 54], [29, 44]].forEach(([v, l], i) => { const wig = kind === 'wiggle' ? Math.sin(phase * 16 + i * 1.8) * 8 : 0; finger(v, 56, l * big + wig, (i - 1.5) * fan); });
    finger(th * 30, 22, 42 * big, th * (flat ? 0.4 : 0.7), 13);   // rises from the palm's lower side, angled up, not out flat
    palm(62);
  }
  // the wrist flows into the arm with no line across it
  x.beginPath(); x.arc(0, 0, 29, 0, Math.PI * 2); x.fillStyle = css(C.armSkin); x.fill();
  x.restore();
}
function drawArm(ctx, box, sd, side, arm, rig, C) {
  const c = ctx.canvas; ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, c.width, c.height);
  ctx.setTransform(ARM_RES, 0, 0, ARM_RES, -box[0] * ARM_RES, -box[1] * ARM_RES);
  const { E, W } = arm, [r0, r1, r2] = rig.radius, P = sd.pivot;
  // upper arm, then the sleeve over it, then forearm and hand in front of everything
  limb(ctx, P, E, r0, r1, C);
  const sl = sleeveShape(P, E, rig.sleeve);
  ctx.fillStyle = css(C.armShade); capsule(ctx, sl.H, [sl.H[0] + sl.d[0] * 12, sl.H[1] + sl.d[1] * 12], r0, r0, 0);   // the shade a sleeve casts on the arm, as in her picture
  drawSleeve(ctx, sd, E, rig, C);
  limb(ctx, E, W, r1, r2, C);
  ctx.fillStyle = css(C.armSkin); capsule(ctx, [E[0], E[1] - 4], [E[0] + (W[0] - E[0]) * 0.12, E[1] - 4 + (W[1] - E[1]) * 0.12], r1 * 0.86, r1 * 0.82, 0);   // no line across the elbow
  const dir = Math.atan2(side * (W[0] - E[0]), W[1] - E[1]);
  drawHand(ctx, W, dir, side, arm.hand, arm.phase || 0, C);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
}

// Her skin without what the polygon covers (her drawn mouth, an eye): the hole is filled smoothly from the skin around it, so the patch matches
// her shading exactly. `grow` widens the hole so soft outlines go too. Returns a canvas the size of the face box, transparent outside the hole.
function cleanPlate(img, spec, poly, skin, grow = 0) {
  const [bx0, by0, bx1, by1] = spec.face.box, w = bx1 - bx0, h = by1 - by0, pts = poly.map(([x, y]) => [x - bx0, y - by0]);
  const src = canvasOf(w, h), s = src.getContext('2d', { willReadFrequently: true }); s.drawImage(img, -bx0, -by0);
  const m = canvasOf(w, h), mc = m.getContext('2d', { willReadFrequently: true }); polygon(mc, pts); mc.fill();
  if (grow) { mc.lineWidth = grow * 2; mc.lineJoin = 'round'; mc.stroke(); }
  const data = s.getImageData(0, 0, w, h), mask = mc.getImageData(0, 0, w, h).data, px = data.data, f = new Float32Array(px), inside = [];
  const isIn = (i) => mask[i * 4 + 3] > 0;
  // Only real skin may feed the patch: hair, lashes and the outline around it would smear in.
  const isSkin = (i) => px[i * 4 + 3] > 250 && Math.abs(px[i * 4] - skin[0]) + Math.abs(px[i * 4 + 1] - skin[1]) + Math.abs(px[i * 4 + 2] - skin[2]) < 70;
  const known = new Uint8Array(w * h);                                     // 0 = ignore, 1 = fixed skin, 2 = hole
  for (let i = 0; i < w * h; i++) { if (isIn(i)) { known[i] = 2; inside.push(i); } else if (isSkin(i)) known[i] = 1; }
  // Start from the skin straight above and below each hole pixel, then relax.
  for (const i of inside) {
    let up = i, dn = i; while (up >= w && known[up] === 2) up -= w; while (dn < w * (h - 1) && known[dn] === 2) dn += w;
    const row = (i - up) / w, span = (dn - up) / w || 1;
    for (let c = 0; c < 3; c++) { const A = known[up] === 1 ? f[up * 4 + c] : skin[c], B = known[dn] === 1 ? f[dn * 4 + c] : skin[c]; f[i * 4 + c] = A + (B - A) * (row / span); }
  }
  const NB = [-1, 1, -w, w];
  for (let it = 0; it < 300; it++) {
    for (const i of inside) {
      let n = 0, r = 0, g = 0, b = 0;
      for (const d of NB) { const j = i + d; if (known[j]) { n++; r += f[j * 4]; g += f[j * 4 + 1]; b += f[j * 4 + 2]; } }
      if (n) { f[i * 4] = r / n; f[i * 4 + 1] = g / n; f[i * 4 + 2] = b / n; }
    }
  }
  for (const i of inside) { for (let c = 0; c < 3; c++) px[i * 4 + c] = f[i * 4 + c]; px[i * 4 + 3] = 255; }
  s.putImageData(data, 0, 0);
  const out = canvasOf(w, h), o = out.getContext('2d'); o.filter = 'blur(1.5px)'; o.drawImage(m, 0, 0); o.filter = 'none';
  o.globalCompositeOperation = 'source-in'; o.drawImage(src, 0, 0);
  return out;
}

function sampleColours(img, spec) {
  const c = canvasOf(img.width, img.height), x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(img, 0, 0);
  const out = {};
  for (const [name, pts] of Object.entries(spec.samples)) {
    const sum = [0, 0, 0];
    for (const [px, py] of pts) { const d = x.getImageData(px, py, 1, 1).data; for (let k = 0; k < 3; k++) sum[k] += d[k]; }
    out[name] = sum.map((v) => Math.round(v / pts.length));
  }
  return out;
}

// ---- the face overlay: one canvas over her eyes and mouth, redrawn only when something changed
function drawMouth(x, spec, C, m, amount, plate, bx0, by0) {
  const [cx0, cy0] = spec.mouth.center, cx = cx0 - bx0, cy = cy0 - by0;
  x.save(); x.globalAlpha = amount; x.drawImage(plate, 0, 0);
  const hw = spec.mouth.halfWidth * m.w, o = m.o * 1.12, r = m.r;   // bigger than life, so a child can read her mouth
  const lift = 3 * (1 - r), sag = (19 - o * 8) * (1 - r) - o * 30 * r, depth = sag + 8 + o * 62;      // corners keep her smile; round mouths arch instead
  const skew = 10 * (1 - r);                                                                           // her drawn mouth hangs a little to one side
  const upper = (ctx) => { ctx.moveTo(cx - hw, cy - lift); ctx.bezierCurveTo(cx - hw * 0.5, cy + sag * 1.25, cx + hw * 0.5, cy + sag * 1.25, cx + hw, cy - lift); };
  const lowerBack = (ctx, extra = 0) => ctx.bezierCurveTo(cx + hw * (0.62 + r * 0.42) + skew, cy + depth * 1.28 + extra, cx - hw * (0.62 + r * 0.42) + skew, cy + depth * 1.28 + extra, cx - hw, cy - lift);
  x.lineJoin = 'round'; x.lineCap = 'round';
  if (o < 0.03) {                                                                                       // closed: her smile as a single line
    x.strokeStyle = css(C.line); x.lineWidth = 5.5; x.beginPath(); upper(x); x.stroke();
    x.restore(); return;
  }
  x.save(); x.beginPath(); upper(x); lowerBack(x); x.closePath(); x.clip();
  x.fillStyle = css(C.inside); x.fillRect(0, 0, x.canvas.width, x.canvas.height);
  if (o > 0.2) { x.fillStyle = css(C.lip); x.beginPath(); x.ellipse(cx + skew * 0.8 - 8, cy + depth * 1.02, hw * 0.62, Math.max(7, depth * 0.36), 0, 0, Math.PI * 2); x.fill(); }   // tongue
  if (m.teeth > 0.02) {
    x.save(); x.fillStyle = css(C.teeth);                                                              // solid white; fewer teeth show less, never grey ones
    const th = Math.min(depth, (9 + o * 18 + m.ff * 14) * Math.min(1, m.teeth * 1.2));
    x.beginPath(); upper(x); x.lineTo(cx + hw, cy - lift + th * 0.7); x.bezierCurveTo(cx + hw * 0.5, cy + sag * 1.25 + th, cx - hw * 0.5, cy + sag * 1.25 + th, cx - hw, cy - lift + th * 0.7); x.closePath(); x.fill(); x.restore();
  }
  if (m.ff > 0.05) { x.save(); x.globalAlpha = amount * m.ff; x.fillStyle = css(C.lip); x.fillRect(cx - hw, cy + depth * 0.5, hw * 2, depth); x.restore(); }  // FF: lower lip under the top teeth
  x.restore();
  x.strokeStyle = css(C.line); x.lineWidth = 4.2; x.beginPath(); upper(x); lowerBack(x); x.closePath(); x.stroke();
  x.restore();
}

function drawLid(x, eye, C, w, plate, bx0, by0) {
  const [a, b] = eye.corners.map(([p, q]) => [p - bx0, q - by0]), ys = eye.contour.map((p) => p[1] - by0), top = Math.min(...ys), bottom = Math.max(...ys);
  // The lid's edge sweeps from above the eye down to a soft closed curve along the lower lid; above the edge, her clean skin.
  const midClosed = bottom + 1, midOpen = top - 40, mid = midOpen + (midClosed - midOpen) * w, cy = 2 * mid - (a[1] + b[1]) / 2, mx = (a[0] + b[0]) / 2;
  x.save(); x.beginPath(); x.moveTo(-1, -1); x.lineTo(x.canvas.width + 1, -1); x.lineTo(x.canvas.width + 1, b[1]); x.lineTo(b[0], b[1]); x.quadraticCurveTo(mx, cy, a[0], a[1]); x.lineTo(-1, a[1]); x.closePath(); x.clip();
  x.drawImage(plate, 0, 0); x.restore();
  x.save(); x.strokeStyle = css(C.lash); x.lineWidth = 7; x.lineCap = 'round'; x.beginPath(); x.moveTo(a[0], a[1]); x.quadraticCurveTo(mx, cy, b[0], b[1]); x.stroke(); x.restore();
  if (w > 0.7) {                                                                                         // closed: her lashes flick out from the outer corner
    const [ox, oy] = eye.lashSide < 0 ? a : b, s = eye.lashSide;
    x.save(); x.globalAlpha = (w - 0.7) / 0.3; x.strokeStyle = css(C.lash); x.lineWidth = 5; x.lineCap = 'round';
    for (const [dx, dy] of [[26, -2], [24, 12], [15, 22]]) { x.beginPath(); x.moveTo(ox - s * 8, oy); x.quadraticCurveTo(ox + s * dx * 0.5, oy + dy * 0.2, ox + s * dx, oy + dy); x.stroke(); }
    x.restore();
  }
}

export async function loadPuppet2D(name) {
  const spec = await (await fetch(`/puppet/${name}/spec.json`)).json();
  const img = new Image(); img.src = `/puppet/${name}/${spec.image}`; await img.decode();
  const k = spec.height.m / spec.height.rows, ax = spec.anchorX * k, hipY = spec.hipRow * k, base = (spec.height.rows - spec.hipRow) * k, A = spec.arms;
  const colours = sampleColours(img, spec);
  const { body, head } = buildLayers(img, spec, colours);
  const [bx0, by0, bx1, by1] = spec.face.box, faceCanvas = canvasOf(bx1 - bx0, by1 - by0);
  const root = new THREE.Group(), figure = new THREE.Group(), bodyG = new THREE.Group(), headG = new THREE.Group();
  root.add(figure); figure.add(bodyG); bodyG.position.y = base; bodyG.add(headG);
  const place = (m, parentX, parentY, z = 0) => { m.position.set(m.userData.origin[0] + parentX, m.userData.origin[1] + parentY, z); };
  // Soft shadow on the floor under her feet.
  const sc = canvasOf(256, 64), sx = sc.getContext('2d'), sg = sx.createRadialGradient(128, 32, 0, 128, 32, 128); sg.addColorStop(0, 'rgba(0,0,0,.34)'); sg.addColorStop(1, 'rgba(0,0,0,0)'); sx.setTransform(1, 0, 0, 0.25, 0, 24); sx.fillStyle = sg; sx.fillRect(0, 0, 256, 256);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(0.72, 0.3), new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(sc), transparent: true, depthWrite: false, toneMapped: false, fog: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.set(0, 0.006, 0.04); shadow.renderOrder = 19; root.add(shadow);
  // Legs stand on the floor and hang from the hips.
  const legs = [-1, 1].map((sd) => {
    const c = legCanvas(spec, sd, colours), top = spec.legs.hipBottom - 70, g = new THREE.Group(), hipX = sd * 130 * k;
    g.position.set(hipX, (spec.height.rows - top) * k, 0); g.userData = { hipX, len: (spec.height.rows - top) * k }; figure.add(g);
    const m = plane(c, 0, 0, spec, k, 20), w = c.width * k;
    m.position.set((sd < 0 ? -w / 2 : w / 2) - hipX, -c.height * k / 2, -0.002); g.add(m);
    return g;
  });
  const bodyM = plane(body, 0, 0, spec, k, 21); place(bodyM, -ax, hipY); bodyG.add(bodyM);
  // Arms: one canvas per side, redrawn when the pose changes, passing in front of her head and face as signs need. Each has its sleeve, grown from the shoulder cap.
  const arms = [['l', -1, A.left], ['r', 1, A.right]].map(([key, sd, S]) => {
    const size = ARM_REACH * 2, c = canvasOf(Math.round(size * ARM_RES), Math.round(size * ARM_RES)), box = [S.pivot[0] - ARM_REACH, S.pivot[1] - ARM_REACH];
    const m = plane(c, box[0], box[1], spec, k, 24, ARM_RES); place(m, -ax, hipY, 0.0005); m.userData.tex.generateMipmaps = false; m.userData.tex.minFilter = THREE.LinearFilter; bodyG.add(m);
    return { key, sd, S, ctx: c.getContext('2d', { willReadFrequently: false }), box, tex: m.userData.tex, drawn: '' };
  });
  const [pvx, pvy] = spec.head.pivot, pX = pvx * k - ax, pY = hipY - pvy * k;
  headG.position.set(pX, pY, 0.002);
  const headM = headPlane(head, spec, k, 22); place(headM, -ax - pX, hipY - pY); headG.add(headM);
  const faceM = plane(faceCanvas, bx0, by0, spec, k, 23); place(faceM, -ax - pX, hipY - pY, 0.001); headG.add(faceM);
  root.userData = { puppet2d: true, spec, k, base, headM, figure, shadow, legs, arms, bodyG, headG, pX, pY, seed: 3, face: { canvas: faceCanvas, ctx: faceCanvas.getContext('2d'), tex: faceM.userData.tex, plate: cleanPlate(img, spec, spec.mouth.mask, colours.lid), eyePlates: spec.eyes.map((e) => cleanPlate(img, spec, e.contour, colours.lid, 7)), colours, key: '' } };
  return root;
}

export function posePuppet2D(host, t, s, plan) {
  const U = host.userData, weights = visemeWeights(plan.visemeTrack, t), amount = speakingAmount(plan.lines, t), m = mouthShape(weights);
  const talk = Math.min(1, Object.values(weights).reduce((a, b) => a + b, 0)), P = puppetMotion(s, t, talk);
  const PF = performance(plan.lines, t, s.emotion), bodyScale = 1 + PF.leanIn * 0.04, headScale = 1 + PF.leanIn * 0.08;
  U.figure.position.y = P.hop; U.shadow.scale.setScalar(1 - Math.min(0.45, P.hop * 3));
  U.bodyG.position.set(P.lean - PF.tilt * 0.09, U.base, 0); U.bodyG.rotation.z = P.tilt + PF.tilt * 0.3; U.bodyG.scale.set(bodyScale, bodyScale * (1 + P.squash + PF.nod * 0.008 + PF.pulse * 0.005), 1);
  U.legs.forEach((g, i) => {           // the hips carry the legs when she leans; the feet stay where they are
    const hipShift = P.lean - PF.tilt * 0.09;
    g.position.x = g.userData.hipX + hipShift; g.rotation.z = (i ? 1 : -1) * P.spread * 0.16 - Math.asin(Math.max(-0.5, Math.min(0.5, hipShift / g.userData.len)));
  });
  const nod = P.nod + PF.nod;
  U.headG.rotation.z = P.headTilt + PF.tilt; U.headG.position.y = U.pY - nod * 0.016; U.headG.scale.set(headScale, headScale * (1 - Math.max(0, nod) * 0.022 + Math.max(0, -nod) * 0.01), 1);
  const HU = U.headM.material.uniforms; HU.uSwing.value = ponySwing(plan.lines, t, P.hop); HU.uBrow.value = PF.brow * U.spec.warp.browLift;
  // Arms.
  const pose = withSign(U.spec.arms, armPose(U.spec.arms, s, t, amount), signAt(plan.signs, t));
  for (const key of ['l', 'r']) { const J = pose[key], sgn = key === 'l' ? 1 : -1, lift = PF.pulse * 11, sway = PF.under * 9 * sgn; J.W = [J.W[0] + sway, J.W[1] + lift]; J.E = [J.E[0] + sway * 0.35, J.E[1] + lift * 0.4]; }   // the hands keep the pulse too
  if (pose.body.nod) U.headG.position.y -= pose.body.nod * 0.012;
  if (pose.body.shake) U.headG.rotation.z += pose.body.shake;
  for (const A of U.arms) {
    const arm = pose[A.key], key = `${arm.E[0].toFixed(1)},${arm.E[1].toFixed(1)},${arm.W[0].toFixed(1)},${arm.W[1].toFixed(1)},${arm.hand},${(arm.phase || 0).toFixed(2)}`;
    if (key !== A.drawn) { A.drawn = key; drawArm(A.ctx, A.box, A.S, A.sd, arm, U.spec.arms, U.face.colours); A.tex.needsUpdate = true; }
  }
  // Face overlay.
  const blink = Math.min(1, blinkAt(t, U.seed) * 1.25), F = U.face, wink = PF.wink ? PF.wink.w : 0, winkEye = PF.wink ? PF.wink.eye : -1;
  if (pose.body.bigO) { const O = pose.body.bigO; m.o += (1.25 - m.o) * O; m.w += (0.74 - m.w) * O; m.r += (1 - m.r) * O; m.teeth *= 1 - O; }
  const key = [amount, m.o, m.w, m.r, m.teeth, m.ff, blink, wink].map((v) => v.toFixed(2)).join();
  if (key === F.key) return;
  F.key = key; const x = F.ctx, [bx0, by0] = U.spec.face.box;
  x.clearRect(0, 0, F.canvas.width, F.canvas.height);
  if (amount > 0.005 || pose.body.bigO) drawMouth(x, U.spec, F.colours, m, Math.max(amount, pose.body.bigO || 0), F.plate, bx0, by0);
  U.spec.eyes.forEach((eye, i) => { const w = Math.max(blink, i === winkEye ? wink : 0); if (w > 0.01) drawLid(x, eye, F.colours, w, F.eyePlates[i], bx0, by0); });
  F.tex.needsUpdate = true;
}
