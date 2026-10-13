# Weather — Phase 2 report: forecast automation

Date: 2026-10-13. **Nothing committed.** Only files phase 2 owns were created (contract §5); no existing file was edited.

The app now writes the day's forecast by itself: one command (later, one button) fetches the 20 largest US metros and the national
alerts, picks the day's lead story by fixed rules, writes a 2–4 minute script from the data, builds `beats.csv` +
`weather_layers.csv`, and freezes the data in `resolved.json`. The user only records the script and renders.

## Files created
| File | What it does |
|---|---|
| `weather/data/metros.json` | the 20 largest metros (2020 Census MSA ranking): city centre, IANA zone, NWS grid, office, climate station + fallback, region, county FIPS. Grid, zone, office and both stations checked live on api.weather.gov (contact `https://example.invalid`) |
| `weather/automation/__init__.py`, `__main__.py` | package doc; CLI `python -m weather.automation prep / changes / due / schedule / why` |
| `weather/automation/coverage.py` | `metros()`, `by_region()`, `all_cities()` (cities.json + metros), `install()` (adds the metros to `find_city` at run time, see request 1) |
| `weather/automation/fetch.py` | `fetch_coverage()`: every metro's forecast (+ latest observation) and the national alerts (summarised: event, states, land, centre, metros covered by county FIPS or polygon); `target_date()` (the day every city still has); forecast older than 6 h → that city is left out (more than 3 left out → the prep stops) |
| `weather/automation/story.py` | `pick_story()`: tropical > severe outbreak > extreme heat/cold > heavy rain/flood > routine; pure, deterministic; `Story.why` in plain words |
| `weather/automation/spoken.py` | numbers as spoken (`ninety-two`, `in the low sixties`), NWS short forecast → clause with its own certainty words, footage condition of a day, pronunciation hints |
| `weather/automation/script.py` | `write_script()`: sections (intro, lead, now, footage ×2–3, regions, week, trend, warnings, close) of sentences, each with the data it says (`refs`) |
| `weather/automation/plan.py` | `build_plan()`: beats.csv + weather_layers.csv; camera places chosen so the marked cities are in view; anchors checked with pakMap's matcher; `check_plan()` loads both files the way the render does before anything is written |
| `weather/automation/prep.py` | `prep()`: fetch → story → script → plan → resolved.json, written all at once (prep.json last); refuses to overwrite a script the user edited (unless `force`); optional `library_dir` → `weather.footage_library.prefer_library` |
| `weather/automation/changes.py` | `diff()`, `check()`: what changed since the prep in plain words + the script lines to re-record; writes `changes.json` only |
| `weather/automation/schedule.py` | launchd plist / Task Scheduler XML text, `is_due()`, `catch_up_offer()`, `install()` / `uninstall()` (never called by code or tests), `notify()` |
| `weather/layers/trend.py` | layer type `temp_trend` (`nws:forecast@City,ST#dayA-B`, 3–7 days) |
| `weather-engine/lib/layers/temp_trend.mjs`, `weather-engine/lib/wxu_auto_trend.mjs` | the chart plugin and its pure maths |
| `weather/testdata/automation/coverage_20261012.json`, `prep_recording.json.gz` | a real coverage snapshot (2026-10-12 22:46 UTC); every NWS/GIBS answer of a real prep (gzip, URL → body) |
| `test_weather_auto_{story,script,plan,changes,schedule,trend,prep}.py`, `weather-engine/test/auto_trend.test.mjs` | tests (no network) |

## How to use
```
python -m weather.automation prep --project ~/Weather/2026-10-13 --contact you@example.com [--library ~/MyClips]
#   -> script.txt (record it), beats.csv, weather_layers.csv, resolved.json, coverage.json, prep.json
python -m weather.automation why --project ~/Weather/2026-10-13          # the story and why
python -m weather.automation changes --project ~/Weather/2026-10-13 --contact you@example.com
#   -> "Dallas Tuesday high 92° → 94°", "new: Flood Warning for Harris County, Texas", and the lines to re-record
python -m weather render --project ~/Weather/2026-10-13 --voiceover vo.wav --out forecast.mp4
python -m weather.automation schedule --root ~/Weather --contact you@example.com [--windows]   # prints the OS task, installs nothing
```

### Story rules (`story.py`)
Only alerts over land in the lower 48 count. First rule that holds wins:
1. **tropical** — any Hurricane / Tropical Storm / Storm Surge warning or watch, or Extreme Wind Warning.
2. **severe** — ≥3 tornado warnings, or ≥2 tornado + severe thunderstorm watches, or ≥10 severe thunderstorm warnings.
3. **extreme_temp** — an Extreme/Excessive Heat or Extreme Cold / Wind Chill warning over a covered city or ≥3 nationally, or highs ≥100 °F / lows ≤10 °F in ≥3 covered cities on the day.
4. **heavy_rain** — a Flash Flood Warning, ≥2 Flood / Flash Flood Watches, a flood alert over a covered city, or rain/storms at ≥70 % in ≥3 covered cities.
5. **routine** — the covered city with the highest chance of rain/snow (≥30 %), else the biggest change in its highs over the next 5 days.

