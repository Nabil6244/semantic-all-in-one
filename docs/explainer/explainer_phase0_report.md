# Explainer style: Phase 0 report

Date: 2026-10-22. Planning only. **No application code, settings, tests, assets or Git history were changed.** The only files created are the four documents listed in section 11.
Companion files: [style guide](explainer_style_guide.md), [scorecard](explainer_scorecard.md), [reference manifest](explainer_reference_manifest.json).

## 1. Executive summary

- The two references were available and inspected. Only **one 2-minute passage** (R2, 0:00 to 1:59.7, 24 shots) is shot-listed. The rest of both videos was reviewed only through coarse contact sheets, so whole-video claims are marked unknown.
- The first chat estimates were partly wrong. Measured in the 2-minute passage: shots average **5.0 s** (median 4.6 s), not 7 to 8 s; the narrator is absent for stretches of **17 and 26 s**, not "every 2 to 3 beats"; transitions seen at fine resolution are **hard cuts**; captions are **typed key phrases, not subtitles**. These changes are carried into the guide and scorecard (section 3).
- Hybrid is a front end on pakMap: `HybridPlan` → pakMap rows → `pakmap.compile` → `pakmap-engine`. That makes the "board" and "cartoon" beat types a change to the plan model, the compiler **and** the engine, not just to Hybrid.
- **Most files those changes touch are protected** by `test_fixtures/weather_protected.json` (hashes of `hybrid/`, `pakmap/`, `pakmap-engine/`, `composition_styles/`, `video_generator.py` and others; no new files allowed inside those folders). Any phase that edits them needs your explicit approval and a manifest refresh. This is the largest architectural constraint found and it decides how the phases are ordered.
- Word-level timing exists (`video_generator.py:304`, faster-whisper `word_timestamps=True`) and reaches the pakMap compiler as `(word, start, end)` tuples, where template cues are resolved. It is **baked into event times at compile time**; the engine never sees words. Per-word or per-character caption cues are therefore a compile-time feature, not a render-time one.
- Fonts: `ChalkboardSE.ttc` (an Apple font bundled in a Windows and macOS installer) is a licensing risk that should be confirmed independently of this project. Patrick Hand and Kalam are the candidates; neither licence was verified in this session.
- Recommendation: a decision on the architecture path (section 9) and a second reference segment before any code.

## 2. Reference access and analysis status

| Item | Status |
|---|---|
| R1 `/Users/muhammadnabil/Downloads/The-Entire-History-SnapYT.App.mp4`, 2127.6 s, 640×360, 30 fps, audio | Accessible. 12 contact sheets (15 s spacing), 2 close-up strips, full-length scene-change count (283 at threshold 0.3). A segment-level transcript exists in the scratchpad but was not used for timing. **No shot list.** |
| R2 `/Users/muhammadnabil/Downloads/Why-Did-the-SnapYT.App.mp4`, 2368.4 s, 640×360, 30 fps, audio | Accessible. 17 contact sheets (12 s spacing), 120 labelled frames at 1 fps over 0:00 to 2:00, fine strips at 10 fps (22 to 24 s) and 6.7 fps (62 to 65 s), scene-change list for 0 to 125 s (22 cuts), word-level transcript for 0 to 125 s (faster-whisper base), palette sampling. **Shot list for 0 to 119.7 s only.** |
| Audio other than the voice (music, effects, ambience) | **Not analysed.** |
| Channel, title, uploader | Only the file names are known. The on-screen title cards were not inspected. |
| Frames and audio actually viewed | Yes, as stated above. Nothing in this report assumes viewing beyond that. |

Measurement limits (stated, not hidden): 640×360 compression; boundaries ±0.5 s except where measured at fine resolution; narration times are Whisper's estimate (about ±0.3 s); change-event times are hand annotated.

### Selected two-minute passage

R2 0:00 to 1:59.7. Chosen because it contains the whole hook-to-thesis arc and uses all four layers (map, cartoon, board, archival), narrator placements on board and map, a reused cartoon set, split screen, a title with scale-in, typed phrases, counters, a changing date chip, crossing arrows, a scroll and paradox arrows. It ends on a detected hard cut, so it contains whole shots. It does **not** exercise two-character dialogue, dark silhouette scenes, chart types, or the signature metaphor (sticky note and scale, whale and shrimp). A second segment is needed for those (recommendation in section 10).

