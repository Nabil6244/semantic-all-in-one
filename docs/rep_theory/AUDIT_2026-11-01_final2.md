# Rep Theory render audit: `053_gyym/final/final 2.mp4` (first render after commit 519dda3)

Same script and CSV (`scenes_manga.csv`) as the earlier 053 renders. Frames every 2 s, the render report
(`final 2.mp4.rep_theory.json`) and the log were read; nothing was changed.

## Numbers

| | Old render `gyym.mp4` | New `final 2.mp4` | Reference |
|---|---|---|---|
| Scenes | 38 | 40 | 115 in 8 min |
| Flow pictures on screen | 6 scenes | 26 scenes | ~50% of time |
| Text-only screens | 9 (takeaway + callout) | 2 | 0 |
| On-screen events / min | 28 | 68 | 45 |
| Frames moving | 85% | 90% | 65% |
| Body-part glows planned | 33 | 33 | |
| …of them drawn | ~29 | **~15** (18 picture scenes carry glows that are never drawn) | |

## 1. Old things that were skipped

The new full-frame picture scenes (26 of 40) draw the picture, the camera move and the words, and nothing else.
Every "state on the picture" from the Isometric Holds study (UPGRADE_LIST.md 5b) was built for the library figure,
poses and the anatomy plate, so it disappears whenever a scene becomes a Flow picture:

- **Highlight on mention**: 18 picture scenes have glows planned ("names a body part: the figure, with it lit"
  appears in the log) that are never drawn.
- **Rings on the joint named, leader-line labels, force arrows**: none on any Flow picture. The reference puts
  them on its pictures (BIGGER, GIANT BICEP, FOREARM/WRIST labels, rings, arrows).
- **The anatomy plate's step-by-step states** (TENDONS → HANDS → WRIST lighting in turn, light sweep): went from
  9 scenes to 2. Removing the repeats was right, but its job (showing *which part* on each word) did not move to the
  pictures.
- **Slot labels**: the CSV put "The go. / The wrist. / The squeeze. / And the line." on their own rows, so the slots card
  only got numbers 1-4, no names. The empty dashed slots are drawn too dark to see.
- **Number shown with the number word**: "about five kilos" used to be a 5 KG ring; now the number is a faint grey
  ghost under the headline on the picture.
- **Nine card looks from the CSV still rejected** (race, study, promise, checklist, engage, stat), so those
  sentences fell back to a picture drawn from the words. Two of those pictures are wrong for the sentence: "Researchers
  watched seventy-four of them" became the trainee kneeling with a red stomach, and "sixteen trained men" / "thirty
  percent" became calf-muscle drawings.
- **Weak leftovers that were there before**: "THE GO" on the bare standing figure, "HOW HEAVY" alone on an empty
  frame.

## 2. Too much zoom

Measured on every picture scene from the render report (how much of the Flow picture is on screen):

| Framing | Share of the picture visible (start → end of shot) | Height cut at the end |
|---|---|---|
| wide, full frame | 99% → 67% | 18% |
| wide, panel | 63% → 43% | 18% |
| medium | 39-61% → 29-45% | 32% |
| close | 21-32% → **17-26%** | **49%** |

Median: **43% of each picture is visible by the end of its shot**; 8 of 26 shots show under a quarter of the picture.

Why:
1. **The push is too strong for these pictures.** Wide pushes 1.00 → 1.22, close starts at 1.75 and ends at 1.95.
   The reference's pictures have lots of black space around a small subject, so a 25% push loses only background.
   Flow's pictures fill the frame edge to edge, so the same push cuts heads, hands and the table.
2. **Panel mode crops twice.** When the picture has no empty side (13 of 26 shots), it is set in 64% of the width at
   full height. That cover-crops a 16:9 picture to a near-square *before* the zoom (only 63% visible on frame 1).
3. **Close-ups stack on top.** The CSV asked for "close" / "close red" on 9 rows (the prompt teaches it), and the
   re-framing rule adds more. Close at 1.75-1.95 inside a panel shows about a sixth of the picture: a bicep filling
   the frame, two clasped fists with no arms, a forearm with no hand.
4. **The focus point is the red paint or "the other side of the subject"**, not the face or the action, so close
   shots land on odd fragments.

## 3. Everything we already had: kept, weakened or dropped

Measured on all 14 test scripts, planner before commit 519dda3 vs now (share of video time per look; overlays counted
per scene), plus a read of the drawing code.

