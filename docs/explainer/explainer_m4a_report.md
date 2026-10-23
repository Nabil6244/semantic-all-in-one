# Milestone 4a report: the director library (no app changes)

Date: 2026-10-22. Scope as approved: **architecture B** (the director builds the Hybrid plan from the narration words and script, installed through the existing plan path), the director as a library, five-topic validation, and **the exact `app.py` and spec diff, written but NOT applied**, for your approval before M4b.
**Nothing committed, staged or pushed. `app.py`, `VideoGenerator.spec`, `settings.json`, every protected file, the protection manifest, installers and CI were not touched** (SHA-256 of all three shared files identical before and after). Spec frozen first: [explainer_director_spec.md](explainer_director_spec.md). Evidence: [m4_evidence/](m4_evidence/).
Offline, one Mac. **All word times are synthetic (rule-made), the narration is not a human voice, the offline test map has no satellite imagery, and the app's UI was not run.**

## Files
New under `explainer/`: `director/{__init__,options,lexicon,segment,select,compose,pacing,plan}.py`, `integration.py` (`direct_plan`, never raises), `packaging.py` (`data_files`, `python_modules`), `board/dry.py` (dry build: resolution, narrator track and layout without drawing), `spike/{verify_m4,m4_topics}.py`.
New under `docs/explainer/`: the director spec, this report, `m4_app_patch.diff`, `m4_evidence/`. **No existing explainer file was edited in this step** (file hashes compared before and after).

## What the director does (rules in the spec; all deterministic, no network, no AI, no randomness)
Sentences (script-aligned when a script exists) → beats of about 3.2 to 8 s that tile the narration with no gap → each beat becomes **map** (a place is spoken inside it and the budget allows), **archive** (a local library picture whose subject is spoken inside it), or **board**. A map beat is mandatory in a Hybrid plan, so with no spoken place the opening map shows an arbitrary fallback place and a warning says so. Board beats get cards (key phrase, icon or prop from a keyword table, colour role from polarity), arrows for cause or contrast, a chip for a number, a header and caption for hook, twist and conclusion sentences, a clear at each next sentence, and the narrator in runs of consecutive board beats (slide in at the first, settled in between, slide out at the last). Every board beat is dry-built, a cue that does not fit is dropped and listed, and still gaps are repaired. Story labels (hook, question, twist, conclusion) are reported, never invented.

## Results: five topics, hard cuts and 0.5 s dissolves (149 of 149 checks)
| Topic | Beats (kinds) | Median shot | Shots 2 to 8 s | Windows with a change | Narrator share / longest absence | Longest still gap | Places found |
|---|---|---|---|---|---|---|---|
| aqueducts (48.5 s) | 10 (9 board, 1 map) | 4.67 s | 100% | 95.8% (23/24) | 51% / 17.1 s | 2.35 s | Italy |
| coffee (36.6 s) | 7 (6 board, 1 map) | 4.82 s | 100% | 100% (18/18) | 58% / 5.9 s | 1.88 s | Ethiopia, Brazil, Colombia |
| inflation (36.7 s, no place) | 7 (6 board, 1 map: arbitrary fallback) | 4.77 s | 100% | 94.4% (17/18) | **63%** / 4.8 s | 1.88 s | none |
| printing (33.1 s) | 7 (5 board, 1 map, 1 archive) | 4.73 s | 100% | 93.8% (15/16) | 48% / 8.8 s | 1.86 s | Mainz, Germany, Europe |
| glaciers (34.3 s) | 7 (5 board, 2 map) | 5.11 s | 100% | **88.2%** (15/17) | 54% / 10.1 s | 1.96 s | Alps, Greenland, Iceland |
Scorecard targets (provisional): median shot near 4.6 s met in all five; 90% of shots 2 to 8 s met; a change in 95% of 2-second windows met in 2 of 5 (aqueducts and coffee), missed in 3 (94.4, 93.8, 88.2%); narrator share 35 to 60% met in 4 of 5 (inflation 63%); narrator absence under 30 s met in 5 of 5. These are reported, not forced. The hard-cut and dissolve runs give the same plan apart from clip lengths (a dissolve clip is half a dissolve longer on each side).
- **Validity gates, every plan, both settings:** `validate_plan` 0 problems; our relevance check 0 problems; the application's own editorial validator `hybrid.validate` 0 errors (it returns 1 to 3 warnings per plan, for example that more than half of the beats are under 5 s, which is the opposite of the reference's pacing; recorded in the report JSON); beats tile and there is exactly one camera start; 6 to 9 board clips per topic exist with the exact expected frame count; no remote or generating asset reference; **0 network attempts** while directing (every non-local connection was refused and counted).
- **Replay check:** every board beat was rebuilt from its recorded cue list in strict mode: no cue problem, **clip bytes identical to the cached clip**, and each cue's first frame equals a frame recomputed independently from its anchor word (36, 29, 32, 24 and 20 cues checked in the hard-cut runs; 0 off by even one frame). Timing of cues themselves was measured from pixels in M1 to M3 and is unchanged.
- **Story report:** every topic has a hook (0.5 s) and a conclusion; twist found in all five; a question found in aqueducts, coffee and inflation (it was missing in printing and glaciers, which simply have no question, and nothing was added).
- **Metaphors and colour roles:** one keyword always maps to one asset and one role in a video (checked for all ten plans); recurring keywords appear in every topic (for example `water` seven times in aqueducts, all `icon:drop`, all blue). A caller's table overrides the default and stays consistent (`water` as `prop:note`, gold, everywhere).
- **Real render:** the aqueducts plan (hard cuts, 49 s synthetic voice file) rendered through the **unmodified** `generate_hybrid_video` offline in 14 s: render ok, 1,470 frames equal to the voice file's length, 0 network attempts ([contact sheet](m4_evidence/aqueducts_render_contact_sheet.jpg)). The plan is 48.5 s because the voice file is whole seconds.
- **Determinism:** plans and clip bytes identical across two fresh folders and a separate process (6 coffee clips compared by SHA-256; plan JSON compared with the work path masked, hash `cbf4c0b2…7a5c`); a second run in the same folder reuses the cached clips and returns the same plan.
- **Robustness (never raises):** empty or garbage words, no work folder, an unwritable folder, a bad archive library, an unreachable fallback place all return problems with no plan. An archive library entry that is a missing file, a remote reference or lacks a reason is ignored with a note.

