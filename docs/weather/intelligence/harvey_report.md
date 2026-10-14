# Weather Intelligence report

Mode: A — no weather layers file: every data graphic was found by the engine

## The event

- Category: flood (also: hurricane, heavy rain, tropical storm)
- Storm: Harvey — AL092017 (2017), Harvey = AL092017 (2017), chosen by the year the script says (2017)
- Date: 2017-08-25 (the story names 2017-08-25, 2017-08-27, 2017-08-28, 2017-08-30, 2017-09-01, 2017-08-29, 2017-08-22, 2017-08-31, 2017-09-05)
- Key moment: 2017-08-26T03:00:00Z — the strongest landfall in TX, LA in the NHC best track (HURDAT2): 2017-08-26T03:00:00Z, 130 mph
- Where: TX, LA; map focus Houston
- Recorded: 2026-10-14 (the voiceover file's date (an assumption))
- Landfall (NHC best track): 2017-08-18T10:00:00Z at 13.1, -59.6
- Landfall (NHC best track): 2017-08-18T15:00:00Z at 13.2, -61.2
- Landfall (NHC best track): 2017-08-26T03:00:00Z at 28.0, -96.9
- Landfall (NHC best track): 2017-08-26T06:00:00Z at 28.2, -97.1
- Landfall (NHC best track): 2017-08-30T08:00:00Z at 29.8, -93.5

## Assumptions and open questions

- Assumed: relative days (yesterday, Sunday ...) are counted from the voiceover file's date (an assumption): 2026-10-14

## Added for you

- **auto_headline** (headline) on beat b1 (0.0s), at the words "This is a post-event report"
  - why: the opening lower-third names the event, the place and the day
- **auto_best_track** (storm_track) on beat b2 (22.2s), at the words "Harvey made landfall on" — nhc:track@AL092017#best
  - why: the narration describes Harvey's path or strength; NHC best track of AL092017
- **auto_rain_map** (rain_map) on beat b3 (54.9s), at the words "This map adds up" — mrms:total@2017-08-25..2017-09-01
  - why: MRMS radar-estimated rain 2017-08-25 to 2017-09-01 around Houston (an estimate, labelled so)
- **auto_rain_totals** (rain_total) on beat b4 (78.7s), at the words "The gauges tell the same story" — acis:pcpn_total@BPT|HOU|IAH|GLS|SGR|CXO#2017-08-25..2017-09-01
  - why: observed rain at the gauges the beat names (BPT, HOU, IAH, GLS, SGR, CXO), 2017-08-25 to 2017-09-01
- **auto_record** (record) on beat b5 (100.6s), at the words "At Houston, the long-term record" — acis:record@Houston,TX#pcpn#2017-08-27
  - why: where 2017-08-27 stands in Houston's period of record (pcpn, RCC-ACIS ranking)
- **auto_crest_buffalo_bayou** (river_crest) on beat b6 (118.9s), at the words "Buffalo Bayou, which runs" — usgs:crest@08074000#2017-08-22..2017-09-08
  - why: Buffalo Bayou at Houston, TX (08074000): its place is named in the narration; the highest gage height 2017-08-22 to 2017-09-08
- **auto_crest_san_jacinto_river** (river_crest) on beat b6 (118.9s), at the words "East of the city," — usgs:crest@08072050#2017-08-22..2017-09-08
  - why: San Jacinto Rv nr Sheldon, TX (08072050): its place is named in the narration; the highest gage height 2017-08-22 to 2017-09-08
- **auto_before_after** (before_after) on beat b7 (152.6s), at the words "From space, the change is clear" — gibs:falsecolor@2017-08-22|2017-08-31
  - why: NASA falsecolor pictures of 2017-08-22 and 2017-08-31 (the two days the beat names)
- **auto_timeline** (event_timeline) on beat b2 (22.2s), at the words "Here is the timeline" — post:timeline@2017-08-21..2017-09-05
  - why: dated marks from the data: nhc:landfall@AL092017#1, nhc:landfall@AL092017#3, acis:peak_day@Houston,TX#2017-08-21..2017-09-05, usgs:crest@08074000#2017-08-22..2017-09-08
- Source lines on beats b2, b3, b4, b5, b6, b7 (they name the data on screen)

## Left out, and why

- Radar loop with warnings: the narration never discusses it
- Satellite loop (daily true colour): beat b7 is full (it already has a radar or satellite loop)
- Warnings issued (count): the narration never discusses it
- Excessive rainfall outlook: the narration never discusses it

## The narration's numbers

11 of 12 numbers the narrator says match a number the graphics show. The others are not wrong — no source the engine read shows them (a damage survey or an article it cannot read), so check them yourself.

- "category 4" (beat b2): matches [auto_best_track] AL092017 best track 2017-08-26T00:00:00+00:00: CAT 4 · 130 MPH · AUG 25 7 PM (NHC best track)
- "one hundred thirty miles per hour" (beat b2): matches [auto_best_track] AL092017 best track 2017-08-26T00:00:00+00:00: CAT 4 · 130 MPH · AUG 25 7 PM (NHC best track)
- "sixty three inches" (beat b3): matches [auto_rain_map] wettest cell of the rain map at 30.04N 94.17W (a day there reached the top of MRMS's encoding: the total is at least this): PEAK ESTIMATE AT LEAST 63 IN (NOAA MRMS 24-hour radar estimates, summed, wettest cell)
- "forty seven point four eight inches" (beat b4): matches [auto_rain_totals] PORT ARTHUR observed rainfall AUG 25–SEP 1, 2017: 47.48 IN (RCC-ACIS daily precipitation, observed (trace = 0))
- "thirty seven point zero one inches" (beat b4): matches [auto_rain_totals] HOUSTON HOBBY observed rainfall AUG 25–SEP 1, 2017: 37.01 IN (RCC-ACIS daily precipitation, observed (trace = 0))
- "twenty one inches" (beat b4): matches [auto_rain_totals] CONROE observed rainfall AUG 25–SEP 1, 2017: 21.44 IN (RCC-ACIS daily precipitation, observed (trace = 0))
- "sixteen point zero seven inches" (beat b5): matches [auto_record] HOUSTON AREA pcpn on 2017-08-27: 16.07 IN (RCC-ACIS daily pcpn, observed)
- "ten point three four inches" (beat b5): matches [auto_record] HOUSTON AREA previous record (1989-06-26): 10.34 IN (RCC-ACIS period-of-record summary)
- "forty one point nine feet" (beat b6): matches [auto_crest_buffalo_bayou] BUFFALO BAYOU crest, 2017-08-28 01:00 local (the record has a gap beside the crest: its time is uncertain): 41.9 FT (USGS gage height (00065), approved)
- "thirty two feet" (beat b6): matches [auto_crest_buffalo_bayou] BUFFALO BAYOU hydrograph line (NWS's current flood stage): MAJOR FLOOD 32.0 FT (NWS water gauge flood categories (current))
- "twenty eight point seven two feet" (beat b6): matches [auto_crest_san_jacinto_river] SAN JACINTO RIVER crest, 2017-08-29 19:30 local (the record has a gap beside the crest: its time is uncertain): 28.72 FT (USGS gage height (00065), approved)
- "twenty three point zero three feet" (beat b8): not verified by a fetched source

## Sources

- NHC HURDAT2: 2 request(s) ok
- NHC ATCF storm list: 1 request(s) ok
- USGS site service: 2 request(s) ok

What each source is:

- NHC HURDAT2 (best_track): the final reviewed best track, with landfall (L) records. Times: fix times (UTC). Caveats: the current season is not in it yet. Credit: NOAA National Hurricane Center.
- NHC ATCF storm list (index): identity of every numbered Atlantic / Pacific system: name, basin, number, year, first and last times, status (ARCHIVE / WARNING / GENESIS / METWATCH). Times: first / last fix times (UTC, YYYYMMDDHH). Caveats: a current-season storm has an open end time (9999999999) and its last status, not its peak. Credit: NOAA National Hurricane Center.
- USGS site service (index): gauge names, numbers and positions. Times: -. Caveats: a name search can match several gauges on one river. Credit: U.S. Geological Survey.

## Evidence

- identity: Harvey (AL092017) — storm identity = AL092017 (issued 2017-08-16T06:00:00Z)
- best_track: Harvey (AL092017) — landfall 1 = 2017-08-18T10:00:00Z (issued 2017-08-18T10:00:00Z) · sustained wind 45 mph (40 kt)
- best_track: Harvey (AL092017) — landfall 2 = 2017-08-18T15:00:00Z (issued 2017-08-18T15:00:00Z) · sustained wind 45 mph (40 kt)
- best_track: Harvey (AL092017) — landfall 3 = 2017-08-26T03:00:00Z (issued 2017-08-26T03:00:00Z) · sustained wind 130 mph (115 kt)
- best_track: Harvey (AL092017) — landfall 4 = 2017-08-26T06:00:00Z (issued 2017-08-26T06:00:00Z) · sustained wind 120 mph (105 kt)
- best_track: Harvey (AL092017) — landfall 5 = 2017-08-30T08:00:00Z (issued 2017-08-30T08:00:00Z) · sustained wind 45 mph (40 kt)
- best_track: Harvey (AL092017) — peak sustained wind = 130 mph (issued 2017-08-26T03:00:00Z)
- best_track: Harvey (AL092017) — minimum pressure = 937 mb (issued 2017-08-26T03:00:00Z)
- identity: Buffalo Bayou — USGS gauge = 08074000
- identity: San Jacinto River — USGS gauge = 08072050
- best_track: hurricane.best_track — storm_track = nhc:track@AL092017#best
- estimate: rain.map — rain_map = mrms:total@2017-08-25..2017-09-01 [ESTIMATE]
- observed: rain.totals — rain_total = acis:pcpn_total@BPT|HOU|IAH|GLS|SGR|CXO#2017-08-25..2017-09-01
- observed: record — record = acis:record@Houston,TX#pcpn#2017-08-27
- observed: river.crest — river_crest = usgs:crest@08074000#2017-08-22..2017-09-08
- observed: river.crest — river_crest = usgs:crest@08072050#2017-08-22..2017-09-08
- observed: satellite.before_after — before_after = gibs:falsecolor@2017-08-22|2017-08-31
- derived: timeline — event_timeline = post:timeline@2017-08-21..2017-09-05
