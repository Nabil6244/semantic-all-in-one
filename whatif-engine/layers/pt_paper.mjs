// PT_PAPER: the flat "infographic" backdrop of the explainer reviews: an opaque off-white sheet with a faint paper grain, drawn first so the flat
// phones, capsules, gauges and cards sit on it. Put it first in the layer list of a shot (the shot itself can be kind "black").
//   { "type": "pt_paper", "start": 0, "end": 7, "tone": "#F2F1EE" }

let grainTile = null;
function grain(g) {
  if (grainTile) return grainTile;
  const c = (typeof OffscreenCanvas !== 'undefined') ? new OffscreenCanvas(128, 128) : (typeof document !== 'undefined' ? Object.assign(document.createElement('canvas'), { width: 128, height: 128 }) : null);
  if (!c) return null;
  const x = c.getContext('2d'), im = x.createImageData(128, 128);
  let s = 7; for (let i = 0; i < im.data.length; i += 4) { s = (s * 1664525 + 1013904223) >>> 0; const v = 120 + (s >>> 24) % 60; im.data[i] = im.data[i + 1] = im.data[i + 2] = v; im.data[i + 3] = 9; }
  x.putImageData(im, 0, 0);
  try { grainTile = g.createPattern(c, 'repeat'); } catch { grainTile = null; }
  return grainTile;
}

export default {
  type: 'pt_paper',
  space: 'screen',
  create: (def) => ({ def }),
  draw(inst, f) {
    const d = inst.def, { g, W, H } = f, a = d.start ?? 0, b = d.end ?? a + 5;
    if (f.t < a - 0.001 || f.t >= b) return;      // a hard window: a fade would show the black shot underneath at every cut
    g.save(); g.globalAlpha = f.alpha ?? 1;
    g.fillStyle = d.tone || '#F2F1EE'; g.fillRect(0, 0, W, H);
    const rg = g.createRadialGradient(W / 2, H / 2, H * 0.3, W / 2, H / 2, W * 0.75); rg.addColorStop(0, 'rgba(255,255,255,0.3)'); rg.addColorStop(1, 'rgba(0,0,0,0.015)');
    g.fillStyle = rg; g.fillRect(0, 0, W, H);
    const p = grain(g); if (p) { g.fillStyle = p; g.fillRect(0, 0, W, H); }
    g.restore();
  },
};
