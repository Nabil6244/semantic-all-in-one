# Doodle Survival — plan (Video Kit look pack)

Goal: Claude or Gemini makes a whole zombie / end-of-the-world survival story video by itself through the
**videokit** MCP (align → story + plan.json → check_plan → scene → look → join). The owner gives a script and a
voiceover; the AI does the rest. Same flow as today, plus a new look pack made for this kind of video.

Reference studied 2026-11-26: the DoodleSurvivals channel (7 videos, 13–67 min). We adopt its *patterns*, not its
character or art: our mascot, our colours, our own code.

## What the reference does (patterns to adopt)
| Pattern | What we saw |
|---|---|
| Day-by-day story | "Day 1 → Day 100", parts of 13–67 min, each day a mini chapter |
| One mascot | flat 2D character, round head, big eyes, many face close-ups (scared, worried, relieved) |
| Dark flat places | hallway with doors, farm, barn, city skyline at night; slow camera drift |
| Inserts | phone screen "Calling…", icon cards ("WHAT IT CAN'T FIX" + crossed icon), supplies |
| Threat | zombie crowds, a door being hit, fire, lightning |
| Thumbnail | huge "DAY 130" text + mascot + zombies |

## Steps

### Step 1 — `agent_kit/looks/doodle_dark/` look pack
- `look.css`: dark navy/charcoal palette, one warm accent (amber) + one danger red, rounded bold font,
  thick soft outlines, grain + vignette, same class names as doc_teal (`title kicker label card caption flash hl ...`)
  so the guide rules still apply.
- `palette.js`: the colours as JS so SVG drawings match the CSS.

### Step 2 — our mascot `doodle_dark/hero.js` (SVG puppet, pure function of t)
- Original design (not their red-cap guy): e.g. round head, beanie or headband, backpack, scarf — owner picks
  from 3 sketches before anything else is built.
- `hero(t, {pose, face, look, x, y, scale, facing})` returns SVG. Faces: calm, scared, panic, worried, relieved,
  angry, sad, thinking, sleeping (eyes + brows + mouth shapes, blink on its own seeded clock, mouth flap when
  `talking`). Poses: stand, walk, run, sneak, crouch, sit, lie, hold item, push door, look out window, eat, sleep.
  Port the pose angles from `stickman/poses.py` to JSON so we reuse that work.
- Close-up mode: head fills the frame (the reference uses this a lot for emotion beats).

### Step 3 — threats `doodle_dark/zombie.js`
- Zombie puppet (same rig, green-grey, torn clothes, red eyes), walk-shamble cycle, crowd helper
  `horde(t, {count, depth, seed})` with parallax rows. Door-bang helper (door shakes + dust + impact cue).

### Step 4 — places `doodle_dark/places.js`
- Flat-vector SVG sets drawn in code, reusable for every video (no per-video art work):
  apartment room, hallway with doors, stairwell, rooftop + skyline, farmhouse inside, barn, field + fence,
  forest edge, supermarket, car interior, bunker, city street at night.
- Each set has day/night/fire/storm variants and layers for parallax (`K.drift` + `K.parallax`).

### Step 5 — survival inserts `doodle_dark/cards.js`
- `dayCard(n)`: big "DAY 47" slam with tally marks, ticks on the day word.
- `phone(state)`: calling / no signal / message / battery low.
- `radio(text)`: static + typed broadcast line.
- `canFix / cantFix(items)`: icon grid with ticks and crosses.
- `supplies({food, water, ammo, meds})`: bars that drop as days pass (values from the narration only).
- `map(path)`: a hand-drawn escape map with a dotted line drawing on.
- `rule(text)`: one survival rule written word by word.
- `teaser(text)`: open-loop card ("but something was knocking…").

### Step 6 — guide + check_plan rules for this look
- Add a **Doodle Survival** section to `agent_kit/GUIDE.md`: everything drawn (no footage); mascot on screen in
  most scenes; a face close-up on every emotion word (scared, panic, relief…); a `dayCard` on every "Day N"
  the narrator says; supplies card when the narration talks about food/water running out; a teaser every
  30–60 s; never the same place twice in a row unless the story stays there.
- `check_plan` (in `agent_kit/kit.py`): when `plan.json` says `"look": "doodle_dark"`, also flag a missing day
  card for a spoken "day N", a missing mascot for more than 20 s, the same card type twice in a row.

### Step 7 — long videos (13–60 min)
- `join` in parts (one per day block) and then one final splice, so a 60-min film does not need one huge encode.
- Scene renders in parallel (`scene` already per scene; add a `scenes` batch tool that renders a list on all cores).
- Chapters file from the day cards (YouTube timestamps) + a "DAY N" thumbnail made from the mascot + horde.

### Step 8 — sound
- Night ambience, wind, rain, distant moans, door bangs, radio static, a tense low music bed. Use the existing
  sound library first (`pakmap/sounds.py` beds, CC0 SFX); only add free CC0 files once, never per video.

### Step 9 — test
- A 60–90 s test from a short script + Edge voice, made end to end by Claude through videokit, sent to the owner.
- Then the same script through Gemini CLI (`gemini mcp add videokit ...`) to confirm both AIs can do it.

