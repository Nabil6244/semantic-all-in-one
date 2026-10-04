# Hybrid Map: investigation and architecture proposal (no code written)

Status: proposal for review. Nothing has been changed in the repository for this document.

## 1. Answers to the ten questions (from reading the code, not assumed)

1. **How Fact Map ("Map Facts") represents its visual plan.** As the normal Visual Director plan: `visual_director.VisualPlan` / `VisualScene` (narration, visual_goal, asset_type, provider_preference, queries, fallbacks, duration), saved as `ai_visual_plan.json`, turned into `SceneRow`s by `to_scene_rows()`. A post-pass (`visual_director/map_pass.py`) turns qualifying scenes into `asset_type=map` rows (at most one per ~30 s, never two in a row). Each map row is an independent shot: `providers/map/provider.py` renders a ~12 s clip (`map_scene` + `map-engine`) into `NNN.mp4`, and `render_video` assembles the clips. There is no shared camera between map scenes.
2. **How PakMap represents its visual plan.** The AI writes a CSV; `pakmap/compile.py` compiles it with the narration's word times into one spec (events with `t_in`/`t_out`, one camera timeline) for `pakmap-engine`. Since Phase 8 the pictures in it are rows of the Visual Plan table (`SceneRow`s derived by `pakmap/sourcing.py`); map layers are not rows.
3. **How the Visual tab represents assets.** `app._scene_rows` (a list of `SceneRow`: scene number, text, `asset_type`, prompt) plus an `AssetManifest` (`.asset_manifest.json`) in one images folder; files are `00N.ext`; state is `AssetResult` per scene (`READY / NEEDS_ACTION / SKIPPED ...`), restored from the manifest on reopen.
4. **Stock / Flow / YouTube / Local.** By `asset_type`: `stock_image`, `stock_video`, `flow_image`/`flow_video` (stored as `image`/`video`), `youtube_video`, `local*`, `map`. `SceneAssetRouter.classify` maps a row to an `AssetSource`; `AssetManager` owns one provider per source.
5. **Replacement.** The table's Change source / Retry / Alternative / Skip / Local clip call `AssetManager.change_source`, `retry_scene`, `attach_manual_clip` ... on the folder `_scene_action_images_dir()` names. The result is a manifest record marked `user_override`, which `AssetManager._cache_hit` keeps on every later run unless the row's own prompt changed. Proven in Phase 8 with the real manager.
6. **Failures.** Providers return a FAILED/NEEDS_ACTION `AssetResult` with a reason (never a substitute asset). The table shows Needs action with the reason; Retry, Change source or Skip resolve it. Skip writes a placeholder; PakMap drops the layer.
7. **Persistence.** `ProjectWorkspace` (`project_workspace.py`): the plan JSON (`ai_visual_plan.json`), the per-mode CSV, per-mode settings in the project meta, and the asset manifest in the mode's images folder. Reopening a project restores all of it (`_bind_workspace_paths`).
8. **How the PakMap persistent camera works.** `lib/camera.mjs`: one timeline (`start` + moves + drift), evaluated per frame. Under a `media_full` event the camera cannot move (validated) and drift is frozen (`freeze` windows), so the camera state when footage ends is exactly the state when it began. Overlays are events with time windows; `media_full` dissolves in and out linearly over 0.5 s.
9. **What Hybrid can reuse.** Almost everything: the PakMap engine, camera, overlays, imagery, geo resolver, CSV compiler, narration anchoring (explicit `t_start`/`t_end` already win over anchors), Phase 8 sourcing and Visual Plan rows, the sound design (a `media_full` already gets a soft transition sound), export, project storage, `GeminiLLM` and the Visual Director's JSON-extract/revise pattern.
10. **Smallest safe integration point.** Hybrid is a new **editorial layer in front of the PakMap compiler**: a `HybridPlan` (beats) that compiles to the same PakMap rows/spec. No second map engine, no second asset system. Only three small, flag-gated additions to the PakMap engine (section 4).

## 2. Architecture

```text
script + timed narration (Whisper words -> sentences with start/end)
   -> Hybrid Visual Director (own prompt, Gemini via visual_director.llm)   hybrid/director.py
   -> HybridPlan = ordered beats (the editable source of truth, saved as JSON in the project)   hybrid/plan.py
   -> validation (deterministic: technical + editorial metrics)   hybrid/validate.py
   -> critic (second LLM pass, own rubric) -> repair of only the weak beats   hybrid/critic.py
   -> Visual Plan table (existing): one row per footage beat, replaceable with the existing actions
   -> compile: HybridPlan + chosen footage files -> PakMap rows with explicit times -> pakmap.compile -> spec   hybrid/compile.py
   -> pakmap-engine render (+ flag-gated Hybrid options) -> existing export / sound
```

New package `hybrid/` (plus `composition_styles/hybrid_director_prompt.txt` and `hybrid_critic_prompt.txt`). It imports `pakmap` and `visual_director.llm`; neither imports it. Fact Map and PakMap code paths are not edited.

