# Rep Theory upgrade list — frame-by-frame study of "How Isometric Holds Give You Supernatural Strength (Full Guide)"

Measured on 2026-10-31 from the 14:15 reference (720p60) and compared with our latest render
`Video_2026-10-30_046_gym/final/final 1.mp4` (2:07, 1080p24). Method: frame-change measurement every 0.1 s, cut detection,
a frame every 3 s across the whole video, frames every 0.2 s in two windows to read the animation, Whisper word timings
for the narration, loudness/silence measurement of the audio. Earlier channel-level study: [PATTERNS.md](PATTERNS.md).

Every item below is a pattern to adopt in code (a rule or a component), never a copy of this video's art or script.

---

## 0. Built for a new topic every day (applies to every step below)

The channel posts a new topic and a new script every day, so every visual must come from **that day's script**, not
from this reference. Today Rep Theory falls short of this: `reptheory/lexicon.py` knows 4 concepts (bottle, forearm,
cap, hang), and the only anatomy picture is the forearm plate. That is why the forearm showed up for food and sleep in
render 046. On a new topic most sentences would fall through to a generic callout.

**Rule 1: choose effects by what the sentence *does*, not by its topic words.** The effects in sections 4, 5 and 5b are
a grammar. Each one is triggered by a sentence shape that any fitness script has, whatever the topic:

| Sentence shape (any topic) | Effect family |
|---|---|
| A number that has to be reached ("at least 70%", "8 hours", "30 g of protein") | Meter or dial climbs; threshold flip with a ring pulse at the stated number |
| A named body part or organ ("your hamstrings", "your liver") | Highlight on mention on the figure or plate; leader label |
| Something hidden or invisible ("what you can't see", "inside your…") | Light-sweep recolour / X-ray state |
| Weak vs strong, off vs on, lazy vs hard | Greyed figure → full colour; toggle; whole-figure glow |
| A mistake ("the most common mistake", "don't…") | Wrong/right panels, red X, the faulty part flashes red |
| A sequence of steps or time marks ("10 seconds in… 20…") | Steps typing on; sensation timeline with a live stopwatch |
| A comparison of options | Spotlight one panel, dim the rest; bars or dots recoloured |
| A danger, limit or "your brain wants to quit" | Red background tint, returning to black when the idea ends |
| A study or year ("a review of 26 studies", "in the 70s") | Study card, rolling number or year, dot matrix |
| A viewer question | Chat bubble with a text marker on its key words |
| Relax / rest / cool down | Icy-blue state, needle drops to 0 |

Numbers, labels and thresholds are always read from the sentence. No reference value ("70%", "forearm", "push-up",
"26 studies") may appear as a constant in code. A test greps the package for them.

**Rule 2: a full body vocabulary, not a keyword list.** Replace the 4-concept lexicon with a body-region map that covers
the major muscles, joints, tendons and organs, with their synonyms. It applies to every figure pose, so any named part
can light up on any topic. Anatomy plates are only shown when the sentence names that part (fixes bug 2.3 for good).
Each library plate gets its skin, muscle and tendon masks made **once** so it can take any colour state.
Topic-specific objects come from the CSV `prompt` column or the library, never from this reference's pictures, and are
never generated per video by default (pictures are sourced once into the library, not per render).

**Rule 3: fresh across days, not only within one video.** The variety director already stops the same look running
twice in a row inside one video. It also needs a **channel history**: the last ~10 videos' looks, plates, poses, effect
combinations and layouts. Anything used recently is down-weighted, so Monday's and Tuesday's videos don't open with the same
move. Choices are seeded from the script text, so the same script renders the same way twice, but a new script gives a
new mix. Each component gets 2-4 layout and colour variants to rotate.

**Rule 4: structure is a scaffold, not this video's outline.** The "Full Guide" blueprint fits the number of units
the script actually has (3 tips, 6 holds, 10 foods). Unit slots that the script doesn't fill are skipped, never padded with
invented content.

**Rule 5: the CSV path stays first.** CSV direction columns still win. A CSV run still makes zero Gemini calls. The CSV
prompt teaches the script writer the sentence shapes in Rule 1 (state the number, name the body part, name the mistake)
so that any day's script gives the planner something to show. It never teaches this reference's script.

**Rule 6: measured on topics it has never seen.** Before any feature is built, a test set of ~12 synthetic scripts on
different topics (sleep, protein, back pain, running, grip, mobility, posture, hydration, fat loss, recovery, a
calisthenics skill, a supplement myth) plus render 046's script. Every step below must hold these numbers on all of them:
- grounded visuals ≥ 80% of scenes, generic fallbacks ≤ 10%
- no anatomy without a named part
- a state change on every picture held longer than 4 s
- no reference-only strings
- **cross-script overlap**: two different scripts share at most ~30% of their opening 60 s look and effect sequence

