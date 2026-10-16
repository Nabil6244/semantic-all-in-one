// PRIMITIVES: the drawing pieces every template is built from, in the What If look (tm_theme colours and fonts). One function per
// primitive: draw(c, it, tr, alpha) where c = { g, T, W, H, image(name) }, it = a built item (lib/tpl.mjs), tr = seconds since the layer
// started. Positions are fractions of the frame ([0.5, 0.5] = the centre); radii and sizes are fractions of the frame HEIGHT (round stays
// round); line widths and type sizes are px at 1920 wide (T.S scales them). Pure functions of tr: the same frame every time.
import { param, hex, flashing, visibility } from './tpl.mjs';
import { drawIcon } from './icons.mjs';
import { fmt, C } from '../layers/tm_theme.mjs';

const TAU = Math.PI * 2;
const rnd = (seed) => { let s = (seed >>> 0) || 1; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); };
const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * (3 - 2 * k); };

/** The item's colour at tr (a flash shows its flash colour). */
const colourOf = (it, tr, name = 'color', d = '#FFFFFF') => hex(flashing(it, tr) && name === 'color' ? it._flash.color : param(it, name, tr, d));
const xy = (c, p) => [p[0] * c.W, p[1] * c.H];

/** Points [[x, y] fractions] -> sampled px polyline (smooth: a curve through the midpoints). */
export function polyline(c, pts, smoothCurve = false) {
  const P = pts.map((p) => xy(c, p));
  if (!smoothCurve || P.length < 3) return P;
  const out = [P[0]];
  for (let i = 1; i < P.length - 1; i++) {
    const a = i === 1 ? P[0] : [(P[i - 1][0] + P[i][0]) / 2, (P[i - 1][1] + P[i][1]) / 2], b = P[i], e = i === P.length - 2 ? P[i + 1] : [(P[i][0] + P[i + 1][0]) / 2, (P[i][1] + P[i + 1][1]) / 2];
    for (let k = 1; k <= 16; k++) { const t = k / 16, u = 1 - t; out.push([u * u * a[0] + 2 * u * t * b[0] + t * t * e[0], u * u * a[1] + 2 * u * t * b[1] + t * t * e[1]]); }
  }
  return out;
}
function lengths(P) { const L = [0]; for (let i = 1; i < P.length; i++) L.push(L[i - 1] + Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1])); return L; }
/** The point at fraction k of a polyline's length, and its direction. */
export function pointAt(P, k) {
  const L = lengths(P), want = Math.min(1, Math.max(0, k)) * L[L.length - 1];
  for (let i = 1; i < P.length; i++) if (L[i] >= want) {
    const seg = L[i] - L[i - 1] || 1, u = (want - L[i - 1]) / seg;
    return { x: P[i - 1][0] + (P[i][0] - P[i - 1][0]) * u, y: P[i - 1][1] + (P[i][1] - P[i - 1][1]) * u, a: Math.atan2(P[i][1] - P[i - 1][1], P[i][0] - P[i - 1][0]) };
  }
  const n = P.length - 1; return { x: P[n][0], y: P[n][1], a: n ? Math.atan2(P[n][1] - P[n - 1][1], P[n][0] - P[n - 1][0]) : 0 };
}
function strokePart(g, P, k) {
  const L = lengths(P), want = Math.min(1, Math.max(0, k)) * L[L.length - 1];
  g.beginPath(); g.moveTo(P[0][0], P[0][1]);
  for (let i = 1; i < P.length; i++) {
    if (L[i] <= want) { g.lineTo(P[i][0], P[i][1]); continue; }
    const seg = L[i] - L[i - 1] || 1, u = (want - L[i - 1]) / seg; g.lineTo(P[i - 1][0] + (P[i][0] - P[i - 1][0]) * u, P[i - 1][1] + (P[i][1] - P[i - 1][1]) * u); break;
  }
  g.stroke();
}
function arrowHead(g, x, y, a, size, color) {
  g.save(); g.fillStyle = color; g.translate(x, y); g.rotate(a);
  g.beginPath(); g.moveTo(0, 0); g.lineTo(-size, -size * 0.55); g.lineTo(-size * 0.7, 0); g.lineTo(-size, size * 0.55); g.closePath(); g.fill(); g.restore();
}
function fontOf(T, kind, px, weight) {
  if (kind === 'display') return T.display(px);
  if (kind === 'mono') return T.mono(px, weight || 600);
  if (kind === 'serif') return `italic ${weight || 400} ${Math.round(px * T.S)}px "Times New Roman", Times, Georgia, serif`;
  return T.sans(px, weight || 800);
}
const up = (it, s) => (it.case === 'keep' ? String(s) : String(s).toUpperCase());

/** A label with an optional small kicker above and a mono line under it (the reference's two-line callout). */
function label(c, it, tr, x, y, { text, sub, size = 26, align = 'left', color, subColor, font = 'sans', glow = false } = {}) {
  const { T } = c;
  if (it.kicker) T.text(up(it, it.kicker), x, y - size * 1.25 * T.S, { font: T.mono(Math.max(13, size * 0.5), 600), track: 3, color: hex(it.kicker_color || 'cyan'), align, shadow: 0 });
  let w = 0;
  if (it.maxw && text != null && text !== '') {            // the line never runs out of its box or off the frame: smaller type instead
    const lim = it.maxw * c.W;
    while (size > 10 && T.measure(up(it, text), fontOf(T, font, size, it.weight), it.track ?? (font === 'mono' ? 1 : 2.5)) > lim) size -= 1;
  }
  if (text != null && text !== '') w = T.text(up(it, text), x, y, { font: fontOf(T, font, size, it.weight), track: it.track ?? (font === 'mono' ? 1 : 2.5), color, align,
    glow: glow ? (typeof glow === 'string' ? glow : 'rgba(255,214,160,0.3)') : null, shadow: it.shadow ?? 0.6 });
  if (sub) T.text(up(it, sub), x, y + (size * 0.5 + 18) * T.S, { font: T.mono(it.sub_size || Math.max(14, size * 0.52), 600), track: 1.5, color: hex(subColor || it.sub_color || 'amber'), align, shadow: 0 });
  return w;
}

