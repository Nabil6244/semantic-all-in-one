# Milestone 3 report: captions, map beats, archive beats

Date: 2026-10-22. Scope: board captions (four-rung ladder), map and archive beats as plan data with relevance checks, rendering through the unchanged Hybrid path.
**Nothing committed, staged or pushed. No protected file, `app.py`, spec, settings, UI, installer, packaging file or protection manifest was touched.** M4, a post-render overlay and any app integration were not started.
Schema frozen first: [explainer_cue_schema_v1_2.md](explainer_cue_schema_v1_2.md) (v1 and v1.1 unchanged). Evidence: [m3_evidence/](m3_evidence/). Offline, one Mac, **synthetic word times made by rule, not a human voice.**

## Files changed
New under `explainer/`: `captions/{__init__,timing}.py`, `beats/{__init__,relevance,mapbeat,archive}.py`, `spike/verify_m3.py`. New under `docs/explainer/`: the v1.2 schema, this report, `m3_evidence/` (19 files).
Edited (my own untracked files): `board/cues.py` (kind `caption`; `map` and `footage` stay reserved), `board/layout.py` (caption slots B, BL, BR), `board/render.py` (caption placement, word boxes, drawing), `board/elements.py` (`draw_caption`), `board/builder.py` (manifest `schema_version` "1.2" when a caption is present), `spike/verify_m1.py` and `spike/verify_m2.py` (one line each: the "still reserved" check now uses `map`, because `narrator` and then `caption` became real; every other result is unchanged).
Read, not edited: `hybrid/plan.py`, `hybrid/validate.py`, `hybrid/compile.py`, `hybrid/geo.py` (to learn the contracts below).

## What the existing validator and renderer actually do (read directly, not assumed)
- `validate_plan` checks structure, ordering, camera fit and that a layer exists in its beat. It does **not** open asset files, ask whether a place is spoken, or judge relevance.
- `asset_problem` **accepts** `stock_image:`, `stock_video:`, `flow_image:`, `flow_video:`, `youtube_video:` references (the renderer would fetch or generate pictures for them) and also accepts a `https://...` string (it is treated as a file name). Measured: `validate_plan` alone accepted 11 of the 13 remote or invalid references I tried (it rejected only `data:` and the `|` list); our check refuses all 13.
- A map beat's layers carry a start time `t` in narration seconds; a footage beat can only carry template graphics; `caption` layers are one whole phrase at one time (no per-word reveal over a map).

## Captions on board clips
**Onset definition used throughout:** a word is revealed on clip frame `ceil((t − clip_origin) · fps)` and is fully drawn on that frame. The pixel check looks for the first video frame whose word box changes from empty to inked (≥ 6 changed pixels more than 50 gray levels from the board); expected video frame = clip frame + the clip's offset in the render (210 hard cut, 203 dissolve).
Three numbers are compared per word: the **plan** frame (manifest), an **independent** recomputation straight from the narration word (not from the manifest), and the **pixel** frame.

| Cue | Rung | What it tests | Words | Plan = independent? | Pixel frame − expected (hard cut / dissolve) |
|---|---|---|---|---|---|
| k1 "prices rose every year" | 1 all matched | each word at its own start (frames 6, 15, 24, 33) | 4 | yes, 4/4 | 0,0,0,0 / 0,0,0,0 |
| k2 "the poor lost their domes" | 2 partial | unmatched trailing word spread to the sentence end (9.552 → 10.096 s, placed at 9.824) | 5 | yes, 4/4 (spread word has no independent value) | all 0 / all 0 |
| k3 "a completely different thought" | 3 by fallback | nothing matches: typed from the anchor | typed | n/a | first character 0 / 0; completion 0 / 0 |
| k4 "the crown grew rich", typed requested | 3 requested | typed mode is a choice, not a fallback | typed | n/a | first character 0 / 0; completion 0 / 0 |
| k5 "nobody counted the cost" at "counted" | 2 partial | first word spoken **before the anchor** is never matched; zero-length interval, so it is stacked on the same frame as "counted" | 4 | yes, 3/3 | all 0 / all 0 |

**13 of 13 words and 2 of 2 typed captions land on the expected frame in both modes (0 frames of error); the plan frame equals the independent recomputation for every matched word; no held or skipped frames.** The completion frame of a typed caption is the first frame whose changed-pixel count reaches 97% of the final count (stated method; ±1 frame would have been plausible and did not occur).
Pure board frames: 300 (hard cut) and 287 (dissolve); the dissolve frames are excluded from pixel comparison, exactly as in M1 and M2.