Headline measurements (details in the manifest):
- 24 shots; mean 4.99 s; median 4.6 s; range 2.2 to 11.4 s.
- Seconds by layer: cartoon 39.1, board 39.0, map 32.5, archival 9.2.
- Narrator on screen about 60 s of 119.7 (≈ 50%); longest absence 25.8 s; first absence 17.35 s.
- 22 detected cuts: 16 within 0.25 s of a sentence start, 17 with clause starts.
- 85 hand-annotated change events, median gap 1.0 s, longest 4.3 s; 58 of 60 two-second windows contain a change or cut.
- Cartoon to board at 23.05 s verified at 10 fps: a hard cut (the scene-change filter missed it, so whole-video counts of 283 and 318 are lower bounds).
- Title onset 63.05 s vs spoken word about 63.0 s; paired icon 0.2 s after its word; type-on of a 19-character phrase about 0.6 s; board cleared at the next sentence start (62.3 s).

## 3. Corrections to earlier estimates in this chat

| Earlier statement | What the measurement shows | Where it is reflected |
|---|---|---|
| New picture every 7 to 8 s | Shots average 5.0 s in the test passage; visible changes about once per second. 7.5 s was a detector artefact. | Guide section 8; scorecard T02, T03 |
| Narrator returns every 2 to 3 beats | Gaps of 17.35 s and 25.8 s occur | Guide section 4; scorecard T05 |
| Mostly dissolves unclear | Hard cut verified where checked | Guide section 8, 12 |
| Captions follow the voice word by word | Short key phrases typed per character; titles scale in; subtitle may finish with the sentence | Guide section 6; scorecard T08, T09 |
| Hybrid has a captions system per word | Per-word timing exists up to compile, not in the engine | Section 4 |
| Cartoon about 35%, board 25%, map 22% | In this passage 33 / 33 / 27 (archival 8); whole-video unknown | Manifest summary |
| "Recap every 8 minutes" | Not supported by anything measured | Scorecard (not made a rule) |

## 4. Repository findings (verified paths)

### 4.1 How Hybrid Map works end to end
- Plan model: [hybrid/plan.py](../../hybrid/plan.py): `MODES = ("map", "footage", "map_footage")` (line 26), `LAYER_TYPES` (29), dataclasses `Layer`, `CameraStep`, `Clip`, `Support`, `Beat`, `HybridPlan`, `validate_plan` (298), `asset_problem` (268; a local file path is accepted as an asset), `DEFAULT_SETTINGS` (34, includes `dissolve_s: 0.5`).
- Planning: [hybrid/director.py](../../hybrid/director.py) (`plan_beats`, `plan_chunk`, `repair_beats`, `derive_cameras`; prompts loaded by `load_prompt` from `composition_styles/`), [hybrid/pipeline.py](../../hybrid/pipeline.py) (`plan_hybrid`, chunked long-form `_plan_long`, per-chunk checkpoints `_save_checkpoint`, `repair_errors`), [hybrid/critic.py](../../hybrid/critic.py), [hybrid/validate.py](../../hybrid/validate.py), [hybrid/quality.py](../../hybrid/quality.py), [hybrid/narration.py](../../hybrid/narration.py) (`Word = Tuple[str, float, float]`, `build_sentences`, `plan_chunks`).
- Script and CSV schema: [hybrid/beat_csv.py](../../hybrid/beat_csv.py): `COLUMNS` (line 38) and a JSON `extra` cell where less common beat and layer fields live (`BEAT_EXTRA`). New fields can be added through `extra` without changing the column set. [hybrid/csv_import.py](../../hybrid/csv_import.py) reads the older pakMap-column format.
- Compile: [hybrid/compile.py](../../hybrid/compile.py): `plan_to_rows` (150) turns a plan into pakMap `Row`s with explicit times; `compile_plan` (406) calls `pakmap.compile.compile_rows`. [hybrid/generate.py](../../hybrid/generate.py) `generate_hybrid_video` writes `hybrid_plan.json` and `hybrid_script.csv`, then calls `generate_pakmap_video(..., whisper_words=words, spec_extra=...)`.
- pakMap schema and compiler: [pakmap/schema.py](../../pakmap/schema.py) `COLUMNS`/`Row`; [pakmap/compile.py](../../pakmap/compile.py) handles layer types including `template` (line 650), `sticker` (597, needs a transparent PNG), `caption` (536), and applies `doc_style` (356) and auto templates (368).
- Engine: [pakmap-engine/lib/draw.mjs](../../pakmap-engine/lib/draw.mjs) draws events (`drawCaption` at 252, layer order at about 393 to 400); [pakmap-engine/lib/hybrid.mjs](../../pakmap-engine/lib/hybrid.mjs) holds Hybrid options (`media_full`, `cover_ui`, `xfade_prev`, `pause_overlays`); `page.js` loads gfx-core templates through `createGfx, drawGfx` (line 13).
- Generate-then-Render split: committed in `c619e8b` ("Hybrid Map: Generate gets the scenes, Render draws"); test [test_hybrid_scenes_then_render.py](../../test_hybrid_scenes_then_render.py).

