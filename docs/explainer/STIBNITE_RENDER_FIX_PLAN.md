# Explainer fix plan — from the Stibnite re-render (hidafjk, 2026-11-03)

Video: `VideoGenerator/Video_2026-11-03_003_hidafjk/final/hidafjk.mp4` (16:38), CSV `~/Downloads/stibnite_scenes.csv`.
Every fix is a general rule in code with a synthetic test, never tuned for this one video.
Order is by how much of the screen each fixes.

## 1. Scene CSV anchors collapse — the root cause of "soldiers everywhere" (biggest)

**Found:** `explainer/scene_csv.py:49` places each scene with
`clock.at(vo_anchor, advance=True, before=<previous anchor>)`. A scene CSV has no script text between
rows, so the clock expects each anchor about a second after the previous one. It then rejects the real match
(minutes later) as "not heard near where the script puts it".
Replayed on this run's words:

| scene | anchor actually heard at | where it was placed |
|---|---|---|
| 4 "By the 1930s" | 334 s | 94.5 s |
| 6 "Almost overnight" | 369 s | 95.4 s |
| 14 "Inside the mill" | 780 s | 105.3 s |
| 18 "During its first six years" (soldier, processing complex, 2032) | 945 s | **110 s → 998 s** |

Scenes 3–17 were squeezed into 92–110 s, and scene 18 covered the last 15 minutes. That's why 166 of the
187 Flow plates are "antimony processing complex, Stibnite, around 2032, people: soldier". It also explains the
military crates in the 1890s, WWII, salmon, tribe and courthouse stretches, and the near-identical
snowy look for 14 minutes.

**Fix:**
- In a scene CSV, search for each anchor forward from the previous scene's start over the whole remaining
  transcript. Take the first fuzzy match, without a "near the predicted time" window. Keep the order rule
  (never before the previous scene).
- Number-word matching for anchors: "Sixty-five hundred feet" ↔ "6500 feet" / "65 hundred",
  "eighty" ↔ "80", "isn't" ↔ "is not". Those three anchors weren't found at all.
- Guard: if any scene note ends up covering more than ~3× the median scene length, or more than 40% of the
  video, log it loudly and fall back to an even split between the neighbouring found anchors. Never let
  one note take over the rest of the video.
- Test: a synthetic 18-scene CSV and transcript where anchors are minutes apart. Every scene start is
  within 1 s of its anchor, and no note covers more than its own stretch.

This one fix should remove issue 1 entirely and most of the "same picture" sameness.

## 2. Phrases cut mid-thought on screen

Examples: "obscure element buried on the", "bottom of a", "becomes", "after", "heavy concentrations of",
"makes Stibnite unique in", "America remains dangerously". The 63c0d1b rule (never stop before
to/so/than/that/of) covers only some endings.
**Fix (director/segment.py phrase picker):** a phrase may not end on a determiner, preposition,
auxiliary, conjunction or a bare adjective/adverb (the/a/an/on/in/into/at/with/for/after/before/becomes/remains/is/are/
dangerously…). Extend it to the clause end, or drop the text. A 1-word phrase is shown only if it's a
noun/name/number. Test: a list of real cut-offs from this video must all extend or drop.

## 3. Numbers and charts

