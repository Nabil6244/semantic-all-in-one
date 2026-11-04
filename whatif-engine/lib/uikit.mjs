// UIKIT: the interface a phone screen shows, drawn from a JSON spec -- one renderer shared by the live screen of a phone (lib/product.mjs liveScreen),
// the exploded interface cards that float above it, and the lock screens on a phone wall. Nothing is a picture: every component is drawn from its
// data, so any product, feature name, rows and colours work.
//
//   ui = { theme: "dark" | "light", accent: "#3b82f6", top: 170 (px of the 540x1170 screen where the stack starts),
//          components: [
//            { type: "header", text: "Settings", sub: "Apple Account, iCloud and more" },
//            { type: "list",   title?, rows: [{ label: "Airplane Mode", toggle: false, icon: "plane", color: "#ff9f0a" }, { label: "Wi-Fi", value: "Home", icon: "wifi" }, ...] },
//            { type: "widget", title: "Cupertino", big: "64°", sub: "Sunny", tint: "#4aa8ff" },
//            { type: "notif",  app: "Messages", title: "Tim", body: "Hello", time: "now" },
//            { type: "dock",   icons: [{ label: "Phone", color: "#34c759" }, ...] },
//            { type: "grid",   icons: [...] },   { type: "slider", label: "Brightness", value: 0.6 },   { type: "clock", time: "9:41", date: "Tuesday, October 21" } ],
//          script: [{ at: 1.2, comp: 1, row: 0 }, ...]   scripted taps: the cursor glides to the row, presses, and a toggle row flips
//          cursor: "touch" | "arrow" | false }
// Everything is a pure function of t (seconds into the shot). Units are logical pixels on a 540 x 1170 screen; the caller scales the context.
const TAU = Math.PI * 2;
let HOLE = '#000';   // the tile colour behind the current glyph: cut-outs are painted in it, never erased, so the canvas keeps its alpha
const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (x) => { const k = clamp01(x); return k * k * (3 - 2 * k); };
const lerp = (a, b, k) => a + (b - a) * k;
const FONT = (w, px) => `${w} ${px}px TMSans, Inter, -apple-system, Helvetica, Arial, sans-serif`;
export const SCREEN_W = 540, SCREEN_H = 1170;

/** A superellipse (Apple-style squircle) path, n = 5 is the icon shape. Appends to the current path of g. */
export function squirclePath(g, x, y, w, h, n = 5, steps = 96) {
  const a = w / 2, b = h / 2, cx = x + a, cy = y + b;
  g.moveTo(cx + a, cy);
  for (let i = 1; i <= steps; i++) {
    const th = (i / steps) * TAU, c = Math.cos(th), s = Math.sin(th);
    g.lineTo(cx + a * Math.sign(c) * Math.abs(c) ** (2 / n), cy + b * Math.sign(s) * Math.abs(s) ** (2 / n));
  }
  g.closePath();
}

