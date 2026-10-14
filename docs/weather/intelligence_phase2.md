# Weather Intelligence — Phase 2 (hurricanes), 2026-10-14

Status: implemented and tested, **not committed** (waiting for approval). Phase 1 is commit `81acb3b`.

## Already in place from phase 1 (verified again on Ian)
Storm identity from the NHC storm list (shared names never guessed), the final best track (HURDAT2: landfalls, peak), advisory
selection by binary search on the archive's ADVDATEs, the 5-day cone with NHC's coastal hurricane / tropical-storm watches and
warnings, the forecast track, the daily VIIRS satellite loop, radar + archived warnings at landfall, a warnings counter, WPC ERO.

## New in phase 2
| Graphic | How | Data |
|---|---|---|
| Storm statistics card (`storm_stats`, new layer + `weather-engine/lib/layers/storm_stats.mjs`) | placed on a beat that discusses the storm's strength; peak strength, lowest pressure, the story's landfall, each with date and time | HURDAT2 (final). A current-season storm uses NHC's working best track, labelled PRELIMINARY, with no landfall row (the working track has no landfall flags) |
| Card placement | the side away from the storm's track as the beat's camera sees it (HURDAT2 positions vs the camera's centre, `hybrid.geo`) | — |
| Landfall marker | `place_label` "LANDFALL" at the HURDAT2 landfall the story is about, on the beat that says it came ashore / moved onshore | HURDAT2 L record |
| Best-track labels at the narrated times | "eight in the morning … September 28" → the 12Z point; "two in the afternoon" → 18Z (a said time within 45 min of a 6-hourly step). If none is a track point the layer labels the strongest point (storm_track change, safe default) | NHC best track |
| No second title | the opening lower-third is skipped when the beat plan already opens with its own title card | — |
| Context storms checked against the best track | a storm named in passing ("remnants of Hurricane Isaias") is checked with its best track peak, never the storm list's type | NHC GIS best track |

## Validation: Hurricane Ian 2022, no weather CSV (test project, synthetic voice)
Engine result: AL092022 (year said), strongest FL landfall 19:05Z (HURDAT2, landfall 3 of 5), advisory 024 for "eleven o'clock"
(15Z), radar 14–22Z (narrated), 5 extreme wind warnings counted, WPC ERO high risk, stats card CAT 5 · 160 MPH / 937 MB /
landfall CAT 4 · 150 MPH Sep 28 3:05 PM EDT, landfall marker at 26.7N 82.2W, best-track labels at 8 AM and 2 PM EDT.
Narration numbers matched by data on screen: 5 of 6 (the unverified one is the ISS's 260-mile altitude, which no weather source has).

Rendered twice; frames inspected (`docs/weather/intelligence/ian_*.png`, video `docs/weather/renders/ian_intelligence_no_sidecar.mp4`,
not committed). v1 had three defects, fixed in v2: the stats card covered the track (now on the side away from it), the engine's
lower-third doubled the plan's own HURRICANE IAN title (now skipped), the source line named the best track twice.

## Tests
`test_weather_intel.py` 46 (6 new: stats card values and report lines, working-track card, current-season storm, context storm
checked against its best track, card side, no second title); `weather-engine/test/storm_stats.test.mjs` 2 (event checks, card
inside the frame on both sides). New fixture: `al092026_best_track.zip` (NHC working best track of Isaias).

Full suite: 3866 tests, all pass except `test_flow_agent_connection` once in the parallel run (a Flow reconnect timing test; no
Weather code involved; it passed alone three times and in both phase-1 full runs). pakmap-engine 133/133, weather-engine 59/59.

## Not done in phase 2
* Track-evolution comparison (several advisories' cones over time) and advisory timeline.
* Verified storm-history comparison (Ian vs other Florida landfalls).
* GOES 10-minute loops for current storms (the daily true-colour loop is used; GOES-East is kept by GIBS for ~2 months).
* Rain / flood maps for hurricanes exist (rain_map, rain_total) but are added only when the narration discusses rainfall.