### 2.1 The plan (beats, not rows)
A beat = a span of narration with one primary mode: `MAP`, `FOOTAGE` (or `MAP+FOOTAGE` where footage is an insert over a map beat, i.e. today's PakMap card). Fields: start/end (seconds, from the real narration), mode, one-line editorial purpose, narration text, and:
- MAP beat: camera target (place + frame, or lat/lon/zoom), overlays (markers, fills, lines, stats, dots, comparisons, with places by name), what state must persist.
- FOOTAGE beat: source (`stock_image/video`, `flow_image/video`, `youtube_video`, `local`), description/prompt, the editorial reason, optional extra clips for a long beat.
Times come from the narration; the AI never guesses them.

### 2.2 Map persistence across footage
- The camera already returns to the same state (frozen under footage).
- Overlay windows are narration time, so a marker with a 9 s default hold could expire while footage plays. The Hybrid compiler therefore extends every layer that is alive when footage starts to at least the footage end plus the return dissolve, and never replays its entrance animation. This is compile-time only.

### 2.3 Engine additions (flag-gated, additive, PakMap output byte-identical)
The three things PakMap's `media_full` does not do today:
1. **Footage owns the screen.** Today cards, stat chips, captions and the HUD draw above full-screen media. Hybrid footage needs them hidden (they come back with the map). New `media_full` option, default off.
2. **Footage to footage without a map flash.** A long footage beat usually needs several clips; consecutive `media_full` events dip back to the map between them, and overlapping ones are an error today. New option: consecutive clips cross-dissolve into each other.
3. **Clip shorter than the beat / stills.** A still or short clip should loop or slowly drift (the app's existing Ken Burns behaviour for stills) so footage does not freeze.
PakMap golden/determinism tests must stay green unchanged; that is the proof PakMap looks exactly as before.

### 2.4 Visual tab
Reuse the existing table, exactly as PakMap pictures do after Phase 8: every footage beat is a row (numbered, source badge, status, error, Retry / Change source / Skip / Local clip, replacement reaches the render). The row text carries the time and the editorial purpose.
Map beats are the open decision (section 5, D1).

### 2.5 Validation, critic, repair
- Technical (deterministic): unresolved places, invalid timing, overlapping incompatible layers, missing assets, malformed compiled events. Reuses the PakMap compiler/validator; errors are tied to the beat.
- Editorial (deterministic metrics, tunable): mode switches per minute; minimum beat length per mode; footage beat with no stated purpose; map run or footage run longer than N seconds without a visual change; repeated footage query; the same overlay pattern repeated; a sentence-per-visual pattern; stated places/numbers with no map beat.
- Critic (LLM, own rubric): geographic clarity, footage value, continuity, mode balance, variety, repetition, timing at natural narration boundaries.
- Repair loop: errors or weak beats go back to the Director **for those beats only** (with their neighbours as context); a bounded number of rounds; whatever remains is shown to the user, not hidden.

### 2.6 Persistence and the CSV
The HybridPlan JSON is the source of truth. The PakMap rows/CSV are compiler output written to the work folder for debugging. The user's picture choices live in the asset manifest (as in Phase 8). Reopening a project restores plan, table state and settings.

## 3. MVP scope (as requested)
Map (persistent camera, existing PakMap overlays, geographic anchoring) + footage (Stock, Flow, YouTube, Local) + map to fullscreen footage to map with dissolves and preserved state + AI plan + existing Visual tab + change source / retry + validation + compile + render. No new map layers.

Proposed order, each step tested before the next:
- **H1 Plan model + compile + engine options** (no AI): a hand-written HybridPlan compiles and renders with fake footage; PakMap goldens unchanged; map state before/after footage proven pixel-for-pixel.
- **H2 Timed narration + Director + deterministic validation + repair loop.**
- **H3 App integration:** third style switch, Visual tab rows, Check plan, generation, persistence.
- **H4 Critic pass + editorial metrics tuning** against reference-quality scripts.

## 4. Risks
- Quality depends on the Director's editorial judgement; the metrics and critic reduce but do not remove that. Needs real scripts and your review of results, not just passing tests.
- Gemini is the only LLM wired into the app today (Director and critic would both use it; each run costs API calls).
- Footage quality from stock/Flow/YouTube is outside our control; the table lets the user swap it.
- Footage has its own audio; the MVP renders footage silent (narration + pakMap sound design only).

## 5. Decisions needed before coding
- **D1. Map beats in the Visual tab.** (a) Footage rows only in the table, with all beats listed (read-only, with times) in the Hybrid plan panel: no change to shared code, same design as PakMap pictures; locations are edited in the panel. (b) Map beats also as table rows: needs an additive change to the shared asset layer (a new "geographic map" source that is ready without a file), because `asset_type=map` would route to the Fact Map renderer. Recommended: (a) for the MVP, (b) later if wanted.
- **D2. UI placement.** A third style switch next to pakMap and Overscaled (recommended) versus a style choice inside the pakMap block.
- **D3. Footage audio.** Muted in the MVP (recommended).
- **D4. Engine changes.** OK to add the three flag-gated options to `pakmap-engine`, guarded by the unchanged PakMap golden tests?
- **D5. LLM.** Gemini through the existing `visual_director.llm` for Director and critic (recommended), or a different provider.
- **D6. Name.** "Hybrid Map" in the UI and `hybrid/` in code.