Lead city: the covered city under the most story alerts, else the nearest to their middle. River Flood Warnings alone do not make a
heavy-rain day (there are usually a dozen ongoing). Example `why` (real data, 2026-10-12):
```
- The forecast is for Tuesday, October 13 (20 cities, 67 alerts over the lower 48).
- Tropical: no hurricane, tropical storm or storm surge alerts over land.
- Severe: 0 tornado warning(s), 0 tornado watch(es), 0 severe thunderstorm warning(s), 0 severe thunderstorm watch(es); not an outbreak (...).
- Extreme heat/cold: 0 heat or cold warning(s), none over a covered city; 0 city(ies) at 100°F or more, 0 at 10°F or less (needs 3).
- Lead: heavy rain and flooding: 3 flood watch(es) in UT, AZ.
```

### Script rules (`script.py`, checked by `test_weather_auto_script.py`)
- Every number spoken is a snapshot value **and** one of that sentence's own refs (exact words, or the band the value is in); dates are ordinals.
- Weather words are the city's own NWS short forecast for that day, with its certainty ("a slight chance of", "a chance of", "… likely", "expect …").
- Comparisons only inside one city's own days ("Highs climb to eighty-five by Thursday" only when Thursday ≥ today + 5). No "cooler/warmer than".
- "today" only when the forecast day is the prep's Central date; otherwise the weekday.
- Hints in brackets only for names in `spoken.HINTS` (e.g. "Maricopa [mair-ih-KOH-puh] County"); they are left out of the beats' text.
- Closing: "… follow your local National Weather Service office. For Phoenix, that is the National Weather Service Phoenix office, at weather dot gov."
- Same day → same wording; the date seeds the templates.

### Plan rules (`plan.py`, checked by `test_weather_auto_plan.py`)
One beat per section; the text cells joined are the script word for word. National beats use `38.5,-97.5` / `continental`; others a state
or named region (frame `region`) chosen so the marked cities are in view (Texas for Dallas + Houston). `type` = `push_in` for the lead,
empty to fly, `hold` when the place is the same. Footage beats (2–3) get 1–2 `stock_video:` clips from a fixed list for that city's
condition (rain/storm/snow/fog/heat/cold/wind/sun/cloud); every description is recognised by `weather.footage_library.condition_of`.
Weather layers: satellite (b1, until end), ≤4 temp markers per beat, alert_area for the story's states (legend once), now card,
forecast strip, temp_trend, alert_area for the most common other warning, a source line on every beat that shows a number; nothing on
footage beats.

### `temp_trend` (new layer type)
```
beat,vo_anchor,t,id,type,place,data_source,hold,until,extra
b13,And here are,,b13_trend,temp_trend,"Phoenix, AZ","nws:forecast@Phoenix,AZ#day2-7",,,
b13,And here are,,b13_src,source_line,,,,,
```
`extra`: `{"title": "..."}` (default `PHOENIX, AZ · HIGHS AND LOWS`). Every high and low drawn is in the numbers report with its
URL and issue time. Same place as the forecast strip (one or the other per beat). Frame: `docs/weather/phase2/trend.png`.

## Tests
E2E_TESTS_PLACEHOLDER

## End-to-end run
E2E_PLACEHOLDER

## Known limits
- **NWS overnight cadence vs the 6 h rule.** Offices update forecasts around 3–5 AM and 3–5 PM local; at night many are 7–11 h old. The prep leaves such cities out (up to 3) and stops beyond that, so a prep run between about 10 PM and 4 AM Central fails cleanly. At 5:30 AM Central the eastern offices are fresh; a western office that has not issued yet may be left out (named in prep.json notes).
- **Render after a late recording.** The phase-1 render rule refuses a forecast older than 6 h, so a 5:30 AM prep must be rendered by about 9:30–11 AM, or the data fetched again (`python -m weather fetch`) and `changes` checked first.
- **Alerts in resolved.json.** The render refuses when ANY alert of a fetched state has ended, even one the layer does not show (request 2).
- The Pacific region rarely fits Seattle and Los Angeles in one view; a city out of view is said but gets no marker.
- `stock_video:` footage comes from Pexels by description; the clip that comes back is not checked against the description (as in Hybrid).
- `due` uses the user's contact on the command line of the OS task (on their own machine only).

## Requests for the integrator
INTEGRATOR_PLACEHOLDER