## Not doing
- No copy of the reference's character, thumbnails or scenes.
- No Gemini calls inside the kit itself; the AI driving the kit is the only model.

## High-end pass (owner, 2026-11-26: "GitHub is fine, Claude makes the video, I want high-end results")
The flat SVG test is the skeleton, not the final look. What lifts it to channel quality:

1. **Painted places, once.** Flow paints each place (step 4 list, 12 sets x day/night/fire/storm) in one fixed
   flat-vector style prompt, at 2K, split into 3 depth layers (sky / back / front) for parallax. Stored in
   `state/doodle_places/`, reused by every video, never painted per video. Code-drawn set is the fallback.
2. **Scout model sheet.** Flow paints a Scout turnaround in the same style; we redraw his SVG parts to match it
   (shading shapes, hat knit, scarf folds, rim light), so painted places and the rigged hero look like one film.
3. **Lighting and atmosphere** with PixiJS v8 + pixi-filters (MIT, GitHub): bloom on windows/torch/fire,
   god rays through windows, soft drop shadow under every character, colour grade per scene (night blue, fire
   orange, dawn), rain, fog, dust, embers, screen flicker, lightning. The hero is tinted by the place's light.
4. **Hand-made line feel**: perfect-freehand (MIT) for brush strokes on cards and doodles, 2-frame line "boil"
   on the hero (tiny seeded wobble at 12 fps) so it feels animated, not vector-stiff.
5. **Motion craft**: GSAP (free, Webflow licence) easing + secondary motion (scarf and bobble swing, hat squash,
   anticipation before a run, overshoot on stops), 12 fps "on twos" option for the hero like cartoon channels.
6. **Camera**: depth-of-field blur on the far layer, slow push-ins on emotion beats, whip pans with motion blur
   between places, handheld shake on threats.
7. **Zombie and horde**: same rig and shading, crowds in 3 depth rows with fog between rows.

Kept: everything stays a pure function of t (videokit renderer), no per-video art work, Claude drives it.

## Reference study 2 (2026-11-26) — "Trapped In a Farm Day 1 To Day 100", 67 min, 2.1M views
20 frames sampled (0:04 → 60:20, plus a 20-s run at 22:05). What actually makes it look high-end:

**It is NOT rich painting.** Places are minimal flat vector: few shapes, soft gradients, muted desaturated
colours (dusk grey-blue, dim navy, warm window light). Quality comes from restraint + lighting + a strict
design system, not detail. => Draw places in code (clean shapes) with lighting; Flow painting would clash.

**About half the runtime is explainer cards**, all one system:
- near-black background with faint dot grid + grain, thin amber/gold line icons (hand, food, stick person,
  radio, door), small widely-spaced CAPS labels in white under each icon
- "RULE 1" card: icon in a circle + kicker + 2-line rule
- metaphor diagrams: balance scale ("what you don't know weighs more": information vs supplies)
- line-art house cross-section (blueprint style) with tiny figures inside, a label like "IN THE DARK", a big
  amber counter top-left (e.g. "300") and a fog of tiny dots (the horde) outside
- object close-up with a camera viewfinder overlay (REC corners, "IMG_2096 · FLASH") and a label ("FLOUR")
- TV news insert: old TV frame, red LIVE tag, red lower-third headline ("HOSPITALS: UNEXPLAINED VIOLENT BEHAVIOR")
- radio close-up with a signal line; tally marks filling a wall; a timer bottom-right ("00:23")
- annotation leader lines in-scene ("TOO FAST", "TOO STIFF" pointing at a zombie)

**Persistent day tag**: small "DAY 18" top-left on every shot (grey word, amber number). Day changes = tally card.

**Character**: small in the world (1/4 frame height), simple, faces only for big emotion close-ups.

**Lighting**: moonlight shafts through windows with floating dust, warm window glow at night, sunrise haze,
dim rooms with one light source. This is the "expensive" feeling.

**Pace**: a cut every 2–3 s; cards hold 3–6 s with small motion (icons pop in one by one, lines draw on).

### Changes to our plan
- Places: code-drawn flat vector + lighting (PixiJS filters), muted palette. Flow painting dropped for places.
- Scout: keep the design, mute his colours to sit in the dim palette; small in wide shots, big in close-ups.
- New card set (Step 5 grows): icon row, rule card, metaphor scale, blueprint cross-section + counter + horde
  dots, viewfinder close-up, TV LIVE insert, radio, tally wall, timer, annotation leader lines.
- Line-icon library: thin-stroke icons drawn on (perfect-freehand / SVG stroke-dash), one stroke weight.
- Day tag on every scene (look pack helper), not only on day cards.

## Owner rule (2026-11-26): follow the narration, no pre-drawn places
"You don't have to draw the places now; follow the narration, for every narration there will be new things."
- Step 4 (12-place library) is dropped. Claude draws each scene new from its sentence through videokit.
- `places.js` keeps 3 example places as style references only; generic pieces moved to `light.js`.
- `README.md` in the look pack is what Claude reads before drawing; GUIDE.md points to it.
- Cards (Step 5) also become a style system + examples, not fixed templates.