A feature that only looks good on the isometrics script fails.

**Built 2026-10-31.** Scripts: `test_fixtures/rep_theory_topics/*.txt`. Measure: `python -m reptheory.topic_eval`.
Floor: `test_rep_theory_topics.py` (numbers may only improve on `baseline.json`; after an improvement, run
`--write-baseline`). The run takes about 1 s and makes no render, Flow or network call. Baseline today, across 13 scripts:

| Measure | Now | Target |
|---|---|---|
| Time on a picture tied to the words | mean 65%, worst 48% (fitness-unrelated topics: recovery, fat loss, 046) | ≥ 80% on every script |
| Beats the planner couldn't ground | mean 17%, worst 38% (creatine) | ≤ 10% |
| Anatomy / 3D with no named body part | 13 scenes (046: forearm on "muscle is built from it", "muscle grows when you rest") | 0 |
| Time in still stretches > 4 s | mean 18% (046: 31%) | ≤ 5% |
| Scenes > 4 s with no change after they open | 6 | 0 |
| Opening-minute sameness between two different scripts | worst 75% (grip vs hip mobility both open 3D → Flow → callout → Flow) | ≤ 30% |
| Reference-video constants in code | 0 | 0 |

---

## 1. The numbers

| Measure | Reference | Our render | What it means |
|---|---|---|---|
| Hard cuts | 5.8 / min (one every ~10 s) | ~0 | The reference is NOT fast-cut. It keeps one shot and keeps changing what is in it. |
| Something new on screen | 42.5 / min, median gap **1.1 s**, 90% within 2.6 s | 28.8 / min, median 1.55 s, 90% within **4.5 s** | We need ~50% more on-screen events and no 4-5 s gaps. |
| Frames with movement | **57%** | 27% | Our screens sit still; theirs always drift, push in or animate. |
| Still stretches ≥ 3 s | 13 in 14 min | 6 in 2 min (≈ 40 per 14 min) | 3x too many still holds. |
| Longest still | 7.3 s (once) | 7.7 s | |
| Screen filled with content | median 12% | median 8%, p10 **3%** | Several of our frames are nearly empty (just an orange bar). |
| Narration speed | 178 words / min, pauses ≤ 2 s | — | Dense, tight voiceover. |
| Loudness | **-14.3 LUFS** (YouTube standard) | **-20.8 LUFS** | We are 6.5 dB too quiet. |
| Silence | never below -29 dB (music bed always on) | **26% of the video is digital silence** | We have no music, no ambience, no sound effects. |
| 3D | none | yes | The reference does it all with flat drawn art + code overlays. Keep 3D as our extra, used sparingly. |

---

## 2. Bugs found in our render (fix first: these are code faults, not taste)

1. **Headlines are broken fragments.** The headline extractor cuts 2-3 words out of the middle of a sentence:
   "LITTLE WEIGHT", "SIX MONTHS GIVES", "CANT SPOT REDUCED", "OUTPERFORM SIX BRUTAL", "INTENTION SLEEP", "WORKOUT BEATS", "DONT FEEL".
   A headline must be a complete phrase that means something on its own (a noun phrase, the instruction, or the number + unit), or nothing.
2. **Apostrophes lost** ("CANT", "DONT", "ISNT"): headlines are built from Whisper's lowercase words, not the CSV's own text. Use the CSV text for anything shown.
3. **Wrong picture for the topic**: the forearm anatomy plate is shown for food, sleep and body shape because the word "muscle" triggers anatomy. Anatomy needs a named body part, not the word "muscle".
4. **Same headline 3 scenes running** ("DONT FEEL" on scenes 27-29).
5. **Empty screens**: scene 19 ("eat slightly above") has no headline, no picture: only the orange bar for 2-3 s. Also visible at ~1:12, ~1:38, ~2:06. A scene must never render with nothing on it.
6. **No audio bed and -20.8 LUFS** (see 1).
7. **The character changes between scenes** (different trainee drawings, different hair/shorts). The reference uses ONE character in 30+ poses.

---

## 3. Structure of the video (script blueprint: "Full Guide")

