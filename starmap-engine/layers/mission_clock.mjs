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
    const w = Math.max(u.measure(big, 40), 200 * u.S) + 48 * u.S, x = W - 63 * u.S - w, y = 37 * u.S, h = (small ? 100 : 70) * u.S;
    u.shadow(12, 0.45); u.box(x, y, w, h, 14, 'rgba(8,19,32,0.92)'); u.noShadow();
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.font = u.font(40); g.fillStyle = '#FBE040'; g.fillText(big, x + w / 2, y + 37 * u.S);
    if (small) { g.font = u.font(20); g.fillStyle = '#ffffff'; g.fillText(small, x + w / 2, y + 79 * u.S); }
    g.textAlign = 'left';
    g.restore();
  },
};
