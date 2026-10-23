# Plan-level splice helper and real-timing test: report

Date: 2026-10-22. Scope: the next step from the builder report. **Part 1 (the splice helper) is built and verified. Part 2 (a real voice-over) has NOT been run yet: it is waiting for the file you will point me to.** A smoke test of the real-timing scripts was run on a locally generated text-to-speech narration (macOS `say`), clearly labelled below and not a substitute for your voice-over.
Nothing committed. Evidence: [splice_evidence/](splice_evidence/).

## What was built

| File | Role |
|---|---|
| [explainer/board/splice.py](../../explainer/board/splice.py) | `splice_board_beats(plan, specs, words, out_dir, sentences=…, dissolve_s=…, tail_frames=…, validate=…)`: plan dict + board-beat specs in, new plan dict out. Pure data, imports nothing from the application |
| [explainer/board/cues.py](../../explainer/board/cues.py) | Changed: sentence boundaries now come from a **given** list, else punctuation, else Hybrid's own pause rule (see finding 1) |
| [explainer/board/builder.py](../../explainer/board/builder.py) | Changed: `sentences=` and `tail_frames=` options; manifest records both |
| [explainer/spike/measure_render.py](../../explainer/spike/measure_render.py) | Read-back helpers (clip frame → video frame map, held and skipped frames, per-cue onset) |
| [explainer/spike/verify_splice.py](../../explainer/spike/verify_splice.py), [verify_tail_sweep.py](../../explainer/spike/verify_tail_sweep.py) | Splice and tail-frame verification |
| [explainer/spike/transcribe_words.py](../../explainer/spike/transcribe_words.py), [verify_real_voiceover.py](../../explainer/spike/verify_real_voiceover.py) | Real-timing scripts (offline faster-whisper; builder and splice on those words; word-time quality estimate) |

