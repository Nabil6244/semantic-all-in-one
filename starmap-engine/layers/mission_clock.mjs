// MISSION_CLOCK: the universe clock on screen (top right): mission elapsed time over the date, or just the date.
//   { "type": "mission_clock", "show": "met+utc" | "met" | "utc" }
export default {
  type: 'mission_clock',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const show = inst.def.show || 'met+utc', { u, g, W } = f;
    const met = show.includes('met') ? f.clock.met(f.t) : null;
    const when = show.includes('utc') || !met ? f.date.toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : null;
    const big = met || when, small = met ? when : null;
    g.save(); g.globalAlpha = f.alpha;
    const w = Math.max(u.measure(big, 28), 140 * u.S) + 34 * u.S, x = W - 52 * u.S - w, y = 37 * u.S, h = (small ? 72 : 50) * u.S;
    u.shadow(12, 0.45); u.box(x, y, w, h, 10, 'rgba(8,19,32,0.92)'); u.noShadow();
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = u.font(28); g.fillStyle = '#FBE040'; g.fillText(big, x + w / 2, y + 26 * u.S);
    if (small) { g.font = u.font(15); g.fillStyle = '#ffffff'; g.fillText(small, x + w / 2, y + 57 * u.S); }
    g.textAlign = 'left';
    g.restore();
  },
};
