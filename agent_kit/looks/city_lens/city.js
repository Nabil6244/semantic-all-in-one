// city_lens pieces: SVG strings in 1920x1080 frame pixels, every one a pure function of a progress k (0..1).
//   import * as C from '/agent_kit/looks/city_lens/city.js';
//   s.innerHTML = C.defs() + C.sat('dt') + C.glowLoop(C.blob(960, 520, 330, 220, 3), K.prog(t, K.when('ring'), 1.2)) + ...;
// Maps:   sat (satellite picture from the `satellite` tool), nightGround, glowLoop/glowLine, route, river, zone, pin,
//         placeLabel, dots (parking lots, buildings lost), ring, layerStack (legend top right).
// Paper:  docCard (newspaper / code / report), table, bars, timeline, cycle, iconRow, crossSection, ad (old ad sheet).
// Type:   bigNumber ($100 M+ with its chip), yearTag (1957 / Intercity Freeway), chip, sourceLine, title.
import { P } from './palette.js';

const cl = (k) => Math.min(1, Math.max(0, k));
const back = (k) => { k = cl(k); const s = 1.5; return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2; };
const out3 = (k) => 1 - (1 - cl(k)) ** 3;
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
let _id = 0;
const uid = (p) => `${p}${++_id}`;

/** Put first in every <svg>: glow, shadow, dot grid, hatch. Resets ids so they stay the same every frame. */
export function defs() {
  _id = 0;
  return `<defs>
  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="9" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <filter id="soft"><feGaussianBlur stdDeviation="14"/></filter>
  <filter id="shadow" x="-10%" y="-10%" width="130%" height="140%"><feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#000" flood-opacity=".22"/></filter>
  <pattern id="dots" width="44" height="44" patternUnits="userSpaceOnUse"><circle cx="22" cy="22" r="1.6" fill="${P.grid}"/></pattern>
  <pattern id="pdots" width="44" height="44" patternUnits="userSpaceOnUse"><circle cx="22" cy="22" r="1.5" fill="${P.rule}"/></pattern>
  <pattern id="hatch" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0 V12" stroke="${P.red}" stroke-width="4" opacity=".7"/></pattern>
  </defs>`;
}

export const text = (x, y, s, { size = 28, color = '#fff', font = 'CL Sans', weight = 600, anchor = 'start', spacing = 0,
  italic = false, op = 1, upper = false } = {}) =>
  `<text x="${x}" y="${y}" font-family="'${font}'" font-size="${size}" font-weight="${weight}" fill="${color}" text-anchor="${anchor}" letter-spacing="${spacing}" opacity="${op}"${italic ? ' font-style="italic"' : ''}>${esc(upper ? String(s).toUpperCase() : s)}</text>`;
/** Any path drawn on with k. */
export const draw = (d, k, { w = 6, c = P.orange, fill = 'none', cap = 'round', dash = '' } = {}) => k <= 0 ? '' :
  `<path d="${d}" pathLength="1" stroke-dasharray="${dash || '1 1'}" stroke-dashoffset="${dash ? 0 : (1 - cl(k)).toFixed(4)}" fill="${fill}" stroke="${c}" stroke-width="${w}" stroke-linecap="${cap}" stroke-linejoin="round"/>`;
export const pop = (svg, k, cx, cy) => k <= 0 ? '' : `<g transform="translate(${cx} ${cy}) scale(${back(k).toFixed(4)}) translate(${-cx} ${-cy})">${svg}</g>`;
export const rise = (svg, k, dy = 40) => k <= 0 ? '' : `<g transform="translate(0 ${((1 - out3(k)) * dy).toFixed(1)})" opacity="${cl(k * 1.6).toFixed(3)}">${svg}</g>`;
export const fade = (svg, k) => k <= 0 ? '' : `<g opacity="${cl(k).toFixed(3)}">${svg}</g>`;

