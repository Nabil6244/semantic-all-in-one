// history_toon props and set pieces: SVG strings, every one a pure function of t (or of a 0..1 progress k).
//   import * as H from '/agent_kit/looks/history_toon/props.js';
//   svg.innerHTML = H.defs() + H.sky() + H.hills(700) + ... ;
// Coordinates are 1920x1080 frame pixels. k = reveal progress 0..1 (use K.prog(t, at, dur)).
import { P, shade } from './palette.js';

const INK = P.ink, W = P.ink_w;
const st = (w = W) => `stroke="${INK}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"`;
const cl = (k) => Math.min(1, Math.max(0, k));
const back = (k) => { k = cl(k); const s = 1.7; return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2; };
let _id = 0;
const uid = (p) => `${p}${++_id}`;
export const resetIds = () => { _id = 0; };   // call once at the top of renderAt so ids stay the same every frame

/** Put once at the start of each <svg>: hatch pattern for zones, soft blur, paper texture. */
export function defs() {
  resetIds();
  return `<defs>
  <pattern id="hatch" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="14" height="14" fill="${P.red}" opacity=".35"/><path d="M0 0 V14" stroke="${P.red}" stroke-width="5" opacity=".55"/></pattern>
  <filter id="soft6"><feGaussianBlur stdDeviation="6"/></filter><filter id="soft16"><feGaussianBlur stdDeviation="16"/></filter>
  <filter id="paperTex"><feTurbulence type="fractalNoise" baseFrequency=".6" numOctaves="2" result="n"/><feColorMatrix in="n" values="0 0 0 0 .4 0 0 0 0 .35 0 0 0 0 .25 0 0 0 .12 0"/><feComposite in2="SourceGraphic" operator="in"/></filter>
  </defs>`;
}

export const rect = (x, y, w, h, fill, extra = '') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" ${extra}/>`;
/** A line or path drawn on with k (0..1). */
export const draw = (d, k, { w = 6, c = P.red, fill = 'none', cap = 'round' } = {}) =>
  `<path d="${d}" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${(1 - cl(k)).toFixed(4)}" fill="${fill}" stroke="${c}" stroke-width="${w}" stroke-linecap="${cap}" stroke-linejoin="round"/>`;
/** Wrap any svg so it pops in (scale from 0 with overshoot) around its own point (cx, cy). */
export const pop = (svg, k, cx, cy) => k <= 0 ? '' : `<g transform="translate(${cx} ${cy}) scale(${back(k).toFixed(4)}) translate(${-cx} ${-cy})">${svg}</g>`;
/** Slide in from below with a fade. */
export const rise = (svg, k, dy = 60) => k <= 0 ? '' : `<g transform="translate(0 ${((1 - back(k)) * dy).toFixed(1)})" opacity="${cl(k * 2)}">${svg}</g>`;
const text = (x, y, s, { size = 34, color = INK, font = 'HT Display', anchor = 'middle', weight = 800, spacing = 1, op = 1, rot = 0 } = {}) =>
  `<text x="${x}" y="${y}" font-family="'${font}'" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}" letter-spacing="${spacing}" opacity="${op}"${rot ? ` transform="rotate(${rot} ${x} ${y})"` : ''}>${s}</text>`;
export { text };

