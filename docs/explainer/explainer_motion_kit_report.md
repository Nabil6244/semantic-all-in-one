# Explainer motion kit (Phase 9 of the reference-2 plan): report (2026-10-27)

Opt-in (`DirectorOptions.motion=False` by default), deterministic, backward compatible. Nothing is staged, committed or pushed. `app.py`, `VideoGenerator.spec`, `settings.json`, `hybrid/`, `pakmap/`, the protection manifest, `m4_app_patch.diff`, `cinematic_explainer/` and `weather/` were not touched.

**Naming clash:** the analysis calls this "Phase 9" and proposed `spike/test_phase9_motion.py`, but `test_phase9_footage.py` already exists (and `test_phase10_look`, `test_phase11_controls`). The tests are therefore in `explainer/spike/test_motion_kit.py`, and the code and docs say "motion kit". "Phase 9" in the analysis and "phase 9" in the footage tests are different things.

## Revision 2 (narrow Phase 9 revision, 2026-10-27): date plates replace the year tag

**Status: the motion kit is ready for your review.** No genuine failure remains in anything the kit touches; the only red checks are the five blocked by the app-patch drift below. Nothing staged, committed or pushed; `app.py`, the spec, the manifest and the patch were not edited.

**What changed (`director/compose_motion.py`, tests, schema doc):**
- A plate is now only for an *important date*, by a deterministic score (`date_score`, needs >= 2): an event word (began, ended, fell, war, freed, signed, ...) within 6 words of the year +2; the sentence is the opening, a twist or a conclusion +1; it is the narration's first year +1. Fixed lexicon, no randomness. Ordinary years (for example "A visitor in 1962 wrote about the quiet ruins", score 0) get no plate and the report says why.
- An eligible date **replaces** the board's own bare-year `tag` or `chip` (same anchor word; the old cue is removed; arrows that reference it block the swap). If no place is found the board is left exactly as it was.
- Duplicate guard kept, now precise: after the swap, any separate year element still carrying that number (another tag, chip, title, header or plate, including a tag like "1945 after") refuses the plate; with no tag to replace, any cue showing the year, including a running phrase, refuses it. One plate per beat, at least 15 s apart (was 10).
- Tests were rewritten for the new rule (28 tests now, all pass): they are requirement changes, not relaxations. Two assertions were refined on genuine fixture facts: the plate/stamp overlap test compares only elements on screen at the same time (the board clears between sentences, so rectangles can overlap without ever being visible together, which is what H07 checks), and the "holds still" check samples 0.4 s after landing because the board's own clear removes the plate about 1 s after it appears, exactly as it removed the tag.