function sideLabel(c, it, tr, x, y, R) {
  if (!it.label) return;
  const side = it.label_side || 'right', gap = (it.label_gap ?? 18) * c.T.S;
  const at = { right: [x + R + gap, y + 8 * c.T.S, 'left'], left: [x - R - gap, y + 8 * c.T.S, 'right'], top: [x, y - R - gap, 'center'], bottom: [x, y + R + gap + 24 * c.T.S, 'center'] }[side];
  label(c, it, tr, at[0], at[1], { text: param(it, 'label', tr, ''), sub: it.sub, size: it.label_size || 24, align: at[2], color: colourOf(it, tr, 'label_color', '#FFFFFF') });
}

// ---- the primitives -------------------------------------------------------------------------------------------------------------
export const PRIMS = {
  text(c, it, tr) {
    const [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5]));
    let s = up(it, param(it, 'text', tr, ''));
    // "#" in the text is a live number: "1 HOUR FOR YOU = # HOURS ON EARTH" with m "count" (or a "value")
    if (s.includes('#') && (it._anim.value || it.value != null)) { const v = Number(param(it, 'value', tr, 0)); s = s.replace('#', fmt(v, it.decimals ?? (Math.abs(v) < 10 && !Number.isInteger(Number(it.to ?? it.value ?? v)) ? 1 : 0))); }
    const k = param(it, 'progress', tr, 1);
    if (k < 1) s = s.slice(0, Math.ceil(s.length * k));
    const size = param(it, 'size', tr, 30), align = it.align || 'left';
    const w = label(c, it, tr, x, y, { text: s, sub: it.sub, size, align, color: colourOf(it, tr), font: it.font || 'sans', glow: it.glow });
    const strike = param(it, 'strike', tr, 0);
    if (strike > 0) {
      const x0 = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x;
      c.T.line(x0 - 6 * c.T.S, y - size * 0.33 * c.T.S, x0 - 6 * c.T.S + (w + 12 * c.T.S) * strike, y - size * 0.33 * c.T.S, { color: hex(it.strike_color || 'red'), width: 5 });
    }
  },
  number(c, it, tr) {
    const [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5]));
    const v = Number(param(it, 'value', tr, 0));
    const s = `${it.prefix || ''}${fmt(v, it.decimals ?? (Math.abs(v) < 10 && !Number.isInteger(Number(it.to ?? it.value ?? v)) ? 1 : 0))}${it.unit ? ` ${it.unit}` : ''}`;
    label(c, it, tr, x, y, { text: s, sub: it.sub, size: param(it, 'size', tr, 64), align: it.align || 'left', color: colourOf(it, tr), font: it.font || 'display', glow: it.glow ?? true });
  },
  ring(c, it, tr) {
    const { g, T, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5]));
    const R = param(it, 'r', tr, 0.1) * H, rx = (it.rx != null ? param(it, 'rx', tr) * H : R), ry = (it.ry != null ? param(it, 'ry', tr) * H : R);
    const k = param(it, 'progress', tr, 1), a0 = ((it.start_deg ?? -90) * Math.PI) / 180, col = colourOf(it, tr);
    g.save(); g.translate(x, y); g.rotate(((param(it, 'rot', tr, 0)) * Math.PI) / 180);
    if (it.fill) { g.fillStyle = hex(it.fill); g.beginPath(); g.ellipse(0, 0, rx, ry, 0, 0, TAU); g.fill(); }
    g.strokeStyle = col; g.lineWidth = param(it, 'width', tr, 2.5) * T.S; g.lineCap = 'round';
    if (it.dash) { g.setLineDash(it.dash.map((d) => d * T.S)); g.lineDashOffset = -(it.spin || 0) * tr * T.S; }
    if (it.glow) { g.shadowColor = col; g.shadowBlur = (it.glow === true ? 14 : it.glow) * T.S; }
    g.beginPath(); g.ellipse(0, 0, rx, ry, 0, a0, a0 + TAU * k); g.stroke();
    g.restore();
    sideLabel(c, it, tr, x, y, rx);
  },
  disc(c, it, tr) {
    const { g, T, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5]));
    const pulse = it.pulse ? 1 + (it.pulse.amp ?? 0.04) * Math.sin(tr * TAU * (it.pulse.hz ?? 0.5)) : 1;
    const R = param(it, 'r', tr, 0.1) * H * param(it, 'scale', tr, 1) * pulse, style = it.style || 'solid', col = colourOf(it, tr, 'color', '#FFFFFF');
    g.save();
    if (style === 'sun' || style === 'star') {
      const corona = g.createRadialGradient(x, y, R * 0.8, x, y, R * 1.9);
      corona.addColorStop(0, 'rgba(255,170,70,0.55)'); corona.addColorStop(1, 'rgba(255,120,40,0)');
      g.fillStyle = corona; g.beginPath(); g.arc(x, y, R * 1.9, 0, TAU); g.fill();
      const body = g.createRadialGradient(x - R * 0.25, y - R * 0.25, R * 0.1, x, y, R);
      body.addColorStop(0, it.color ? hex(it.color) : '#FFB45A'); body.addColorStop(0.7, '#F06A1E'); body.addColorStop(1, '#B8380E');
      g.fillStyle = body; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill();
    } else if (style === 'planet' || style === 'earth') {
      const base = style === 'earth' ? '#2F6BDF' : col;
      const body = g.createRadialGradient(x - R * 0.35, y - R * 0.35, R * 0.1, x, y, R);
      body.addColorStop(0, base); body.addColorStop(1, '#05070B');
      g.fillStyle = body; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill();
    } else if (style === 'shadow') {
      // a black hole on a diagram: a black disc with a thin warm rim and a soft outer glow (V4 0:30)
      const halo = g.createRadialGradient(x, y, R, x, y, R * 1.5); halo.addColorStop(0, 'rgba(255,170,70,0.25)'); halo.addColorStop(1, 'rgba(255,170,70,0)');
      g.fillStyle = halo; g.beginPath(); g.arc(x, y, R * 1.5, 0, TAU); g.fill();
      g.fillStyle = '#000'; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill();
      g.strokeStyle = hex(it.rim || 'gold'); g.lineWidth = (it.rim_width ?? 3) * T.S; g.shadowColor = hex(it.rim || 'gold'); g.shadowBlur = 10 * T.S; g.stroke();
    } else if (style === 'ring_photo') {
      // the Event Horizon Telescope look (M87*, Sgr A*): a soft orange ring, brighter on one side, dark centre -- the stand-in when the real photo is missing
      const k = it.bright_deg ?? 200;
      g.filter = `blur(${R * 0.18}px)`;
      g.lineWidth = R * 0.42; g.strokeStyle = '#E8661C'; g.beginPath(); g.arc(x, y, R * 0.72, 0, TAU); g.stroke();
      g.strokeStyle = '#FFC46B'; g.lineWidth = R * 0.3; g.beginPath(); g.arc(x, y, R * 0.72, ((k - 70) * Math.PI) / 180, ((k + 70) * Math.PI) / 180); g.stroke();
      g.filter = 'none';
    } else if (style === 'glow') {
      const grd = g.createRadialGradient(x, y, 0, x, y, R); grd.addColorStop(0, col); grd.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = grd; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill();
    } else {
      g.fillStyle = col; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill();
      if (it.rim) { g.strokeStyle = hex(it.rim); g.lineWidth = (it.rim_width ?? 2) * T.S; g.stroke(); }
    }
    g.restore();
    sideLabel(c, it, tr, x, y, R);
  },
  line(c, it, tr) {
    const { g, T } = c, P = [xy(c, param(it, 'from', tr, [0.3, 0.5])), xy(c, param(it, 'to', tr, [0.7, 0.5]))], col = colourOf(it, tr);
    const k = param(it, 'progress', tr, 1);
    g.save(); g.strokeStyle = col; g.lineWidth = param(it, 'width', tr, 2.5) * T.S; g.lineCap = 'round';
    if (it.dash) { g.setLineDash(it.dash.map((d) => d * T.S)); g.lineDashOffset = -(it.speed || 0) * tr * 40 * T.S; }
    if (it.glow) { g.shadowColor = col; g.shadowBlur = (it.glow === true ? 12 : it.glow) * T.S; }
    strokePart(g, P, k);
    g.setLineDash([]);
    const end = pointAt(P, k), hs = (it.head ?? 16) * T.S;
    if (it.arrow === 'end' || it.arrow === 'both' || it.p === 'arrow') arrowHead(g, end.x, end.y, end.a, hs, col);
    if (it.arrow === 'both' || it.arrow === 'start') arrowHead(g, P[0][0], P[0][1], Math.atan2(P[0][1] - P[1][1], P[0][0] - P[1][0]), hs, col);
    g.restore();
    if (it.label) {
      const m = pointAt(P, 0.5), off = (it.label_offset ?? -16) * T.S;
      label(c, it, tr, m.x, m.y + off, { text: param(it, 'label', tr), sub: it.sub, size: it.label_size || 20, align: 'center', color: colourOf(it, tr, 'label_color', '#FFFFFF') });
    }
  },
  path(c, it, tr) {
    const { g, T } = c, pts = param(it, 'points', tr, [[0.2, 0.5], [0.8, 0.5]]);
    if (!Array.isArray(pts) || pts.length < 2) return;
    const P = polyline(c, pts, it.smooth !== false), col = colourOf(it, tr), k = param(it, 'progress', tr, 1);
    g.save(); g.strokeStyle = col; g.lineWidth = param(it, 'width', tr, 2.5) * T.S; g.lineCap = 'round'; g.lineJoin = 'round';
    if (it.dash) { g.setLineDash(it.dash.map((d) => d * T.S)); g.lineDashOffset = -(it.speed || 0) * tr * 40 * T.S; }
    if (it.glow) { g.shadowColor = col; g.shadowBlur = (it.glow === true ? 12 : it.glow) * T.S; }
    if (it.closed && k >= 1) { g.beginPath(); P.forEach(([px, py], i) => (i ? g.lineTo(px, py) : g.moveTo(px, py))); g.closePath(); if (it.fill) { g.fillStyle = hex(it.fill); g.fill(); } g.stroke(); }
    else strokePart(g, P, k);
    g.setLineDash([]);
    if (it.arrow && k > 0.02) { const e = pointAt(P, k); arrowHead(g, e.x, e.y, e.a, (it.head ?? 14) * T.S, col); }
    if (it.pulse_dot) { const e = pointAt(P, (tr * (it.pulse_dot.speed ?? 0.4)) % 1); g.fillStyle = hex(it.pulse_dot.color || col); g.beginPath(); g.arc(e.x, e.y, 5 * T.S, 0, TAU); g.fill(); }
    g.restore();
    if (it.label) {
      const e = pointAt(P, it.label_at ?? 1), off = it.label_off || [10, -12];
      label(c, it, tr, e.x + off[0] * T.S, e.y + off[1] * T.S, { text: param(it, 'label', tr), sub: it.sub, size: it.label_size || 20, align: it.label_align || 'left', color: colourOf(it, tr, 'label_color', '#FFFFFF') });
    }
  },
  dot(c, it, tr) {
    const { g, T, H } = c;
    const where = (t) => {
      if (it.orbit) {
        const o = it.orbit, [cx, cy] = xy(c, o.c || [0.5, 0.5]);
        const deg = (o.deg0 ?? 0) + (it._anim.along ? 360 * param(it, 'along', t, 0) * (o.turns ?? 1) : (o.spin ?? 20) * Math.max(0, t - it._in));
        const a = (deg * Math.PI) / 180, tilt = ((o.tilt ?? 0) * Math.PI) / 180;
        const ex = Math.cos(a) * (o.rx ?? 0.2) * H, ey = Math.sin(a) * (o.ry ?? o.rx ?? 0.2) * H;
        return [cx + ex * Math.cos(tilt) - ey * Math.sin(tilt), cy + ex * Math.sin(tilt) + ey * Math.cos(tilt)];
      }
      if (it.path) { const e = pointAt(polyline(c, it.path, it.smooth !== false), param(it, 'along', t, 0)); return [e.x, e.y]; }
      return xy(c, param(it, 'at', t, [0.5, 0.5]));
    };
    const col = colourOf(it, tr, 'color', '#00E5FF'), r = param(it, 'r', tr, 7) * param(it, 'scale', tr, 1);
    if (it.trail) {
      const n = it.trail.n ?? 14, dt = it.trail.dt ?? 0.08;
      for (let i = n; i >= 1; i--) { if (tr - i * dt < it._in) continue; const [px, py] = where(tr - i * dt); g.save(); g.globalAlpha *= 0.6 * (1 - i / (n + 1)); g.fillStyle = col; g.beginPath(); g.arc(px, py, r * 0.55 * (1 - i / (n + 2)) * T.S, 0, TAU); g.fill(); g.restore(); }
    }
    const [x, y] = where(tr);
    if (it.style === 'plain') { g.fillStyle = col; g.beginPath(); g.arc(x, y, r * T.S, 0, TAU); g.fill(); }
    else T.node(x, y, { color: col, r, ring: it.ring !== false });
    sideLabel(c, it, tr, x, y, r * T.S);
  },
  icon(c, it, tr) {
    const { H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5]));
    const bob = it.bob ? Math.sin(tr * TAU * 0.25) * it.bob * H : 0;
    const size = param(it, 'size', tr, 0.12) * H * param(it, 'scale', tr, 1);
    drawIcon(c.g, it.name, x, y + bob, size, { color: it.color ? colourOf(it, tr) : undefined, accent: it.accent && hex(it.accent), level: param(it, 'level', tr, undefined),
      burn: param(it, 'burn', tr, 0), sx: param(it, 'sx', tr, 1), sy: param(it, 'sy', tr, 1), rot: param(it, 'rot', tr, 0) + (it.spin || 0) * tr, flip: it.flip });
    if (it.label) label(c, it, tr, x, y + size * 0.62 + 26 * c.T.S, { text: param(it, 'label', tr), sub: it.sub, size: it.label_size || 20, align: 'center', color: colourOf(it, tr, 'label_color', '#FFFFFF') });
  },
  image(c, it, tr) {
    const { g, T, W, H } = c, img = c.image(it.name);
    const [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5])), w = param(it, 'w', tr, 0.3) * W * param(it, 'scale', tr, 1);
    if (img) {
      const h = it.h ? it.h * H : w * (img.height / img.width);
      g.save();
      if (it.mask === 'circle' || it.mask === 'feather') { g.beginPath(); g.arc(x, y, Math.min(w, h) / 2, 0, TAU); g.clip(); }
      g.drawImage(img, x - w / 2, y - h / 2, w, h);
      if (it.mask === 'feather') { const grd = g.createRadialGradient(x, y, Math.min(w, h) * 0.3, x, y, Math.min(w, h) / 2); grd.addColorStop(0, 'rgba(5,7,11,0)'); grd.addColorStop(1, 'rgba(5,7,11,1)'); g.fillStyle = grd; g.fillRect(x - w / 2, y - h / 2, w, h); }
      g.restore();
      if (it.border) { g.save(); g.strokeStyle = hex(it.border); g.lineWidth = 2 * T.S; g.strokeRect(x - w / 2, y - h / 2, w, h); g.restore(); }
      if (it.label) label(c, it, tr, x, y + h / 2 + 34 * T.S, { text: param(it, 'label', tr), sub: it.sub, size: it.label_size || 22, align: 'center', color: colourOf(it, tr, 'label_color', '#FFFFFF') });
    } else if (it.fallback) PRIMS.disc(c, { ...it, ...it.fallback, _anim: {} }, tr);
  },
  panel(c, it, tr) {
    const { T, W, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.1, 0.1]));
    const w = param(it, 'w', tr, 0.3) * W, h = param(it, 'h', tr, 0.3) * H;
    T.card(x, y, w, h, { accent: it.accent ? hex(it.accent) : null, fill: it.fill || 'rgba(10,13,18,0.72)', border: it.border ? hex(it.border) : C.border });
    if (it.title) label(c, it, tr, x + 22 * T.S, y + 44 * T.S, { text: param(it, 'title', tr), sub: it.sub, size: it.title_size || 22, color: colourOf(it, tr, 'title_color', '#FFFFFF') });
  },
  grid(c, it, tr) {
    // a sheet of spacetime: a wire grid seen at an angle, pulled down into a well (V4 2:10 "GRAVITY SLOWS TIME")
    const { g, T, W, H } = c, [cx, cy] = xy(c, param(it, 'at', tr, [0.5, 0.55]));
    const size = param(it, 'size', tr, 0.55) * W, well = param(it, 'well', tr, 1), n = it.n ?? 22, tilt = ((it.tilt ?? 62) * Math.PI) / 180;
    const spin = ((it.spin ?? 4) * tr * Math.PI) / 180, throat = it.throat ?? 0.1, depth = it.depth ?? 0.9;
    const project = (u, v) => {
      const rr = Math.hypot(u, v), z = -well * depth / (1 + (rr / throat) ** 1.6);
      const X = u * Math.cos(spin) - v * Math.sin(spin), Z = u * Math.sin(spin) + v * Math.cos(spin);
      const yy = z * Math.cos(tilt) - Z * Math.sin(tilt), zz = z * Math.sin(tilt) + Z * Math.cos(tilt);
      const s = 2.6 / (2.6 + zz);
      return [cx + X * s * size, cy - yy * s * size * 0.62, rr];
    };
    g.save(); g.strokeStyle = colourOf(it, tr, 'color', '#B9A46A'); g.lineWidth = (it.width ?? 1.4) * T.S;
    // each grid line in short pieces, each fading with its distance from the well (the sheet dissolves at its edges)
    for (let axis = 0; axis < 2; axis++) for (let i = 0; i <= n; i++) {
      const fixed = -1 + (2 * i) / n;
      let prev = null;
      for (let k = 0; k <= 60; k++) {
        const s = -1 + (2 * k) / 60, cur = axis ? project(fixed, s) : project(s, fixed);
        if (prev) {
          g.globalAlpha = c.alpha * (it.alpha ?? 0.6) * Math.max(0, 1 - ((prev[2] + cur[2]) / 2) * 0.72);
          g.beginPath(); g.moveTo(prev[0], prev[1]); g.lineTo(cur[0], cur[1]); g.stroke();
        }
        prev = cur;
      }
    }
    g.restore();
    if (it.ball !== false) {
      const [bx, by] = project(0, 0);
      T.node(bx, by + (it.ball_offset ?? 0) * H, { color: hex(it.ball_color || 'cyan'), r: it.ball_r ?? 9 });
    }
  },
  particles(c, it, tr) {
    const { g, T, W, H } = c, mode = it.mode || 'stars', n = it.count ?? 200, r = rnd(it.seed ?? 11), col = colourOf(it, tr, 'color', '#FFFFFF');
    const box = it.box || [0, 0, 1, 1], [bx0, by0, bx1, by1] = [box[0] * W, box[1] * H, box[2] * W, box[3] * H];
    const speed = param(it, 'speed', tr, 1), age = Math.max(0, tr - it._in);
    g.save(); g.fillStyle = col; g.strokeStyle = col;
    if (mode === 'stars') {
      for (let i = 0; i < n; i++) { const x = bx0 + r() * (bx1 - bx0), y = by0 + r() * (by1 - by0), s = 0.6 + r() ** 3 * 2.2, ph = r() * TAU;
        g.globalAlpha = c.alpha * (0.35 + 0.5 * (0.5 + 0.5 * Math.sin(age * 1.3 + ph))) * (it.alpha ?? 0.8); g.beginPath(); g.arc(x, y, s * T.S, 0, TAU); g.fill(); }
    } else if (mode === 'flow') {
      // dashes carried along a band: the "moving walkway" of space (V4 3:40), faster towards the end they flow to
      const dir = it.dir ?? -1, len = (it.length ?? 14) * T.S;
      g.lineWidth = (it.width ?? 2) * T.S; g.lineCap = 'round';
      for (let i = 0; i < n; i++) {
        const y = by0 + r() * (by1 - by0), x0 = r(), v = (0.06 + r() * 0.05) * speed;
        let u = (x0 + dir * v * age) % 1; if (u < 0) u += 1;
        const prof = it.profile === 'river' ? (dir < 0 ? 1 + 2.2 * (1 - u) : 1 + 2.2 * u) : 1;
        const x = bx0 + u * (bx1 - bx0);
        g.globalAlpha = c.alpha * (0.35 + 0.6 * r()) * (it.alpha ?? 0.8);
        g.beginPath(); g.moveTo(x, y); g.lineTo(x - dir * len * prof, y); g.stroke();
      }
    } else if (mode === 'radial') {
      // streaks rushing from (or into) one point: the singularity (V4 7:30)
      const [cx, cy] = xy(c, it.at || [0.5, 0.5]), maxR = Math.hypot(W, H) * 0.6, inward = it.inward;
      g.lineWidth = (it.width ?? 1.5) * T.S;
      for (let i = 0; i < n; i++) {
        const a = r() * TAU, v = 0.15 + r() * 0.35, ph = r();
        let u = (ph + v * age * speed) % 1; if (inward) u = 1 - u;
        const d0 = u * maxR, d1 = d0 + (it.length ?? 0.08) * maxR * (0.5 + u);
        g.globalAlpha = c.alpha * (it.alpha ?? 0.7) * Math.min(1, u * 3) * (0.4 + 0.6 * r());
        g.beginPath(); g.moveTo(cx + Math.cos(a) * d0, cy + Math.sin(a) * d0); g.lineTo(cx + Math.cos(a) * d1, cy + Math.sin(a) * d1); g.stroke();
      }
    } else if (mode === 'orbit') {
      const [cx, cy] = xy(c, it.at || [0.5, 0.5]), r0 = (it.r0 ?? 0.15) * H, r1 = (it.r1 ?? 0.3) * H, flat = it.flat ?? 0.3;
      for (let i = 0; i < n; i++) { const rad = r0 + r() * (r1 - r0), a = r() * TAU + age * speed * (0.6 / Math.sqrt(rad / r0)), s = 0.8 + r() * 1.8;
        g.globalAlpha = c.alpha * (0.4 + 0.6 * r()) * (it.alpha ?? 0.8); g.beginPath(); g.arc(cx + Math.cos(a) * rad, cy + Math.sin(a) * rad * flat, s * T.S, 0, TAU); g.fill(); }
    } else if (mode === 'squiggle') {
      // little wavy marks drifting away from a disc: Hawking radiation (V4 8:20)
      const [cx, cy] = xy(c, it.at || [0.5, 0.5]), r0 = (it.r0 ?? 0.14) * H;
      g.lineWidth = 1.6 * T.S;
      for (let i = 0; i < n; i++) {
        const a = r() * TAU, u = (r() + age * 0.08 * speed) % 1, d = r0 + u * H * 0.32, hue = r() < 0.5 ? (it.color2 ? hex(it.color2) : '#00E5FF') : col;
        g.strokeStyle = hue; g.globalAlpha = c.alpha * (1 - u) * (it.alpha ?? 0.9);
        const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d;
        g.beginPath(); for (let k = 0; k <= 8; k++) { const t = k / 8; g.lineTo(x + Math.cos(a) * t * 14 * T.S - Math.sin(a) * Math.sin(t * TAU) * 3 * T.S, y + Math.sin(a) * t * 14 * T.S + Math.cos(a) * Math.sin(t * TAU) * 3 * T.S); } g.stroke();
      }
    } else if (mode === 'pack') {
      // many small discs inside one big circle ("1.3 MILLION EARTHS FIT INSIDE THE SUN"), filling in as "progress" runs
      const [cx, cy] = xy(c, it.at || [0.5, 0.5]), R0 = (it.r0 ?? 0.3) * H, k = param(it, 'progress', tr, 1), s = (it.dot ?? 3) * T.S;
      for (let i = 0; i < n * k; i++) { const a = r() * TAU, d = Math.sqrt(r()) * (R0 - s); g.globalAlpha = c.alpha * (it.alpha ?? 0.9); g.beginPath(); g.arc(cx + Math.cos(a) * d, cy + Math.sin(a) * d, s, 0, TAU); g.fill(); }
    } else if (mode === 'fall' || mode === 'rise') {
      const sgn = mode === 'fall' ? 1 : -1;
      for (let i = 0; i < n; i++) { const x = bx0 + r() * (bx1 - bx0), v = 0.1 + r() * 0.2; let u = (r() + sgn * v * age * speed) % 1; if (u < 0) u += 1;
        g.globalAlpha = c.alpha * (it.alpha ?? 0.7) * (0.4 + 0.6 * r()); g.beginPath(); g.arc(x, by0 + u * (by1 - by0), (1 + r() * 1.5) * T.S, 0, TAU); g.fill(); }
    } else if (mode === 'burst') {
      const [cx, cy] = xy(c, it.at || [0.5, 0.5]), k = smooth(age / (it.dur ?? 1.6));
      for (let i = 0; i < n; i++) { const a = r() * TAU, d = (0.05 + r() * 0.35) * H * k; g.globalAlpha = c.alpha * (1 - k * 0.8); g.beginPath(); g.arc(cx + Math.cos(a) * d, cy + Math.sin(a) * d, (1 + r() * 2) * T.S, 0, TAU); g.fill(); }
    }
    g.restore();
  },
  clock(c, it, tr) {
    // an analog clock; its hands run at "speed" (animatable): 1 = the minute hand turns once in 60 s of video
    const { g, T, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5])), R = param(it, 'r', tr, 0.12) * H, col = colourOf(it, tr, 'color', '#FFFFFF');
    let turns = it.start ?? 0;
    for (let t = it._in; t < tr; t += 0.1) turns += (param(it, 'speed', t, 1) * Math.min(0.1, tr - t)) / 60;
    g.save(); g.strokeStyle = col; g.lineWidth = (it.width ?? 3) * T.S;
    g.beginPath(); g.arc(x, y, R, 0, TAU); g.stroke();
    for (let i = 0; i < 12; i++) { const a = (i / 12) * TAU, r0 = R * (i % 3 ? 0.86 : 0.8); g.lineWidth = (i % 3 ? 1.6 : 2.6) * T.S; g.beginPath(); g.moveTo(x + Math.cos(a) * r0, y + Math.sin(a) * r0); g.lineTo(x + Math.cos(a) * R * 0.94, y + Math.sin(a) * R * 0.94); g.stroke(); }
    const hand = (a, len, w) => { g.lineWidth = w * T.S; g.lineCap = 'round'; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len); g.stroke(); };
    hand(turns * TAU - Math.PI / 2, R * 0.82, 3);
    hand((turns / 12) * TAU - Math.PI / 2 + (it.hour0 ?? 2), R * 0.55, 4.5);
    g.fillStyle = col; g.beginPath(); g.arc(x, y, 4 * T.S, 0, TAU); g.fill();
    g.restore();
    if (it.label) label(c, it, tr, x, y - R - 26 * T.S, { text: param(it, 'label', tr), size: it.label_size || 26, align: 'center', color: colourOf(it, tr, 'label_color', '#FFFFFF') });
    if (it.sub) T.text(up(it, param(it, 'sub', tr)), x, y + R + 40 * T.S, { font: T.mono(16, 600), track: 1.5, color: hex(it.sub_color || 'grey'), align: 'center', shadow: 0 });
  },
  axis(c, it, tr) {
    const { g, T } = c, A = xy(c, param(it, 'from', tr, [0.1, 0.6])), B = xy(c, param(it, 'to', tr, [0.9, 0.6])), col = colourOf(it, tr, 'color', '#8E99A8');
    const k = param(it, 'progress', tr, 1), rot = (param(it, 'rot', tr, 0) * Math.PI) / 180, pv = it.pivot ? xy(c, it.pivot) : [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2];
    g.save(); g.translate(pv[0], pv[1]); g.rotate(rot); g.translate(-pv[0], -pv[1]);
    T.line(A[0], A[1], A[0] + (B[0] - A[0]) * k, A[1] + (B[1] - A[1]) * k, { color: col, width: it.width ?? 2 });
    if (it.arrow && k >= 0.99) arrowHead(g, B[0], B[1], Math.atan2(B[1] - A[1], B[0] - A[0]), 14 * T.S, col);
    const ticks = [...(it.ticks || [])];
    if (it.log) for (let e = it.log.from; e <= it.log.to; e += it.log.every || 1) ticks.push({ at: (e - it.log.from) / Math.max(1, it.log.to - it.log.from), label: `10${sup(e)}` });
    const nx = -(B[1] - A[1]), ny = B[0] - A[0], nl = Math.hypot(nx, ny) || 1;
    for (const tk of ticks) {
      if (tk.at > k + 1e-6) continue;
      const px = A[0] + (B[0] - A[0]) * tk.at, py = A[1] + (B[1] - A[1]) * tk.at, s = (tk.major === false ? 6 : 10) * T.S;
      T.line(px - (nx / nl) * s, py - (ny / nl) * s, px + (nx / nl) * s, py + (ny / nl) * s, { color: col, width: 1.6 });
      if (tk.label) T.text(up(it, tk.label), px + (nx / nl) * 30 * T.S, py + (ny / nl) * 30 * T.S + 6 * T.S, { font: T.mono(it.tick_size || 15, 600), color: hex(tk.color || col), align: 'center', shadow: 0 });
    }
    g.restore();
    if (it.label) {
      const at = it.label_at === 'start' ? A : B;
      label(c, it, tr, at[0] + (it.label_off?.[0] ?? 0) * T.S, at[1] + (it.label_off?.[1] ?? -18) * T.S, { text: param(it, 'label', tr), sub: it.sub, size: it.label_size || 18, align: it.label_align || 'center', color: colourOf(it, tr, 'label_color', '#C9D2DD'), font: 'mono' });
    }
  },
  rail(c, it, tr) {
    // a progress rail: nodes along a line, the current one lit (the mission card's stage rail, a chapter strip)
    const { T, W } = c, [x, y] = xy(c, param(it, 'at', tr, [0.3, 0.1])), w = param(it, 'w', tr, 0.4) * W, nodes = it.nodes || [];
    const cur = param(it, 'current', tr, 0), col = hex(it.color || 'cyan'), n = Math.max(1, nodes.length - 1);
    T.line(x, y, x + w, y, { color: 'rgba(255,255,255,0.35)', width: 1.4 });
    T.line(x, y, x + (w * Math.min(cur, n)) / n, y, { color: col, width: 2 });
    nodes.forEach((nm, i) => {
      const px = x + (w * i) / n, on = Math.abs(i - cur) < 0.5;
      if (on) T.node(px, y, { color: col, r: 6 }); else { c.g.save(); c.g.fillStyle = i < cur ? col : '#FFFFFF'; c.g.beginPath(); c.g.arc(px, y, 3.5 * T.S, 0, TAU); c.g.fill(); c.g.restore(); }
      if (on || it.all_labels) T.text(up(it, nm), px, y + 26 * T.S, { font: T.mono(it.label_size || 12, 700), track: 1, color: on ? col : C.label, align: 'center', shadow: 0 });
    });
  },
  bar(c, it, tr) {
    const { g, T, W, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.2, 0.5])), vertical = it.vertical;
    const len = param(it, 'w', tr, 0.4) * (vertical ? H : W), th = (it.h ?? 22) * T.S, v = Math.max(0, Math.min(1, param(it, 'value', tr, 1))), col = colourOf(it, tr, 'color', '#00E5FF');
    g.save();
    g.fillStyle = it.track || 'rgba(255,255,255,0.08)';
    if (vertical) { g.fillRect(x - th / 2, y - len, th, len); g.fillStyle = col; g.fillRect(x - th / 2, y - len * v, th, len * v); }
    else { g.fillRect(x, y - th / 2, len, th); g.fillStyle = col; g.fillRect(x, y - th / 2, len * v, th); }
    g.restore();
    if (it.label) T.text(up(it, param(it, 'label', tr)), vertical ? x : x, vertical ? y + 30 * T.S : y - th / 2 - 12 * T.S, { font: T.sans(it.label_size || 20, 800), track: 2, color: '#FFFFFF', align: vertical ? 'center' : 'left', shadow: 0 });
    if (it.value_text) T.text(up(it, param(it, 'value_text', tr)), vertical ? x : x + len * v + 14 * T.S, vertical ? y - len * v - 14 * T.S : y + 8 * T.S, { font: T.mono(it.value_size || 20, 700), color: col, align: vertical ? 'center' : 'left', shadow: 0 });
  },
  band(c, it, tr) {
    const { g, T, W, H } = c, b = param(it, 'box', tr, [0, 0.4, 1, 0.6]), [x0, y0, x1, y1] = [b[0] * W, b[1] * H, b[2] * W, b[3] * H];
    const cols = (it.colors || ['#7A2A1A', '#0B0E14']).map(hex);
    g.save();
    const grd = it.dir === 'v' ? g.createLinearGradient(0, y0, 0, y1) : g.createLinearGradient(x0, 0, x1, 0);
    cols.forEach((cc, i) => grd.addColorStop(i / Math.max(1, cols.length - 1), cc));
    g.globalAlpha *= param(it, 'opacity', tr, 0.6); g.fillStyle = grd;
    if (it.feather) { g.filter = `blur(${it.feather * T.S}px)`; }
    g.fillRect(x0, y0, x1 - x0, y1 - y0);
    g.filter = 'none';
    if (it.lines) { g.globalAlpha = c.alpha * 0.9; g.strokeStyle = hex(it.line_color || 'gold'); g.lineWidth = 1.4 * T.S;
      for (let i = 0; i < it.lines; i++) { const yy = y0 + ((i + 0.5) / it.lines) * (y1 - y0), shrink = Math.abs(i - (it.lines - 1) / 2) / it.lines; g.beginPath(); g.moveTo(x0 + (x1 - x0) * shrink * 0.4, yy); g.lineTo(x1 - (x1 - x0) * shrink * 0.4, yy); g.stroke(); } }
    g.restore();
  },
  equation(c, it, tr) {
    // a formula in a serif face with real sub/superscripts: "G_{μν} = 8πG T_{μν} / c^{4}", an optional coloured tail ("→ ∞") and a mono line
    const { g, T } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5])), size = param(it, 'size', tr, 56) * T.S, col = colourOf(it, tr, 'color', '#F2F4F7');
    const parts = []; const re = /([_^])\{([^}]*)\}|([^_^]+|[_^])/g; let m;
    const src = String(param(it, 'text', tr, ''));
    while ((m = re.exec(src))) parts.push(m[1] ? { s: m[2], lvl: m[1] === '_' ? -1 : 1 } : { s: m[3], lvl: 0 });
    if (it.tail) parts.push({ s: ` ${it.tail}`, lvl: 0, tail: true });
    const font = (lvl) => `italic 400 ${Math.round(lvl ? size * 0.6 : size)}px "Times New Roman", Times, Georgia, serif`;
    let total = 0; for (const p of parts) { g.font = font(p.lvl); total += g.measureText(p.s).width; }
    let cx = (it.align || 'center') === 'center' ? x - total / 2 : x;
    g.save(); g.textBaseline = 'alphabetic'; g.shadowColor = 'rgba(0,0,0,0.6)'; g.shadowBlur = 10 * T.S;
    for (const p of parts) { g.font = font(p.lvl); g.fillStyle = p.tail ? hex(it.tail_color || 'red') : col; g.fillText(p.s, cx, y + (p.lvl === -1 ? size * 0.22 : p.lvl === 1 ? -size * 0.4 : 0)); cx += g.measureText(p.s).width; }
    g.restore();
    if (it.sub) T.text(up(it, param(it, 'sub', tr)), x, y + size * 0.8 + 10 * T.S, { font: T.mono(it.sub_size || 18, 600), track: 1.5, color: hex(it.sub_color || 'amber'), align: 'center', shadow: 0 });
  },
  glow(c, it, tr) {
    const { g, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5]));
    const pulse = it.pulse ? 1 + (it.pulse.amp ?? 0.1) * Math.sin(tr * TAU * (it.pulse.hz ?? 0.5)) : 1;
    const R = param(it, 'r', tr, 0.2) * H * pulse, grd = g.createRadialGradient(x, y, 0, x, y, R);
    grd.addColorStop(0, colourOf(it, tr, 'color', '#FF7A1A')); grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.save(); g.globalAlpha *= param(it, 'opacity', tr, 0.5); g.fillStyle = grd; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill(); g.restore();
  },
  wave(c, it, tr) {
    const { g, T, W, H } = c, A = xy(c, param(it, 'from', tr, [0.1, 0.5])), B = xy(c, param(it, 'to', tr, [0.9, 0.5]));
    const amp = param(it, 'amp', tr, 0.05) * H, wl = param(it, 'wavelength', tr, 0.1) * W, ph = tr * (it.speed ?? 1) * TAU, k = param(it, 'progress', tr, 1);
    const L = Math.hypot(B[0] - A[0], B[1] - A[1]), ang = Math.atan2(B[1] - A[1], B[0] - A[0]);
    g.save(); g.translate(A[0], A[1]); g.rotate(ang); g.strokeStyle = colourOf(it, tr, 'color', '#00E5FF'); g.lineWidth = (it.width ?? 2.5) * T.S;
    if (it.glow) { g.shadowColor = g.strokeStyle; g.shadowBlur = 10 * T.S; }
    const damp = param(it, 'damp', tr, 0);
    g.beginPath(); for (let s = 0; s <= L * k; s += 2) { const fade = damp ? Math.exp(-damp * s / L) : 1; g.lineTo(s, Math.sin((s / wl) * TAU - ph) * amp * fade); } g.stroke();
    g.restore();
    if (it.label) label(c, it, tr, (A[0] + B[0]) / 2, Math.min(A[1], B[1]) - amp - 24 * T.S, { text: param(it, 'label', tr), sub: it.sub, size: it.label_size || 20, align: 'center', color: '#FFFFFF' });
  },
  donut(c, it, tr) {
    const { g, T, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5])), R = param(it, 'r', tr, 0.18) * H, k = param(it, 'progress', tr, 1);
    const parts = it.parts || [], tot = parts.reduce((s, p) => s + (Number(p.v) || 0), 0) || 1, pal = ['#00E5FF', '#FFB703', '#FF2A4B', '#2EE6A8', '#C9CED6', '#2F6BDF'];
    let a = -Math.PI / 2;
    g.save(); g.lineWidth = (it.width ?? 34) * T.S;
    parts.forEach((p, i) => {
      const span = ((Number(p.v) || 0) / tot) * TAU, drawn = Math.max(0, Math.min(span, TAU * k - (a + Math.PI / 2)));
      if (drawn > 0) { g.strokeStyle = hex(p.color || pal[i % pal.length]); g.beginPath(); g.arc(x, y, R, a, a + drawn); g.stroke(); }
      if (drawn >= span * 0.99 && p.label) {
        const m = a + span / 2, lx = x + Math.cos(m) * (R + 60 * T.S), ly = y + Math.sin(m) * (R + 60 * T.S);
        T.text(up(it, p.label), lx, ly, { font: T.sans(18, 800), track: 2, color: '#FFFFFF', align: Math.cos(m) >= 0 ? 'left' : 'right', shadow: 0 });
        if (p.text) T.text(up(it, p.text), lx, ly + 22 * T.S, { font: T.mono(15, 600), color: hex(p.color || pal[i % pal.length]), align: Math.cos(m) >= 0 ? 'left' : 'right', shadow: 0 });
      }
      a += span;
    });
    g.restore();
    if (it.center) T.text(up(it, it.center), x, y + 10 * T.S, { font: T.display(it.center_size || 36), color: '#FFFFFF', align: 'center' });
  },
  blackhole(c, it, tr) {
    // the side-view schematic V4 returns to at every stage: hot gas disc as gold lines left and right, the dark disc with a warm rim,
    // the photon sphere as a dashed ring (1.5x), optional labels with leader lines
    const { g, T, W, H } = c, [x, y] = xy(c, param(it, 'at', tr, [0.5, 0.5])), R = param(it, 'r', tr, 0.07) * H;
    g.save();
    if (it.disc !== false) {
      const span = (it.disc_w ?? 0.2) * W, gap = R * 2.1;
      for (const s of [-1, 1]) {
        const grd = g.createLinearGradient(x + s * gap, 0, x + s * (gap + span), 0); grd.addColorStop(0, 'rgba(255,200,120,1)'); grd.addColorStop(1, 'rgba(255,170,80,0)');
        g.strokeStyle = grd;
        for (let i = -1; i <= 1; i++) { g.lineWidth = (i ? 1.4 : 3.2) * T.S; g.beginPath(); g.moveTo(x + s * gap, y + i * 4 * T.S); g.lineTo(x + s * (gap + span * (i ? 0.85 : 1)), y + i * 4 * T.S); g.stroke(); }
      }
    }
    if (it.photon !== false) { g.strokeStyle = 'rgba(220,230,240,0.5)'; g.lineWidth = 1.5 * T.S; g.setLineDash([4 * T.S, 6 * T.S]); g.lineDashOffset = -tr * 6 * T.S; g.beginPath(); g.arc(x, y, R * 1.5, 0, TAU); g.stroke(); g.setLineDash([]); }
    g.fillStyle = '#000'; g.beginPath(); g.arc(x, y, R, 0, TAU); g.fill();
    g.strokeStyle = hex(it.rim || 'gold'); g.lineWidth = 2.4 * T.S; g.shadowColor = hex(it.rim || 'gold'); g.shadowBlur = 12 * T.S; g.stroke(); g.shadowBlur = 0;
    if (it.singularity) { g.fillStyle = hex('red'); g.beginPath(); g.arc(x, y, 3.5 * T.S, 0, TAU); g.fill(); }
    g.restore();
    for (const lb of it.labels || []) {
      const [lx, ly] = xy(c, lb.at), [px, py] = lb.point ? xy(c, lb.point) : [x, y];
      if (lb.t != null && tr < lb.t) continue;
      T.line(px, py, lx, ly + 6 * T.S, { color: 'rgba(255,255,255,0.45)', width: 1.2 });
      T.text(up(it, lb.text), lx, ly, { font: T.mono(13, 700), track: 1.2, color: hex(lb.color || '#FFFFFF'), align: lb.align || 'center', shadow: 0 });
    }
  },
  callout(c, it, tr) {
    const { T } = c, P = xy(c, param(it, 'point', tr, [0.5, 0.5])), L = xy(c, param(it, 'at', tr, [0.7, 0.3])), k = param(it, 'progress', tr, 1);
    const col = colourOf(it, tr, 'color', 'rgba(255,255,255,0.6)');
    T.line(P[0], P[1], P[0] + (L[0] - P[0]) * k, P[1] + (L[1] - P[1]) * k, { color: col, width: 1.5 });
    if (it.dot !== false) T.node(P[0], P[1], { color: hex(it.dot_color || 'cyan'), r: 4, ring: false });
    if (k >= 0.98) label(c, it, tr, L[0] + (it.align === 'right' ? -10 : 10) * T.S, L[1] + 6 * T.S, { text: param(it, 'text', tr), sub: it.sub, size: it.size || 22, align: it.align || 'left', color: colourOf(it, tr, 'text_color', '#FFFFFF') });
  },
};
PRIMS.arrow = PRIMS.line;
export const PRIM_NAMES = Object.keys(PRIMS).sort();