// ================= grounds =================
/** The satellite picture made by the `satellite` tool (scenes/<name>_sat.jpg), dark and grey so orange glows. lit: brighter. */
export const sat = (name, { lit = false, x = 0, y = 0, w = 1920, h = 1080 } = {}) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${P.sat}"/><image href="/@scene/${name}_sat.jpg" x="${x}" y="${y}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid slice" style="filter:${lit ? 'saturate(.45) brightness(.82) contrast(1.05)' : 'saturate(.18) brightness(.6) contrast(1.12)'}"/>`;
/** Dark navy map ground with a faint dot grid (for line maps: counties, rail, beltways). */
export const nightGround = () => `<rect width="1920" height="1080" fill="${P.night}"/><rect width="1920" height="1080" fill="url(#dots)" opacity=".7"/>`;
/** Warm paper ground with a faint dot grid (infographics, documents, charts). */
export const paperGround = (dots = true) => `<rect width="1920" height="1080" fill="${P.paper}"/>` + (dots ? `<rect width="1920" height="1080" fill="url(#pdots)" opacity=".5"/>` : '');

// ================= map marks =================
/** A soft closed loop around (cx, cy): the "downtown", the beltway, the district. seed changes its wobble. Returns path d. */
export function blob(cx, cy, rx, ry, seed = 1, n = 9) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2, j = 1 + 0.09 * Math.sin(i * 2.7 + seed * 1.9) + 0.05 * Math.cos(i * 4.1 + seed);
    pts.push([cx + Math.cos(a) * rx * j, cy + Math.sin(a) * ry * j]);
  }
  let d = '';
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    if (!i) d += `M${p1[0].toFixed(1)} ${p1[1].toFixed(1)}`;
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d + 'Z';
}
/** The signature mark: a glowing orange line drawn on (a freeway loop, a district edge). pulse 0..1 brightens it. */
export const glowLoop = (d, k, { c = P.orange, w = 7, pulse = 0 } = {}) => k <= 0 ? '' :
  `<g filter="url(#glow)" opacity="${(0.85 + 0.15 * pulse).toFixed(3)}">${draw(d, k, { w: w + 2 * pulse, c })}</g>`;
export const glowLine = glowLoop;
/** A road/rail/line on a night map (yellow by default), drawn on; dashed: rail. */
export const route = (d, k, { c = P.yellow, w = 5, dashed = false } = {}) => dashed && k > 0 ?
  `<g opacity="${cl(k * 2)}"><path d="${d}" fill="none" stroke="${c}" stroke-width="${w}" stroke-dasharray="14 10"/></g>` : draw(d, k, { w, c });
/** A river: wide blue band drawn on. */
export const river = (d, k, { w = 26, c = P.blue } = {}) => draw(d, k, { w, c, cap: 'butt' });
/** A filled area fading in: a park (green), a parking zone (red), a county (ochre). hatch: red hatching. */
export const zone = (d, k, { c = P.green, op = 0.9, stroke = '', hatch = false } = {}) => k <= 0 ? '' :
  `<path d="${d}" fill="${hatch ? 'url(#hatch)' : c}" opacity="${(op * out3(k)).toFixed(3)}"${stroke ? ` stroke="${stroke}" stroke-width="4"` : ''}/>`;
/** A place pin: white ring dot + black chip label. side: right | left. */
export function pin(x, y, label, k, { side = 'right', c = '#fff', size = 24 } = {}) {
  if (k <= 0) return '';
  const w = label.length * size * 0.54 + 24, lx = side === 'right' ? x + 22 : x - 22 - w;
  return pop(`<circle cx="${x}" cy="${y}" r="10" fill="${c}"/><circle cx="${x}" cy="${y}" r="17" fill="none" stroke="${c}" stroke-width="3" opacity=".6"/>`, k, x, y) +
    rise(`<rect x="${lx}" y="${y - size * 0.85}" width="${w}" height="${size * 1.55}" fill="${P.chip}"/>` +
      text(lx + 12, y + size * 0.35, label, { size, color: '#fff' }), k, 16);
}
/** An italic serif place name (on maps: Missouri River, Downtown). */
export const placeLabel = (x, y, s, k, { size = 46, color = '#fff', anchor = 'start', rot = 0 } = {}) => k <= 0 ? '' :
  `<g opacity="${cl(k * 1.5)}"${rot ? ` transform="rotate(${rot} ${x} ${y})"` : ''}>${text(x, y, s, { size, color, font: 'CL Serif', italic: true, anchor })}</g>`;
