# Addendum to the splice report: real-timing smoke test on a second synthetic narration

Date: 2026-10-22. Companion to [explainer_splice_report.md](explainer_splice_report.md), which is unchanged.

**This is a synthetic test: the narration is macOS `say`, voice Samantha, rate 165. It is NOT a human voice-over test.** Synthetic speech is cleaner than human speech, so these numbers are an upper bound on quality. Nothing was committed, staged or pushed. No code, fixture, protection manifest or setting was changed.

## Setup

| Item | Value |
|---|---|
| Script | Temporary, written for this test: 10 sentences about aqueducts (not kept in the repository) |
| Voice | `say -v Samantha -r 165`, with `[[slnc 800]]` (0.8 s) between sentences |
| Audio | 53.4 s, converted to 44.1 kHz WAV |
| Transcription | `explainer/spike/transcribe_words.py`, faster-whisper `base`, offline, word timestamps, VAD: 151 words, 151 app-style tokens |
| Run | `explainer/spike/verify_real_voiceover.py`, window start hint 12 s |
| Window | Hybrid sentence index 3 of 10; board beat 1.733 s to 15.9 s inside an 18.07 s cut taken at offset 15.667 s of the audio (about 3 sentences) |
| Render | Unmodified `generate_hybrid_video`, 1 board beat, offline |

A first attempt without the 0.8 s pauses found no window of three Hybrid sentences within 14 s (Hybrid's pause rule needs a gap of at least 0.55 s), so the script was re-read with pauses. This is a property of the test audio, not a defect found in the splice code.

## Results

| Variant | Runs | Held frames | Skipped frames | Max cue error vs clip map | Max cue error vs builder plan | Latency after anchor word |
|---|---|---|---|---|---|---|
| Hard cut (`dissolve_s` 0), no tail | 1 | 0 | 0 | 0 frames | 0 frames | +0.0203 to +0.207 s |
| Hard cut, `tail_frames` 2 | 1 | 0 | 0 | 0 frames | 0 frames | +0.0203 to +0.207 s |
| Dissolve 0.5 s, no tail | 1 | 0 | 0 | 0 frames | 1 frame | +0.0203 to +0.2403 s |

All three renders succeeded with no render errors; no cue went undetected. Hard-cut render: 542 video frames. Render time 8.1 s for the tail-2 variant.

### Sentence-boundary comparison (sample: the 10 Hybrid sentences of this narration)

| Source | Equal to Hybrid's sentences | Differences |
|---|---|---|
| Whisper-punctuated words | yes | none |
| App-style words with the pause fallback | yes | none |
| App-style words with Hybrid `build_sentences` given | yes | none |

### Word-time quality (rough proxy)

Audio energy onset minus Whisper start, n = **7** words: mean −82 ms, median −98 ms, std 135 ms, 90th percentile of absolute error 239 ms, max absolute 248 ms. Negative means the audio rises before the transcribed start. The proxy is crude (word-initial sounds and coarticulation) and n is small; it is not a measure of Whisper accuracy.

## Frame-alignment caveat

The earlier report found that a beat whose start or length is not a whole number of frames can show the clip's first frame held for one extra frame in hard-cut mode (2 of 5 boards in the tail sweep), fixed by 2 spare tail frames. **That problem did not appear here** (0 held frames in all three variants, including with no tail). This beat's times happened to fall in a way that caused no hold, so this run neither supports nor weakens the case for `tail_frames=2`. It remains opt-in; the default is unchanged.

The 1-frame difference to the builder plan in the dissolve variant is consistent with the pipeline-rounding ambiguity described in the splice report (finding 3).

## Not tested

- A human voice-over (messier word times, breaths, varying pace).
- A script-aligned sentence list from a real script file (Hybrid was given its pause-rule sentences only).
- Non-frame-aligned beat times on this audio, and more than one board beat per plan.
- Per-beat dissolve (`dissolve_s` is still plan-wide).
- Audio mixing, narrator or captions over a map, other voices or languages, larger Whisper models.
- Any run on another machine.
- The protection guard was not re-run for this addendum: other sessions have since modified protected-scope files and the manifest, so an earlier clean guard result no longer applies as-is.

## Where the temporary files are

Audio, transcript, renders and `verify_real_voiceover.json` are in the session scratchpad, **not in the repository**:
`/private/tmp/claude-501/-Users-muhammadnabil--claude-spares-spare-HI7QKl/528a896b-0d53-4c44-9a01-ed25459cb69e/scratchpad/real_vo/`
This path is specific to this Mac and session and may be cleaned up; it is not portable. To reproduce, regenerate the narration with `say`, then run the two scripts named above.
