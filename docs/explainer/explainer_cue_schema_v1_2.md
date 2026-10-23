# Explainer schema v1.2 (additive; Milestone 3): board captions, map beats, archive beats

Date: 2026-10-22. [v1](explainer_cue_schema.md) and [v1.1](explainer_cue_schema_v1_1.md) are unchanged; every earlier cue means what it meant. The manifest `schema_version`
is `1` (no narrator, no caption), `"1.1"` (narrator) and `"1.2"` when a caption cue is present. Still reserved: `map`, `footage` as cue kinds (map and archive beats are
**plan data**, below, not board cues). Nothing here touches a protected file; map and archive beats use the existing plan schema, `validate_plan` and renderer.

## 1. The `caption` cue (board clips)

`Cue(id, kind="caption", anchor, text, role, offset_s, cps, slot, pos, params)`.

| Field | Meaning |
|---|---|
| `text` | the key phrase, 1 to 12 words (policy target 8; more than 8 is recorded as `over_policy`, more than 12 is a problem) |
| `anchor` | where the phrase may start: `{"word": w, "occurrence": n}`, `{"index": k}` or `{"time": t}` (as every cue) |
| `offset_s` | seconds added to **every** reveal time (default 0.0) |
| `params.mode` | `words` (default): each word appears when it is spoken; `typed`: the whole phrase is typed at `cps` (default 30) from the anchor |
| `role` | colour of the newest word for 6 frames (`blue` default); body ink otherwise |
| `slot` | `B` (full band, x 640..1824), `BL` (640..1232), `BR` (1232..1824); y 900..984; default: first free of B, BL, BR; `pos` is the top-left of the text box and is checked like every explicit position |

**Onset (what the verification means by "the frame it appears").** A word is *revealed on clip frame* `ceil((t - clip_origin) * fps)`, the same rule as every cue,
where `t` is its reveal time in narration seconds (+ `offset_s`). On that frame the word is fully drawn (no fade). The caption's first frame is the reveal frame of its
first word. A typed caption shows its first character on the first frame and character `k` (0-based) when `age >= k / cps`, `age = frame/fps - onset`.

### Timing resolution: the four-rung ladder (explicit; the rung used is always recorded)
Phrase tokens: each phrase word is lower-cased and stripped of everything but letters, digits and `'`; a word with nothing left (a dash) is *display-only*, is drawn with
the previous word and is not matched. Narration tokens are the beat's words (hyphenated words are not split; same normalisation).
Search window: the narration words of the **anchor's sentence**, from the anchor word to the sentence end, and inside the beat (start < beat end).
(For a `time` anchor: words of the beat with start >= the time, until the beat end.)

Matching, in phrase order: each phrase word takes the **leftmost** narration word that is after the previous match (at or after the anchor word for the first one), has
the same token, and lies within **6 narration words** of the previous match (of the anchor for the first). A repeated word therefore matches the nearest occurrence after
the previous match, never one far away; a word spoken **before the anchor** is never matched; a word in the next sentence or after the beat end is not in the window.
Out-of-order times in the transcript (a start earlier than the previous matched start) are clamped to the previous start and noted; more than 2 clamps = the matches are not trusted
(all treated as unmatched). Reveal times are never earlier than the anchor time (before `offset_s` is added).

| Rung | When | Reveal times |
|---|---|---|
| 1 `all_matched` | every matchable phrase word matched | each word at its own spoken start |
| 2 `partial` | at least one, not all | matched words at their own starts. A run of unmatched words is spread evenly **inside the interval from the preceding matched word's start (or the anchor's time) to the next matched word's start; when no later word matched, to the sentence end** (to the beat end for a time anchor): `k`-th of `m` words at `a + (b - a) * k / (m + 1)`. If that interval is shorter than `(m + 1)` frames or not positive, the run is revealed on the same frame as its preceding matched word (recorded `stacked`) |
| 3 `anchor_only` | nothing matched but the anchor resolved, or `mode=typed` was requested | typed at `cps` from the anchor time |
| 4 `unresolvable` | the anchor cannot be resolved (word absent from the beat, index or time outside it), the phrase has no visible text, or its layout does not fit | a problem; the cue is skipped (strict mode raises before anything is drawn) |

A phrase that runs past the beat end can only reach rung 1 if every word is spoken inside the beat; otherwise the words after the beat end are unmatched and the cue
is rung 2 (their spread interval ends at the sentence end **clamped to one frame before the clip ends**). A reveal outside the clip is never produced.

