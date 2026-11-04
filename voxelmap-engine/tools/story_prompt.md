# Writing a voxelmap story CSV

Give this file to the writer (a person or an AI) together with the topic. The output is one CSV; check it before rendering:

    node render.mjs story.csv --check        # errors, warnings, length, detail tiles and download size
    node render.mjs story.csv --prepare      # builds the detail terrain the camera needs (may download, see --check)

## Columns

`row,id,date,place,lon,lat,rung,alt,heading,site,gap,text,extra` — `extra` is JSON (escape quotes by doubling them).

| row | fill | meaning |
|---|---|---|
| plan | id = film title; extra = `{"world": "<world id>", "subtitle": "...", "endcard": "...", "credits_lines": ["Music: ..."]}` | one per story, first |
| chapter | id; text = chapter title | the beats after it belong to it (aim for 1–3 minutes each) |
| territory | id = key; date = YYYY-MM it starts; extra = `{"legend": [{"label", "color"}], "rules": [...]}` | rules: `{"iso": ["VNM"], "lat_min"?, "lat_max"?, "names"?: [province names], "color": "#rrggbb", "strength"?}` per province, or `{"polygon": [[lon, lat], ...], "color", "strength"?}` for a drawn front line |
| label | text = name; lon, lat; extra = `{"kind": "country" or "city", "min_alt"?, "max_alt"?}` | place tags on the map |
| beat | see below | one shot of the story |

Beat columns: `id`, `date` (YYYY-MM of the event; `-0216-08` is August 216 BC; a story before 1800 gets ancient armies and no modern equipment), `place` (shown as the scene's name), `lon`, `lat`, `rung`, `alt`/`heading` (optional),
`site` (ground beats), `gap` (optional extra seconds of silence before it), `text` (the narration: 1–3 plain sentences), `extra`:

| extra key | values |
|---|---|
| territory | a territory key: the map switches to it as the camera leaves for this beat |
| shot | force a shot: globe_spin, establishing, pullback, aerial_track, orbit, low_track, flyover |
| path | `[[lon, lat], [lon, lat]]` for an aerial track along a road, river or front |
| factions | sides in a ground scene: us_marine, us_army, arvn, pavn, viet_cong, french, pla, civilian, sailor; before firearms: roman, carthaginian, gaul, germanic, greek, byzantine, ottoman (spear and shield), senator (toga). Before 1800 the engine picks the two sides of a battle from the place and narration when none are given |
| landmark | a real building for the scene: colosseum, temple, pantheon, palace, domed (Hagia Sophia), mosque, cathedral, castle, wall (Hadrian's), arch, pyramid, column; `none` for no landmark. Without it, a city/village/fortress scene takes the one its place or narration names |
| names | `["Gen. X"]` named people placed in the scene |
| signs | `["WELCOME"]` banners in the scene |
| light | day, dawn, sunset, night, fog |
| effects | `[{"kind": "blasts" | "smoke" | "fires" | "planes", "at": [lon, lat], "to"?: [lon, lat], "count"?: n}]` on the map |
| museum | `{"item": "tank", "name": "Type 59 tank No. 390", "note": "Held at ..."}` — items: tank, apc, truck, jeep, howitzer, helicopter, jet, cargoPlane, landingCraft, patrolBoat, sampan, ship, bicycle |

## Rungs (how close the camera is)

- **globe** — the whole Earth (open and close the film on it; a globe first beat carries the film title)
- **map** — a region, top-down (context, outcomes, numbers)
- **oblique** — a tilted view along a front, a coast or a trail
- **ground** — a human-scale scene at a `site`: village, city, airfield, lz, battle, fortress, beach_landing, jungle, trail, delta, and indoors: hall (a treaty hall; a senate before 1800), office (a leader at a desk)

## Rules that make it look like the reference

1. Open on a globe beat, end on a globe beat (credits and end card play over it).
2. Alternate map and ground: context → event → consequence. Never two ground beats far apart without a map or oblique beat between.
3. One sentence is one caption: keep sentences short (8–20 words), factual, with the month in the beat's `date`.
4. Numbers live in the narration, not on screen. Dates only move forward.
5. Every chapter should open with a short silence (the planner adds one for the chapter card) — do not start a chapter mid-sentence.
6. Use `territory` changes for who controls what, `effects` for bombing and air campaigns, `light` for night actions and endings, `museum` for one real surviving object every few minutes.
7. All lon/lat must be inside the world's bounding box (`--check` says so). Built worlds: `indochina` (lon 84 to 124, lat 0 to 30),
   `southasia` (lon 60 to 90, lat 6 to 38), `mediterranean` (lon -12 to 45, lat 28 to 58: Europe, North Africa, Turkey). Another region
   needs a new world first: `python3 tools/build_world.py --id <id> --bbox=lon0,lat0,lon1,lat1`.
8. Ground beats in one city may share the same coordinates: each shows its own scene, and the camera rises out and comes back down between them.
9. Battles: name both sides in `factions` (e.g. `["roman", "carthaginian"]`); never `civilian` for an army. Rooms (`hall`, `office`)
   for treaties, councils and leaders; a `landmark` for a famous building the narration talks about.
10. The voice-over may be longer than the CSV text: the film follows what is said, so one or two sentences per beat that say what the
    beat shows are enough.
