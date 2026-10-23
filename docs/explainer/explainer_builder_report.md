# Word-timed board-clip builder: report

Date: 2026-10-22. Scope: the single next step named in the spike report, nothing more. No narrator art, no font decision, no UI, no integration into the application. Nothing committed.
Evidence: [builder_evidence/](builder_evidence/). Code: [explainer/board/](../../explainer/board/), verification [explainer/spike/verify_builder.py](../../explainer/spike/verify_builder.py).

## What was built

`build_board_clip(cues, words, beat_start, beat_end, out_path, dissolve_s=…)` takes cues that say **what** appears and on **which spoken word**, and returns:
- one grey-board clip of exactly the beat's length (plus `dissolve_s` when the join is a dissolve);
- a manifest of every cue (word, word time, planned onset, planned frame, bounding box, problems);
- a plain-data **plan fragment**: a `footage` beat holding the clip as a local file, plus the `dissolve_s` setting it needs.

| File | Role |
|---|---|
| [explainer/board/cues.py](../../explainer/board/cues.py) | `Cue`, `ResolvedCue`, `resolve_cues`: finds the anchor word inside the beat, finds sentence starts and ends from the punctuation on the words, applies the offset, converts to clip time |
| [explainer/board/render.py](../../explainer/board/render.py) | Placeholder drawing (flat grey board, typed text, scale-in circles, an outlined title) and ffmpeg encode. `instrument=True` adds the frame-number cells and red border used only to verify |
| [explainer/board/builder.py](../../explainer/board/builder.py) | `build_board_clip`, `clip_geometry`, the plan fragment, the manifest |
| [explainer/spike/verify_builder.py](../../explainer/spike/verify_builder.py) | Unit-level checks, then renders the 24 s fixture with the clip through the unmodified pipeline and reads the render back |

Cue kinds: `type` (typed phrase, optional `finish_with: sentence_end`), `pop` (circle with label scales in), `title` (large outlined title scales in), `clear` (empties the board at the next sentence start, or at a word). Default offsets come from the Phase 0 reference passage and are **provisional**: type +0.0 s, pop +0.2 s, title +0.1 s, clear +0.0 s, type speed 30 characters per second.

Timing model (from the spike): hard cut → clip second 0 is the beat start and the clip is the beat's length; dissolve → clip second 0 is `beat start − dissolve_s/2` and the clip is `beat + dissolve_s` long.

The package imports nothing from the application and nothing protected. Only the verification script imports `hybrid` and `pakmap` (read-only, to run the real pipeline).

## How it was tested

Test narration: our own six sentences with Whisper-shaped words (text with punctuation, start, end), 0.294 s per word, so the word times are **exact inputs**. Six cues in the footage beat (9 to 17 s): a typed phrase on "river", two pop-ins on "farmers" and "water", a clear at the next sentence start, a title on "glaciers", and a typed phrase that must finish when its sentence ends. The clip was inserted as the fixture's footage beat and rendered through the **unmodified** `generate_hybrid_video` (offline imagery, synthetic tone as narration, sound design off), twice: `dissolve_s = 0` and `dissolve_s = 0.5`. Each render was read back frame by frame: the 16-bit frame number locates every clip frame in the video, and for each cue the first frame whose pixels change in the cue's own region is its real onset.

No network, no external generation, no commits, no pushes, and none of the repository's test suites were run.

## Results

### Builder checks

| Check | Result |
|---|---|
| Strict mode raises `BoardCueError` for a word not spoken in the beat | PASS |
| Non-strict mode drops the bad cue, lists it in `problems`, and still builds the clip | PASS |
| Problems reported (not guessed) for: unknown kind, missing text, empty anchor, bad `clear.at`, an offset that puts the cue outside the clip | PASS (5 of 5) |
| Same inputs give the same manifest, the same frames, and the same bytes | PASS (all three; same machine and ffmpeg build) |

### Frame-number check (where the clip sits in the render)