| Time | Part | Length | What happens |
|---|---|---|---|
| 0:00 | Hook | 17 s | Skinny-vs-big face-off image, counter-intuitive claim, "by the end you'll know…", roadmap of 3 things (the holds, the one rule, a full week). |
| 0:17 | Premise / proof | 21 s | "A review of 26 studies…", one number (≈2% a week), the brain angle. |
| 0:38 | Hold 1 (+ the test) | 86 s | Unit + **"try it right now"** benchmark that is paid off at 13:19. |
| 2:04 | Hold 2 | 87 s | Unit + a science aside (angle specific) + **bonus** + **like CTA** woven in ("be honest, have you only done half squats? tap like"). |
| 3:31 | Hold 3 | 88 s | "The hold you asked for in the comments" + **subscribe CTA** woven in at 4:46. |
| 4:59 | Hold 4 | 89 s | |
| 6:28 | Hold 5 | 81 s | |
| 7:49 | Hold 6 | 75 s | |
| 9:04 | The Rule | 75 s | Effort as two dials, 3 mistakes, why it suits skinny guys, **callback to the thumbnail**. |
| 10:19 | Questions everyone asks | 96 s | 5 Q&A as chat bubbles + "the bonus nobody expects". |
| 11:55 | A week you can copy | 55 s | Calendar built day by day, 5-minute busy-day version, track your times. |
| 12:47 | What to expect + safety | 32 s | Two curves (nervous system fast, muscle/tendon slow), 12 weeks, 3 safety rules. |
| 13:19 | Your test result | 40 s | Payoff of the 0:38 test: dial + 4 tiers + "comment your time, retest in 4 weeks". |
| 13:59 | Close | 16 s | Hook image callback, community (phone mockup), one-line sign-off. |

**The unit template** (every hold, 75-90 s, same order, so the viewer learns the rhythm):
1. Teaser at the end of the previous unit: `NEXT` pill + ghosted next pose + one tease line ("the hold that feels like flying").
2. Title: `HOLD N` big, name types on underneath, breadcrumb at top-left switches to `HOLD N · NAME`.
3. Setup: numbered steps that appear **on the word** (①Stand on the middle ②Grab both ends ③Bend to 90°), rings/arrows on the body part each step names.
4. What works: the muscles glow on the same figure + leader-line labels (SHOULDERS / CHEST / TRICEPS) + "STRETCHED UNDER LOAD".
5. The feeling: a live stopwatch + a vertical sensation timeline (10 s arms shake → 20 s chest on fire → 30 s brain says quit) that fills in sync.
6. The cue: `THE CUE` label + a close-up of the body part + an action word in big type ("PUSH THE FLOOR AWAY", "GLUED").
7. Prescription: "20-30 s × 4 rounds", a chain of hold cards with rest connectors.
8. Easier / harder: a slider (EASIER ←→ HARDER) whose knob moves to the variation named ("on your knees", "+ a backpack").
9. The mistake: `THE MOST COMMON MISTAKE` + WRONG (red X) vs RIGHT side-by-side panels.
10. Optional: science aside (graph), bonus, a woven-in CTA.

**Script rules seen** (for the CSV/script prompt): second person; 5-16-word sentences; every unit has a cue, a number, a mistake and a progression; claims are followed by a named study card; one interactive test early, paid off near the end; CTAs are framed as part of the content ("comment your time, at the end I'll tell you what it means"); recurring signposts ("Here's the cue", "The most common mistake", "Not ready?", "When it gets easy").

---

## 4. Scene types used (component inventory)

Everything below is drawn in code on a black background over one consistent character, except where marked "art".

**Character & body**
- One trainee (white shorts outline style, orange shorts) in ~30 poses: push-up bottom, split squat, towel curl, doorway push, hollow body, tuck, handstand on wall, pike on chair, L-sit on chairs, standing front, side, close-ups (face sweating, hands on floor, feet). *(art, made once, reused for every video)*
- The big guy (grey tank top) for face-off scenes; group of 4 characters for the community scene. *(art)*
- Muscle glow painted on the exact region of the same figure (front thigh, chest, triceps, core) with **ember particles** rising from it.
- Leader lines from a body part to a small label (SHOULDERS, CHEST, TRICEPS, FRONT THIGH, GLUTES, NECK, RIBS IN).
- Rings that pop on a joint as it is named (elbows, hands, feet, neck) and arrows that show a force direction (push the floor, knees up, shoulders down).
- Lock icons on joints ("ARMS LOCKED"), a straight green alignment line along the body ("ONE STRAIGHT LINE"), a red curve for a bad shape ("BANANA BACK").
- Ghost / afterimage of the figure moving (drifting up, coming down slowly).
- Realistic anatomy plates as insets (chest muscle, forearm on rope with tendons, heart and lungs) connected by a dashed arc. *(art)*

