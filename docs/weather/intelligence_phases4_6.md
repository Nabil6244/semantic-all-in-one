# Weather Intelligence — Phases 4, 5 and 6 (2026-10-14)

Done in one pass, kept small on purpose (the user asked not to spend credits). Not committed until approved.

## Phase 4 — floods and post-event (Harvey 2017)
* **Flood progression map**: `rain_map` takes `extra.by_day` — the MRMS running total shown day by day ("RAINFALL SO FAR",
  then the full total with its peak). The engine turns it on when the story spans 3+ days and the narration walks through them
  ("day by day"). Harvey: Aug 25 → Sep 1, eight steps on beat b3.
* Already in place and re-checked on Harvey with no CSV: gauge totals (BPT, HOU, IAH, GLS, SGR, CXO), Houston record (16.07 in vs
  10.34 in, 1989), Buffalo Bayou 08074000 and San Jacinto 08072050 crests found by name, before/after Aug 22 / Aug 31, timeline,
  best track; flash-flood warnings come with a radar loop when a flood story talks about radar or warnings.
* `python -m weather check` on the no-CSV Harvey project: 16 graphics, 31 numbers on screen, each with its source.

## Phase 5 — forecast, heat, winter
* **Snowfall totals** (`snow_total`, ACIS `snow` element; chip or bars like rain totals). The engine adds it to winter stories on a
  beat that talks about snow and names stations. Verified live: Denver International 5.7 in on 2024-03-14 (fixture saved).
* Forecast stories: the forecast strip, current conditions and active alerts specs exist from phase 1 (they need the NWS contact
  and a current story); the daily forecast automation is unchanged.

## Not done (honest list)
* **Winter warnings**: the IEM storm-based warnings archive holds polygon warnings (tornado, severe, flash flood, extreme wind ...);
  winter storm / blizzard warnings are zone-based and are not in it. Not built rather than guessed.
* Heat anomaly vs normals, heat index, wind chill; fronts / pressure systems (no archive verified).
* Observed-vs-forecast rain (WPC QPF archive not verified); several hurricane cones over time; GOES 10-minute loops; warning/report
  timeline; surveyed-tornado counter; app report panel / overrides editor / recording-date field; a live click-through of the app.

## Phase 6 — verification
* Full Python suite **3878 tests OK**; pakmap-engine **133/133**; weather-engine **62/62** (includes `test_weather_isolation`,
  upstream drift and packaging tests).
* Windows CI fixes: portable date formatting (`%-d`) and Weather's own US time-zone rules instead of `zoneinfo` (Windows has no tz
  database) — the cause of the `test_weather_intel` failures on the Windows runner.
* Final renders (no weather CSV): Harvey and the tornado (survey tracks now limited to the 6 that start in South Carolina).
  Stillness and frames: see the end of this file.

### Final render results (measured on the videos: frames compared twice a second)
| Video | Longest still moment | Time in still stretches of 6 s+ | Checked |
|---|---|---|---|
| Harvey, no CSV (`docs/weather/renders/harvey_intelligence_final.mp4`) | 4.5 s | 0 s | flood map fills in day by day (frames in `intelligence/harvey_flood_progression.png`) |
| Tornado, your voiceover, no CSV (`docs/weather/renders/tornado_intelligence_final.mp4`) | 7.0 s | 19.5 s | survey layers draw the 6 tracks that start in SC only |