**Encoded evidence** (real clips from a 35.7 s synthetic script, motion off vs on; `phase_motion_evidence/plate_e4_1944_before_after_sheet.jpg`, `plate_e7_1945_before_after_sheet.jpg`, `*_on_landed_full.jpg`, `*_off_tag_full.jpg`, `plate_encoded_verification.json`):
- e4: the navy "1944" tag is replaced by a 1944 plate; e7: the large dark "1945" chip is replaced by a 1945 plate. Both words are in the beat's narration.
- Timing, measured in the encoded clip: the plate's first changed frame is clip frame 36 in both beats, equal to the planned frame, 0 frames after the word's frame; zero changed pixels in the three frames before it.
- Safe margins: the measured changed-pixel box at landing is (1682,96,1823,184) and (1680,96,1823,184), inside the safe area (96,96,1824,984).
- No duplicated year: the old tag/chip rectangle holds ink in the motion-off clip (0.42 and 0.23 of pixels) and none in the motion-on clip (0.0); the only separate year element on each board is the plate (the typed phrase "siege began in 1944" is the narration's own text and was there before).
- The on/off clips differ only in beats e3 (SURROUNDED stamp), e4, e7. One run each: 13.1 s off, 13.3 s on (single run, not a timing claim).
- Honest design note: the plate is smaller and quieter than the tag or chip it replaces (a small cream corner plate against a navy tag / big dark chip). The year is still on screen in the typed phrase. If you want dates to be *more* prominent, the plate size (`PLATE_PX`) is the knob; I did not change it.

**Verification re-run after the changes**
| Check | Result |
|---|---|
| `test_motion_kit` | 28/28 pass |
| `motion=False` vs recorded HEAD (plan, options, cue specs, clip names; Korea + verdict script, both looks) | identical, re-verified after the final edit |
| `verify_m1` / `m2` / `m3` | 21/21, 41/41, 115/115; clip hashes equal the recorded evidence |
| `test_phase7_cartoon` | 25/25 |
| `verify_m4` | 251/253 (via scratch copy, see below); both failures are patch-drift |
| `test_phase8_hardening` | 8/11; all 3 failures are patch-drift |

**Blocked by `m4_app_patch.diff` drift (not genuine failures of this work):** `verify_m4` `app_patch_applies_cleanly_to_the_current_files` and `patched_app_and_spec_still_parse` (plus the unmodified script crashing at its `patch -R` step with `check=True`, which is why a scratch copy with that one flag relaxed was used; the copy is outside the repo and the real script is unchanged apart from the packaging count); Phase 8 `PatchedHandlers.setUpClass`, `AppPatch.test_it_applies_cleanly_to_head_and_the_result_parses`, `AppPatch.test_the_weather_guard_sees_only_added_lines`.
**Exact cause:** HEAD's `app.py` already contains the patch (commit b0608df), and commit aa53b01 ("patch v2") then added four lines directly to `app.py` inside the patched regions without regenerating the patch: `from explainer.ui_options import install ...` and `_install_explainer_options(self, actions)` (after the Explainer switch/button block) and `from explainer.ui_options import status_after_plan ...` and `status_after_plan(self, plan)` (in `_hybrid_explainer_direct`). Reversing the patch therefore fails 2 of 4 `app.py` hunks (the two hunks that contain those regions). `tests/verify` all fail at the same call (`unpatched_files`, test line 37, which asserts `patch -R` returns 0). Proof: in a scratch copy of `app.py` with exactly those four lines removed, `patch -R --dry-run` applies cleanly. The spec hunk is not involved. The fix is to regenerate `m4_app_patch.diff` from the current `app.py` (out of scope here; it is a pending-patch edit).

Remaining blockers: only that patch regeneration. Not done, unchanged from before: everything in section 6 below; no real voiceover or long render; one Mac.


## 1. What was built

| File | What |
|---|---|
| `explainer/motion/presets.py` | pure frame tables on a 30 fps grid: `slam` (8 frames: 1.55x down to 0.94x at the impact on frame 4, small shake, 1.012x overshoot, settled on frame 7) and `slide_in` (9 frames, ease-out cubic, 60 px). No randomness. |
| `explainer/motion/sprites.py` | stamp and plate drawing and measuring, cached by parameters; stamp worn by a mask from `assets/stamps`, verified against `manifest.json` (SHA-256 + byte count). Missing or damaged mask = plain stamp. The sprite is kept whole inside the frame during the large approach frames. |
| `explainer/motion/build_assets.py` | one-time builder, `--check` rebuilds in memory and compares bytes; never run during a render |
| `explainer/assets/stamps/` | `grunge_a.png`, `grunge_b.png`, `manifest.json` (3 files, drawn from fixed seeds with Pillow, no outside art) |
| `explainer/director/compose_motion.py` | the motion pass: at most one verdict stamp and one year plate per board beat; every candidate (size, place) is tested with `dry_build` and accepted only if the whole beat still builds with no problem |
| edits | `board/styles.py` (two styles, `measure` delegates), `board/elements.py` (`draw_visual` delegates), `director/options.py` (`motion`), `director/plan.py` (pass after repair for `look=="reference"` non-cartoon beats, re-gate, `motion` record per beat; `motion` omitted from the report options when False; the clip name gains a mask-manifest digest only for a beat with a textured stamp), `packaging.py` (`assets/stamps`), `integration.py` (`motion_enabled(settings)` reads `explainer_motion`, default False, bad values False; passed to `DirectorOptions`), `spike/verify_m4.py` (packaging file count now includes the stamps folder; nothing else) |
| docs | `explainer_cue_schema_v1_5.md` (short), this report. `EXPLAINER_VERSION` and `SCHEMA_VERSION` are **not** bumped (would change every clip hash); motion cues carry `params.mv`. |

Rules in the pass: stamp words come from a fixed lexicon (`VERDICT`, plus a green `VERDICT_GREEN`); the stamp text is the speaker's word in capitals; it needs 0.8 s left in the beat and 15 s since the previous stamp; the cue is anchored on the word with offset 0 (first visible frame = the word's frame, never earlier). A plate is a spoken 1000-2099 digit token, 10 s since the previous plate, skipped when any cue on the board already shows that number.