/** Many small squares popping one by one (parking lots, lost buildings, crashes). pts [[x,y],...]. */
export function dots(pts, k, { c = P.red, size = 18, gap = 0.6 } = {}) {
  let g = '';
  pts.forEach(([x, y], i) => {
    const kk = cl(k * (1 + gap * pts.length) - i * gap);
    if (kk > 0) g += pop(`<rect x="${x - size / 2}" y="${y - size / 2}" width="${size}" height="${size}" fill="${c}" rx="2"/>`, kk, x, y);
  });
  return g;
}
/** Seeded scatter of n points inside a blob-like ellipse (for dots()). */
export function scatter(cx, cy, rx, ry, n, seed = 1) {
  const pts = [];
  let s = seed * 9301 + 49297;
  const r = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  while (pts.length < n) { const x = r() * 2 - 1, y = r() * 2 - 1; if (x * x + y * y < 0.9) pts.push([cx + x * rx, cy + y * ry]); }
  return pts;
}
/** A thin white ring growing around a point (focus). */
export const ring = (x, y, r, k, { c = '#fff', w = 4 } = {}) => k <= 0 ? '' :
  `<circle cx="${x}" cy="${y}" r="${(r * back(k)).toFixed(1)}" fill="none" stroke="${c}" stroke-width="${w}" opacity="${cl(k * 2)}"/>`;
/** A filled glowing spot (an interchange, a junction). */
export const hotspot = (x, y, r, k, { c = P.orange } = {}) => k <= 0 ? '' :
  `<ellipse cx="${x}" cy="${y}" rx="${r * back(k)}" ry="${r * 0.62 * back(k)}" fill="${c}" opacity=".75" filter="url(#glow)"/>`;

/** The layer legend top right: stacked isometric tiles, one per idea the video adds ("01 RIVER", "02 PARKING"...).
 *  items [{label, color}], shown = how many are in so far (can be fractional for the newest one popping in). */
export function layerStack(items, shown, { x = 1770, y = 120, size = 46 } = {}) {
  let g = `<rect x="${x - 230}" y="${y - 74}" width="${330}" height="${74 + items.length * 30 + 60}" fill="${P.chip}" opacity=".72"/>`;
  g += text(x - 214, y - 48, 'THE STACK', { size: 13, color: '#fff', spacing: 2, op: 0.6 });
  items.forEach((it, i) => {
    const k = cl(shown - i); if (k <= 0) return;
    const cy = y + (items.length - 1 - i) * 14 - 6 * (1 - back(k)) * 6, s = size;
    g += `<g opacity="${cl(k * 2)}"><path d="M${x} ${cy - s * 0.32} L${x + s} ${cy} L${x} ${cy + s * 0.32} L${x - s} ${cy} Z" fill="${it.color}" stroke="${P.chip}" stroke-width="1.5"/>` +
      `<path d="M${x - s} ${cy} L${x} ${cy + s * 0.32} L${x} ${cy + s * 0.32 + 8} L${x - s} ${cy + 8} Z" fill="${it.color}" opacity=".6"/></g>`;
    g += text(x - 214, y - 14 + i * 26, `${String(i + 1).padStart(2, '0')} ${it.label}`, { size: 15, color: '#fff', spacing: 1.5, op: cl(k * 2), upper: true });
  });
  return g;
}

