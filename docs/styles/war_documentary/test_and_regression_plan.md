# War Documentary style: test and regression plan

Status: plan. Numbers marked **[measured]** come from this session (see `performance_plan_bounded_memory.md`); **[proposed]** are my gates, to be agreed. Test files live in the repo root (`test_*.py`, unittest style, run with `python3 -m pytest <files> -q -p no:cacheprovider`).

## 0. Baselines already taken (before any new code)
- Focused existing-style set: `test_doc_style`, `test_normal_gfx`, `test_gfx_templates`, `test_hybrid_graphics_planning`, `test_weather_newsdoc`, `test_zoom_blur_callouts`, `test_graphics_composition`, `test_graphics_engine`, `test_gfx_inventory`: **193 passed, 1 error in 104 s [measured]**. The error is `test_weather_newsdoc.py::test_video` (a helper pytest mistakes for a test), present before any change.
- With the Phase 1 file added (`test_cinematic_explainer.py`, 13 tests): **184 passed** on the same set minus the weather file **[measured]**.
- Protected manifests and segment/cache suites today: `test_enoch_template_phase0.py`, `test_weather_isolation.py`, `test_render_segmented.py`, `test_render_cache.py`: **57 passed in 44 s [measured]**.
- Memory/time baseline for the existing styles: **not measured** (no existing-style render was run). Gate: take it before Phase 2 (section 6).