### 4.2 Graphics components
- gfx-core: 80 templates in `gfx-core/templates/{broadcast,editorial,facts,geo,news,stats,text}`; theme tokens in [gfx-core/lib/theme.mjs](../../gfx-core/lib/theme.mjs) with only two themes, `documentary` and `editorial`, both dark; fonts in `gfx-core/fonts` (Cormorant Garamond, OFL).
- whatif-engine: 96 templates across `blackhole, data, distance, forces, physics, scale, space, story, structure, survival, text, time`; about 45 science-themed icons in [whatif-engine/lib/icons.mjs](../../whatif-engine/lib/icons.mjs).
- Registry and placement: [gfx_templates.py](../../gfx_templates.py) (`load_library`, `find_cues` 236, `event_for` 247 with a `follow` argument, `over_footage_problem` 219, `auto_events`); allow-list [normal_gfx/allowlist.json](../../normal_gfx/allowlist.json); inventory in [docs/hybrid/template_inventory.md](../hybrid/template_inventory.md) (79 templates, 39 with an automatic placement rule). Templates in Hybrid footage beats must be drawn over footage; full-frame opaque cards are disabled by default for Normal Video.
- News Doc looks: [graphics/doc_looks.py](../../graphics/doc_looks.py), switch in [graphics/doc_style.py](../../graphics/doc_style.py).

### 4.3 Providers and assets
- Footage sources `stock_image, stock_video, flow_image, flow_video, youtube_video` (`hybrid/plan.py:27`), local files accepted. Archival images come through the same path (a Commons provider exists: `test_commons_provider.py`). `Clip.reason` records why each picture exists.
- The engine's `sticker` layer takes a transparent PNG; `pip` and `filmstrip` types also exist ([pakmap/pacing.py](../../pakmap/pacing.py) lists `PICTURE_TYPES`).
- Fonts: `assets/fonts` (13 files: ChalkboardSE, DMSans, Inter, Manrope, Outfit, PlusJakartaSans, SpaceGrotesk) has **no licence files**; `pakmap-engine/assets/fonts/README.txt` records Montserrat as OFL 1.1 with its source. The PyInstaller spec bundles `assets/fonts` ([VideoGenerator.spec](../../VideoGenerator.spec) around line 251).

### 4.4 Narration and audio timing
- Transcription: [video_generator.py:304](../../video_generator.py) `model.transcribe(source, word_timestamps=True, vad_filter=True)`.
- Hybrid passes the words on: `generate_hybrid_video(..., whisper_words=...)` → `generate_pakmap_video(..., whisper_words=words)`; Hybrid plans already carry explicit start and end times, so the words are used for cue lookups (`gfx_templates.find_cues`) and for the "stat" and auto-template placement. The engine receives event times, not words. **Verified for the code paths above; whether every Hybrid entry point supplies real words (not the placeholder `[("hybrid", 0.0, 0.1)]`) was not traced.**
- Captions today: Normal Video draws a scene caption ([normal_gfx/captions.py](../../normal_gfx/captions.py), `render_caption_overlay` in `video_generator.py:973`); pakMap/Hybrid have a `caption` layer and Doc Style turns captions into the typed-caption template.
- Sound design for Hybrid: [pakmap/audio_plan.py](../../pakmap/audio_plan.py), `audio_mix.py`, `sounds.py`.

