# Explainer upgrade, phases C to F: report (2026-10-27)

Phases A (long-form foundation) and B (camera/texture) were skipped on request. Everything below is opt-in (a `DirectorOptions` switch, default False, and a settings key read by `explainer/integration.py`), deterministic, and proved equal to recorded HEAD output when off. Nothing is staged, committed or pushed. `app.py`, `VideoGenerator.spec`, `settings.json`, `hybrid/`, `pakmap/`, the protection manifest and `m4_app_patch.diff` were not touched. Evidence is in `docs/explainer/phase_motion_evidence/phase_c|phase_d|phase_e|phase_f/`. Specs: `explainer_cue_schema_v1_5.md` (stamps, plates); params added here (`count`, `cross`, `sv`, `pv`) are listed per phase below.

## What was built

| Phase | Switch / setting | What the viewer gets | Code |
|---|---|---|---|
| C numbers | `numbers` / `explainer_numbers` | A bare quantity shown as a tag or chip ("45 percent", "1,200", "$2.5 million") rolls up from zero in 0.8-1.2 s and ends on exactly its text. A negation (no, not, never, without ...) within 3 words before a picture's word draws two red strokes over that picture after it lands. | `director/compose_numbers.py`, `motion/presets.py` (`count_spec`, `count_text`, `cross_out`), `motion/sprites.py` (cross), small edits in `board/elements.py`, `render.py`, `cues.py`, `styles.py` |
| D map lines (re-scoped) | `maplines` / `explainer_maplines` | A `flow` line layer between two places the narration joins with a relation word ("from Egypt to Libya", "marched into"), drawn by the existing map engine. | `director/compose_maplines.py`, map part of `director/plan.py` |
| E variety | `variety` / `explainer_variety` | No picture-layout family three beats in a row (the third is authored again with the mirror variant, kept only if the family changes); a lamp-lit "dossier" backdrop on a beat that says secret, classified, spy, cipher ... (at most one beat in three, never the first board beat). | `director/compose_variety.py`, `board/backdrops.py`, `director/plan.py` (per-beat background, clip name) |
| F budget | `budget` / `explainer_budget` | Per-video windows: one stamp per 120 s, plate 180 s, count-up 90 s, cross-out 180 s, map line 150 s; stamp entrances (slam, drop, soft press) and plate entrances (slide down, from the right, fade and rise) rotate in order; the plan report gets `fx_budget` with every use and refusal. | `motion/budget.py`, `motion/presets.py`, `motion/sprites.py`, wiring in the passes and `plan.py` |

**Phase D was re-scoped.** The plan's overlay (stamp, plate, outline composited over the compiled map clip) needs either a layer the Hybrid plan does not have or the Explainer rendering maps itself: both mean changes in `hybrid/` or `pakmap/`. What was built needs neither. The map engine already draws country fills, zone labels and stats on Explainer map beats; the missing piece was the relation line.
**Not built** from the plan: dialogue bubbles (a board beat has no speaker to hang a bubble on), split/sort/seesaw layouts, staged diagrams, icon grids, a pop preset, stamps/plates on maps, camera push-in and grain (phase B).

## Evidence (encoded clips and real renders, not in-memory frames)

- C: `phase_c/count_e5_45_percent_sheet.jpg` (the tag reads 0, 30, 43, 45 percent over 26 frames and equals the switch-off board on the settled frame), `cross_e4_sheet.jpg` (two strokes over the water picture after "no water").
- D: `phase_d/map_flow_line_before_after_sheet.jpg`, a real `generate_hybrid_video` render through the unchanged map engine (offline map, tone audio). The line appears at the second place's word. It is thin and short for two neighbouring countries, so the visual gain is modest.
- E: `phase_e/dossier_before_after_sheet.jpg` (dossier vs plain paper for two beats). Ink-on-paper contrast across the content area is at least 4.5:1 at the 1st percentile (min 4.2:1 in the extreme corner); the first dossier tuning failed that test (3.2:1) and was lightened, not the test.
- F: `phase_f/stamp_variants_sheet.jpg` from a 5.5-minute (331.8 s) all-switches-on render: three stamps (SURROUNDED at 10 s, FREED at 132 s, CAUGHT at 257 s) in the three entrance variants. During the first 3-4 approach frames the "drop" variant can cross a neighbouring element (it passes over the "war" icon label in the sheet); the settled stamp never collides.
- Encode time, 331.8 s of narration, 69 board clips, one run each: all switches off 145.3 s, on 131.9 s and 151.1 s (two on-runs). That is run-to-run noise (other work was running on the machine), not a measurement; no cost was observed.
- 5.5-minute plan with budget on (synthetic script): 3 stamps, 2 plates, 4 count-ups, 2 cross-outs; without the budget the same script authors many more; 61 refusals are logged with reasons.

