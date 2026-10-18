// TM_METRIC: a spoken number on screen (telemetry look) -- "464 °C", "1.4 SECONDS" with "AT THE SPEED OF LIGHT" under it. A
// heavy white figure with a soft warm glow, scaling in from 95% (quart out) a beat before the narrator says it; or a stack of
// readouts at the left ("30 km" / "222 °C", each with a small label above and a note beside).
//   { "type": "tm_metric", "value": "464", "unit": "°C", "sub": "HOT ENOUGH TO MELT LEAD", "sub_color": "amber",
//     "size": "hero" | "large" | "medium", "anchor": "center" | "top" | "upper_left" | "left" | "right",
//     "count": { "from": 0, "to": 464, "decimals": 0, "s": 1.0 }, "color": "white", "start": 12.3, "end": 15.5 }
//   "kicker": "ALL SIX COMPUTERS TOGETHER\nHOLD ABOUT" -- one or two small cyan lines above the number (the reference's information block)
//   { "type": "tm_metric", "anchor": "left", "rows": [{ "label": "ALTITUDE", "value": "30 km", "note": "", "color": "white" }, ...] }
import { C, tm, colour, quartOut, fmt } from './tm_theme.mjs';

const SIZES = { hero: 150, large: 112, medium: 78 };
// where the reference puts a number: in the empty sky beside the subject. "464 °C" starts at x 12.5 %, centred on y 35 % (V1 0:16);
// "92 BAR" starts at x 55 %, y 18 % (V1 0:26); "55 KM UP" is centred a little below the middle (V1 0:44).
const ANCHORS = { center: [0.5, 0.5, 'center'], top: [0.5, 0.22, 'center'], upper_left: [0.125, 0.35, 'left'], left: [0.073, 0.43, 'left'],
  right: [0.927, 0.43, 'right'], upper_right: [0.55, 0.2, 'left'], low: [0.5, 0.74, 'center'], mid: [0.5, 0.52, 'center'] };

export default {
  type: 'tm_metric',
  space: 'screen',
  create: (def) => {
    if (def.value == null && !def.text && !def.rows) throw new Error('tm_metric: "value", "text" or "rows" is required');
    return { def };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const age = f.t - (d.start ?? 0), k = quartOut(age / 0.3), s = 0.95 + 0.05 * k;
    const [ax, ay, align] = ANCHORS[d.anchor] || ANCHORS.center;
    g.save(); g.globalAlpha = f.alpha * k;
    // a soft dark pool behind the type keeps it readable over a bright picture (never a box)
    const px = W * ax, py = H * ay, rad = W * 0.2, scrim = g.createRadialGradient(px, py, 0, px, py, rad);
    scrim.addColorStop(0, 'rgba(0,0,0,0.38)'); scrim.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = scrim; g.fillRect(px - rad, py - rad, rad * 2, rad * 2);
    g.translate(W * ax, H * ay); g.scale(s, s);
    if (d.rows) {
      let y = 0;
      for (const r of d.rows) {
        if (r.label) { T.text(String(r.label).toUpperCase(), 0, y, { font: T.mono(16, 600), track: 2, color: C.label }); y += 46 * T.S; }
        const w = T.text(r.value, 0, y, { font: T.display(52), color: colour(r.color), glow: 'rgba(255,214,160,0.28)', track: 1 });
        if (r.note) T.text(String(r.note).toUpperCase(), w + 18 * T.S, y - 4 * T.S, { font: T.mono(17, 600), track: 1.5, color: colour(r.note_color, C.cream) });
        y += 64 * T.S;
      }
    } else {
      let big = d.text;
      if (big == null) {
        const c = d.count;
        const v = c ? c.from + (c.to - c.from) * quartOut(age / (c.s ?? 1.0)) : null;
        big = (c ? fmt(v, c.decimals ?? 0) : String(d.value)) + (d.unit ? `${d.unit.startsWith('%') ? '' : ' '}${d.unit}` : '');
      }
      let px = SIZES[d.size] || SIZES.large;
      // the room its anchor leaves inside the frame (5 % margins): "upper_right" starts at 55 % and once ran "4.37 LIGHT-YE" off the edge
      const room = W * (align === 'left' ? 0.95 - ax : align === 'right' ? ax - 0.05 : 2 * Math.min(ax, 1 - ax) - 0.1);
      while (px > 40 && T.measure(big, T.display(px), 2) > Math.min(W * 0.8, room)) px -= 6;
      const y = d.sub ? -10 * T.S : px * 0.34 * T.S;
      // the reference's kicker (V3 1:34 "ALL SIX COMPUTERS TOGETHER / HOLD ABOUT" over "70"): cyan caps, one or two lines, above the number
      const kick = d.kicker ? String(d.kicker).toUpperCase().split('\n').slice(0, 2) : [];
      kick.forEach((ln, i) => T.text(ln, 0, y - (px * 0.78 + 16) * T.S - (kick.length - 1 - i) * 27 * T.S,
        { font: T.sans(21, 800), track: 2.4, color: colour(d.kicker_color, C.cyan), align, shadow: 0.6 }));
      T.text(String(big).toUpperCase(), 0, y, { font: T.display(px), color: colour(d.color), track: 2, align, glow: 'rgba(255,214,160,0.24)', shadow: 0.85 });
      if (d.sub) T.text(String(d.sub).toUpperCase(), 0, y + (px * 0.42 + 8) * T.S, { font: T.sans(Math.max(22, px * 0.23), 800), track: 3,
        color: colour(d.sub_color, C.amber), align });
      if (d.note) T.text(String(d.note).toUpperCase(), 0, y + (px * 0.42 + 46) * T.S, { font: T.mono(18, 600), track: 2, color: C.label, align });
    }
    g.restore();
  },
};
