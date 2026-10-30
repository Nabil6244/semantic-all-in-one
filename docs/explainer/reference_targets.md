# Reference targets (five Ethos history explainers)

Source: `report.md` per video, written 2026-10-29 from full-length scene-cut detection, 1 frame per 15 s contact sheets and 4 fps bursts. Videos: Russian Revolution (3WoNGoQFQeQ), Soviet Union vs Hitler (7E1wOxHCBiE), Dutch (II3GGCL4VMU), Mexican-American War (YUBqnFXCg98), Spanish Empire (zW6uJMCq9Nw). The cut counts are ffmpeg scene > 0.3 and under-count soft cuts. The layer shares are visual estimates from sampled frames.

| Measure | Reference range | Source values | Check |
|---|---|---|---|
| Median shot (s) | 4.0 to 5.9 | 5.0, 5.85, 4.0, 5.9, 4.38 | R01 |
| Cuts per minute | 7.8 to 12.6 | 10.4, 7.8, 12, 8.2, 12.6 | R02 |
| Longest shot (s) | at most 31, 90% under 20 | max 31, 47.6, 21 | R03 |
| Map share | 20 to 30% | 25, 30, 20, 25, 30 | R04 |
| Board (grey, mascot, props) share | 25 to 45% | 40, 25, 45, 30, 25 | R05 |
| Illustrated scene share | 25 to 35% | 25, rest, 35 | R06 |
| Archival share | 8 to 12% | 10, 12, 10, 10, 12 | R07 |
| Visible change in each 2 s window | at least 95% | one new thing every 1 to 3 s | R08 |
| Longest static run (s) | at most 3 | 4 to 6 s holds have internal motion | R09 |
| Cuts within 0.5 s of a sentence start | at least 50% | 56% within 0.5 s, 61% within 1 s | R10 |
| Labels short (words) | 80% at most 8 | typed word by word | R11 |
| Map beats name a place in the narration | 95% | place pin per noun | R12 |
| Archival beats have a matching subject | 100% | one card per named person or place | R13 |
| Host mascot present | 25 to 45% of runtime | recurring | R14 (not measurable until the overlay renders) |

Scored by `explainer/reference_score.py`: `python3 -m explainer.reference_score plan.json [--video v.mp4] [--words narration_words.json --offset 33.6]`. R13 and R14 are reported, not scored, until a human or the overlay supplies them.

## Validation set (saved word timings, `state/narration_words.json`)

| Narration | Kind | Length | Use |
|---|---|---|---|
| `Video_2026-10-29_043_saaaaad` (Venice) | history | 236 s | already used, 33.6 to 70 s slice |
| `Video_2026-10-29_045_YYttttt` (South Korea, 1960 onward) | history | 1154 s | slice 0 to 70 s, second history story |
| `Video_2026-10-29_046_sollar` (light across the universe) | science, no archival | 914 s | checks that fixes do not break non-history stories |

## Baseline: Venice 70 s render (2026-10-30)

Pass: R01 median 4.95 s, R02 12.0 cuts/min, R03 longest 6.7 s, R04 map 28%, R06 scenes 26%, R08 change 100% (loose), R09 static 0 s, R11 captions 100%.
Fail: R05 boards 47% (target 25 to 45), R07 archival 0% (target 8 to 12), R10 cuts near a clause start 31% (target 50).