### 4.5 Robustness mechanisms available to reuse
- Stall watchdog: [stall_guard.py](../../stall_guard.py) `StallWatchdog`, installed in `app.py` around line 16245.
- Per-scene recovery: [scene_recovery.py](../../scene_recovery.py) `SceneRecoveryTracker`.
- Render cache: [render_cache.py](../../render_cache.py) `RenderCache`, `build_scene_cache_key`.
- Never-stop guard for pakMap and Hybrid: [pakmap/guard.py](../../pakmap/guard.py) `dry_run`, `compile_guarded`, `heal_text`, `check_gfx`.
- Hybrid-side: checkpoints and chapter repair in `hybrid/pipeline.py`, `hybrid/local_fix.py`, `hybrid/cell_fix.py`.
- Frame QA: `visual_qa/frame_sampler.py`, `scene_qa.py`.

### 4.6 Opt-in switches and the UI
- Style picker: `STYLE_CHOICES` in [app.py:2979](../../app.py) lists nine styles including "Hybrid Map"; the styles are exclusive (`_hybrid_deactivate`, line 3355). The Hybrid block is built at about line 3441 and holds its own switch `hybrid_auto_templates`.
- Settings are stored in `settings.json`: `doc_style` (true on this Mac), `hybrid_auto_templates` (true), `normal_hybrid_style` (false), `caption_style` ("classic"). Per project notes, the Doc Style switch is Mac-wide, which already caused different output on two Macs, so an Explainer switch should be stored with the project or inside the Hybrid block and shown in the plan, not as another Mac-wide switch.
- CSV prompt per style: [app_csv_prompts.py](../../app_csv_prompts.py) maps `"hybrid"` to `hybrid_beats_prompt.txt` (and a graphics variant).

### 4.7 Tests and fixtures
- 20 Hybrid test files (`test_hybrid*.py`) plus `test_hybrid_app_plan.json` (a 24 s plan with three beats: map, footage, map_footage) and [hybrid_longform_fixtures.py](../../hybrid_longform_fixtures.py) (synthetic narration with word times and a stand-in LLM: no network, no credits).
- A regression harness that hashes rendered frames was **not found** in this search (not exhaustive). `test_preview_parity.py`, `test_perf_visual_qa.py` and `visual_qa/` exist and may be reusable.
- Protection guards: [test_weather_isolation.py](../../test_weather_isolation.py) with [test_fixtures/weather_protected.json](../../test_fixtures/weather_protected.json) (433 files, base commit `84700a7`) and an Enoch equivalent ([test_fixtures/enoch_template_protected.json](../../test_fixtures/enoch_template_protected.json), 235 files). Protected folders: `pakmap, pakmap-engine, hybrid, starmap, starmap-engine, map-engine, map_scene, composition_styles, providers, flow-engine`, plus `project_workspace.py`, `app_csv_prompts.py`, `asset_manager.py`, `video_generator.py`. Rules: protected files keep their hash; no new files inside protected folders; `app.py` and the spec may only gain lines. **I did not run these tests.**

## 5. Current capabilities vs missing

| Need | Exists | Gap |
|---|---|---|
| Map beats with fills, pins, lines, labels, chips | Yes (`hybrid/plan.py` layer types; engine) | Red X on route, faces on countries, block grid, weather overlay, globe-turn between beats |
| Footage and photo cards, archival with reason | Yes | Painting/engraving sourcing bias; edge-soften treatment |
| Data components (numbers, charts, gauge, donut, checklist, timeline) | Yes (gfx-core, whatif) | Grey/cream theme; handwritten font; the extra objects (scale, pyramid, calendar, crossing arrows, scroll, sticky note, puzzle, icon grid) |
| Full-frame board beat | **No** (only `map`, `footage`, `map_footage`) | New beat mode, plate and compile path |
| Narrator and any animated character | **No** | Whole asset and animation system |
| Icon library for history/economics | Partial (about 45 science icons in whatif) | A few hundred icons, packaged once |
| Per-character or per-word typed captions tied to speech | Partial: typed phrase template exists; word times reach compile; `find_cues` and `follow` exist | A cue-driven type-on that uses them |
| Structured story shape (hook, twist, reversal, aphorism), colour-role table, signature metaphor | **Not found** in the director code or prompts (read only `plan.py`, `director.py` signatures and the prompt loader; the prompt text itself was not read in full) | Director rules and plan fields |
| Opt-in switch that cannot affect other styles | Pattern exists (`doc_style`, `normal_hybrid_style`, `hybrid_auto_templates`) | Project-level storage; no Mac-wide side effect |
| Hard-cut transitions | **Unverified**: `TRANSITIONS = ("dissolve",)`; whether `dissolve_s = 0` gives a hard cut was not tested | Test in Phase 1 |

