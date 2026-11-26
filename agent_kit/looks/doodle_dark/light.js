// doodle_dark light + drawing building blocks (also detail: floorBoards, wallTex, door, contact, fg, frame, clock, plant, rug, clutter). Use them to draw ANY place the narration names, new each scene.
//   import { defs, R, lin, rad, shaft, glow, dust, treeline, dayTag } from '/agent_kit/looks/doodle_dark/light.js';
// defs() once per <svg>: blur filters + the light tints a character takes from the place
//   (hero(t, { light: 'night' | 'moon' | 'dusk' | 'warm' | 'day' })).
import { rand } from '/agent_kit/lib/kit.js';

const INK = '#0b0f18';

// ---------- shared defs: blurs, glows, and the light tints characters take from the place ----------
export function defs() {
  const lit = (id, m) => `<filter id="lit-${id}" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="${m}"/></filter>`;
  return `<defs>
    <filter id="blur4" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>
    <filter id="blur8" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="8"/></filter>
    <filter id="blur12" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="12"/></filter>
    <filter id="blur40" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="40"/></filter>
    <filter id="blur90" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="90"/></filter>
    ${lit('night', '0.50 0 0 0 0.02  0 0.56 0 0 0.03  0 0 0.78 0 0.07  0 0 0 1 0')}
    ${lit('moon', '0.62 0 0 0 0.03  0 0.68 0 0 0.04  0 0 0.86 0 0.08  0 0 0 1 0')}
    ${lit('dusk', '0.80 0 0 0 0.04  0 0.72 0 0 0.03  0 0 0.74 0 0.05  0 0 0 1 0')}
    ${lit('warm', '0.80 0 0 0 0.03  0 0.74 0 0 0.02  0 0 0.66 0 0.01  0 0 0 1 0')}
    ${lit('day', '0.95 0 0 0 0  0 0.95 0 0 0  0 0 0.97 0 0.02  0 0 0 1 0')}
  </defs>`;
}

export const R = (x, y, w, h, fill, extra = '') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" ${extra}/>`;
export const lin = (id, stops, x2 = 0, y2 = 1) =>
  `<linearGradient id="${id}" x1="0" y1="0" x2="${x2}" y2="${y2}">${stops.map(([o, c, a = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join('')}</linearGradient>`;
export const rad = (id, stops) =>
  `<radialGradient id="${id}">${stops.map(([o, c, a = 1]) => `<stop offset="${o}" stop-color="${c}" stop-opacity="${a}"/>`).join('')}</radialGradient>`;

// floating dust inside a polygon (light shaft): slow drift, twinkle, seeded
export function dust(t, poly, { n = 60, seed = 5, color = '#f6e7c4', size = 2.6, id = 'dust' } = {}) {
  const r = rand(seed), xs = poly.map((p) => p[0]), ys = poly.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  let s = `<clipPath id="${id}"><polygon points="${poly.map((p) => p.join(',')).join(' ')}"/></clipPath><g clip-path="url(#${id})">`;
  for (let i = 0; i < n; i++) {
    const bx = x0 + r() * (x1 - x0), by = y0 + r() * (y1 - y0), sp = 6 + r() * 14, ph = r() * 6.28;
    const x = bx + Math.sin(t * 0.3 + ph) * 18 + t * sp * 0.4, y = by + ((t * sp) % (y1 - y0 + 40)) * 0.35 - 10;
    const a = 0.25 + 0.55 * (0.5 + 0.5 * Math.sin(t * (0.8 + r()) + ph));
    s += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${(size * (0.5 + r())).toFixed(1)}" fill="${color}" opacity="${a.toFixed(2)}"/>`;
  }
  return s + '</g>';
}

// a soft light shaft (window / door / bulb) — blurred gradient polygon in screen blend
export function shaft(id, poly, color, a = 0.22, flick = 0) {
  return `<g style="mix-blend-mode:screen" opacity="${(a + flick).toFixed(3)}">` +
    `<defs>${lin(id, [[0, color, 1], [1, color, 0]], 0.25, 1)}</defs>` +
    `<polygon points="${poly.map((p) => p.join(',')).join(' ')}" fill="url(#${id})" filter="url(#blur12)"/></g>`;
}

export const glow = (cx, cy, r, color, a = 0.5) =>
  `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" opacity="${a}" filter="url(#blur40)" style="mix-blend-mode:screen"/>`;

// tree line / town skyline silhouettes (seeded)
export function treeline(y, color, seed, h = 90, step = 46) {
  const r = rand(seed); let d = `M-60 1100 L-60 ${y}`;
  for (let x = -60; x <= 1980; x += step) {
    const hh = h * (0.4 + r() * 0.7), w = step * (0.6 + r() * 0.5);
    d += ` L${x} ${y} Q${x + w * 0.1} ${y - hh * 0.6} ${x + w / 2} ${y - hh} Q${x + w * 0.9} ${y - hh * 0.6} ${x + w} ${y}`;
  }
  return `<path d="${d} L1980 1100 Z" fill="${color}"/>`;
}