// ================= type =================
/** A black (or orange/red/green) chip with text. anchor start|end. */
export function chip(x, y, s, { bg = P.chip, fg = '#fff', size = 24, anchor = 'start', k = 1 } = {}) {
  if (k <= 0) return '';
  const w = String(s).length * size * 0.53 + 26, lx = anchor === 'end' ? x - w : x;
  return rise(`<rect x="${lx}" y="${y}" width="${w}" height="${size * 1.6}" fill="${bg}"/>` + text(lx + 13, y + size * 1.15, s, { size, color: fg }), k, 12);
}
/** The big money/size number, top right by default: "$3" + unit "B" + a chip under it. Count it up with K.countUp. */
export function bigNumber(value, unit, k, { x = 1820, y = 190, size = 150, chipText = '', c = P.orange, anchor = 'end', chipBg = P.chip } = {}) {
  if (k <= 0) return '';
  const u = unit ? `<tspan font-size="${size * 0.55}" dx="${size * 0.12}">${esc(unit)}</tspan>` : '';
  const g = `<text x="${x}" y="${y}" font-family="'CL Sans'" font-weight="800" font-size="${size}" fill="${c}" text-anchor="${anchor}" letter-spacing="-2">${esc(value)}${u}</text>` +
    (chipText ? chip(x, y + 24, chipText, { anchor, size: 22, bg: chipBg, k: cl(k * 1.5 - 0.3) }) : '');
  return rise(g, k, 30);
}
/** The opening tag on archive footage: big upright year, italic serif subject, small place/date line. */
export function yearTag(year, subject, line, k, { x = 80, y = 520, color = '#fff' } = {}) {
  if (k <= 0) return '';
  return rise(text(x, y, year, { size: 110, font: 'CL Serif', weight: 700, color }) +
    text(x + 4, y + 58, subject, { size: 46, font: 'CL Serif', italic: true, color }) +
    text(x + 6, y + 96, line, { size: 20, color, op: 0.85 }), k, 24);
}
/** A section title on paper or a map: italic serif, top left, with a short rule. */
export const title = (s, k, { x = 96, y = 140, size = 64, color = P.ink } = {}) => k <= 0 ? '' :
  rise(text(x, y, s, { size, font: 'CL Serif', italic: true, color }) + `<rect x="${x}" y="${y + 18}" width="${(s.length * size * 0.42 * out3(k)).toFixed(0)}" height="2" fill="${color}" opacity=".35"/>`, k, 18);
/** The tiny source line, bottom left (every map, chart and document has one). */
export const sourceLine = (s, { color = '#fff', op = 0.5 } = {}) => text(48, 1050, s, { size: 14, color, op, spacing: 1, upper: true });

// ================= paper pieces =================
/** A document card: newspaper page, zoning code, report. head (masthead), heading, lines of grey body, a quote with
 *  a yellow highlight sweeping on (hl 0..1). k slides it in. */
export function docCard(x, y, w, h, { head = '', date = '', heading = '', quote = '', hl = 0, lines = 8, rot = -1.5 } = {}, k = 1) {
  if (k <= 0) return '';
  let g = `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="#f6f1e4" filter="url(#shadow)"/>`;
  let cy = y + 56;
  if (head) { g += text(x + w / 2, cy, head, { size: 40, font: 'CL Serif', weight: 700, color: P.ink, anchor: 'middle' }) + `<rect x="${x + 30}" y="${cy + 16}" width="${w - 60}" height="3" fill="${P.ink}"/>`; cy += 50; }
  if (date) g += text(x + w - 30, y + 30, date, { size: 15, color: P.mute, anchor: 'end' });
  if (heading) { g += text(x + 36, cy + 30, heading, { size: 34, font: 'CL Serif', weight: 700, color: P.ink }); cy += 58; }
  if (quote) {
    const qw = Math.min(w - 72, quote.length * 15.5);
    g += `<rect x="${x + 32}" y="${cy + 2}" width="${(qw * cl(hl)).toFixed(1)}" height="40" fill="${P.yellow}" opacity=".85"/>`;
    g += text(x + 36, cy + 32, `“${quote}”`, { size: 28, font: 'CL Serif', italic: true, weight: 600, color: P.ink });
    cy += 64;
  }
  for (let i = 0; i < lines && cy + 20 < y + h - 20; i++, cy += 24)
    g += `<rect x="${x + 36}" y="${cy}" width="${(w - 72) * (i % 4 === 3 ? 0.62 : 0.96)}" height="9" fill="${P.rule}"/>`;
  return `<g transform="rotate(${rot} ${x + w / 2} ${y + h / 2})">${rise(g, k, 60)}</g>`;
}
/** A comparison table card. cols ['', 'Old office building', 'Surface lot'], rows [['Upkeep','High','Minimal'],...].
 *  Rows arrive one by one with k; hi = index of a row to fill red. */
