# Explainer cue schema v1.5: motion cues (stamp, plate)

Opt-in (`DirectorOptions.motion`, settings key `explainer_motion`, default off). With it off, no cue, plan, clip name or report key differs from before. `EXPLAINER_VERSION` and `SCHEMA_VERSION` are deliberately **not** bumped: that would change every clip hash and break the disabled-path identity. Motion cues carry their own version, `params.mv` (`explainer/motion/presets.py: VERSION`).

Both are ordinary `visual` cues with a new `params.style`; they use the existing anchor, `offset_s`, `pos`, `role` and `text` fields, so the layout gate, collision checks and timing code are shared.

| style | text | params | drawn by |
|---|---|---|---|
| `stamp` | one spoken verdict word, shown in capitals (a contiguous quote of the narration) | `style`, `mv`, `texture` (bool: worn texture used or plain), `px` (chosen size) | `motion/sprites.py`, animation `slam` (8 frames at 30 fps, impact on frame 4) |
| `plate` | a spoken four-digit year (1000-2099) | `style`, `mv`, `px` | `motion/sprites.py`, animation `slide_in` (9 frames, ease-out cubic, 60 px) |

Rules (enforced by `director/compose_motion.py`, tested in `spike/test_motion_kit.py`):
- at most one stamp and one plate per board beat; board beats only (not map, archive or cartoon beats), `look == "reference"` only;
- the cue is anchored on the word itself with offset 0, so the first visible frame is the word's frame (0 to +1 frame later), never before;
- a stamp needs 0.8 s left in its beat and 15 s since the previous stamp; a plate is only for an **important date** (score >= 2: an event word such as began, ended, fell, war, freed within 6 words of the year +2; the sentence is the opening, a twist or a conclusion +1; the narration's first year +1; `compose_motion.date_score`), so ordinary years get no plate; at least 15 s since the previous plate;
- a plate **replaces** the board's own bare-year `tag` or `chip` (same anchor word, the old cue removed) and is refused, leaving the board untouched, when a separate year element (another tag, chip, title, header or plate carrying that number) would remain; with no tag to replace, it is also refused when any cue, including a running phrase, already shows the year;
- a place is accepted only when the whole beat still builds with no layout problem; largest size first (120, 96, 72 px for stamps), candidate places in a fixed order; nothing is dropped later by the gate;
- the plan report gets `beat_details[<beat>]["motion"] = {stamps, plates, skipped}` for beats the pass looked at; the key is absent when motion is off;
- a missing or damaged texture (`assets/stamps/manifest.json` + two masks, SHA-256 checked) gives a plain stamp, `texture: false`, and a note in the beat's `repairs`; never a failure. The clip name includes a digest of the mask manifest when a textured stamp is present.
