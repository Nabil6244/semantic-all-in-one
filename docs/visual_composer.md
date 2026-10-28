# Visual composer (2026-10-29)

Goal: a relevant visual for every narration line, in any niche (finance, history, cooking, health ... not only space). A reference video teaches
pace, density and layout; its content is never copied.

- `visual_composer/concepts.py` reads a sentence (quote, change, comparison, percent, timeline, sequence, list, figure, definition, keyword) from its words alone.
- `visual_composer/compose.py` builds a graphic for that sentence from the engine's primitives (card over footage, or full frame on a plate); `author()` lets an AI
  model write one (`run(system, user) -> text`) and keeps it only if `problems()` finds nothing wrong.
- `visual_composer/relevance.py` + `apply.gate_3d`: a craft/globe shot whose narration is not about it becomes a picture of what is said.
- What If: hooked in `whatif/planner.py` after `variety.apply` (auto plans; CSV-authored 3D shots are never gated).
- StarMap Cinema: `visual_composer/cinema.py:enrich_spec(spec, plan, notes)`, to be called once in `starmap/cinema.py:apply` after `variety(...)`
  (protected file: needs the owner's OK and a manifest refresh). Until then Cinema gets the relevance fixes only through `whatif.planner._world/_craft`.
- Tests: `test_visual_composer.py`, `test_whatif_3d_relevance.py`.

## 3D scene composer, slice one (2026-10-29)
- Engine: `whatif-engine/lib/scene_gen.mjs`, new shot kind `scene` (`scene_spec` JSON; `repairScene` repairs bad values, never fatal). One shader draws any world from
  parameters (gas bands + storms, rock + craters, ice + cracks, ocean + land + clouds + city lights, lava, sun, haze), rings, atmosphere glow; craft built from parts
  (probe, capsule, lander, satellite, rocket, telescope, rover, free parts) with a parachute option; cloud layers a falling craft passes through; rain/snow/embers/
  dust/streak particles; camera paths orbit/push/pullback/descend/flyby/drift. No model or texture files.
- Python: `visual_composer/scene.py` `scene_for(sentence) -> (spec, confidence)` from the sentence's properties (type words, colour words, craft words, air, fall,
  camera words; a hash of the sentence seeds the details). Named real worlds only give default colours.
- Planner: `apply.upgrade_scenes` turns picture/clip shots about something drawable into scenes (not next to another 3D shot, not over a "photo" claim, <= 45 % of
  shots); `gate_3d` makes a scene instead of a stand-in picture when it can. `compile.py` writes `scene_spec`.
- Tests: `whatif-engine/test/scene_gen.test.mjs`, `SceneComposer` in `test_visual_composer.py`. Stills checked in the real renderer (worlds, parachute descent, hot sky).
- Not yet: cutaways/layered interiors, magnetic field lines, scene transitions inside one shot, an AI author for scene specs, Cinema (StarMap) support for `scene`.

## Slice two (2026-10-29)
- **Cutaway interiors:** `world.cutaway.layers [{r, color}]` removes an octant and draws the layers on the three cut faces (crust/mantle/core, cloud deck/liquid/metallic hydrogen/core, ice shell/ocean/rock/core ...).
- **Magnetic field lines:** `world.field {lines, color, tilt, reach}`: dipole lines as tubes with a travelling pulse.
- **Rules:** `scene_for` reads "inside / core / layers / beneath the surface" (cutaway) and "magnetic field / magnetosphere / aurora" (field lines); a fall inside the air stays a descent, not a cutaway; a star named as a reference ("far from any star") is not the subject.
- **AI author:** `scene.author(text, run)` + `scene.problems()` validation; `apply.upgrade_scenes(author=...)` asks it only for picture shots the rules cannot read (<= 14 per video, router-cached).
  It is OFF unless `settings.json` has `"scene_ai_author": true` and a provider key is configured (`visual_composer/ai.py`). The engine's `repairScene` is the last safety net.
- Not yet: labels on cutaway layers, scene support in StarMap Cinema, a full-video render check.

- **Cutaway labels:** each layer may carry `label` (upper-cased, <= 22 chars); `scene.py` LAYERS presets give per-world-type names (CRUST / MANTLE / OUTER CORE, CLOUD DECK / LIQUID HYDROGEN / METALLIC HYDROGEN / CORE, ICE SHELL / OCEAN ...). The engine draws them as camera-facing sprites in a column at the right of the frame with a thin leader and a dot on the layer's band of the cut face, stacked in the order of their anchors (no crossing leaders), fading in one by one over the shot and out at its end. Positions are recomputed per frame from the camera, so they stay on screen while it orbits.