| Existing feature | Before | Now | Why |
|---|---|---|---|
| Body-part highlight on the word | 158 planned, 9 not drawn | 157 planned, **57 not drawn (36%)** | full-frame pictures draw no glows |
| Red background tint (warning, mistake, pain) | 34, 5 hidden | 33, **15 hidden** | the tint is drawn first, then the full-frame picture is pasted over it |
| Body gains / leans out on "bulk" / "lose fat" | 5 | 10 planned, **7 not drawn** | only the standing figure can morph |
| Standing figure with the part lit | 13.4% of time | **3.6%** | its score was lowered whenever pictures are on |
| Pose library (28 poses of the one character) | 12.5% | 8.1% (**0 in the 053 render**) | the CSV now directs a Flow picture on almost every row, so the app's pose choice never runs |
| Forearm/anatomy plate with step-by-step states + light sweep | 11.6% | **4.0%** | 30 s repeat rule + long scenes split; its job did not move to the pictures |
| Question bubble / checklist / dial / graph / myth / calendar / steps cards | 3.1 / 2.8 / 1.7 / 1.7 / 1.3 / 0.7 / 0.6% | 1.5 / 2.0 / 0.9 / 0.7 / 0.6 / 0.3 / 0.3% | a card used in the last 3 scenes now loses to a Flow picture (before it beat the plain figure) |
| Takeaway card (word-by-word key line) | 0.4% | **0** | switched off whenever pictures are on |
| Realistic anatomy pictures (tendon into bone etc.) | REAL_STYLE prompt | replaced by an ink sketch prompt | prompt change; also every old cached picture has a new id, so none are reused |
| Stamps, NEXT teaser, chapter card + streak wipe, safety chip, lock, section tag, PART n/N, stopwatch | drawn | drawn | these sit on top of every scene kind: kept |
| 3D clips, stat ring, mistake, versus, bars, engage, study | — | about the same | kept |
| Whole-scene push + drift | every scene | not on full-frame pictures (their own camera replaces it) | by design |
| CSV prompt | "direct about one row in three, the app chooses the rest" | "direct every row" | so the app's grounded choices (pose for an action, figure with the part lit, plate, cards from sentence shape) are overruled by the CSV |
| Headline picking | — | stricter (no "I'LL TELL" fragments) | some scenes now have no headline instead of a fragment: intended |

In short: the new picture scenes replaced the older looks instead of carrying their overlays, the CSV prompt now
overrules the app's own choices on every row, and three things drawn under the picture (tint, glows, body morph)
are hidden by it.

## What to fix (proposal, not done)

0. Keep everything we had: overlays (glows, labels, rings, morph-equivalent, tint) drawn *on top of* the Flow
   picture; poses / figure / plate / cards stay in the rotation (a picture is one look among them, not the default for
   every row); the CSV prompt goes back to directing the important rows and leaves the rest to the app; takeaway
   allowed again for the final line.

1. Draw the existing overlays on Flow pictures too: the planned glows as a soft highlight + leader label at the
   body part, rings on joints named, arrows. Where the part is in the picture comes from its red paint (already
   found by `picture.study`) or, without red, a label in the free space pointing at the subject.
2. Zoom: fit the whole picture first (contain, not cover), push at most ~8-12% on wide, medium at most ~1.25,
   close at most ~1.45, and never cut the top of the subject (keep the head in frame). Panel mode should *contain*
   the picture in its 64%, not crop it.
3. Slots: take the item names from the short rows that follow a slots row (the CSV pattern the prompt itself
   suggests), and draw the empty slots brighter.
4. Show a stated number as a value chip / small ring beside the picture, not a faint ghost.
5. Make the rejected card detectors accept the CSV's sentences (number words, "researchers watched N", "I'll tell
   you … at the end"), and fix the log message.
6. CSV prompt: "close" only for a part that is small in the picture; never two close rows in a row.

## Done (2026-11-01, after this audit; not yet rendered)

- Zoom: wide 1.00 → 1.10, medium 1.12 → 1.25, close 1.30 → 1.45; wide and medium never cut above the subject's head;
  the half-width panel fits the whole picture instead of cropping it; a repeated picture goes medium first and never
  two close shots in a row. Measured on the final 2 pictures: faces and hands stay in.
- On pictures: the planned body-part highlight (glow + ring + leader label on a dark plate), the warning tint (lighter,
  over the picture), and the body change ("BIGGER" / "LEANER" arrow).
- Rotation: a Flow picture is one look among the others again (pose, figure with the part lit, plate, cards); the
  figure's score is back to what it was. Takeaway stays off only when Flow is on.
- Slots take their names from the short rows after the count; empty slots are visible.
- Card detectors accept the CSV's sentences (race, study, promise without numbers, comma lists, "linked below");
  the log says what each look needs; on_screen accepts hyphenated words; a chip alone becomes the headline.
- The shared CSV aligner ignores apostrophes and matches spelled numbers to digits (98-99% matched on this CSV,
  was 94%); "I'll show you" and "It's called" no longer start one word late.
- The app's own anatomy pictures use the old realistic prompt again (same wording, so earlier pictures are reused).
- CSV prompt: direct the rows that matter (about half), leave the rest to the app; close only for small parts.
