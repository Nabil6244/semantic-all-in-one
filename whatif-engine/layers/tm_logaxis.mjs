// TM_LOGAXIS: distances as light-travel time on one logarithmic line across the frame (telemetry look). Major ticks at a
// light-second, -minute, -hour, -day and -year; places marked above the line; a glowing node ("YOU") glides to each value
// the narration gives, the line behind it lit amber; a mark lights from grey to white as the node reaches it.
//   { "type": "tm_logaxis", "min": 0.1, "max": 3.2e8, "y": 0.56,
//     "marks": [{ "v": 1.28, "label": "MOON", "sub": "1.3 LIGHT-SECONDS" }],
//     "keys": [{ "t": 12, "v": 1.28 }], "node_label": "YOU", "caption": { "text": "EVERY HUMAN JOURNEY, EVER", "color": "amber" },
//     "start": 11.5, "end": 17 }                                       (v in light-seconds)
import { C, tm, colour, glideOut, drift } from './tm_theme.mjs';

export const LIGHT = { second: 1, minute: 60, hour: 3600, day: 86400, year: 31557600 };
const MAJORS = [['1 LIGHT-SECOND', 1], ['1 LIGHT-MINUTE', 60], ['1 LIGHT-HOUR', 3600], ['1 LIGHT-DAY', 86400], ['1 LIGHT-YEAR', 31557600]];

export default {
  type: 'tm_logaxis',
  space: 'screen',
  create: (def) => ({ def, keys: (def.keys || []).slice().sort((a, b) => a.t - b.t) }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const lo = Math.log10(d.min ?? 0.1), hi = Math.log10(d.max ?? 3.2e8);
    const x0 = W * 0.0, x1 = W * 1.0, y = H * (d.y ?? 0.56);
    const xOf = (v) => x0 + (x1 - x0) * ((Math.log10(Math.max(v, 1e-9)) - lo) / (hi - lo));
    const reveal = glideOut((f.t - (d.start ?? 0)) / 0.8);
    let lv = null, cur = null;
    for (let i = 0; i < inst.keys.length; i++) {
      const k = inst.keys[i];
      if (k.t > f.t) break;
      const from = i ? Math.log10(inst.keys[i - 1].v) : lo + 0.02 * (hi - lo);
      lv = from + (Math.log10(k.v) - from) * glideOut((f.t - k.t) / 1.4); cur = k;
    }
    const nx = lv == null ? null : xOf(10 ** lv);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    // the lit stretch behind the node: everything closer than where you are
    if (nx != null) {
      const band = g.createLinearGradient(0, 0, nx, 0);
      band.addColorStop(0, 'rgba(255,183,3,0)'); band.addColorStop(1, 'rgba(255,183,3,0.22)');
      g.fillStyle = band; g.fillRect(0, y - 16 * T.S, nx, 32 * T.S);
      T.line(0, y, nx, y, { color: C.amber, width: 3, glow: 10 });
    }
    T.line(x0, y, x0 + (x1 - x0) * reveal, y, { color: '#C9D1DC', width: 1.6, alpha: 0.75 });
    for (let e = Math.floor(lo); e <= Math.ceil(hi); e++) for (let m = 1; m < 10; m++) {
      const v = m * 10 ** e, x = xOf(v);
      if (x < x0 || x > x0 + (x1 - x0) * reveal) continue;
      T.line(x, y - 5 * T.S, x, y + 5 * T.S, { color: '#C9D1DC', width: 1, alpha: 0.4 });
    }
    for (const [name, v] of MAJORS) {
      const x = xOf(v);
      if (x < x0 + 30 * T.S || x > x0 + (x1 - x0) * reveal - 30 * T.S) continue;
      T.line(x, y - 13 * T.S, x, y + 13 * T.S, { color: C.white, width: 2, alpha: 0.85 });
      T.text(name, x, y + 44 * T.S, { font: T.sans(17, 800), track: 2, align: 'center', color: C.label, shadow: 0 });
    }
    for (const m of d.marks || []) {
      const x = xOf(m.v), reached = nx != null && nx >= x - 2;
      if (x < x0 || x > x1) continue;
      const a = reached ? 1 : 0.45, col = reached ? C.white : C.label;
      T.line(x, y - 70 * T.S, x, y - 18 * T.S, { color: col, width: 1.5, alpha: a });
      // a label near an edge stays on the screen, however long it is ("PROXIMA CENTAURI" once ran off the right edge)
      const half = Math.max(T.measure(String(m.label).toUpperCase(), T.sans(30, 800), 2), m.sub ? T.measure(String(m.sub).toUpperCase(), T.mono(19, 600), 1.5) : 0) / 2;
      const lx = Math.min(W - 60 * T.S - half, Math.max(60 * T.S + half, x));
      T.text(String(m.label).toUpperCase(), lx, y - 112 * T.S, { font: T.sans(30, 800), track: 2, align: 'center', color: col, alpha: a });
      if (m.sub) T.text(String(m.sub).toUpperCase(), lx, y - 82 * T.S, { font: T.mono(19, 600), track: 1.5, align: 'center',
        color: reached ? colour(m.color, C.cream) : C.label, alpha: a });
    }
    if (nx != null) {
      T.node(nx, y, { color: C.amber, r: 8 });
      if (d.node_label) T.text(String(d.node_label).toUpperCase(), nx, y - 26 * T.S, { font: T.sans(16, 800), track: 2, align: 'center', color: C.cyan });
      const cap = cur?.caption || d.caption;
      if (cap?.text) T.text(String(cap.text).toUpperCase(), Math.max(80 * T.S, nx - 340 * T.S), y + 92 * T.S,
        { font: T.sans(28, 800), track: 2.5, color: colour(cap.color, C.amber) });
    }
    g.restore();
  },
};
