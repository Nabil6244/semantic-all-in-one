// TM_FADE: the frame fades to black and back (telemetry look) -- kept for the moments a probe goes silent or a person blacks
// out. Visibility is the layer's own start / end / fade_in / fade_out.
//   { "type": "tm_fade", "start": 9.4, "end": 11.0, "fade_in": 0.7, "fade_out": 0.6 }
export default {
  type: 'tm_fade',
  space: 'screen',
  over_footage: true,
  create: (def) => ({ def }),
  draw(inst, f) {
    const { g, W, H } = f;
    g.save(); g.globalAlpha = f.alpha; g.fillStyle = '#000'; g.fillRect(0, 0, W, H); g.restore();
  },
};