## Bugs found while building and in review

1. Stamp entrance variants were ignored by the renderer (the draw call did not pass them) although the unit tests passed, because the tests called the sprite function directly. Found from the encoded frames; fixed; a new test goes through Cue, layout and `draw_frame` and fails on the old code (verified by reverting the one line).
2. Dossier paper first failed its own ink-contrast test; the paper was lightened.
3. Review agent: Phase D map lines were broken after the budget wiring (`motion_state` used before it was assigned inside the map beat's try block, so a map beat that earned a line was silently demoted to a board beat; 3 maplines tests failed). I had not rerun the maplines tests after the budget edit. Fixed by creating the state and budget before the map loop; the maplines tests pass again.
4. Review agent: comma quantities from 1,000 to 2,099 ("1,200") were classified as years and never rolled. Fixed (`_is_year` requires no comma); a pass-level test now covers 13 text cases, replacing a test that could not fail.
5. Review agent: a line could join a place that had no fill or marker on that beat. Fixed (only places actually drawn are passed); a test asserts every line's places have their own layer; a budget test now uses a script that produces two lines so the refusal is actually exercised (the first version never reached it).
6. Layer ids: adding the line shifts the numbering of the layers after it (caption3 becomes caption4). Content is otherwise identical; the test compares everything except those ids.

## Tests (all offline; none encode)

`test_motion_kit` 28, `test_motion_numbers` 18, `test_motion_maplines` 10, `test_motion_variety` 10, `test_motion_budget` 16. Each file also proves its switch off equals the recorded HEAD baseline (`disabled_path_baseline_HEAD.json`: plan, options, cue specs, clip names for the Korea fixture and a verdict script, both looks) and that the same plan twice gives identical bytes.

## Verification (final code, run after the last edit)

| Check | Result |
|---|---|
| `test_motion_kit` / `numbers` / `maplines` / `variety` / `budget` | 28 / 18 / 10 / 10 / 16 tests, all pass |
| Every switch off vs recorded HEAD (plan, options, cue specs, clip names; Korea + verdict script, both looks) | identical |
| `verify_m1` / `m2` / `m3` (dissolve 0, real renders) | 21/21, 41/41, 115/115; clip hashes equal the recorded evidence |
| `test_phase7_cartoon` | 25/25 |
| `verify_m4` (scratch copy, see below) | 251 of 253 |
| `test_phase8_hardening` | 8 of 11 |

**Genuine failures: none** in anything these phases touch. **Blocked by the stale `m4_app_patch.diff`** (unchanged from the earlier report): `verify_m4` `app_patch_applies_cleanly_to_the_current_files` and `patched_app_and_spec_still_parse`; Phase 8 `PatchedHandlers.setUpClass`, `AppPatch.test_it_applies_cleanly_to_head_and_the_result_parses`, `AppPatch.test_the_weather_guard_sees_only_added_lines`. Cause: commit aa53b01 added four `explainer.ui_options` lines inside the patched regions of `app.py` without regenerating the patch, so the reverse patch fails 2 of its 4 `app.py` hunks. The unmodified `verify_m4.py` crashes at its `patch -R` step, so a scratch copy outside the repo with that one `check=True` relaxed was run.

Process note: two sub-agents were used. A read-only reviewer found items 3-5 under "Bugs" above. A verification agent ran `verify_m1-m4` and the equivalence check but was cut off by an API rate limit before reporting; its saved outputs (m1-m3 JSON, the m4 log, the equivalence file) were read directly and the focused tests, phase 7 and phase 8 were rerun by me afterwards. `app.py` and `VideoGenerator.spec` currently show as modified in `git status`: that is another session's Health Cinema work (files last written at 11:07 and 11:30), not these phases.


## Limitations

Synthetic voice and word times; one Mac; no human rating; effect rates are only measured on synthetic scripts of up to 5.5 minutes (never 30); quantity roll covers digits only (not spelled-out numbers); negation cross-out only over tile/circle pictures; map lines need both places in one camera view; the dossier lexicon is fixed (secret, classified, spy ...); stamp "drop" approach frames can briefly cross a neighbour; the real 5-minute voiceover look you were offered is still needed before any quality claim.