export function table(x, y, cols, rows, k, { colW = 300, rowH = 64, ttl = '', hi = -1 } = {}) {
  if (k <= 0) return '';
  const w = colW * cols.length;
  let g = ttl ? text(x, y - 30, ttl, { size: 34, color: P.ink, weight: 400 }) : '';
  g += `<rect x="${x - 20}" y="${y - 10}" width="${w + 40}" height="${rowH * (rows.length + 1) + 20}" fill="${P.card}" filter="url(#shadow)"/>`;
  cols.forEach((c, j) => { g += text(x + j * colW + 8, y + rowH * 0.6, c, { size: 22, color: P.ink }); });
  g += `<rect x="${x}" y="${y + rowH * 0.85}" width="${w}" height="2" fill="${P.ink}"/>`;
  rows.forEach((r, i) => {
    const kk = cl(k * (rows.length + 1) - i - 0.5); if (kk <= 0) return;
    const ry = y + rowH * (i + 1);
    let row = i === hi ? `<rect x="${x}" y="${ry + 4}" width="${w}" height="${rowH - 6}" fill="${P.red}"/>` : '';
    r.forEach((c, j) => { row += text(x + j * colW + 8, ry + rowH * 0.62, c, { size: 24, color: i === hi ? '#fff' : P.ink, weight: j ? 400 : 600, upper: !j }); });
    row += `<rect x="${x}" y="${ry + rowH}" width="${w}" height="1" fill="${P.rule}"/>`;
    g += fade(row, kk);
  });
  return g;
}
/** Horizontal bars growing (trip time, share of jobs). bars [{label, value, color}], max = full width value. */
export function bars(x, y, w, bars_, k, { max = 0, barH = 54, gap = 34, ttl = '' } = {}) {
  const m = max || Math.max(...bars_.map((b) => b.value));
  let g = ttl ? text(x - 200, y - 40, ttl, { size: 30, color: P.ink, weight: 400 }) : '';
  g += `<rect x="${x}" y="${y - 20}" width="2" height="${bars_.length * (barH + gap) + 10}" fill="${P.ink}"/>`;
  bars_.forEach((b, i) => {
    const kk = out3(cl(k * 1.4 - i * 0.25)), by = y + i * (barH + gap);
    g += text(x - 20, by + barH * 0.65, b.label, { size: 24, color: P.ink, anchor: 'end', weight: 400 });
    g += `<rect x="${x + 2}" y="${by}" width="${(w * b.value / m * kk).toFixed(1)}" height="${barH}" fill="${b.color || P.red}"/>`;
  });
  return g;
}
/** Vertical bar pair or set (normal day vs record day). */
export function columns(x, y, h, cols, k, { colW = 110, gap = 120, max = 0 } = {}) {
  const m = max || Math.max(...cols.map((c) => c.value));
  let g = `<rect x="${x - 30}" y="${y}" width="${cols.length * (colW + gap) + 30}" height="2" fill="${P.ink}"/><rect x="${x - 30}" y="${y - h - 20}" width="2" height="${h + 20}" fill="${P.ink}"/>`;
  cols.forEach((c, i) => {
    const kk = out3(cl(k * 1.4 - i * 0.3)), ch = h * c.value / m * kk, cx = x + i * (colW + gap);
    g += `<rect x="${cx}" y="${y - ch}" width="${colW}" height="${ch}" fill="${c.color || P.orange}"/>` + text(cx + colW / 2, y + 40, c.label, { size: 22, color: P.ink, anchor: 'middle', weight: 400 });
    if (c.chip && kk > 0.9) g += chip(cx + colW / 2 - 40, y - ch - 50, c.chip, { size: 20, bg: P.orange, fg: P.chip });
  });
  return g;
}
/** A timeline ruler: from/to labels, tick marks, a bar filling from start, marks [{at:0..1, label}]. */
export function timeline(x, y, w, from, to, k, { marks = [], c = P.orange, chipText = '' } = {}) {
  let g = `<rect x="${x}" y="${y}" width="${w}" height="2" fill="${P.mute}"/>`;
  g += chip(x, y - 60, from, { size: 20, bg: P.red, k: cl(k * 3) }) + chip(x + w, y - 60, to, { size: 20, anchor: 'end', k: cl(k * 3 - 1.5) });
  g += `<rect x="${x}" y="${y - 3}" width="${(w * out3(k)).toFixed(1)}" height="8" fill="${c}"/>`;
  marks.forEach((m, i) => {
    const kk = cl(k * 1.2 - m.at); if (kk <= 0) return;
    g += `<rect x="${x + w * m.at - 1}" y="${y - 14}" width="3" height="30" fill="${P.ink}"/>` + chip(x + w * m.at - 40, y + 26, m.label, { size: 18, bg: P.orange, fg: P.chip });
  });
  if (chipText) g += chip(x + w / 2 - 60, y + 26, chipText, { size: 18, bg: P.orange, fg: P.chip, k: cl(k * 2 - 1) });
  return g;
}
/** A feedback loop: nodes [{label, icon}] around a circle with arrows drawn between them (cause and effect). */
export function cycle(cx, cy, r, nodes, k, { c = P.red } = {}) {
  let g = '';
  const n = nodes.length;
  nodes.forEach((nd, i) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2, x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
    const kk = cl(k * (n + 1) - i);
    if (kk <= 0) return;
    const a2 = a + (Math.PI * 2) / n;
    if (kk > 0.4) {
      const sx = cx + Math.cos(a + 0.3) * r, sy = cy + Math.sin(a + 0.3) * r, ex = cx + Math.cos(a2 - 0.3) * r, ey = cy + Math.sin(a2 - 0.3) * r;
      g += draw(`M${sx.toFixed(1)} ${sy.toFixed(1)} A${r} ${r} 0 0 1 ${ex.toFixed(1)} ${ey.toFixed(1)}`, cl(kk * 1.6 - 0.6), { w: 3, c: P.mute });
    }
    g += pop(`<circle cx="${x}" cy="${y}" r="44" fill="${P.card}" stroke="${i === 0 ? P.orange : c}" stroke-width="4"/>` +
      text(x, y + 14, nd.icon || '•', { size: 38, color: i === 0 ? P.orange : c, anchor: 'middle', weight: 800 }), kk, x, y);
    const right = Math.cos(a) >= -0.1;
    g += fade(text(x + (right ? 64 : -64), y + 8, nd.label, { size: 22, color: P.ink, anchor: right ? 'start' : 'end', spacing: 1.5, upper: true }), kk);
  });
  return g;
}
/** A row of n small icons (cities, cars, blocks), the hi ones in orange: "4 of 10". icon: any short svg path d at 0,0 (32px). */
export function iconRow(x, y, n, k, { hi = [], per = 10, gap = 52, icon = 'M-14 10 H14 V-6 L0 -14 L-14 -6 Z', c = P.ink } = {}) {
  let g = '';
  for (let i = 0; i < n; i++) {
    const kk = cl(k * (n * 0.35 + 1) - i * 0.35); if (kk <= 0) continue;
    const ix = x + (i % per) * gap, iy = y + Math.floor(i / per) * gap;
    g += pop(`<path d="${icon}" transform="translate(${ix} ${iy})" fill="${hi.includes(i) ? P.orange : 'none'}" stroke="${hi.includes(i) ? P.orange : c}" stroke-width="3" stroke-linejoin="round"/>`, kk, ix, iy);
  }
  return g;
}
/** A north-south cross-section: grey ground profile, water on the low side, outlined skyscrapers rising on the high side.
 *  profile: [[x, y], ...] ground top line (frame px, left to right); towers [{x, w, h}] standing on the profile;
 *  water: y level filling the low part (or 0); labels [{x, y, s}] italic serif. k: ground draws, then towers rise. */
