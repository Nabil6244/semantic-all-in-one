// TM_ORBITMAP: the solar system seen from above, to scale in rings (telemetry look): the Sun, planet orbits as thin circles,
// a glowing path ("YOU") drawn out to a place, with labelled stops. For "THE SUN AND ITS PLANETS", a fly-by route, a signal home.
//   { "type": "tm_orbitmap", "scale": "sqrt", "extent_au": 40, "path": [{ "t": 8, "au": 5.2, "angle": 40, "label": "JUPITER FLY-BY, 1979" }, ...],
//     "you": "SATURN, 1980", "start": 6, "end": 14 }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

const PLANETS = [['MERCURY', 0.39], ['VENUS', 0.72], ['EARTH', 1], ['MARS', 1.52], ['JUPITER', 5.2], ['SATURN', 9.58], ['URANUS', 19.2], ['NEPTUNE', 30.1]];
export default {
  type: 'tm_orbitmap',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W), ext = d.extent_au || 32, cx = W * (d.cx ?? 0.5), cy = H * (d.cy ?? 0.55), R = H * 0.4;
    const rOf = (au) => R * Math.sqrt(Math.min(au, ext * 1.5) / ext);        // a square-root scale keeps the inner planets visible
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    const reveal = glideOut((f.t - (d.start ?? 0)) / 0.9);
    for (const [name, au] of PLANETS) if (au <= ext * 1.1) {
      g.strokeStyle = 'rgba(255,255,255,0.2)'; g.lineWidth = 1.5 * T.S; g.beginPath(); g.arc(cx, cy, rOf(au) * reveal, 0, Math.PI * 2); g.stroke();
      if (d.labels !== false && reveal > 0.9) T.text(name, cx + rOf(au) * 0.707 + 6 * T.S, cy - rOf(au) * 0.707 - 4 * T.S, { font: T.mono(12, 600), color: C.label, shadow: 0 });
    }
    T.node(cx, cy, { color: C.amber, r: 9 }); T.text('THE SUN', cx - 14 * T.S, cy + 30 * T.S, { font: T.sans(15, 800), track: 2, align: 'right', shadow: 0 });
    const pts = (d.path || []).map((p) => ({ ...p, x: cx + Math.cos(p.angle * Math.PI / 180) * rOf(p.au), y: cy - Math.sin(p.angle * Math.PI / 180) * rOf(p.au) }));
    let last = null;
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i]; if (f.t < p.t) break;
      const a = i ? pts[i - 1] : { x: cx, y: cy }, k = glideOut((f.t - p.t) / 1.3), x = a.x + (p.x - a.x) * k, y = a.y + (p.y - a.y) * k;
      T.line(a.x, a.y, x, y, { color: C.amber, width: 3, glow: 8 }); last = { x, y, p, k };
    }
    if (last) {
      T.node(last.x, last.y, { color: C.cyan, r: 8 }); T.text('YOU', last.x + 24 * T.S, last.y - 6 * T.S, { font: T.sans(20, 800), track: 2, shadow: 0 });
      if (last.p.label) T.text(String(last.p.label).toUpperCase(), last.x + 24 * T.S, last.y + 20 * T.S, { font: T.mono(14, 600), color: C.cream, shadow: 0 });
    }
    g.restore();
  },
};
