// BODY labels: a white chip under every body big enough to matter at the current scale. Bodies merged into one dot (a
// planet and its moons; the whole solar system from light-years away) are named by the one highest in the tree (then the
// biggest); nearest first; no overlaps.
//   { "type": "body_labels", "only": ["earth", "moon"], "exclude": ["sun"] }
const depthOf = (world, id) => { let d = 0; for (let n = world.get(id); n && n.parent; n = world.get(n.parent)) d++; return d; };

export default {
  type: 'body_labels',
  space: 'world',
  create: (def) => ({ only: def.only ? new Set(def.only) : null, exclude: new Set(def.exclude || []) }),
  draw(inst, f) {
    const { W, H, u } = f;
    let labels = [];
    for (const b of f.bodies) {
      if (!b.n.label || (inst.only && !inst.only.has(b.id)) || inst.exclude.has(b.id) || (b.away ?? 1) < 0.5) continue;
      const atScale = b.dist < 60 * f.cam.distance || b.id === f.cam.anchor;
      if (b.front && Math.abs(b.ndc[0]) < 1.05 && Math.abs(b.ndc[1]) < 1.05 && b.px < 0.32 * H && (f.inside > 0.3 || b.n.kind === 'galaxy') && atScale)
        labels.push({ id: b.id, x: b.sx, y: b.sy, r: b.px, text: b.n.label, dist: b.dist, size: b.n.radiusKm, depth: depthOf(f.world, b.id) });
    }
    labels.sort((a, b) => a.depth - b.depth || b.size - a.size);   // a merged dot is named by the body highest in the tree (the Sun, a planet), then the biggest
    labels = labels.filter((L, i) => !labels.slice(0, i).some((K) => Math.hypot(K.x - L.x, K.y - L.y) < 30));
    labels.sort((a, b) => a.dist - b.dist);
    const taken = [];
    f.g.save(); f.g.globalAlpha = f.alpha;
    for (const L of labels) {
      const y0 = L.y + Math.max(L.r, 6) + 16 * u.S, w = u.measure(L.text, 24) + 28 * u.S, x = L.x - w / 2, h = 46 * u.S;
      if (taken.some((o) => x < o.x + o.w && x + w > o.x && y0 < o.y + h && y0 + h > o.y)) continue;
      const y = f.place(x, y0, w, h);                                    // make room for chips other layers put here
      taken.push({ x, y, w }); u.chip(x, y, L.text, 24, { bg: 'rgba(255,255,255,0.92)', shadowBlur: 0 });
    }
    f.g.restore();
    void W;
  },
};