## Existing work preserved
`verify_m1` (21 checks), `verify_m2` (41), `verify_m3` (115) all true; cue rows, narrator state-change frames, caption frames, clip SHA-256s and asset hashes identical to the M1, M2 and M3 evidence (the M3 map plan is identical once its work-folder path is masked); `verify_builder` and `verify_splice` identical (board clip bytes and the splice render byte-identical).

## Protection, Git state, off-mode
| Check | Result |
|---|---|
| Official guard `test_weather_isolation` (4 tests), before and after | OK, OK. **Caveat unchanged:** the manifest is dirty (another session refreshed it for its own edits to 4 protected files), so this shows no change relative to that manifest, not relative to HEAD. Not touched; no file added to a protected folder |
| `git status`, tracked diff, `app.py` / spec / `settings.json` hashes, before vs after | identical |
| Off-mode snapshot (original fixture compiled twice, 571 protected-scope hashes, 1,331-file census, HEAD, `settings.json` hash) | identical in every field |
| Bytecode in `explainer/` | none |

## The app diff for your approval: [m4_app_patch.diff](m4_app_patch.diff) (not applied)
`git apply --check` passes on the current files; the patched `app.py` and spec parse; **79 added lines (73 in `app.py` in 3 hunks, 6 in the spec), 0 removed**, so the guard's "no line removed or changed" rule is respected by construction.
- `app.py` hunk 1 (`_build_hybrid_section`): `self._hybrid_explainer_var = ctk.BooleanVar(value=bool(self._settings.get("explainer_style", False)))`: the opt-in, **off unless the user turns it on**; the key is read with an inline default, so `settings.json` needs no change and gains the key only when the user flips the switch.
- hunk 2 (same method, a new row under the existing Hybrid buttons): a switch "Explainer look (board clips, narrator, captions)" and a button "Direct with Explainer" that is disabled while the switch is off.
- hunk 3 (after `_on_hybrid_auto_gfx_changed`): `_on_hybrid_explainer_changed` (stores the setting, enables or disables the button; changes nothing else) and `_hybrid_explainer_direct`, which mirrors `_hybrid_plan_with_ai`: voiceover and script, transcription through `_pakmap_get_words`, `explainer.integration.direct_plan(...)` on a worker thread, then `_hybrid_set_plan(plan, None)`. On any failure or withheld plan it logs, shows a message and **leaves the current plan untouched**. The explainer package is imported only inside the worker.
- Spec: `from explainer.packaging import data_files, python_modules`, `datas += ...`, `hiddenimports += ...` (same pattern as What If and Weather); it ships the 14 narrator layers and 5 font files (19 files) and 31 modules; Inter ships with the existing `assets/fonts` folder.
Not in the diff: per-project persistence (`project_workspace.py` is protected), any change to the render path, any UI outside the Hybrid block.
**Not verified:** that the patched app actually runs and shows the switch. I cannot run the GUI here, and a frozen build was not made. In a packaged app the narrator asset path relies on PyInstaller setting `__file__` under its bundle folder; untested.

## Limits and open issues (please read)
- **Quality of the authored content is weak, as the contact sheet shows.** The rule-based key phrases are fragments ("engineers measured", "almost", "go", "hand across"), boards are sparse, and repair cards sometimes carry words that mean little. The mechanics (timing, layout, gates, pacing numbers) are verified; whether it looks like a good explainer is not, and no reviewer ratings (M01, M03, M04) were collected. Better text needs a language model or a human-written plan loaded through the same gates (a prompt file and an optional AI step were left out of M4a). This is the largest gap.
- **Place detection** depends on the script's capitals and the offline lookup; without a script only the caller's list is used. A name spoken at the start of a sentence counts only if it is a country or region (so "Rome" at a sentence start is missed unless listed).
- **Hard cuts:** `dissolve_s` is plan-wide in Hybrid; the director defaults to 0 (the reference), so map and archive beats also cut. A dissolve setting is supported but changes every transition.
- Map beats use the engine's own look; camera framing is only warned about; the marker animation starts a few frames early (M3 finding); the narrator is never over a map (deferred).
- Real-voice word times, the 2-frame tail adjustment and Whisper accuracy remain untested and unresolved. Inter's licence text is unverified. **Cross-OS validation is not done:** there is no Windows or second-Mac run, and no cross-platform script yet (the M4c work).
- Clips are cached by content hash under the project folder; nothing prunes them.

## Next smallest step
Your decision on `m4_app_patch.diff` (apply as written, change it, or hold). If approved, M4b applies it and I verify what can be verified without the GUI (import, switch default, the patched file's guard result, the off path byte-identical); M4c would add the cross-OS script and a stronger content step.
