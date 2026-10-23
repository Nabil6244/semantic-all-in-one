# Explainer Phase 4: map beats on the existing pakMap (2026-10-23)

Uses the repository's own pakMap/Hybrid path unchanged (`hybrid.compile.compile_plan` -> `pakmap.engine_runner.render_spec`, imagery on, per-user NASA tile cache). Nothing in `hybrid/`, `pakmap/`, `app.py`, the spec or `settings.json` changed.

## What was found
The Hybrid plan gives the camera one place plus a frame (`country`, `region`, ...) and relative `pull_back`/`push_in`; layers include `zone_label`, `stat`, `line`. The old director framed the first place only, so on the Korea beat the compiled view (lat 33.0 to 39.8) cut off most of North Korea (lat 37.7 to 43.0): the previous "may be off screen" warning was a real defect, found independently from the compiled spec.

## Changes (all under `explainer/`)
- `beats/framing.py` (new): view geometry from `pakmap.geo` (the engine's own constants), `plan_camera` (one view holding every place, centred and pulled back with room for the caption band; else the camera goes to each place in turn; a place the camera cannot show in this beat is rejected with a reason), `check_framing` (proof from the plan), an optional slow `push_in` for a long single view.
- `beats/mapbeat.py`: `camera_steps`, `zone_labels` (country names inside their outlines), `stats` (a spoken whole number with a quantity word, never a year).
- `beats/relevance.py`: the framing warning now uses the real view (pull_back/push_in included) instead of "centre inside the camera place's box".
- `director/plan.py`: map beats use `plan_camera`; layers wait for the camera; `map_layers_rejected` in the report; `_stats_for`.
- Tests: `spike/test_phase4_maps.py` (15; 8 failed before the change, all pass after).

## Results (Korea, real-material fixture)
| | Before | After |
|---|---|---|
| Both Koreas in the compiled view when their layers appear | North Korea cut off | both fully inside, room under for the caption |
| Map layers | 2 fills + caption | 2 fills + 2 zone labels (SOUTH KOREA, NORTH KOREA) + caption, 1 pull_back |
| Off-screen warning | yes | none |
| Meaningful-change windows (existing definition, counts labels and camera steps) | 0.913 | 0.957 |
| Content coverage, occupancy, still gaps | 0.799, 0.424, 3.24 s | unchanged |
Imagery run (whole 47 s video through the unchanged renderer): imagery loaded, 0 tiles failed, 0 stand-in tiles. First run 48 s with 55 new tiles downloaded; a run after the framing change downloaded 16 more (wider view) in 46 s; an identical re-run downloaded none (39 s): the cache is reused. Offline vector render 36 s. Credits file written (NASA GIBS acknowledgement); the imagery-off run writes the same line, so the credits file is not proof imagery was used. Pictures: `phase4_evidence/korea_map_before_after_sheet.jpg`, `frames/`, 7 s sample `korea_map_beat_sample_imagery.mp4`.

## Not done / limits
- No narrator over maps, archive pictures, `line` (border) layers or `hud_title` (a border line needs a spoken adjacency claim; not added). The camera is a single place plus frame, so a "both Koreas" view is centred on one of them (South Korea) and pulled back; Korea is small in it.
- Camera drift (0.5% per second) is covered only by a 4% margin. Tile cache and the NASA service are per-machine; cross-OS and the app GUI are untested.
- Visual quality is judged by me from frames; no human rating.
- The synthetic `say` voice and one script only.
