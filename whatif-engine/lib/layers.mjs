// The layer registry: everything drawn on top of the bare universe is a LAYER, named by a generic type and configured by
// data. The renderer knows no mission, spacecraft or place -- only layer types. A new kind of graphic is one new module
// that calls register(); nothing else in the renderer changes.
//
// A layer type:
//   { type: "marker",                       the name used in spec.layers[].type
//     space: "world" | "screen",            attached to something in space (projected every frame) or to the screen
//     create(def, ctx) -> instance,         once, before the first frame (may be async: textures, images)
//     update(inst, frame)?,                 every frame BEFORE the 3D render (move 3D objects; frame.alpha 0 = hide them)
//     draw(inst, frame)? }                  every frame AFTER the 3D render, on the 2D overlay (only while visible)
//
// Every layer in spec.layers gets narration-time visibility for free (start / end / fade_in / fade_out, see timing.mjs):
// frame.alpha is that visibility times the layer's own "opacity". World layers draw before screen layers; within each,
// spec order (or "z") decides.
import { opacityAt } from './timing.mjs';

const SPACES = new Set(['world', 'screen']);

export function createRegistry() {
  const types = new Map();
  return {
    register(impl) {
      if (!impl || typeof impl.type !== 'string' || !impl.type) throw new Error('a layer type needs a "type" name');
      if (!SPACES.has(impl.space)) throw new Error(`layer ${impl.type}: space must be "world" or "screen"`);
      if (typeof impl.create !== 'function') throw new Error(`layer ${impl.type}: create(def, ctx) is required`);
      if (!impl.update && !impl.draw) throw new Error(`layer ${impl.type}: needs update() and/or draw()`);
      if (types.has(impl.type)) throw new Error(`layer type ${impl.type} is registered twice`);
      types.set(impl.type, impl);
      return this;
    },
    has: (type) => types.has(type),
    get: (type) => types.get(type),
    types: () => [...types.keys()].sort(),
    /** spec.layers -> live layers (in draw order). Unknown types fail loudly, naming the layer. */
    async instantiate(defs, ctx) {
      const out = [];
      const byId = new Map();
      ctx.layer = (id) => { const L = byId.get(id); if (!L) throw new Error(`no layer with id ${id}`); return L.inst; };
      for (const [i, def] of (defs || []).entries()) {
        const impl = types.get(def.type);
        if (!impl) throw new Error(`layer ${def.id || i}: unknown type "${def.type}" (known: ${[...types.keys()].sort().join(', ')})`);
        if (def.id && byId.has(def.id)) throw new Error(`layer id ${def.id} is used twice`);
        const L = { def, impl, order: i, inst: null };
        L.inst = await impl.create(def, ctx);
        if (def.id) byId.set(def.id, L);
        out.push(L);
      }
      const rank = (L) => (L.impl.space === 'world' ? 0 : 1e6) + (L.def.z ?? 0) * 1e3 + L.order;
      return out.sort((a, b) => rank(a) - rank(b));
    },
  };
}

/** Run one phase ("update" before the 3D render, "draw" after it) of every layer for this frame. */
export function runLayers(layers, frame, phase, only = null) {
  for (const L of layers) {
    if (!L.impl[phase] || (only && !only(L))) continue;
    const alpha = opacityAt(L.def, frame.t) * (L.def.opacity ?? 1);
    if (phase === 'draw' && alpha <= 0.002) continue;
    L.impl[phase](L.inst, { ...frame, alpha, def: L.def });
  }
}

/** A spec written before layers existed (Phase 1) still shows what it showed: body labels, distance, clock, title. */
export function defaultLayers(spec) {
  let out = spec.layers;
  if (!Array.isArray(out)) {
    out = [{ type: 'body_labels' }, { type: 'distance' }, { type: 'mission_clock' }];
    if (spec.title) out.push({ type: 'title', text: spec.title });
  }
  // the app's channel-name setting (the same {"text": ...} PakMap takes) becomes a watermark layer
  const wm = spec.watermark;
  if (wm && wm.text && wm.enabled !== false && !out.some((l) => l.type === 'channel_name'))
    out = out.concat([{ type: 'channel_name', text: wm.text, corner: wm.position || 'br', ...(wm.opacity != null ? { opacity_text: wm.opacity } : {}) }]);
  return out;
}

/** Does a layer stay on screen over footage? (its own "over_footage", else its type's default) */
export const overFootage = (L) => L.def.over_footage ?? L.impl.over_footage ?? false;
