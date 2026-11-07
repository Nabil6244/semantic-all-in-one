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
    const d = inst.def, { g, W, H } = f, T = tm(g, W), sc = d.scale || 1, pre = d.prefix || '';
    const x0 = W * 0.18, x1 = W * 0.82, y = H * 0.55, xOf = (yr) => x0 + (x1 - x0) * (yr - d.from) / (d.to - d.from);
    const reveal = glideOut((f.t - (d.start ?? 0)) / 0.8);
    g.save(); g.globalAlpha = f.alpha; drift(g, f, d);
    T.line(x0, y, x0 + (x1 - x0) * reveal, y, { color: C.label, width: 1.5, alpha: 0.7 });
    const step = d.step || 10;
    if (d.ticks) {                                                                   // explicit ticks (a run of dates across months): only the dates, each labelled "Oct 23"
      for (const tk of d.ticks) {
        const x = xOf(tk.at);
        T.line(x, y - 6 * T.S, x, y + 6 * T.S, { color: C.label, width: 1.2, alpha: 0.7 });
        T.text(String(tk.text), x, y + 34 * T.S * sc, { font: T.mono(14 * sc, 600), align: 'center', color: C.label, shadow: 0 });
      }
    } else for (let yr = Math.ceil(d.from / step) * step; yr <= d.to; yr += step) {
      const x = xOf(yr);
      T.line(x, y - 6 * T.S, x, y + 6 * T.S, { color: C.label, width: 1.2, alpha: 0.7 });
      T.text(pre + String(yr), x, y + 34 * T.S * sc, { font: T.mono(14 * sc, 600), align: 'center', color: C.label, shadow: 0 });
    }
    const shown = inst.events.filter((e) => (e.t ?? d.start ?? 0) <= f.t);
    if (d.connect && shown.length && shown.length < inst.events.length) {        // the line travels from the last event towards the next one and arrives as it is spoken
      const a0 = shown[shown.length - 1], a1 = inst.events[shown.length], t0 = a0.t ?? d.start ?? 0, t1 = a1.t ?? t0 + 2;
      const k = glideOut((f.t - t0) / Math.max(0.5, t1 - t0)), xa = xOf(a0.year), xb = xa + (xOf(a1.year) - xa) * k;
      T.line(xa, y, xb, y, { color: C.cyan, width: 3.5 * sc, glow: 12, alpha: 0.9 });
      T.node(xb, y, { color: C.cyan, r: 5 * sc, ring: false });
    }
    if (d.connect && shown.length > 1) {                                           // the finished stretch stays lit
      const e0 = shown[shown.length - 2], e1 = shown[shown.length - 1];
      T.line(xOf(e0.year), y, xOf(e1.year), y, { color: C.cyan, width: 3.5 * sc, glow: 12, alpha: 0.9 });
    }
    shown.forEach((e, i) => {
      const x = xOf(e.year), last = i === shown.length - 1, a = clamp01((f.t - (e.t ?? d.start ?? 0)) / 0.3);
      T.node(x, y, { color: last ? C.cyan : colour(e.color, '#F2D9A6'), r: (last ? 6 : 4.5) * sc, ring: last });
      const pr = (f.t - (e.t ?? d.start ?? 0)) / 0.8;
      if (d.connect && pr >= 0 && pr < 1) { g.save(); g.globalAlpha *= 0.6 * (1 - pr); g.strokeStyle = C.cyan; g.lineWidth = 2.5 * T.S; g.beginPath(); g.arc(x, y, (8 + 46 * pr) * T.S * sc * 0.6, 0, 7); g.stroke(); g.restore(); }   // a ring leaves each date as it lands
      if ((last || d.label_all) && e.label) {                                          // long labels wrap to short lines and alternate in height so neighbours never collide
        const words = String(e.label).toUpperCase().split(' '), lines = []; let cur = '';
        for (const w of words) { if (cur && (cur + ' ' + w).length > 14) { lines.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; }
        if (cur) lines.push(cur);
        const fs = (lines.length > 2 || d.ticks ? 0.8 : 1) * sc, lh = 24 * T.S * fs, base = y - 36 * T.S * sc - (d.ticks && i % 2 ? lines.length * lh + 14 * T.S : 0);
        lines.forEach((ln, k) => T.text(ln, Math.min(W * 0.9, Math.max(W * 0.1, x)), base - (lines.length - 1 - k) * lh, { font: T.sans(19 * fs, 800), track: 2, align: 'center', color: last ? C.cyan : '#F2D9A6', alpha: a }));
      }
      if (d.label_all && e.sub) T.text(String(e.sub), x, y + 78 * T.S * sc, { font: T.mono(14 * sc, 600), align: 'center', color: C.label, shadow: 0, alpha: a });
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