Bugs found by the first smoke run and fixed: (1) a stamp at 120 px is 835 px wide and the old fixed candidate places rarely fit (a `worthless` stamp found no place); candidates are now a preference-ordered grid inside the content area with the tilt, shake and settle overshoot reserved, trying 120, 96, then 72 px; (2) the 1.55x approach frames ran past the right frame edge (visible in the first evidence sheet); now clamped inside the frame; (3) the plate duplicate check compared whole texts only, so a plate "1945" next to the caption "1945 the survivors were freed" slipped through; it now compares number tokens.

## 2. Tests and results (what ran, and what did not pass)

| Check | Result |
|---|---|
| `spike/test_motion_kit.py` (new) | **24 tests, all pass** (~17 s). Covers: presets pure/deterministic, slam settles in 8 frames with undershoot and overshoot, slide monotonic; stamp first visible frame 0..+0.3 s after the word, and pixel-identical to "no stamp" one frame before; stamp text a contiguous quote; no two stamps within 15 s (stress script) and at most one per beat; stamp and plate inside the safe area on impact, shake and settled frames, no collision, layout gate clean; every other cue of a beat unchanged by the stamp; plate year spoken in the beat and never a duplicate of a shown number; plate lands on the word, holds still; stamp and plate in one beat do not overlap; `--check` passes and mask hashes verify; packaging lists the folder; no byte under `explainer/assets` changes during a render; missing mask, damaged mask and missing manifest each give a plain stamp, a logged note and no failure; `motion=False` equals the recorded HEAD baseline; same plan twice gives identical plan JSON and identical frame hashes; setting parser |
| `motion=False` vs HEAD | A copy of HEAD's `explainer/` (outside the working tree, no stash) was run on the Korea fixture and a 37 s verdict script, both looks: **plan, options, cue specs and every clip name are identical** (`phase_motion_evidence/disabled_path_baseline_HEAD.json`, re-checked after the last edit). |
| `verify_m1` / `m2` / `m3` (dissolve 0, full runs with real renders) | **21 / 41 / 115 checks all true**; `clip_sha256` and `clip_bytes` equal the recorded `m1/m2/m3_evidence` files |
| `verify_m4` | **251 of 253 true. Two fail, both about the app patch:** `app_patch_applies_cleanly_to_the_current_files` and `patched_app_and_spec_still_parse`. The packaging check (adjusted for the stamps folder) passes. **The unmodified script crashes** at its `patch -R` step because the patch no longer fits the current `app.py`; to get the other results I ran a scratch copy with that one `check=True` relaxed (`check=False`), copy not in the repo. The patch drift predates this work (`patch --dry-run` of `m4_app_patch.diff` against `git show HEAD:app.py` fails 2 of 4 hunks) and I was told not to touch `app.py` or the patch. |
| `test_phase7_cartoon` | 25 tests, all pass |
| `test_phase8_hardening` | **8 of 11 pass; 3 fail with the same cause** (`PatchedHandlers.setUpClass`, `AppPatch.test_it_applies_cleanly_to_head...`, `AppPatch.test_the_weather_guard_sees_only_added_lines`: "2 out of 4 hunks failed" applying the app patch). Its packaging test passes. |

## 3. Frames (`docs/explainer/phase_motion_evidence/`)

