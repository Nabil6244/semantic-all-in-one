# Rep Theory render audit: `Video_2026-11-01_053_gyym` (arm wrestling / tendons, 2:12)

Compared with the local reference *How Isometric Holds Give You Supernatural Strength (Full Guide)* (same first 2:12, and
the whole 14:15), measured the same way as in [UPGRADE_LIST.md](UPGRADE_LIST.md) section 1, plus the 9-video pattern study
in [PATTERNS.md](PATTERNS.md). I looked at a frame every 2 s of both videos and at single frames where something seemed off.

## Verdict

The **mechanics** now match the reference: sound, loudness, motion, chrome, typing text, NEXT teasers, the test with a
"comment your time" card, the parts tracker. The **picture choice** does not. About a third of the video is the same forearm
plate, two of the four 3D clips show the legs while the label says "Forearm", and the standing figure fills in whenever
nothing better is found. The reference shows *what the narrator is describing* (the hold, the two fighters, the test) and
puts its labels on that. We mostly show *the body part named in the sentence*. On a script where nearly every sentence
names a tendon, a hand or a wrist, that means the same plate over and over. Overall: roughly 6/10 against the reference.
In April that would have been 3/10.

## Numbers (first 2:12 of each)

| Measure | Ours | Reference 0-2:12 | Reference whole |
|---|---|---|---|
| Frames with movement | **85%** | 63% | 59% |
| On-screen events / min | 28 | **56** | 41 |
| Median gap between events | 1.5 s | **0.5 s** | 0.7 s |
| 90% of gaps under | 4.3 s | **2.4 s** | 3.4 s |
| Still runs ≥ 3 s | 0 | 1 | 13 |
| Loudness | -14.0 LUFS, LRA 2.1 | -14.4, LRA 2.7 | -14.3 |
| Silence | none | none | none |
| Screen filled, median / p10 | 11% / **3%** | 11% / 7% | 12% / 6% |

Sound and motion are solved. Cadence is about half the reference (fewer, bigger changes), and some frames are still
nearly empty (p10 3%: the "HOW HEAVY" chip alone, "I'LL TELL" alone).

## Time on screen by picture

| Picture | Seconds | Share |
|---|---|---|
| Forearm anatomy plate (as plate, stat backdrop or takeaway) | 47 | **36%** |
| Standing figure `rep_stand_v1` | 23 | 17% |
| Text-only callouts / takeaways | 21 | 16% |
| 3D body clips | 15 | 11% (2 of 4 framed wrong) |
| Flow pictures for this script (arm wrestle, table test, kneeling, tendon on bone) | 19 | **14%** |
| Stat / dial / engage cards | 8 | 6% |

The reference's first 2:12: about 70% character art in the actual pose being discussed, about 15% data/UI cards, and
one anatomy inset. Across the whole 14 min it reuses its single plate 4 times, each time in a different state. Ours shows
the forearm plate in about 10 separate scenes in 2 minutes, and usually looks the same each time.

## Defects, worst first

1. **3D "Forearm" shows the thighs** (0:06, 1:09, 1:10). Code fault in the asset build: `health_cinema/bench/prep_muscles.py:19`
   groups `"flexor digitorum"`, which also matches *flexor digitorum longus/brevis* in the leg and foot. So
   `anchors_gym.json → m_forearm_flexors` spans z 0.007-1.12 m (feet to elbow), with its centre at thigh height. The camera
   frames the legs, and the label line points at a thigh. The skeleton anchor `forearm_l/r` (z 0.85-1.11) is correct. Fix:
   match `flexor digitorum superficialis/profundus` only, then rebuild `body_gym.glb` and its anchors, and add a test that
   every muscle group's box fits inside its limb's skeleton box.
2. **One plate carries the video.** The forearm plate shows on 0:06-0:16, 0:18-0:22, 1:00, 1:22, 1:30-1:32 and 1:43-2:02
   (19 s in a row with only chips changing: "WHOEVER", "FAST", "TRAINED MEN"). Cause: a named body part sends the scene to
   anatomy, and the variety director leaves grounded looks alone ("looks grounded in the words are never moved"). Nothing
   limits how often the same plate comes back. A general rule is needed: a plate may return only in a new *state*
   (5b: light sweep, tendon recolour, threshold flip) and at most about once per 20-30 s. Otherwise the scene should go to
   the action the sentence describes (pose / Flow), or to a card.
