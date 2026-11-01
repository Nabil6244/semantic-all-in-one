# Rep Theory render audit: `053_gyym/final/final 3.mp4` (CSV `scenes_manga_v2.csv`, after the zoom / overlay fixes)

Frames every 1.5 s, the render report and the log were read; picture sizes and card timings were measured from the report.
Nothing was changed.

## What makes it unattractive (worst first)

### 1. The pictures still look too big: it is the full-bleed layout, not only the push
- On every full-frame picture shot the subject fills **97-100% of the screen height**, and in **all 15 picture
  shots the subject touches the frame edge** (heads, feet and hands at the border).
- The push is now small (82% of the picture visible at the end of a wide shot), but Flow draws its pictures edge to
  edge: the person already fills the whole picture. Shown full-bleed, it fills the whole screen. The reference shows
  its subject at roughly 55-70% of the screen height with black space around it.
- Two picture sizes alternate: full-bleed shots (subject 97-100% tall) and half-width panels (about 62% tall).
  Cutting between them makes the size jump on every cut.
- The CSV still asks for close (rows 18, 25, 42) and medium on 4 more rows, which adds more crop to pictures that are
  already tight.

### 2. Scenes change before they finish
Measured from each card's own timing against its scene length:

| Scene | Card | Length | Needs | Result |
|---|---|---|---|---|
| 4 | race (stiff vs stretchy) | 1.6 s | 3.7 s | cut 2.1 s early: the slow lane never arrives, no LATE |
| 6 | slots (4 moments) | 2.6 s | 3.6 s | cut 1.1 s early: the slots appear during the transition |
| 13 | slots (never trained these 4) | 3.2 s | 4.3 s | cut 1.1 s early |
| 20 | stat (5 kilos) | 3.6 s | 3.8 s | cut 0.3 s early |
| 23 | comment card | 1.8 s | 2.0 s | cut 0.2 s early: the typed comment is only seen blurring out |
| 25 | stat (12 weeks) | 5.9 s | 6.2 s | cut 0.3 s early, and the ring sat empty for 3 s before "twelve" |

Other causes of the "never settles" feel:
- **Every cut is a 0.45 s blur-in / blur-out.** With a median scene of 3.5 s (7 scenes under 2.5 s), 13-28% of each
  scene is blurred. The reference uses hard cuts with a sound, so each shot is sharp from its first frame.
- **Two headlines overlap while one types over the other** ("BIGGER TH…" over "TENDONS"; "ARM BRE…" over "THE LINE"):
  the old line fades out in the same place as the new one types in.
- **Number rings sit empty**: the ring and its unit ("KG", "WEEKS") show for 2-3 s before the number word, with no
  number in them. Before today they showed 0, which was also wrong. Ring and number should arrive together on the word.

### 3. The four moments never get their names
The CSV did what the prompt says (short rows "The go." "The wrist." … left blank), but the planner joined those blank
rows into one scene, "the go. the wrist. the squeeze. and the line. you've seen it happen.". The slot filler only
looks for separate short scenes, so the slots stay numbered. That joined scene then became a 3D forearm clip with
"WRIST", which is unrelated to what is said.

### 4. Repetitive and generic labels on pictures
The part labels on pictures are ARMS ×5, TENDONS ×3, HANDS, WRIST. In the arm-wrestling stretch the same "ARMS"
label sits on the same spot four scenes running, sometimes on the rival's arm (it follows the red paint, wherever it
is in the picture).

### 5. Wrong or weak pictures where a card was refused or words were lost
- "Tendon stiffness alone explained up to about thirty percent": the voiceover transcript dropped "percent", so the
  stat card was refused and the headline reads **"30 OF THE DIFFERENCE"** over a giant realistic leg.
- "They measured it in the thigh, but every muscle…": a 3D quads clip with the headline "MUSCLE".
- The two leg pictures (realistic anatomy) are the largest shots of the video: the calf fills the whole screen.