## 1. Unit tests (new file per area, all in new test files)
| File (new) | Covers |
|---|---|
| `test_cinematic_explainer.py` (exists, 13) | cards deterministic, inside the frame, fades, count timing, word order, list timing, no portrait without an image, no blank frames across cut and ramp, isolation |
| `test_war_taxonomy.py` | asset metadata schema validation: required fields per category, enum values, event date vs footage capture/publish date kept separate, licence/attribution present, verification status in the allowed set, "illustrative" flag mandatory on diagrams and trajectories |
| `test_war_planner_rules.py` | narration to visual: each rule has a positive and a negative case (a country name alone never makes a map; a leader's name without a verified portrait gives no portrait; a stated number gives a number card; unsupported weapon identification gives a flagged mismatch, not a card) |
| `test_war_segments.py` | segment planning: frame-aligned boundaries, no card straddling a cut, input cap, deterministic cache key (same inputs same key, any card/portrait/clip change a different key, dict order irrelevant) |
| `test_war_motion.py` | each motion primitive is a pure function of `t`; monotonic where it must be (counts, drawn lines, front-line reveal); bounded values; settled frame equals the last frame |
| `test_war_failure.py` | missing clip, corrupt portrait, missing font, ffmpeg failure: safe fallback or a clear error, work folder removed, no half-written output |

## 2. Visual tests
Automated checks do not judge quality; each phase also gets a human review of a contact sheet and of the moving render.
- **Frame-level assertions:** text inside the safe margin (5 % of width), no two full cards at once, card text contrast against the dimmed plate >= 4.5:1 [proposed], lower-third never overlaps a card, portrait circle fully inside frame, map labels do not overlap each other (bounding-box test).
- **Golden frames [proposed]:** for each card kind, the settled frame at fixed `t` is stored as a PNG hash **only for the new pack** (`test_fixtures/war_documentary/golden/*.sha`). Refresh only by a deliberate, logged step. Because the segmented renderer is not bit-identical to the Phase 1 monolithic one (mean 46.4 dB, worst 38.4 dB **[measured]**), goldens are made from the segmented renderer only.
- **Reference comparison sheet:** `contact_sheet(render, every=4 s)` and the same for the reference video, side by side, scored against the measured reference numbers: average shot 4 to 5.5 s, card time 25 to 35 %, at least 12 number cards, at least 4 source cards, at least 4 map visits per 14 minutes, no still stretch over 8 s, no two cards at once.
- **Required sequence:** the representative demo (clean footage, footage with a card, portrait, source document, number/chart reveal, map, chapter transition, recap) rendered and viewed in full.

## 3. Regression tests: existing styles unchanged
1. **Same focused set** as the baseline, must give the same result (193 passed, same 1 pre-existing error) after every phase: `test_doc_style`, `test_normal_gfx`, `test_gfx_templates`, `test_hybrid_graphics_planning`, `test_weather_newsdoc`, `test_zoom_blur_callouts`, `test_graphics_composition`, `test_graphics_engine`, `test_gfx_inventory`.
2. **Style-specific suites for every style the new pack could touch:** `test_hybrid*.py`, `test_pakmap_*.py`, `test_starmap_*.py`, `test_whatif*.py`, `test_exp_solar_*.py`, `test_overscaled_*.py`, `test_enoch_template_*.py`, `test_weather_*.py` (excluding the known error), `test_style_picker.py`, `test_style_engine.py`, `test_settings_respected.py`, `test_settings_tabs.py`, `test_text_switches.py`. Run the full list once before approval and once at the end; the intermediate phases run the focused set.
3. **Protected manifests:** `test_enoch_template_phase0.py` (`test_fixtures/enoch_template_protected.json`) and `test_weather_isolation.py` (`test_fixtures/weather_protected.json`) must pass **before and after** every phase. If a phase must touch a protected file (only the single `app.py` hook, additions only), grep both manifests for that path first; a refresh needs your explicit approval and an entry in the manifest's `_about` field; never refreshed to hide a change.
4. **Isolation test (exists):** nothing outside `cinematic_explainer/` and its tests mentions the package, until the approved hook; then the test is changed to allow exactly that one reference (`app.py`) and fails on any other.
5. **Frame-hash fixtures for existing styles:** before Phase 2, render one short fixture per style that already has a deterministic offline path (Doc Style card PNGs from `graphics/doc_style.render_doc_style`, Hybrid template layers) and store the hashes in `test_fixtures/war_documentary/regression_hashes.json`; rerun after each phase. Only deterministic outputs get hashes (not encoded video).
6. **Settings leakage:** the pack's settings keys are namespaced (`cinematic_explainer.*`); a test loads and saves settings with the pack on and off and compares every other key byte for byte; `doc_style` behaviour must be identical with the pack off.
7. **Default off and style switching:** a fresh settings file has the pack off; switching pack on then off restores exactly the previous behaviour; repeated export of the same project twice gives identical frames.
8. **Cache correctness:** wrong-asset-reuse test (two different portraits with the same name and size never share a cache entry); a changed card invalidates only its segment; project isolation (two projects never share entries, as `test_render_cache.py` already requires of the shared cache); corrupt or wrong-schema index is a miss, not a crash.
9. **Existing shared render tests must stay green untouched:** `test_render_segmented.py`, `test_render_cache.py`, `test_render_opens_export_page.py`, `test_export_workflow.py`, `test_export_integration.py`, `test_xfade_transitions.py`, `test_visual_transitions.py`.

## 4. Integration tests
- **End-to-end small project:** a 60 s project (script, fixture word timings, local footage, one portrait file with provenance metadata) rendered through the real pipeline with the pack on: output has the exact frame count, correct audio length, 0 blank frames, planner report lists every visual with its source and verification status, no card without provenance.
- **Resume and cancel:** cancel mid-render leaves no work folder; a rerun reuses unchanged segments (cache hit count equals the number of untouched segments).
- **Mixed style project:** the same project exported with the pack off, then on, then off: first and third outputs identical.
- **Long project (10 min):** the segmented render completes under the budgets below; run once per phase gate, not on every commit.

## 5. Audio and synchronization checks
- Segmented output is video only; the **mux step** attaches the existing mix. Checks: video duration equals audio duration within one frame (40 ms); the narration word at which a card is meant to change appears within +-1 frame (40 ms) of the change in the rendered frames (measure by detecting the card's first non-blank frame, compare with the word-timing fixture); every segment is a whole number of frames and every join is on a keyframe (`ffprobe` packet flags, measured pattern in the prototype: joins at 4.6, 10.4, 15.2, 20.6 s all keyframes); loudness unchanged by the pack (the pack never touches audio): LUFS of the mixed file with the pack on equals the pack off within 0.1 LU on the same project.
- Real-audio sync test is **not yet possible** (Phase 1 had fixture timings only); it is a Phase 3 gate.

## 6. Performance gates [proposed numbers, based on measurements]
Measured: monolithic Phase 1 peaks 2.46 GB at 25 s and 3.0 GB at 3 min; segmented peaks 0.59 / 0.61 / 0.62 GB at 25 s / 3 min / 10 min and renders at about 3.5x real time (10 min in 166 s) on this 8-core Mac.

| Gate | Threshold |
|---|---|
| Peak RSS of any ffmpeg process, any video length | **<= 1.0 GB** |
| Peak RSS growth from a 3 min to a 10 min render | **<= 10 %** (measured 1.3 %) |
| Render speed, 1280x720 25 fps, 8 cores | **>= 2.0x real time** (measured 3.5x), else a documented reason |
| Style-selection / pack import overhead when the pack is off | **0 ms**: the pack is not imported until selected (test with `sys.modules`) |
| Cache: second identical render | **>= 95 % segments reused**, wall time <= 25 % of the first |
| One card edited | **exactly the segments overlapping it re-render** |
| Existing styles' render time with the pack installed but off | within **+-3 %** of the pre-change baseline (baseline to be taken before Phase 2; not measured yet) |
| Python process peak | **<= 300 MB** (to measure) |
| Frames at every join | 0 blank, 0 duplicated, total equals `round(duration x fps)` |

## 7. Failure recovery
Missing/corrupt footage: segment uses the planner's next truthful choice or a flagged placeholder, never unrelated footage; missing portrait: no portrait, name plate only, plan report line; font missing: fall back to the bundled font and log it; ffmpeg exits non-zero: the work folder is removed, the error text (last 800 chars) is shown, the previous good cached segments are kept; disk full: a clear message and no partial file at the output path; cancel: no leftover child processes (checked with `ps`).

## 8. Scorecard hooks (pass/fail)
Each phase ends with `docs/styles/war_documentary/scorecard_phase<n>.md` created from `cinematic_explainer_scorecard.md`: seven weighted categories scored 1 to 5 with evidence (frame sheet path, test name, measured number). **Pass = all hard gates true AND weighted >= 4.0 AND no category below 3.** Hard gates (any failure is a fail regardless of score): sections 3.1 to 3.9 pass, protected manifests untouched or approved, no existing style behaviour changed, peak RSS and speed gates met, no provenance-less factual visual in the planner report. Scores come with the evidence list; I do not score "Visual quality" above 3 without your viewing the render.

## 9. Decisions needed from you (10 lines)
1. Retire the single-graph renderer in favour of the **per-shot segmented renderer** (0.6 GB flat vs 2.5 to 3 GB growing); accept that its frames are not bit-identical to the Phase 1 demo.
2. Approve **new files only** (`cinematic_explainer/segments.py`, new tests, new `test_fixtures/war_documentary/`) and **zero edits to `render_cache.py`, `video_generator.py`, `scene_graph/` or Doc Style files**.
3. Approve exactly **one `app.py` hook, additions only**, to select the pack (later phase), after a protected-manifest check.
4. Approve **namespaced settings keys** `cinematic_explainer.*` and default **off**.
5. Fonts: approve or decline adding a **condensed face and a news serif** (separate decision; open licence; new files under `assets/fonts/` and `gfx-core/fonts/`).
6. Allow me to **take an existing-style render baseline** (one short render per style, about 10 min of compute) before Phase 2.
7. Agree the **numeric gates** in section 6 (1.0 GB, 2.0x real time, 95 % cache reuse).
8. Confirm the frame rule: **all shot boundaries rounded to whole frames** by the planner (needed for audio sync).
9. Portrait provenance: **no verified portrait means no portrait** (name plate only); who supplies verified sources (you, or a cached licence-checked lookup).
10. Do you want a **real-audio sync test project** (voiceover plus word timings) supplied for the Phase 3 gate?
