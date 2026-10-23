# Explainer Phase 7: cartoon kit (2026-10-23)

Schema: [v1.4](explainer_cue_schema_v1_4.md). Evidence: `phase7_evidence/` (kit sheet, before/after sheet, frames, 17 s sample, plan, report, test logs).

## What was missing and what exists now
Missing before: any cartoon asset, any cartoon beat, a crowd, time of day, a second cast member (scorecard T01 cartoon share 0 by design).
Now (all under `explainer/`): `cartoon/build_assets.py` (built once; `--check`), `cartoon/kit.py` (read-only loader, SHA-256 per file), `assets/cartoon/` (42 files, 1.3 MB: 5 sets x day/dusk, cast in 4 colours x 4 poses plus 2 extra idle looks, 7 props), `visual` styles `set`/`figure`/`crowd`/`prop` (styles.py, cues.py, render.py, elements.py, builder.py), `director/compose_cartoon.py`, opt-in `DirectorOptions.cartoon_share` (default 0), `select._assign_cartoons`, lexicon tables, plan.py branch.
The cast uses the narrator's drawing code with other colours (one style, not the same character); the narrator assets are byte-identical after the build (`--check`).

## Tests
`spike/test_phase7_cartoon.py` 22 tests: 17 failed before the change, all pass after (`phase7_evidence/phase7_tests_*.txt`). Also: Phase 4 maps 15/15, director regressions 23/23, `verify_m4` 253/253, `verify_m1` 23, `verify_m2` 49, `verify_m3` 115, builder 16, splice 20 checks, none false; M1 and M2 hash fields all equal to the recorded evidence; M3's plan hash differs only because the plan file contains the work folder path (as before). Off-mode snapshot identical, `app.py`/spec/`hybrid/`/`pakmap/` unchanged, patch applies and is not applied. Guard `test_weather_isolation` passes, but only against the dirty manifest (not proof against HEAD; not refreshed).

## Korea (real-material fixture, cartoon_share 0.3; Phase 4 map sample untouched)
Two beats became cartoon (e5 21.5 to 25.6 s, e7 31.8 to 38.0 s): a set, 2 figures, a row of 7 small figures, one word-by-word caption, no narrator. Layer mix board 0.895 to 0.676, map 0.105, cartoon 0.219; meaningful-change windows 0.957 to 1.0; longest still gap 3.24 to 3.08 s; content coverage 0.799 to 0.764 (one caption replaces the board's phrases); narrator share 0.52 to 0.583.

## Limits (not hidden)
- The cartoon scene is generic: the Korea script got a sunny desert town for "family business" and "prison camp". The set follows keywords, not meaning; with `cartoon_share` 0 (default) nothing changes. A human must judge whether such a scene suits the story.
- Figures do not speak, change pose or walk; they appear on words, pop in, and bob. Sets are not animated; time of day is a choice, not a transition. One caption per cartoon beat (a clear would also remove the set).
- Not done: speech-driven second character, dialogue scenes, split-screen of two sets, props added mid-beat, narrator over maps, archive pictures. Real-voice timing, cross-OS, GUI, human ratings are unverified. Phase 8 not started.
