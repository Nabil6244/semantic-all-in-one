# kids_audio: preschool music and sound effects

A small, reusable audio engine for preschool videos. Everything is synthesised locally with numpy and ffmpeg: no downloads, no licences, no per-video sourcing. Nothing else in Semantic YT Studio imports it, and the 8 documentary tracks in `assets/music/` are untouched.

## Library (`library.py`, `synth.py`)

One musical identity: C major, I-V-vi-IV harmony, toy instruments (marimba, glockenspiel, ukulele pluck, soft bass, kick, snap, shaker), and a signature four-note motif every bed quotes.

| Beds (seamless loops) | Use |
|---|---|
| `playroom` | 104 bpm, ukulele strum, marimba motif, soft drums (default) |
| `calm` | 84 bpm, glockenspiel arpeggios, no drums |
| `sunny` | 112 bpm, brighter, for outdoor sets (auto for the park world) |

Effects: `pop`, `sparkle`, `chime`, `ding_1`..`ding_10` (climbing pentatonic, for counting), `success`, `drumroll`.

The library is written once to `kids_audio/library/` (git-ignored) and rebuilt only when `synth.py` or `library.py` change. Beds are written into a circular buffer and reverbed by circular convolution, so they loop with no gap or click by construction.

## Mixer (`mixer.py`)

`python3 -m kids_audio.mixer job.json`, see the docstring for the job format.

- Three buses: the voice (passed through untouched), the music bed and the effects.
- Music sits 12 dB under the voice in pauses and ducks a further 10 dB while she speaks (60 ms attack, 450 ms release, 50 ms lookahead), with fade in and out.
- Effects are levelled by peak (short sounds fall below loudness gating) and placed exactly on event times.
- One overall gain lands the mix at -14 LUFS; a peak guard on music and effects only keeps the sum under -1 dBFS.
- The report gives the voice-over-music margin during speech (median and worst 5%).

## In lessons

`node cartoon3d-engine/lesson.mjs --csv lesson.csv [--music auto|playroom|calm|sunny|off] [--sfx on|off]`

Events: toy appears → `pop`, counted item → `ding_n`, word card → `sparkle`, "Your turn" badge → `chime`, cheer line → `success` (in the gap before her words). With `--music off --sfx off` the old voice-only path runs unchanged.

Tests: `python3 -m pytest test_kids_audio.py`.

## Chants (`chant.py`)

`python3 -m kids_audio.chant job.json` re-times a spoken line so each word's audible onset lands on the beat: one word per beat, short words ("with me") share a beat, a sentence fills its bar, and a word too long for its slot is sped up (pitch kept, at most 1.7x). Beds record their tempo in the manifest so chants and music share one grid.

In lessons, a `chant` row (e.g. `chant,"One, two, three, four! Clap, clap, clap with me!"`) starts on a half-bar of the music, the 3D host claps on every beat, counted numbers ding, and the music ducks less (4 dB) so it carries the rhythm. Sample: `cartoon3d-engine/samples/chant_lesson.csv`.

Next: imported sung audio with automatic lip-sync.