### Layout
One line, Patrick Hand 52 px shrinking by 4 px to 36 px, centred in its slot, drawn with the final text width so words never move as they appear. The collision box is the
text box (+8 px), not the whole band. Chips use the same strip: a chip and a caption may be on screen together only if their boxes do not overlap (a chip beside a short caption is fine; the later one is refused or takes another slot). Narrator, cards, icons,
props, arrows and margins are checked as for every element.

### Manifest record (per caption cue, key `caption`)
`rung`, `rung_name`, `mode`, `phrase_words` (display words), `matched` (phrase word, narration word, narration index, start, end), `reveal_times_abs`, `reveal_frames`,
`spread` (each spread interval and its words), `window` (anchor index, anchor start, sentence end, beat end, clip origin, fps, clip frames), `clamped`, `stacked`, `over_policy`,
`slot`, `word_boxes` (pixel box of each word at its final place), `notes`.

## 2. Map and archive beats (plan data; `explainer/beats/`)
They are ordinary beats of the existing plan (`mode` map or footage; `map_footage` cards are not produced by M3). The explainer never changes how they are rendered.

**Map beat.** `layers` of type `marker`, `zone_label`, `fill`, `line` and `caption`, camera steps `start` / `fly_to`. A layer's time `t` is the spoken start of the word
its place was matched to, plus an offset (default 0.0 for `fill`, 0.1 for `marker`).
**Archive beat.** `mode` footage; one or more clips with a local file `asset`, a non-empty `reason`, optional `kenburns`; the subject phrases are kept in a side record.

**Relevance rules (checked by `explainer.beats.relevance`, not by `validate_plan`).**
1. Place match: a `place` (and each of `places`) must be spoken **inside the layer's own beat window** as a contiguous run of narration tokens (a name with several words must
   appear as those words one after another; a hyphen or space splits tokens). A name spoken elsewhere in the script does not count. The matched words, their indices and times
   are recorded per layer. The layer's `t` must lie between 0.2 s before and 0.6 s after the matched word's start (provisional).
2. A marker or zone label: the label's words must be the place or be spoken in the window.
3. A map `caption` layer: its text is matched with the same ladder (anchor = the first narration word at or after `t` - 0.25 s equal to the phrase's first word, window = the rest of the beat); its `t` must be the first reveal (within 0.05 s); rung 3 (no phrase word spoken in the window) and rung 4 are problems. Over a map a caption layer is one whole phrase (no per-word reveal); the plan builder anchors it explicitly with `anchor_word`.
4. Camera `fly_to` places not spoken in the window are warnings (recorded), the opening `start` camera is exempt.
5. Archive clip: asset must be a **local file** (exists, is a regular file, non-empty, extension jpg jpeg png webp mp4 mov m4v), `reason` non-empty, and **at least one subject
   phrase** spoken inside the beat window (match recorded). A clip without a subject record is a problem (relevance cannot be established).
6. **Refused before rendering:** any asset with a URL scheme (`http:`, `https:`, `ftp:`, `file:`, `//host`), any `stock_image:`, `stock_video:`, `flow_image:`, `flow_video:`,
   `youtube_video:` reference (the existing plan accepts these and would fetch or generate), a `|` list, and a directory or missing file.
8. Camera framing (warning only): the camera target in force when a layer appears (the latest `start` or `fly_to` at or before its time) must be that place, or an area whose bounding box contains it (looked up offline); otherwise the layer is recorded with a warning that it may be off screen. The real view is not computed.
7. Each map place is also looked up with the application's own offline resolver (`hybrid.geo.resolve`); the answer is recorded (`resolvable_offline`) and an unresolvable place
   is a problem. This establishes that a place name exists, **not** that the offline test map is geographically or visually correct.

`validate_plan` is run on every produced plan and its problems are reported; it does not check asset files, relevance or timing meaning, so a plan can pass it and fail ours.

## 3. Strict mode and compatibility
Board captions: strict raises `BoardCueError` before anything is drawn; non-strict leaves the cue out, records it and renders the rest (as for every cue). Plan builders raise
`PlanBuildError` listing every problem in strict mode and return the problems with the partial result otherwise. Old cue files load unchanged (unknown keys are ignored).
Hard cuts versus dissolves: `dissolve_s` is plan-wide; a plan with map beats and archive beats keeps the application's default dissolve unless the caller sets it.