**Fallback semantics and edge cases (18 timing unit tests, plus 33 caption cue-rule and layout checks)**: matches are leftmost within 6 narration words of the previous match; a word before the anchor is never used; the match window is the anchor's sentence inside the beat (words of the next sentence or after the beat end are not matched); a match more than 6 words away is ignored; out-of-order times are clamped and noted, more than 2 clamps discards all matches (rung 3); a zero or too-short interval stacks the run on the previous matched word's frame; a phrase past the beat is rung 2 with the spread ending one frame before the clip end; dashes are display-only and share the neighbour's time; more than 12 words is rung 4, more than 8 is recorded `over_policy`. Interpretation noted in the schema: for an interior run of unmatched words the spread interval ends at the **next matched word**, not the sentence end (a sentence-end interval would put it after a later matched word); only a trailing run is spread to the sentence end.
**Manifest** records for every caption: rung and name, mode, matched words with narration indices and times, reveal times and frames, spread intervals, clamped and stacked counts, window (anchor, sentence end, beat end, clip origin), slot, word boxes, notes, `over_policy`.

**Layout and geometry.** The caption box is the text box in a one-line band (y 900 to 984). Tests (all pass): an explicit card, prop icon or margin violation is refused; chip and caption may share the strip only if their boxes do not overlap (automatic chip beside a short caption is allowed; a named chip slot under the text is refused; a caption moves to BR when a chip blocks BL); with the narrator on the right a long caption takes the left half (BL), a short one stays in B beside it, a named BR is refused; a caption during the narrator's enter or exit slide is refused where it would overlap, allowed after the exit has finished. In the 10 s layout render (captions plus the M1 cards, icons, props, arrows, chip and the M2 narrator, 300 frames, both modes) **0 frames** have a caption word box outside the margins, overlapping another element's inflated box, or overlapping the narrator's exact opaque pixels (14 of 14 caption words detected, 0 frames of error).

## Map beats and archive beats (plan data)
Builders: `make_map_beat` (camera start/fly_to, markers, fills, lines, whole-phrase captions) and `make_archive_beat` (local pictures, reason, subject phrases); `check_plan` re-derives every match from the plan and the narration (it does not trust the builder).
- **Word match per layer:** the place must be a contiguous run of narration tokens **inside that layer's own beat window**; a mention in another beat does not count (negative test: a marker for Lahore in the beat that does not mention it is refused even though Lahore is spoken in the next beat, and `validate_plan` accepts that plan). The matched tokens, narration word indices and times are recorded; layer time must be 0.2 s before to 0.6 s after the match.
- **Archive clips:** a local regular, non-empty, readable file with an allowed extension; a non-empty `reason`; at least one subject phrase spoken inside the beat window; remote or generating references refused **before rendering**.
- **Offline place lookup:** each place is resolved with the application's own offline resolver; an unresolvable place is a problem. This shows the name exists, **not** that the test map is correct.
- **Camera framing (warning only):** a layer whose place is not inside the area the camera is looking at (by bounding box) gets a warning. The real view is not computed. A first run of my own sample showed why: Lahore and Karachi were drawn while the camera still looked at Gilgit, so they were off screen. The sample plan was fixed with a `fly_to` and the checker now reports that case.

**Sample plan** ([map_archive_sample_plan.json](m3_evidence/map_archive_sample_plan.json), 24 s, 4 beats: map, map, archive footage, map): passes `validate_plan` (0 problems) and our checks (0 problems; 7 layers and 1 clip checked; 2 warnings: the `Pakistan` fly_to is not spoken in its beat, and the b4 caption "the story returns to the map" starts with a word spoken before its anchor so it is rung 2). Rendered through the unchanged `generate_hybrid_video` offline (imagery off): render ok, 720 frames, 18.5 s, **0 network attempts** (every non-local connection was refused and counted; ffmpeg subprocesses are not covered by that guard).
**Negative tests, all rejected with the expected message (33 plan-level checks and 19 builder refusals):** unsupported place; marker too early; marker too late; label not spoken; place unknown to the offline lookup; caption layer not in the narration; layer outside its beat (caught by `validate_plan`); archive clip without a reason and with a blank reason; subject not spoken; no subject given; missing file, directory, empty file, unsupported extension, unreadable file (mode 000); 13 remote or generating references (`stock_image`, `stock_video`, `flow_image`, `flow_video`, `youtube_video`, `https`, `http`, `ftp`, `file://`, `//host`, `www.`, `data:`, a `|` list), each both in a hand-written plan and in the builder; a `map_footage` card with a remote asset. Builders: strict raises with all problems; non-strict returns the problems and the good layers.
**Rendered layer timing that can be measured offline** (counterfactual renders of the same plan without one layer; frames that differ from the base render; the renderer is deterministic: before a layer exists the two renders differ by exactly 0 for the marker and caption):

