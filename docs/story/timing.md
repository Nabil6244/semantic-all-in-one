# story_align -- pictures appear when their words are spoken

File: `story_align.py` (repo root, stdlib only). Tests: `test_story_align.py`. Nothing in `video_generator.py` / `app.py` is edited.

## API
```python
import story_align as sa
aligned, audio_end, report = sa.align_story(rows, whisper_words, min_dur=1.2, log=print, fallback=None)
sa.compare(app_aligned, new_aligned)            # per-scene start/end shifts
sa.speech_window_check(rows, words, windows)    # share of each scene's heard words inside a (start, end) window
with sa.applied(vg):                             # vg = the video_generator module
    ...                                          # vg.align_rows (and app.py's vg.align_rows call) now use story_align
```
* Row contract = `video_generator.align_rows`: each aligned row is `dict(row)` + `start_time`, `end_time`, `confidence` (0..1; the app uses 1.0 / 0.0).
  Scenes tile the audio: first starts at 0, each starts where the previous ends, last ends at `audio_end`. Every scene is at least `min_dur` long.
* `report`: `coverage` (share of syllables heard), `rate_s_per_syllable`, `weak` (scene numbers with weak evidence), `scenes[]` (start, end, confidence,
  status heard/inferred/weak, coverage, reasons), `fallback` / `fallback_recommended`.
* `applied(vg)` wraps `vg.align_rows`; any exception (or an implausible result, see below) falls back to the original and logs why; the original is restored on exit.

## Method
1. Phonetic key per word: consonant skeleton; matras, nukta, nasal marks, aspiration, voicing (k/g, c/j, t/d, p/b/v, m/n) are ignored; Latin words are
   mapped onto the same alphabet (Amazon = अमेज़न ~ Whisper's आमजोन); repeated letters collapse (Whisper's "होगगगगग").
2. Candidates: every (script word, Whisper word) pair with key similarity >= 0.62 inside a time band, plus 1-2 / 2-1 merges (Whisper splits/joins words).
3. Heaviest monotonic chain of candidates where each consecutive pair is physically possible: the script syllables between two matches cannot be spoken
   faster than ~2x the median rate in the time the transcript gives. This is what stops a scene's last words from matching the next scene's first words.
4. Words nobody heard are placed between their heard neighbours by syllables (+ pause weight at `, ।  .`) with a speaking-rate prior; if the gap is far
   longer than the words need, the slack is parked at sentence ends (real silence), not spread over words.
5. Scene start = its first word - 0.2 s (clamped after the previous scene's last word start + 0.2); end = next scene's start.
6. Confidence = 0.15 + 0.55 * heard share + 0.3 if the first word (or the next) was heard. Fallback to the app's aligner if heard coverage < 25% or > 40% of
   scenes have implausible speaking rates (only when `fallback=` is passed; `applied()` always passes it).

## Result on hrt (32 scenes, 277 s, `out/puppet_cache/hrt_timing.json`)
App aligner: 18/32 anchored, scene 18 shown 158-165 s although spoken 145-154 s; scene 28 shown 252-257 s, spoken 229-239 s.
story_align: 614/734 words matched (82% of syllables), 2 weak scenes (3 and 22, both mostly dropped by Whisper). Runtime ~2 s.
Share of heard words inside the scene window: app 15/32 scenes >= 90% (337/608 words), story_align 32/32 (608/608). Semi-independent check with
`puppet_story.realign` (different DP): 15 -> 31 scenes >= 90% (scene 3, mostly unheard, is the one left).

## Weaknesses
* Evidence is Whisper only: a scene whose speech Whisper dropped completely (hrt scene 3, ~15 s) is placed by syllables, +-1-2 s.
* The "inside the window" verification shares its evidence with the aligner; the puppet_story check is the independent one.
* Whisper hallucinating a word that sounds like the previous scene's last word (hrt scene 4: आपको for उस) can shift a boundary by <= ~0.7 s.
* Digits are never matched (Whisper writes numbers as words or digits unpredictably); they only count as syllables.
* Long audio: cost ~ words x band (band capped at 120 s); a 10-minute script takes several seconds.
