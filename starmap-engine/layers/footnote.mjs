// FOOTNOTE: a small line of fine print at the bottom centre ("FLIGHT PATH ILLUSTRATED"): honest about how something is known,
// without taking the screen.
//   { "type": "footnote", "text": "FLIGHT PATH ILLUSTRATED", "start": 10, "end": 24 }
export default {
  type: 'footnote',
  space: 'screen',
  create: (def) => { if (!def.text) throw new Error('footnote: "text" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, g, W, H } = f;
    g.save(); g.globalAlpha = f.alpha * (d.opacity_text ?? 0.78);
    g.font = u.font(d.px || 14, 700); g.textAlign = 'center'; g.textBaseline = 'alphabetic';
    u.shadow(4, 0.8); g.fillStyle = '#ffffff'; g.fillText(d.text, W / 2, H - (d.bottom ?? 22) * u.S); u.noShadow();
    g.textAlign = 'left';
    g.restore();
  },
};