## 6. Font and narrator recommendations

Detail is in the [style guide](explainer_style_guide.md) sections 2 and 4. Summary:
- **Fonts.** Compare Patrick Hand, Kalam and two or three others by rendering 20 reference phrases at the output size next to a crop of the reference, then three reviewers rate. Both named fonts are believed to be OFL 1.1 (**not verified here**). Read each licence file from the downloaded package and store it beside the font, as `pakmap-engine/assets/fonts/README.txt` does. Do not choose ChalkboardSE. Confirm independently whether the existing bundled ChalkboardSE file may be redistributed.
- **Narrator.** Draw an original layered character (reference sheet, 6 to 8 pose layers, separate eyes and mouth layers, mouth driven by speech activity). Do not copy the reference's character. A licensed pack is acceptable only if its licence permits modification and redistribution in a paid desktop app; a generated-then-traced sheet carries the generator's terms and style drift. No art is created in Phase 0.

## 7. Scorecard summary and unresolved thresholds

26 checks: 8 hard gates (render completes, assets resolve, no blank frames, audio, **regression**, **no per-render asset creation**, legibility, never-stop), 13 weighted style targets, 5 human ratings. Three numbers reported separately; a gate failure is a FAIL whatever the style score. Full tables in the [scorecard](explainer_scorecard.md).

Unresolved (labelled provisional there): whole-video layer mix; recap and callback frequency; signature-metaphor recurrence; narrator mouth behaviour; latency windows (n = 3 and n = 1); phase score floors; the static-frame threshold.

## 8. Baseline and regression strategy

State of the working tree (no changes made by this task):
- Branch `master` at `42c4d17`. Modified and uncommitted from other work: `composition_styles/whatif_csv_prompt.txt`, `starmap-engine/page.js`, `starmap/cinema.py`, `test_fixtures/weather_protected.json`, `whatif-engine/layers/tm_theme.mjs`, `whatif-engine/lib/tpl.mjs`, `whatif-engine/page.js`, `whatif/compile.py`, `whatif/planner.py`. Untracked: `docs/terrain3d/`, `out/`, `test_whatif_variety.py`, `whatif/variety.py`. A second worktree exists at `.worktrees/upgrade` (branch `upgrade/overnight-2026-10-19`). None of these was touched. The new `docs/explainer/` directory is mine only.
- The modified `weather_protected.json` belongs to another session. Any Explainer phase that needs a manifest refresh must wait for it to be settled.

Baseline candidates (no render was started):
1. **`test_hybrid_app_plan.json`**: 24 s, three beats (map, footage, map_footage), already used by `test_hybrid_app_integration.py`. Best first baseline for H05 because it needs no network.
2. **`hybrid_longform_fixtures.make_narration`**: synthetic words with times and a stand-in director, for long-form behaviour without credits.
3. Real beat CSVs in `~/Downloads` (for example `bone_valley_hybrid_map_beats_v3.csv`, `Switzerland_Lakes_Graphics_Pass_Hybrid_Map_Beat_Plan.csv`, `Cornubian_Batholith_Hybrid_Map_Beat_Plan_v2.csv`) for a realistic render later. They need their voice-over and media to be reusable; whether those still exist was not checked.
- **No existing Hybrid baseline render was found** in the repository. `out/` holds Flow tests and StarMap Cinema clips (`cinema_1min*.mp4`), not Hybrid output. I did not search other folders for a render.

Procedure to prove "Explainer off = unchanged" **[proposal]**, in increasing cost:
1. **Plan and CSV level (free, offline).** Run `plan_to_rows` / `compile_plan` on the fixture, store SHA-256 of `hybrid_plan.json`, `hybrid_script.csv` and the compiled spec. Repeat after each phase with the switch off: must be byte-identical. `plan_to_rows` is a pure function of the plan, so this needs no render. (Not run in Phase 0.)
2. **Test level.** The 20 Hybrid test files plus `test_weather_isolation.py`; ask before running because the suite is long.
3. **Frame level (needs your approval).** One short render of the 24 s fixture with local media only, no Flow, no network, written to a new folder under the scratchpad or `out/explainer_baseline_<date>`; record frames at fixed times (for example 1, 6, 12, 18, 23 s) and compare hashes after each phase. Capture the log and output settings with it.
4. Keep the baseline artefacts in a folder that no phase writes to.

