# Cinematic Explainer — acceptance scorecard

Scored at the end of Phase 1 and Phase 5. Score 1–5 with evidence (frame paths, test names, timings). Threshold: weighted ≥ 4.0, no category below 3.

| Category | Weight | Phase 1 | Final | Evidence |
|---|---:|---|---|---|
| Visual quality and art direction | 20 % | – | – | |
| Animation quality and timing | 20 % | – | – | |
| Narration-to-visual relevance | 20 % | – | – | |
| Typography and readability | 10 % | – | – | |
| Transition quality and pacing | 10 % | – | – | |
| Performance and caching | 10 % | – | – | |
| Regression safety | 10 % | – | – | |

## Hard gates (all must pass regardless of score)
- Existing style tests pass unchanged; protected manifests (`test_fixtures/*_protected.json`) untouched.
- News Doc, Hybrid Map, Explainer output identical with the new look off (frame hash on a fixed fixture).
- New look is opt-in and not the default; its settings do not leak.
- No blank frames at transitions; graphics inside frame bounds; narration timing unchanged.
- Render time and peak memory measured against the baseline, no unexplained regression.

## Measured targets for the demonstration render (from the references)
average shot 4–5.5 s · card time 25–35 % · ≥ 12 number cards per 14 min · ≥ 4 source cards · ≥ 4 map visits · no two cards at once · no still stretch over 8 s.

## Baseline (before any new code, 2026-10-27)
Focused set (test files are in the repo root, not `tests/`): `test_doc_style`, `test_normal_gfx`, `test_gfx_templates`, `test_hybrid_graphics_planning`, `test_weather_newsdoc`, `test_zoom_blur_callouts`, `test_graphics_composition`, `test_graphics_engine`, `test_gfx_inventory`: **193 passed, 1 error in 104 s**. The error is `test_weather_newsdoc.py::test_video`: pytest treats a helper named `test_video` as a test and cannot find its fixture. It was there before my change and is unrelated to it. Not measured: render time and memory of an existing style (no existing-style render was run).

## Phase 1 result (prototype, 2026-10-27)

Demo: `out/cinematic_phase1.mp4` (25.4 s, 1280x720, 25 fps, silent), built by `python3 -m cinematic_explainer.demo`. It shows clean footage with a typed shot headline, dimmed/blurred footage under a source card (words darken with fixture word timings, highlighter follows), a number card (count, label, drawn rule), a three-row list, a circle portrait (placeholder silhouette, no real person) and the dim ramp as the transition.

| Check | Result |
|---|---|
| New tests `test_cinematic_explainer.py` | **13 passed**: deterministic cards, inside the frame, fade in/out, count timing, word-by-word order, list rows follow item times, no portrait without an image, no blank or missing frame across the cut and dim ramps, exact frame count |
| Same render twice | identical frame hashes (md5 of all 635 frame hashes equal) |
| Regression, same focused set plus the new file | **184 passed** (the weather newsdoc file is excluded because of the pre-existing error above) |
| Existing styles changed | none. `git status` shows only new files; nothing outside `cinematic_explainer/` imports the pack (checked by a test) |
| Render speed | 8.7 s for 25.4 s of video (about 72 fps, about 2.9x real time) on this Mac |
| Peak memory | **2.3 GB** for a 25 s clip. **Defect:** ffmpeg buffers the footage while it waits for the dim branch, so this grows with video length. A 14-minute render must be done per segment, as the app's segmented render already does |
| Narration sync | verified against fixture word timings only; no real audio and no planner yet |

Self-scores (my judgement, to be confirmed by your eye on the render):

| Category | Weight | Score | Why |
|---|---:|---:|---|
| Visual quality and art direction | 20 % | 3 | Reads like the reference family; fonts are not condensed or newspaper-serif (none bundled); demo footage is generic |
| Animation quality and timing | 20 % | 3 | Timings copied from measurements; not yet compared side by side as moving video |
| Narration-to-visual relevance | 20 % | 3 | Not testable before Phase 3; fixture only |
| Typography and readability | 10 % | 3 | Readable at 720p; the serif is Cormorant Bold, lighter than the reference |
| Transition quality and pacing | 10 % | 3 | Only the dim ramp and hard cuts exist; push and masked reveal not built |
| Performance and caching | 10 % | 3 | Fast, but the memory defect above |
| Regression safety | 10 % | 5 | 184 tests pass, no existing file touched |
| **Weighted** | | **3.2** | below the 4.0 acceptance threshold, as expected for a prototype |

**Phase 1 decision: PASS as a prototype** (it renders, is deterministic, isolated, and every card in the brief's list is shown). **Not an acceptance pass.** Blocking items for Phase 2: segment rendering to remove the memory growth, a font decision (condensed face and a bold news serif need your approval to add), the missing push / masked-reveal transitions, and a real-audio sync test.
