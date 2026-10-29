# Story pipeline and quality gates (Agent E)

Files: `story_pipeline.py` (orchestration + render hook), `story_audit.py` (gates), `test_story_pipeline.py`, `test_story_audit.py`.
Everything is OFF unless `settings.json` has `"story_video": true`. `video_generator.py` is not touched. No Flow, no network, no Whisper here.

## Data flow

```
inputs  CSV rows + Whisper words (cached or passed in)  ->  settings["rows"/"words"/"aligned"] win over files found in the project folder
  A  align      story_align.align_story(rows, words)                   -> aligned (start_time/end_time), audio_end, report
  B  shots      shot_director.plan_shots(scenes, words, settings, log)  -> {"protagonist", "shots", "stats"}; shots tiled 0..audio_end (tile_shots)
  C  generate   story_character.plan_generation(shots, protagonist, budget, done_shot_ids)   DRY RUN ONLY (counts, no pictures made)
  D  clips      story_motion.plan_clips(shots, images, settings)       -> jobs (always)
                story_motion.render_clips(jobs, out_dir, ...)          -> {shot_id|"<id>+link": mp4}   (only dry_run=False; local CPU, free)
                story_motion.assemble_timeline(shots, clips, settings) -> frame-exact segments (shot / link / graphic / gap), clip_in for shots after a link
  E  audit      story_audit.audit_all(plan=..., aligned=..., words=...) on the plan; on the rendered mp4 after the render (see below)
```

Every step is cached in `<project>/state/story/<step>.json`, keyed by a hash of its inputs and of the module file (size+mtime); a second run says
`cached` for everything unchanged (resume after a crash or Stop: finished steps and finished clips are not redone). `cancel()` is polled between steps and
inside `render_clips`; the run comes back with `run.cancelled = True`. A missing or failing module turns its step into `skipped`/`failed` plus a line in
`run.risks`; `build_story` never raises. Missing `shot_director` -> one shot per scene -> `run.usable()` is False -> the render is exactly the old one.

