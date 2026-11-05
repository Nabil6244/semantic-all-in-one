// Filled, shaded rooms for the colour looks (navy cartoon, bright interiors, underwater), like the plane / cinema / mall / store / school / aquarium
// references: one-point perspective, flat colour with a darker side wall, floor lines toward the vanishing point, soft light pools.
// The white-on-black looks keep the line-art sets in rhkit.drawSet. Same set names and ground lines, so figures stand where they did before.
// Colours are written once as daylight values; tone() pushes them to the palette's time of day (night navy, deep teal, warm, red, dawn).

const TAU = Math.PI * 2;
const lerp = (a, b, k) => a + (b - a) * k;
const hash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const rgb = (h) => { const s = h.replace('#', ''), v = parseInt(s.length === 3 ? s.split('').map((c) => c + c).join('') : s, 16); return [(v >> 16) & 255, (v >> 8) & 255, v & 255]; };
const hex = (c) => '#' + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
export const mix = (a, b, k) => { const A = rgb(a), B = rgb(b); return hex(A.map((v, i) => lerp(v, B[i], k))); };
export const shade = (a, k) => (k < 0 ? mix(a, '#000000', -k) : mix(a, '#ffffff', k));
const lum = (a) => { const [r, g, b] = rgb(a); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };

export const ROOM_NAMES = ['bedroom', 'hallway', 'house_section', 'yard', 'door', 'window', 'classroom', 'stairs', 'hall_lit', 'street', 'cutaway', 'cabin', 'store', 'bathroom', 'kitchen', 'hall_mirror'];
const GROUND = { bedroom: 0.80, hallway: 0.80, house_section: 0.84, yard: 0.80, door: 0.88, window: 0.88, classroom: 0.82, stairs: 0.84, hall_lit: 0.80, street: 0.80, cutaway: 0.84, cabin: 0.90, store: 0.90, bathroom: 0.84, kitchen: 0.84, hall_mirror: 0.80 };

/** The palette's time of day: day palettes keep daylight colours; dark ones darken toward their own night colour. */
export function toner(pal) {
  const day = lum(pal.bg1) > 0.55;
  return { day, tone: day ? (c) => mix(c, pal.wall, 0.1) : (c) => mix(shade(c, -0.45), pal.bg1, 0.55), glow: pal.glow || '#ffd27a' };
}

