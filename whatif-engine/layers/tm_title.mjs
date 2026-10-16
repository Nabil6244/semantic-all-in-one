// TM_TITLE: the episode's title card (telemetry look): a white first line and a bigger accent second line, centred in the
// upper third over the opening plate, with a small line under it ("TELL ME IN THE COMMENTS").
//   { "type": "tm_title", "line1": "WHAT IF YOU TRAVELED AT", "line2": "THE SPEED OF LIGHT?", "accent": "cyan" | "amber",
//     "sub": "", "start": 22, "end": 27 }
import { C, tm, colour, quartOut } from './tm_theme.mjs';

export default {
  type: 'tm_title',
  space: 'screen',
  create: (def) => { if (!def.line1 && !def.line2) throw new Error('tm_title: "line1" or "line2" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const age = f.t - (d.start ?? 0), k1 = quartOut(age / 0.45), k2 = quartOut((age - 0.25) / 0.45);
    const accent = colour(d.accent, C.amber);
    let p1 = 64, p2 = 84;
    while (p2 > 40 && Math.max(T.measure(d.line1 || '', T.display(p1), 2), T.measure(d.line2 || '', T.display(p2), 2)) > W * 0.84) { p1 -= 4; p2 -= 5; }
    const y = H * (d.y ?? 0.2);
    g.save(); g.globalAlpha = f.alpha;
    if (d.line1) T.text(String(d.line1).toUpperCase(), W / 2, y, { font: T.display(p1), track: 2, align: 'center', alpha: k1, glow: 'rgba(0,0,0,0.6)' });
    if (d.line2) T.text(String(d.line2).toUpperCase(), W / 2, y + (d.line1 ? p2 * 1.02 * T.S : 0), { font: T.display(p2), track: 2, align: 'center',
      color: accent, alpha: k2, glow: 'rgba(0,0,0,0.6)' });
    if (d.sub) T.text(String(d.sub).toUpperCase(), W / 2, y + (p2 * 1.02 + 52) * T.S, { font: T.mono(19, 600), track: 2, align: 'center', color: C.cream, alpha: k2 * 0.85 });
    g.restore();
  },
};