// "DAY 18" tag, top-left on every shot (grey word, amber number) — HTML string
export const dayTag = (n) =>
  `<div class="abs" style="left:64px;top:44px;font-family:'Doodle Display',Impact,sans-serif;font-size:40px;letter-spacing:3px;` +
  `color:#8d97ab;text-shadow:0 2px 0 #0b0f18">DAY <span style="color:#ffb547">${n}</span></div>`;

// ---------- detail: what stops a place looking empty (use several in every place) ----------
const shade = (hex, f) => {            // lighten (f>0) or darken (f<0) a #rrggbb colour
  const n = parseInt(hex.slice(1), 16), c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.max(0, Math.min(255, Math.round(f > 0 ? v + (255 - v) * f : v * (1 + f)))));
  return '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
};
export { shade };

// wooden floor: boards running away from camera (seams + per-board tone)
export function floorBoards(y, h, color = '#2a241e', { seed = 3, step = 120 } = {}) {
  const r = rand(seed); let s = R(0, y, 1920, h, color);
  for (let x = -200, i = 0; x < 2120; x += step, i++) {
    const v = (r() - 0.5) * 0.12, x2 = 960 + (x - 960) * 1.9;
    s += `<polygon points="${x},${y} ${x + step},${y} ${960 + (x + step - 960) * 1.9},${y + h} ${x2},${y + h}" fill="${shade(color, v)}"/>`;
    s += `<path d="M${x} ${y} L${x2} ${y + h}" stroke="${shade(color, -0.35)}" stroke-width="3"/>`;
  }
  return s + `<rect x="0" y="${y}" width="1920" height="${h}" fill="url(#flfade)"/>` +
    `<defs>${lin('flfade', [[0, '#000', 0.35], [1, '#000', 0]])}</defs>`;
}

// wall: base colour + faint vertical stripes (wallpaper) or planks, a skirting board, a soft top shadow
export function wallTex(y0, y1, color = '#232a3b', { kind = 'paper', seed = 5, step = 64 } = {}) {
  const r = rand(seed); let s = R(0, y0, 1920, y1 - y0, color);
  if (kind === 'paper') for (let x = 0; x < 1920; x += step) s += R(x, y0, step / 2, y1 - y0, shade(color, 0.05), 'opacity=".55"');
  else for (let x = 0; x < 1920; x += step) s += R(x, y0, step - 4, y1 - y0, shade(color, (r() - 0.5) * 0.1)) + R(x + step - 4, y0, 4, y1 - y0, shade(color, -0.4));
  s += R(0, y1 - 34, 1920, 34, shade(color, -0.25), `stroke="${INK}" stroke-width="4"`);
  s += `<defs>${lin('wtop' + seed, [[0, '#000', 0.45], [1, '#000', 0]])}</defs>` + R(0, y0, 1920, 220, `url(#wtop${seed})`);
  return s;
}

// a proper door: frame, raised panels with bevel light, grain, hinges, knob; open 0..1 swings it inward (shows darkness)
export function door(x, y, w = 260, h = 540, { wood = '#5b4632', open = 0, knob = 'right', dark = '#05070c' } = {}) {
  const fr = shade(wood, -0.35), pn = shade(wood, -0.12), hi = shade(wood, 0.18);
  let s = R(x - 22, y - 22, w + 44, h + 22, fr, `stroke="${INK}" stroke-width="6"`) + R(x, y, w, h, dark);
  const ww = w * (1 - open * 0.8), dx = knob === 'right' ? x : x + w - ww;
  s += `<g>` + R(dx, y, ww, h, wood, `stroke="${INK}" stroke-width="6"`);
  for (const [py, ph] of [[0.07, 0.38], [0.53, 0.4]]) {
    const px = dx + ww * 0.12, pw = ww * 0.76, yy = y + h * py, hh = h * ph;
    s += R(px, yy, pw, hh, pn, `stroke="${INK}" stroke-width="4" rx="5"`) + `<path d="M${px + 4} ${yy + hh - 4} V${yy + 4} H${px + pw - 4}" stroke="${hi}" stroke-width="3" fill="none" opacity=".7"/>`;
  }
  for (let i = 0; i < 5; i++) s += `<path d="M${dx + ww * (0.2 + i * 0.15)} ${y + 8} q6 ${h * 0.5} -2 ${h - 16}" stroke="${shade(wood, -0.2)}" stroke-width="2" fill="none" opacity=".5"/>`;
  const kx = knob === 'right' ? dx + ww - 30 : dx + 30;
  s += `<circle cx="${kx}" cy="${y + h * 0.52}" r="14" fill="#b8954a" stroke="${INK}" stroke-width="4"/><circle cx="${kx - 4}" cy="${y + h * 0.52 - 4}" r="4" fill="#f1dca0"/>`;
  const hx = knob === 'right' ? dx + 2 : dx + ww - 12;
  s += R(hx, y + h * 0.12, 10, 34, '#6d7380', `stroke="${INK}" stroke-width="3"`) + R(hx, y + h * 0.8, 10, 34, '#6d7380', `stroke="${INK}" stroke-width="3"`);
  return s + '</g>';
}