**Data & science**
- Study card: paper with red header ("REVIEW · 26 STUDIES · Oranchuk et al. 2019"), a fan of 26 papers that counts up, a sticky note "1980 MORITANI & deVRIES".
- Line graphs that draw themselves and **morph** (strength vs squat depth; force vs time explosive vs gentle; two progress curves).
- Bar charts (strength through the move; blood-pressure drop by training type, horizontal).
- Dot matrix (90% vs 40% fibres switched on; 270 trials).
- Gauges / dials: effort dial 0-10 that sweeps, speedometer 0% → 34% → 100%, blood-pressure gauge, result dial with coloured tiers.
- Big number with unit and caption (`1.7% A WEEK`, `57%`, `270 TRIALS`).
- Battery icons (energy left), bathroom scale (how much you weigh on your hands), weight split bars (hands 35% / feet 65%).

**Instruction & UI**
- Live stopwatch (top right, counts the real seconds of the hold).
- Vertical sensation timeline (10 s / 20 s / 30 s with labels, orange → red).
- Difficulty slider EASIER ↔ HARDER with labelled stops (feet down / tuck / one leg / full).
- WRONG vs RIGHT panels (tilted cards, red X / green label).
- Toggle switch LAZY ↔ STRONG.
- Numbered checklist; checkmark list; 3 safety-rule warning cards stacked in; "3 mistakes" cards that flip and get X-stamped.
- Hold-card chain with rest connectors (4 × 20-30 s).
- Week calendar that fills day by day with pose icons, highlighted hard days, a total ("3 sessions · about 15 minutes each").
- 5:00 ring "BUSY DAY" with a 3-item checklist.
- Notebook (3D-looking) with week-by-week times and "+3 s".
- Angle dial (90° / 75° / 60° "your limit"), measurement marks ("1 FIST", "A LITTLE WIDER").
- Result board: dial + 4 tiers revealed one at a time, each with a pose icon and an instruction.

**Engagement mockups**
- YouTube comment box: typing dots → comment appears → highlighted ("please make one on overcoming isometrics"); later "36 seconds" + "4 weeks later: 51 seconds" reply.
- Like button press ("LIKED · MORE GUYS SEE THIS"), Subscribe button → "SUBSCRIBED" + bell.
- Locked list ("levels revealed AT THE END") = curiosity lock.
- Fan of the channel's video thumbnails; "our tendon video" card with play button; "THE THUMBNAIL" callback card.
- Chat-bubble questions with avatars (Q1-Q5) and a Q tracker (5 dots top-right) that fills.
- Phone mockup of the community group.

**Stamps & words**
- Rubber stamps that slam in, tilted: TEST, MORE FORCE, REAL STRENGTH (green), THE ZONE, FULL GUIDE, BONUS, GLUED, LOCKED, STARTER, 0 MOVEMENT, FIGHT, BURNOUT, THE PLAN MIXES BOTH, THAT'S NORMAL, 12 WEEKS.
- Big title with glitch / RGB-split entrance ("HOLD 3", "ISOMETRICS").
- Kicker + headline pairs ("THE KEY" / "ZERO → EVERYTHING"), colour contrast inside a headline ("ZERO→**EVERYTHING**").

**Persistent chrome**
- Breadcrumb top-left that changes per part (`ISOMETRICS · FULL GUIDE · AT HOME · NO WEIGHTS` → `HOLD 2 · DEEP SPLIT SQUAT` → `THE RULE · EFFORT` → `QUESTIONS EVERYONE ASKS`).
- Safety chip bottom-left during every hold ("⚠ BE SAFE · go slowly, stop if it hurts").
- Question tracker / hold stopwatch top-right.

**Real footage / photos**: one (gymnast photo inset). Under 1% of the runtime.

---

## 5. Motion and animation

- **Every shot moves**: a slow push-in (≈3-5% over the shot) on the figure; nothing is ever perfectly still.
- **Camera travels inside the shot**: punch in to the feet, pan up to the hands, pull back out (seen 3:45-3:51), instead of cutting.
- **Focus-pull transitions**: the old scene blurs and darkens while the new element comes in sharp; an info card appears over a blurred background.
- **Typewriter text** for titles and labels, letters landing with the words.
- **Pop-in** with a slight overshoot for rings, pills, checkmarks and icons; **slam-in** with a small shake for stamps.
- **Self-drawing** lines, arrows, curves, leader lines and dashed arcs.
- **Counters and needles** move live: stopwatch, dials, percentages, the "26" paper count.
- **Morphing** graphs (a curve changes shape as the narration changes the claim).
- **Glitch / RGB split** on unit titles, **ember particles** on burning muscles, **shake lines** on effort, **speed lines** on running.
- **Ghost / afterimage** to show movement direction without animation frames.
- **Layering**: a scene builds up 3-6 elements over 5-10 s, one on each stressed word, then clears for the next idea.
- Text lands on the word it belongs to (0-0.2 s ahead), measured on "HOLD 1" and the numbered steps.

