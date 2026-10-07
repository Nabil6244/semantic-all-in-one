// PHOTO_CARD: a photograph on screen: white frame, the picture (cover-cropped, a slow push-in), a yellow title chip under
// it, an optional caption line and a source credit. The image is content (spec "media"), never part of the renderer.
//   { "type": "photo_card", "image": "as11-40-5903.jpg", "title": "BUZZ ALDRIN ON THE MOON", "caption": "20 JULY 1969",
//     "credit": "NASA", "x": 1437, "y": 190, "width": 420, "height": 303, "side": "right", "enter": "rise" | "slide" | "fade",
//     "start": 50, "end": 58 }
const smooth = (k) => { const x = Math.min(1, Math.max(0, k)); return x * x * (3 - 2 * x); };

export default {
  type: 'photo_card',
  space: 'screen',
  async create(def, ctx) {
    if (!def.image) throw new Error('photo_card: "image" is required');
    return { def, img: await ctx.loadImage(def.image) };
  },
  draw(inst, f) {
    const d = inst.def, { u, g, W } = f, img = inst.img;
    const w = (d.width ?? 420) * u.S, h = (d.height ?? 303) * u.S;
    let x = d.x != null ? d.x * u.S : d.side === 'left' ? 63 * u.S : W - 63 * u.S - w, y = (d.y ?? 190) * u.S;
    const enter = smooth((f.t - (d.start ?? 0)) / (d.fade_in ?? 0.5));
    if ((d.enter || 'rise') === 'rise') y += (1 - enter) * 40 * u.S;
    else if (d.enter === 'slide') x += (1 - enter) * (d.side === 'left' ? -60 : 60) * u.S;
    g.save(); g.globalAlpha = f.alpha;
    u.shadow(18, 0.55); u.box(x - 5 * u.S, y - 5 * u.S, w + 10 * u.S, h + 10 * u.S, 18, '#ffffff'); u.noShadow();
    // the photo: cover-cropped, pushing in slowly while the card is up
    const life = d.end != null && d.start != null ? Math.min(1, Math.max(0, (f.mu(f.t) - f.mu(d.start)) / Math.max(1e-6, f.mu(d.end) - f.mu(d.start)))) : 0;
    const zoom = 1 + (d.push_in ?? 0.06) * life;
    const s = Math.max(w / img.width, h / img.height) * zoom, sw = w / s, sh = h / s;
    g.save(); g.beginPath(); g.roundRect(x, y, w, h, 13 * u.S); g.clip();
    g.drawImage(img, (img.width - sw) / 2, (img.height - sh) / 2, sw, sh, x, y, w, h);
    if (d.credit) {
      g.font = u.font(15, 700); const cw = g.measureText(d.credit).width + 16 * u.S;
      g.fillStyle = 'rgba(0,0,0,0.55)'; g.fillRect(x + w - cw, y + h - 26 * u.S, cw, 26 * u.S);
      g.fillStyle = '#ffffff'; g.textBaseline = 'middle'; g.fillText(d.credit, x + w - cw + 8 * u.S, y + h - 12 * u.S);
    }
    g.restore();
    if (d.title) {
      const tw = u.measure(d.title, 26) + 32 * u.S;
      u.chip(x + w / 2 - tw / 2, y + h + 11 * u.S, d.title, 26, { bg: '#FBE040', padX: 16, h: 42 });
    }
    if (d.caption) {
      const cw = u.measure(d.caption, 20) + 24 * u.S;
      u.chip(x + w / 2 - cw / 2, y + h + 61 * u.S, d.caption, 20, { bg: '#111111', fg: '#ffffff', padX: 12, h: 34 });
    }
    g.restore();
  },
};