3. **The opening 6 s is a wall of text.** "Training your tendons can make you win arm wrestles against guys way bigger than
   you" is the textbook face-off hook (PATTERNS 1a, and the channel's 3.9M video). The script even has the arm-wrestle
   picture, but it only shows up at 0:26. The reference opens on its strongest image within the first frame. The hook beat
   should get the face-off or the action picture, never a callout.
4. **The standing figure is a filler, and it lights the wrong part.** "ARM BREAKS", "FIRST SECOND" and "ARM WRESTLING"
   light the abs and waist. "BICEPS" lights nothing on the arms. Glows go on the figure even when the named part isn't
   visible or isn't mapped. Rule: no region match on this pose means no glow and no figure. Use the next look instead.
5. **Pose name leaks as a headline.** The table-test pose (which is correct: seated, hand hanging off the table) is captioned
   **"BAR HANG"** because the pose id is `rep_hang_v1`. Headlines must come from the script's words, never from asset names.
6. **Weak or misleading text.**
   - "I'LL TELL" (a dangling clause that passed the phrase filter).
   - "WARNING · KNUCKLES DROP" with a red background tint: this is a test instruction, not a danger. "stop the clock"
     tripped the warning shape.
   - "MISTAKE · FOUR MOMENTS".
   - "HOW HEAVY" chip alone on an empty frame.
   - "MUSCLE" over a 3D clip whose label says "Quads". The quads are correct ("they measured it in the thigh"), but the
     headline should have been "THIGH".
7. **No stopwatch for the test.** "Hold it there… the moment your knuckles drop, stop the clock" is exactly where the
   reference runs a live stopwatch through the hold, and that is its most memorable device. Our timeline card only fires on
   "N seconds in". "Stop the clock" or "time how long" should start a stopwatch.
8. **Number counters start at 0 on screen** ("0 KG", "0 WEEKS" visible for 1-2 s before rolling up). The reference rolls to
   the number on its word, so it is never caught showing a 0 the narrator didn't say. Start the count on the word, or start
   from a plausible lower value, not 0.
9. **Fewer things per scene.** The reference layers 3-6 elements onto one picture (stopwatch + sensation timeline + leader
   labels + toggle + stamp). Ours mostly swaps one chip for another. That is why our event rate is half of theirs even
   though our frames move more.

## What is genuinely good now

- Sound bed, sound effects and -14 LUFS: indistinguishable from the reference by measurement.
- Breadcrumb per part (TENDON BASICS → FOUR MOMENTS → THE CUP TEST → MOMENT 1: THE GO), PART n/4 tracker, NEXT teasers,
  streak wipe on the unit opener. This is the reference's chrome grammar.
- The Flow pictures for this script (arm wrestle face-off, seated table test, kneeling at the table, tendon into bone) are
  the best frames in the video and look like one character.
- The dial counts to 8/10 on "8 out of 10", the study line, the comment card on "comment your time", the red tint on
  "arm breaks": the right devices on the right sentences.
- No broken fragments of the old kind ("CANT", "SIX MONTHS GIVES"); apostrophes are kept.

## Suggested fix order (all general rules plus synthetic tests, nothing tuned to this video)

1. Rebuild the forearm muscle group (defect 1). It is a data fault and also hurts every grip, wrist or forearm script.
2. Plate repeat limit with state-or-switch (defect 2), and the hook beat never being a callout (defect 3). Add both to `topic_eval`:
   "longest run on one picture" and "same picture share".
3. Figure glow only on mapped, visible regions (defect 4); headlines never from asset ids (defect 5); text fixes (defect 6).
4. Stopwatch on "stop the clock / time it" (defect 7), counters not showing 0 (defect 8).
5. Layering: let a held picture take 3-6 overlays from the beat (defect 9). This is the main lever on cadence.

One caveat: the reference tests in `topic_eval` passed (picture share 94%) while this render is a third forearm plate. The
eval counts a picture as grounded when it matches a word. It does not penalise showing the same grounded picture ten
times, or a 3D framing that misses. Those two checks should go into the eval before any of the fixes.