export function crossSection(profile, k, { towers = [], water = 0, labels = [], ground = '#55595c', base = 1000 } = {}) {
  const d = `M${profile[0][0]} ${base} ` + profile.map(([x, y]) => `L${x} ${y}`).join(' ') + ` L${profile[profile.length - 1][0]} ${base} Z`;
  let g = `<path d="${d}" fill="${ground}" opacity="${cl(k * 2)}"/>`;
  if (water) g += `<rect x="${profile[0][0]}" y="${water}" width="${(profile[profile.length - 1][0] - profile[0][0]) * 0.32}" height="${base - water}" fill="${P.blue}" opacity="${0.85 * cl(k * 2 - 0.4)}"/>`;
  const topAt = (x) => { for (let i = 1; i < profile.length; i++) if (x <= profile[i][0]) { const [x0, y0] = profile[i - 1], [x1, y1] = profile[i]; return y0 + (y1 - y0) * (x - x0) / Math.max(1, x1 - x0); } return profile[profile.length - 1][1]; };
  towers.forEach((tw, i) => {
    const kk = out3(cl(k * 2 - 0.8 - i * 0.08)); if (kk <= 0) return;
    const gy = topAt(tw.x + tw.w / 2), h = tw.h * kk;
    g += `<rect x="${tw.x}" y="${gy - h}" width="${tw.w}" height="${h}" fill="${P.card}" stroke="${P.ink}" stroke-width="2"/>`;
    for (let wy = gy - h + 14; wy < gy - 10; wy += 22) g += `<rect x="${tw.x + 6}" y="${wy}" width="${tw.w - 12}" height="2" fill="${P.rule}"/>`;
  });
  labels.forEach((l) => { g += placeLabel(l.x, l.y, l.s, cl(k * 2 - 1), { size: 34, color: l.color || P.ink }); });
  return g;
}