const THEMES = {
  dark: { panel: 'rgba(24,24,30,0.72)', panel2: 'rgba(255,255,255,0.08)', ink: '#FFFFFF', sub: 'rgba(235,235,245,0.62)', line: 'rgba(255,255,255,0.12)', off: 'rgba(120,120,128,0.55)' },
  light: { panel: 'rgba(255,255,255,0.78)', panel2: 'rgba(0,0,0,0.05)', ink: '#101114', sub: 'rgba(60,60,67,0.62)', line: 'rgba(0,0,0,0.10)', off: 'rgba(120,120,128,0.32)' },
};
const PALETTE = ['#ff9f0a', '#0a84ff', '#30d158', '#bf5af2', '#ff375f', '#64d2ff', '#ffd60a', '#ff453a'];
const hash = (s) => { let h = 7; for (const ch of String(s)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; };
const colorFor = (label) => PALETTE[hash(label) % PALETTE.length];

// ---------- glyphs: small vector icons picked from the label, else the first letter ----------
const GLYPHS = {
  wifi(g, r) { for (let i = 0; i < 3; i++) { g.beginPath(); g.arc(0, r * 0.55, r * (0.5 + i * 0.42), -Math.PI * 0.78, -Math.PI * 0.22); g.stroke(); } g.beginPath(); g.arc(0, r * 0.55, r * 0.1, 0, TAU); g.fill(); },
  plane(g, r) { g.beginPath(); g.moveTo(0, -r); g.lineTo(r * 0.2, -r * 0.2); g.lineTo(r, r * 0.25); g.lineTo(r, r * 0.5); g.lineTo(r * 0.2, r * 0.2); g.lineTo(r * 0.12, r * 0.8); g.lineTo(r * 0.4, r * 0.95); g.lineTo(r * 0.4, r * 1.1); g.lineTo(0, r * 1.0); g.lineTo(-r * 0.4, r * 1.1); g.lineTo(-r * 0.4, r * 0.95); g.lineTo(-r * 0.12, r * 0.8); g.lineTo(-r * 0.2, r * 0.2); g.lineTo(-r, r * 0.5); g.lineTo(-r, r * 0.25); g.lineTo(-r * 0.2, -r * 0.2); g.closePath(); g.fill(); },
  moon(g, r) { g.beginPath(); g.arc(0, 0, r, Math.PI * 0.2, Math.PI * 1.8); g.arc(r * 0.45, -r * 0.1, r * 0.78, Math.PI * 1.55, Math.PI * 0.45, true); g.closePath(); g.fill(); },
  bell(g, r) { g.beginPath(); g.moveTo(-r * 0.8, r * 0.5); g.quadraticCurveTo(-r * 0.7, -r * 0.1, -r * 0.4, -r * 0.5); g.quadraticCurveTo(0, -r * 1.1, r * 0.4, -r * 0.5); g.quadraticCurveTo(r * 0.7, -r * 0.1, r * 0.8, r * 0.5); g.closePath(); g.fill(); g.beginPath(); g.arc(0, r * 0.75, r * 0.2, 0, TAU); g.fill(); },
  lock(g, r) { g.beginPath(); g.roundRect(-r * 0.75, -r * 0.1, r * 1.5, r * 1.0, r * 0.2); g.fill(); g.lineWidth = r * 0.22; g.beginPath(); g.arc(0, -r * 0.1, r * 0.48, Math.PI, 0); g.stroke(); },
  sun(g, r) { g.beginPath(); g.arc(0, 0, r * 0.45, 0, TAU); g.fill(); g.lineWidth = r * 0.16; for (let i = 0; i < 8; i++) { const a = i * TAU / 8; g.beginPath(); g.moveTo(Math.cos(a) * r * 0.72, Math.sin(a) * r * 0.72); g.lineTo(Math.cos(a) * r * 1.0, Math.sin(a) * r * 1.0); g.stroke(); } },
  battery(g, r) { g.beginPath(); g.roundRect(-r, -r * 0.5, r * 1.9, r, r * 0.22); g.fill(); g.fillRect(r * 0.95, -r * 0.2, r * 0.18, r * 0.4); },
  camera(g, r) { g.beginPath(); g.roundRect(-r, -r * 0.55, r * 2, r * 1.3, r * 0.25); g.fill(); g.fillStyle = HOLE; g.beginPath(); g.arc(0, r * 0.1, r * 0.46, 0, TAU); g.fill(); g.fillStyle = '#FFFFFF'; g.beginPath(); g.arc(0, r * 0.1, r * 0.3, 0, TAU); g.fill(); g.fillStyle = HOLE; g.beginPath(); g.arc(0, r * 0.1, r * 0.14, 0, TAU); g.fill(); g.fillStyle = '#FFFFFF'; g.beginPath(); g.roundRect(-r * 0.35, -r * 0.8, r * 0.7, r * 0.3, r * 0.1); g.fill(); },
  music(g, r) { g.lineWidth = r * 0.2; g.beginPath(); g.moveTo(r * 0.45, -r * 0.9); g.lineTo(r * 0.45, r * 0.55); g.stroke(); g.beginPath(); g.ellipse(r * 0.1, r * 0.6, r * 0.38, r * 0.28, -0.3, 0, TAU); g.fill(); g.beginPath(); g.moveTo(r * 0.45, -r * 0.9); g.lineTo(r * 0.95, -r * 0.55); g.lineTo(r * 0.95, -r * 0.3); g.lineTo(r * 0.45, -r * 0.6); g.fill(); },
  heart(g, r) { g.beginPath(); g.moveTo(0, r * 0.85); g.bezierCurveTo(-r * 1.3, -r * 0.1, -r * 0.5, -r * 1.0, 0, -r * 0.3); g.bezierCurveTo(r * 0.5, -r * 1.0, r * 1.3, -r * 0.1, 0, r * 0.85); g.fill(); },
  gear(g, r) { g.beginPath(); for (let i = 0; i < 16; i++) { const a = i * TAU / 16, rr = i % 2 ? r * 0.78 : r; g.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); } g.closePath(); g.fill(); g.fillStyle = HOLE; g.beginPath(); g.arc(0, 0, r * 0.32, 0, TAU); g.fill(); },
  message(g, r) { g.beginPath(); g.ellipse(0, -r * 0.1, r, r * 0.72, 0, 0, TAU); g.fill(); g.beginPath(); g.moveTo(-r * 0.5, r * 0.45); g.lineTo(-r * 0.85, r * 0.95); g.lineTo(-r * 0.1, r * 0.6); g.fill(); },
  phone(g, r) { g.beginPath(); g.roundRect(-r * 0.5, -r, r, r * 2, r * 0.22); g.fill(); },
  globe(g, r) { g.lineWidth = r * 0.14; g.beginPath(); g.arc(0, 0, r * 0.9, 0, TAU); g.stroke(); g.beginPath(); g.ellipse(0, 0, r * 0.4, r * 0.9, 0, 0, TAU); g.stroke(); g.beginPath(); g.moveTo(-r * 0.9, 0); g.lineTo(r * 0.9, 0); g.stroke(); },
  star(g, r) { g.beginPath(); for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * TAU / 10, rr = i % 2 ? r * 0.42 : r; g.lineTo(Math.cos(a) * rr, Math.sin(a) * rr); } g.closePath(); g.fill(); },
  mail(g, r) { g.beginPath(); g.roundRect(-r, -r * 0.65, r * 2, r * 1.3, r * 0.15); g.fill(); g.strokeStyle = 'rgba(0,0,0,0.35)'; g.lineWidth = r * 0.14; g.beginPath(); g.moveTo(-r * 0.9, -r * 0.5); g.lineTo(0, r * 0.15); g.lineTo(r * 0.9, -r * 0.5); g.stroke(); },
  bluetooth(g, r) { g.lineWidth = r * 0.2; g.lineJoin = 'round'; g.beginPath(); g.moveTo(-r * 0.6, -r * 0.5); g.lineTo(r * 0.6, r * 0.5); g.lineTo(0, r * 1.0); g.lineTo(0, -r * 1.0); g.lineTo(r * 0.6, -r * 0.5); g.lineTo(-r * 0.6, r * 0.5); g.stroke(); },
  photo(g, r) { g.beginPath(); g.roundRect(-r, -r * 0.8, r * 2, r * 1.6, r * 0.2); g.fill(); g.fillStyle = 'rgba(0,0,0,0.3)'; g.beginPath(); g.moveTo(-r * 0.8, r * 0.6); g.lineTo(-r * 0.2, -r * 0.1); g.lineTo(r * 0.2, r * 0.35); g.lineTo(r * 0.5, 0); g.lineTo(r * 0.8, r * 0.6); g.closePath(); g.fill(); },
};
const GLYPH_KEYS = [['wifi', 'wi-fi'], ['wifi', 'wifi'], ['plane', 'airplane'], ['plane', 'flight'], ['moon', 'focus'], ['moon', 'sleep'], ['moon', 'dark'], ['bell', 'notif'], ['bell', 'alert'], ['lock', 'lock'], ['lock', 'privacy'],
  ['lock', 'security'], ['sun', 'bright'], ['sun', 'display'], ['battery', 'batter'], ['battery', 'charg'], ['camera', 'camera'], ['camera', 'photo'], ['music', 'music'], ['music', 'sound'], ['music', 'audio'],
  ['heart', 'health'], ['gear', 'setting'], ['gear', 'general'], ['message', 'message'], ['message', 'chat'], ['phone', 'phone'], ['phone', 'call'], ['globe', 'safari'], ['globe', 'web'], ['globe', 'network'],
  ['globe', 'cellular'], ['mail', 'mail'], ['bluetooth', 'bluetooth'], ['star', 'favor'], ['star', 'star'], ['photo', 'gallery'], ['photo', 'picture']];