`StoryRun.report()` prints: step table, shot count/length/tiers, "would generate" (new pictures, character references, Flow runs, agent requests, clip
jobs by type, local render time from story_motion's own `est_seconds`, AI video jobs with seconds), the plan audit and the risks.

## What render_video keys by scene, and what is remapped (precise)

`render_video` makes clip i from `aligned_rows[i]`; the window is `[start_time_i, start_time_{i+1})` (row 0 from 0, the last to `audio_end`), the
picture is `find_image_for_scene(images_dir, row["scene_number"])` (int(); image or mp4), the audio is muxed whole, so sync is only the sum of
durations. `applied_story` wraps `vg.render_video` (one wrapper, restored on exit) and rewrites its arguments from the ORIGINAL call, so app.py keeps
its call unchanged. Unit = one timeline segment (a shot's clip or a link clip), or one shot when no clips exist yet. Synthetic `scene_number` =
`100000 + index + 1` (integer, cannot collide with a real scene).

| render_video input | keyed by | what is done |
|---|---|---|
| `aligned_rows` | position, `scene_number`, `start_time`, `script_segment` | one row per unit, contiguous from 0 to `audio_end` (`build_units`); `script_segment` = the shot's own phrase, so captions follow the shot; a link unit keeps the text of the shot it leaves |
| `find_image_for_scene` (also used by `missing_images_for_scenes`) | `int(scene_number)` | patched: synthetic number -> clip, else the shot's picture, else its scene's picture; real numbers -> the previous finder |
| clip playback of a segment with `clip_in > 0` | - | `render_video` always plays a clip from frame 0, so the segment is played from a trimmed copy in `state/story/trims/` (re-encode crf 12, cached) |
| `scene_text_effects` | list index = row index; each fx has absolute `start/end`, `local_start/end`, `scene_number` | re-assigned to the unit containing the effect's start, `local_*` rebased, cut at the unit end (`expand_text_effects`) |
| `transition_by_scene` | `str(scene_number)` | the scene's style goes to its first non-link unit; other units use the shot's `transition_in` mapped to a style (`TRANSITION_STYLE`: dissolve/fade/soft/flash/zoom_blur; cut and match_cut = hard cut); a link unit and the unit after it get none (the link is the transition). `visual_transitions` is recomputed |
| `camera_by_scene` | `str(scene_number)` | each unit gets the shot's `camera`, else its scene's |
| `edit_decisions_by_scene` | `str(scene_number)`, scene-local times | B-roll entries re-assigned by absolute time and rebased; MULTI_SHOT/strategy decisions are DROPPED (the shots are the editing); every unit that plays a clip gets `{"strategy": "HOLD_TAIL"}` so a short clip freezes instead of looping |
| `editorial_timeline` (graphics) | absolute time | unchanged (overlap test by time; a graphic across two units is drawn in both) |
| `.asset_manifest.json` coverage flags | real scene number | never match a synthetic number (no accidental `avoid_blind_loop`) |
| render cache | `sn_key` + file content + window + overlays | works per unit; only changed units re-render |
| `real_transition_into_scene` (xfade) | edit_decision shots | not used: transitions stay duration-preserving fades (xfade would re-encode the whole video) |

Gaps (not remapped, by design or not yet): the production graph/plan and progress counts (`clips_total`) still count scenes; the Hybrid sound hook's
`_starts` / `_by_idx` stay the ORIGINAL scenes' absolute times (valid, but the sound design does not know the shot cuts); `scene_text_fx` computed from
scenes is re-sliced by time only (an effect that straddles two units keeps its start unit); a `HOLD_TAIL` freeze of a too-short clip shows as a
still stretch in the audit (that is the point of the audit); Ken Burns on shots that have no clip is the app's (`zoom=True`), same as before.
The unit rows carry `_shot_id`/`_parent_scene`, which render_video ignores.

## Exact additive lines for app.py / ui (not applied; yours to integrate)

1. Setting: `settings.json` key `"story_video"` (bool, default False). Optional: `"story_dry_run"` (default True: plan only), `"story_budget": {"max_images": N}`,
   `"story_pictures": {shot_id: path}` (or put images in `<project>/state/story/pictures/<shot_id>.png`), `story_shot_*` (passed to shot_director with the
   prefix removed, e.g. `story_shot_seed`, `story_shot_target_len`), `story_motion_*` (to story_motion: intensity, link_seconds, time_budget_s ...), `story_workers`.
2. app.py, next to `_set_puppet_stills` (about line 11474):
```python
    def _set_story_video(self, on: bool) -> None:
        """The "Story Video (shots, links, motion)" switch (Audio & Effects > Smart editing, settings.json "story_video", off by default): story_pipeline.py."""
        self._settings["story_video"] = bool(on)
        save_settings(self._settings)
```
3. ui/views.py, right after the `_puppet_var` block (about line 1906), same pattern:
```python
        self._story_var = ctk.BooleanVar(value=bool(getattr(app, "_settings", {}).get("story_video", False)))
        _feature("Story Video (shots, links, motion)",
                 "Splits each scene into short shots that follow the narration, moves every picture, and joins pictures with walk-through / match-cut links. "
                 "Replaces the Paper-Cutout switch while on. Off by default; any failure leaves the normal video.",
                 self._story_var, on_toggle=lambda on: app._set_story_video(on) if hasattr(app, "_set_story_video") else None)
```
4. app.py, just BEFORE alignment (line ~15146 `aligned, audio_end = vg.align_rows(...)`): optional but recommended, so the app's `aligned` is Agent A's:
```python
            _story_align_cm = None
            if self._settings.get("story_video"):
                try:
                    import story_align as _story_align
                    _story_align_cm = _story_align.applied(vg)
                    _story_align_cm.__enter__()
                except Exception as exc:
                    print(f"[STORY] story_align unavailable ({exc})")
            aligned, audio_end = vg.align_rows(config["rows"], whisper_words)
            if _story_align_cm is not None:
                _story_align_cm.__exit__(None, None, None)
```
   (or push `_story_align_cm` into an ExitStack). Without it the pipeline still works: pass `aligned` (step 5) and shots follow the app's alignment.
5. app.py, in the hook block next to the puppet one, right before `_render_job = ledger.create("render"...)` (line ~15544), AFTER the puppet block so story wins:
```python
            try:   # story video: shots + links + motion; off unless settings.json "story_video" is true; a failure leaves the normal render
                if self._settings.get("story_video"):
                    import story_pipeline as _story_pipeline

                    _story_run = _story_pipeline.build_story(
                        Path(state_dir).parent,
                        {**self._settings, "rows": config["rows"], "words": whisper_words, "aligned": aligned, "audio_end": float(audio_end),
                         "images_dir": str(config["images_dir"]), "audio_path": str(config["audio_path"]),
                         "resolution": config.get("resolution") or "1920x1080"},
                        log=print, cancel=None,        # pass the app's Stop test here, e.g. lambda: self._overscaled_cancel.is_set() or the pipeline's own flag
                        dry_run=bool(self._settings.get("story_dry_run", True)))
                    _hybrid_stack.enter_context(_story_pipeline.applied_story(vg, _story_run))
            except Exception as exc:
                print(f"[STORY] skipped ({exc})")
```
   `puppet_stills` and `story_video` must not both be on: if both, `applied_story` (entered last) answers synthetic numbers and the puppet map is simply unused.
6. After the render (same try-block area, after `_hybrid_stack.close()`), the gate on the real file:
```python
            if self._settings.get("story_video"):
                try:
                    import story_audit
                    story_audit.audit_all(config["output_path"], plan=_story_run.plan, aligned=aligned, words=whisper_words, print_fn=print,
                                          sheets_dir=Path(state_dir).parent / "state" / "story")
                except Exception as exc:
                    print(f"[STORY AUDIT] skipped ({exc})")
```
   The audit decodes the video once (about 40 s for 4.5 min at 1080p). It reports; it never fails the render.

## Dry run vs live

* `dry_run=True` (default): align, shots, picture-generation plan, clip jobs and the plan audit. Nothing rendered. `applied_story` then still splits scenes at shot cuts
  (each shot shows its scene's picture or an already made picture) - useful as a preview of pacing, captions and timing.
* `dry_run=False`: also renders the LOCAL clips (story_motion: motion + link clips, CPU) and assembles the timeline; the render then plays them.
* In neither mode are pictures generated (Flow) or AI video made: those are PLANNED only (counts in the report, `ai_video_job` records). When pictures
  exist (`story_pictures` or `state/story/pictures/`), they are picked up on the next run (the clip step is re-keyed by the picture list).

## Audit gates (story_audit.THRESHOLDS)

still stretch <= 3 s (frame difference of 64x36 blurred grey frames, 0.5 s apart, mean < 1.5 = still; calibrated on the old hrt video), every shot <= 6 s,
no more than 3 identical transitions in a row, <= 35 % shots with no motion, >= 90 % of matched words inside their scene window, 0 flash frames (a one-frame
jump of >= 40 grey levels that falls back within 6 frames; fades and cuts are not flashes). Also `contact_sheet(video, every_s, out)`, `cut_sheets(video, cuts, out)`.

## Risks / weaknesses

* The still detector measures change, not "interesting" change: a heavily textured picture with a strong Ken Burns zoom can read above 1.5 and slip through
  (the threshold is a measured compromise; `still_stretches(thresh=...)` is tunable), a slow genuine pan can read as still. A big on-screen animated graphic
  counts as motion.
* `sync_report` matches script words to Whisper words on a consonant skeleton (Hindi spellings differ); it uses `story_align.sync_report` if that ever exists, and
  only judges words it could match (`match_pct` says how many that was: about half of hrt's script words, because Whisper garbles Hindi).
* The plan audit's "idle shots" counts only tier 0/still; story_motion's `still_motion` shots count as moving, which is only true if that motion is real. The
  rendered-video still check is the honest gate.
* Link clips are a few frames taken from the neighbouring shots' time; if D's link frame count differs from what the file really has, `assemble_timeline` reads the
  file (it does), so timing stays exact; captions change text at the link midpoint, not at the exact word.
* The render makes ~3x more clips (hrt: 32 scenes -> 91 shots -> ~100 units): the render cache and parallel scene workers carry this; first render is slower.
* `applied_story` replaces `vg.render_video` for the duration of the context; any other code that patches `render_video` in the same stack must be entered before it.
* Trimmed copies and clips are cached by name+size; deleting `state/story/` is the reset.
