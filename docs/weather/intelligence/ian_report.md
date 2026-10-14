# Weather Intelligence report

Mode: A — no weather layers file: every data graphic was found by the engine

## The event

- Category: hurricane (also: heavy rain, tornado)
- Storm: Ian — AL092022 (2022), Ian = AL092022 (2022), chosen by the year the script says (2022)
- Date: 2022-09-28
- Key moment: 2022-09-28T19:05:00Z — the strongest landfall in FL in the NHC best track (HURDAT2): 2022-09-28T19:05:00Z, 150 mph
- Where: FL; map focus landfall
- Recorded: 2026-10-14 (the voiceover file's date (an assumption))
- Landfall (NHC best track): 2022-09-27T08:30:00Z at 22.2, -83.7
- Landfall (NHC best track): 2022-09-28T02:00:00Z at 24.6, -82.9
- Landfall (NHC best track): 2022-09-28T19:05:00Z at 26.7, -82.2
- Landfall (NHC best track): 2022-09-28T20:35:00Z at 26.8, -82.0
- Landfall (NHC best track): 2022-09-30T18:05:00Z at 33.3, -79.2

## Assumptions and open questions

- Assumed: "Wednesday" is read as Wednesday September 28, 2022, the Wednesday nearest the date the script says (September 28, 2022)

## Added for you

- **auto_best_track** (storm_track) on beat b2 (24.0s), at the words "This is the storm's" — nhc:track@AL092022#best
  - why: the narration describes Ian's path or strength; NHC best track of AL092022, labelled at the times the beat says (2022-09-28T12:00Z, 2022-09-28T18:00Z)
- **auto_cone** (storm_cone) on beat b3 (50.9s), at the words "That morning, the hurricane" — nhc:cone@AL092022#024
  - why: advisory 024 of AL092022, issued 2022-09-28T15:00Z: the last one at or before 2022-09-28T15:00Z (the advisory time the beat says)
- **auto_cone_track** (storm_track) on beat b3 (50.9s), at the words "That morning, the hurricane" — nhc:track@AL092022#024
  - why: the forecast track and points of the same advisory
- **auto_radar** (radar) on beat b4 (72.7s), at the words "Now the radar, from" — iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q
  - why: radar mosaic 2022-09-28T14:00Z..2022-09-28T22:00Z (the times the beat says)
- **auto_warnings** (warnings_archive) on beat b4 (72.7s), at the words "Now the radar, from" — iem:warnings@2022-09-28T14:00Z..2022-09-28T22:00Z#EW,TO
  - why: NWS EW, TO warnings in the same window, each from its issue time
- **auto_storm_stats** (storm_stats) on beat b2 (24.0s), at the words "At eight in the" — nhc:stats@AL092022
  - why: the narration discusses Ian's strength; peak, lowest pressure and landfall from HURDAT2
- **auto_sat_loop** (satellite_loop) on beat b1 (0.0s), at the words "Here is the storm" — gibs:truecolor_loop@2022-09-23..2022-09-28
  - why: one NASA true-colour picture a day, 2022-09-23 to 2022-09-28, as the narration describes the storm from space
- **auto_warn_count** (counter) on beat b5 (93.7s), at the words "In all, the National" — iem:warnings@2022-09-28T12:00Z..2022-09-29T00:00Z#EW
  - why: the narration counts EW warnings; IEM archive 2022-09-28T12:00Z..2022-09-29T00:00Z
- **auto_ero** (wpc_ero) on beat b5 (93.7s), at the words "The Weather Prediction Center's" — wpc:ero@2022-09-28#day1
  - why: the narration discusses the rain outlook; WPC day 1 excessive rainfall outlook of 2022-09-28
- **auto_landfall** (place_label) on beat b4 (72.7s), at the words "The warnings appear as"
  - why: the landfall the story is about: HURDAT2 2022-09-28T19:05:00Z at 26.7, -82.2
- Source lines on beats b2, b3, b4, b1, b5 (they name the data on screen)

## Left out, and why

- Opening lower-third: the beat plan already opens with its own title card on that beat (beat b1)
- Rainfall (radar estimate) map: the narration never discusses it
- Gauge rain totals: the narration never discusses it
- Verified record: the narration never discusses it
- Before and after from space: the narration never discusses it
- Event timeline: the narration never discusses it

## The narration's numbers

5 of 6 numbers the narrator says match a number the graphics show. The others are not wrong — no source the engine read shows them (a damage survey or an article it cannot read), so check them yourself.

- "category 5" (beat b2): matches [auto_best_track] AL092022 best track 2022-09-28T12:00:00+00:00: CAT 5 · 160 MPH · SEP 28 8 AM (NHC best track)
- "one hundred sixty miles per hour" (beat b2): matches [auto_best_track] AL092022 best track 2022-09-28T12:00:00+00:00: CAT 5 · 160 MPH · SEP 28 8 AM (NHC best track)
- "category 4" (beat b2): matches [auto_best_track] AL092022 best track 2022-09-28T18:00:00+00:00: CAT 4 · 155 MPH · SEP 28 2 PM (NHC best track)
- "one hundred fifty five miles per hour" (beat b3): matches [auto_best_track] AL092022 best track 2022-09-28T18:00:00+00:00: CAT 4 · 155 MPH · SEP 28 2 PM (NHC best track)
- "five extreme wind warnings" (beat b5): matches [auto_warn_count] extreme wind warnings issued: 5 (NWS Extreme Wind Warnings issued (IEM archive))
- "two hundred sixty miles" (beat b6): not verified by a fetched source

## Sources

- NHC GIS advisory archive: 7 request(s) ok
- NHC HURDAT2: 2 request(s) ok
- NHC ATCF storm list: 1 request(s) ok

What each source is:

- NHC GIS advisory archive (forecast): an advisory's 5-day cone, forecast track and points, coastal watches / warnings. Times: ADVDATE (issue, local), forecast points VALIDTIME (UTC). Caveats: a forecast, not what happened; advisory numbers have no times in the archive listing (the engine reads each file's ADVDATE). Credit: NOAA National Hurricane Center.
- NHC HURDAT2 (best_track): the final reviewed best track, with landfall (L) records. Times: fix times (UTC). Caveats: the current season is not in it yet. Credit: NOAA National Hurricane Center.
- NHC ATCF storm list (index): identity of every numbered Atlantic / Pacific system: name, basin, number, year, first and last times, status (ARCHIVE / WARNING / GENESIS / METWATCH). Times: first / last fix times (UTC, YYYYMMDDHH). Caveats: a current-season storm has an open end time (9999999999) and its last status, not its peak. Credit: NOAA National Hurricane Center.

