// Map-scale effects (CSV extra.effects on a beat): the reference's fire puffs and smoke over bombed cities and small
// aircraft crossing the map, drawn at the scale of the map view rather than a ground scene.
//   { kind: 'blasts' | 'smoke' | 'fires' | 'planes', at: [lon, lat], to?: [lon, lat] (planes), count? }
// Pure: -> boxes { x, y, z, sx, sy, sz, rot, c, a } in world units for the page's particle mesh.

const hash = (a, b) => { let h = (a * 374761393 + b * 668265263) >>> 0; h = ((h ^ (h >>> 13)) * 1274126177) >>> 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };

/** Effects live at t, as boxes. `D` is the camera's distance (cells): sizes follow it so the effect reads at any zoom. */
export function mapEffectsAt(effects, t, geo, groundY, D) {
  const out = [], u = Math.max(0.05, D * 0.012);
  effects.forEach((e, ei) => {
    if (t < e.t0 || t > e.t1 || !e.at) return;
    const life = Math.min(1, (t - e.t0) / 1.2, (e.t1 - t) / 1.2); // the whole effect fades in and out
    if (life <= 0) return;
    const p = geo.toWorld(e.at[0], e.at[1]), gy = groundY(p.x, p.z), n = e.count ?? 4;
    if (e.kind === 'planes') {
      const q = e.to ? geo.toWorld(e.to[0], e.to[1]) : { x: p.x + 4, z: p.z };
      const dx = q.x - p.x, dz = q.z - p.z, rot = Math.atan2(-dz, dx);
      for (let i = 0; i < n; i++) {
        const k = ((t - e.t0) / Math.max(1, e.t1 - e.t0) + i * 0.07) % 1, off = (i - (n - 1) / 2) * u * 3;
        const x = p.x + dx * k - Math.sin(rot) * off, z = p.z + dz * k - Math.cos(rot) * off, y = gy + u * 14;
        out.push({ x, y, z, sx: u * 2.2, sy: u * 0.35, sz: u * 0.5, rot, c: [226, 228, 232], a: life });
        out.push({ x, y, z, sx: u * 0.6, sy: u * 0.3, sz: u * 2.4, rot, c: [210, 212, 218], a: life });
      }
      return;
    }
    for (let i = 0; i < n; i++) {
      const ox = (hash(ei, i) - 0.5) * u * 18, oz = (hash(i, ei + 7) - 0.5) * u * 18, x = p.x + ox, z = p.z + oz, g = groundY(x, z);
      if (e.kind === 'smoke' || e.kind === 'blasts') for (let j = 0; j < 7; j++) {
        const age = ((t * 0.5 + j / 7 + hash(ei, i * 3)) % 1);
        out.push({ x: x + age * u * 2, y: g + age * u * 16, z, s: u * (1.2 + age * 3), c: [128 - age * 40, 124 - age * 40, 118 - age * 38], a: life * (1 - age) * Math.min(1, age / 0.08) });
      }
      if (e.kind === 'blasts' || e.kind === 'fires') {
        const per = 2.2 + hash(i, ei) * 2, age = (t + hash(ei + 3, i) * per) % per, k = age / 0.9;
        if (e.kind === 'fires' || k < 1) for (let j = 0; j < 5; j++) {
          const f = e.kind === 'fires' ? 0.5 + 0.5 * Math.sin(t * 8 + j + i) : k, a = j * 1.26;
          out.push({ x: x + Math.cos(a) * f * u * 2, y: g + f * u * 2.5, z: z + Math.sin(a) * f * u * 2, s: u * (1 + f), c: [255, 190 - f * 110, 50], a: life * (e.kind === 'fires' ? 1 : (1 - k) * Math.min(1, age / 0.08)) });
        }
      }
    }
  });
  return out;
}
