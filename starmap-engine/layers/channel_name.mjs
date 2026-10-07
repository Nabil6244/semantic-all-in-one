// CHANNEL_NAME: the channel's name as a quiet watermark (bottom corner, a small yellow play mark before it), the same
// look as PakMap's. Shown over footage too unless "over_footage": false. spec.watermark = {"text": ...} (what the app passes
// for PakMap) adds one automatically.
//   { "type": "channel_name", "text": "MY CHANNEL", "corner": "br" | "bl", "opacity": 0.6 }
export default {
  type: 'channel_name',
  space: 'screen',
  over_footage: true,
  create: (def) => { if (!def.text) throw new Error('channel_name: "text" is required'); return { def, text: String(def.text).toUpperCase() }; },
  draw(inst, f) {
    const { u, g, W, H } = f, left = inst.def.corner === 'bl', px = 22, icon = 30 * u.S;
    g.save(); g.globalAlpha = f.alpha * (inst.def.opacity_text ?? 0.6);
    g.font = u.font(px); g.letterSpacing = `${u.S}px`;
    const w = g.measureText(inst.text).width, base = H - 36 * u.S;
    const tx = left ? 36 * u.S + icon : W - 36 * u.S - w, ix = tx - icon;
    u.shadow(6, 0.6);
    g.fillStyle = '#FBE040'; g.beginPath();
    g.moveTo(ix + 6 * u.S, base - 17 * u.S); g.lineTo(ix + 6 * u.S, base + 1 * u.S); g.lineTo(ix + 21 * u.S, base - 8 * u.S); g.closePath(); g.fill();
    g.fillStyle = '#ffffff'; g.textAlign = 'left'; g.textBaseline = 'alphabetic'; g.fillText(inst.text, tx, base);
    u.noShadow(); g.restore();
  },
};
