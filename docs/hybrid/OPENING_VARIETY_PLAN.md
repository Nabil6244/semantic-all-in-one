# Hybrid Map: a different opening for every video

Status: plan only (2026-11-03). Nothing built.

## The problem

Every Hybrid Map video opens the same way: the whole globe for 1.4 s, then a 2.2 s fly-in to the subject.
Two videos watched back to back look like one template, and the first 5 seconds are the ones that keep a viewer.

## Why it happens (one rule, written in four places)

| Where | What it forces |
|---|---|
| `hybrid/plan.py:40` | `globe_opening: True` by default |
| `hybrid/director.py:321` | the first map beat always gets `start` on globe + `fly_to` at 1.4 s |
| `composition_styles/hybrid_director_prompt.txt:77` | tells Gemini "the video OPENS on the whole planet" |
| `composition_styles/hybrid_csv_prompt.txt:67` | tells the user's CSV writer: first row = camera start, frame=globe |

Any one of these alone would keep the same opening, so all four change together.
CSV runs with no camera row also fall back to a fixed start (`hybrid/csv_import.py:261`).

## The goal

- No two videos in a row open the same way.
- The opening follows the first sentence of the script, not a template.
- The globe fly-in stays, as one choice among several, picked when it really fits (a planet-wide or "where is this" story).

## Step 1: opening types (new file `hybrid/openings.py`)

Each type is a small recipe that sets the first 3-6 s: the camera, the first beat's mode, and any first layer.

| Type | Looks like | Picked when the first sentence... |
|---|---|---|
| `globe_fly_in` | today's opening | names a place most viewers can't place, or a planet-wide story |
| `cold_footage` | starts on a footage beat, map comes second | describes a scene, an event, a person, an action |
| `close_pull_back` | starts tight on the place (local), pulls out to region | names a city, a site, a building, a border crossing |
| `region_drift` | starts already at region frame, slow drift, no fly-in | continues a known story ("Since 2014, ...") |
| `stat_open` | big number / date card over the map first | opens on a number, a year or a ranking |
| `route_open` | an arrow or route already drawing as the video starts | opens on movement: trade, migration, invasion, a journey |
| `two_place` | split or fast move between two places | contrasts two places ("X and Y") |

Within each type, small seeded variation (seed = video title): camera bearing, the side it enters from, move speed (±20 %),
start zoom. So two videos of the same type still differ.

## Step 2: picking the type (rules, no Gemini call)

- Read the first 1-2 sentences: places named (already in `hybrid/geo.py`), numbers/years, action verbs, movement words.
- Score each type with plain rules, pick the top one.
- Works the same for Director plans and CSV plans. A CSV run still makes no Gemini calls.
- If the CSV already has its own camera start row, keep it: the user's choice wins. Only an opening the code made itself gets varied.

## Step 3: don't repeat (opening history)

- A small file in the app's data folder keeps the last 5 opening types used by Hybrid (type + date + title).
- A type used in either of the last 2 videos loses its turn, and the next best type is picked.
- The type picked is written to the plan notes so it shows in the log ("opening: close_pull_back (globe_fly_in used last video)").

## Step 4: prompts follow the code

- Director prompt: drop "the video OPENS on the whole planet". Say instead that the code picks the opening, and the first beat
  should simply be the best-matching beat for the first sentence (map or footage).
- CSV prompt: the first camera row becomes optional. If the writer leaves it out, the app picks a varied opening.
  Remove "frame=globe" as the required first row.
- Rule 9 in the Director prompt ("first beat is usually the map") goes, since `cold_footage` needs footage first.

## Step 5: keep everything else working

- `globe_opening` setting stays (News Doc and Weather set it to False). New setting `opening: "auto"` (default) or a fixed
  type name, so a user can force one.
- `derive_cameras` keeps its later rules (long-jump globe hop, push-in) unchanged. Only the opening block changes.
- The 2.2 s `OPENING_MOVE_S` in `csv_import.py` becomes per type.
- `validate.py`'s "first card in the first N seconds" check still passes for every type.

## Step 6: tests (synthetic, no renders)

New `test_hybrid_openings.py`:
1. 10 synthetic scripts on different topics (a city, a war, a trade route, a statistic, a country history...): at least 5
   different opening types come out.
2. The same script twice in a row: the second run gets a different type.
3. A CSV with its own camera start row: kept exactly.
4. `globe_opening: False` (News Doc / Weather): unchanged behaviour.
5. Every type produces a valid plan (camera starts at 0, no move inside a dissolve, first beat starts at 0).

Then run only the touched tests: `test_hybrid_director.py`, `test_hybrid_beat_csv.py`, `test_hybrid_openings.py`.

## Before building: approval needed

`hybrid/plan.py`, `hybrid/director.py`'s neighbours and the Hybrid prompts in `composition_styles/` are listed in
`test_fixtures/weather_protected.json`. Changing them needs the owner's OK and a manifest refresh with a dated note.

## Order and size

1. `hybrid/openings.py` + tests (new file, nothing else touched)
2. Hook it into `derive_cameras` and `csv_import.py` (small edits)
3. Prompt changes
4. Manifest refresh (with approval)

About a day of work. No render needed to check it; one real video afterwards to see it.

## Other styles to check later

StarMap, Explainer and pakMap may also have a fixed opening. Same idea could apply once Hybrid is done.
