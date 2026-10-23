# Explainer Path A spike: report

Date: 2026-10-22. Scope: the isolated feasibility spike only. Phase 1 has **not** been started.
Evidence files are in [spike_evidence/](spike_evidence/). Spike scripts are in [explainer/spike/](../../explainer/spike/).

## Results

| # | Question | Result |
|---|---|---|
| Q1 | Can a clip made outside Hybrid enter a Hybrid plan as a local-file footage beat and render in the right place and time, with protected files untouched? | **PASS** |
| Q2 | Can that join be a hard cut instead of a dissolve? | **PASS**, with one limit: the switch is a plan-wide setting |
| Q3 | Is the existing (off-mode) Hybrid behaviour unchanged by the spike? | **PASS, scoped.** It proves the existing path is unchanged. It does **not** prove a future Explainer switch is safe, because no such switch exists to exercise (see Q3) |

## Method in one paragraph

The original fixture [test_hybrid_app_plan.json](../../test_hybrid_app_plan.json) (24 s: map, footage, map+footage) names network picture sources, so a derived copy was made in scratch with local files only. The footage beat (b2, 9 to 17 s) holds one placeholder board clip made by [make_board_clip.py](../../explainer/spike/make_board_clip.py): 1920×1080, 30 fps, a grey board, a typed label, icon pops, and on every frame a 16-bit frame number in the top-left corner plus a red border at the exact frame edges, so any shift, skip, crop or scale shows up in the render. The plan was rendered through the **unmodified** `hybrid.generate.generate_hybrid_video`, with the offline switch the repository's own tests use (`imagery=False`, passed through the `render=` argument that `generate_pakmap_video` already accepts; nothing monkeypatched). The narration is a synthetic 24 s tone with a click at every whole second. Sound design was off so the narration is the only audio. Three renders:

| Variant | `dissolve_s` | Footage beat holds | Purpose |
|---|---|---|---|
| A | 0.5 (the fixture's own) | board clip, 8.5 s (slot plus dissolve padding) | what Hybrid does by default |
| B | 0 | board clip, 8.0 s | the hard-cut question |
| C | 0 | plain flat-blue local clip | control: is the behaviour the board clip's or the pipeline's? |

Everything was local: no network, no Flow, no external generation, no commits, no test suites. The only network use in this render path is NASA imagery (`pakmap-engine/lib/imagery.mjs`), which `imagery=False` disables. The log reports 0 tiles requested or failed. I did not capture packets, so "no network use" rests on that switch and the log.

## Q1: board clip as a local footage beat: PASS

- `validate_plan` returned no problems; the plan compiled; all three renders finished (about 19 s each at 1080p).
- Output (all three): **1920×1080, 30 fps, 720 frames, 24.000 s**, H.264 video plus AAC 48 kHz mono audio of 24.000 s.
- Variant B, frame by frame (from [analysis_B.json](spike_evidence/analysis_B.json)):
  - map frames 0 to 269, **board frames 270 to 509** (9.0000 s to 17.0000 s), map again from frame 510;
  - board frame numbers read back 0 to 239 with every step exactly +1: nothing skipped, repeated, slowed or sped up; the clip plays at 1:1 for exactly its 240 frames;
  - the red border box in the rendered frames equals the source's (rows 21 to 1079, columns 0 to 1919) for the first, second, middle and last board frames: no crop, no scale, no offset;
  - mean absolute RGB difference between rendered and source frames of the same number: 0.11 (first frame) to 0.24 (last), p99 ≤ 6: this is the H.264 re-encode, not a transform;
  - interior grey and border colours are constant across the whole board run (interior exactly 192/192/192, border 222/0/0): no fade.
- The map HUD title chip is hidden under the board, as for any footage (`cover_ui` is on by default); the map beat resumes unchanged.
- Variant A: the same clip plays at 1:1 too (steps +1), see Q2 for its timing.
- Protected files: none edited (Q3).

## Q2: hard cut: PASS, one limit

Evidence: [joins_B.jpg](spike_evidence/joins_B.jpg) shows frames around each join, and [joins_A.jpg](spike_evidence/joins_A.jpg) the same for the default.

**With `dissolve_s = 0` (variant B)** the join is a hard cut at both ends:
- frame 269 (8.9667 s) is the map, frame 270 (9.0000 s) is board frame 0, with no intermediate frame;
- frame 509 (16.9667 s) is board frame 239, frame 510 (17.0000 s) is the map;
- the control (variant C, a plain blue clip) hard-cuts at the same frames: pixel probe at (1700, 300) reads map green (59, 94, 58) in frames 268 and 269, flat clip blue (46, 97, 157) in frames 270 to 272 and 507 to 509, map green again from 510. So the hard cut belongs to the pipeline setting, not to the board clip.

**With the fixture's default `dissolve_s = 0.5` (variant A)** the join is a centred dissolve and it shifts the clip in time:
- blend frames 264 to 276 (8.80 s to 9.23 s) at the start and 504 to 516 (16.80 s to 17.23 s) at the end;
- the first pure board frame is video frame 277 (9.2333 s) and it shows clip frame 14, so the clip started playing at video frame 263 (about 8.77 s, 0.23 s before the beat start); the last pure board frame is 503 (clip frame 240);
- consequence: with a dissolve the clip must be `beat length + dissolve_s` long (8.5 s here) and its first and last ~0.25 s are partly hidden. With an exact 8.0 s clip the engine would use its `fit: slow` behaviour; **that case was not tested**.

**Limit.** `dissolve_s` is one setting for the whole plan (`HybridPlan.settings`, `hybrid/plan.py:34`). It also governs map-to-footage and clip-to-clip joins everywhere in that plan. `TRANSITIONS = ("dissolve",)` is the only declared transition and I found no per-beat hard-cut control. So an Explainer plan that wants hard cuts around board beats and a dissolve around real footage would need either a plan-wide `0` (everything cuts) or a change in protected code.

## Q3: off-mode unchanged: PASS, scoped

What exists: there is **no Explainer switch, setting or mode** (none was added: `app.py` and `settings.json` are unmodified). So "off" means "the existing Hybrid path". That path is what was tested; a future switch cannot be tested yet.

What was compared (script [offmode_snapshot.py](../../explainer/spike/offmode_snapshot.py); run before the spike's render work, and after; output files are byte-identical, SHA-256 of both `b7082dcf9ff861766cd9…`):

| Item | Before | After | Same |
|---|---|---|---|
| HEAD | `42c4d17b0b999faad4255d79717cf2df8822ae90` | same | yes |
| Fixture `test_hybrid_app_plan.json` SHA-256 | `22e3050c673251520fe479b42012a2e93a0e4808ddf0af2ad56def607a410103` | same | yes |
| Compiled plan (`plan.to_dict()`) | `af18e83be103debd…` | same | yes |
| Compiled rows CSV (10 rows) | `7e978d52b4dd3751…` | same | yes |
| Row-to-beat line map | `0e710f1ac5d131ac…` | same | yes |
| Compiled pakMap spec (7 events: fill, hud_title, marker, media_full, pip) | `ecf4b524b47307e8…` | same | yes |
| Compile determinism (control: compiled twice each time) | deterministic | deterministic | yes |
| `DEFAULT_SETTINGS`, `MODES`, `LAYER_TYPES`, `TRANSITIONS`, `SOURCES` | recorded | same | yes |
| `settings.json`, `app.py`, `VideoGenerator.spec` SHA-256 | recorded | same | yes |
| 571 files in the protected scope (all tracked files in `hybrid`, `pakmap`, `pakmap-engine`, `composition_styles`, `map_scene`, `map-engine`, `providers`, `flow-engine`, `starmap`, `starmap-engine`, `gfx-core`, `gfx-overlay-engine`, `graphics`, `normal_gfx`, plus the root protected files, `gfx_templates.py`, the fixture and both manifests) | hashes recorded | no file changed | yes |
| Files inside protected folders (1,331) | listed | same list; none added or removed | yes |
| `weather_protected.json` manifest vs. its 433 files (my read-only check that mirrors the guard's hash test) | 0 mismatches | 0 mismatches | yes |
| `git status` | see below | identical | yes |

Pre-existing uncommitted work (from other sessions) was present at the start and is unchanged: `composition_styles/starmap_beats_prompt.txt`, `composition_styles/whatif_csv_prompt.txt`, `starmap-engine/page.js`, `starmap/cinema.py`, `test_fixtures/weather_protected.json`, `whatif-engine/layers/tm_theme.mjs`, `whatif-engine/lib/tpl.mjs`, `whatif-engine/page.js`, `whatif/compile.py`, `whatif/planner.py`; untracked `docs/terrain3d/`, `out/`, `test_whatif_variety.py`, `whatif/variety.py`. New from this spike: `explainer/` and `docs/explainer/` only. No `__pycache__` or `.pyc` was created (everything ran with `-B -I`).

What this does and does not prove:
- It shows the unmodified fixture compiles to the same plan, rows and spec before and after, that the spike's files changed no protected file or setting, and that nothing was added to a protected folder.
- It does **not** run the existing test files (not allowed in this spike) or the Weather isolation test itself; I only mirrored its hash comparison.
- It does **not** prove that a future Explainer switch leaves Hybrid unchanged. That needs a switch to exist, and adding one touches `app.py` (added lines only) and an Explainer entry point; it should be tested then with the same snapshot.
- The original fixture itself was only **compiled**, not rendered, because it names network pictures. Its rendered equivalent is the derived local plan, and variant C is the control for that.

## Audio continuity

Same for all three variants (the audio passes through unchanged):

| Measure | Result |
|---|---|
| Output audio duration vs input | 24.000 s vs 24.000 s |
| Clicks found (one per whole second) | 24 of 24 |
| Click timing offset, output minus input | mean +0.05 ms, std 0.28 ms, range −0.04 to +1.37 ms |
| Steady tone level (min over median of 20 ms windows) | 0.991 (input 0.992) |
| Silent windows (< 0.2× median) | 0 |

So the board clip's 8 s span, the joins and the AAC re-encode introduced no gap, shift or drop. (This audio is a synthetic test signal, not speech, and sound design was off. Interaction with the sound-design mixer was not tested.)

## Files created

Inside the repository (new files only, nothing overwritten):
- `explainer/spike/README.md`
- `explainer/spike/offmode_snapshot.py`
- `explainer/spike/make_board_clip.py`
- `explainer/spike/make_audio.py`
- `explainer/spike/run_spike.py`
- `explainer/spike/analyze.py`
- `docs/explainer/explainer_spike_report.md` (this file)
- `docs/explainer/spike_evidence/`: `joins_A.jpg`, `joins_B.jpg`, `analysis_A.json`, `analysis_B.json`, `analysis_C.json`, `render_result_{A,B,C}.json`, `render_log_{A,B,C}.txt`, `derived_plan_B.json`, `offmode_before.json`, `offmode_after.json`, `guard_before.json`, `guard_after.json`, `git_status_before_preedit.txt`, `git_status_after.txt`, `sha256_scope_before_preedit.txt`

Outside the repository (session scratchpad, not user data): the renders, the clips and the synthetic audio under `…/scratchpad/explainer_spike/`. Render hashes: A `3e11c0555eaf…`, B `7e7166f61cc9…`, C `4d84abdc39d3…`; board clips `board_8.0.mp4` `c6a18310a57f…`, `board_8.5.mp4` `861016cfc64e…`; `voice.wav` `4f4e741dc4555…`. The scratchpad and output paths did not exist beforehand. The pakMap tile cache was redirected into the scratchpad (`VIDEOGEN_PAKMAP_CACHE`); `~/Library/Caches/SemanticYTStudio` was not modified.

**Protected files: untouched.** No file in the 571-file protected scope changed, none was added to a protected folder, `app.py`, `settings.json`, the spec and both manifests are unmodified, nothing was staged, committed or pushed, and no test suite was run.

## Remaining integration limitations

1. **Narrator or captions over a map beat are not covered.** A board beat replaces the whole frame, so it works. The reference also shows the narrator at the edge of map shots and captions typed over maps; the map is drawn inside the protected pakMap engine. The existing `sticker` (static transparent PNG) and `pip` layers might carry a narrator, but an animated narrator over a map was **not tested**.
2. **Hard cut is plan-wide** (Q2 limit).
3. **Dissolve mode shifts clip time** by about 0.23 s at each end and needs a clip longer than the beat (Q2).
4. **Cues are baked at compile time.** A board clip is a finished video, so its typed text and object pops are timed inside the clip, not against the spoken word at render time. For word-synchronised board content the Explainer engine must receive the word times itself (the Hybrid compile only passes event times to the engine).
5. **The fixture's `fit: slow`, `loop`, and Ken Burns behaviours** were not exercised on the board clip (Ken Burns did not alter the frames; the others were not triggered).
6. **Audio mixing:** sound design was off. Whether the narration/effects mixer treats a board beat like footage is untested.
7. **The Weather isolation test** (`test_weather_isolation.py`) was not run; only its hash rule was mirrored. Its "no new file in a protected folder" rule is satisfied by the file census.
8. **Scale:** 24 s, one board beat. Long-form behaviour, many board beats, and render time per board beat are unknown.
9. **Placeholder content only.** No narrator, no real board design, no font, no template restyle, no UI: all deliberately out of scope.

## Smallest safe next step

A board clip needs no change to Hybrid or any protected file to enter a render, and a hard cut needs only `dissolve_s = 0` in the plan. The smallest next step that builds on that, and stays inside the approved directories, is:

> In `explainer/` only, write a **script-driven board-clip builder that is timed from the narration's word times**: given a short list of cues (a typed phrase starting on word N, an object popping on word M, board cleared at the next sentence start), it renders one grey-board clip of exactly the beat's length (plus `dissolve_s` if one is used) and returns a plan fragment that inserts it as a footage beat. Test it on the 24 s fixture with the same frame-number check, and add a cue-latency measurement (cue time in the clip against the word time) so the scorecard's T08 can be computed. No narrator art, no font decision, no UI.

I have not started it and will not without your authorization.