| Layer | Plan frame | First changed pixel | 5% of the final difference | Largest single jump |
|---|---|---|---|---|
| caption "single river system" | 60 | −47 (tiny global change from frame 13) | **0** | **0** |
| marker Gilgit | 200 | −6 | −3 | −4 |
| fill Pakistan | 15 | −15 (the base map differs from frame 0 when a fill exists) | −15 | +1 |

So the whole-phrase caption lands on its plan frame; the marker's entrance animation starts about 3 to 6 frames before the plan frame (cause not investigated; plan time is the engine's start time and the pin animates in); the fill cannot be isolated by this method. These are measurements, not a claim that map timing is frame-exact. The archive picture is on screen mid-beat (correlation of the downscaled frame with the source picture 0.943, against −0.061 for a map frame).

## Existing work preserved
| Check | Result |
|---|---|
| `verify_m1` (21 checks) | all true; cue rows and both clip SHA-256 identical to the M1 evidence |
| `verify_m2` (41 checks) | all true; narrator state-change frames, alignment numbers, face accuracy, collisions and both clip SHA-256 identical to the M2 evidence; asset hashes identical |
| `verify_builder` / `verify_splice` (legacy) | cue rows, checks and board clip bytes identical; splice render byte-identical |
| `verify_m3` | 115 of 115 checks |

## Determinism (methods and hashes)
- Caption clip built twice in one process, plain and instrumented: SHA-256 of the file, `ffmpeg -f framemd5` of all frames, and the manifest text (file name masked) all identical (6 of 6). Built in a separate interpreter: SHA-256 identical.
- Plain caption clip `d9b64c5a…dfa0` (81,030 bytes), instrumented `b9132916…cbc`. Plan builders run twice: JSON text SHA-256 identical, plan `49eacc75…da5`.
- The rendered map video was not compared byte for byte across runs (only the pre-layer frames of the counterfactual renders, which differed by exactly 0).

## Protection, Git state, off-mode
| Check | Result |
|---|---|
| Official guard `test_weather_isolation` (4 tests), before and after | OK, OK. **Caveat unchanged:** the manifest is dirty (another session refreshed it for its own edits to 4 protected files), so this proves no change relative to that manifest, not relative to HEAD. I did not touch the manifest and added no file to a protected folder |
| `git status` and the tracked diff, before vs after | identical |
| Off-mode snapshot (original fixture compiled twice, 571 protected-scope hashes, 1,331-file census, HEAD, `settings.json` hash) | identical in every field |
| Bytecode in `explainer/` | none |

## Visual scorecard (against the Phase 0 scorecard)
| ID | Result |
|---|---|
| T09 caption policy | typed at 30 characters per second (the reference value); captions are key phrases of 4 to 5 words (policy at most 8); one cue type measured |
| T08 latency | caption words appear on their spoken start (0 s) by design; map layer offsets above |
| T11 relevance | every checked label, pin and archive clip is tied to a word inside its own beat window (7 layers, 1 clip); the offline map cannot show geographic correctness |
| H07 overlap | 0 caption collisions in 300 frames, both modes |
| H02 no missing assets | local files only; refusal tested; no network attempt in rendering |
| M01, M03 to M05 | **no reviewer ratings were collected**; not claimed |

## Visual limitations and open issues
- The map is the offline vector base (no satellite imagery) and the archive "picture" is a test pattern; nothing here shows the look of a real map or archive image.
- Captions on boards use Patrick Hand; map caption layers use the engine's own typeface and one whole-phrase reveal (no per-word timing over a map); the engine's marker animation starts a few frames before its plan time.
- Hard cuts: `dissolve_s` is plan-wide; the map sample keeps 0.5 s dissolves, the board samples were tested in both modes; per-beat dissolve remains impossible without a protected change.
- **Word times are synthetic.** Real Whisper starts can be off by tenths of a second; the ladder's rung 1 would then inherit that error, and rung 2's spread depends on the sentence end. Not tested on a human voice. The 2-frame tail adjustment is still unresolved and unused.
- A map caption layer cannot be typed; narrator and captions over a rendered map were not built (deferred as instructed).
- Inter's licence text is unverified; installers and the packaging spec are unchanged; Windows and macOS packaging not tested.
- The shared fixture is 10 s (boards) and 24 s (map plan); no long-form or multi-topic run.

## Next smallest step
M4 needs your approval first. Smallest slice: the director's beat-selection rules on plan data (choose board, map or archive per sentence from the narration), reusing `check_plan` as its gate, before any switch or UI.
