// TIME_JUMP: the map dips dark for a moment while the universe date jumps (1969 -> 2026, 2027 -> 2050 · HYPOTHETICAL), and a
// card says where time went. The jump itself is in the spec's clock (one frame at "at"); this only hides it and names it.
//   { "type": "time_jump", "at": 31.2, "text": "1969 → 2026", "start": 30.75, "end": 33.0 }
const smooth = (x) => { const k = Math.min(1, Math.max(0, x)); return k * k * (3 - 2 * k); };

/** How dark the map is at narration time t (1 = black): fully dark for a moment around the jump. */
export function dipAt(def, t) {
  const lead = Math.max(0.05, def.at - (def.start ?? def.at - 0.45)), hold = def.hold_s ?? 0.12, out = def.out_s ?? 0.5;
  if (t <= def.at - lead || t >= def.at + hold + out) return 0;
  if (t < def.at - hold) return smooth((t - (def.at - lead)) / Math.max(1e-6, lead - hold));
  if (t <= def.at + hold) return 1;
  return 1 - smooth((t - def.at - hold) / out);
}

export default {
  type: 'time_jump',
  space: 'screen',
  create: (def) => { if (!Number.isFinite(def.at)) throw new Error('time_jump: "at" (narration seconds) is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, g, W, H } = f, dark = dipAt(d, f.t);
    g.save();
    if (dark > 0) { g.globalAlpha = dark; g.fillStyle = '#000000'; g.fillRect(0, 0, W, H); }
    const show = f.t >= d.at - 0.1 ? Math.min(1, (f.t - (d.at - 0.1)) / 0.25) * Math.min(1, ((d.end ?? d.at + 1.8) - f.t) / 0.4) : 0;
    if (d.text && show > 0) {
      const px = 40, w = u.measure(d.text, px) + 60 * u.S, h = 84 * u.S, x = (W - w) / 2, y = H * 0.42 - h / 2;
      g.globalAlpha = show;
      u.shadow(16, 0.6); u.box(x, y, w, h, 14, 'rgba(8,19,32,0.94)'); u.noShadow();
      g.font = u.font(px); g.fillStyle = '#FBE040'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(d.text, W / 2, y + h / 2 + 1 * u.S); g.textAlign = 'left';
    }
    g.restore();
  },
};
