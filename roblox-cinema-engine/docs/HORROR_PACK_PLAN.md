# Roblox Cinema — Horror Story Pack (plan, 2026-11-06)

Goal: Roblox Cinema can tell a modern "rules" horror story (first test: the bus-stop candy script) with the right sets, props and
shots, not a war film's. Everything is general: any horror script that names a bus stop, a shop, a gift, a phone call, a doorway
or a flashback gets the same tools. Nothing is tuned for the candy video.

Rules carried over: additions only, old war/history films must render exactly as before (plan.json diff on the D-Day and Rome
samples); a supplied CSV makes no Gemini calls; pictures come through the Visuals tab (`visual_bridge.py`); touched tests only.

## What exists today (checked in code)
Night + rain streets (`city`/`town`), American brick town, street lamps; kitchen, living room, hallway, bedroom, bathroom with
prop-aimed cameras (`lib/rooms.mjs`); `phone`, `table`, `door`, `lamp`; civilians with grey long/bun hair; `child` role; modern era.
Missing: everything in the steps below. There is no image-card layer in this engine at all.

## Step 1 — Story mode, not war mode (small, do first)
- `extra.genre = "horror"` on the plan row (and the app section gets a Genre: History / Horror story switch).
- New events: `encounter` (one stranger meets the hero), `pursuit_slow` (something keeps pace behind), `phone_call`, `flashback`,
  `refuge` (reaching a safe person). Each recipe: 1-3 people, no crowd, no armed roles, empty streets.
- Default for horror beats with no event is `encounter`/`civilian_life_quiet`, never the village crowd.
- Character roles: `stranger` (old woman look: grey bun, long coat, cardigan colours, slow walk, warm fixed smile), `hero`
  (same face every beat via a fixed name seed), `mother`, `parent`, `child` reused.
- Story prompt: a second file `docs/story_prompt_horror.md` with the new events/props/cards, script copied unchanged.
- Test: horror CSV plan has no soldiers, no crowd above 4, same hero id in every beat.

## Step 2 — Horror light and sound
- Look presets `night_horror` (low sodium-orange street pools, deep blue-black, heavier vignette, slight green grade) and
  `interior_night` (one warm lamp, dark corners). Night stays readable: subjects in a light pool, QC checks mean luma floor.
- Slow camera language: `creep_in`, `hold_breathe` (tiny drift, never frozen), `behind_follow` (from just behind the hero).
- Audio: horror beds (rain on shelter roof, empty street hum, room tone, low drone) from the bundled library; cues `paper_rustle`,
  `phone_ring`, `door_chime`, `footsteps_slow`, `whisper_name`. Music mood `dread`.
- Test: preset chosen for horror + night; no chase speed on camera; cues placed at keyword times.

## Step 3 — Street sets
- `bus_shelter` prop (glass sides, bench, roof, timetable board, lamp) + `bus_stop` anchor on the street; rain hits the roof.
- `shop_front` building kind: lit window, display shelves, hand-lettered `OPEN` sign, door with bell. Words: shop, store, bakery,
  candy shop, open sign.
- `parked_car`, `bench`, `puddles` (wet road shine at night).
- Location words route here: bus stop, bus shelter, shop, parking lot, platform (Step 6).
- Test: "bus stop" location builds a shelter and frames the hero under it.

## Step 4 — Small objects and the dry circle
- Hand-held props in the character kit: `paper_bag`, `gift_small` (a wrapped sweet: colour from the text — gold, silver, red,
  green), `letter`, `card_id`, `drawing`, `pocket_items` (several wrappers). Prop words: bag, candy, sweet, wrapper, gift,
  letter, license, drawing.
- `hands` focus outdoors: camera close on a character's hand/held item (today hands only work in rooms).
- FX `dry_circle`: rain particles skip a radius around a named character, ground under them stays dry (no wet shine).
- FX `rain_stops_at`: a character the weather "doesn't touch".
- Test: "candy in her hand" adds `gift_small` to a hand and a close shot; dry circle has zero rain instances inside the radius.

## Step 5 — Picture cards for details 3D cannot show (via Visuals tab) — built 2026-11-06, not yet seen on screen
The name on a wrapper, child's pencil handwriting, drawings with blank faces, a blank driver's license, a phone screen showing
11:40. These are closer than the blocky world can read, so they come as picture cards:
- New CSV column use: `extra` `{"card":"wrapper with a name in blue ink"}` or `card` prop words; the director makes a card beat.
- Cards are pictures (Flow or user files) fetched through the Visuals tab, then shown as an in-world insert: the camera pushes
  into the held object and dissolves to the card, with grain + the horror grade so it matches.
- Text cards generated in code (no picture needed): a clock/phone screen with a time, a name written in "ink" or "pencil".
- Test: a card beat with no picture falls back to the code-made text card, never a blank screen.

## Step 6 — Other places from flashbacks and side stories
- Church bake sale: church + tables + small crowd (6-10), day.
- Train platform: platform edge, canopy, the existing `train` vehicle at the platform.
- Wedding: hall interior with tables and lights (new room kind `hall`).
- Flashback look: desaturated + soft vignette, child-size hero.
- Test: each place word builds its set; flashback beats get the flashback grade.

## Step 7 — Candy video test (only after asking)
- Write the candy CSV with the horror prompt (script unchanged), plan-only run, check the plan beat by beat against the script.
- Stills only at chosen times; full render only when you say so.

## Order and size
| Step | Size | Needed for the candy video |
|---|---|---|
| 1 Story mode | small | yes |
| 2 Light + sound | small-medium | yes |
| 3 Street sets | medium | yes (bus shelter, candy shop) |
| 4 Small objects + dry circle | medium | yes (bag, candy, dry circle) |
| 5 Picture cards | medium | yes (name, handwriting, drawings) |
| 6 Flashback places | medium | Marcy + ending only; can wait |
| 7 Test | — | after your OK |

Open question: the app already has a Rules Horror style (Final Sight study). This pack keeps the Roblox look; it borrows only
pacing/lighting ideas from Rules Horror, it does not change that style.
