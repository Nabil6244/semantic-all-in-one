# Real-material readiness gate (2026-10-23)

Input: user's North/South Korea script (timestamps removed, 147 words, `script.txt`), voiceover made with macOS `say` (default voice, 47.05 s) on the user's instruction, so it is **real narration timing from a TTS voice, not a human recording**.
Timing: `explainer/spike/transcribe_words.py` (faster-whisper `base`, cached model, offline). Director/render: a scratchpad copy of `quality_gate.py` pointing at this material (no repository code changed), reference look, offline map (`imagery=False`), unchanged `generate_hybrid_video`.
Script vs audio: difflib ratio 0.997; the only difference is the final "So," which Whisper dropped (146 of 147 words).

Measured: see `summary.json`, `report_korea.json`, `phrases_korea.txt`, `sheet_korea.jpg`, `frames/`.

## Narrow director correction (2026-10-23)
Tests first: `explainer/spike/test_director_real_material.py` (fixture `explainer/spike/fixtures/korea/`). Before the fix: 21 tests, 14 failed (`after/tests_before_fix.txt`). Two map-caption tests were added after that baseline run (23 total). After: 23 of 23 pass (`after/tests_after_fix.txt`); `verify_m4` still 253 of 253.
Changes (all under `explainer/director/`): `segment.py` (a word belongs to the sentence its midpoint is in), `select.py` (direction words are not places; yardstick mentions such as "the size of England" never trigger a map; `places_comparison` and `places_not_shown` in the report; a crash when the plan had exactly two beats, `groups[-2] += groups.pop()`), `lexicon.py` (function-word contractions, "same" may begin a phrase, direction words, comparison cues), `plan.py` (sentence ends bound map-caption and repair phrases; rescue hook; `rescued`/`lost` per board), `compose.py` (fields), `compose_ref.py` (`rescue_text_ref`, reference look only).
Before/after Korea: `after/before_after_frames.jpg`, `after/sheet_korea.jpg`, `after/frames/`.