Do not claim the baseline passes until steps 1 to 3 have actually been run and inspected.

## 9. Architecture recommendations for Phases 1 to 8

### 9.1 The constraint that shapes everything
New beat types need changes in `hybrid/plan.py`, `hybrid/beat_csv.py`, `hybrid/compile.py`, `pakmap/schema.py`, `pakmap/compile.py` and `pakmap-engine/lib/draw.mjs` (all protected), plus prompts in `composition_styles/` and a key in `app_csv_prompts.py` (also protected). The protection test forbids new files inside those folders and changes to existing ones unless the manifest is refreshed by you.

### 9.2 Two paths (decision needed)
| | A: sibling package and engine, Hybrid unchanged | B: extend Hybrid, pakMap and the engine in place |
|---|---|---|
| How | New top-level `explainer/` (Python) and `explainer-engine/` (Node page, like `whatif-engine`, `starmap-engine`, `weather-engine`). Board and cartoon beats are rendered by the new engine into clips and enter Hybrid as **footage beats using local file paths**, which `asset_problem` already accepts. | Add modes, layer types, engine drawing and director rules directly. |
| Protected files | Untouched; `app.py` and the spec get added lines only | Many edited; manifest refresh needed each phase |
| Map overlays on the narrator, captions on maps | Hard: the map is drawn in the pakMap engine. Possible only via the existing `sticker` or `pip` layers (static PNGs) or a later approved engine hook. **Unverified.** | Direct |
| Regression risk (H05) | Lowest | Highest |
| Matches the repository's pattern | Yes: every other style has its own engine folder | No |
| Hard-cut transitions | Depends on `dissolve_s = 0` behaviour; **unverified** | Direct |

Recommendation: **start with A** and treat B as a small, approved set of hooks added only where A cannot reach (narrator over the map; per-word captions on the map). A Phase 1 spike (see 9.4) tests A on one board beat before anything is committed to.

### 9.3 Proposed structured beat representation
Do not add a database or a parallel planner. Extend the existing plan: new beat modes `board` and `cartoon`, and put the new fields in the existing extension points (`Layer.params`, the beat CSV `extra` cell). Proposal:

```json
{
  "id": "b12",
  "mode": "board",
  "start": 58.0, "end": 67.7,
  "narration": "…", "purpose": "one-idea sentence",
  "explainer": {
    "idea": "poverty, inflation, crime -> but the twist",
    "narrator": {"asset": "narr_v1", "side": "left", "scale": 0.5, "pose": "point_right", "enter": "slide", "exit": "none"},
    "set": {"id": null, "time_of_day": null, "props": []},
    "objects": [{"id": "ico_house", "text": "poverty", "role": "red", "cue_word": "poverty", "at": null, "pop": "scale"}],
    "captions": [{"text": "THE TWIST", "style": "display", "cue_word": "twist", "type_cps": null},
                 {"text": "almost nobody knows", "style": "typed", "cue_word": "almost", "finish_with": "sentence_end", "type_cps": 30}],
    "clear_at": "next_sentence",
    "continuity": {"roles": {"north": "blue", "south": "gold"}, "metaphor_ref": null, "reuses": ["set:desert_town"]},
    "fallback": ["board", "map"]
  }
}
```
Narration interval is the existing `start`/`end`; caption cue times are resolved at compile time from the word list by the existing cue mechanism (`find_cues`), then written as event times. Asset ids refer to a packaged library index that records licence and source.

### 9.4 Phases, dependencies and risk
Order is set by dependencies, not by size. Every phase ends with a short test render and a scorecard result (your rule, kept).