export function glyphFor(label, icon) {
  const t = String(icon || label || '').toLowerCase();
  if (GLYPHS[t]) return t;
  for (const [g, key] of GLYPH_KEYS) if (t.includes(key)) return g;
  return null;
}
/** An app icon: a coloured squircle tile with the glyph (or the first letter) in white. Centre (cx, cy), side s. */
export function drawTile(g, cx, cy, s, label, color, icon, glyphK = 1) {
  g.save(); g.translate(cx, cy);
  const col = color || colorFor(label), gr = g.createLinearGradient(0, -s / 2, 0, s / 2); gr.addColorStop(0, col); gr.addColorStop(1, shade(col, 0.72));
  g.fillStyle = gr; g.beginPath(); squirclePath(g, -s / 2, -s / 2, s, s); g.fill();
  HOLE = shade(col, 0.86); const gl = glyphFor(label, icon); g.fillStyle = g.strokeStyle = '#FFFFFF';
  if (glyphK > 0.001) {   // glyphK 0..1 (1.1 allowed): the glyph's scale, so a builder can pop it in after the tile
    if (gl) { g.save(); g.scale(glyphK, glyphK); GLYPHS[gl](g, s * 0.27); g.restore(); }
    else { g.save(); g.scale(glyphK, glyphK); g.font = FONT(700, s * 0.48); g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(String(label || '?').trim().charAt(0).toUpperCase() || '?', 0, s * 0.03); g.restore(); }
  }
  g.restore();
}
function shade(hex, m) {
  const c = String(hex).replace('#', ''), n = c.length === 3 ? c.split('').map((x) => x + x).join('') : c.padEnd(6, '0').slice(0, 6);
  const v = [0, 2, 4].map((i) => Math.max(0, Math.min(255, Math.round(parseInt(n.slice(i, i + 2), 16) * m))));
  return `rgb(${v[0]},${v[1]},${v[2]})`;
}

