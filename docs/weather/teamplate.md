# Weather Teamplate — editing style (2026-10-13)

A second editing style for Weather videos. Same plan files, data, narration and renderer; a different edit.
Pick it in the Weather card (**Editing style: Weather | Weather Teamplate**, saved per project in `weather/weather.json` as
`edit_style`) or `python -m weather render --style teamplate`. Unset = the Weather style, unchanged.

## What the reference does (measured, "Lake Michigan Rose 6 Feet…", 20:05, 1280x720)
- **Rhythm**: 185 shots, median 5.0 s, mean 6.5 s. Shot lengths cluster at 5 s (86 shots) and 10 s (22, graphic holds);
  the opening 2 min is faster (~4 s), the middle slower (8–9 s). Every footage change is a **hard cut**.
- **Footage**: drone aerials of the actual place, wide establishing then closer angles of the same subject; footage dominates,
  maps/graphics punctuate. Drone motion is the camera move (no Ken Burns on video).
- **Titles**: (1) keyword card — heavy white sans caps, the key word in a red box (`ROCK [PROTECTION]`, `[BOTTOM] OF BLUFF`),
  centred, words appear one after another, ~3 s; long ones stack left-aligned with the key word alone on the last line.
  (2) chapter card — serif italic date kicker over a light, widely tracked title (`NOVEMBER 2019 / HOUSE AT RISK`), title wiped in.
  (3) full-red section card (`CASE STUDIES`) — rare.
- **Every card dims the frame** (~40 % plus a vignette) while it is up; nothing else is on screen with it.
- **Tags**: small black caps tag top centre for context; orange box for facts/places, sometimes with thin HUD brackets.
- **Numbers**: big white numeral counting up (4→5→6) on a darkened shot, label typed in beside it (`6 FEET WATER LEVEL`).
- **People**: name bottom right with a small orange role tag, or an orange monogram square.
- **Maps**: dark, muted land and ocean, glowing outline, orange label tag, white pulse ring on the point, circular inset;
  hard cut in and out of maps.
- **Ending**: calm wide shots, a stacked keyword card, ends on footage.

## How Teamplate implements it
| Reference trait | Teamplate | Where |
|---|---|---|
| Hard cuts | Hybrid's dissolve becomes 1 frame; footage `dissolve_s` = 1 frame | `weather/teamplate/__init__.py` `apply_plan`, `apply_spec` |
| Map cuts, slow hold | every `fly_to` after the opening becomes a 1-frame move on a frame boundary + slow push-in (≤10 s, never under footage); the opening globe zoom is kept | `cut_camera` |
| Cut first, then words | a keyword card that would start just before a cut waits for it | `apply_spec` `on_cut` |
| ~5 s shots | a single stock shot ≥ 9 s → ~5 s shots of the same subject (`…`, `…, close up`, `…, wide shot`, `…, aerial view`); event footage and your own files are never split | `weather/teamplate/footage.py` `split_long_shots` |
| Relevant footage only | a stock request contradicting its beat's narration (weather type, or a tropical/coast/desert/city setting it never mentions) stops the render, naming the beat; your-library swaps are checked against the narration too | `relevance_problems`, `prefer_library_strict` |
| Keyword / chapter cards | beat `hud_title` → `tp_title` (first one: chapter card); its `sub` → black `tp_tag` after the card | `tp_title.mjs`, `tp_tag.mjs` |
| Frame dims under cards | `tp_dip` over every card and big number (merged when close) | `tp_dip.mjs` |
| Count-up numbers | Weather `counter` → `tp_stat` (big count-up + typed label, after any card), then a compact orange tag top right | `tp_stat.mjs` |
| Orange place tags + pulse | `place_label` → `tp_place`; steps aside while a card is up | `tp_place.mjs` |
| Lower third | `headline` → `tp_lower` (orange kicker, white title, no bar) | `tp_lower.mjs` |
| Dark map | base-imagery grade only (radar, satellite loops, warnings and data colours untouched) + map vignette | `MAP_GRADE`, `tp_vignette.mjs` |

Shared maths (layouts, timing): `weather-engine/lib/wxu_tp_style.mjs`. Every word drawn is one the plan or the data already had;
values are the counters' own (the numbers report is unchanged). Source lines, legends, radar clocks and footage credits are kept as
they are (accuracy and licensing).

## Generic footage (storm, flood, rain, surge, coast)
Two ways in, both through the app's existing stock providers (Pexels/Pixabay; your footage library first) and the relevance check:
1. **The CSV (main way).** With Weather Teamplate picked, *Copy the CSV prompt* adds `weather/prompts/teamplate_csv_addendum.txt`:
   the AI puts `stock_video:` footage beats (4–10 s, ~40 % of the narration) on the sentences that DESCRIBE weather ("Streets turned
   into rivers"), worded from the sentence, never naming a place, storm or date; every data sentence stays on the map. Same CSV columns.
2. **Automatic cutaways (fallback)** — `weather/teamplate/cutaways.py`: inside map beats, where nothing is arriving on the map, no
   radar/satellite loop is running, no measurement is being read out ("category", "inches", "feet", digits …) and the words describe
   something filmable (not agencies, products or sources), the map cuts to 4–10 s of stock footage built from those words; long quiet
   stretches alternate footage and map. Total footage is capped at 40 %. Sidecar windows are computed before the split, so
   weather_layers.csv is unchanged. Data-dense scripts (the Ian and Harvey test scripts) correctly get almost none.
- Stock clips carry **no on-screen label** (your choice); they are listed in the credits file. Context tags, place tags and lower
  thirds step aside under footage, so no place name or date is ever captioned over a generic clip.
- A data graphic that would arrive under a title card comes in right after it; a camera move written at the very start of a map
  beat after footage is moved past the cut instead of failing.

## Not reproduced (and why)
- Event footage: only approved clips. Generic stock depends on Pexels search quality (e.g. "floodwater in city streets" returned
  rural flooded fields); the app's VQA flags weak matches for review in the Visual Plan table.
- Circular map insets, HUD bracket/dot-grid decoration, the full-red section card, the people lower-third/monogram (Weather data has
  no people rows) and the subscribe animation.
- The reference's map texture (relief) and glowing US outline: the Weather base imagery is graded instead.
- pakMap's "nothing changes for …" log lines appear in Teamplate renders: that check counts only map events, and Teamplate's titles
  are weather events. Harmless; the shared validator was left untouched.

## Evidence
- `teamplate/compare_weather_vs_teamplate.mp4` — top: Weather, bottom: Teamplate; Hurricane Ian News test project (real NHC/IEM/NASA
  data, the macOS `say` test voice — no project with your recorded voice exists yet), 0–14 s, 48–60 s, 93–115 s.
- `teamplate/frames_A.png`, `frames_B.png` — same moments, Weather on top, Teamplate below. `cut_then_card.png` — the map cut, then the card.
- `teamplate/harvey_footage_weather_vs_teamplate.mp4`, `harvey_frames_A.png`, `harvey_frames_B.png` — a descriptive 72 s Harvey
  post-event test script (same real data; macOS test voice), CSV written per the Teamplate prompt: 32 % stock footage
  (rain on a street, flooded land, flooded street at night, river, storm surge on a sea wall, flooded neighbourhood). Top: Weather, bottom: Teamplate.
- Tests: `test_weather_teamplate.py` (26), `weather-engine/test/tp_unit.test.mjs` (8), `tp_render.test.mjs` (1, real offline render).
