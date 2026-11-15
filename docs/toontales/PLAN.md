# Toon Tales — plan (2026-11-15)

A new Shorts style: one-minute narrated stories ("How X Worked") with flat 2D stick-figure
puppets standing inside lit 3D sets, word-by-word captions and dense sound effects.
Reference studied: Ricks Clips "How Mine Salting Worked" (61 s, 3.5M views in a day).
We copy the *patterns*, not his characters, names or sets: our own cast and our own set kits.

## What the reference does (measured)

| Part | Measured |
|---|---|
| Length / format | 61 s, 1080x1920, 30 fps |
| Voice | one narrator, 231 words, ~228 wpm, no silent gaps |
| Shots | ~35, 1.5–3 s each, a cut on (almost) every sentence; a few cross-dissolves |
| Characters | flat 2D cut-outs: white round head, ink outline, stick legs, bean body; faces swap drawn eyes/mouths; hats/clothes have soft shading |
| Sets | real 3D (stable geometry, true parallax on dollies), warm practical lights, stylised textures |
| Puppets in sets | stand on the floor and cast matching shadows -> textured cards inside the 3D scene |
| Props carry the story | newspaper headline = deadline, price board, sign "SURE THING MINE", chalk "10 FT" overlay = ending |
| Captions | one word at a time, bold white, thick black outline, ~70% down |
| Story | absurd first image -> name the concept -> deadline -> smart obstacle -> con wins -> ironic twist (last 5 s) |

The community recipe (two tutorials, 12–13 Nov) is Claude writing script + shots and driving
Blender, plus an AI voice. That is exactly what we can build on what we already have.

## What we reuse

* Blender host + Python authoring (`cartoon3d-engine/authoring/`, `--disable-autoexec` habit).
* `authoring/sets/scene_audio.py`: Edge TTS per line + Rhubarb mouth cues + timeline + mix.
* `authoring/sets/compose.py` pattern: append cast under an empty, land on the floor, render shots.
* `authoring/sets/animate.py` / `mocap.py` ideas for timed actions (here simpler: 2D poses).
* `web/puppet_rules.mjs` mouth-chart / gesture rules (port the rules, not the three.js renderer).
* Caption, join and loudness code from the existing Shorts / Story video path.
* Style page via `ui/style_registry.py` + `ui/style_pages.py` (Voiceover / Script / Plan / Render).

## Engine layout (new, nothing else changed)

```
toontales/
  cast/        puppet builder (Blender): parts, face sheets, outfits; cast.json
  sets/        set kits (Blender, procedural + CC0 packs): mine, street, office, room, road, forest
  props/       prop builder: text props (sign, newspaper, label, board) from story text
  plan/        shot plan schema + checker (pure Python, testable)
  shots/       per-shot builder: place cast, pose timeline, camera move, render
  audio/       voice, words, SFX placement, music bed, mix
  edit/        join, dissolves, overlays, captions, final encode
  library/     poses.json, expressions, camera moves, sfx map
```

## How each part works

1. **Puppets (2D in 3D).** Each character is a small rig of flat planes in Blender:
   head disc (flat white, ink outline), face plane with swappable eye/mouth textures
   (Rhubarb A–H + expressions: smile, grin, shock, sly, laugh, angry, worried),
   bean body with soft toon shading, stick limbs as bevelled curves driven by 2–3 bones
   (so arms bend and legs walk), hat/clothing pieces as shaded low-poly. Outline = solidify
   flip-normals or Freestyle. Cards cast shadows on the set floor. Faces always turn toward camera
   (billboard yaw within a limit) so they never show edge-on.
   Cast is built once from `cast.json` (name, hat, body colour, outfit, height) — new characters
   are a JSON row, not new art.
2. **Sets.** Built once per place type, procedurally plus free CC0 packs (Kenney, Quaternius,
   Poly Haven) — no per-video asset work. Each set ships with named marks (floor spots, doors,
   walls to hit, camera spots) and a warm light rig. Text on signs/props comes from the plan.
3. **Shot plan (Claude writes it, no Gemini).** One JSON row per shot:
   sentence, set, camera (wide / medium / close / insert / pov / low), cast + marks,
   action (walk_in, point, laugh, shrug, run, throw, hold, pick_up, nod, fall, bonk), expression,
   props + prop text, camera move (push, dolly, pan, tilt, static-with-drift), sfx, transition,
   overlay (chalk text/arrow). A Claude skill (`toon-tales`) writes the script with the
   6-beat formula and this plan.
4. **Checker (before any render).** Rules like: every sentence has a shot; no shot over 3.5 s
   or under 1 s; no two same camera types in a row; every abstract claim has a prop or action;
   cast stays the same look; the first shot is the strangest image; last shot shows the payoff;
   speakers' mouths only move on their own lines; nothing stands still longer than 2 s
   (see the no-still-screens rule). Auto-repair where it can, otherwise a clear message.
5. **Animation per shot.** Mouth from Rhubarb, blinks, idle breathing/bob, one main action from
   the pose library, eye-line toward the other speaker, small physics FX (dust, sparks, flying bills,
   gold flakes) as particle presets. Camera always moving slightly.