## Evidence

- identity: Ian (AL092022) — storm identity = AL092022 (issued 2022-09-22T18:00:00Z)
- best_track: Ian (AL092022) — landfall 1 = 2022-09-27T08:30:00Z (issued 2022-09-27T08:30:00Z) · sustained wind 125 mph (110 kt)
- best_track: Ian (AL092022) — landfall 2 = 2022-09-28T02:00:00Z (issued 2022-09-28T02:00:00Z) · sustained wind 125 mph (110 kt)
- best_track: Ian (AL092022) — landfall 3 = 2022-09-28T19:05:00Z (issued 2022-09-28T19:05:00Z) · sustained wind 150 mph (130 kt)
- best_track: Ian (AL092022) — landfall 4 = 2022-09-28T20:35:00Z (issued 2022-09-28T20:35:00Z) · sustained wind 145 mph (125 kt)
- best_track: Ian (AL092022) — landfall 5 = 2022-09-30T18:05:00Z (issued 2022-09-30T18:05:00Z) · sustained wind 80 mph (70 kt)
- best_track: Ian (AL092022) — peak sustained wind = 160 mph (issued 2022-09-28T12:00:00Z)
- best_track: Ian (AL092022) — minimum pressure = 937 mb (issued 2022-09-28T12:00:00Z)
- best_track: hurricane.best_track — storm_track = nhc:track@AL092022#best
- forecast: hurricane.cone — storm_cone = nhc:cone@AL092022#024
- forecast: hurricane.cone — storm_track = nhc:track@AL092022#024
- observed: radar.loop — radar = iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q
- warning: NWS warnings in the window — warning polygons = 9 · one warning can have several polygons (updates)
- observed: hurricane.stats — storm_stats = nhc:stats@AL092022
- observed: hurricane.satellite_loop — satellite_loop = gibs:truecolor_loop@2022-09-23..2022-09-28
- warning: Extreme Wind Warnings Issued — count = 5 (issued 2022-09-29T00:00:00+00:00)
- forecast: rain.ero — wpc_ero = wpc:ero@2022-09-28#day1
