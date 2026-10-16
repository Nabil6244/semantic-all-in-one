// ICONS: the small drawn figures templates use (an astronaut, an eye, a letter ...). Drawn with canvas paths -- nothing to download,
// nothing generated per video -- in the What If line style: white or one meaning colour, soft round strokes. Each icon draws in a unit
// box centred on (0, 0), about 1 high; the caller scales it. opts: { color, level (0..1, thermometer / hourglass / battery), burn (0..1, letter) }.

const TAU = Math.PI * 2;
function rr(g, x, y, w, h, r) { g.beginPath(); g.roundRect(x, y, w, h, r); }
const stroke = (g, w = 0.05) => { g.lineWidth = w; g.stroke(); };

export const ICONS = {
  astronaut(g, o) {
    const c = o.color || '#F2F4F7';
    g.fillStyle = '#C9CED6'; rr(g, -0.27, -0.12, 0.54, 0.42, 0.08); g.fill();                     // backpack
    g.fillStyle = c;
    rr(g, -0.42, -0.06, 0.16, 0.42, 0.08); g.fill(); rr(g, 0.26, -0.06, 0.16, 0.42, 0.08); g.fill();   // arms
    rr(g, -0.24, -0.1, 0.48, 0.5, 0.12); g.fill();                                                   // torso
    rr(g, -0.22, 0.32, 0.18, 0.2, 0.06); g.fill(); rr(g, 0.04, 0.32, 0.18, 0.2, 0.06); g.fill();       // legs
    g.beginPath(); g.arc(0, -0.28, 0.22, 0, TAU); g.fill();                                          // helmet
    g.fillStyle = '#1B2230'; rr(g, -0.15, -0.36, 0.3, 0.16, 0.08); g.fill();                         // visor
    g.fillStyle = 'rgba(120,200,255,0.55)'; rr(g, -0.11, -0.34, 0.08, 0.05, 0.02); g.fill();
    g.fillStyle = '#8E99A8'; g.fillRect(-0.12, 0.02, 0.24, 0.08);                                    // chest panel
  },
  human(g, o) {
    g.fillStyle = o.color || '#F2F4F7';
    g.beginPath(); g.arc(0, -0.36, 0.12, 0, TAU); g.fill();
    rr(g, -0.14, -0.2, 0.28, 0.36, 0.08); g.fill();
    rr(g, -0.13, 0.12, 0.1, 0.38, 0.04); g.fill(); rr(g, 0.03, 0.12, 0.1, 0.38, 0.04); g.fill();
    rr(g, -0.24, -0.18, 0.08, 0.32, 0.04); g.fill(); rr(g, 0.16, -0.18, 0.08, 0.32, 0.04); g.fill();
  },
  eye(g, o) {
    const c = o.color || '#F2F4F7';
    g.strokeStyle = c; g.beginPath(); g.moveTo(-0.45, 0); g.quadraticCurveTo(0, -0.42, 0.45, 0); g.quadraticCurveTo(0, 0.42, -0.45, 0); stroke(g, 0.07);
    g.fillStyle = o.accent || '#00E5FF'; g.beginPath(); g.arc(0, 0, 0.14, 0, TAU); g.fill();
    g.fillStyle = '#05070B'; g.beginPath(); g.arc(0, 0, 0.06, 0, TAU); g.fill();
  },
  star(g, o) {
    g.fillStyle = o.color || '#FFFFFF';
    g.beginPath();
    for (let i = 0; i < 8; i++) { const a = (i / 8) * TAU - Math.PI / 2, r = i % 2 ? 0.1 : 0.48; g.lineTo(Math.cos(a) * r, Math.sin(a) * r); }
    g.closePath(); g.fill();
  },
  letter(g, o) {
    const burn = o.burn || 0;
    g.save(); g.rotate(-0.08);
    g.fillStyle = '#EFE6D2'; g.beginPath(); g.moveTo(-0.42, -0.32); g.lineTo(0.42, -0.36); g.lineTo(0.44, 0.34 - burn * 0.5); g.lineTo(-0.4, 0.32 - burn * 0.55); g.closePath(); g.fill();
    g.strokeStyle = 'rgba(60,60,70,0.55)'; g.lineWidth = 0.035;
    for (let i = 0; i < 6; i++) { const y = -0.22 + i * 0.09; if (y > 0.3 - burn * 0.55) break; g.beginPath(); g.moveTo(-0.32, y); g.lineTo(0.3 - (i % 3) * 0.08, y - 0.01); g.stroke(); }
    if (burn > 0) {
      const y = 0.32 - burn * 0.55; const grd = g.createLinearGradient(0, y - 0.06, 0, y + 0.06);
      grd.addColorStop(0, 'rgba(255,120,30,0)'); grd.addColorStop(0.5, 'rgba(255,140,40,0.95)'); grd.addColorStop(1, 'rgba(255,60,20,0)');
      g.fillStyle = grd; g.fillRect(-0.46, y - 0.06, 0.92, 0.12);
    }
    g.restore();
  },
  rocket(g, o) {
    const c = o.color || '#F2F4F7';
    g.fillStyle = c; g.beginPath(); g.moveTo(0, -0.5); g.quadraticCurveTo(0.2, -0.25, 0.14, 0.25); g.lineTo(-0.14, 0.25); g.quadraticCurveTo(-0.2, -0.25, 0, -0.5); g.fill();
    g.beginPath(); g.moveTo(-0.14, 0.05); g.lineTo(-0.28, 0.32); g.lineTo(-0.12, 0.25); g.fill();
    g.beginPath(); g.moveTo(0.14, 0.05); g.lineTo(0.28, 0.32); g.lineTo(0.12, 0.25); g.fill();
    g.fillStyle = '#00E5FF'; g.beginPath(); g.arc(0, -0.18, 0.06, 0, TAU); g.fill();
    g.fillStyle = '#FFB703'; g.beginPath(); g.moveTo(-0.09, 0.27); g.lineTo(0, 0.5); g.lineTo(0.09, 0.27); g.fill();
  },
  heart(g, o) {
    g.fillStyle = o.color || '#FF2A4B'; g.beginPath(); g.moveTo(0, 0.38);
    g.bezierCurveTo(-0.6, -0.05, -0.28, -0.52, 0, -0.18); g.bezierCurveTo(0.28, -0.52, 0.6, -0.05, 0, 0.38); g.fill();
  },
  skull(g, o) {
    g.fillStyle = o.color || '#F2F4F7';
    g.beginPath(); g.arc(0, -0.08, 0.34, Math.PI, 0); g.lineTo(0.3, 0.14); g.lineTo(0.16, 0.2); g.lineTo(0.16, 0.36); g.lineTo(-0.16, 0.36); g.lineTo(-0.16, 0.2); g.lineTo(-0.3, 0.14); g.closePath(); g.fill();
    g.fillStyle = '#05070B'; g.beginPath(); g.arc(-0.13, -0.04, 0.08, 0, TAU); g.fill(); g.beginPath(); g.arc(0.13, -0.04, 0.08, 0, TAU); g.fill();
    g.beginPath(); g.moveTo(0, 0.06); g.lineTo(-0.04, 0.14); g.lineTo(0.04, 0.14); g.fill();
  },
  thermometer(g, o) {
    const lvl = Math.max(0, Math.min(1, o.level ?? 0.6)), c = o.color || '#FF2A4B';
    g.strokeStyle = '#F2F4F7'; rr(g, -0.08, -0.46, 0.16, 0.66, 0.08); stroke(g, 0.04);
    g.beginPath(); g.arc(0, 0.3, 0.15, 0, TAU); stroke(g, 0.04);
    g.fillStyle = c; g.beginPath(); g.arc(0, 0.3, 0.11, 0, TAU); g.fill();
    g.fillRect(-0.04, 0.2 - 0.6 * lvl, 0.08, 0.6 * lvl + 0.02);
  },
  hourglass(g, o) {
    const lvl = Math.max(0, Math.min(1, o.level ?? 0.5)), c = o.color || '#FFB703';
    g.strokeStyle = '#F2F4F7'; g.beginPath(); g.moveTo(-0.26, -0.44); g.lineTo(0.26, -0.44); g.lineTo(0.03, 0); g.lineTo(0.26, 0.44); g.lineTo(-0.26, 0.44); g.lineTo(-0.03, 0); g.closePath(); stroke(g, 0.04);
    g.fillStyle = c;
    const top = 0.4 * lvl; g.beginPath(); g.moveTo(-0.03 - 0.22 * (top / 0.44), -top); g.lineTo(0.03 + 0.22 * (top / 0.44), -top); g.lineTo(0.02, -0.02); g.lineTo(-0.02, -0.02); g.closePath(); g.fill();
    const bot = 0.4 * (1 - lvl); g.beginPath(); g.moveTo(-0.24, 0.42); g.lineTo(0.24, 0.42); g.lineTo(0.24 - 0.2 * (bot / 0.44), 0.42 - bot); g.lineTo(-0.24 + 0.2 * (bot / 0.44), 0.42 - bot); g.closePath(); g.fill();
  },
  satellite(g, o) {
    const c = o.color || '#F2F4F7';
    g.fillStyle = '#2F6BDF'; g.fillRect(-0.5, -0.1, 0.3, 0.2); g.fillRect(0.2, -0.1, 0.3, 0.2);
    g.fillStyle = c; rr(g, -0.14, -0.16, 0.28, 0.32, 0.04); g.fill(); g.fillRect(-0.2, -0.015, 0.4, 0.03);
    g.strokeStyle = c; g.beginPath(); g.arc(0, -0.28, 0.1, 0.2, Math.PI - 0.2); stroke(g, 0.035);
  },
  planet(g, o) {
    const c = o.color || '#C9A36A';
    g.fillStyle = c; g.beginPath(); g.arc(0, 0, 0.28, 0, TAU); g.fill();
    g.strokeStyle = '#F3E3C3'; g.save(); g.scale(1, 0.32); g.beginPath(); g.arc(0, 0, 0.48, 0, TAU); g.restore(); stroke(g, 0.035);
  },
  sun(g, o) {
    const c = o.color || '#FFB703';
    g.strokeStyle = c; for (let i = 0; i < 12; i++) { const a = (i / 12) * TAU; g.beginPath(); g.moveTo(Math.cos(a) * 0.34, Math.sin(a) * 0.34); g.lineTo(Math.cos(a) * 0.48, Math.sin(a) * 0.48); stroke(g, 0.045); }
    g.fillStyle = c; g.beginPath(); g.arc(0, 0, 0.26, 0, TAU); g.fill();
  },
  atom(g, o) {
    const c = o.color || '#00E5FF';
    g.strokeStyle = c;
    for (let i = 0; i < 3; i++) { g.save(); g.rotate((i * Math.PI) / 3); g.scale(1, 0.36); g.beginPath(); g.arc(0, 0, 0.45, 0, TAU); g.restore(); stroke(g, 0.03); }
    g.fillStyle = '#FFFFFF'; g.beginPath(); g.arc(0, 0, 0.07, 0, TAU); g.fill();
  },
  lightning(g, o) {
    g.fillStyle = o.color || '#FFB703'; g.beginPath(); g.moveTo(0.08, -0.5); g.lineTo(-0.24, 0.06); g.lineTo(-0.02, 0.06); g.lineTo(-0.1, 0.5); g.lineTo(0.24, -0.08); g.lineTo(0.02, -0.08); g.closePath(); g.fill();
  },
  flame(g, o) {
    g.fillStyle = o.color || '#FF7A1A'; g.beginPath(); g.moveTo(0, -0.48); g.bezierCurveTo(0.36, -0.1, 0.34, 0.4, 0, 0.44); g.bezierCurveTo(-0.34, 0.4, -0.36, -0.1, 0, -0.48); g.fill();
    g.fillStyle = '#FFD27A'; g.beginPath(); g.moveTo(0, -0.08); g.bezierCurveTo(0.16, 0.1, 0.16, 0.36, 0, 0.38); g.bezierCurveTo(-0.16, 0.36, -0.16, 0.1, 0, -0.08); g.fill();
  },
  drop(g, o) {
    g.fillStyle = o.color || '#2F6BDF'; g.beginPath(); g.moveTo(0, -0.46); g.bezierCurveTo(0.3, -0.05, 0.32, 0.4, 0, 0.42); g.bezierCurveTo(-0.32, 0.4, -0.3, -0.05, 0, -0.46); g.fill();
  },
  warning(g, o) {
    g.strokeStyle = o.color || '#FFB703'; g.beginPath(); g.moveTo(0, -0.42); g.lineTo(0.46, 0.38); g.lineTo(-0.46, 0.38); g.closePath(); g.lineJoin = 'round'; stroke(g, 0.06);
    g.fillStyle = o.color || '#FFB703'; g.fillRect(-0.03, -0.14, 0.06, 0.3); g.beginPath(); g.arc(0, 0.27, 0.04, 0, TAU); g.fill();
  },
  check(g, o) { g.strokeStyle = o.color || '#2EE6A8'; g.lineCap = 'round'; g.beginPath(); g.moveTo(-0.32, 0.02); g.lineTo(-0.08, 0.28); g.lineTo(0.36, -0.26); stroke(g, 0.1); },
  cross(g, o) { g.strokeStyle = o.color || '#FF2A4B'; g.lineCap = 'round'; g.beginPath(); g.moveTo(-0.28, -0.28); g.lineTo(0.28, 0.28); g.moveTo(0.28, -0.28); g.lineTo(-0.28, 0.28); stroke(g, 0.1); },
  question(g, o) {
    g.strokeStyle = o.color || '#00E5FF'; g.lineCap = 'round'; g.beginPath(); g.arc(0, -0.14, 0.2, Math.PI * 1.05, Math.PI * 0.45); g.lineTo(0, 0.14); stroke(g, 0.09);
    g.fillStyle = o.color || '#00E5FF'; g.beginPath(); g.arc(0, 0.34, 0.06, 0, TAU); g.fill();
  },
  magnet(g, o) {
    g.strokeStyle = o.color || '#FF2A4B'; g.lineCap = 'butt'; g.beginPath(); g.arc(0, 0, 0.28, Math.PI, 0); g.lineTo(0.28, 0.36); g.moveTo(-0.28, 0); g.lineTo(-0.28, 0.36); stroke(g, 0.16);
    g.strokeStyle = '#F2F4F7'; g.beginPath(); g.moveTo(-0.28, 0.26); g.lineTo(-0.28, 0.4); g.moveTo(0.28, 0.26); g.lineTo(0.28, 0.4); stroke(g, 0.16);
  },
  ship(g, o) {
    g.fillStyle = o.color || '#F2F4F7'; g.beginPath(); g.moveTo(-0.5, 0.06); g.lineTo(0.5, 0.06); g.lineTo(0.36, 0.26); g.lineTo(-0.4, 0.26); g.closePath(); g.fill();
    g.fillRect(-0.2, -0.12, 0.36, 0.18); g.fillRect(0.02, -0.3, 0.08, 0.2);
  },
  plane(g, o) {
    g.fillStyle = o.color || '#F2F4F7'; rr(g, -0.5, -0.05, 1.0, 0.1, 0.05); g.fill();
    g.beginPath(); g.moveTo(-0.05, -0.04); g.lineTo(0.15, -0.04); g.lineTo(-0.15, -0.42); g.lineTo(-0.25, -0.42); g.fill();
    g.beginPath(); g.moveTo(-0.05, 0.04); g.lineTo(0.15, 0.04); g.lineTo(-0.15, 0.42); g.lineTo(-0.25, 0.42); g.fill();
    g.beginPath(); g.moveTo(-0.42, -0.03); g.lineTo(-0.5, -0.2); g.lineTo(-0.44, -0.2); g.lineTo(-0.34, -0.03); g.fill();
  },
  car(g, o) {
    g.fillStyle = o.color || '#F2F4F7'; rr(g, -0.46, -0.02, 0.92, 0.2, 0.06); g.fill();
    g.beginPath(); g.moveTo(-0.26, -0.02); g.lineTo(-0.14, -0.2); g.lineTo(0.18, -0.2); g.lineTo(0.3, -0.02); g.fill();
    g.fillStyle = '#05070B'; g.beginPath(); g.arc(-0.24, 0.2, 0.09, 0, TAU); g.arc(0.24, 0.2, 0.09, 0, TAU); g.fill();
  },
  building(g, o) {
    g.fillStyle = o.color || '#C9CED6'; g.fillRect(-0.3, -0.46, 0.34, 0.92); g.fillRect(0.06, -0.2, 0.24, 0.66);
    g.fillStyle = '#05070B'; for (let r = 0; r < 7; r++) for (let c = 0; c < 2; c++) g.fillRect(-0.24 + c * 0.14, -0.38 + r * 0.12, 0.08, 0.06);
  },
  tree(g, o) {
    g.fillStyle = '#7A5A3C'; g.fillRect(-0.05, 0.1, 0.1, 0.36);
    g.fillStyle = o.color || '#2EE6A8'; g.beginPath(); g.arc(0, -0.12, 0.3, 0, TAU); g.fill();
  },
  brain(g, o) {
    g.strokeStyle = o.color || '#F3A6C0';
    g.beginPath(); g.ellipse(0, 0, 0.42, 0.32, 0, 0, TAU); stroke(g, 0.05);
    g.beginPath(); g.moveTo(0, -0.32); g.bezierCurveTo(-0.08, -0.1, 0.08, 0.1, 0, 0.32); stroke(g, 0.04);
    for (const s of [-1, 1]) { g.beginPath(); g.moveTo(s * 0.32, -0.12); g.quadraticCurveTo(s * 0.12, -0.02, s * 0.3, 0.12); stroke(g, 0.035); }
  },
  cell(g, o) {
    g.strokeStyle = o.color || '#2EE6A8'; g.beginPath(); g.ellipse(0, 0, 0.44, 0.34, 0.3, 0, TAU); stroke(g, 0.05);
    g.fillStyle = o.color || '#2EE6A8'; g.beginPath(); g.arc(0.06, -0.02, 0.12, 0, TAU); g.fill();
  },
  camera(g, o) {
    g.fillStyle = o.color || '#F2F4F7'; rr(g, -0.42, -0.22, 0.84, 0.5, 0.06); g.fill(); g.fillRect(-0.14, -0.32, 0.28, 0.12);
    g.fillStyle = '#05070B'; g.beginPath(); g.arc(0, 0.03, 0.17, 0, TAU); g.fill();
  },
  radio(g, o) {
    g.strokeStyle = o.color || '#00E5FF'; g.fillStyle = o.color || '#00E5FF'; g.beginPath(); g.arc(0, 0.2, 0.06, 0, TAU); g.fill();
    for (const r of [0.18, 0.32, 0.46]) { g.beginPath(); g.arc(0, 0.2, r, -Math.PI * 0.8, -Math.PI * 0.2); stroke(g, 0.045); }
  },
  battery(g, o) {
    const lvl = Math.max(0, Math.min(1, o.level ?? 0.7));
    g.strokeStyle = '#F2F4F7'; rr(g, -0.42, -0.2, 0.78, 0.4, 0.05); stroke(g, 0.045); g.fillStyle = '#F2F4F7'; g.fillRect(0.38, -0.08, 0.06, 0.16);
    g.fillStyle = o.color || (lvl < 0.25 ? '#FF2A4B' : '#2EE6A8'); g.fillRect(-0.37, -0.15, 0.68 * lvl, 0.3);
  },
  cube(g, o) {
    const c = o.color || '#C9CED6';
    g.fillStyle = c; g.beginPath(); g.moveTo(0, -0.42); g.lineTo(0.38, -0.2); g.lineTo(0, 0.02); g.lineTo(-0.38, -0.2); g.closePath(); g.fill();
    g.globalAlpha *= 0.75; g.beginPath(); g.moveTo(-0.38, -0.2); g.lineTo(0, 0.02); g.lineTo(0, 0.46); g.lineTo(-0.38, 0.24); g.closePath(); g.fill();
    g.globalAlpha *= 0.7; g.beginPath(); g.moveTo(0.38, -0.2); g.lineTo(0, 0.02); g.lineTo(0, 0.46); g.lineTo(0.38, 0.24); g.closePath(); g.fill();
  },
  telescope(g, o) {
    g.fillStyle = o.color || '#F2F4F7'; g.save(); g.rotate(-0.5); rr(g, -0.42, -0.09, 0.7, 0.18, 0.04); g.fill(); g.fillRect(0.28, -0.12, 0.1, 0.24); g.restore();
    g.strokeStyle = o.color || '#F2F4F7'; g.beginPath(); g.moveTo(0, 0.02); g.lineTo(-0.22, 0.46); g.moveTo(0, 0.02); g.lineTo(0.22, 0.46); stroke(g, 0.04);
  },
};
export const ICON_NAMES = Object.keys(ICONS).sort();

/** Draw icon `name` centred at (x, y), `size` px high. */
export function drawIcon(g, name, x, y, size, opts = {}) {
  const f = ICONS[name];
  if (!f) throw new Error(`icon "${name}" is not one of ${ICON_NAMES.join(', ')}`);
  g.save(); g.translate(x, y); g.rotate(((opts.rot || 0) * Math.PI) / 180); g.scale(size * (opts.sx ?? 1) * (opts.flip ? -1 : 1), size * (opts.sy ?? 1));
  g.lineCap = 'round'; g.lineJoin = 'round';
  f(g, opts);
  g.restore();
}