| | `dissolve_s = 0` | `dissolve_s = 0.5` |
|---|---|---|
| Output | 1920×1080, 30 fps, 720 frames, 24.000 s | same |
| Clip | 240 frames (8.0 s) | 255 frames (8.5 s) |
| Pure board frames in the render | 270 to 509 (240 frames) | 277 to 503 (227 frames; the rest are the dissolve) |
| Codes read back | 0 to 239, every step exactly +1 | 14 to 240, every step exactly +1 |
| Constant offset (video frame minus clip frame) | 270 → clip frame 0 at **9.0000 s** (ideal 9.0) | 263 → clip frame 0 at **8.7667 s** (ideal 8.75) |

The clip is not slowed, skipped, repeated or drifting in either mode. In dissolve mode the pipeline places clip frame 0 on video frame 263, half a frame after the ideal 262.5, so cues can land up to one frame (33 ms) later than the builder's ideal plan.

### Cue landing (measured from the render's pixels, ±1 frame = ±33 ms)

| Cue | Word (start) | Planned onset | Detected, hard cut | Detected, dissolve | Latency after the word (hard / dissolve) |
|---|---|---|---|---|---|
| c1 type | "river" 9.494 s | 9.494 s (frame 285) | frame 285, 9.500 s | frame 286, 9.533 s | +0.006 s / +0.039 s |
| c2 pop | "Farmers" 11.400 s | 11.600 s (348) | frame 348, 11.600 s | frame 349, 11.633 s | +0.200 s / +0.233 s |
| c3 pop | "water" 12.576 s | 12.776 s (384) | frame 384, 12.800 s | frame 384, 12.800 s | +0.224 s / +0.224 s |
| c4 clear | next sentence starts 14.150 s | 14.150 s (425) | frame 425, 14.167 s | frame 425, 14.167 s | +0.017 s after the sentence start (both) |
| c5 title | "glaciers" 14.738 s | 14.838 s (446) | frame 446, 14.867 s | frame 446, 14.867 s | +0.129 s / +0.129 s |
| c6 type, finishes with its sentence | sentence ends 16.752 s | starts 16.052 s (482) | frame 482; complete at 16.733 s | frame 483; complete at 16.767 s | completes −0.019 s / +0.015 s from the sentence end |

