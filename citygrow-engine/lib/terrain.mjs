// The low-poly ground, shared by Node (placing houses, trees, camera) and the page (drawing it), so everything sits on
// exactly the surface that is drawn. Units: metres; x east, z south, origin = the city centre; y up.
//
// The world's fine height grid (height.f32, row 0 = north) is smoothed and sampled every `step` cells into a coarse
// vertex grid. Each quad is split along the same diagonal the mesh uses, and heightAt() interpolates on that triangle.

export const EXAG = 1.25;          // vertical exaggeration: low hills read better from the air

export function makeTerrain(height, w, h, cell, { step = 2, exag = EXAG, water = null, level = null } = {}) {
  const M = Math.floor((w - 1) / step);          // quads per side
  const n = M + 1;                               // vertices per side
  const sp = cell * step;                        // metres between vertices
  const x0 = 0.5 * cell - (w * cell) / 2;       // vertex i sits on fine cell i*step's centre
  const half = -x0;
  const hs = new Float32Array(n * n);
  const ls = new Float32Array(n * n).fill(-1e4);   // inland water surface per vertex (-1e4 = none)
  const isWater = (idx) => (water ? water[idx] === 1 : height[idx] < 0);
  const r = step + 1;                            // box smoothing radius in fine cells (city DSM bumps are buildings)
  for (let j = 0; j < n; j++) {
    for (let i = 0; i < n; i++) {
      const cx = Math.min(w - 1, i * step), cy = Math.min(h - 1, j * step);
      let s = 0, k = 0, minV = Infinity, maxV = -Infinity;
      for (let dy = -r; dy <= r; dy++) {
        const y = cy + dy; if (y < 0 || y >= h) continue;
        for (let dx = -r; dx <= r; dx++) {
          const x = cx + dx; if (x < 0 || x >= w) continue;
          const v = height[y * w + x]; s += v; k++; if (v < minV) minV = v; if (v > maxV) maxV = v;
        }
      }
      let v = s / k;
      // keep the coast where the data has it: a vertex next to water and land stays on its own side of sea level
      const idx = cy * w + cx, own = height[idx];
      if (isWater(idx)) {
        v = Math.min(v, own < 0 ? -0.6 : own);                      // the bed stays under its water
        if (level && level[idx] > 0) ls[j * n + i] = level[idx] * exag;
      } else if (v < 0.4) v = 0.4;
      hs[j * n + i] = v > 0 ? v * exag : v;
    }
  }
  const at = (i, j) => hs[Math.max(0, Math.min(n - 1, j)) * n + Math.max(0, Math.min(n - 1, i))];
  /** Height of the drawn surface at (x, z). */
  function heightAt(x, z) {
    const fx = (x - x0) / sp, fz = (z - x0) / sp;
    const i = Math.max(0, Math.min(M - 1, Math.floor(fx))), j = Math.max(0, Math.min(M - 1, Math.floor(fz)));
    const u = Math.max(0, Math.min(1, fx - i)), v = Math.max(0, Math.min(1, fz - j));
    const a = at(i, j), b = at(i + 1, j), c = at(i, j + 1), d = at(i + 1, j + 1);
    // diagonal a–d: triangles (a, b, d) when u >= v, (a, d, c) otherwise
    return u >= v ? a + (b - a) * u + (d - b) * v : a + (d - c) * u + (c - a) * v;
  }
  /** Largest rise over a square of side `size` around (x, z): used to keep houses off cliffs. */
  function slopeAt(x, z, size) {
    const s = size / 2;
    const v = [heightAt(x - s, z - s), heightAt(x + s, z - s), heightAt(x - s, z + s), heightAt(x + s, z + s)];
    return (Math.max(...v) - Math.min(...v)) / size;
  }
  /** Is (x, z) water (sea, river or lake)? Read from the fine grid. */
  function waterAt(x, z) {
    const c = Math.round((x - x0) / cell), r = Math.round((z - x0) / cell);
    if (c < 0 || r < 0 || c >= w || r >= h) return false;
    return isWater(r * w + c);
  }
  return { n, M, sp, x0, half: Math.min(half, x0 + M * sp), hs, ls, heightAt, slopeAt, waterAt, size: M * sp };
}
