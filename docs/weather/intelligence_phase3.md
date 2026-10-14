# Weather Intelligence — Phase 3 (severe weather), 2026-10-14

Status: implemented and tested, **not committed** (waiting for approval). Phase 1 `81acb3b`, phase 2 `e25d6a4`.

## The October 11 test event, verified before rendering
Year, identity and archive coverage were checked against the archives themselves (the engine now does this for every tornado /
severe story with a known moment and writes it to the report, "Archive coverage of the event"):

| Archive | What it holds for 2026-10-11 10:05Z, Newberry County SC |
|---|---|
| SPC storm reports | the 1005 UTC tornado report (2 WSW Blair, Newberry Co.) is in the file of convective day **2026-10-10** (12Z–12Z); the Oct 11 file has no SC reports |
| IEM warnings archive | Tornado Warning **CAE #16**, issued 10:05Z, ended about 10:11Z |
| NWS Damage Assessment Toolkit | surveyed track 10:05:48Z–10:09:01Z: **EF2 · 115 mph · 1.47 mi · 450 yd**, 0 injuries, 0 fatalities (preliminary) |

The narration's EF2, 115 mph, 1.47 miles and 450 yards — unverified in phases 1–2 — are now matched to the survey on screen.
The survey also holds the other tornadoes the script mentions: Barnwell EF2 (115 mph, 18.04 mi), Kline EF1 (95 mph), Northern and
Western Allendale EF1s, Wagener EF1.

## New in phase 3
| Piece | Notes |
|---|---|
| `weather/news/dat.py` + `nws_dat` source | NWS Damage Assessment Toolkit (ArcGIS FeatureServer, layer 1 damage lines): one query per state envelope and UTC window; the service itself calls its data preliminary (official record: NCEI Storm Data), so every value is shown and reported as preliminary |
| `tornado_tracks` layer | every surveyed track that **begins inside** the story's states (the envelope also catches neighbours' tracks: Georgia's are left out), drawn as lines coloured by EF; the story's tornado labelled with the survey's own numbers; legend "EF… TORNADO TRACK · SURVEYED · PRELIMINARY"; each label in the numbers report |
| Surveyed track spec | on the beat that describes the tornado's path, preferring a camera already close in (Newberry: b7 "Its maximum reported width… surveyed path"), focused on the event's moment; shown again at b20 and b33 |
| Other surveyed tornadoes spec | on a beat that names other surveyed tornadoes (labels those by the survey's names) |
| SPC reports step aside | when surveyed tracks are shown, the preliminary reports are not added (the report says why); with no survey they remain the evidence (tests cover both) |
| `explainer` layer + `explainer.mjs` | fixed NWS definitions, words only: TORNADO WATCH "conditions are favorable…" / TORNADO WARNING "sighted or indicated by weather radar…"; added where a beat compares a watch and a warning (b30) |
| Archive coverage check | SPC file of the convective day, IEM warnings within an hour, DAT track within 20 minutes — one report line and one evidence fact each |
| Radar loop fitted to the warning (phase 1 follow-up) | kept: 5:55–6:25 AM EDT, the warning on screen 2.5 s |

## Your feedback on the 9-minute video: too little movement
The map stood still for long stretches (pakMap's own warnings: up to 53 s between 299 s and 352 s): the script's beats say "hold"
and Weather turns pakMap's drift off. Fixed for every Weather video, not this one:
* `weather/motion.py` (applied in `weather.generate.plan_layers`, after Teamplate's cutaways): every map stretch with no camera move
  longer than 6 s gets a slow push in, the next one easing back by the same amount (zoom bounded, the centre never moves, never inside
  footage dissolves). On the tornado video: 29 moves added; the longest still map stretch went from 53 s to 5.1 s.
* The engine shows a graphic again where the narration returns to it (`repeat_after_s`): the Newberry surveyed track comes back at
  b20 (touchdown, lifting time and surveyed track) and b33 (the recap), not only at b7.
* A map beat of 12 s or more with no graphic gets the county or city it names labelled (b3, b9, b24).
* The surveyed track is placed on a beat whose camera is already close in on the touchdown (b7), not the state-wide b2 where a
  1.5-mile track is a speck; the story's track is drawn and labelled first.

## Tests
`test_weather_intel.py` 55 (9 new: the motion pass leaves no map still > 6 s with the zoom bounded; the render plan moves; a small track prefers the close-up beat; survey track placed on the path beat with focus and label; other named tornadoes and reports
stepping aside; survey numbers verify the narration and are preliminary; archive coverage; 6 SC tracks drawn, Georgia's left out,
legend; the explainer). Phase-1 report tests now run with "no survey yet", so the fallback to SPC reports stays covered.
`weather-engine/test/explainer.test.mjs` 3. New fixtures: DAT tracks (SC envelope, Oct 10–12), IEM warnings for the coverage check.

## Not done in phase 3
* Warning and report timelines (a dated line of warnings / touchdowns).
* Counters of surveyed tornadoes (only added when the narration states a count; this script states none).
* DAT damage points and EF swaths (layers 0 and 2) are not drawn; the track lines carry the rating.
* SPC outlook was not added for this story because the narration never discusses it (the spec exists and is tested from phase 1).
