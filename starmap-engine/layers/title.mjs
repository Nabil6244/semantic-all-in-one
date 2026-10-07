// TITLE: the white title chip (top left) with an optional dark subtitle chip under it.
//   { "type": "title", "text": "APOLLO 11", "subtitle": "THE FIRST LANDING", "x": 45, "y": 37 }
export default {
  type: 'title',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('title: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, g } = f, x = (d.x ?? 45) * u.S, y = (d.y ?? 37) * u.S;
    g.save(); g.globalAlpha = f.alpha;
    u.chip(x, y, d.text, 32, { padX: 14, h: 48, r: 8, shadowBlur: 6 });
    if (d.subtitle) u.chip(x - 1 * u.S, y + 55 * u.S, d.subtitle, 19, { bg: '#111111', fg: '#ffffff', padX: 11, h: 29, shadowBlur: 6 });
    g.restore();
  },
};
