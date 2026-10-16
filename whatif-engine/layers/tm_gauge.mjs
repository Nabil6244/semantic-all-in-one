// TM_GAUGE: a vertical gauge down the right edge (telemetry look) -- the altitude of a descent, the depth of a dive. A thin
// scale with numbered ticks and coloured zones; a glowing node glides to each value the narration gives, trailing a line to
// its readout ("46 km" / "1.79 bar · 104 °C"); zone labels light up while the node is in them.
//   { "type": "tm_gauge", "label": "ALTITUDE", "min": 0, "max": 80, "step": 10,
//     "zones": [{ "from": 48, "to": 70, "label": "ACID CLOUDS", "color": "amber" }],
//     "keys": [{ "t": 30, "v": 55, "text": "55 km", "sub": "27 °C · 0.53 bar" }], "start": 28, "end": 120 }
import { C, tm, colour, glideOut, plateAlpha } from './tm_theme.mjs';

export default {
  type: 'tm_gauge',
  space: 'screen',
  create: (def) => {
    if (!(def.max > def.min)) throw new Error('tm_gauge: needs min < max');
    return { def, keys: (def.keys || []).slice().sort((a, b) => a.t - b.t) };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), keys = inst.keys;
    const away = d.hide_on_plates === false ? 1 : 1 - plateAlpha(f.spec, f.t);
    const x = W - 56 * T.S, y0 = H * 0.24, y1 = H * 0.86;   // below a top-right card
    const yOf = (v) => y1 - (y1 - y0) * ((v - d.min) / (d.max - d.min));
    // the node's value: glides (1.2 s, eased) from the previous key to each new one
    let v = keys.length ? keys[0].v : d.min, cur = null;
    for (let i = 0; i < keys.length; i++) {
      if (keys[i].t > f.t) break;
      const from = i ? keys[i - 1].v : keys[i].v;
      v = from + (keys[i].v - from) * glideOut((f.t - keys[i].t) / 1.2); cur = keys[i];
    }
    g.save(); g.globalAlpha = f.alpha * away;
    T.text(String(d.label || 'ALTITUDE').toUpperCase(), x, y0 - 40 * T.S, { font: T.sans(17, 800), track: 3, align: 'right', color: '#E8ECF2', shadow: 0.4 });
    for (const z of d.zones || []) {
      T.line(x, yOf(z.to), x, yOf(z.from), { color: colour(z.color, C.label), width: 3 });
      const inside = v >= z.from && v <= z.to;
      if (z.label) T.text(String(z.label).toUpperCase(), x - 40 * T.S, (yOf(z.to) + yOf(z.from)) / 2 + 6 * T.S,
        { font: T.sans(15, 800), track: 2, align: 'right', color: inside ? C.white : C.label, alpha: inside ? 1 : 0.7, shadow: 0.4 });
    }
    T.line(x, y0, x, y1, { color: C.label, width: 1.5, alpha: 0.6 });
    const step = d.step || (d.max - d.min) / 8;
    for (let t = d.min; t <= d.max + 1e-9; t += step) {
      const y = yOf(t);
      T.line(x - 8 * T.S, y, x, y, { color: C.label, width: 1.5, alpha: 0.7 });
      T.text(String(Math.round(t * 100) / 100), x + 10 * T.S, y + 5 * T.S, { font: T.mono(12, 600), color: C.label, shadow: 0 });
    }
    const ny = yOf(Math.max(d.min, Math.min(d.max, v)));
    T.line(x - 260 * T.S, ny, x, ny, { color: C.cyan, width: 1.5, alpha: 0.7 });
    T.node(x, ny, { color: C.cyan, r: 7 });
    if (cur?.text) T.text(cur.text, x - 262 * T.S, ny - 16 * T.S, { font: T.sans(34, 800), align: 'right', track: 1 });
    if (cur?.sub) T.text(cur.sub, x - 262 * T.S, ny + 20 * T.S, { font: T.mono(18, 600), align: 'right', color: C.cream });
    g.restore();
  },
};