Rendered from real encoded clips of a 37.1 s synthetic script (motion on vs off, `look=reference`):
- `stamp_e3_surrounded_sheet.jpg`, `stamp_e6_caught_sheet.jpg`: frame before, slam frame 0, 2, impact (4), shake (6), settled (9). `*_impact_full.jpg`: full-size impact frame.
- `pixel_proof.json`: on-vs-off difference around the stamp in the **encoded** clips: frame before the first frame is 0.001 mean abs difference and 0 pixels over 40 (stamp absent), then 42-45 thousand changed pixels from the first frame on.
- `plate_1945_slide_in_sheet_in_memory.jpg`: plate slide-in, **drawn in memory, not from an encoded clip, on a plain grey board**, from a real beat with its year cues removed (see section 5, plates).
- Determinism: encoded clip md5 identical across 6 runs per mode; the 4 beats the pass did not touch are byte-identical to motion off, the 2 stamped beats differ.

## 4. Timing (what was measured)

The pipeline is Pillow frame drawing plus ffmpeg encoding of each board clip. Measured: wall time of `direct(..., materialize=True)` (planning including the motion pass candidates, plus encoding every board clip) for the 37 s script, 7 board clips, 2 stamps, fresh work folder per run, off and on alternated, 6 runs each, one Mac.
- motion off: 14.51 s mean (13.8 to 15.7, sd 0.65); motion on: 14.89 s mean (14.3 to 15.4, sd 0.42). **+0.38 s, +2.6 %**, which is about one standard deviation of the run-to-run noise.
- An earlier set of runs while the machine was busy was too noisy to use (18.7 vs 19.4 s with sd 4 to 6 s); I discarded it and repeated on a quiet machine.
- Drawing only (in memory, per frame, the two stamped beats, best of 3): 2.17 to 2.98 ms per frame without, 2.42 to 3.35 ms with, i.e. +11 to +13 % of the drawing cost in beats that carry a stamp. Encoding dominates, hence the small total.
- Not measured: a long (10+ min) video, other machines, Windows.

## 5. Limitations and honest caveats

- **(Superseded by Revision 2 above.)** Original finding, kept for the record: plates never fired on ordinary scripts. The existing planner already shows every spoken year (a tag plus a phrase), so by the "never a duplicate of a shown number" rule the plate is skipped; I tried about a dozen year sentences and the skip reason was always "already shown". The plate path is tested by taking a real beat and removing its year cues, and the plate frames are in-memory evidence, not an encoded clip. Whether plates are worth having is a design question for you (for example: replace the tag instead of adding beside it).
- Synthetic voice and word times (rule-made), so "on the word" is verified against those times, not against a real voice. One Mac. No human has rated the look.
- Year plates exist only for digit tokens (1000-2099); spelled-out years are not detected.
- The verdict list is a fixed lexicon (32 red words, 7 green); words like "no" and "never" from the analysis are not included. Stamps are added only to board beats with `look == "reference"`, never to map, archive or cartoon beats, so a stamp can be absent where the narration has a verdict word.
- The approach frames of the slam (first 4 frames, up to 1.55x, partly transparent) may briefly cover neighbouring elements; the layout gate and the collision tests check the impact, shake and settled frames, not those 4.
- Textures depend on the Pillow version that built them (manifest records it); `--check` fails on another Pillow if it renders the masks differently, but the shipped bytes are what is used at render time and are verified by SHA.
- Stamp and plate sizes shrink to 72 px / 28 px if needed; a very long verdict word may find no place and is then skipped with a reason in the report.
- The unit tests need ffmpeg only for the encoded evidence, not for the test file.

## 6. Not done (analysis items out of this scope)

`count_up`, `cross_out`, `pop`, `grow` as presets (only `slam` and `slide_in` exist), the map overlay layer and draw-on outlines, camera push-in, grain and vignette, place and name plates (only years), dialogue/speech bubbles, the dark dossier stage, staged diagrams, sort/split layouts, layout-variety rule. Also not done: a real voiceover render, a long render, any change to `app.py` or the app patch (so the setting `explainer_motion` is read by `integration.motion_enabled` but nothing in the app sets it yet).

## 7. Open items for review

1. Decide whether the quieter plate is acceptable or should be larger (Revision 2). 2. The stale app patch makes `verify_m4` crash and 3 `test_phase8_hardening` tests fail independent of this work; it needs its own fix. 3. Nothing is committed; the new files are untracked.