- Broken values: "0 metric", "300 0 ounces", "187 per", "covers about 18" / "supply 35" (lost %).
  **Fix (compose_numbers / _stats_for):** join spoken number parts before display ("three hundred
  thousand" → 300,000). Keep "percent" → "%". Drop a badge whose value is 0 or whose unit is a bare
  "per". Year badges keep the "s" ("70-year", not "70 year").
- Bar charts that compare unlike things: "1 national vs 100 tons", "10 left vs 5 million tons",
  "4 Stibnites vs 8 million ounces", "6 feet vs 500 feet" + River icon, "impressive / grams / first".
  **Fix:** a comparison chart needs at least 2 values with the **same unit**, and labels that are nouns
  from the sentence (not "left", "national", "impressive", "first"). Otherwise show a single number card.
- Test: synthetic sentences for each bad case → no chart, or a correct one.

## 4. Crowd of little people used for non-people numbers

"40 million" (dollars), "9 billion financing", "80 years", "20 miles", "15 year", "25 year", "63".
**Fix (lexicon_v2.crowd_for):** a crowd only when the number counts people (people/workers/
miners/residents/soldiers/jobs follow the number). Money uses a coin/stack icon, years a calendar,
distance a road/ruler. Test: each case above gets the right prop.

## 5. Wrong icons and stamps

- Crossed swords for "war production board", "crushed ore", "ground in Idaho"; a "states" building for
  "America's only reserve" / "Bank of the United States"; a key for "peace returned".
- Stamps that misread the narration: "LIES" from "lies a canyon", "ENOUGH" from "enough to drive",
  "BANKRUPT" is fine.
  **Fix:** an icon or stamp fires only on a word used in its sense. "battle/war" icons need a
  war noun next to them, not "ground"/"ore". "lies" as a verb of place ("lies a canyon") never stamps.
  "enough" never stamps. Use the part-of-speech/sense check the lexicon already uses for labels.
  Test: a phrase list with expected icon or none.

## 6. Speech bubbles that don't fit

"Wall street headlines of lithium!" from three cartoon kids. "Bottom of the yellow pine!" from a worker.
**Fix (compose_dialogue):** a bubble only for quoted speech or a line a person in the scene would say.
Never narration about headlines/places turned into an exclamation. Test: both lines produce no
bubble.

## 7. Misheard words shown as captions

"indium antimonyde", "giant deuterine pumps", "art tailings storage facility armored".
**Fix:** before a transcript word goes on screen, correct it against the script text and the CSV vocabulary
(the `vocab_casing` fuzzy match, extended from casing to spelling, for words ≥ 6 letters within edit
distance 2). "Dry-stack" / "dewatering" / "antimonide" come from the script. When no script is
supplied, low-confidence words aren't shown as captions.

## 8. Empty paper screens

Plain paper with only the presenter (or nothing) at ~1:16, 4:28, 7:04, 11:28, 12:24, 15:04. Paper is about a quarter
of the video. **Fix:** a board beat must show at least one element (phrase, number, icon or plate).
If all are rejected by the rules above, it keeps the previous plate or uses a CSV scene plate, never a blank page.
Cap paper-only beats to ~10%, and never two in a row. This matters more once fixes 2–5 drop
more bad text. Test: a plan check counts blank board beats.

## 9. Three-panel background with hard seams (~10:40–11:40, ~15:40–16:10)

The plate looks like three stitched slices that don't line up. **Find first:** whether these are a "split"
layout in compose_fill/compose_recipes or a Flow picture that came back as a triptych. If layout,
add a soft edge or a gutter and only use it with three different pictures. If Flow, add "single continuous
scene, no panels" to the plate prompt and reject panelled returns (vertical edge check).

## 10. Opening globe on Europe

The first frame is a globe centred on Europe for a US story. **Fix:** the opening camera starts on the
story's home region (first CSV region / most-named country), not a fixed "continental Europe".

## 11. Quiet audio — -22.7 LUFS

YouTube plays at about -14. **Fix:** the Explainer/Hybrid final mix is normalised to -14 LUFS, -1 dBTP,
like the Review QA fix did for What If styles. One shared helper, not a second copy.

## 12. Text polish

Mixed "america"/"America", and "next week were uncovering". Sentence-case names through the
existing casing pass. Restore apostrophes from the script ("we're") when the transcript drops them.

---

### Suggested order of work
1 → 2 → 3/4 → 5/6 → 8 → 7 → 9 → 11 → 10 → 12.
Fix 1 alone changes most of the look, so it's worth a re-render (your call) before tuning 2–8.
Touched tests only, per change.
