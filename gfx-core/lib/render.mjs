// GFX-CORE RENDER: one template -> frames. createGfx builds the items once (slots, cues, times); drawGfx paints one frame at time t
// (seconds from the layer start) on any 2D canvas context: the browser page of any niche engine, or a mock canvas in node tests.
import { build } from './tpl.mjs';
import { drawItem } from './prims.mjs';
import { drawPlate, makeT, theme, restoreTheme, THEMES, clamp01 } from './theme.mjs';

export function createGfx(template, slots = {}, { len = null, cues = {}, warn = null } = {}) {
  const L = len ?? template.hold ?? 6;
  let items;
  try { items = build(template, slots, { len: L, cues }); }
  catch (e) {
    // a slot value the template cannot use: that slot keeps its default, the rest still apply
    const ok = {};
    for (const [k, v] of Object.entries(slots || {})) { try { build(template, { [k]: v }, { len: L, cues }); ok[k] = v; } catch { /* default kept */ } }
    items = build(template, ok, { len: L, cues });
    if (warn) warn(`gfx ${template.id}: ${e.message}; defaults were used for the bad values`);
  }
  items.sort((a, b) => (a.z ?? 0) - (b.z ?? 0) || a._n - b._n);
  return { template, items, len: L };
}

/** A soft elliptical dark backing: shade = { at: [x, y], rx, ry, a } in fractions of the frame; solid at the middle, clear at the rim, easing in over half a second. */
function drawShade(g, W, H, sh, t) {
  const [x, y] = sh.at || [0.5, 0.5], rx = (sh.rx ?? 0.34) * W, ry = (sh.ry ?? 0.26) * H, a = (sh.a ?? 0.5) * clamp01(t / 0.5);
  g.save(); g.translate(x * W, y * H); g.scale(1, ry / rx);
  const gr = g.createRadialGradient(0, 0, 0, 0, 0, rx);
  gr.addColorStop(0, `rgba(6,8,10,${a.toFixed(3)})`); gr.addColorStop(0.55, `rgba(6,8,10,${(a * 0.85).toFixed(3)})`); gr.addColorStop(1, 'rgba(6,8,10,0)');
  g.fillStyle = gr; g.fillRect(-rx, -rx, rx * 2, rx * 2); g.restore();
}

/** Draw the frame at t. `alpha` fades the whole layer; a template with "plate": false draws over whatever is on the canvas (a map). */
export function drawGfx(inst, g, W, H, t, { alpha = 1, follow = null, image = null, project = null } = {}) {
  const prev = theme(), want = inst.template.theme && THEMES[inst.template.theme];
  if (want && want !== prev) restoreTheme(want);
  const T = makeT(g, W, H);
  g.save(); g.globalAlpha *= alpha;
  if (inst.template.plate) drawPlate(g, W, H);
  else if (inst.template.dim) { g.fillStyle = `rgba(6,8,10,${(inst.template.dim * clamp01(t / 0.5)).toFixed(3)})`; g.fillRect(0, 0, W, H); }   // footage underneath is dimmed so the type reads
  if (inst.template.shade) drawShade(g, W, H, inst.template.shade, t);   // a soft dark backing under the type, local to it (graphics drawn over footage)
  const c = { g, T, W, H, alpha: 1, follow, project, image: image || ((n) => (inst.images && inst.images.get(n)) || null) };
  try {
    for (const it of inst.items) {
      if (it._broken) continue;
      try { g.save(); drawItem(c, it, t); } catch (e) { it._broken = true; if (typeof console !== 'undefined') console.warn(`gfx ${inst.template.id}: item ${it.p} off: ${e.message}`); } finally { g.restore(); }
    }
  } finally { g.restore(); if (want && want !== prev) restoreTheme(prev); }
}
