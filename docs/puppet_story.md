# Puppet story director

`puppet_story.plan_story(scenes, words, settings, log)` plans ONE protagonist for the whole video who follows the narration and walks from picture to picture.

* Input: scenes `{scene_no, start, end, script_segment, prompt, still}`, Whisper words `[[w, start, end]]`, settings `{intensity, character, seed, rows}`.
* Output: `{"protagonist", "scenes": {no: {character, action, direction, beats, why, enter, exit, y, char_h, prop, journey, role}}, "links": [(a, b)]}`.
  Beat times are seconds from the start of that scene's clip; `x0/x1` are screen fractions (outside 0..1 = off screen); `params.facing` tells the side.
* Rules: skip crowds/maps/charts/aerials/stat narration, scenes under 3 s, and pictures whose subject is already a person unless the narration moves.
  Journeys are runs of 2-4 consecutive scenes: the figure leaves scene N at the walking speed through one side and enters N+1 from the other with the same
  speed, `char_h`, row `y` and direction. Beats come from narration words (movement -> walk/run, उठा/carry -> pick_up, रख/deliver -> put_down, greetings -> wave,
  देखिए -> look). Budget per intensity: low 0.6, medium 1.3, high 2 appearances per minute; CSV `character_action/character/character_ground` rows win.
* `explain(plan, scenes)` prints each beat with the narration phrase behind it. Any exception gives an empty plan.
* `puppet_stills.prepare(..., words=None, motion_renderer=None)`: `settings["puppet_mode"]` is `story` (default) or `classic` (old planner). With a
  `motion_renderer` (or `puppet_motion` on and `health_cinema.puppet.motion` present) every scene without a character gets a motion clip (scene + 0.5 s).

## Timing (re-alignment) and lanes

* `realign(scenes, words)` maps every scene's script words onto the Whisper words (monotonic DP on a consonant skeleton of the sound: matras, nukta, aspiration and dental/retroflex differences are ignored, English words are keyed the same way, numbers are skipped). It returns per scene `speech_start/speech_end` (where its words are really spoken), `cov` (share found), `in_frac` (share inside the app's clip window), `foreign` (share of the clip playing other scenes' speech), `timing_ok`, `reason`, `trust` (`heard` or `inferred`: Whisper dropped the stretch, words are spread between the heard neighbours). `timing_report(scenes, words)` prints app window vs real speech per scene.
* Beats use only words whose real time lies inside the scene's clip window; a scene is not eligible when `timing_ok` is false (under 70% of its words inside the clip, or 70-90% with the speech more than 2 s outside, or over 50% of the clip playing other scenes' speech).
* Lanes: `health_cinema.puppet.lanes.lane_for` (or `settings["lane_fn"]`; `False` disables) is called lazily for every otherwise eligible picture. None means no floor: never a character. Beats are clamped to the lane (open edges, within 0.04 of the frame edge, let the figure walk in from outside), the figure stands clear of the avoid spans, `y`/`char_h` come from the lane (a journey shares the mean y and the smallest h_hint, lanes of consecutive pictures must be within 0.07 in y and open at the exit/entry edge, within 0.2 of it), and the lane dict is passed as `params["lane"]` to `render_shot`. Settings `puppet_lane_fn`, `puppet_lane_overrides`, `puppet_project_dir` reach `prepare_story`; the project folder is found above the pictures folder (the one holding `state/`).
* `plan["info"]["timing"]` and `["skipped"]` hold the per-scene findings; `explain` prints lane, timing and skipped scenes.