Splice rules (all tested): only a `footage` beat can become a board beat (a map beat's layers would be lost, so it is refused); nothing is drawn until every spec resolves (in strict mode a bad cue anywhere raises before any clip is encoded); the input plan is never modified; other beats are copied unchanged; `dissolve_s` must be given or already in the plan; an optional `validate` callable (the verification passes the real `validate_plan`) checks the result; notes say that `dissolve_s` is plan-wide.

## Findings that changed the design

1. **The application's words carry no punctuation.** `video_generator._transcribe_locked` returns normalised tokens (`split_words`): lower case, punctuation stripped. My builder from the previous step found sentence ends from punctuation, so it would have failed on real app data (it would have treated the whole narration as one sentence). The builder now takes sentence boundaries from, in order: a list passed by the caller (for example `hybrid.narration.build_sentences`, which is script-aligned when a script exists), punctuation if present, else the **same pause rule Hybrid uses** (a gap of at least 0.55 s after at least 5 words, or 32 words). Tested below: all sources give identical cue times on the test narration and on the smoke narration.
2. **The pipeline holds one frame mid-clip when the beat is not a whole number of frames.** In hard-cut mode, 2 of 5 board beats at non-frame-aligned times showed the clip's first frame held for an extra frame (the clip then lags the beat by one frame and the board runs one frame past the beat end). In the smoke test a held frame appeared in the middle of a clip. Adding **2 spare tail frames** removed every hold in both tests (details below).
3. **A one-frame ambiguity remains.** Cues land exactly where the clip's own frame map says (0 frames of error), but up to 1 frame (33 ms) later than the builder's ideal plan, because the pipeline rounds where a clip starts.

## Part 1 results: the splice helper

Test plan: five beats (map, **board**, map, **board**, map), 28 s, two board beats at 6.8 to 15.07 s and 17.83 to 24.83 s, 8 cues, our own narration. Both dissolve modes, rendered through the unmodified `generate_hybrid_video`, read back frame by frame.

| Check | Result |
|---|---|
| Sentence sources give identical cue onsets (punctuated words; normalised words with the pause fallback; with Hybrid's `build_sentences` pauses; with its script-aligned sentences) | PASS (4 of 4 equal, no problems) |
| Unknown beat refused, map beat refused, duplicate refused, missing `dissolve_s` refused | PASS |
| Strict mode stops before any clip is drawn (the output folder stays empty) | PASS |
| Non-strict mode records the problem and still builds both clips | PASS |
| Input plan not mutated; non-board beats unchanged; board beats point at the built clips | PASS |
| Spliced plan passes the real `validate_plan` and renders | PASS (hard cut and dissolve); my first run of this was refused by `validate_plan` because my own test plan had a marker outside its beat, which shows the `validate` hook works |
| Output | 1920×1080, 30 fps, 840 frames (28.0 s) |
| Two board runs found in the render | PASS, both modes |

| | Hard cut | Dissolve 0.5 s |
|---|---|---|
| Board 1 | video frames 204 to 452; clip frame 0 held for one frame (6.8 s is not frame-exact in floating point); codes step +1 otherwise | frames 211 to 445 pure; clip frame 0 at video frame 197; no hold |
| Board 2 | frames 535 to 744; no hold, no skip | frames 542 to 738; no hold |
| Cues measured | 7 | 7 |
| Detected vs the clip's frame map | 0 frames of error | 0 frames of error |
| Detected vs the builder's ideal plan | within 1 frame | within 1 frame |
| Latency after the anchor word | +0.021 to +0.244 s | +0.021 to +0.244 s |
| Typed phrase set to finish with its sentence | finishes −0.011 s from the sentence end | −0.011 s |

(A first version of that last cue anchored on the sentence's last word, so it could not finish before the sentence did; it finished 0.12 to 0.22 s late, as designed: a phrase starts no earlier than its word. The cue was re-anchored on an earlier word.)

## Tail-frame sweep

Five board beats at deliberately non-frame-aligned times (130.3, 130.9, 129.6, 136.2, 139.1 frames long), 32 s plan, four configurations ([verify_tail_sweep.json](splice_evidence/verify_tail_sweep.json)):

| Configuration | Boards with a held frame | Skipped frames | Max cue error vs clip map | Max cue error vs ideal plan |
|---|---|---|---|---|
| Hard cut, no tail | **2 of 5** (clip frame 0 held at video frames 571 and 757) | 0 | 0 | 1 frame |
| Hard cut, 2 tail frames | **0 of 5** | 0 | 0 | 1 frame (one board) |
| Dissolve, no tail | 0 of 5 | 0 | 0 | 1 frame |
| Dissolve, 2 tail frames | 0 of 5 | 0 | 0 | 1 frame |

So spare tail frames are a reliable fix for the hold in this sample (5 boards, one machine). **It is not made the default** until it has been tried on more beats and on real plans.

## Real word timings: smoke test on TTS (not your voice-over)

To be sure the real-timing scripts run end to end before using your file, I generated a 28.8 s narration with the local macOS `say` voice (nine sentences, 0.8 s pauses), transcribed it offline with the application's own approach (faster-whisper `base`, word timestamps, VAD, int8, decoded by ffmpeg to 16 kHz mono; model already cached, `HF_HUB_OFFLINE=1`), and ran the builder and splice on those words. The transcript has 76 words. A synthetic voice is cleaner than a human voice, so **these numbers are an upper bound on quality, not a result for real speech.**

| Check | Result |
|---|---|
| Whisper words carry punctuation in the raw form; the app-style form has none | both produced |
| Sentence sources on real Whisper words (raw punctuated; app-style with the pause fallback; app-style with Hybrid's `build_sentences`) | all three give identical cue onsets |
| Cue landing, hard cut, no tail | 5 cues, all detected, 0 frames vs clip map, ≤ 1 frame vs ideal plan; **one held frame mid-clip** at video frame 195 (clip frame 142) |
| Cue landing, dissolve | 0 held frames; 0 frames vs clip map; ≤ 1 frame vs ideal plan |
| Cue landing, hard cut, 2 tail frames | **0 held frames**, constant offset, **0 frames vs ideal plan** |
| Latency after anchor word (non-finishing cues) | +0.007 to +0.227 s |
| Typed phrase finishing with its sentence | +0.007 s from the sentence end |
| Word-time quality, rough proxy: audio energy onset minus Whisper start (8 words in the window) | mean −56 ms, median −115 ms, std 168 ms, max 235 ms |

The word-time quality figure uses a crude proxy (the first rise of the audio's energy envelope within ±0.25 s of the transcribed start). Word-initial sounds and coarticulation make it noisy, and n = 8, so treat it only as evidence that Whisper's starts can be a couple of tenths of a second from where the audio rises. The real voice-over test will have more words.

## Off-mode and protection

Re-run before and after the splice work ([offmode_before_splice.json](splice_evidence/offmode_before_splice.json), [offmode_after_splice.json](splice_evidence/offmode_after_splice.json): **byte-identical**).

| Item | Result |
|---|---|
| HEAD | `42c4d17b0b999faad4255d79717cf2df8822ae90`, unchanged |
| Original fixture compiled: plan `af18e83be103debd…`, rows `7e978d52b4dd3751…`, spec `ecf4b524b47307e8…` | identical to the start of the spike and to both earlier reports |
| `DEFAULT_SETTINGS`, `MODES`, `LAYER_TYPES`, `TRANSITIONS`, `SOURCES`, `settings.json`, `app.py`, `VideoGenerator.spec` | unchanged |
| 571 protected-scope files | none changed |
| Files in protected folders | 1,331 before and after, none added or removed |
| `weather_protected.json` (433 files) vs the files | 0 mismatches |
| `git status` | identical before and after (only `?? explainer/` and `?? docs/explainer/` are new from this work; other sessions' changes untouched) |
| Regression of the earlier builder verification (10 checks, both dissolve modes) | still passes; landing unchanged |
| Bytecode in new folders | none |

Nothing was committed, staged or pushed. No test suite was run. All media is local; the only network-capable component (NASA imagery) is switched off, and faster-whisper ran offline. The TTS audio is machine generated on this Mac.

## Files created (this step)

In the repository, new files only: `explainer/board/splice.py`; `explainer/spike/{measure_render,transcribe_words,verify_splice,verify_tail_sweep,verify_real_voiceover}.py`; `docs/explainer/explainer_splice_report.md`; `docs/explainer/splice_evidence/` (14 files). Existing files I had created in earlier steps and edited: `explainer/board/{cues,builder,__init__}.py`, `explainer/spike/README.md`. No protected file, `app.py`, `settings.json`, spec or manifest was touched.

## Limits

1. The real voice-over has not been tested. TTS is cleaner than human speech.
2. Window and cues for the real test are derived from the transcript by rule (second word, longest word, last words), so they exercise timing, not meaningful design.
3. `tail_frames=2` is demonstrated on 5 boards plus one smoke case on one machine; the default is unchanged.
4. A one-frame difference to the ideal plan remains in some cases (pipeline rounding).
5. Layout is still naive; only four cue kinds; one clip per beat; placeholder look.
6. Dissolve and hard cut are still plan-wide.
7. The splice helper takes a plan dict; nothing in the application calls it.
8. Audio mixing, narrator or captions over a map are still untested.

## What I need from you

The path to the voice-over (any common audio or video format; the first 30 to 90 seconds are enough, and I will use roughly a 10 to 14 s window of three sentences from it, cut into a scratch copy; your file is only read). If it contains a script, tell me where it is: Hybrid's sentence builder is more accurate with the script text than with the pause rule alone, and testing both is useful. Say if there is any audio I must not process locally.

I have not started the real voice-over run and will not touch your file until you point me to it.
