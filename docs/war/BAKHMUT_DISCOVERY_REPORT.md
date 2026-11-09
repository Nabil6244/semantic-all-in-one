# Bakhmut — Footage Director discovery report (dry run, no render) — 2026-11-09

Script: `~/Downloads/VideoGenerator/Video_2026-11-09_040_bakhmut_director/csv/bakhmut_war.csv` (18 scenes, 1:35 Edge voiceover).
Dry run = real searches, metadata and storyboard frames; capture replaced by a stub (age-restricted videos simulated as refused, as the real
capture browser refuses them). Full report JSON: `discovery_report_dryrun.json` in the project folder. Verdicts below are mine, from the
storyboard frames inside each chosen window.

## Result

| | Render 040 (before) | Dry run now |
|---|---|---|
| footage scenes with a clip | 0 of 10 | **9 of 10** |
| exact / contextual / atmospheric | 0 / 0 / 0 | **5 / 4 / 0** |
| verdicts (match / partial / wrong) | — | **6 / 2 / 1** |
| repeats, non-footage clips, footage on claim/stat/question scenes | — | 0 / 0 / 0 |
| clips with full provenance | — | 9 of 9 |

| Scene | Narration (short) | Pick | Level | Verdict |
|---|---|---|---|---|
| 001 | Prigozhin said his fighters took Bakhmut | Guardian News: Wagner fighters lined up in Prigozhin's video | contextual | match |
| 004 | The battle began in summer 2022 | ABC News: drone footage of the Bakhmut battle | contextual | match |
| 006 | Wagner recruited prisoners | CNN: studio split screen beside an unrelated story | exact (title) | **wrong** |
| 007 | Its fighters attacked street by street | France 24: Bakhmut street with soldiers, reporter box in a corner | contextual | partial |
| 008 | Ukrainian soldiers called it a meat grinder | BBC News: Ukrainian soldiers in the field | exact | match |
| 009 | Zelensky visited troops in Bakhmut | Times Radio: Zelensky with troops in Bakhmut | exact | match |
| 010 | He gave Congress a flag signed by soldiers | AP Archive: Ukrainian soldiers at Bakhmut | contextual | partial |
| 011 | Prigozhin among the bodies, blamed Moscow | none passed (Reuters re-uploads dated 2026, age-restricted originals) | — | map |
| 014 | Ukraine retook Andriivka and Klishchiivka | AP Archive: aerial of a retaken village | exact | match |
| 016 | A month later Wagner marched on Moscow | WSJ: Moscow street with a military truck on the mutiny night | exact | match |

The other 8 scenes are claims, statistics, questions or transitions and get War graphics by design.

## What changed (all War-only files)

1. **Narrative classification** (`narration_read.py`): past-tense actions by a named actor or group are events (visited, gave, recruited,
   attacked, marched, retook …); names no catalogue knows (Prigozhin, Wagner Group, Congress) are actors and search terms; pronouns
   (its / he) take the previous actor; a group subject ("Ukrainian soldiers …") gets subject footage; the story's place carries into
   sentences that do not repeat it ("Its fighters …" → Bakhmut); nationality words are not places; durations are not statistics.
2. **Dates**: months only as capitalised whole words ("marched" ≠ March, "may" ≠ May); seasons ("summer of 2022"); "since December" in a May
   2023 story is December 2022; relative dates ("the next day", "a month later") are resolved but marked `relative`, carried dates
   `carried`; only `stated` dates may reject footage.
3. **Historical context** (`director_rules.py`, `director_authenticity.py`): event date, upload date and film date are separate. The story
   period comes from the script's stated dates (here June 2022 – Oct 2023). Earlier footage of the story's own place is kept as
   *contextual* instead of rejected; the "years away from the film" rule applies only to news scripts with no dated story; authenticity
   for contextual / carried-date scenes is judged against the story period.
4. **Age-restricted footage**: metadata failures that need a sign-in are recorded (`metadata_blocked`, content warning kept, e.g.
   "graphic content"); the candidate is previewed from YouTube's three thumbnails, classed **unverified** (never "irrelevant"), allowed for
   an event only from an agency/broadcaster, tried last, and a capture without a storyboard is checked on its own frames and trimmed to its
   longest cut-free stretch (≥ 3 s).
5. **Match levels**: every pick is exact / contextual / atmospheric; event scenes never take atmospheric footage; the report counts them.
6. **Frames**: a still presenter box beside moving pictures (news split screen) is studio, not footage.
7. **Grid / coverage** (other agent, `direction.py`, `cards_motion.py`, `integration.py`): root causes in render 040 — a corner stamp card
   alone on the plate after a map ended (0:06.7–0:11.1), transparent big-number and stat-split cards drawn on the plate (0:24.8–0:31.1,
   1:04.8–1:10.1). New final pass covers any such span (motion card, opaque `kit_field` under transparent cards, neighbour hold);
   `direction.uncovered_spans()` is the plan-level check. Rebuilt Bakhmut plan: 0 uncovered spans.
8. **Short shots**: footage shots ≥ 3 s except the montage hook; tested on tiny real renders through `render_qa`.

## Tests

War suite: **622 passed**, 1 skipped. New: Bakhmut regression tests (classification, actors, carried place, March/marched, relative and
"since" dates, durations), historical/contextual and age-restricted tests, thumbnail window and trim, split-screen, coverage tests with two
tiny renders (0 s bare grid, no footage shot < 3 s). Bakhmut is in `test_fixtures/war_director_eval.json` (render 040, 18 scenes, judged picks).

## Known failures / unresolved

- **Scene 006 is wrong** (CNN studio split screen). The split-screen check catches it in some windows but not when the pictures beside the
  anchors barely move; no reliable threshold without hurting good clips (Times Radio, BBC score the same on footage share). Options: drop
  CNN "See what … said" anchor programmes by title pattern, or accept a graphic for that scene.
- **Age-restricted videos cannot be captured**: the shared capture browser is not signed in (tested: `age_restricted`). They stay
  unverified candidates in the report but never reach the film unless the capture browser is signed in (shared code / profile — needs your
  approval).
- Entity-named share is 5 of 10 (target 70 %): contextual picks name the place, not the sentence's own subject.
- Moment check is 0 of 9 here only because the dry run does not capture; the real run verifies every capture against the storyboard.
- `kit_field` (the new opaque card base) has been seen only in tiny test renders, not in a full film.
- Sparse map dip at 0:56.0–0:56.3 in render 040 was not reproduced in the plan (likely a dim map); not changed.
