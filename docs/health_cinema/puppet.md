# Health Cinema: paper-cutout puppet (pipeline side)

A rigged paper-cutout character walks, points or picks things up across a still picture, and can carry on through the cut into the next still. The character engine is `health_cinema/puppet/`; this page covers how the pipeline uses it.

## Switch and options (Health Cinema card)
- **Paper-cutout character on some stills (Classic edit)**: OFF by default; session-only like the other options. Nothing starts until Render.
- **Intensity** Low / Medium / High: about 20% / 35% / 50% of the scenes get a move, and the motion amount (`params.motion`) is 0.6 / 1.0 / 1.4.
- **Character**: Auto (varied across the video, kept through adjacent shots) or one cast member.
- High-end edit does not use it (a log line says so).

## CSV columns (optional)
`character_action`: `walk | run | stand_idle | look_around | point | turn | pick_up | put_down | wave | stop`, or a phrase (`walk_in_from_left`, `stand_and_look`, `pick_up_box`); `none` keeps the scene plain. `from_left` means moving right, `to_left` moving left. `character`: a cast name, blank = Auto.
Blank cells are decided by the planner; unknown values are dropped with a warning in the log. A CSV without these columns behaves as before. With the switch off the cells are ignored (one log line).

## Planning (`puppet_plan.plan_puppet`, deterministic per seed; the seed defaults to a hash of the narration)
- Only scenes that have a still picture (`visual.still|image|path` or an acquired image asset), are footage/text-card scenes, last 2.5 s or more, and whose narration names a person or a movement. Crowds, maps, charts, diagrams, statistics and percentages stay plain.
- CSV cells win; the rest are filled up to the intensity's share. No action twice in a row. Adjacent shots keep the character and direction and are joined by a transition (`tear_seam`, `door_walk`, `page_flip`, `behind_object`, picked from the wording, never the same twice in a row); shots further apart vary character and direction.

## Rendering (`puppet_plan.Runner`, called from `engine.run_health_cinema`)
- Raw renders are cached in `<project>/state/health_cinema/<quality>/puppet/` by (still hash, character, action/transition, direction, params, frames, size, engine `VERSION`). Editing one scene re-renders only that scene. The raw video is then conformed (size, 24 fps, yuv420p, exact frame count, captions) so it joins the other clips with `-c copy`.
- A transition borrows its frames from the start of the second scene, so scene lengths and the voiceover sync stay exact.
- Any puppet failure (no still, no cast, engine error, engine missing) logs one line, adds a `puppet_fallback` note flag and renders that scene normally. Stop is checked every 0.1 s during an engine call and raises `Cancelled`.
- The report lists `puppet` per scene and a run summary (`planned`, `rendered`, `cache_hits`, `fallbacks`, `transitions`).

Tests: `python3 test_health_cinema_puppet_plan.py` (uses a fake engine).