/** Placement helper: lon/lat -> frame px for a satellite or vector map proj (same as K.lonlat). */
export function lonlat(proj, lon, lat) {
  const r = Math.PI / 180, y = Math.log(Math.tan(Math.PI / 4 + Math.max(-85, Math.min(85, lat)) * r / 2));
  return [(lon * r - proj.x0) * proj.scale + proj.ox, (proj.y1 - y) * proj.scale + proj.oy];
}
/** A path d through lon/lat points [[lon, lat], ...] (a freeway, a river, a rail line). closed: back to the start. */
export const geoPath = (proj, pts, closed = false) => pts.map(([lo, la], i) => { const [x, y] = lonlat(proj, lo, la); return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`; }).join(' ') + (closed ? ' Z' : '');
/** A smooth curve through frame points [[x, y], ...] (Catmull-Rom); closed: a loop (rings, district edges). */
export function smoothPath(pts, closed = false) {
  const n = pts.length, at = (i) => pts[closed ? (i + n) % n : Math.max(0, Math.min(n - 1, i))];
  let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
    d += ` C${(p1[0] + (p2[0] - p0[0]) / 6).toFixed(1)} ${(p1[1] + (p2[1] - p0[1]) / 6).toFixed(1)} ${(p2[0] - (p3[0] - p1[0]) / 6).toFixed(1)} ${(p2[1] - (p3[1] - p1[1]) / 6).toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d + (closed ? 'Z' : '');
}
/** smoothPath through lon/lat points on a map proj (a ring road, a bayou, a coastline). */
export const geoSmooth = (proj, pts, closed = false) => smoothPath(pts.map(([lo, la]) => lonlat(proj, lo, la)), closed);