// ---------- layout ----------
const GAP = 18, MX = 26, RH = 78;   // RH: list row height
function compH(c) {
  switch (c.type) {
    case 'header': return c.sub ? 112 : 76;
    case 'list': return (c.title ? 48 : 0) + (c.rows || []).length * RH + 10;
    case 'widget': return c.h || 190;
    case 'notif': return 118;
    case 'dock': return 116;
    case 'grid': return Math.ceil(((c.icons || []).length || 1) / 4) * 128;
    case 'slider': return 92;
    case 'clock': return 230;
    default: return 80;
  }
}
/** The rect { x, y, w, h } of every component on the 540 x 1170 screen: stacked from `top` unless a component gives its own x / y / w. */
export function uiLayout(ui) {
  let y = ui.top ?? 150;
  return (ui.components || []).map((c) => {
    const h = compH(c), r = { x: c.x ?? MX, y: c.y ?? y, w: c.w ?? SCREEN_W - 2 * MX, h };
    if (c.y == null) y += h + GAP;
    return r;
  });
}

// ---------- the scripted cursor and the toggles it flips ----------
function rowCentre(ui, rects, step) {
  const c = (ui.components || [])[step.comp ?? 0], r = rects[step.comp ?? 0];
  if (!c || !r) return null;
  if (c.type === 'list' && step.row != null) {
    const y0 = r.y + (c.title ? 48 : 0) + 5, rr = Math.max(0, Math.min(step.row, c.rows.length - 1));
    return { x: c.rows[rr].toggle !== undefined ? r.x + r.w - 56 : r.x + r.w * 0.62, y: y0 + rr * RH + RH / 2 };
  }
  return { x: r.x + r.w * 0.5, y: r.y + r.h * 0.5 };
}
const LEAD = 0.7;   // seconds the cursor takes to glide to a target before the press
export function cursorState(ui, rects, t) {
  const steps = (ui.script || []).filter((s) => Number.isFinite(s.at)).sort((a, b) => a.at - b.at);
  if (!steps.length || ui.cursor === false) return null;
  let from = { x: SCREEN_W * 0.82, y: SCREEN_H * 0.9 }, pos = null, press = 0, ripple = null;
  for (let i = 0; i < steps.length; i++) {
    const tgt = rowCentre(ui, rects, steps[i]); if (!tgt) continue;
    const t0 = Math.max(steps[i].at - LEAD, i ? steps[i - 1].at + 0.35 : -1);
    if (i === 0 && t < t0 - 0.3) return null;                      // not on screen until just before its first move: it fades in, then glides
    if (t < t0) { pos = pos || from; break; }
    const k = smooth((t - t0) / Math.max(0.2, steps[i].at - t0));
    const arc = Math.sin(clamp01((t - t0) / Math.max(0.2, steps[i].at - t0)) * Math.PI) * 14;   // a slight arc so it reads as a hand, not a line
    pos = { x: lerp(from.x, tgt.x, k) + arc * 0.4, y: lerp(from.y, tgt.y, k) - arc };
    const dt = t - steps[i].at;
    if (dt >= 0 && dt < 0.45) { press = dt < 0.12 ? smooth(dt / 0.12) : 1 - smooth((dt - 0.12) / 0.33); ripple = { x: tgt.x, y: tgt.y, k: dt / 0.45 }; }
    if (t >= steps[i].at) from = tgt;
  }
  const first = steps.length ? Math.max(steps[0].at - LEAD, -1) : 0;
  return pos ? { ...pos, press, ripple, alpha: smooth((t - first + 0.3) / 0.3) } : null;
}
function toggleOn(ui, ci, ri, base, t) {
  let state = base ? 1 : 0;
  for (const s of (ui.script || []).filter((q) => (q.comp ?? 0) === ci && q.row === ri && Number.isFinite(q.at)).sort((a, b) => a.at - b.at)) {
    const k = smooth((t - s.at - 0.05) / 0.25); state = k >= 1 ? 1 - state : lerp(state, 1 - state, k);
  }
  return state;
}
const pressedRow = (ui, ci, ri, t) => {
  let best = 0;
  for (const s of (ui.script || [])) if ((s.comp ?? 0) === ci && s.row === ri && t >= s.at && t < s.at + 0.45) best = Math.max(best, 1 - smooth((t - s.at) / 0.45));
  return best;
};

