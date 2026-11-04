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

Beat columns: `id`, `date` (YYYY-MM of the event), `place` (shown as the scene's name), `lon`, `lat`, `rung`, `alt`/`heading` (optional),
`site` (ground beats), `gap` (optional extra seconds of silence before it), `text` (the narration: 1–3 plain sentences), `extra`:

| extra key | values |
|---|---|
| territory | a territory key: the map switches to it as the camera leaves for this beat |
| shot | force a shot: globe_spin, establishing, pullback, aerial_track, orbit, low_track, flyover |
| path | `[[lon, lat], [lon, lat]]` for an aerial track along a road, river or front |
| factions | sides in a ground scene: us_marine, us_army, arvn, pavn, viet_cong, french, pla, civilian, sailor |
| names | `["Gen. X"]` named people placed in the scene |
| signs | `["WELCOME"]` banners in the scene |
| light | day, dawn, sunset, night, fog |
| effects | `[{"kind": "blasts" | "smoke" | "fires" | "planes", "at": [lon, lat], "to"?: [lon, lat], "count"?: n}]` on the map |
| museum | `{"item": "tank", "name": "Type 59 tank No. 390", "note": "Held at ..."}` — items: tank, apc, truck, jeep, howitzer, helicopter, jet, cargoPlane, landingCraft, patrolBoat, sampan, ship, bicycle |

## Rungs (how close the camera is)

- **globe** — the whole Earth (open and close the film on it; a globe first beat carries the film title)
- **map** — a region, top-down (context, outcomes, numbers)
- **oblique** — a tilted view along a front, a coast or a trail
- **ground** — a human-scale scene at a `site`: village, city, airfield, lz, battle, fortress, beach_landing, jungle, trail, delta

## Rules that make it look like the reference

1. Open on a globe beat, end on a globe beat (credits and end card play over it).
2. Alternate map and ground: context → event → consequence. Never two ground beats far apart without a map or oblique beat between.
3. One sentence is one caption: keep sentences short (8–20 words), factual, with the month in the beat's `date`.
4. Numbers live in the narration, not on screen. Dates only move forward.
5. Every chapter should open with a short silence (the planner adds one for the chapter card) — do not start a chapter mid-sentence.
6. Use `territory` changes for who controls what, `effects` for bombing and air campaigns, `light` for night actions and endings, `museum` for one real surviving object every few minutes.
7. All lon/lat must be inside the world's bounding box (`--check` says so); build a new world for another region:
   `python3 tools/build_world.py --id <id> --bbox lon0,lat0,lon1,lat1`.