// soft contact shadow under anything standing on the floor
export const contact = (cx, cy, w, a = 0.45) => `<ellipse cx="${cx}" cy="${cy}" rx="${w / 2}" ry="${Math.max(6, w * 0.06)}" fill="#000" opacity="${a}" filter="url(#blur8)"/>`;

// out-of-focus foreground object (depth): wrap any SVG, it gets blurred and darkened
export const fg = (svg, blur = 'blur8', a = 1) => `<g filter="url(#${blur})" opacity="${a}">${svg}</g>`;

// small room props
export const frame = (x, y, w, h, art = '#3d5a6b') => R(x, y, w, h, '#4a3b2c', `stroke="${INK}" stroke-width="5"`) + R(x + 10, y + 10, w - 20, h - 20, art) +
  `<path d="M${x + 10} ${y + h - 10} L${x + w * 0.45} ${y + h * 0.45} L${x + w * 0.65} ${y + h * 0.65} L${x + w - 10} ${y + h * 0.35} V${y + h - 10} Z" fill="${shade(art, -0.3)}"/>`;
export function clock(x, y, r, t) {
  const a = t * 6, b = t * 0.5;   // seconds hand ticks
  return `<circle cx="${x}" cy="${y}" r="${r}" fill="#d9d3c4" stroke="${INK}" stroke-width="5"/>` +
    `<path d="M${x} ${y} l${(Math.sin(b) * r * 0.5).toFixed(1)} ${(-Math.cos(b) * r * 0.5).toFixed(1)}" stroke="${INK}" stroke-width="5" stroke-linecap="round"/>` +
    `<path d="M${x} ${y} l${(Math.sin(Math.floor(a) / 9.55) * r * 0.8).toFixed(1)} ${(-Math.cos(Math.floor(a) / 9.55) * r * 0.8).toFixed(1)}" stroke="#b3262c" stroke-width="2"/>`;
}
export const plant = (x, y) => `<path d="M${x - 30} ${y} l8 -60 h44 l8 60 z" fill="#6b4a36" stroke="${INK}" stroke-width="4"/>` +
  [[-40, -150], [0, -170], [36, -140], [-20, -120], [24, -110]].map(([dx, dy]) => `<path d="M${x} ${y - 60} Q${x + dx * 0.3} ${y - 60 + dy * 0.5} ${x + dx} ${y + dy - 60 + 60}" stroke="#3f5a3a" stroke-width="10" fill="none" stroke-linecap="round"/>`).join('');
export const rug = (cx, cy, w, color = '#5a3f4a') => `<ellipse cx="${cx}" cy="${cy}" rx="${w / 2}" ry="${w * 0.09}" fill="${color}" stroke="${INK}" stroke-width="4"/><ellipse cx="${cx}" cy="${cy}" rx="${w / 2 - 22}" ry="${w * 0.09 - 8}" fill="none" stroke="${shade(color, 0.2)}" stroke-width="3" stroke-dasharray="10 8"/>`;
// a row of shelf clutter (books, jars, boxes) between x and x+w standing on y
export function clutter(x, y, w, seed = 2) {
  const r = rand(seed); let s = '', cx = x;
  while (cx < x + w - 30) {
    const k = r(), c = ['#6b5a44', '#5b6a5c', '#8a5a44', '#6d6f78', '#4f5b78', '#7d6a4a'][Math.floor(r() * 6)];
    if (k < 0.45) { const bw = 14 + r() * 12, bh = 50 + r() * 30; s += R(cx, y - bh, bw, bh, c, `stroke="${INK}" stroke-width="3"`); cx += bw + 1; }
    else if (k < 0.75) { const jw = 34 + r() * 14, jh = 40 + r() * 26; s += R(cx, y - jh, jw, jh, c, `stroke="${INK}" stroke-width="3" rx="6"`) + R(cx + 3, y - jh - 7, jw - 6, 8, '#3b3f48', `stroke="${INK}" stroke-width="2"`); cx += jw + 8; }
    else { const bw = 60 + r() * 30, bh = 36 + r() * 20; s += R(cx, y - bh, bw, bh, '#6a5640', `stroke="${INK}" stroke-width="3"`) + `<path d="M${cx} ${y - bh + 8} H${cx + bw}" stroke="${INK}" stroke-width="2" opacity=".5"/>`; cx += bw + 8; }
  }
  return s;
}
