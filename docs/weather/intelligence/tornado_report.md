# Weather Intelligence report

Mode: A — no weather layers file: every data graphic was found by the engine

## The event

- Category: tornado (also: severe, hurricane, forecast)
- Also named: Isaias = AL092026 (2026), chosen by the year the script says (2026); named 1 time(s) in a tornado story, so it is context, not the subject (no storm graphics)
- Date: 2026-10-11 (the story names 2026-10-11, 2026-10-12, 2026-10-13)
- Key moment: 2026-10-11T10:05:00Z — "6:05 a.m." on 2026-10-11 (beat b5)
- SPC convective day: 2026-10-10 (12 UTC to 12 UTC)
- Where: SC; map focus Newberry County
- Recorded: 2026-10-13 (the voiceover file's date (an assumption))

## Assumptions and open questions

- Assumed: "Sunday" is read as Sunday October 11, 2026, the Sunday nearest the date the script says (October 11, 2026)
- Assumed: "Monday" is read as Monday October 12, 2026, the Monday nearest the date the script says (October 11, 2026)
- Assumed: "Tuesday" is read as Tuesday October 13, 2026, the Tuesday nearest the date the script says (October 13, 2026)

## Added for you

- **auto_headline** (headline) on beat b1 (0.0s), at the words "A tornado carrying estimated"
  - why: the opening lower-third names the event, the place and the day
- **auto_radar** (radar) on beat b18 (259.8s), at the words "The report says the" — iem:radar@2026-10-11T09:55Z..2026-10-11T10:25Z#n0q
  - why: radar mosaic fitted to the warnings it shows (10:05Z to 10:11Z): 2026-10-11T09:55Z..2026-10-11T10:25Z
- **auto_warnings** (warnings_archive) on beat b18 (259.8s), at the words "The report says the" — iem:warnings@2026-10-11T09:55Z..2026-10-11T10:25Z#TO
  - why: NWS warnings, same window (fitted to the warnings it shows (10:05Z to 10:11Z): 2026-10-11T09:55Z..2026-10-11T10:25Z)
- **auto_reports** (storm_reports) on beat b22 (314.5s), at the words "In Allendale County, the" — spc:reports@2026-10-10#tornado
  - why: SPC preliminary reports of the convective day 2026-10-10 (the event at 2026-10-11T10:05Z is before 12 UTC, so it is in the previous day's file)
- **auto_label_newberry_county** (place_label) on beat b1 (0.0s), at the words "A tornado carrying estimated"
  - why: Newberry County is named here; the label marks the county's centre on the map
- **auto_label_fairfield_county** (place_label) on beat b5 (53.9s), at the words "The location is close"
  - why: Fairfield County is named here; the label marks the county's centre on the map
- **auto_label_allendale_county** (place_label) on beat b21 (304.0s), at the words "The article published Monday"
  - why: Allendale County is named here; the label marks the county's centre on the map
- Source lines on beats b18, b22 (they name the data on screen)

## Left out, and why

- SPC outlook: the narration never discusses it
- Active alerts: active alerts are for today's video; past warnings come from the archive (beat b18)
- Warnings issued (count): the narration never discusses it
- Report counter: the narration never discusses it
- Excessive rainfall outlook: the narration never discusses it

## The narration's numbers

0 of 6 numbers the narrator says match a number the graphics show. The others are not wrong — no source the engine read shows them (a damage survey or an article it cannot read), so check them yourself.

- "115 miles per hour" (beat b1): not verified by a fetched source
- "450 yards" (beat b2): not verified by a fetched source
- "EF2" (beat b3): not verified by a fetched source
- "1.47 miles" (beat b6): not verified by a fetched source
- "135 miles per hour" (beat b14): not verified by a fetched source
- "EF1" (beat b22): not verified by a fetched source

## Sources

- IEM NEXRAD composite (N0Q): 2 request(s) ok
- IEM storm-based warnings archive: 2 request(s) ok
- NHC ATCF storm list: 1 request(s) ok

What each source is:

- IEM NEXRAD composite (N0Q) (observed): base reflectivity mosaic of NWS radars. Times: scan time (UTC). Caveats: a mosaic made by IEM, not an official NWS product; since 2022 N0Q is a downscaled N0B. Credit: Radar: NOAA/NWS NEXRAD via Iowa Environmental Mesonet.
- IEM storm-based warnings archive (warning): NWS warning polygons (tornado, severe thunderstorm, flash flood, extreme wind ...). Times: issue / expire (UTC). Caveats: a polygon may be re-issued (one warning, many polygons): counts use one per event id. Credit: National Weather Service via IEM.
- NHC ATCF storm list (index): identity of every numbered Atlantic / Pacific system: name, basin, number, year, first and last times, status (ARCHIVE / WARNING / GENESIS / METWATCH). Times: first / last fix times (UTC, YYYYMMDDHH). Caveats: a current-season storm has an open end time (9999999999) and its last status, not its peak. Credit: NOAA National Hurricane Center.

## Evidence

- identity: Isaias (AL092026) — storm identity = AL092026 [PRELIMINARY] (issued 2026-09-30T00:00:00Z) · the storm is still listed as active: its record may change
- identity: Isaias (AL092026) — storm type in the list = TS [PRELIMINARY]
- observed: radar.loop — radar = iem:radar@2026-10-11T09:55Z..2026-10-11T10:25Z#n0q
- warning: NWS warnings in the window — warning polygons = 1 · one warning can have several polygons (updates)
- preliminary_report: tornado reports — count = 9 [PRELIMINARY] · reports are not tornado counts: one tornado can bring several reports
- preliminary_report: tornado report — report = 6 SSW Appleton [PRELIMINARY] (issued 2026-10-10T20:17:00+00:00)
- preliminary_report: tornado report — report = 3 N Appleton [PRELIMINARY] (issued 2026-10-10T20:34:00+00:00)
- preliminary_report: tornado report — report = 3 NNE Appleton [PRELIMINARY] (issued 2026-10-10T20:39:00+00:00)
- preliminary_report: tornado report — report = 1 WSW Kline [PRELIMINARY] (issued 2026-10-10T20:41:00+00:00)
- preliminary_report: tornado report — report = 1 WSW Kline [PRELIMINARY] (issued 2026-10-10T20:47:00+00:00)
- preliminary_report: tornado report — report = 3 NNW Barnwell [PRELIMINARY] (issued 2026-10-10T21:10:00+00:00)
- preliminary_report: tornado report — report = 5 SSW Elko [PRELIMINARY] (issued 2026-10-10T21:15:00+00:00)
- preliminary_report: tornado report — report = 5 NNE Aiken State Park [PRELIMINARY] (issued 2026-10-10T21:58:00+00:00)
- preliminary_report: tornado report — report = 2 WSW Blair [PRELIMINARY] (issued 2026-10-11T10:05:00+00:00)

## Notes

- the script calls Isaias a hurricane; NHC's storm list records its type as TS (AL092026) — worth checking before publishing
