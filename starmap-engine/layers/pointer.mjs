// POINTER: a pin on a thing in space with a label beside it ("YOU ARE HERE" on the Sun seen from outside the galaxy).
//   { "type": "pointer", "at": "sun", "label": "YOU ARE HERE", "sub": "ORION ARM" }
// "at" is a body, a surface point or a layer with a position. Drawn only while the point is in view.
export function drawPointer(f, p, label, sub, { color = '#FBE040' } = {}) {
  if (!p) return;
  const s = f.project(p), { u, g, W, H } = f;
  if (!s.front || s.x < 0 || s.x > W || s.y < 0 || s.y > H || f.hidden(p)) return;
  g.save(); g.globalAlpha *= 1;
  u.pin(s.x, s.y, color);
  f.claim(s.x - 14 * u.S, s.y - 14 * u.S, 28 * u.S, 28 * u.S);
  if (label) {
    const w = u.measure(label, 22) + 26 * u.S, h = 40 * u.S, w2 = sub ? u.measure(sub, 16) + 20 * u.S : 0, h2 = sub ? 30 * u.S : 0;
    const bw = Math.max(w, w2), right = s.x + 24 * u.S, left = s.x - 24 * u.S - bw;
    const at = f.placeAny(s.x > W * 0.7 ? [left, right] : [right, left], s.y - h / 2, bw, h + h2);
    const onLeft = at.x < s.x;
    u.chip(onLeft ? at.x + bw - w : at.x, at.y, label, 22, { h: 40, bg: color });
    if (sub) u.chip(onLeft ? at.x + bw - w2 : at.x, at.y + h + 4 * u.S, sub, 16, { bg: '#111111', fg: '#ffffff', padX: 10, h: 28 });
  }
  g.restore();
}

export default {
  type: 'pointer',
  space: 'world',
  create(def) { if (!def.at) throw new Error('pointer: "at" is required'); return { def }; },
  draw(inst, f) {
    const d = inst.def;
    f.g.save(); f.g.globalAlpha = f.alpha;
    drawPointer(f, f.locate(d.at), d.label || '', d.sub || '', d.color ? { color: d.color } : {});
    f.g.restore();
  },
};