- **Render versus the clip's own frame map: 0 frames of error for every cue in both modes** (`max_abs_frame_error_vs_clip_map` = 0). What the builder draws is what the render shows.
- **Render versus the builder's ideal plan:** 0 frames in hard-cut mode; 0 or +1 frame in dissolve mode (the half-frame rounding above).
- **Latency summary** (cues c1, c2, c3, c5; c6 starts later by design): min +0.006 s, max +0.224 s (hard cut); min +0.039 s, max +0.233 s (dissolve). 4 of 4 inside the scorecard's T08 window of 0 to +0.4 s. This restates the offsets chosen from the reference; the informative result is the zero-frame agreement above.
- The typed phrase that is meant to **finish with its sentence** finishes within 0.02 s of the sentence end in both modes. (My first measurement of this read past the clip's end and showed 0.25 s; the measurement code was wrong, not the builder. Fixed and the full verification re-run before these numbers were recorded.)
- The board is cleared at the next sentence start, within one frame.
- Evidence images: [cue_onsets_d0_0.jpg](builder_evidence/cue_onsets_d0_0.jpg) and [cue_onsets_d0_5.jpg](builder_evidence/cue_onsets_d0_5.jpg) (the frame before, at, and 3 frames after each cue's onset).

### Off-mode and protection (re-run before and after the builder work)

| Item | Result |
|---|---|
| HEAD | `42c4d17b0b999faad4255d79717cf2df8822ae90`, unchanged |
| Original fixture compiled: plan `af18e83be103debd…`, rows CSV `7e978d52b4dd3751…`, spec `ecf4b524b47307e8…` | identical before the builder work, after it, and at the start of the spike |
| `DEFAULT_SETTINGS`, `MODES`, `LAYER_TYPES`, `TRANSITIONS`, `SOURCES`, `settings.json`, `app.py`, `VideoGenerator.spec` | unchanged |
| 571 protected-scope files | no file changed |
| Files inside protected folders | 1,331 before and after; none added or removed |
| Manifest (`weather_protected.json`, 433 files) vs the files, my mirror of its hash check | 0 mismatches before and after |
| `git status` | identical before and after the builder work (only `?? explainer/` and `?? docs/explainer/` are new from this work; other sessions' changes are untouched) |
| Bytecode in new folders | none (everything ran with `-B -I`) |

The before and after snapshots are byte-identical ([offmode_before_builder.json](builder_evidence/offmode_before_builder.json), [offmode_after_builder.json](builder_evidence/offmode_after_builder.json), SHA-256 `b7082dcf9ff861766cd9…`). As in the spike report, this proves the existing path is unchanged; it does not exercise a future switch, because none exists.

## Files created

In the repository (new files only):
- `explainer/__init__.py`
- `explainer/board/__init__.py`, `explainer/board/cues.py`, `explainer/board/render.py`, `explainer/board/builder.py`
- `explainer/spike/verify_builder.py`; `explainer/spike/README.md` was extended (a file I created in the spike)
- `docs/explainer/explainer_builder_report.md` (this file)
- `docs/explainer/builder_evidence/`: `verify_builder.json`, `cue_onsets_d0_0.jpg`, `cue_onsets_d0_5.jpg`, `board_manifest_d0_0.json`, `board_manifest_d0_5.json`, `derived_plan_d0_0.json`, `offmode_before_builder.json`, `offmode_after_builder.json`, `guard_before_builder.json`, `guard_after_builder.json`

Outside the repository (session scratchpad): the clips and renders. Render hashes start `2544aa32730c…` (hard cut) and `6c637b61e908…` (dissolve); clips `139f20c311d4…` and `a83e8ba98dde…`.

**Protected files: untouched. `app.py`, `settings.json`, `VideoGenerator.spec` and both manifests: unmodified. Nothing staged, committed or pushed.** The only existing file read by the new package is `assets/fonts/Inter-Bold.ttf`, as a placeholder so text can be drawn; it was not copied and is not a font choice.

## Limits and what was not tested

1. **The narration was synthetic.** The word times were exact inputs, so this measures the builder and the pipeline, not real transcription error (Whisper word times are typically ±0.3 s). Sentence detection relies on punctuation on the words; the Phase 0 reference transcript did carry punctuation, but the builder has not been run on a real transcription of a real voice-over.
2. **Detection resolution is one frame (33 ms).** Pixel detection of onsets cannot say better than that.
3. **Placeholder look.** Plain circles and a bundled sans font. No narrator, icons, handwriting, board design, caption styling, or the reference's objects (scale, pyramid, scroll, calendar and so on).
4. **Layout is naive.** One slot per cue, no wrapping or fitting. A long phrase can run off the frame; this was not guarded.
5. **Only four cue kinds**, one clip per beat, and one board per beat: no multi-board beats, no cue sets across beats.
6. **Not wired in.** The plan fragment was spliced into the fixture by the verification script. Nothing in Hybrid or the app calls the builder, and nothing combines several board beats into a plan.
7. **Dissolve is plan-wide** (spike finding), so a plan that mixes board beats (hard cut) with real footage (dissolve) is still undecided.
8. **Audio was a tone with sound design off**; the mixer's treatment of board beats is untested. Audio duration stayed 24.000 s.
9. **Map-beat overlays** (narrator over a map, captions over a map) are still untested, as before.
10. **Determinism** was checked on one machine and one ffmpeg build.

## Smallest safe next step

Still inside `explainer/` and untouched protected files:

> Add a **plan-level splice helper** (pure data: a plan dict plus a list of board-beat specs, each with cues, in; a new plan dict out, with the footage beats replaced by builder clips and `dissolve_s` applied), validate its output with the existing `validate_plan`, and run the same off-mode snapshot. In the same step, run the builder on **real word timings** from a real transcription of a short voice-over you choose, to measure how real Whisper punctuation and word-time error change cue landing.

I have not started either and will not without your authorization. The one question that decides how far past this we can go without touching protected files is still the plan-wide `dissolve_s`: tell me if a plan-wide hard cut for Explainer videos is acceptable.
