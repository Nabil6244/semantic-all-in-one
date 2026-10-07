// CAPTION: a lower-third line of text (a quote, a fact, a translation).
//   { "type": "caption", "text": "THE EAGLE HAS LANDED", "sub": "NEIL ARMSTRONG, 20:17 UTC" }
export default {
  type: 'caption',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('caption: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, g, W, H } = f;
    const w = Math.max(u.measure(d.text, 40), d.sub ? u.measure(d.sub, 22) : 0) + 60 * u.S, h = (d.sub ? 108 : 76) * u.S;
    const x = (W - w) / 2, y = H - (d.bottom ?? 70) * u.S - h;
    g.save(); g.globalAlpha = f.alpha;
    u.shadow(14, 0.5); u.box(x, y, w, h, 14, 'rgba(8,19,32,0.92)'); u.noShadow();
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = u.font(40); g.fillStyle = '#ffffff'; g.fillText(d.text, W / 2, y + 39 * u.S);
    if (d.sub) { g.font = u.font(22); g.fillStyle = '#FBE040'; g.fillText(d.sub, W / 2, y + 82 * u.S); }
    g.textAlign = 'left';
    g.restore();
  },
};
