# War documentary style: inspection report (design phase, nothing implemented)

Date 2026-10-27. Scope: what exists, what Phase 1 proved, what it did not, and what the war style can reuse. No existing file was modified; no commit.

## 1. Phase 1 as it stands (preserved untouched)

| Item | State |
|---|---|
| `cinematic_explainer/` | 5 files, 489 lines: `look.py` (tokens, fonts, easing), `cards.py` (kicker, source card, number, list, portrait, shot headline as pure functions of time), `render.py` (ffmpeg graph + RGBA frames piped in), `demo.py` (fixture timeline) |
| `test_cinematic_explainer.py` | 13 tests, all pass; plus 184 regression tests on existing styles pass |
| Demo `out/cinematic_phase1.mp4` | 25.4 s, silent, fixture text only, placeholder portrait; render 8.7 s |
| Scorecard | 3.2/5 weighted, Phase 1 = PASS as prototype, not acceptance |
| Working tree | only new files; other sessions' untracked `docs/terrain3d/` and `out/` left alone |

**What Phase 1 proves:** card grammar and measured timings from reference A can be drawn deterministically; the dim/blur backdrop is cheap in ffmpeg; the pack can stay isolated.
**What it does not prove:** anything about war content. It has no equipment, map, front-line, source-verification or planning logic, and the number card, source card and portrait are generic. It is a general explainer foundation, not the war style.

**Known defects carried into this design:** (1) memory 2.3 GB for 25 s and growing with length (cause and fix: see performance plan); (2) no condensed or news-serif font bundled (separate approval); (3) no push or masked-reveal transition; (4) sync tested on fixture timings only.

## 2. Existing components the war style can reuse (verified by listing, not by running)

| Need | Existing component | Note |
|---|---|---|
| Animated geographic map, country/region fill | `map_scene/` (data: countries, admin1, land, named_regions), Hybrid Map (`hybrid/`), pakMap (`pakmap/`) | Hybrid Map already outlines named places (`docs/hybrid/place-boundary-highlighting.md`); front lines are not in the data |
| Place cards, routes, distances | gfx-core `geo/`: `location_card`, `place_lowerthird`, `route_travel`, `distance_ruler`, `region_label`, `region_spotlight`, `territory_clock`, `flow_route`, `chokepoint_callout` | most are map-only per `docs/hybrid/template_inventory.md` |
| Statistics, comparisons | gfx-core `stats/` (16 templates: `rank_bars`, `versus_numbers`, `bar_race`, `stacked_compare`, `trend_line`, `big_number`), `graphics/dataviz.py`, `graphics/statistic.py` | restyle only |
| Evidence/quotes/portrait-like | gfx-core `news/`: `quote_boxed`, `framed_still`, `checklist_card`, `name_bar`, `polaroid_board`, `dossier_card`, `timeline_strip`; `editorial/quote_card`, `photo_plate_*` | portrait circle and paper source card are new (Phase 1 versions exist) |
| Narration-driven planning | `graphics/doc_plan.py`, `gfx_extractors.py`, `graphics/director.py`, Hybrid planner (39 rules), `editorial/` | rules exist for names, places, numbers, quotes; none for equipment or front lines |
| Asset cache / provenance | `cache_manager.py`, `downloaded_assets.py`, `asset_manager.py`, `weather/provenance.py`, `boundary_source.py` | agent A states which carry the new fields |
| Segmented render, render cache | `test_render_segmented.py`, `test_render_cache.py`, `docs/pakmap_render_segment_reuse.md` | agent C states how a segment plugs in |
| Audio | streaming audio mixer, curated ambience/SFX | unchanged |

## 3. What is genuinely missing for a war documentary
Equipment identification model and cards; front-line and territorial-change data and reveal; verified insignia/flag/icon set; provenance with event/captured/published dates, verification state and recycled-footage flags; a war-aware planner (sources, attributed statements, equipment, trajectories labelled illustrative); bounded-memory segment renderer. These are the subject of the other documents in this folder.

## 4. Deliverable index
1. `asset_taxonomy_and_metadata.md`, 2. `visual_treatment_and_animation_catalog.md`, 3. `narration_to_visual_planning_rules.md`, 4. `source_verification_and_reuse_policy.md`, 5. `demonstration_sequence.md`, 6. `performance_plan_bounded_memory.md`, 7. `test_and_regression_plan.md`, 8. `file_changes_and_dependencies.md`, 9. `phases_and_pass_fail.md`.
