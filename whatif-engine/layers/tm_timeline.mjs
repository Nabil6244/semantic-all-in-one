// TM_TIMELINE: years along one line (telemetry look) -- "LANDINGS ON VENUS": a dot appears for each event as the narration
// reaches it, the latest one labelled; an optional stretch after the last event in red ("NOTHING SINCE").
//   { "type": "tm_timeline", "from": 1970, "to": 2026, "step": 10,
//     "events": [{ "t": 50, "year": 1970, "label": "VENERA 7" }, ...], "gap_to": 2026, "gap_label": "NOTHING SINCE", "start": 49, "end": 56 }
import { C, tm, colour, glideOut, clamp01, drift } from './tm_theme.mjs';

export default {
  type: 'tm_timeline',
  space: 'screen',
  create: (def) => {
    if (!(def.to > def.from)) throw new Error('tm_timeline: needs from < to (years)');
    return { def, events: (def.events || []).slice().sort((a, b) => a.year - b.year) };
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const x0 = W * 0.18, x1 = W * 0.82, y = H * 0.55, xOf = (yr) => x0 + (x1 - x0) * (yr - d.from) / (d.to - d.from);
    const reveal = glideOut((f.t - (d.start ?? 0)) / 0.8);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    T.line(x0, y, x0 + (x1 - x0) * reveal, y, { color: C.label, width: 1.5, alpha: 0.7 });
    const step = d.step || 10;
    for (let yr = Math.ceil(d.from / step) * step; yr <= d.to; yr += step) {
      const x = xOf(yr);
      T.line(x, y - 6 * T.S, x, y + 6 * T.S, { color: C.label, width: 1.2, alpha: 0.7 });
      T.text(String(yr), x, y + 34 * T.S, { font: T.mono(14, 600), align: 'center', color: C.label, shadow: 0 });
    }
    const shown = inst.events.filter((e) => (e.t ?? d.start ?? 0) <= f.t);
    shown.forEach((e, i) => {
      const x = xOf(e.year), last = i === shown.length - 1, a = clamp01((f.t - (e.t ?? d.start ?? 0)) / 0.3);
      T.node(x, y, { color: last ? C.cyan : colour(e.color, '#F2D9A6'), r: last ? 6 : 4.5, ring: last });
      if (last && e.label) T.text(String(e.label).toUpperCase(), x, y - 36 * T.S, { font: T.sans(19, 800), track: 2, align: 'center', color: C.cyan, alpha: a });
    });
    if (d.gap_to && shown.length && shown.length === inst.events.length) {
      const last = inst.events[inst.events.length - 1], k = glideOut((f.t - (last.t ?? 0) - 0.6) / 1.2);
      if (k > 0) {
        const xa = xOf(last.year), xb = xa + (xOf(d.gap_to) - xa) * k;
        T.line(xa, y, xb, y, { color: C.red, width: 3, glow: 8 });
        if (d.gap_label) T.text(String(d.gap_label).toUpperCase(), W / 2, y + 140 * T.S, { font: T.display(56), track: 2, align: 'center', alpha: k });
      }
    }
    g.restore();
  },
};
