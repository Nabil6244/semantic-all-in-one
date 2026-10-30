// TM_TITLE: the episode's title card (telemetry look): a white first line and a bigger accent second line, centred in the
// upper third over the opening plate, with a small line under it ("TELL ME IN THE COMMENTS").
//   { "type": "tm_title", "line1": "WHAT IF YOU TRAVELED AT", "line2": "THE SPEED OF LIGHT?", "accent": "cyan" | "amber",
//     "sub": "", "start": 22, "end": 27 }
import { C, tm, colour, quartOut } from './tm_theme.mjs';

// the two lines' sizes (shrunk until the wider fits 84% of the frame) and the share of the frame's width they take
function fit(d, T, W) {
  let p1 = 64, p2 = 84;
  const span = () => Math.max(T.measure(d.line1 || '', T.display(p1), 2), T.measure(d.line2 || '', T.display(p2), 2));
  while (p2 > 40 && span() > W * 0.84) { p1 -= 4; p2 -= 5; }
  return { p1, p2, span: span() / W + 0.04 };
}

export default {
  type: 'tm_title',
  space: 'screen',
  create: (def) => { if (!def.line1 && !def.line2) throw new Error('tm_title: "line1" or "line2" is required'); return { def }; },
  update(inst, f) {
    // the title's box is taken before the map's labels are placed, so a label never sits on the words; where the map has pins in the
    // way (the pins already hold their boxes), the card moves to the first height that is free
    if (!f.claim || !(f.alpha > 0.05)) return;
    const d = inst.def, { W, H } = f, y0 = d.y ?? 0.2, h = H * (d.sub ? 0.24 : 0.19), bw = Math.min(0.88, fit(d, tm(f.g, W), W).span) * W;
    const free = (y) => !(f.claims || []).some((o) => W / 2 - bw / 2 < o.x + o.w && W / 2 + bw / 2 > o.x && y - H * 0.07 < o.y + o.h && y - H * 0.07 + h > o.y);
    inst.y = [y0, 0.12, 0.3, 0.42, 0.66, 0.78].find((y) => free(H * y)) ?? y0;
    f.claim(W / 2 - bw / 2, H * inst.y - H * 0.07, bw, h);
  },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const age = f.t - (d.start ?? 0), k1 = quartOut(age / 0.45), k2 = quartOut((age - 0.25) / 0.45);
    const accent = colour(d.accent, C.amber);
    const { p1, p2 } = fit(d, T, W);
    const y = H * (inst.y ?? d.y ?? 0.2);
    g.save(); g.globalAlpha = f.alpha;
    if (d.line1) T.text(String(d.line1).toUpperCase(), W / 2, y, { font: T.display(p1), track: 2, align: 'center', alpha: k1, glow: 'rgba(0,0,0,0.6)' });
    if (d.line2) T.text(String(d.line2).toUpperCase(), W / 2, y + (d.line1 ? p2 * 1.02 * T.S : 0), { font: T.display(p2), track: 2, align: 'center',
      color: accent, alpha: k2, glow: 'rgba(0,0,0,0.6)' });
    if (d.sub) T.text(String(d.sub).toUpperCase(), W / 2, y + (p2 * 1.02 + 52) * T.S, { font: T.mono(19, 600), track: 2, align: 'center', color: C.cream, alpha: k2 * 0.85 });
    g.restore();
  },
};
