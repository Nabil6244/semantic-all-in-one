# Phase 8: globe zoom-out defect, fixed

**Symptom.** Zooming out into the globe range (below about zoom 3) showed rippled, smeared bands along the globe's left and right edges. A still at the same camera, or zooming in, was clean. Open since Phase 1; the sample stopped its pull-back at zoom 3.4 to avoid it.

**Root cause.** Not MapLibre. In `pakmap-engine/page.js` each frame is composited onto a 2D canvas (`out`) that was never cleared between frames. The globe leaves the sky around it transparent, so wherever the new, smaller globe did not cover the pixels, the previous frames' larger globes showed through. On a zoom-out that stacks into the rippled bands. On a zoom-in each new globe covers the old one, and a single still has no earlier frame, which is why only zoom-out showed it. (Found by rendering two frames: the second showed the previous globe as a ghost behind it. The map's transform, projection state, clipping plane and tile set were identical to a clean cold render; only the output canvas differed.)

**Fix.** One step in `renderFrame`: fill the canvas with the space colour (`#03070d`) before drawing the map. No other behaviour changes; flat-map frames are fully covered by the map so they are unchanged.

**Evidence.**
- `globe-zoom-out-BEFORE.jpg` / `globe-zoom-out-AFTER.jpg`: frames 0, 12, 22, 30, 39 of `samples/globe-outro-repro.json` (real NASA imagery).
- Regression test `render.integration.test.mjs` "zooming out into the globe leaves clean space around it": fails with the clear removed, passes with it.
- pakmap-engine suite 107/107; the pakMap Python tests for the compiler, schema, audio, generate and app integration pass.

**Also changed.** The compiler no longer warns when a pull-back ends in the globe range (and its test now asserts there is no warning); the README, Phase 1 report, build plan and sample notes are updated.
