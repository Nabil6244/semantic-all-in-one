// TM_CAPTION: a lower-left lockup (telemetry look): an optional small coloured kicker, a bold tracked line and a monospaced
// note under it -- "47 KM: PARACHUTE RELEASED" / "AS ON VENERA 13", or a name card: "YOUR SHIP" / "VOYAGER 1" /
// "LAUNCHED 5 SEPTEMBER 1977". size "large" is the name card's heavy display line.
//   { "type": "tm_caption", "kicker": "AT SATURN", "kicker_color": "cyan", "text": "THE TEAM'S CHOICE", "sub": "ON TO PLUTO",
//     "size": "small" | "large" | "photo", "anchor": "bl" | "ml" | "tl" | "bc", "start": 3, "end": 7.5 }
//   anchor "bc": the lockup centred at the bottom ("VENERA 13" / "1 MARCH 1982"), as under the reference's hero shots (y 88 % / 92 %).
//   size "photo": the caption centred under a letterboxed real photograph (bold grey line, mono line under it; y 78 %).
import { C, tm, colour, quartOut } from './tm_theme.mjs';

const ANCHOR_Y = { bl: 0.74, ml: 0.5, tl: 0.24 };

export default {
  type: 'tm_caption',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('tm_caption: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, T = tm(g, W);
    const k = quartOut((f.t - (d.start ?? 0)) / 0.35);
    if (d.anchor === 'bc' || d.size === 'photo') {
      const photo = d.size === 'photo', y = H * (photo ? 0.78 : 0.88);
      g.save(); g.globalAlpha = f.alpha * k;
      const txt = String(d.text).toUpperCase();
      let px = photo ? 27 : 29;
      while (px > 18 && T.measure(txt, T.sans(px, 800), 3) > W * 0.8) px -= 2;
      T.text(txt, W / 2, y, { font: T.sans(px, 800), track: 3, align: 'center', color: photo ? '#A3AAB3' : C.white, shadow: photo ? 0 : 0.7 });
      String(d.sub || '').toUpperCase().split('\n').filter(Boolean).forEach((ln, i) => T.text(ln, W / 2, y + (photo ? 36 : 36) * T.S + i * 26 * T.S,
        { font: T.mono(photo ? 16 : 17, 600), track: 2, align: 'center', color: photo ? '#8A8F96' : colour(d.sub_color, C.cream), shadow: photo ? 0 : 0.6, alpha: 0.9 }));
      g.restore();
      return;
    }
    const x = W * 0.073, large = d.size === 'large';
    let y = H * (ANCHOR_Y[d.anchor] ?? ANCHOR_Y.bl);
    g.save(); g.globalAlpha = f.alpha; g.translate(-14 * T.S * (1 - k), 0);
    if (d.kicker) { T.text(String(d.kicker).toUpperCase(), x, y - (large ? 70 : 46) * T.S, { font: T.sans(20, 800), track: 2.5, color: colour(d.kicker_color, C.cyan) }); }
    let px = large ? 66 : 36;
    const font = (n) => (large ? T.display(n) : T.sans(n, 800));
    while (px > 30 && T.measure(String(d.text).toUpperCase(), font(px), large ? 2 : 2.5) > W - 2 * x) px -= 3;      // never off the edge
    T.text(String(d.text).toUpperCase(), x, y, large ? { font: font(px), track: 2, glow: 'rgba(255,214,160,0.22)' } : { font: font(px), track: 2.5 });
    const lines = d.sub ? String(d.sub).toUpperCase().split('\n') : [];
    lines.forEach((ln, i) => T.text(ln, x + 2 * T.S, y + (large ? 42 : 36) * T.S + i * 28 * T.S,
      { font: T.mono(19, 600), track: 1.5, color: colour(d.sub_color, C.cream), alpha: 0.88 }));
    g.restore();
  },
};
