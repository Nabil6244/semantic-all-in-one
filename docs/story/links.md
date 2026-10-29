# Story links and clip planner (Agent D)

Files: `health_cinema/puppet/links.py`, `story_motion.py`, `test_story_links.py`. Reuses `puppet/motion.py` (read-only), `effects.py`, `scene.py`.

## links.render_link
`render_link(still_a, still_b, kind, out_path, duration=1.2, fps=30, size=(1920,1080), seed=0, params=None, cancel=None, progress=None) -> out_path`

mp4, no audio, exactly `round(duration*fps)` frames, deterministic per seed, cached in `out/puppet_cache/links` (key: both stills' pixels, kind, duration, fps, size, seed, params, VERSION, every `puppet/*.py`). A cancelled or failed render leaves no `.part` file. `resolve_link(a, b, kind, params)` says what will really happen (kind used, fallback flag, points found) without rendering; `estimate_seconds(kind, duration, fps, size)`.

| kind | what it does | best use |
|---|---|---|
| torn_wipe | A is a paper sheet that slides away with a torn cream edge (frayed, jittering at boil rate), shadow on B, B drifts underneath. dir `l`/`r`. | new place or beat of the same chapter, "turn the page" |
| push_through | camera dives into a door / dark blob / centre of A (radial motion blur, dark bridge) and emerges from B's door or the same screen point. `point_a`, `point_b`, `zoom_max`, `dip`. | going INTO something, time/location jump with a "through" |
| match_cut | finds a dominant blob (or the horizon) in both stills, scales/moves so it coincides, dissolves while both drift, B relaxes to its own framing. `points`, `min_score`. No convincing shared feature -> `dissolve_alive` (`resolve_link()["fallback"]`). | visual rhymes: "this is like that" |
| whip | fast sideways whip pan, horizontal motion blur, parallax. dir `l`/`r`. | energetic hand-off, "meanwhile", lists |
| dissolve_alive | patchy paper dissolve (areas change at different moments, no uniform double exposure), both pictures keep moving. | gentle continuation, same topic, time passing |

Continuity: params `cam_a` / `cam_b` = `[[z, fx, fy] at link start, [z, fx, fy] at link end]` (camera zoom and offset as frame fractions, same numbers a motion.py clip has) make frame 0 / last frame exactly where the neighbouring motion clips are. `story_motion` fills them from `motion._Rig.cam()`. Without them the link frames A as a slow push and B as a settle.

## story_motion
- `plan_clips(shots, images, settings)` -> jobs (`motion`, `link`, `ai_video_job`, `puppet`, `skip`), each with `est_seconds`. camera map: push_in/pull_out/drift_l/drift_r as is, diag -> diag_in/diag_out (by shot id), hold_alive -> push_in at intensity low. Clip duration = shot length + `margin` (0.5 s).
- Links: shot `link_to_next.kind` (match_cut, walk_through->push_through, push_through, torn_wipe) wins, else the next shot's `transition_in` (doorway_push->push_through, dissolve->dissolve_alive, whip, match_cut, torn_wipe) when `transitions_as_links` (default on). No link between identical stills or next to a graphic/skip shot.
- tiers: still_motion -> motion clip; link -> motion clip + link clip; ai_video -> `ai_video_job` record (first_picture, last_picture, prompt, seconds; `ai_video_jobs(jobs)`) AND the still_motion fallback; puppet -> `settings`/`render_clips(puppet_renderer=callable(job))`, else fallback; graphic -> skipped.
- `time_budget_s`: drops links (plain ones first) until the estimate fits. `estimate_total(jobs, workers)`.
- `render_clips(jobs, out_dir, log, cancel, workers=1, puppet_renderer=None) -> {shot_id: mp4, "<shot_id>+link": mp4}`; shot clips render before links; a failing link is logged and becomes a cut; `Cancelled` propagates.
- `assemble_timeline(shots, clips, settings)` -> `{"segments","skipped","fps","frames","seconds"}`.

### Timeline rule
A link of L frames is TAKEN from the tail of shot N and the head of shot N+1, never added: link = `[end_N - tail, end_N + head]`, `tail = round(L*split)`, `head = L - tail` (split default 0.5). Shot N+1's clip is played from `clip_in = head/fps`. All boundaries are whole frames (`round(t*fps)`), segments tile exactly, so total = last end - first start = audio length. A link is dropped (listed in `skipped`) if a shot would keep < 0.4 s of its own picture.

## Timings (1080p, 30 fps, 1.2 s link = 36 frames, shared busy Mac; warp_scale .75 like motion.py)
torn_wipe 140-165 ms/frame (5-6 s), dissolve_alive ~155 (5.7 s), match_cut 200-320 (7-11 s), whip 210-310 (8-11 s), push_through 230-350 (8-12 s). motion clip ~150-160 ms/frame.
This is over the ~100 ms/frame goal: Post (grain/vignette at working size) is ~60 ms and each mesh warp ~45 ms, and links warp two pictures.

## Weaknesses
- match_cut feature finder is a blob/DoG heuristic; on the 32 hrt stills true visual rhymes are rare (best consecutive scores .35-.5), many pairs fall back to the horizon or to dissolve_alive.
- push_through target is whichever dark door/blob is found (can be a person's dark clothing); give `point_a` for control.
- whip has faint streaks at the extreme edges at peak blur; torn_wipe edge is a procedural cream band, not scanned paper.
- Frame-exact continuity needs `cam_a`/`cam_b`; a ~1-2 px boil/par mismatch at the joins is possible.
