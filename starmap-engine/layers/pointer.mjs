// POINTER: a pin on a thing in space with a label beside it ("YOU ARE HERE" on the Sun seen from outside the galaxy).
//   { "type": "pointer", "at": "sun", "label": "YOU ARE HERE", "sub": "ORION ARM" }
// "at" is a body, a surface point or a layer with a position. Drawn only while the point is in view.
/** Where a pin shows on screen (null when its point is off screen, behind the camera or hidden). */
export function pinSpot(f, p) {
  if (!p) return null;
  const s = f.project(p);
  return !s.front || s.x < 0 || s.x > f.W || s.y < 0 || s.y > f.H || f.hidden(p) ? null : s;
}

/** Take a pin's box before any label is placed, so a label drawn earlier is never covered by a pin drawn later. */
export function claimPin(f, p) {
  const s = pinSpot(f, p);
  if (s) f.claim(s.x - 14 * f.u.S, s.y - 14 * f.u.S, 28 * f.u.S, 28 * f.u.S);
}

export function drawPointer(f, p, label, sub, { color = '#FBE040' } = {}) {
  if (!p) return;
  const s = pinSpot(f, p), { u, g, W } = f;
  if (!s) return;
  // the same words drawn twice in one frame (the galaxy guide's "YOU ARE HERE" and a CSV pointer to the Sun) are drawn once
  const shown = (f.claims.labels ||= new Set()), key = String(label || '').trim().toUpperCase();
  if (key) { if (shown.has(key)) return; shown.add(key); }
  g.save(); g.globalAlpha *= 1;
  u.pin(s.x, s.y, color);
  f.claim(s.x - 14 * u.S, s.y - 14 * u.S, 28 * u.S, 28 * u.S);
  if (label) {
    const w = u.measure(label, 22) + 26 * u.S, h = 40 * u.S, w2 = sub ? u.measure(sub, 16) + 20 * u.S : 0, h2 = sub ? 30 * u.S : 0;
    const bw = Math.max(w, w2), right = s.x + 24 * u.S, left = s.x - 24 * u.S - bw;
    const at = f.placeAny(s.x > W * 0.7 ? [left, right] : [right, left], s.y - h / 2, bw, h + h2);
    const onLeft = at.x < s.x;
    if (Math.abs(at.y + h / 2 - s.y) > h * 0.75) {                    // moved aside to make room: a thin line keeps the label tied to its pin
      g.save(); g.strokeStyle = color; g.globalAlpha *= 0.8; g.lineWidth = 2 * u.S; g.beginPath();
      g.moveTo(s.x, s.y); g.lineTo(onLeft ? at.x + bw : at.x, Math.min(at.y + h, Math.max(at.y, s.y))); g.stroke(); g.restore();
    }
    u.chip(onLeft ? at.x + bw - w : at.x, at.y, label, 22, { h: 40, bg: color });
    if (sub) u.chip(onLeft ? at.x + bw - w2 : at.x, at.y + h + 4 * u.S, sub, 16, { bg: '#111111', fg: '#ffffff', padX: 10, h: 28 });
  }
  g.restore();
}

export default {
  type: 'pointer',
  space: 'world',
  create(def) { if (!def.at) throw new Error('pointer: "at" is required'); return { def }; },
  pins(inst, f) { claimPin(f, f.locate(inst.def.at)); },
  draw(inst, f) {
    const d = inst.def;
    f.g.save(); f.g.globalAlpha = f.alpha;
    drawPointer(f, f.locate(d.at), d.label || '', d.sub || '', d.color ? { color: d.color } : {});
    f.g.restore();
  },
};