const SUP = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' };
export const sup = (n) => String(n).split('').map((ch) => SUP[ch] ?? ch).join('');

/** Draw one built item at tr (its own transform: scale / rot / pulse about its "at"). */
export function drawItem(c, it, tr) {
  const vis = visibility(it, tr);
  if (vis <= 0.002) return;
  const f = PRIMS[it.p];
  if (!f) throw new Error(`template primitive "${it.p}" is not one of ${PRIM_NAMES.join(', ')}`);
  const { g } = c;
  g.save(); g.globalAlpha = c.alpha * vis;
  const appear = it.appear === 'cut' ? 1 : 0.94 + 0.06 * smooth((tr - it._in) / 0.35);
  const sc = (['disc', 'icon', 'image', 'dot', 'number'].includes(it.p) ? 1 : param(it, 'scale', tr, 1)) * appear;
  if (sc !== 1 && it.p !== 'grid' && it.p !== 'particles') {
    const at = param(it, 'at', tr, [0.5, 0.5]), [x, y] = Array.isArray(at) ? xy(c, at) : [c.W / 2, c.H / 2];
    g.translate(x, y); g.scale(sc, sc); g.translate(-x, -y);
  }
  f({ ...c, alpha: c.alpha * vis }, it, tr);
  g.restore();
}
