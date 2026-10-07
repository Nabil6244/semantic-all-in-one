// STATUS_BADGE: what the viewer must know about what they are seeing -- "PLANNED · NET SEP 2027", "HYPOTHETICAL · 2050",
// "ESTIMATED · DATA TO JUN 2026". Top right, under the clock. The words and colours come from the spec; the renderer does not
// know what they mean.
//   { "type": "status_badge", "text": "PLANNED · NET SEP 2027", "bg": "#5fd3ff", "fg": "#06121d", "start": 12, "end": 30 }
export default {
  type: 'status_badge',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('status_badge: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, g, W } = f, px = d.px || 18;
    const w = u.measure(d.text, px) + 30 * u.S, h = (px + 16) * u.S, x = W - 52 * u.S - w;
    const y = f.place(x, (d.y ?? 120) * u.S, w, h);
    g.save(); g.globalAlpha = f.alpha;
    u.shadow(10, 0.45); u.box(x, y, w, h, 8, d.bg || '#ffffff'); u.noShadow();
    g.font = u.font(px); g.fillStyle = d.fg || '#06121d'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(d.text, x + w / 2, y + h / 2 + 1 * u.S); g.textAlign = 'left';
    g.restore();
  },
};
