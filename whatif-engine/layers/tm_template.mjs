// TM_TEMPLATE: any visual of the template library (whatif-engine/templates/**.json) -- one layer type for hundreds of visuals. The planner
// puts the template itself in the layer (so a render needs no file lookups), the slot values the CSV row gave, and the narration cues:
//   { "type": "tm_template", "template": { ...the JSON... }, "slots": { "left": "EARTH", "ratio": 100 }, "cues": { "hours": 2.4 },
//     "start": 41.2, "end": 49.8 }
// The template's items are built once (lib/tpl.mjs) and drawn every frame by the primitives (lib/prims.mjs). A plate template lives in the
// same slow push as every diagram (1.00 -> 1.04), so it is never a still.
import { tm, drift } from './tm_theme.mjs';
import { build } from '../lib/tpl.mjs';
import { drawItem } from '../lib/prims.mjs';

export default {
  type: 'tm_template',
  space: 'screen',
  async create(def, ctx = {}) {
    const tpl = def.template;
    if (!tpl || typeof tpl !== 'object') throw new Error('tm_template: "template" (the template JSON) is required');
    const len = def.end != null && def.start != null ? def.end - def.start : (tpl.hold ?? 6);
    let items;
    try { items = build(tpl, def.slots || {}, { len, cues: def.cues || {} }); }
    catch (e) {
      // a slot value the template cannot use (a word where a number belongs): the template's own defaults are kept for that slot
      const ok = {};
      for (const [k, v] of Object.entries(def.slots || {})) { try { build(tpl, { [k]: v }, { len, cues: def.cues || {} }); ok[k] = v; } catch { /* default kept */ } }
      items = build(tpl, ok, { len, cues: def.cues || {} });
      if (ctx.warn) ctx.warn(`tm_template ${tpl.id}: ${e.message}; the template's defaults were used for the bad values`);
    }
    items.sort((a, b) => (a.z ?? 0) - (b.z ?? 0) || a._n - b._n);
    const images = new Map();
    for (const it of items) {
      if (it.p !== 'image' || !it.name || images.has(it.name) || !ctx.loadImage) continue;
      try { images.set(it.name, await ctx.loadImage(it.name)); } catch (e) { images.set(it.name, null); if (typeof console !== 'undefined') console.warn(`tm_template ${tpl.id}: ${e.message}`); }
    }
    return { def, tpl, items, images };
  },
  draw(inst, f) {
    const { g, W, H } = f, T = tm(g, W), d = inst.def, tr = f.t - (d.start ?? 0);
    g.save();
    if (inst.tpl.plate !== false && inst.tpl.drift !== false) drift(g, f, d, 0.035);
    const c = { g, T, W, H, alpha: f.alpha, image: (n) => inst.images.get(n) || null, reserved: f.reserved || [] };
    for (const it of inst.items) {
      if (it._broken) continue;
      try { g.save(); drawItem(c, it, tr); } catch (e) { it._broken = true; if (typeof console !== 'undefined') console.warn(`tm_template ${inst.tpl.id}: item ${it.p} off: ${e.message}`); } finally { g.restore(); }
    }
    g.restore();
  },
};