## 5b. State changes on the same picture (colour, light, focus)

Missed in the first pass, because sampling every 3 s logs *what* is on screen, not how it changes. Found with two extra
scans: (a) pixels whose colour changes within 1 s while brightness and shape stay the same (9 moments), (b) 8×8 blocks
whose pattern stays the same while they brighten or dim, plus the tint of the dark background (72 + 22 moments). Every
moment was then checked as a before/after pair or at 0.25 s steps. The rule behind all of them: **the picture stays,
its state changes on the word**. One picture can carry 2-4 meanings this way, which is how the video gets ~1 change a
second with only ~6 cuts a minute.

**The forearm on the rope (one plate, used 4 times, a different state each time)**

| Time | Words | What happens |
|---|---|---|
| 1:58 | "your tendons stiffer" | Plate comes in blurred and sharpens (focus pull); red muscle fill grows brighter from the hand up; leader-line label "TENDONS" draws on; green "STIFFER" stamp slams in tilted. |
| 4:41 | "the strength you can't see" | Starts red-on-white. A glowing diagonal **light bar sweeps** across the arm; everything behind it turns **navy blue (skin) with the muscles still red** — an X-ray look. Headline types on as the bar passes. |
| 9:15 | "your tendons only change with hard holds" | Starts as a grey plate. A bright band **travels along the arm and only the tendons turn icy blue** where it has passed; label "TENDONS"; effort dial in the corner reads 3. |
| 9:18 | "at least 70% effort" | Dial needle climbs 3 → 5 → 6 → 7 on the words; the "40%" figure **rolls like a slot counter** 40 → 50 → 70; the instant it hits 70 the **whole arm flips blue → red in one frame**, the dial throws a **shockwave ring**, a red "70%" tick lights on the dial rim. |
| 11:00 | "the studies that change tendons" | Small grey thumbnail of the plate **turns red** when "tendons" is said; label draws on. |

**The same effects elsewhere (each is a reusable rule)**

