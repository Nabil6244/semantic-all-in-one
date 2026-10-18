# What If: reference-matched visual system — audit and plan (2026-10-17)

Spec: the four references (V1-V4) and render #016, analysed in `reference_graphics_analysis.md` / `analysis/ref_vs_016.jpg`.

## Audit

Pipeline: `whatif/app_section.generate` → `app_integration.generate_whatif_video` → `plan_from` (CSV: `heal.read_healed` →
`shot_csv.read_shots` + `layers_from_rows`; else narration only) → `planner.plan` (shots, diagrams, templates, callouts, captions,
instruments, `engage`, `direct`, plate repairs, Flow limits) → `media.fetch` (NASA → Commons → AI stand-ins) → `compile.compile_spec`
→ `engine_runner.render_spec` (parallel parts) → `whatif-engine/render.mjs` + `page.js` (one canvas per frame, layers in
`whatif-engine/layers/`) → audio mix → export.

Timing: Whisper word timestamps (`state/narration_words.json`), matched to the Script box text by `narration.words_of`; CSV rows anchor on
words through `anchor_clock.AnchorClock`. Every visual event is placed in seconds on that word timeline.

Where things are:
- `drawPlate` (page.js): the plate background and its top-centre heading.
- `screen_name` (planner): a CSV label cut to a name (added this session).
- Number callouts: `planner.plan` "every other spoken measurement" → `tm_metric` (layers/tm_metric.mjs), 4 rotating anchors.
- Diagram rows: `narration.layers_from_row` (diagram / metric / hud) and `templates.layer_for`.
- Shot length: `cut_points` (TARGET_S 6.4 / MAX_S 11) for narration plans; a CSV plan keeps its rows as shots.
- Star field: `scene3d.stars` (3D shots), `skyTile` (plates, added this session).
- Spacecraft: `craft` shots (3D model) with a name caption; no "YOU" marker exists.

Fixes from this session, verified present and tested (102 tests): CSV repairs (label from text, `|` lists, steps), empty-plate safety net,
screen names, HUD boxes reserved, Commons = Wikimedia only, NASA checks (generic words, event photos), stock set aside on NASA rows,
90 s repeat rule, light-clock window, mission card defaults, parallel render, frame watchdog.

New findings:
1. `planner._bare_plate` treats a plate with a heading as not bare, so the old `fill_empty_plates` never touched CSV diagram plates.
2. `narration.sentences` needs punctuation: #016's transcript has none, so 18 minutes were 3 "sentences". Every rule that reads a
   sentence (diagrams, templates, titles) saw minutes of text.
3. The type sizes already match the reference (caption large 66 px = 6.1 % of 1080; number large 112 px = 10 %). The gap is use:
   #016 had 10 numbers in 18 min and headline-level type on screen 41 % of the time; captions were CSV shot directions.
4. Shots: CSV rows become shots one to one (median 6.0 s; V3 9.8 s), each a new composition.

## Plan

Phase A — narration typography and composition
- A1 `sentences()` falls back to pauses when the transcript has no sentence punctuation.
- A2 `tm_metric` gains a kicker; number callouts on craft / globe / sky shots use the left-third block (kicker · number · sub).
- A3 New pass `whatif/typeset.py`: a kicker / headline / sub block from the words of each beat (a spoken number, else a key name or
  term), every 5-7 s where nothing else is said on screen; never across a cut, never the same headline within 90 s, values only from
  the words.
- A4 Plate headings: drawn only on a plate with no type block (the kicker introduces a diagram); `_bare_plate` counts a titled plate.

Phase B — diagrams in the world: plates over the sky (done), no headings, templates checked at ≥ 2 % label height and 50-70 % size.
Phase C — the journey's craft gets a ring + "YOU · ON BOARD" marker (engine layer, projected from the 3D model); date stamp top right
when a date is said; mission card only from verified rows (done).
Phase D — compatible consecutive beats merged into one evolving shot; real photos as a right-hand card when a type block is on.

After each phase: focused tests, a short render of #016 at matching moments, frames inspected against V3.

Risks: the planner is shared by narration-only and CSV plans (both covered by tests); `sentences()` feeds every rule that reads a sentence
(punctuated scripts are unchanged by the fallback); engine changes affect every What If render (stills checked). Nothing outside
whatif/ and whatif-engine/ is touched in these phases.