| Phase | Depends on | Main risk | Protected files touched (path A / path B) |
|---|---|---|---|
| 0 Approve guide, scorecard, manifest | nothing | thresholds are provisional | none / none |
| 1 Board foundation (beat mode, plate, theme, handwritten font, restyled templates) + **spike**: one board clip rendered through the footage path, regression check, hard-cut test | 0, font choice | `dissolve_s=0` may not give a hard cut; theme work duplicates gfx-core | none (A) / plan, compile, engine (B) |
| 2 Narrator (art, rig, placement) | 0, narrator decision, **interface freeze** of the asset index and beat schema | art quality; mouth driven by speech activity | none |
| 3 Board components + icon pack | 1 | icon licensing; sourcing time | none |
| 4 Map and archival additions | 1; likely path B hooks | engine edits are protected | engine, compile (B only) |
| 5 Word-timed captions | 1; cue mechanism | needs compile-time cues; map captions need B | `pakmap/compile.py` (B only) |
| 6 Director (hook, twist, recap, callback, colour roles, metaphor schedule, narrator interval) | 1 (schema), 3 (objects), 5 | prompts live in protected `composition_styles/`; new style key in `app_csv_prompts.py` | new prompt files in `explainer/` need a loader hook (A needs one added line in `app.py` / a new loader) |
| 7 Cartoon kit (sets, cast, props, `cartoon` mode) | 1; art can start earlier | largest asset effort; consistency | none (A) |
| 8 Hardening, UI switch, regression, 10 topics | all | `app.py` additions only | `app.py`, spec: added lines only |

### 9.5 Parallel work and file ownership (for future agents)
Parallel only after the **interface freeze** (beat schema, asset id and licence index, scorecard harness entry points). Until then work is serial.

| Stream | Owns (new files) | May not touch |
|---|---|---|
| Schema and director | `explainer/plan_ext.py`, `explainer/director*.py`, `explainer/prompts/` | any protected file |
| Board engine and theme | `explainer-engine/`, `explainer/board/` | gfx-core (copy, do not edit) |
| Narrator | `explainer/assets/narrator/`, `explainer/narrator/` | everything else |
| Icons and components | `explainer/assets/icons/`, `explainer/components/` | narrator and engine |
| Cartoon kit | `explainer/assets/sets/`, `explainer/assets/cast/` | engine |
| Scorecard harness | `explainer/qa/`, `docs/explainer/` | renderers |
| UI and wiring | added lines in `app.py`, `VideoGenerator.spec` | all else (Weather guard: no line removed or changed) |
Serial (one writer at a time, needs approval): any protected file; `settings.json`; the manifests.

## 10. Risks, assumptions, open questions

Risks
1. **Protection guard.** Any edit to a protected file fails `test_weather_isolation.py` until you approve a manifest refresh; another session currently has an uncommitted edit to that manifest.
2. **Licensing.** `ChalkboardSE.ttc` is shipped in installers; no licence files for the other bundled fonts; the new font, icon and character licences must be recorded per asset.
3. **Thin evidence.** One 2-minute segment, 640×360, hand-annotated. Several thresholds are provisional.
4. **Character originality.** A copy of the reference's narrator would be a likeness problem; keep the function, change the design.
5. **Engine reach (path A).** A narrator over the map and captions over the map cannot be done from outside the pakMap engine without an approved hook.
6. **Cartoon kit scale.** The largest asset cost; not required for Phases 1 to 6.
7. **Two-Mac drift.** Mac-wide switches already caused different output on two Macs; the Explainer switch should be stored with the project.

Assumptions: path A's footage-clip route works (not tested); word timestamps reach every Hybrid entry (not traced); the two named fonts are OFL (not verified).

Unanswered questions
1. Are you willing to approve manifest refreshes later (path B), or must the Explainer stay out of protected files?
2. Who draws or commissions the narrator and cast, and what is the budget for it?
3. Should the Explainer be a separate style card (like StarMap) or a switch inside the Hybrid block?
4. Which second reference segment? Recommendation: R2 about 38 to 41 minutes or a stretch containing the sticky note and scale, a chart, and a two-character dialogue.
5. Is hard-cut-only acceptable for board and cartoon beats?

## 11. Files created and confirmation

Created (new directory `docs/explainer/`, nothing overwritten):
1. `docs/explainer/explainer_style_guide.md`
2. `docs/explainer/explainer_scorecard.md`
3. `docs/explainer/explainer_reference_manifest.json` (parsed as valid JSON)
4. `docs/explainer/explainer_phase0_report.md` (this file)

Temporary analysis files (frames, contact sheets, transcripts) are in the session scratchpad, outside the repository.

Confirmation: **no application source, test, setting, asset, UI, dependency, branch or commit was changed.** `git status` shows only `?? docs/explainer/` as new from this task; the other modified and untracked paths listed in section 8 were already there. Nothing was staged, committed or pushed. No render, test suite or external generation was started.