// ================= outdoor sets =================
export function sky(top = P.sky, bottom = '#e6eee4', h = 1080) { const id = uid('sky'); return `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${top}"/><stop offset="1" stop-color="${bottom}"/></linearGradient>${rect(0, 0, 1920, h, `url(#${id})`)}`; }
export function cloud(x, y, s = 1, c = P.cloud) {
  return `<g transform="translate(${x} ${y}) scale(${s})"><path d="M-120 30 Q-130 -10 -90 -14 Q-80 -60 -30 -50 Q-6 -90 40 -60 Q90 -70 96 -24 Q140 -18 130 30 Z" fill="${c}"/><path d="M-120 30 H130" stroke="${shade(c, -0.08)}" stroke-width="6"/></g>`;
}
/** Rolling hills band whose top sits near y. seed changes the shape. */
export function hills(y, color = P.hill, { seed = 1, amp = 60, step = 240 } = {}) {
  let d = `M0 1080 L0 ${y}`;
  for (let x = 0, i = 0; x <= 1920 + step; x += step, i++) {
    const h = y - amp * (0.5 + 0.5 * Math.sin(i * 1.7 + seed * 2.3)) ;
    d += ` Q${x + step / 2} ${h - amp * 0.6} ${x + step} ${y - amp * 0.3 * Math.cos(i + seed)}`;
  }
  return `<path d="${d} L1920 1080 Z" fill="${color}"/>`;
}
export function trees(y, n = 10, { seed = 2, color = '#5d7a4a', x0 = 0, x1 = 1920, h = 90 } = {}) {
  let g = '';
  for (let i = 0; i < n; i++) {
    const x = x0 + ((i + 0.5) / n) * (x1 - x0) + Math.sin(i * 7.3 + seed) * 30, hh = h * (0.7 + 0.4 * Math.abs(Math.sin(i * 3.1 + seed)));
    g += `<rect x="${x - 5}" y="${y - hh * 0.3}" width="10" height="${hh * 0.3}" fill="${P.woodDark}"/><ellipse cx="${x}" cy="${y - hh * 0.55}" rx="${hh * 0.38}" ry="${hh * 0.45}" fill="${color}" ${st(3)}/>`;
  }
  return g;
}
export function ground(y, color = P.grass) { return rect(0, y, 1920, 1080 - y, color) + `<path d="M0 ${y} H1920" ${st(4)}/>`; }
/** Sea from y down with moving wave marks. */
export function sea(t, y, { color = P.sea, deep = P.seaDeep } = {}) {
  const id = uid('sea');
  let g = `<linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}"/><stop offset="1" stop-color="${deep}"/></linearGradient>${rect(0, y, 1920, 1080 - y, `url(#${id})`)}`;
  for (let r = 0; r < 6; r++) for (let i = 0; i < 9; i++) {
    const yy = y + 30 + r * ((1080 - y) / 6), x = ((i * 240 + r * 120 + t * 30 * (r % 2 ? 1 : -1)) % 2160 + 2160) % 2160 - 120;
    g += `<path d="M${x} ${yy} q16 -10 32 0 q16 10 32 0" fill="none" stroke="#fff" stroke-width="3" opacity=".45"/>`;
  }
  return g;
}
/** Dust/smoke puff growing with k. */
export function puff(x, y, k, s = 1, c = '#e8dcc0') {
  if (k <= 0 || k >= 1.4) return '';
  const r = 30 + 90 * Math.min(1, k), a = Math.max(0, 1 - Math.max(0, k - 0.6) / 0.8);
  return `<g opacity="${a.toFixed(3)}" transform="translate(${x} ${y}) scale(${s})">` + [[-60, 0, 1], [0, -30, 1.2], [60, 0, 1], [-20, 20, 0.9], [30, 18, 0.8]].map(([dx, dy, m]) =>
    `<circle cx="${dx * Math.min(1, k)}" cy="${dy * Math.min(1, k)}" r="${(r * m).toFixed(1)}" fill="${c}" ${st(3)}/>`).join('') + '</g>';
}

// ================= interiors =================
/** A plank wall from y0 to y1 with vertical boards. */
export function plankWall(y0, y1, color = P.wall, step = 90) {
  let g = rect(0, y0, 1920, y1 - y0, color);
  for (let x = 0; x < 1920; x += step) g += `<path d="M${x} ${y0} V${y1}" stroke="${shade(color, -0.12)}" stroke-width="3"/>`;
  return g + rect(0, y1 - 26, 1920, 26, shade(color, -0.2), st(3));
}
export function floorBoards(y, color = P.floor) {
  let g = rect(0, y, 1920, 1080 - y, color);
  for (let i = 1; i < 8; i++) { const yy = y + (1080 - y) * (i / 8) ** 1.4; g += `<path d="M0 ${yy} H1920" stroke="${shade(color, -0.15)}" stroke-width="3"/>`; }
  return g;
}
export function windowFrame(x, y, w, h, view = P.sky) {
  return rect(x, y, w, h, view, st()) + `<path d="M${x + w / 2} ${y} V${y + h} M${x} ${y + h / 2} H${x + w}" ${st(8)} stroke="${P.woodLight}"/><rect x="${x}" y="${y}" width="${w}" height="${h}" fill="none" ${st(10)}/>` +
    `<path d="M${x + 20} ${y + 30} l40 -20 M${x + 20} ${y + 70} l80 -40" stroke="#fff" stroke-width="6" opacity=".5"/>`;
}
/** Hanging lamp with a warm cone of light down to floorY. */
export function lamp(t, x, y, floorY, swing = 0) {
  const a = Math.sin(t * 1.3) * swing;
  return `<g transform="rotate(${a.toFixed(2)} ${x} 0)"><path d="M${x} 0 V${y - 30}" ${st(3)}/><path d="M${x - 40} ${y} Q${x} ${y - 60} ${x + 40} ${y} Z" fill="${P.metalDark}" ${st(4)}/><circle cx="${x}" cy="${y + 4}" r="10" fill="#fff3c4"/>` +
    `<path d="M${x - 30} ${y} L${x - 260} ${floorY} H${x + 260} L${x + 30} ${y} Z" fill="#fff3c4" opacity=".16"/></g>`;
}
export function desk(x, y, w = 560, h = 200, color = P.wood) {
  return rect(x, y, w, 26, shade(color, 0.1), st()) + rect(x + 20, y + 26, w - 40, h, color, st()) +
    rect(x + w - 200, y + 50, 160, 50, shade(color, -0.1), st(3)) + `<circle cx="${x + w - 120}" cy="${y + 75}" r="6" fill="${P.gold}" ${st(2)}/>`;
}
export function crate(x, y, s = 1) { return `<g transform="translate(${x} ${y}) scale(${s})">${rect(-60, -110, 120, 110, P.woodLight, st())}<path d="M-60 -110 L60 0 M-60 -55 H60" ${st(4)}/></g>`; }
export function barrel(x, y, s = 1, c = '#6f7a5a') { return `<g transform="translate(${x} ${y}) scale(${s})"><path d="M-40 0 Q-50 -60 -40 -120 H40 Q50 -60 40 0 Z" fill="${c}" ${st()}/><path d="M-46 -40 H46 M-46 -82 H46" ${st(4)}/></g>`; }
/** Desk-top close-up background: green blotter, pencil cup, ink pad, cup. */
export function deskTop({ wood = '#bfae7a' } = {}) {
  return rect(0, 0, 1920, 1080, wood) + rect(380, 230, 1120, 820, '#4f8a4a', st(6) + ' rx="30"') +
    `<g transform="translate(250 150)"><path d="M-60 -30 L-50 130 H50 L60 -30 Z" fill="${P.metal}" ${st()}/>` +
    [[-30, P.red], [0, P.olive], [28, P.gold]].map(([dx, c]) => `<path d="M${dx} -30 l${dx / 3} -110" stroke="${INK}" stroke-width="18" stroke-linecap="round"/><path d="M${dx} -30 l${dx / 3} -110" stroke="${c}" stroke-width="10" stroke-linecap="round"/>`).join('') + `</g>` +
    rect(1580, 110, 240, 170, '#3a3f44', st(6) + ' rx="16"') + rect(1606, 136, 188, 118, '#1f2226', ' rx="10"') +
    `<circle cx="1720" cy="880" r="110" fill="#e9e2d0" ${st(6)}/><circle cx="1720" cy="880" r="74" fill="#d6ccb4" ${st(4)}/>`;
}

// ================= paper and writing =================
/** A hand with a pen; the nib is at (x, y). angle in degrees. Sleeve comes from bottom-right. */
export function penHand(x, y, { angle = -35, sleeve = P.olive, pen = P.pen } = {}) {
  return `<g transform="translate(${x} ${y}) rotate(${angle})"><path d="M0 0 L16 -12 L190 -12 L190 12 L16 12 Z" fill="${pen}" ${st(4)}/><path d="M0 0 L16 -6 V6 Z" fill="${INK}"/>` +
    `<path d="M150 -8 L900 -60 L900 70 L150 20 Z" fill="${sleeve}" ${st(5)}/><ellipse cx="160" cy="12" rx="36" ry="30" fill="#fff" ${st(4)}/></g>`;
}
/** A paper form with handwritten values.
 *  rows: [{label, value, at, dur, color, strike (time), check (time)}]; values are written left to right from `at`.
 *  Returns {svg, pen:[x,y]} — pen is where the writing is now (draw penHand there while something is being written). */
export function paperForm(t, { x = 560, y = 170, w = 800, h = 600, title = 'REPORT', no = 'No. 4817', rows = [], tilt = -1.5, k = 1 } = {}) {
  let g = `<g transform="rotate(${tilt} ${x + w / 2} ${y + h / 2})">`;
  g += rect(x + 10, y + 14, w, h, '#000', 'opacity=".18" rx="6"') + rect(x, y, w, h, P.paper, st(4) + ' rx="6"') + rect(x, y, w, h, P.paper, 'filter="url(#paperTex)" rx="6"');
  g += text(x + 50, y + 80, title, { size: 46, anchor: 'start' }) + text(x + w - 40, y + 50, no, { size: 20, anchor: 'end', color: P.red });
  g += `<path d="M${x + 50} ${y + 100} H${x + w - 50}" stroke="${INK}" stroke-width="3"/>`;
  let pen = null;
  rows.forEach((r, i) => {
    const ry = y + 180 + i * 90, lx = x + 50;
    g += text(lx, ry, r.label, { size: 24, anchor: 'start', spacing: 2 });
    const vx = lx + (r.labelW ?? 200);
    g += `<path d="M${vx} ${ry + 10} H${x + w - 50}" stroke="${P.mute}" stroke-width="2" stroke-dasharray="4 6"/>`;
    if (r.value && t >= r.at) {
      const len = r.value.length, dur = r.dur ?? Math.max(0.5, len * 0.07), kk = cl((t - r.at) / dur);
      const id = uid('wr'), tw = len * 22 * (r.size ?? 1);
      g += `<clipPath id="${id}"><rect x="${vx - 10}" y="${ry - 60}" width="${(tw * kk + 10).toFixed(1)}" height="90"/></clipPath>`;
      g += `<g clip-path="url(#${id})">${text(vx, ry, r.value, { size: 40 * (r.size ?? 1), anchor: 'start', font: 'HT Hand', color: r.color || P.pen, weight: 700, spacing: 0 })}</g>`;
      if (kk > 0 && kk < 1) pen = [vx + tw * kk, ry - 6];
      if (r.check !== undefined && t >= r.check) g += draw(`M${vx + tw + 20} ${ry - 14} l12 14 l24 -34`, cl((t - r.check) / 0.25), { w: 5, c: P.pen });
      if (r.strike !== undefined && t >= r.strike) g += draw(`M${vx - 6} ${ry - 12} L${vx + tw + 6} ${ry - 16}`, cl((t - r.strike) / 0.3), { w: 5, c: r.strikeColor || P.pen });
    }
  });
  g += '</g>';
  return { svg: k < 1 ? rise(g, k, 120) : g, pen };
}
/** Rubber stamp that slams in at `at` (big -> landed, slight rotation). */
export function stamp(t, at, x, y, label, { color = P.red, size = 56, rot = -12, box = true } = {}) {
  if (t < at) return '';
  const k = cl((t - at) / 0.22), s = 2.4 - 1.4 * (1 - (1 - k) ** 3);
  const w = label.length * size * 0.66 + 40;
  return `<g transform="translate(${x} ${y}) rotate(${rot}) scale(${s.toFixed(3)})" opacity="${Math.min(1, k * 3) * 0.9}">` +
    (box ? `<rect x="${-w / 2}" y="${-size * 0.85}" width="${w}" height="${size * 1.35}" rx="8" fill="none" stroke="${color}" stroke-width="7"/>` : '') +
    text(0, size * 0.25, label, { size, color, spacing: 3 }) + `</g>`;
}
/** Checklist on lined notebook paper: items [{text, at, check:true|false}]. */
export function notebook(t, { x = 620, y = 150, w = 680, h = 560, title = 'LIST', items = [], tilt = 2 } = {}) {
  let g = `<g transform="rotate(${tilt} ${x + w / 2} ${y + h / 2})">` + rect(x + 10, y + 14, w, h, '#000', 'opacity=".18"') + rect(x, y, w, h, '#fbf8ef', st(4));
  for (let ly = y + 110; ly < y + h - 20; ly += 64) g += `<path d="M${x} ${ly} H${x + w}" stroke="#a9c4e0" stroke-width="2.5"/>`;
  g += `<path d="M${x + 70} ${y} V${y + h}" stroke="#e39a9a" stroke-width="3"/>`;
  g += text(x + 100, y + 80, title, { size: 46, anchor: 'start', font: 'HT Hand', color: P.pen, weight: 700 });
  items.forEach((it, i) => {
    if (t < it.at) return;
    const iy = y + 160 + i * 64, k = cl((t - it.at) / 0.4);
    g += `<rect x="${x + 96}" y="${iy - 30}" width="32" height="32" fill="none" stroke="${P.red}" stroke-width="4"/>`;
    if (it.check !== false) g += draw(`M${x + 100} ${iy - 14} l10 12 l22 -30`, cl((t - it.at) / 0.25), { w: 5, c: P.red });
    const id = uid('nb');
    g += `<clipPath id="${id}"><rect x="${x + 140}" y="${iy - 50}" width="${(it.text.length * 22 * k).toFixed(0)}" height="70"/></clipPath><g clip-path="url(#${id})">${text(x + 148, iy, it.text, { size: 38, anchor: 'start', font: 'HT Hand', color: P.pen, weight: 700, spacing: 0 })}</g>`;
  });
  return g + '</g>';
}

// ================= map pieces =================
/** Flat paper map background: sea colour, faint grid, optional big sea label. */
export function mapSea({ color = '#a8d3cc', label = '', lx = 1300, ly = 300 } = {}) {
  let g = rect(0, 0, 1920, 1080, color);
  for (let x = 0; x < 1920; x += 160) g += `<path d="M${x} 0 V1080" stroke="#fff" stroke-width="1.5" opacity=".18"/>`;
  for (let y = 0; y < 1080; y += 160) g += `<path d="M0 ${y} H1920" stroke="#fff" stroke-width="1.5" opacity=".18"/>`;
  if (label) g += text(lx, ly, label, { size: 54, color: '#fff', spacing: 14, op: 0.55, rot: -8 });
  return g;
}
/** A land shape (path d in frame pixels) with a coast line and a soft inner edge. */
export const land = (d, color = P.land) => `<path d="${d}" fill="${color}" ${st(4)}/><path d="${d}" fill="none" stroke="${shade(color, -0.12)}" stroke-width="10" opacity=".5" transform="translate(0 4)"/>`;
/** A red hatched zone (controlled area) that grows in with k. cx,cy = where it grows from. */
export function zone(d, k, cx = 960, cy = 540) {
  if (k <= 0) return '';
  const s = 0.6 + 0.4 * back(k);
  return `<g transform="translate(${cx} ${cy}) scale(${s.toFixed(3)}) translate(${-cx} ${-cy})" opacity="${cl(k * 2)}"><path d="${d}" fill="url(#hatch)" stroke="${P.red}" stroke-width="5" stroke-dasharray="14 8"/></g>`;
}
/** Map pin (teardrop, icon inside) with a label below; pops in with k. */
export function pin(x, y, label, k, { color = '#f3ead4', icon = 'dot', size = 1 } = {}) {
  if (k <= 0) return '';
  const ic = icon === 'plane' ? `<path d="M-14 0 H14 M0 -12 V12 M-6 10 H6" ${st(3.5)}/>` : icon === 'ship' ? `<path d="M-14 2 H14 L8 10 H-8 Z M-4 2 V-10 H6" fill="${INK}" ${st(2)}/>` : `<circle r="6" fill="${INK}"/>`;
  const g = `<g transform="translate(${x} ${y}) scale(${size})"><ellipse cx="0" cy="4" rx="16" ry="6" fill="#000" opacity=".2"/><path d="M0 0 C-12 -16 -26 -30 -26 -48 A26 26 0 1 1 26 -48 C26 -30 12 -16 0 0 Z" fill="${color}" ${st(4)}/><g transform="translate(0 -48)">${ic}</g></g>` +
    (label ? text(x, y + 40 * size, label, { size: 28 * size, spacing: 1 }) : '');
  return pop(g, k, x, y);
}
/** Curved arrow along path d (drawn on with k), arrowhead at the end. */
export function arrow(d, k, { c = P.red, w = 9 } = {}) {
  if (k <= 0) return '';
  const id = uid('ar');
  return `<marker id="${id}" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="${c}"/></marker>` +
    `<path d="${d}" pathLength="1" stroke-dasharray="1 1" stroke-dashoffset="${(1 - cl(k)).toFixed(4)}" fill="none" stroke="${c}" stroke-width="${w}" stroke-linecap="round" ${k > 0.97 ? `marker-end="url(#${id})"` : ''}/>`;
}
/** Red circle drawn around a place, hand-drawn (slightly overshooting). */
export function ring(x, y, r, k, c = P.red) {
  let d = '';
  for (let i = 0; i <= 40; i++) { const a = -0.5 + (i / 40) * (Math.PI * 2 + 0.45), rr = r * (1 + 0.04 * Math.sin(i * 0.9)); d += `${i ? 'L' : 'M'}${(x + Math.cos(a) * rr).toFixed(1)} ${(y + Math.sin(a) * rr * 0.92).toFixed(1)}`; }
  return draw(d, k, { w: 8, c });
}

// ================= tags, banners, titles =================
/** Small date tag top-left: "1944" with a red square. */
export const dateTag = (label, x = 40, y = 34) =>
  `<g transform="translate(${x} ${y})"><rect width="${label.length * 17 + 56}" height="42" rx="6" fill="${P.paper}" ${st(3.5)}/>${text(16, 30, label, { size: 24, anchor: 'start' })}<rect x="${label.length * 17 + 24}" y="12" width="18" height="18" fill="${P.red}" ${st(2.5)}/></g>`;
/** Dark counter box top-right, e.g. "x2" with a small caption over it. */
export const counterTag = (value, caption = '', x = 1750, y = 34) =>  // keep tags OUTSIDE the moving camera layer
  `<g transform="translate(${x} ${y})"><rect width="130" height="${caption ? 84 : 62}" rx="8" fill="#2b2b2b" ${st(3.5)}/>${caption ? text(65, 24, caption, { size: 15, color: P.gold, spacing: 2 }) : ''}${text(65, caption ? 70 : 46, value, { size: 40, color: P.paper })}</g>`;
/** Red ribbon banner with folded ends; pops in with k. */
export function banner(x, y, label, k, { color = P.red, small = '' } = {}) {
  if (k <= 0) return '';
  const w = label.length * 22 + 80, d = shade(color, -0.3);
  const g = `<g transform="translate(${x} ${y})"><path d="M${-w / 2 - 50} 10 l40 -24 v48 z M${w / 2 + 50} 10 l-40 -24 v48 z" fill="${d}" ${st(3.5)}/>` +
    `<rect x="${-w / 2}" y="-30" width="${w}" height="58" fill="${color}" ${st(4)}/>${text(0, 10, label, { size: 32, color: P.paper, spacing: 2 })}` +
    (small ? text(0, -40, small, { size: 18, spacing: 3 }) : '') + `</g>`;
  return pop(g, k, x, y);
}
/** Scroll that unrolls sideways with k, title + red sub line, optional emblem. */
export function scroll(x, y, title, k, { sub = '', w = 840, emblem = true } = {}) {
  if (k <= 0) return '';
  const kk = cl(k / 0.7), ww = w * (1 - (1 - kk) ** 3), id = uid('sc');
  let g = `<clipPath id="${id}"><rect x="${x - ww / 2}" y="${y - 140}" width="${ww}" height="280"/></clipPath>`;
  g += `<g clip-path="url(#${id})">${rect(x - w / 2, y - 90, w, 180, P.paper, st(4))}<path d="M${x - w / 2 + 30} ${y - 70} H${x + w / 2 - 30} M${x - w / 2 + 30} ${y + 70} H${x + w / 2 - 30}" stroke="${P.red}" stroke-width="3"/>`;
  const tk = cl((k - 0.6) / 0.4);
  g += `<g opacity="${tk}">${text(x + (emblem ? 40 : 0), y + 16, title, { size: 56 })}${sub ? text(x + (emblem ? 40 : 0), y + 54, sub, { size: 22, color: P.red, spacing: 3 }) : ''}`;
  if (emblem) g += `<circle cx="${x - w / 2 + 110}" cy="${y}" r="44" fill="${P.paper}" ${st(4)}/><path d="M${x - w / 2 + 84} ${y} h52 M${x - w / 2 + 110} ${y - 26} v52" ${st(6)}/>`;
  g += `</g></g>`;
  for (const sx of [x - ww / 2, x + ww / 2]) g += `<rect x="${sx - 22}" y="${y - 110}" width="44" height="220" rx="20" fill="${P.paper2}" ${st(4)}/><rect x="${sx - 10}" y="${y - 126}" width="20" height="252" rx="8" fill="${P.woodDark}" ${st(3)}/>`;
  return g;
}
/** Wall calendar with a red header; circles day `circle` (drawn on at k2) and crosses days in `cross`. */
export function calendar(x, y, { month = 'JULY', year = '1945', first = 0, days = 31, circle = null, k2 = 1, cross = [], s = 1 } = {}) {
  let g = `<g transform="translate(${x} ${y}) scale(${s})">` + rect(-200, -40, 400, 470, '#fbf8ef', st(4)) + rect(-200, -40, 400, 80, P.red, st(4)) + text(0, 18, year, { size: 44, color: P.paper }) + text(0, 86, month, { size: 32, color: P.red });
  'SMTWTFS'.split('').forEach((c, i) => { g += text(-160 + i * 53, 126, c, { size: 18, color: P.mute }); });
  for (let d = 1; d <= days; d++) {
    const i = d - 1 + first, cx = -160 + (i % 7) * 53, cy = 170 + Math.floor(i / 7) * 52;
    g += text(cx, cy, d, { size: 26, color: i % 7 === 0 ? P.red : INK });
    if (cross.includes(d)) g += `<path d="M${cx - 16} ${cy - 26} l32 32 m0 -32 l-32 32" stroke="${P.red}" stroke-width="4" opacity=".8"/>`;
    if (circle === d) g += ring(cx, cy - 9, 26, k2);
  }
  for (const rx of [-120, 120]) g += `<rect x="${rx - 8}" y="-58" width="16" height="36" rx="6" fill="${P.metal}" ${st(3)}/>`;
  return g + '</g>';
}
/** Portrait card (character card): art = svg drawn inside (local coords, centre 0,0 of the picture window), label strip below,
 *  optional stamp label, highlighted = lifted with a gold edge. */
export function card(x, y, { w = 230, h = 300, art = '', label = '', stampLabel = '', stampAt = 0, t = 0, highlighted = false, dim = false, tilt = 0, bg = P.tealLight } = {}) {
  const id = uid('cd'), lift = highlighted ? -24 : 0;
  let g = `<g transform="translate(${x} ${y + lift}) rotate(${tilt})" opacity="${dim ? 0.55 : 1}">` + rect(-w / 2 + 8, -h / 2 + 12, w, h, '#000', 'opacity=".2" rx="10"') +
    rect(-w / 2, -h / 2, w, h, P.paper, `stroke="${highlighted ? P.gold : INK}" stroke-width="${highlighted ? 8 : 4}" rx="10"`) +
    `<clipPath id="${id}"><rect x="${-w / 2 + 16}" y="${-h / 2 + 16}" width="${w - 32}" height="${h - 86}" rx="6"/></clipPath>` +
    `<g clip-path="url(#${id})">${rect(-w / 2, -h / 2, w, h, bg)}<g transform="translate(0 ${-h / 2 + 16 + (h - 86) / 2})">${art}</g></g>` +
    rect(-w / 2 + 16, h / 2 - 62, w - 32, 46, highlighted ? P.red : INK, 'rx="4"') + text(0, h / 2 - 30, label, { size: 22, color: P.paper, spacing: 2 });
  if (stampLabel) g += stamp(t, stampAt, 0, -10, stampLabel, { size: 30, rot: -14 });
  return g + '</g>';
}
/** Name tag (lower third pointer under a person): small role line + name. */
export const nameTag = (x, y, name, role = '') =>
  `<g transform="translate(${x} ${y})"><rect x="${-name.length * 9 - 30}" y="-24" width="${name.length * 18 + 60}" height="48" rx="24" fill="${P.paper}" ${st(3.5)}/><circle cx="${-name.length * 9 - 12}" cy="0" r="22" fill="${P.red}" ${st(3)}/>` +
  `${text(10, 9, name, { size: 24, spacing: 1 })}${role ? text(10, -34, role, { size: 16, color: P.paper, spacing: 3 }) : ''}</g>`;
/** Pointer label over a person/thing: small paper label with a stem down to (x, y). */
export const pointLabel = (x, y, label, { up = 90, color = P.paper, tc = INK } = {}) =>
  `<path d="M${x} ${y} V${y - up + 20}" ${st(3)}/><rect x="${x - label.length * 8 - 18}" y="${y - up - 16}" width="${label.length * 16 + 36}" height="36" rx="5" fill="${color}" ${st(3)}/>${text(x, y - up + 9, label, { size: 20, color: tc, spacing: 2 })}`;

// ================= explainer objects =================
/** Chalkboard with a wooden frame. Write with chalkText / tally inside. */
export const chalkboard = (x, y, w, h) => rect(x - 18, y - 18, w + 36, h + 36, P.woodDark, st(5) + ' rx="8"') + rect(x, y, w, h, P.chalk, st(3)) +
  `<path d="M${x + 40} ${y + h * 0.3} q200 -40 400 10 M${x + 80} ${y + h * 0.7} q300 30 500 -20" stroke="#fff" stroke-width="20" opacity=".05"/>` + rect(x + w * 0.2, y + h + 10, w * 0.6, 18, P.woodLight, st(3));
export const chalkText = (x, y, s, { size = 60, op = 1, anchor = 'start' } = {}) => text(x, y, s, { size, color: '#f2f0e6', font: 'HT Hand', weight: 700, op, anchor, spacing: 0 });
/** Tally marks (groups of five) drawn on one by one: n marks, each appearing at at + i*gap. */
export function tally(t, x, y, n, at, { gap = 0.15, c = '#f2f0e6', h = 110 } = {}) {
  let g = '';
  for (let i = 0; i < n; i++) {
    const k = cl((t - at - i * gap) / 0.12), grp = Math.floor(i / 5), j = i % 5, gx = x + grp * 150;
    g += j < 4 ? draw(`M${gx + j * 26} ${y} l4 ${h}`, k, { w: 8, c }) : draw(`M${gx - 14} ${y + h * 0.7} L${gx + 100} ${y + h * 0.25}`, k, { w: 8, c });
  }
  return g;
}
/** Balance scale; tilt -1..1 (+ = right side down). left/right = svg drawn in each pan (local 0,0 = pan centre). */
export function balance(x, y, tilt, { left = '', right = '', leftLabel = '', rightLabel = '' } = {}) {
  const a = tilt * 14, r = 300, dy = Math.sin(a * Math.PI / 180) * r;
  const pan = (px, py, art, lab) => `<path d="M${px - 90} ${py} L${px} ${py - 160} L${px + 90} ${py}" fill="none" ${st(3)}/><path d="M${px - 110} ${py} Q${px} ${py + 70} ${px + 110} ${py} Z" fill="${P.gold}" ${st(4)}/><g transform="translate(${px} ${py - 30})">${art}</g>` + (lab ? `<rect x="${px - 80}" y="${py + 50}" width="160" height="36" fill="${P.paper}" ${st(3)}/>${text(px, py + 77, lab, { size: 20, spacing: 2 })}` : '');
  return `<path d="M${x} ${y + 360} V${y}" ${st(14)} stroke="${P.gold}"/><path d="M${x} ${y + 360} V${y}" ${st(4)} fill="none"/><path d="M${x - 120} ${y + 380} H${x + 120} L${x + 80} ${y + 350} H${x - 80} Z" fill="${P.gold}" ${st(4)}/>` +
    `<g><path d="M${x - r} ${y - dy} L${x + r} ${y + dy}" stroke="${P.gold}" stroke-width="16" stroke-linecap="round"/><path d="M${x - r} ${y - dy} L${x + r} ${y + dy}" fill="none" ${st(3)}/></g>` +
    pan(x - r, y - dy + 160, left, leftLabel) + pan(x + r, y + dy + 160, right, rightLabel) + `<circle cx="${x}" cy="${y}" r="16" fill="${P.gold}" ${st(4)}/>`;
}
/** Thought bubble (cloud) with svg inside, pops in with k; tail points to (tx, ty). */
export function thought(x, y, w, h, inner, k, tx, ty) {
  if (k <= 0) return '';
  let g = '';
  const n = 12;
  let d = '';
  for (let i = 0; i <= n; i++) { const a = (i / n) * Math.PI * 2, bx = x + Math.cos(a) * w / 2, by = y + Math.sin(a) * h / 2; d += i === 0 ? `M${bx} ${by}` : ` Q${x + Math.cos(a - Math.PI / n) * w * 0.62} ${y + Math.sin(a - Math.PI / n) * h * 0.66} ${bx} ${by}`; }
  g += `<path d="${d}Z" fill="#fff" ${st(5)}/>${inner}`;
  if (tx !== undefined) [0.35, 0.62, 0.82].forEach((f, i) => { g += `<circle cx="${x + (tx - x) * (0.55 + f * 0.45)}" cy="${y + h / 2 * 0.7 + (ty - y - h / 2 * 0.7) * f}" r="${18 - i * 5}" fill="#fff" ${st(4)}/>`; });
  return pop(g, k, x, y);
}
/** Dark status panel (top-right style) with segment bars: bars [{label, value 0..1, color}]. */
export function statusPanel(x, y, { title = 'STATUS', bars = [], w = 420 } = {}) {
  let g = rect(x, y, w, 60 + bars.length * 54, '#2b2b2b', st(4) + ' rx="8"') + rect(x, y, w, 36, P.red, 'rx="8"') + text(x + w / 2, y + 26, title, { size: 20, color: P.paper, spacing: 3 });
  bars.forEach((b, i) => {
    const by = y + 60 + i * 54, segs = 12, on = Math.round(b.value * segs);
    g += text(x + 20, by + 22, b.label, { size: 20, color: P.paper, anchor: 'start', spacing: 2 });
    for (let s = 0; s < segs; s++) g += rect(x + 150 + s * 18, by + 2, 13, 26, s < on ? (b.color || P.gold) : '#555', 'rx="2"');
    g += text(x + w - 20, by + 22, Math.round(b.value * 100) + '%', { size: 20, color: P.paper, anchor: 'end' });
  });
  return g;
}
/** Poster on a wall: art svg (local centre 0,0) and a red caption strip. */
export const poster = (x, y, { w = 280, h = 380, art = '', caption = '', bg = '#efe2c2' } = {}) =>
  `<g transform="translate(${x} ${y})">${rect(-w / 2, -h / 2, w, h, bg, st(4))}<g transform="translate(0 ${-30})">${art}</g>${rect(-w / 2 + 18, h / 2 - 70, w - 36, 52, P.red, st(3))}${text(0, h / 2 - 34, caption, { size: 26, color: P.paper, spacing: 2 })}</g>`;
/** Big title card (paper plate) e.g. a label for a type of person: "FEARLESS / FANATIC". */
export function plate(x, y, lines, k, { art = '', w = 760, h = 260 } = {}) {
  if (k <= 0) return '';
  let g = rect(x - w / 2 + 10, y - h / 2 + 12, w, h, '#000', 'opacity=".2" rx="12"') + rect(x - w / 2, y - h / 2, w, h, P.paper, st(5) + ' rx="12"') + rect(x - w / 2 + 14, y - h / 2 + 14, w - 28, h - 28, 'none', `stroke="${P.red}" stroke-width="3" rx="8"`);
  const tx = art ? x + 90 : x;
  if (art) g += `<g transform="translate(${x - w / 2 + 150} ${y})">${art}</g>`;
  lines.forEach((l, i) => { g += text(tx, y - (lines.length - 1) * 38 + i * 76 + 22, l, { size: 70, color: i === lines.length - 1 && lines.length > 1 ? P.red : INK }); });
  return pop(g, k, x, y);
}

// ================= vehicles (generic, recolour per video) =================
/** A generic propeller plane seen from the side, nose to the right. t spins the prop. */
export function plane(t, x, y, { s = 1, body = P.olive, belly = '#9aa08a', roundel = P.red, facing = 1 } = {}) {
  const pr = Math.abs(Math.sin(t * 40)) * 60;
  return `<g transform="translate(${x} ${y}) scale(${s * facing} ${s})">` +
    `<path d="M-260 -10 L-300 -90 L-250 -90 L-190 -20 Z" fill="${body}" ${st()}/>` +
    `<path d="M-280 -20 Q-200 -50 0 -46 Q170 -44 200 -10 Q210 18 170 26 Q0 36 -200 14 Q-270 6 -280 -20 Z" fill="${body}" ${st()}/>` +
    `<path d="M-250 4 Q0 30 180 22" stroke="${belly}" stroke-width="16" fill="none"/>` +
    `<path d="M30 -46 Q60 -86 120 -82 Q150 -60 140 -44 Z" fill="#9cc7c0" ${st()}/><path d="M78 -84 V-46" ${st(3)}/>` +
    `<path d="M-60 6 L90 4 L60 48 L-90 48 Z" fill="${shade(body, -0.15)}" ${st()}/><circle cx="-10" cy="-10" r="24" fill="${roundel}" stroke="#fff" stroke-width="6"/>` +
    `<rect x="196" y="-26" width="22" height="50" rx="6" fill="${P.metalDark}" ${st(3)}/><ellipse cx="226" cy="0" rx="8" ry="${(14 + pr).toFixed(1)}" fill="${P.metal}" opacity=".6" ${st(2)}/>` +
    `<path d="M-30 48 l-10 40 M70 46 l10 42" ${st(5)}/><circle cx="-40" cy="92" r="14" fill="${INK}"/><circle cx="80" cy="92" r="14" fill="${INK}"/></g>`;
}
/** A generic warship side view, bow to the right. */
export function ship(x, y, { s = 1, hull = '#6f7d86', facing = 1 } = {}) {
  return `<g transform="translate(${x} ${y}) scale(${s * facing} ${s})"><path d="M-420 -40 H420 L360 40 H-380 Z" fill="${hull}" ${st()}/><path d="M-380 10 H380" stroke="${shade(hull, -0.25)}" stroke-width="6"/>` +
    `<rect x="-140" y="-120" width="220" height="80" fill="${shade(hull, 0.12)}" ${st()}/><rect x="-60" y="-190" width="90" height="70" fill="${shade(hull, 0.12)}" ${st()}/><path d="M-20 -190 V-260 M-60 -240 H30" ${st(5)}/>` +
    `<rect x="160" y="-80" width="90" height="40" fill="${shade(hull, 0.1)}" ${st()}/><path d="M250 -64 H330" ${st(8)}/><path d="M-300 -64 H-220" ${st(8)}/><rect x="-310" y="-80" width="90" height="40" fill="${shade(hull, 0.1)}" ${st()}/></g>`;
}
