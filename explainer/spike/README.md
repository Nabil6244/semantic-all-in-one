# Explainer spike (Path A feasibility)

Isolated feasibility spike for the Explainer style. Nothing here is imported by the application, nothing here edits a protected file,
and nothing here is wired to a switch. Scripts read the repository (never write to it) and write their outputs outside it.

- `offmode_snapshot.py`  snapshot of how the UNMODIFIED Hybrid path compiles the original fixture, plus protected-scope hashes (Q3)
- `make_board_clip.py`   placeholder grey-board clip with burned-in frame numbers (Q1, Q2)
- `make_audio.py`        synthetic narration with a tone and a click every second (audio continuity)
- `run_spike.py`         renders the 24 s fixture offline through generate_hybrid_video with the board clip as a footage beat
- `analyze.py`           frame, timing and audio checks on the renders

Report: docs/explainer/explainer_spike_report.md

Builder stage (word-timed board clips):
- `../board/`            the builder: `cues.py` (cue model, resolution against word times), `render.py` (placeholder drawing + encode), `builder.py` (`build_board_clip`)
- `verify_builder.py`    builds clips from word-timed cues, renders them through the unmodified Hybrid pipeline in both dissolve modes, measures where each cue lands

Report: docs/explainer/explainer_builder_report.md

Splice stage (plan-level, real timings):
- `../board/splice.py`           `splice_board_beats`: plan dict + board-beat specs + words in, new plan dict out (pure data)
- `measure_render.py`            read-back helpers for instrumented board clips
- `verify_splice.py`             two board beats in a five-beat plan, both dissolve modes, rules and sentence-source checks
- `verify_tail_sweep.py`         five non-frame-aligned board beats, tail_frames 0 and 2, hard cut and dissolve
- `transcribe_words.py`          offline faster-whisper word timings, raw and application-style
- `verify_real_voiceover.py`     builder + splice on real word timings, plus a word-time quality estimate

Report: docs/explainer/explainer_splice_report.md