1. **Light-sweep recolour** (4:41, 9:15): a soft bright bar crosses the picture; behind it the picture is in its new colour state. Used for "the hidden thing" reveals.
2. **Threshold flip** (9:18): a value climbs; when it crosses the number in the narration the subject snaps to the "working" colour with a ring pulse. Colour is the meaning: blue/grey = not enough, red = working.
3. **Highlight on mention** (1:01 chest, 2:04 legs, 2:28 front thigh, 5:36 lower back "ABS OFF", 6:44 shoulders, 8:27 shoulders orange on "push away", 11:00 tendons): the named body part fills with a glowing colour on the word, then pulses gently while it is talked about. Everything else stays white/grey.
4. **Whole-figure glow** (0:37 "fires everything": figure turns red with a lightning line from the brain; 10:01 green outline on "skinny guys"; 10:13 red-white aura on "every bit of you"; 4:13 figure turns **icy blue on "relax"** next to a blue 0% dial, after red 100% "all out").
5. **Greyed = weak / off** (1:07 lazy/strong toggle: figure desaturated on "lazy", colour back on "strong"; 10:13 "MORE MUSCLE" text fades to grey as it is argued against; previous headline line greys out when the next line types on, 2:19).
6. **Spotlight / dim the rest** (5:21 and 5:58 three panels: the one being named gets a white frame and full colour, the others drop to a red outline ghost; 6:24 figure shown as a red ghost outline before it is "revealed"; 7:46 black silhouette fills in to the drawn figure on "2 sturdy chairs").
7. **Danger tint of the background** (1:16 "30… your brain asks you to quit": black background warms to a red vignette, "QUIT?" bubble; 10:15 "SUPERNATURAL": red bloom behind both figures; 4:28 "your brain": red glow). The tint returns to black when the idea ends.
8. **Colour fill of meters** (0:21 force bar grey → red + "MORE FORCE" stamp; 3:34 raw-strength bar fills red to "MAX"; 8:06 hands 0% → 85% vs feet 100% → 20% bars move in opposite directions; 9:58 strength bar fills red "doesn't match your size"; 11:41 blood-pressure bars grow, isometrics red, others grey).
9. **Cell-by-cell recolour** (11:00 week boxes: green ticks turn to red "HARD" boxes one by one on Mon / Wed / Fri, Sat appears as a dashed "HARD?"; 11:36 dot matrix fills red dot by dot while "268" counts up; 10:28-10:40 bar chart: bars in white, then only the gaps fill red on "holds fill the gaps").
10. **Line colour as state** (6:06 breath line goes from a red flat line to a green small wave on "small breaths").
11. **Text marker highlight** (10:48 "bulky?", 11:06 "How long", 10:20 "replace weights?"): a red marker box swipes behind the key words of the viewer's question.
12. **Rolling year / number** (10:53: a "2026" research card rolls back to "1979" on "back in the 70s").
13. **Energy beam** (10:13, 14:00: red beam from the skinny figure's eyes to the big guy; 0:37 lightning from brain to body) for "signal / power" ideas.
14. **Red streak wipe** (5:01, 9:05): a band of red diagonal speed streaks crosses the frame as the transition into a new unit or "one thing".
15. **Radial speed lines** burst in behind the figure and the dial on "EVERYTHING" (9:28).
16. **Angle quadrant fill** (6:54: a 90° arc fills orange from 60° to 90°, then turns green and shrinks to "your limit").

How this maps to code: these are not new pictures, they are **states of one picture**, so they belong in the renderer
as per-element state tracks (colour, tint, saturation, focus, brightness) keyed to word times — not as more Flow images.
Recolour of a plate is done with masks made once per library plate (skin / muscle / tendon layers), the same way the
3D muscle clips already separate layers (`reptheory/clip3d.py` has `tints`, `glow`, layer order).

## 6. Text and colour system

- Font: one heavy geometric sans (Montserrat-like), ALL CAPS, wide tracking for small labels.
- White = instruction, orange = emphasis / unit numbers / your figure, red = warning / burn / wrong / muscle, green = good / right / fix / progress, yellow = safety.
- Hierarchy: kicker (small, coloured) → headline (big, white) → sub-line (small caps). Max ~5 words per headline.
- Labels sit in rounded pills with thin coloured outlines.

## 7. Sound

- Continuous low music bed under the voice (never silent), voice-forward, final mix at -14 LUFS with a narrow loudness range (3 LU).
- ~45 sharp high-frequency events per minute (mostly sound effects on visual events: whooshes on transitions, pops on rings/pills, thuds on stamps, ticks on counters, typing on typewriter text, a camera-shutter / click on UI mockups).

---

## 8. What Rep Theory has today vs this list

| Area | Have | Missing |
|---|---|---|
| Breadcrumb / part tracker | Section tag, PART n/7 bar | Breadcrumb text per unit that includes the unit name; persistent safety chip; top-right stopwatch / Q tracker |
| Character | Library figure + Flow pictures (style varies) | One locked character in a pose library (made once, reused forever) |
| Body overlays | Glow regions, rings, leader labels, 3D muscle clips | Ember particles, force arrows, lock icons, alignment line, bad-shape curve, ghost trail, anatomy inset with dashed arc |
| Cards | Stat ring, steps, versus, takeaway, chapter banner, tier board, equation | Study card, line graph (with morph), bar chart, dot matrix, effort dial/gauge, slider, toggle, wrong/right panels, hold-card chain, calendar builder, notebook, result board, sensation timeline, live stopwatch, warning cards, battery/scale icons |
| Engagement | Optional end card | Comment / like / subscribe / chat-bubble / phone mockups, locked list, thumbnail callback |
| Motion | Slow push, ring pop, connector draw, flash | Push-in on every shot, in-shot camera travel, focus-pull transitions, typewriter, overshoot pops, stamp slam + shake, glitch title, counters, morphs |
| State changes (5b) | `anatomy_glow` region glow, `glow_ring` pulse, tier-row light sweep + dim, 3D clip tints | Light-sweep recolour of a plate, threshold flip with ring pulse, highlight-on-mention for every named part, whole-figure glow/blue relax, desaturate = weak, spotlight-and-dim panels, silhouette fill-in, red background tint, meter/cell/dot recolour, text marker highlight, rolling number, energy beam, streak wipe, radial speed lines, angle fill; skin/muscle/tendon masks per library plate |
| Text | Headline + chips + kicker | Phrase-quality headlines (bug 2.1), colour semantics beyond orange, stamps |
| Sound | Voiceover only | Music bed with ducking, SFX on visual events, -14 LUFS master |
| Structure | Beat planner, units from narration, variety director, CSV direction columns | "Full Guide" blueprint with the unit template, test → payoff loop, woven CTAs, teaser of the next unit |

---

## 9. Build order (proposal)

**Step −1 — the new-topic test set and its measurements (section 0, Rule 6)**, built first so every later step is
judged on scripts it was not designed around.

**Step 0 — done 2026-10-31 (uncommitted).** Measured on all 13 topics with the app's CSV word path: 85 broken texts → 0,
forearm on a bare "muscle" 12 → 0, repeats 1 → 0, empty scenes 0 (guard added). Fixes: words take the script's spelling and
punctuation (`planner.respell`); every headline/chip passes `narrative.phrase` (one clause, never cut from a longer
phrase, no dangling verb); "muscle" alone never picks anatomy; no headline from the 2 scenes before; `planner.never_empty`
runs after the looks are chosen. Bugs 6 (sound) and 7 (one character) belong to Steps 1 and 5. Picture share fell on 046
(49% → 35%) only because the wrong forearm no longer counts.

**Step 0 — fix the bugs in section 2** (headline phrases, CSV text not Whisper words, anatomy relevance, no repeated headline, never an empty frame). Synthetic tests for each.

**Step 1 — done 2026-10-31 (uncommitted).** `reptheory/sound.py`: a sound on every meaningful on-screen change from the
plan's own events (scene → soft transition, new part → whoosh, headline → pop, chip → pluck, number → ticks, ring/glow →
marker pop, equation/tier mark → clack, ranking → thud), What If's spacing rule, pakMap's mixer ducking under the voice,
StarMap's music bed (chosen by the script's words, seeded by title), then -14 LUFS. On by default (`sound=True`); any
failure keeps the narration alone. Measured: 22-32 sounds a minute today (it rises with Step 3's cadence), 0% silence,
-15.7 → -14.0 LUFS on a spoken test. The music is CC-BY (Kevin MacLeod): its credit line is in the render log and
belongs in the video description.

**Step 1 — sound** (biggest gain for least work): music bed ducked under the voice, an SFX map tied to the events the renderer already knows (scene change → whoosh, ring/pill → pop, stamp → thud, counter → tick, text → type), master to -14 LUFS. Reuse the app's existing ambience/music mixer, no per-video assets.

**Step 2 — part 1 done 2026-10-31 (uncommitted).** `scenes._push`: the whole composition of every scene pushes in at
≥1.2%/s (max 10% a scene) with an alternating drift, never stopping before the scene ends; `scenes.transition` is now a
focus pull (out of focus + darken → in focus). Measured on 45 s preview renders, frames moving: 046 30% → 82%, hydration
17% → 73% (reference 57%); longest still 5.0 s → 1.4 s and 4.0 s → 2.6 s. Pills already overshoot. Still open from this
step: typewriter titles, stamp slam, glitch unit titles, and the 5b state tracks (highlight-on-mention beyond the
forearm, threshold flip, light-sweep recolour, spotlight-and-dim, background tint).

**5b state effects — first set done 2026-10-31 (uncommitted).** `reptheory/states.py` runs on every plan: 16 body
regions on the standing figure (neck to feet, plus heart, lungs, brain) light up at the word that names them, and a
text-only scene that names a part gets the figure; warnings / mistakes / pain / quitting warm the background red from
their word. Drawing: stat number flips to orange with a ring pulse when it lands (threshold flip), earlier steps and the
first versus side dim (spotlight), a light sweep reveals the anatomy plate, a marker swipes behind question headlines.
Each is a cadence event, so it also gets a sound. On the 13 topics: picture share 62% → 72%, still 19% → 16%, held scenes
5 → 3, opening sameness 75% → 57%. Still open: plate recolour masks (blue/red X-ray states), energy beam, streak wipe,
rolling year, typewriter / stamp / glitch titles.

**Step 3 (first pass) + unit openers — done 2026-10-31 (uncommitted).** `states.develop` runs after the looks are
chosen: where a scene would hold more than 3 s with nothing new, the phrase said in that gap (a whole short clause, its
key phrase, or its ending, all under the Step 0 phrase rules) arrives at its own first word; never a headline from the
same or the two previous scenes. New parts of the video open with a red/orange streak wipe and a title that types on.
On the 13 topics: still time 16% → 8% (target 5%), no new repeats or broken texts. What remains still is mostly
versus / steps cards after their last item.

**Still time and Rule 3 memory — done 2026-10-31 (uncommitted).** Versus / steps cards show the narrator's next phrase
as a caption strip once they have said everything: still time 8% → 5% (target met). The variety director now takes a
seed from each script's own text (same script → same video, new script → new mix of close calls) and a channel memory:
`engine.remember_opening` keeps the opening looks of the last 10 rendered videos in `.rep_theory_recent.json` beside the
project folders, and the next video is steered away from repeating a look at the same place (a script opened like the
last three videos drops to 25% alike). Looks grounded in the words (anatomy, pose, tier…) are never moved. Worst
opening sameness across the 13 fresh scripts stays 57%: with ~6 look types, common looks line up by chance; Step 4's
new components widen the vocabulary.

**Step 4 — first five cards done 2026-10-31 (uncommitted).** Detected in `variety.py` from the sentence's shape only,
drawn in `cards.py`, each a CSV `look` value (listed in the CSV prompt), an event with its own sound, and a caption strip
for the narration that follows: `timeline` (stopwatch + what you feel at each "N seconds in" mark), `mistake` (red WRONG
panel with a slashed cross; green RIGHT panel with a tick when a fix follows), `slider` (too hard? / too easy?), `dial`
(N out of 10 / N% effort, needle swings, pulse when it lands), `study` (papers fan in, count rolls to "N studies / people").
On the 13 topics: picture share 73% → 78% (worst 39% → 44%); the mistake card fires in 11 of 13 scripts. Still time
5% → 6% (a mistake card whose sentence ends its scene has nothing further to show) and worst opening sameness
57% → 62% (two scripts put their mistake card in the same slot) — both recorded honestly in the baseline. Next from the
list: line graph with morph, bar chart / dot matrix, calendar builder, result board, warning card, engagement mockups.

**Step 4 — rest of the cards done 2026-10-31 (uncommitted).** Six more, same rules (sentence shape only, CSV `look` value, own
sound, listed in the CSV prompt): `graph` (a line that bends up / down / level at each "rises / drops / levels off" word, over
time), `bars` (2-3 numbers of one unit as bars, or "1 in 3 adults" / "40% of lifters" as a dot grid), `calendar` (three or
more named days, or "N days a week" spread with rest days), `result` (a board from "under N, ... N to M, ... over M, ..."),
`warning` (a sign of harm + what to do, stacked amber cards), `engage` (comment box typing in the ask, like / subscribe
button pressed on its word). On the 13 topics: picture share 78% → 82% (mean), held scenes 3 → 2, still time 6.1% → 5.7%,
opening sameness mean 19% → 16% (worst stays 62%). Baseline rewritten.

**Step 2 — rest done 2026-10-31 (uncommitted).** Callout headlines type on (first word from the first frame, then ~30 ms a
letter, orange typing head). `states.stamps`: a short whole sentence said for emphasis (2-4 words, not a signpost or a unit
title, not ending on a function word) is stamped at its first word, tilted, slam + shake, red for a warning, held 2.4 s;
at most one per scene and one every 20 s (13 stamps across the 13 topics). Chapter titles get a glitch / RGB-split entrance
while they type on. Still open from 5b: plate recolour masks, energy beam, rolling year.

**Step 6 — done 2026-10-31 (uncommitted).** `reptheory/full_guide_prompt.txt` + a "Copy the script prompt" button: the
blueprint (hook + roadmap, early test, units with the slot template, the rule, questions, week plan, safety, result scale,
callback close) and the sentence shapes the app can draw, for any topic; units and slots the topic doesn't have are left
out. `reptheory/blueprint.py` (runs last): a NEXT teaser with the next unit's name at the end of each unit, a RESULT AT
THE END lock on an early test the script pays off later, the script's own safety rule as a chip through the units, and a
per-unit slot report in the render log. The CSV prompt makes each Full Guide unit a chapter. None of the 13 test scripts
has a test + payoff, so the lock fires 0 times there (Rule 4).

**Step 2 — motion layer**: push-in on every scene, focus-pull transitions, typewriter text, overshoot pops, stamp component, glitch unit titles, and the state tracks from 5b (colour / tint / saturation / focus per element, keyed to word
times: highlight-on-mention, threshold flip, light-sweep recolour, spotlight-and-dim, background tint, streak wipe).
Measure: ≥ 50% frames moving, no still run ≥ 4 s, and at least one state change per held picture longer than 4 s.

**Step 3 — cadence controller**: a new element every 1-2.5 s on the stressed word (layering 3-6 elements per scene). Measure: event gap median ≤ 1.2 s, p90 ≤ 2.6 s.

**Step 4 — component library, in order of how often the reference uses them**: live stopwatch + sensation timeline, wrong/right panels, difficulty slider, effort dial/gauge, study card, line graph with morph, numbered setup steps, bar chart / dot matrix, calendar builder, result board, warning cards, engagement mockups. Each one gets a CSV `look` value and a detector from the sentence's own words.

**Step 5 — one locked character pose library**: ~30 poses of one trainee generated once through Flow and kept in the library (no per-video generation), plus body-region maps per pose so glows/rings/arrows land on the right spot.

**Step 6 — blueprint**: a "Full Guide" blueprint in the CSV prompt and the planner: hook + roadmap, units with the 10-slot template, test early → result board at the end, woven CTAs, next-unit teaser, safety rules, close with a callback.