6. **Render.** Eevee, 1080x1920, 30 fps, one clip per shot (+0.3 s handles), cached per shot
   so a fix re-renders only the changed shots. Expected: ~20–30 min for a 60 s video on this Mac.
7. **Voice and sound.** Voice: user's own recording, or Edge TTS at a fast rate (~225 wpm).
   Words from Whisper drive cut times and captions. SFX: one per physical action from a CC0 SFX map
   (gunshot, pick, splash, coins, bonk, fuse, boom, footsteps, car); light folk/banjo bed under the voice,
   -14 LUFS final.
8. **Edit.** Hard cuts on sentences, dissolves only on time jumps ("next morning"), chalk overlays,
   word-by-word captions in the measured style, final H.264 BT.709.

## Built for a series (many stories, same cast)

Walt and Pip star in every story, so everything that defines them is made once and reused:

* **Cast is fixed data.** `toontales/cast/cast.json` holds each character's look, fixed voice
  (Edge voice + rate + pitch) and role/traits. `voice.speak(who, text)` always uses that voice,
  so a character sounds the same in every video. Faces/outfits are drawn once into `build/faces/`.
* **Stories are data, not code.** A story is a script + shot plan JSON (cast ids, set, marks,
  lines, actions, faces, camera). The engine never needs edits for a new story.
* **Sets are reusable kits** with named marks; a new story picks a kit and marks, it does not build a place.
  New kits (street, saloon, bank, office, home, road, forest) are added once and then serve every story.
* **Caching per character line and per shot.** Voice lines are cached by text+voice; rendered shots
  (step 5) are cached by a hash of their shot JSON, so editing one line re-renders one shot.
* **Guest characters** are new rows in `cast.json` (look + voice + role), no new art.
* **Script writer** (step 4 skill) reads roles/traits so Walt is always the schemer and Pip the
  "wait, how?" sidekick, and keeps a `stories/` log of past topics so stories do not repeat.

## Build steps (each ends with something to look at)

1. **Cast spike** — 2 characters as 2D-in-3D puppets on a grey floor: stills sheet of faces,
   poses and the shadow. *Gate: you approve the look.*
2. **One set + one shot** — mine tunnel set; one 3 s shot with lip sync and a push-in.
   *Gate: you approve the shot.*
3. **Pose + expression library** — the ~12 actions and ~8 faces, contact sheet.
   Built: `library/poses.json` (23 static poses as data), `library/actions.py` (pure Python, 16 timed
   actions: walk, run, sneak_walk, jump, celebrate, fall, bonk, nod, shake_head, laugh, throw, pick_up,
   scratch_head, tremble, explain, look_around, sigh; every pose is also a hold action),
   16 eye states + 18 mouths. One *state* format drives the puppet (`puppet.apply_state`) and the shot
   builder (`{"who","do","t0","dur","params"}`); moves carry the character's spot into later actions.
4. **Plan schema + checker + `toon-tales` skill** — tests on the checker.
   Built: `plan/schema.py` (format, vocab, shot-length estimate from each voice's measured pace),
   `plan/check.py` (18 rules, `--fix` auto-repair), `plan/vocab.py` (prints every usable name),
   `sets/kits.json` (marks/spots without Blender), narrator voice in `cast.json` (~229 wpm),
   `.claude/skills/toon-tales/SKILL.md`, sample `stories/fools_gold/plan.json` (23 shots, ~60 s),
   `test_toontales_plan.py` (25 tests).
5. **Shot builder + render cache** — whole plan to clips.
   Built: `shots/compile.py` (plan shot + real voice -> Blender shot: timing, marks, actions, props,
   9:16 camera framing per type/move, kept inside set bounds), `props/props.py` + `props/text_art.py`
   (16 prop types, text art, wall/hand/pick-up/throw), `shots/shot.py --batch` (one Blender run),
   `shots/build_story.py` (check -> voices -> compile -> render changed shots only -> clips.json,
   `--draft`, `--rough`). Cache key = shot content + engine source hash.
6. **Audio + edit** — voice, words, SFX, music, captions, join.
   Built: `audio/voice.py` word timings (Edge word boundaries aligned to the trimmed wav),
   `audio/sfx.py` (22 SFX synthesised/bundled + banjo boom-chick bed, made once, no downloads),
   `edit/art.py` (one-word captions ~70% down; chalk/arrow/circle/stamp/label/cross overlays),
   `edit/edit.py` (per-shot caption/overlay burn-in cached, cuts + time-jump dissolves, numpy mix with
   auto action SFX and ducked bed, loudnorm -14 LUFS). `python3 -m toontales.edit.edit <plan> [--draft]`.
7. **First full 60 s video** — our own story, sent to you.
8. **App page** — Toon Tales style page, nothing starts until Generate, autorun support.
9. **More sets** — street/town, office/counter, home room, road, forest (one at a time, on request).

## Open questions for the user

* Name of the style ("Toon Tales" is a placeholder).
* Voice: your own recording, or Edge TTS?
* Cast look: stay close to the stick-figure look (white round head, stick legs), or a different face style?
* First story topic for the step 7 video.
