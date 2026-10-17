// BIG_NUMBER: a full-screen number moment -- the map dims, a huge figure counts up in the middle with its unit and a line
// under it, then it leaves (the compiler hands the number on to a corner stat chip). For the few numbers a video turns on.
//   { "type": "big_number", "value": 24000000000, "unit": "KM", "label": "FROM EARTH", "decimals": 0,
//     "start": 41.2, "end": 44.4, "fade_in": 0.35, "fade_out": 0.5 }
const fmt = (v, dec) => v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
const easeOut = (x) => 1 - (1 - Math.min(1, Math.max(0, x))) ** 3;

export default {
  type: 'big_number',
  space: 'screen',
  create: (def) => { if (def.value == null) throw new Error('big_number: "value" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def, { u, g, W, H } = f;
    const k = easeOut((f.t - d.start) / 1.3);                     // counts up over the first 1.3 s
    let big = typeof d.value === 'number' ? fmt(d.value * k, d.decimals ?? 0) : String(d.value);
    g.save();
    // the map steps back: a dark vignette, strongest at the edges
    const grd = g.createRadialGradient(W / 2, H / 2, H * 0.1, W / 2, H / 2, H * 0.95);
    grd.addColorStop(0, 'rgba(2,6,14,0.55)'); grd.addColorStop(1, 'rgba(2,6,14,0.88)');
    g.globalAlpha = f.alpha; g.fillStyle = grd; g.fillRect(0, 0, W, H);
    const s = 0.9 + 0.1 * easeOut((f.t - d.start) / 0.6);         // a small scale-in, settling
    g.translate(W / 2, H / 2 - 20 * u.S); g.scale(s, s);
    g.textAlign = 'center'; g.textBaseline = 'alphabetic';
    let size = 170;
    g.font = u.font(size);
    const unit = d.unit ? ` ${d.unit}` : '';
    while (size > 70 && u.measure(big, size) + u.measure(unit, size * 0.42) > W * 0.86 / u.S * u.S) { size -= 10; g.font = u.font(size); }
    const wNum = u.measure(big, size), wUnit = unit ? u.measure(unit, size * 0.42) : 0, x0 = -(wNum + wUnit) / 2;
    u.shadow(30, 0.6);
    g.textAlign = 'left'; g.fillStyle = d.color || '#FBE040'; g.font = u.font(size); g.fillText(big, x0, 40 * u.S);
    if (unit) { g.fillStyle = '#ffffff'; g.font = u.font(size * 0.42); g.fillText(unit, x0 + wNum, 40 * u.S); }
    u.noShadow();
    if (d.label) {
      g.textAlign = 'center'; g.fillStyle = 'rgba(255,255,255,0.92)'; g.font = u.font(34, 700);
      g.fillText(String(d.label).split('').join(String.fromCharCode(8202)), 0, 40 * u.S + 70 * u.S);
    }
    g.restore();
  },
};