export function drawRoom(g, name, W, H, t, pal) {
  const nm = ROOM_NAMES.includes(name) ? name : 'yard', { day, tone: T, glow } = toner(pal);
  const X = (x) => x * W, Y = (y) => y * H;
  const poly = (pts, fill, stroke = null, lw = 0) => { g.beginPath(); g.moveTo(X(pts[0][0]), Y(pts[0][1])); for (const p of pts.slice(1)) g.lineTo(X(p[0]), Y(p[1])); g.closePath(); g.fillStyle = fill; g.fill(); if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw || Math.max(1, H * 0.0025); g.stroke(); } };
  const rect = (x, y, w, h, fill, stroke = null) => poly([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], fill, stroke);
  const ink = T('#2b2f3a');
  const pool = (x, y, rx, ry, colour, a) => { g.save(); g.translate(X(x), Y(y)); g.scale(1, ry / rx); const r = g.createRadialGradient(0, 0, 0, 0, 0, X(rx)); r.addColorStop(0, colour.replace(')', `,${a})`).replace('rgb', 'rgba')); r.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = r; g.beginPath(); g.arc(0, 0, X(rx), 0, TAU); g.fill(); g.restore(); };
  const glowRGB = `rgb(${rgb(day ? '#fff6e0' : glow).join(',')})`;
  g.save(); g.lineJoin = 'round'; g.lineCap = 'round';

  // ------------------------------------------------------------ a perspective box room: back wall B, side walls, floor, ceiling
  const room = (B, c) => {
    const [x0, y0, x1, y1] = B;
    poly([[0, 0], [1, 0], [x1, y0], [x0, y0]], T(c.ceil));
    poly([[0, 0], [x0, y0], [x0, y1], [0, 1]], T(shade(c.side, -0.12)));
    poly([[1, 0], [x1, y0], [x1, y1], [1, 1]], T(shade(c.side, -0.2)));
    poly([[0, 1], [x0, y1], [x1, y1], [1, 1]], T(c.floor));
    rect(x0, y0, x1 - x0, y1 - y0, T(c.back));
    if (c.trim) { poly([[0, 1 - 0.0], [x0, y1], [x0, y1 - (y1 - y0) * 0.32], [0, 1 - 0.32]], T(c.trim)); poly([[1, 1], [x1, y1], [x1, y1 - (y1 - y0) * 0.32], [1, 1 - 0.32]], T(shade(c.trim, -0.1))); rect(x0, y1 - (y1 - y0) * 0.32, x1 - x0, (y1 - y0) * 0.32, T(c.trim)); }
    g.strokeStyle = T(shade(c.floor, -0.18)); g.lineWidth = Math.max(1, H * 0.0022);
    const vx = (x0 + x1) / 2;
    if (c.lines !== 'none') for (let i = 1; i < 10; i++) { const u = i / 10; g.beginPath(); g.moveTo(X(u), Y(1)); g.lineTo(X(lerp(x0, x1, u)), Y(y1)); g.stroke(); }
    if (c.lines === 'tile') for (let i = 1; i < 7; i++) { const k = 1 - Math.pow(1 - i / 7, 1.8); const y = lerp(1, y1, k), xa = lerp(0, x0, k), xb = lerp(1, x1, k); g.beginPath(); g.moveTo(X(xa), Y(y)); g.lineTo(X(xb), Y(y)); g.stroke(); }
    for (const [a, b] of [[[0, 0], [x0, y0]], [[1, 0], [x1, y0]], [[0, 1], [x0, y1]], [[1, 1], [x1, y1]]]) { g.strokeStyle = T(shade(c.side, -0.3)); g.beginPath(); g.moveTo(X(a[0]), Y(a[1])); g.lineTo(X(b[0]), Y(b[1])); g.stroke(); }
    if (c.lights) for (let i = 0; i < c.lights; i++) { const k = (i + 0.5) / c.lights * 0.85, y = lerp(0, y0, k), xa = lerp(0.3, vx - 0.02, k), xb = lerp(0.7, vx + 0.02, k);
      poly([[xa, y], [xb, y], [xb - 0.004, y + 0.012 * (1 - k)], [xa + 0.004, y + 0.012 * (1 - k)]], day ? '#fbfaf3' : glow); pool(vx, lerp(1, y1, k * 0.9), 0.22 * (1 - k * 0.6), 0.06 * (1 - k * 0.6), glowRGB, day ? 0.25 : 0.35); }
    return B;
  };
  // points and boxes on the floor: u across (0 left .. 1 right), k depth (0 front .. 1 back wall)
  const fp = (B, u, k) => [lerp(lerp(0, B[0], k), lerp(1, B[2], k), u), lerp(1, B[3], k)];
  const fbox = (B, u, k, w, h, d, front, top) => {
    const s = lerp(1, B[2] - B[0], k), [x, y] = fp(B, u, k), hw = w * s / 2, hh = h * s * (W / H), dd = d * s * 0.5;
    const vx = (B[0] + B[2]) / 2, vy = B[3] - (B[3] - B[1]) * 0.45, kx = (vx - x) * 0.18 * dd * 6, ky = (vy - y) * 0.18 * dd * 6;
    poly([[x - hw, y - hh], [x + hw, y - hh], [x + hw + kx, y - hh + ky], [x - hw + kx, y - hh + ky]], T(top));
    const sx = x < vx ? x + hw : x - hw; poly([[sx, y], [sx, y - hh], [sx + kx, y - hh + ky], [sx + kx, y + ky]], T(shade(front, -0.25)));
    rect(x - hw, y - hh, hw * 2, hh, T(front));
    return { x, y, hw, hh };
  };
  // a quad on a side wall from depth k0 to k1, v0..v1 up the wall (0 floor, 1 ceiling)
  const wq = (B, side, k0, k1, v0, v1, fill, stroke = null) => {
    const P = (k, v) => { const xw = side < 0 ? lerp(0, B[0], k) : lerp(1, B[2], k), yb = lerp(1, B[3], k), yt = lerp(0, B[1], k); return [xw, lerp(yb, yt, v)]; };
    poly([P(k0, v0), P(k1, v0), P(k1, v1), P(k0, v1)], fill, stroke);
  };
  const nightSky = (y1) => { const gr = g.createLinearGradient(0, 0, 0, Y(y1)); gr.addColorStop(0, day ? '#8fb4d9' : mix(pal.bg0, '#000000', 0.3)); gr.addColorStop(1, day ? '#dbe7ef' : pal.bg1); g.fillStyle = gr; g.fillRect(0, 0, W, Y(y1));
    if (!day) { g.fillStyle = 'rgba(255,255,255,0.7)'; for (let i = 0; i < 40; i++) g.fillRect(X(hash(i)), Y(hash(i + 50) * y1 * 0.8), Math.max(1, H * 0.002), Math.max(1, H * 0.002)); g.fillStyle = '#f1ead2'; g.beginPath(); g.arc(X(0.85), Y(0.13), Y(0.04), 0, TAU); g.fill(); } };
  const winPane = (x, y, w, h) => { rect(x - 0.008, y - 0.012, w + 0.016, h + 0.024, T('#f2efe6')); const gr = g.createLinearGradient(0, Y(y), 0, Y(y + h)); gr.addColorStop(0, day ? '#a9cbe6' : '#0b1430'); gr.addColorStop(1, day ? '#e3eef5' : '#1d2b52'); g.fillStyle = gr; g.fillRect(X(x), Y(y), X(w), Y(h));
    if (!day) { g.fillStyle = '#e8e2c8'; g.beginPath(); g.arc(X(x + w * 0.72), Y(y + h * 0.28), Y(Math.min(w * 0.9, h) * 0.13), 0, TAU); g.fill(); }
    g.fillStyle = T('#f2efe6'); g.fillRect(X(x + w / 2) - Y(0.004), Y(y), Y(0.008), Y(h)); g.fillRect(X(x), Y(y + h / 2) - Y(0.004), X(w), Y(0.008)); };
  const door = (x, y, w, h, colour, open = false) => { rect(x - 0.006, y - 0.01, w + 0.012, h + 0.01, T('#efe9dc')); rect(x, y, w, h, open ? '#0a0c10' : T(colour)); if (!open) { rect(x + w * 0.12, y + h * 0.08, w * 0.76, h * 0.36, T(shade(colour, -0.08))); rect(x + w * 0.12, y + h * 0.52, w * 0.76, h * 0.4, T(shade(colour, -0.08))); g.fillStyle = T('#c9a13a'); g.beginPath(); g.arc(X(x + w * 0.85), Y(y + h * 0.55), Y(0.008), 0, TAU); g.fill(); } };
  const lampPool = (x, y, r) => pool(x, y, r, r * 0.8, glowRGB, day ? 0.18 : 0.45);

  if (nm === 'classroom') {
    const B = room([0.2, 0.12, 0.8, 0.56], { ceil: '#efece4', side: '#e9e1cc', back: '#efe8d4', floor: '#d9cfb8', trim: '#3f8f8a', lights: 3, lines: 'tile' });
    rect(0.3, 0.2, 0.4, 0.16, T('#f7f7f4'), T('#9aa0a8')); rect(0.3, 0.36, 0.4, 0.012, T('#9aa0a8'));
    g.fillStyle = T('#e5e5e0'); g.beginPath(); g.arc(X(0.75), Y(0.21), Y(0.03), 0, TAU); g.fill(); g.strokeStyle = ink; g.lineWidth = Math.max(1, H * 0.003); g.stroke();
    g.beginPath(); g.moveTo(X(0.75), Y(0.21)); g.lineTo(X(0.75), Y(0.19)); g.moveTo(X(0.75), Y(0.21)); g.lineTo(X(0.762), Y(0.214)); g.stroke();
    rect(0.215, 0.2, 0.07, 0.14, T('#b8834f')); for (let i = 0; i < 6; i++) rect(0.222 + (i % 3) * 0.021, 0.21 + Math.floor(i / 3) * 0.06, 0.016, 0.045, T(['#e86a5a', '#f2c94c', '#5b9bd5', '#7dc47d', '#f2a65a', '#c78ad9'][i]));
    for (const k of [0.12, 0.42, 0.7]) wq(B, -1, k, k + 0.18, 0.42, 0.85, day ? '#bcd9ee' : '#16224a', T('#f2efe6'));
    for (const k of [0.55, 0.35]) for (const u of [0.18, 0.4, 0.62, 0.84]) { const d = fbox(B, u, k, 0.14, 0.03, 0.1, '#9a7350', '#c99a6b'); rect((d.x - d.hw * 0.08) / W, (d.y) / H, d.hw * 0.16 / W, d.hh * 1.6 / H, T('#6c7480')); }
  } else if (nm === 'store') {
    const B = room([0.36, 0.2, 0.64, 0.58], { ceil: '#f1f1ee', side: '#eef0f2', back: '#dfe5ec', floor: '#e7e4dc', lights: 4, lines: 'tile' });
    const goods = ['#e85d4a', '#f2c94c', '#4a90d9', '#5fb36b', '#f29b4a', '#9b6bd1', '#ffffff', '#3cc0c0'];
    for (const side of [-1, 1]) { wq(B, side, 0.0, 0.98, 0.0, 0.78, T('#cfd6de')); for (let r = 0; r < 4; r++) { const v0 = 0.06 + r * 0.18; wq(B, side, 0.0, 0.98, v0, v0 + 0.015, T('#8b96a3'));
      for (let i = 0; i < 16; i++) { const k0 = i / 16 * 0.97, k1 = k0 + 0.05; wq(B, side, k0, k1, v0 + 0.02, v0 + 0.13, T(goods[Math.floor(hash(i * 7 + r * 3 + side) * goods.length)])); } } }
    rect(0.42, 0.34, 0.16, 0.24, T('#9aa3ad')); rect(0.425, 0.35, 0.073, 0.23, T('#c3cad2')); rect(0.502, 0.35, 0.073, 0.23, T('#c3cad2'));
    rect(0.43, 0.27, 0.14, 0.045, T('#2f6fbf')); g.fillStyle = '#fff'; g.font = `800 ${Math.round(H * 0.022)}px sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('RECEIVING', X(0.5), Y(0.293));
    for (const [x, n] of [[0.22, '4'], [0.78, '5']]) { rect(x - 0.035, 0.06, 0.07, 0.07, T('#2f6fbf')); g.fillStyle = '#fff'; g.font = `900 ${Math.round(H * 0.045)}px sans-serif`; g.fillText(n, X(x), Y(0.097)); }
  } else if (nm === 'cabin') {
    const B = room([0.38, 0.26, 0.62, 0.6], { ceil: '#e6e8ee', side: '#d9dde6', back: '#cfd5e0', floor: '#3a4a7a', lights: 0, lines: 'none' });
    for (const side of [-1, 1]) { wq(B, side, 0, 1, 0.68, 0.95, T('#eef0f5'), T('#b5bbc8')); for (let i = 0; i < 6; i++) { const k = i / 6 + 0.04; wq(B, side, k, k + 0.06, 0.45, 0.6, day ? '#9cc3e6' : '#0b1430'); } }
    g.strokeStyle = day ? '#ffffff' : '#7aa0ff'; g.lineWidth = Math.max(2, H * 0.004); for (const s of [-1, 1]) { g.beginPath(); g.moveTo(X(s < 0 ? 0.08 : 0.92), 0); g.lineTo(X(s < 0 ? 0.39 : 0.61), Y(0.265)); g.stroke(); }
    for (let r = 5; r >= 0; r--) { const k = 0.08 + r * 0.15, s = lerp(1, B[2] - B[0], k); for (const u of [0.07, 0.21, 0.79, 0.93]) {      // seat backs: rounded, a white headrest cover, an armrest
      const [x, y] = fp(B, u, k), w = 0.12 * s, h = 0.3 * s, rr = Math.min(X(w), Y(h)) * 0.28; g.fillStyle = T('#2b4a94'); g.strokeStyle = T('#1c2f63'); g.lineWidth = Math.max(1, H * 0.002);
      g.beginPath(); g.roundRect(X(x - w / 2), Y(y - h), X(w), Y(h), [rr, rr, rr * 0.3, rr * 0.3]); g.fill(); g.stroke();
      g.fillStyle = T('#3a5cad'); g.beginPath(); g.roundRect(X(x - w * 0.38), Y(y - h * 0.9), X(w * 0.76), Y(h * 0.55), rr * 0.6); g.fill();
      g.fillStyle = T('#eef1f7'); g.beginPath(); g.roundRect(X(x - w * 0.34), Y(y - h * 0.97), X(w * 0.68), Y(h * 0.16), rr * 0.4); g.fill();
      rect(x + (u < 0.5 ? w / 2 : -w / 2 - 0.012 * s), y - h * 0.35, 0.012 * s, h * 0.06, T('#5b6478')); } }
    rect(0.47, 0.32, 0.06, 0.28, T('#9aa3b5'));
  } else if (nm === 'hallway' || nm === 'hall_lit' || nm === 'hall_mirror') {
    const B = nm === 'hall_mirror' ? [0.41, 0.31, 0.59, 0.66] : [0.42, 0.3, 0.58, 0.62];
    room(B, { ceil: '#ece9e1', side: '#dcd4c2', back: '#d4cbb6', floor: '#b79a76', trim: '#7d5a3c', lights: 3, lines: 'plank' });
    for (const side of [-1, 1]) for (const k of [0.15, 0.48, 0.74]) wq(B, side, k, k + 0.12 * (1 - k * 0.5), 0.0, 0.62, T('#8a6a4a'), T('#efe9dc'));
    if (nm === 'hall_lit') { rect(B[0] + 0.03, B[1] + 0.06, B[2] - B[0] - 0.06, B[3] - B[1] - 0.06, '#fff2c4'); pool(0.5, 0.75, 0.25, 0.08, glowRGB, 0.5); }
    else if (nm === 'hallway') door(B[0] + 0.035, B[1] + 0.06, B[2] - B[0] - 0.07, B[3] - B[1] - 0.06, '#8a6a4a');
    rect(0.48, B[1] - 0.045, 0.04, 0.025, '#2e9e55'); g.fillStyle = '#fff'; g.font = `800 ${Math.round(H * 0.014)}px sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText('EXIT', X(0.5), Y(B[1] - 0.032));
  } else if (nm === 'bedroom') {
    const B = room([0.12, 0.14, 0.88, 0.62], { ceil: '#e6e0d6', side: '#c9b8d6', back: '#d8c9e3', floor: '#9c7b5c', lights: 0, lines: 'plank' });
    winPane(0.58, 0.24, 0.16, 0.22); rect(0.56, 0.22, 0.03, 0.29, T('#7b6aa3')); rect(0.73, 0.22, 0.03, 0.29, T('#7b6aa3'));
    fbox(B, 0.24, 0.45, 0.38, 0.08, 0.3, '#5b6fa8', '#e8e6f0'); rect(0.12, 0.5, 0.04, 0.2, T('#7d5a3c'));
    const n = fbox(B, 0.5, 0.42, 0.08, 0.1, 0.06, '#7d5a3c', '#9a7350'); rect(0.485, 0.53, 0.03, 0.04, T('#f2e2b0')); lampPool(0.5, 0.56, 0.12);
    rect(0.82, 0.3, 0.1, 0.5, T('#8a6a4a')); poly([[0.15, 0.95], [0.5, 0.95], [0.46, 0.84], [0.2, 0.84]], T('#7b4a5a')); void n;
  } else if (nm === 'kitchen') {
    room([0.06, 0.1, 0.94, 0.66], { ceil: '#efe8da', side: '#efdcb8', back: '#f2e3c4', floor: '#d8d2c4', lights: 0, lines: 'tile' });
    rect(0.08, 0.46, 0.52, 0.2, T('#6f8f7a')); rect(0.07, 0.44, 0.54, 0.03, T('#e8e2d6')); for (let i = 0; i < 4; i++) rect(0.09 + i * 0.128, 0.48, 0.115, 0.16, T('#7fa08a'));
    rect(0.08, 0.14, 0.24, 0.18, T('#7fa08a')); winPane(0.36, 0.17, 0.18, 0.2); rect(0.66, 0.16, 0.14, 0.5, T('#e6e8ea'), T('#b8bcc0')); rect(0.66, 0.36, 0.14, 0.006, T('#b8bcc0'));
    g.strokeStyle = ink; g.lineWidth = Math.max(1, H * 0.002); g.beginPath(); g.moveTo(X(0.5), 0); g.lineTo(X(0.5), Y(0.08)); g.stroke(); poly([[0.47, 0.11], [0.53, 0.11], [0.515, 0.08], [0.485, 0.08]], T('#c0392b')); lampPool(0.5, 0.2, 0.18);
  } else if (nm === 'bathroom') {
    room([0.04, 0.06, 0.96, 0.68], { ceil: '#eef2f2', side: '#cfe3e6', back: '#d9ecee', floor: '#b9c9cc', lights: 0, lines: 'tile' });
    g.strokeStyle = T('#b7d0d4'); g.lineWidth = Math.max(1, H * 0.0018); for (let i = 1; i < 14; i++) { g.beginPath(); g.moveTo(X(0.04 + i * 0.066), Y(0.06)); g.lineTo(X(0.04 + i * 0.066), Y(0.68)); g.stroke(); }
    for (let j = 1; j < 9; j++) { g.beginPath(); g.moveTo(X(0.04), Y(0.06 + j * 0.07)); g.lineTo(X(0.96), Y(0.06 + j * 0.07)); g.stroke(); }
    rect(0.57, 0.56, 0.32, 0.04, T('#f2f2f0')); rect(0.6, 0.6, 0.26, 0.16, T('#e6e6e2')); rect(0.69, 0.53, 0.02, 0.04, T('#a8b0b8'));
    rect(0.06, 0.6, 0.3, 0.16, T('#f4f4f2'), T('#c8cdd0')); rect(0.4, 0.2, 0.1, 0.48, T('#8aa3b0'));
  } else if (nm === 'door' || nm === 'window') {
    const gy = GROUND[nm]; rect(0, 0, 1, gy, T('#d8cfbf')); rect(0, gy - 0.12, 1, 0.12, T('#8a6a4a')); rect(0, gy, 1, 1 - gy, T('#6e5440'));
    if (nm === 'door') { door(0.46, 0.2, 0.22, gy - 0.2, '#8a6a4a'); rect(0.46, gy - 0.008, 0.22, 0.008, day ? '#fff6d8' : glow); lampPool(0.57, gy, 0.14); }
    else { winPane(0.36, 0.16, 0.28, 0.42); rect(0.33, 0.13, 0.05, 0.5, T('#7b6aa3')); rect(0.62, 0.13, 0.05, 0.5, T('#7b6aa3')); rect(0.34, 0.59, 0.32, 0.025, T('#f2efe6')); }
  } else if (nm === 'stairs') {
    const gy = GROUND.stairs; rect(0, 0, 1, gy, T('#d9d2c4')); rect(0, gy, 1, 1 - gy, T('#8f735a'));
    const n = 9; for (let i = 0; i < n; i++) { const x = 0.16 + i * 0.06, y = gy - (i + 1) * 0.065; rect(x, y, 0.62 - i * 0.06 + 0.06, 0.065, T(i % 2 ? '#a3825f' : '#b08e69')); rect(x, y, 0.06, 0.012, T('#c9a77f')); }
    g.strokeStyle = T('#5a4330'); g.lineWidth = Math.max(2, H * 0.006); g.beginPath(); g.moveTo(X(0.16), Y(gy - 0.18)); g.lineTo(X(0.7), Y(gy - 0.18 - 9 * 0.065)); g.stroke();
    for (let i = 0; i < n; i += 2) { const x = 0.19 + i * 0.06; g.beginPath(); g.moveTo(X(x), Y(gy - (i + 1) * 0.065)); g.lineTo(X(x), Y(gy - 0.18 - i * 0.065 - 0.03)); g.stroke(); }
    door(0.8, 0.12, 0.1, gy - 0.12 - 0.585 + 0.4, '#8a6a4a');
  } else if (nm === 'yard' || nm === 'street') {
    const gy = GROUND[nm]; nightSky(gy - 0.12);
    g.fillStyle = T('#203a2a'); g.beginPath(); g.moveTo(0, Y(gy - 0.1)); for (let i = 0; i <= 20; i++) g.lineTo(X(i / 20), Y(gy - 0.12 - 0.05 * hash(i + 4))); g.lineTo(W, Y(gy)); g.lineTo(0, Y(gy)); g.fill();
    if (nm === 'yard') {
      rect(0, gy - 0.12, 1, 1, T('#4f7a45')); rect(0, gy, 1, 1 - gy, T('#456c3d'));
      const hx = 0.66; rect(hx, 0.3, 0.3, gy - 0.3, T('#c9b79a')); poly([[hx - 0.02, 0.3], [hx + 0.15, 0.14], [hx + 0.32, 0.3]], T('#6e4a3a'));
      for (const [x, y] of [[hx + 0.04, 0.38], [hx + 0.19, 0.38], [hx + 0.04, 0.56]]) { rect(x, y, 0.07, 0.1, day ? '#9cc3e6' : '#f2c94c', T('#f2efe6')); if (!day) lampPool(x + 0.035, y + 0.05, 0.07); }
      door(hx + 0.19, 0.56, 0.06, gy - 0.56, '#7d4a3a');
      g.strokeStyle = T('#f2efe6'); g.lineWidth = Math.max(1.5, H * 0.004); for (let i = 0; i < 26; i++) { const x = i * 0.026; g.beginPath(); g.moveTo(X(x), Y(gy + 0.005)); g.lineTo(X(x), Y(gy - 0.07)); g.stroke(); } g.beginPath(); g.moveTo(0, Y(gy - 0.05)); g.lineTo(X(0.66), Y(gy - 0.05)); g.stroke();
    } else {
      for (let i = 0; i < 6; i++) { const x = i * 0.18 - 0.02, h = 0.25 + 0.2 * hash(i + 2); rect(x, gy - 0.12 - h, 0.16, h, T(['#7a6a8a', '#8a7a6a', '#6a7a8a'][i % 3])); for (let k = 0; k < 6; k++) rect(x + 0.02 + (k % 3) * 0.045, gy - 0.1 - h + 0.04 + Math.floor(k / 3) * 0.08, 0.03, 0.045, hash(i * 9 + k) > 0.5 && !day ? '#f2c94c' : T('#3a4458')); }
      rect(0, gy - 0.12, 1, 0.12, T('#a7a39a')); rect(0, gy, 1, 1 - gy, T('#3d4048')); for (let i = 0; i < 8; i++) rect(i * 0.14 + 0.02, gy + 0.09, 0.07, 0.012, T('#e8e2c8'));
      for (const x of [0.2, 0.62]) { rect(x, 0.22, 0.008, gy - 0.12 - 0.22, T('#2b2f3a')); rect(x - 0.02, 0.21, 0.045, 0.015, T('#2b2f3a')); poly([[x - 0.01, 0.225], [x + 0.03, 0.225], [x + 0.12, gy - 0.12], [x - 0.1, gy - 0.12]], day ? 'rgba(255,255,255,0.0)' : 'rgba(255,214,120,0.16)'); }
    }
  } else {                                                                 // house_section, cutaway: the house in section on a night lawn
    const cut = nm === 'cutaway', gy = GROUND[nm], [hx, hy, hw] = cut ? [0.1, 0.23, 0.8] : [0.18, 0.28, 0.46], mid = cut ? 0.5 : 0.56;
    nightSky(gy); rect(0, gy, 1, 1 - gy, T('#456c3d'));
    poly([[hx - 0.04, hy], [hx + hw / 2, hy - (cut ? 0.15 : 0.18)], [hx + hw + 0.04, hy]], T('#6e4a3a'));
    const rooms = cut ? [[hx, hy, hw * 0.55, mid - hy, '#d8c9e3'], [hx + hw * 0.55, hy, hw * 0.45, mid - hy, '#cfe0d0'], [hx, mid, hw * 0.4, gy - mid, '#f2e3c4'], [hx + hw * 0.4, mid, hw * 0.6, gy - mid, '#e6d6c0']]
      : [[hx, hy, hw / 2, mid - hy, '#d8c9e3'], [hx + hw / 2, hy, hw / 2, mid - hy, '#cfe0d0'], [hx, mid, hw, gy - mid, '#f2e3c4']];
    for (const [x, y, w, h, c] of rooms) { rect(x, y, w, h, T(c)); rect(x, y + h - 0.02, w, 0.02, T('#8a6a4a')); if (!day) pool(x + w / 2, y + h * 0.3, w * 0.4, h * 0.3, glowRGB, 0.3); }
    g.strokeStyle = T('#5a4330'); g.lineWidth = Math.max(3, H * 0.008); g.strokeRect(X(hx), Y(hy), X(hw), Y(gy - hy));
    if (cut) { for (let i = 0; i < 6; i++) rect(hx + hw * 0.5 + i * 0.03, gy - (i + 1) * ((gy - mid) / 6), 0.03, (i + 1) * ((gy - mid) / 6), T('#a3825f')); rect(hx + 0.03, mid - 0.07, 0.17, 0.05, T('#5b6fa8')); rect(hx + 0.03, mid - 0.085, 0.05, 0.02, T('#e8e6f0')); }
  }
  g.restore();
}