### 6. Still lost compared with the render before today (`gyym.mp4`)
| Before today | final 3 |
|---|---|
| Forearm plate with parts lighting in turn: 9 scenes | 2 |
| Standing figure with the part lit: 6 scenes | 2 (glow too small to see at this size) |
| Takeaway key lines: 4 | 0 (off whenever Flow is on) |
| Seated table pose for the test | replaced by Flow pictures |
| Plain callouts that build headline + chips: 5 | 0 |

Some of these were removed on purpose (the plate repeated 10 times; full-screen text). But the video now leans on one
kind of shot (15 of 36 scenes are big Flow pictures) where it used to mix figure, plate, poses and text builds.

### 7. Smaller things
- The empty "comment" box with typing dots holds most of its 1.8 s scene.
- The stopwatch is tiny (top right) and easy to miss.
- 3D clips still show the hip and thigh beside the forearm on wide 3D framings.

## What to fix (proposal)

1. **Picture size**: never full-bleed. Fit every picture inside a frame margin so the subject is at most about 75% of
   the screen height, with black around it (the reference look). Use one consistent size, with the words beside it.
   Keep the gentle push inside that frame. Ignore close / medium from the CSV unless the subject is small in the
   picture.
2. **Let scenes finish**: a card scene lasts at least as long as its animation (borrow time from the neighbouring
   picture scene, or start the card's animation at the scene's first frame). Hard cuts with a sound instead of the
   0.45 s blur, keeping the blur only for chapter changes. Fade the old headline out before the new one types.
3. **Number rings**: the ring builds and the number rolls in together on the number word; no empty ring before.
4. **Slots**: read the item names from inside the joined scene ("the go. the wrist. …") as well as from separate
   rows, and never put a 3D clip or picture on those item sentences.
5. **Labels**: use the planner's specific part word (FOREARM, WRIST, BICEP) rather than the region name (ARMS), never
   the same label on 2 scenes running, and only on the trainee's red part.
6. **Lost words**: if the CSV says "percent" and the transcript dropped it, use the CSV's own text for the card and
   headline (the CSV is the script).
7. **Mix back**: give the forearm plate, the standing figure and plain callout builds a fair share again (they
   are lost to pictures), and allow one key line card per chapter even with Flow on.

## Already in the code, but not showing (checked 2026-11-01, plan of all 14 test scripts + the drawing code)

| Feature (where) | Status |
|---|---|
| Leader-line label `draw.leader()` | written, **never called anywhere** |
| Line-figure scenes drawn in code `sketch.py` (push-up, plank, squat, pull-up, gym) | offered by the planner (score 0.82) but **chosen 0 times** in 14 scripts: the pose library and pictures always win |
| Holding a prop `draw.hold_figure` + `squeeze_pulses` + grip rings + hand switch | only for the 4 words of the old lexicon (bottle, cap, pinch, hang): **0 times** in 14 scripts |
| Equation scenes `draw.equation` ("1 bottle = ...") | same old lexicon: **0 times** |
| Anatomy inset (small figure joined to the plate by a drawn line, `draw.connector`) | **0 times** |
| Brain → muscle signal beam `draw.beam` | needs "tells / signals / fires" + a named part in one sentence: **0 times** |
| Ring on the part named, on props `_label_ring` | **1 time** |
| Body-part highlights | 112 planned; on picture scenes only the latest one is drawn and its label once |
| Small kicker above a headline (CUE, TEST, MISTAKE...) | exists, rarely set (7 in the whole video), never on most picture scenes |
| Big orange number in the text column (`callout_column` value) | exists; on pictures it competes with the stat ring and is mostly empty |
| Tier board, safety chip, test lock chip | need a ranking / a safety sentence / a test paid off later: 0 in this script part |

The planner's own first choice is a plain text callout for 385 of 464 beats; everything visual comes from the director
upgrading those, so the old overlays that live on the figure, the plate and the props never get a scene to sit on.