// ---------- components ----------
function panel(g, r, T, radius = 26, strong = false) {
  g.save(); g.fillStyle = strong ? T.panel : T.panel; g.beginPath(); g.roundRect(r.x, r.y, r.w, r.h, radius); g.fill();
  g.strokeStyle = T.line; g.lineWidth = 1; g.stroke(); g.restore();
}
function text(g, s, x, y, px, w, color, align = 'left', base = 'middle') {
  g.font = FONT(w, px); g.textAlign = align; g.textBaseline = base; g.fillStyle = color; g.fillText(String(s), x, y);
}
function fit(g, s, px, w, maxW) { g.font = FONT(w, px); let p = px; while (p > 10 && g.measureText(String(s)).width > maxW) p -= 1; return p; }
function toggle(g, x, y, on, acc, T) {   // an iOS-style switch, centre (x, y); on 0..1
  const w = 68, h = 40; g.save(); g.fillStyle = on > 0.5 ? acc : T.off; if (on > 0 && on < 1) g.fillStyle = mix(T.off, acc, on);
  g.beginPath(); g.roundRect(x - w / 2, y - h / 2, w, h, h / 2); g.fill();
  g.fillStyle = '#FFFFFF'; g.shadowColor = 'rgba(0,0,0,0.3)'; g.shadowBlur = 5; g.beginPath(); g.arc(x - w / 2 + h / 2 + on * (w - h), y, h / 2 - 3, 0, TAU); g.fill(); g.restore();
}
function mix(a, b, k) {
  const rgb = (c) => { if (c.startsWith('rgba')) return c.match(/[\d.]+/g).slice(0, 3).map(Number); const h = c.replace('#', ''); const n = h.length === 3 ? h.split('').map((x) => x + x).join('') : h; return [0, 2, 4].map((i) => parseInt(n.slice(i, i + 2), 16)); };
  const A = rgb(a), B = rgb(b); return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], k))).join(',')})`;
}

function drawComponent(g, c, ci, r, ui, t, T, acc, solo) {
  const px = r.x, py = r.y;
  switch (c.type) {
    case 'header': {
      if (solo) panel(g, r, T);
      let tx = px + (solo ? 24 : 4);
      if (c.avatar !== false && c.sub) { g.fillStyle = mix(acc, '#ffffff', 0.15); g.beginPath(); g.arc(tx + 32, py + r.h / 2, 32, 0, TAU); g.fill(); text(g, String(c.text || '?').charAt(0).toUpperCase(), tx + 32, py + r.h / 2 + 1, 32, 700, '#fff', 'center'); tx += 80; }
      const p1 = fit(g, c.text, c.sub ? 40 : 50, 700, r.w - (tx - px) - 20);
      text(g, c.text || '', tx, c.sub ? py + r.h * 0.38 : py + r.h / 2, p1, 700, T.ink);
      if (c.sub) text(g, c.sub, tx, py + r.h * 0.74, fit(g, c.sub, 23, 500, r.w - (tx - px) - 20), 500, T.sub);
      break;
    }
    case 'list': {
      panel(g, r, T);
      let y0 = py + 5;
      if (c.title) { text(g, String(c.title).toUpperCase(), px + 22, py + 28, 17, 600, T.sub); y0 += 48; }
      (c.rows || []).forEach((row, i) => {
        const cy = y0 + i * RH + RH / 2, pr = pressedRow(ui, ci, i, t);
        if (pr > 0) { g.fillStyle = T.panel2; g.globalAlpha = pr; g.beginPath(); g.roundRect(px + 8, cy - RH / 2 + 4, r.w - 16, RH - 8, 20); g.fill(); g.globalAlpha = 1; }
        drawTile(g, px + 50, cy, 48, row.label, row.color, row.icon);
        const rightRoom = row.toggle !== undefined ? 100 : row.value ? 150 : 56;
        text(g, row.label, px + 92, cy, fit(g, row.label, 28, 500, r.w - 92 - rightRoom), 500, T.ink);
        if (row.toggle !== undefined) toggle(g, px + r.w - 56, cy, toggleOn(ui, ci, i, row.toggle, t), acc, T);
        else {
          if (row.value) text(g, row.value, px + r.w - 48, cy, 24, 500, T.sub, 'right');
          g.strokeStyle = T.sub; g.lineWidth = 2.6; g.lineCap = 'round'; g.beginPath(); g.moveTo(px + r.w - 34, cy - 8); g.lineTo(px + r.w - 25, cy); g.lineTo(px + r.w - 34, cy + 8); g.stroke();
        }
        if (i < c.rows.length - 1) { g.strokeStyle = T.line; g.lineWidth = 1; g.beginPath(); g.moveTo(px + 92, cy + RH / 2); g.lineTo(px + r.w - 8, cy + RH / 2); g.stroke(); }
      });
      break;
    }
    case 'widget': {
      const tint = c.tint || acc; g.save(); const gr = g.createLinearGradient(px, py, px + r.w, py + r.h); gr.addColorStop(0, shade(tint, 1.05)); gr.addColorStop(1, shade(tint, 0.62));
      g.fillStyle = gr; g.beginPath(); g.roundRect(px, py, r.w, r.h, 30); g.fill();
      g.fillStyle = 'rgba(255,255,255,0.10)'; g.beginPath(); g.roundRect(px + 2, py + 2, r.w - 4, r.h * 0.45, 28); g.fill(); g.restore();
      text(g, c.title || '', px + 26, py + 34, 26, 600, '#FFFFFF'); text(g, c.big || '', px + 26, py + r.h * 0.55, fit(g, c.big || '', 84, 600, r.w - 52), 600, '#FFFFFF');
      if (c.sub) text(g, c.sub, px + 26, py + r.h - 30, fit(g, c.sub, 24, 500, r.w - 52), 500, 'rgba(255,255,255,0.86)');
      break;
    }
    case 'notif': {
      panel(g, r, T, 28);
      drawTile(g, px + 52, py + 59, 62, c.app, c.color, c.icon);
      text(g, c.title || c.app || '', px + 100, py + 40, fit(g, c.title || c.app || '', 27, 700, r.w - 100 - 90), 700, T.ink);
      text(g, c.time || 'now', px + r.w - 22, py + 40, 20, 500, T.sub, 'right');
      text(g, c.body || '', px + 100, py + 80, fit(g, c.body || '', 24, 500, r.w - 100 - 24), 500, T.sub);
      break;
    }
    case 'dock': case 'grid': {
      if (c.type === 'dock') panel(g, r, T, 34);
      const n = Math.max(1, (c.icons || []).length), cols = c.type === 'dock' ? n : 4, step = r.w / Math.max(cols, 1), s = c.type === 'dock' ? 74 : 86;
      (c.icons || []).forEach((ic, i) => {
        const col = c.type === 'dock' ? i : i % 4, row = c.type === 'dock' ? 0 : Math.floor(i / 4), cx = px + step * (col + 0.5), cy = py + (c.type === 'dock' ? r.h / 2 : 58 + row * 128);
        drawTile(g, cx, cy, s, ic.label, ic.color, ic.icon);
        if (c.type === 'grid' && ic.label) text(g, ic.label, cx, cy + s / 2 + 20, fit(g, ic.label, 19, 500, step - 8), 500, T.ink, 'center');
      });
      break;
    }
    case 'slider': {
      panel(g, r, T, 22); const v = clamp01(c.value ?? 0.5), y = py + r.h * 0.64, x0 = px + 24, x1 = px + r.w - 24;
      text(g, c.label || '', px + 24, py + 28, 22, 600, T.sub);
      g.fillStyle = T.off; g.beginPath(); g.roundRect(x0, y - 7, x1 - x0, 14, 7); g.fill(); g.fillStyle = acc; g.beginPath(); g.roundRect(x0, y - 7, (x1 - x0) * v, 14, 7); g.fill();
      g.fillStyle = '#fff'; g.shadowColor = 'rgba(0,0,0,0.3)'; g.shadowBlur = 6; g.beginPath(); g.arc(x0 + (x1 - x0) * v, y, 15, 0, TAU); g.fill(); g.shadowBlur = 0;
      break;
    }
    case 'clock': {
      if (c.date !== false) text(g, c.date || 'Tuesday, October 21', px + r.w / 2, py + 40, 28, 600, T.ink, 'center');
      text(g, c.time || '9:41', px + r.w / 2, py + 136, 138, 700, T.ink, 'center');
      break;
    }
    default: break;
  }
}

function drawCursor(g, cur, style, T) {
  const { x, y, press, ripple } = cur; g.save(); g.globalAlpha *= cur.alpha ?? 1;
  if (ripple) { g.save(); g.strokeStyle = 'rgba(255,255,255,0.85)'; g.lineWidth = 3; g.globalAlpha = 1 - ripple.k; g.beginPath(); g.arc(ripple.x, ripple.y, 18 + ripple.k * 44, 0, TAU); g.stroke(); g.restore(); }
  g.save(); g.translate(x, y);
  if (style === 'arrow') {   // a pointer, scaled down a touch while pressed
    const s = 1 - 0.12 * press; g.scale(s, s); g.fillStyle = '#FFFFFF'; g.strokeStyle = '#111'; g.lineWidth = 2.5; g.shadowColor = 'rgba(0,0,0,0.4)'; g.shadowBlur = 8;
    g.beginPath(); g.moveTo(0, 0); g.lineTo(0, 34); g.lineTo(9, 26); g.lineTo(15, 40); g.lineTo(22, 37); g.lineTo(16, 24); g.lineTo(28, 24); g.closePath(); g.fill(); g.stroke();
  } else {   // a fingertip: a soft translucent disc that tightens on the press
    const r = 30 - 8 * press; g.fillStyle = 'rgba(255,255,255,0.30)'; g.shadowColor = 'rgba(0,0,0,0.35)'; g.shadowBlur = 14; g.beginPath(); g.arc(0, 0, r, 0, TAU); g.fill();
    g.shadowBlur = 0; g.strokeStyle = 'rgba(255,255,255,0.8)'; g.lineWidth = 2.5; g.stroke();
  }
  g.restore(); g.restore();
}

/** Draw the interface on the 540 x 1170 screen (the caller sets the transform). opt.skip: component indexes drawn elsewhere (exploded cards). */
export function uiDraw(g, ui, t, opt = {}) {
  const T = THEMES[ui.theme === 'light' ? 'light' : 'dark'], acc = ui.accent || '#0a84ff', rects = uiLayout(ui), skip = opt.skip || null;
  g.save(); g.lineJoin = 'round';
  (ui.components || []).forEach((c, i) => {
    if (skip && skip.has(i)) return;
    const k = c.in != null ? smooth((t - c.in) / 0.5) : 1;   // optional staggered entrance
    if (k <= 0.001) return;
    g.save(); g.globalAlpha *= k; g.translate(0, (1 - k) * 22); drawComponent(g, c, i, rects[i], ui, t, T, acc, false); g.restore();
  });
  const cur = opt.cursor === false ? null : cursorState(ui, rects, t);
  if (cur) drawCursor(g, cur, ui.cursor === 'arrow' ? 'arrow' : 'touch', T);
  g.restore();
}

/** One component on its own glass card (for the exploded layers): { canvas, w, h } in logical px; the canvas is `scale` times larger. */
export function uiCard(ui, index, t, scale = 2, cache = null) {
  const rects = uiLayout(ui), r = rects[index], c = (ui.components || [])[index];
  if (!r || !c) return null;
  const pad = 14, W = r.w + pad * 2, H = r.h + pad * 2, cv = cache || document.createElement('canvas');
  if (cv.width !== Math.round(W * scale)) { cv.width = Math.round(W * scale); cv.height = Math.round(H * scale); }
  const g = cv.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height); g.setTransform(scale, 0, 0, scale, 0, 0);
  const T = THEMES[ui.theme === 'light' ? 'light' : 'dark'], acc = ui.accent || '#0a84ff', rr = { x: pad, y: pad, w: r.w, h: r.h };
  if (c.type === 'header' || c.type === 'clock' || c.type === 'grid') { g.fillStyle = ui.theme === 'light' ? 'rgba(255,255,255,0.82)' : 'rgba(22,22,28,0.78)'; g.beginPath(); g.roundRect(rr.x, rr.y, rr.w, rr.h, 26); g.fill(); }
  drawComponent(g, c, index, rr, ui, t, T, acc, c.type === 'header' ? false : false);
  return { canvas: cv, w: W, h: H, rect: r, pad };
}

/** A lock screen for a phone on a wall: a gradient wallpaper with a clock, the date and (optionally) a widget row. Static, drawn once. */
export function drawLockScreen(g, opt = {}) {
  const c1 = opt.c1 || '#5b3cc4', c2 = opt.c2 || '#1d6fe0', c3 = opt.c3 || '#0b1030';
  const bg = g.createLinearGradient(0, 0, SCREEN_W * 0.4, SCREEN_H); bg.addColorStop(0, c1); bg.addColorStop(0.55, c2); bg.addColorStop(1, c3); g.fillStyle = bg; g.fillRect(0, 0, SCREEN_W, SCREEN_H);
  const seed = hash(c1 + c2);
  for (let i = 0; i < 4; i++) {   // soft blobs so no two screens look alike
    const a = ((seed >> (i * 3)) & 7) / 7, x = SCREEN_W * (0.2 + 0.6 * a), y = SCREEN_H * (0.3 + 0.18 * i), r = 170 + 40 * i, gr = g.createRadialGradient(x, y, 0, x, y, r);
    gr.addColorStop(0, i % 2 ? 'rgba(255,255,255,0.20)' : 'rgba(255,120,200,0.22)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, SCREEN_W, SCREEN_H);
  }
  g.fillStyle = 'rgba(255,255,255,0.92)'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.font = FONT(600, 26); g.fillText(opt.date || 'Monday 31 March', SCREEN_W / 2, 150); g.font = FONT(700, 150); g.fillText(opt.time || '9:41', SCREEN_W / 2, 260);
  if (opt.widgets !== false) for (let i = 0; i < 3; i++) { g.fillStyle = 'rgba(255,255,255,0.22)'; g.beginPath(); g.arc(SCREEN_W / 2 + (i - 1) * 92, 410, 36, 0, TAU); g.fill(); }
  g.fillStyle = '#05070a'; g.beginPath(); g.arc(SCREEN_W / 2, 46, 13, 0, TAU); g.fill();
}
