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

/** Draw the frame at t. `alpha` fades the whole layer; a template with "plate": false draws over whatever is on the canvas (a map). */
export function drawGfx(inst, g, W, H, t, { alpha = 1, follow = null, image = null, project = null } = {}) {
  const prev = theme(), want = inst.template.theme && THEMES[inst.template.theme];
  if (want && want !== prev) restoreTheme(want);
  const T = makeT(g, W, H);
  g.save(); g.globalAlpha *= alpha;
  if (inst.template.plate) drawPlate(g, W, H);
  else if (inst.template.dim) { g.fillStyle = `rgba(6,8,10,${(inst.template.dim * clamp01(t / 0.5)).toFixed(3)})`; g.fillRect(0, 0, W, H); }   // footage underneath is dimmed so the type reads
  const c = { g, T, W, H, alpha: 1, follow, project, image: image || ((n) => (inst.images && inst.images.get(n)) || null) };
  try {
    for (const it of inst.items) {
      if (it._broken) continue;
      try { g.save(); drawItem(c, it, t); } catch (e) { it._broken = true; if (typeof console !== 'undefined') console.warn(`gfx ${inst.template.id}: item ${it.p} off: ${e.message}`); } finally { g.restore(); }
    }
  } finally { g.restore(); if (want && want !== prev) restoreTheme(prev); }
}
