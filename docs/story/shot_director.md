# Shot director (`shot_director.py`)

Turns "one picture per scene" into a shot list with a change of visual every ~2-5 s, following the narration phrase by phrase. Offline and deterministic for a seed: no network, no Flow, no LLM (an optional `refine` hook exists, off by default).

```python
import shot_director as sd
plan = sd.plan_shots(scenes, words=None, settings=None, log=print)
rows = sd.to_csv_rows(plan)          # list of dicts, CSV friendly
plan2 = sd.from_csv_rows(rows)       # inverse; also accepts old 4-column CSVs
```

* `scenes`: list of dicts with `scene_number` (or `scene_no`), `script_segment`, `prompt`, `start`, `end` (`duration` used if `end` is missing). Timings can come from any source (the Agent A aligner, `out/puppet_cache/hrt_timing.json`, ...).
* `words`: optional `[[word, start, end], ...]`. Used only to place phrase cuts in time (by character proportion inside each scene's window), so spelling differences between script and transcript do not matter. Without it, cuts are placed proportionally to character count inside the scene.
* `settings` (all optional): `seed` 0, `target_len` 3.2, `min_len` 1.8, `max_len` 5.0, `max_new_ratio` 1.8 (new pictures <= ratio x scenes), `ai_video_ratio` 0.22, `link_ratio` 0.20, `graphic_ratio` 0.12, `allow_puppet` False, `puppet_ratio` 0.05, `close_gaps` True (split silences between scenes, up to `max_gap_close` 4 s, between the neighbouring shots), `protagonist` {name, look}, `refine` callable(plan)->plan.

## Schema

```
{"protagonist": {"name", "look", "reference_key"},
 "shots": [{
   "shot_id": "003a",            scene number (3 digits) + letter, unique, sorted
   "scene_no": 3,
   "start": float, "end": float, seconds; shots of a scene tile it with no gaps
   "text": str,                  the narration phrase (exact slice of script_segment)
   "subject": str,               what is concretely seen (concept keys) or "detail of: ..."
   "prompt_en": str,             image prompt. picture=="existing": the scene's own prompt verbatim; "new": composed prompt
   "picture": "existing"|"new",  existing = reuse the scene's picture (first shot of each scene, or over budget); new = generate
   "character": bool,            the protagonist is in this shot (a person acting is named in the phrase)
   "motion_tier": "still_motion"|"link"|"ai_video"|"puppet"|"graphic",
   "camera": "push_in|pull_out|drift_l|drift_r|diag|hold_alive",
   "transition_in": "cut|match_cut|torn_wipe|doorway_push|dissolve|whip",   how this shot comes in
   "link_to_next": null | {"kind": "match_cut|walk_through|push_through|torn_wipe", "note": str},
   "beats": [{"t0","t1","word_idx"}],  timed concept words inside the shot; word_idx = index into script_segment.split() of that scene
   "why": str,                   phrase / cue / reason for the choices
   "side": "left"|"right",       (extra) where the main subject sits in a new picture (alternates; kept across a shared object for match cuts)
   "graphic": {"kind":"stat","value":str}   (extra, only motion_tier=="graphic")
 }],
 "stats": {scenes, shots, avg_len, min_len, max_len, shorter_than_min, longer_than_max, new_pictures,
           character_shots, tiers{}, transitions{}, longest_same_picture_s}}
```

Rules for consumers:
* Picture identity: a shot with `picture=="new"` owns its own picture (`shot_id`); `"existing"` shots show the scene's picture (scene `S<scene_no>`). Every picture gets the still-motion layer with the shot's `camera`.
* `motion_tier=="link"` means the link goes **from this shot to the next** (`link_to_next` is set exactly then). The next shot's `transition_in` is the matching style (`match_cut`->match_cut, `torn_wipe`->torn_wipe, `walk_through`/`push_through`->doorway_push). Links are only planned between different pictures that are adjacent in time (gap <= 1.5 s).
* `motion_tier=="graphic"`: the backdrop is the scene picture (`picture=="existing"`), the app's animated graphic carries the number in `graphic.value`.
* `ai_video` is capped near 22% of shots, never on adjacent shots; `puppet` only when `allow_puppet`.
* No transition appears three times in a row (a link-forced transition is never silently changed; if three linked ones would collide the link is dropped).

## CSV

`to_csv_rows` columns, in order: `scene_number, shot_id, script_segment, asset_type, prompt, character, motion_tier, camera, transition_in, link_to_next`, then optional extras `start, end, picture, subject, why`. `asset_type` is `image` for new pictures and `reuse` for shots that show the scene's existing picture (the consumer must not generate an image for `reuse` rows; their `prompt` is the scene prompt). `link_to_next` is `kind: note` or empty. `character` is `true/false`.

`from_csv_rows` is tolerant: missing columns get defaults; an old CSV (`scene_number, script_segment, asset_type, prompt`) becomes one shot per scene (`001a`, `picture: existing`, `still_motion`). If a CSV has several rows per scene and no `picture`/`asset_type=reuse` column, the first row of a scene is `existing`, the rest `new`. Start/end are `None` when the CSV has none (timings then come from the aligner).

## Example (hrt scenes 1-3, abridged: beats and some text trimmed)

```json
{"protagonist": {"name": "Night-shift warehouse worker", "reference_key": "protagonist_night_shift_warehouse_worker_fe6a5b",
   "look": "a faceless sepia paper-collage silhouette of a lean night-shift warehouse worker in a flat cap, a high-collar work coat, rolled sleeves and heavy boots, a handheld scanner on his belt, white cut-out outline"},
 "shots": [
  {"shot_id": "001a", "scene_no": 1, "start": 0.0, "end": 3.4, "text": "आज रात Amazon के", "subject": "detail of: a torn parchment map ...",
   "prompt_en": "<scene 1 prompt verbatim>", "picture": "existing", "character": false, "motion_tier": "still_motion",
   "camera": "push_in", "transition_in": "cut", "link_to_next": null, "beats": [{"t0": 0.0, "t1": 0.6, "word_idx": 0}], "why": "..."},
  {"shot_id": "001b", "scene_no": 1, "start": 3.4, "end": 6.9, "text": "किसी ऑर्डर का ट्रैकिंग पेज खोलिए और आपको वहाँ कोई दुकान दिखाई नहीं देगी।",
   "subject": "phone, shop", "prompt_en": "Collage illustration, close-up of a hand holding a phone showing a tracking page with a small old storefront, ... no text, no letters, no logos.",
   "picture": "new", "character": false, "motion_tier": "still_motion", "camera": "diag", "transition_in": "cut", "link_to_next": null, "beats": [], "why": "..."},
  {"shot_id": "003c", "scene_no": 3, "start": 18.7, "end": 21.9, "text": "और फिर एक ऐसी वैन में पहुँचता है", "subject": "van",
   "prompt_en": "Collage illustration, wide establishing view of a delivery van turning into a quiet street, ...", "picture": "new", "character": false,
   "motion_tier": "ai_video", "camera": "drift_r", "transition_in": "whip", "link_to_next": null, "beats": [], "why": "phrase \"और फिर एक ऐसी वैन...\"; 3.2s; ai_video: action 'arriving at a doorstep'; transition: time jump cue at phrase start"},
  {"shot_id": "003d", "scene_no": 3, "start": 21.9, "end": 25.0, "text": "जो आपकी गली में उस समय मुड़ती है,", "subject": "home",
   "picture": "new", "character": false, "motion_tier": "link", "camera": "drift_l", "transition_in": "cut",
   "link_to_next": {"kind": "push_through", "note": "movement carries over: turning a corner"}, "beats": [], "why": "..."}
 ],
 "stats": {"...": "see out/story/hrt_shots.json for the full real output"}}
```

The complete real output for hrt is in `out/story/hrt_shots.json` and `out/story/hrt_shots.csv`.

## How it decides

1. **Cuts**: tokens of the scene; boundary strengths: sentence end 3.0, comma-like 2.0, strong connector before a token (और, लेकिन, जब, फिर, क्योंकि, तो, but/and/when...) 1.5, relative words (जो, जहाँ, कि...) 1.0. A small dynamic program picks cuts minimising distance from `target_len`, with heavy penalties under `min_len` / over `max_len`, a bonus for strong boundaries and a penalty for one/two-word fragments. A scene under 2 x `min_len` stays one shot.
2. **Subject**: ~40 concept entries (Hindi stems with nukta/chandrabindu normalised + English words) -> concrete picture description, kind (place/object/person/vehicle) and scale (wide/mid/close). Verb stems give the action and whether it is a journey.
3. **New pictures**: shots after the first of a scene are scored (concrete concepts, new concept versus the scene prompt, length, long scene, run of same picture over 6 s, journey/person) and picked greedily up to `max_new_ratio x scenes`, with a penalty for several in one scene.
4. **Tiers**: graphic (numbers, years, %, lakh/trillion words) first; ai_video for strong action by a person or a journey (not adjacent, >= 2.4 s); links for adjacent different pictures with a journey verb, a shared object, or a place change; the rest still_motion.
5. **Transitions**: link style if linked; whip on time-jump cues (फिर, अचानक); dissolve for time shifts / new scene; match_cut for a shared object; torn_wipe / doorway_push for place change; cut for same-picture camera changes. No triple repeats.
6. **Protagonist**: theme words over the whole script/prompts pick a role (warehouse worker, doctor, farmer, soldier, astronaut, scientist, else everyman in a long coat). `look` is the verbatim character sheet used in every character prompt; `reference_key` is stable (role slug + hash of the look).

## Honest limits

* Heuristic and lexicon based: a phrase with no known concept gets no concrete picture (it reuses the scene picture or makes a vague "detail of" picture). The lexicon is small (about 40 concepts) and warehouse/commerce biased; extend `_LEX_RAW` for other topics. Proper names (Jacqueline, Bezos) are not recognised as people.
* Phrase boundaries come from punctuation and connectors in the script; unpunctuated long run-ons are cut by timing only.
* Timing quality is inherited: hrt scenes 20 and 27 have long silent gaps inside the scene (one 11 s shot on a single word, "ब्रांड"), so single words can own a shot for many seconds. Fix upstream (aligner), not here. Shots at the very ends of scenes may fall under 1.8 s (2 of 83 on hrt).
* "Existing" first shots keep whatever the scene picture shows; the protagonist is only guaranteed in **new** pictures made from `prompt_en`. `character: true` on an existing shot is a hint, not a guarantee.
* Person detection is by role words (कर्मचारी, पत्रकार, वकील, ...); "you" (आप) is not treated as the protagonist.
* ai_video / link choices are suggestions; whether a clip can actually be generated is the consumer's call. Camera choice is rule-based, not visual.

## Same-picture limit and silent shots (2026-10-29)
`max_same_pic` (default 6.0 s): after the scored choice of new pictures, any picture that would stay on screen longer than this gets a new picture at the shot that crosses the limit (Flow images are free, so this may exceed `max_new_ratio`; set `max_same_pic: 0` for the old hard cap). A shot longer than `max_len + 0.5` (usually a pause or a closed gap after its last word) is cut into even pieces; the words stay on the first piece. Graphic shots count as a visible change in `longest_same_picture_s`.
Checked on hrt (Hindi), 042_seddd (English, 21 scenes) and 037_stre (English, 17 min): longest same picture 6.0 / 5.0 / 5.9 s.
