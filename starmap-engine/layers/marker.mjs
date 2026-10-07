// MARKER: a point on any body's surface (a landing site, a crater, a launch pad). Hidden on the far side of the body and
// behind other bodies; it fades in once the body is big enough on screen for the point to mean something.
//   { "type": "marker", "body": "moon", "lon": 23.47, "lat": 0.67, "label": "TRANQUILITY BASE",
//     "description": "20 JULY 1969", "style": { "color": "#ffffff", "icon": "pin" | "dot" | "ring" }, "side": "r" | "l",
//     "min_body_px": 40 }
export default {
  type: 'marker',
  space: 'world',
  create(def, ctx) {
    if (!ctx.world.get(def.body)) throw new Error(`marker: unknown body ${def.body}`);
    if (!Number.isFinite(def.lon) || !Number.isFinite(def.lat)) throw new Error('marker: lon and lat are required');
    return { def };
  },
  locate(inst, f) { const d = inst.def; return f.toCam(d.body, f.world.surfaceOffset(d.body, d.lon, d.lat, d.alt_km || 0)); },
  draw(inst, f) {
    const d = inst.def, p = this.locate(inst, f);
    const body = f.bodies.find((b) => b.id === d.body);
    const grow = Math.min(1, Math.max(0, ((body ? body.px : 0) - (d.min_body_px ?? 40)) / 40));
    const s = f.project(p);
    if (!s.front || f.hidden(p) || grow <= 0) return;
    // fade towards the limb: a point seen edge-on reads poorly
    const nrm = f.world.surfaceNormal(d.body, d.lon, d.lat), l = Math.hypot(...p);
    const facing = -(nrm[0] * p[0] + nrm[1] * p[1] + nrm[2] * p[2]) / l;
    const a = f.alpha * grow * Math.min(1, Math.max(0, facing / 0.15));
    if (a <= 0.01) return;
    const { u, g } = f, st = d.style || {}, color = st.color || '#ffffff';
    g.save(); g.globalAlpha = a;
    if (st.icon === 'dot') { u.shadow(6, 0.6); g.fillStyle = color; g.beginPath(); g.arc(s.x, s.y, 8 * u.S, 0, Math.PI * 2); g.fill(); u.noShadow(); }
    else if (st.icon === 'ring') { u.shadow(6, 0.6); g.strokeStyle = color; g.lineWidth = 4 * u.S; g.beginPath(); g.arc(s.x, s.y, 16 * u.S, 0, Math.PI * 2); g.stroke(); u.noShadow(); }
    else u.pin(s.x, s.y, color);
    f.claim(s.x - 14 * u.S, s.y - 14 * u.S, 28 * u.S, 28 * u.S);
    if (d.label) {
      // the label and its description move as one block when they have to make room
      const w = u.measure(d.label, 30) + 30 * u.S, h = 52 * u.S;
      const w2 = d.description ? u.measure(d.description, 20) + 24 * u.S : 0, h2 = d.description ? 40 * u.S : 0;
      const bw = Math.max(w, w2), right = s.x + 27 * u.S, leftX = s.x - 27 * u.S - bw;
      const at = f.placeAny(d.side === 'l' ? [leftX, right] : [right, leftX], s.y - h / 2, bw, h + h2);
      const onLeft = at.x < s.x, lx = onLeft ? at.x + bw - w : at.x;
      u.chip(lx, at.y, d.label, 30, { h: 52 });
      if (d.description) u.chip(onLeft ? at.x + bw - w2 : at.x, at.y + h + 6 * u.S, d.description, 20, { bg: '#111111', fg: '#ffffff', padX: 12, h: 34 });
    }
    g.restore();
  },
};
