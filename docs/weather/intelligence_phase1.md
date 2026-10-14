# Weather Intelligence — Gate 0 audit and Phase 1 report (2026-10-14)

Status: implemented and tested, **not committed** (waiting for approval).

## Gate 0 — audit

Baseline: commit `cfd72c8` (master), full suite **3820 tests OK** (`.venv310`, `scripts/run_tests_parallel.py`, 293 s). Backup of
`weather/`, `weather-engine/`, `app.py`, `VideoGenerator.spec`, the Weather tests and `test_fixtures/` taken in the session
scratchpad before any change.

What already existed and was reused unchanged:

| Piece | Where | Used for |
|---|---|---|
| Layer registry (radar, warnings_archive, storm_reports, counter, spc_outlook, wpc_ero, storm_cone/track, satellite_loop, rain_map, rain_total, record, river_crest, before_after, event_timeline, headline, place_label …) | `weather/layers/` | every graphic the engine proposes renders through one of these types — no new renderer |
| Source clients (NHC GIS + HURDAT2, IEM radar + warnings, SPC, WPC, MRMS, RCC-ACIS, USGS + NWPS, GIBS, NWS API) | `weather/news`, `weather/post`, `weather/resolve.py` | data acquisition |
| Snapshot (`resolved.json`) + numbers report | `weather/resolve.py`, `weather/events.py` | the render reads only the snapshot |
| Hybrid beat plan, transcript matcher, autofix, timing | `hybrid/`, `weather/autofix.py`, `weather/timing.py` | beats and narration alignment |
| HTTP cache with retries | `weather/layers/__init__.py`, `weather/cache.py` | every request |

What was missing: every data graphic had to be written as a row of `weather_layers.csv`. The only automatic step
(`weather/autodata.py`) wrote a fixed bundle (radar + warnings + reports + counter) into the user's own CSV, keyed on the first
full date in the script — and for a morning tornado it used the wrong SPC day (a 6:05 AM EDT tornado is in the previous
convective day's file; the Oct 11, 2026 file has no SC reports at all).

## Phase 1 — what was built (`weather/intel/`, new)

```
script + voiceover + beats (optional) + weather_layers.csv (optional) + intel/overrides.json (optional)
  → understand.py   category, storm names, dates in words or digits, relative days, clock times, places, claims, topics per beat
  → context.py      event resolved from official indexes: NHC storm list → storm id; HURDAT2 → landfalls/peak; the moment;
                    SPC convective day; map focus (county centroid / city / landfall)
  → planner.py      graphic opportunities (catalog.py) scored against each beat's words, placed under the limits
  → engine.py       data fetched per graphic (one failure never stops the rest), verified, evidence-driven refinement,
                    narration numbers checked against the numbers the graphics will show
  → intel/auto_plan.json, intel/evidence.json, intel/report.md, resolved.json
  → weather.generate.plan_layers merges the user's rows and the engine's (user ids win), then the existing render
```

* **Modes.** A: no `weather_layers.csv` (even no `beats.csv`: `beats.py` makes map beats from the narration). B: the user's rows
  are kept as written; only gaps are filled. C: `intel/overrides.json` (`event` {category, storm, day, moment, year, states,
  focus, recorded_at}, `exclude`, `only`, `place`, `gauges`, `accept`).
* **User files are never written.** Conflicts (another storm id, the wrong SPC day, a `latest` product in a past-event story,
  a window far from the event) are reported with a proposal; applied in memory only when `accept` lists them.
* **Idempotent.** Stable ids (`auto_*`), the engine's own file is replaced on each run; an id the user's file already uses
  gets `_engine`.
* **Placement limits.** Map beats only (never full-screen footage); per beat at most 1 loop, 1 counter, 3 data graphics (the
  user's included); a graphic needs its beat's words to discuss it (`min_score`, `must` topics); graphics spread by a crowding
  penalty; each is anchored on the first words of the sentence that triggered it.
* **Evidence model.** Facts carry kind (identity / best_track / forecast / warning / preliminary_report / observed / estimate /
  official_record / derived), quality, timeframe, issue/valid times, source and record, caveats and derivation method; every
  request is logged as ok / unavailable / temporary / malformed / skipped / ambiguous.
* **Identity rules.** A shared name is never guessed (Harvey without a year → ambiguous, listing AL091993 … AL092017); the year
  said, then the dates said, then the recording's season decide. A storm named once in a tornado story is context, not the
  subject (Isaias → AL092026, no storm graphics; the report notes that NHC lists it as TS while the script says hurricane).
* **Dry run** (`--dry-run`): everything resolved and reported, nothing written.
* **App.** The Weather card's Check plan and Generate run the engine first (`app_section.run_intelligence`); a plan with no
  weather rows now loads (the old rows are moved to `weather_layers.previous.csv`, never deleted); `weather.json`
  `"intelligence": false` restores the old behaviour. CLI: `python -m weather auto --project DIR [--voiceover F] [--words W]
  [--dry-run] [--no-fetch] [--export-csv FILE]`.
* Small additive change to existing Weather layers: `storm_reports` and the SPC `counter` accept `extra.states` (unchanged
  without it).

## Acceptance tests (real projects, real data)

| Project | Mode | Result |
|---|---|---|
| Newberry County tornado, Oct 11 2026 — the user's real voiceover (546 s), copy with `weather_layers.csv` removed | A | Event tornado, 2026-10-11, moment 10:05Z from "6:05 a.m. EDT", **SPC convective day 2026-10-10**, SC. Added: headline, radar + archived **Tornado Warning CAE #16 issued 10:05Z** (beat b18, where the narration describes the warning), 9 preliminary SC tornado reports (b22), county labels (Newberry b1, Fairfield b5, Allendale b21). Rendered twice (1920×1080, 546 s). v1's loop (04–09 EDT, moment ±2 h) showed the 6-minute warning for 1.0 s and mostly empty radar after the storm left; v2 fits the loop to the warning the evidence returned (09:55–10:25Z): the polygon is on screen 2.5 s and the storm stays in view. Frames: `docs/weather/intelligence/`. |
| same, with the user's own `weather_layers.csv` | B | All 9 user rows kept (4 headlines, 4 labels, satellite). Added radar/warnings/reports. Flagged `sat1` (`gibs:geocolor@latest` in an Oct 11 story) with the proposal `gibs:geocolor@2026-10-11T10:00Z` — not applied. |
| Hurricane Ian 2022 — test project, sidecar removed | A | AL092022 by the year said; strongest FL landfall 19:05Z (HURDAT2); advisory **024** found by searching the archive for "eleven o'clock" Wednesday = 15Z (the same one chosen by hand earlier); radar 14–22Z from the narrated times; **5** extreme wind warnings counted (the narration says five); WPC ERO; daily satellite loop; best track. |
| Ian with its hand-made sidecar | B | 6 user graphics kept; only a headline added. |
| Hurricane Harvey 2017 post-event — sidecar removed | A | AL092017; MRMS rain map Aug 25–Sep 1 (the dates the beat says); gauges BPT/HOU/IAH/GLS/SGR/CXO; Houston record (16.07 in vs 10.34 in, 1989); Buffalo Bayou 08074000 and San Jacinto 08072050 found by name in the USGS site list; before/after Aug 22 / Aug 31; timeline. 11 of 12 narrated numbers match numbers the graphics show. |
| Harvey with its hand-made sidecar | B | 7 user graphics kept (river crests matched by gauge id); headline and best track added. |

Reports of the three no-sidecar runs: `docs/weather/intelligence/{tornado,ian,harvey}_report.md`.

## Tests

`test_weather_intel.py`, 40 tests, offline (official answers recorded 2026-10-14 in `weather/testdata/intel/`, see its
README): spoken numbers and dates, story-year vs record-year, weekdays, relative days with and without a recording date,
weekday/date mismatch, organisation names that contain a state, county lookup, shared storm names, current-season storms,
invests, convective day, bounded advisory search, gauge choice, Mode A end to end, files untouched, evidence categories,
repeat runs, render payload, per-beat limits, footage beats, dry run, missing archive (404), network failure (temporary,
"Degraded"), malformed answers, missing storm list, overrides (exclude, event), Mode B preserve / conflicts / accept,
no beat plan at all, the app card's entry points, narration numbers vs shown numbers, fitted radar loop and its fallback.

Full suite after the change: **3860 tests OK** (3820 baseline + 40 new). Weather modules: 311 → 351 OK; pakmap-engine 133/133 and
weather-engine 57/57 (node); no PakMap / Hybrid / StarMap file changed;
`test_weather_isolation.py` (protected files, no Weather imports in other styles) passes; `weather/packaging.py` ships
`weather.intel.*` automatically.

## Not done / limits (honest list)

* Tornado survey facts (EF2, 115 mph, 1.47 mi, 450 yd) are **not verified**: the NWS Damage Assessment Toolkit is not a source
  yet (phase 3). The report lists them as unverified, never as wrong.
* The recording date falls back to the voiceover file's date, flagged as an assumption; set `recorded_at` in weather.json or the
  overrides for relative days.
* Winter graphics are not built (reported as skipped); heat is records only; current forecasts need the NWS contact.
* Beats made from the narration (no beats.csv) are all map beats, without footage.
* The report shows in the log and the Check plan box; there is no dedicated panel or overrides editor in the app yet. The
  live GUI was not clicked through in this session (entry points are tested with stubs).
* Pakmap renderer warnings "nothing changes between …" on long map holds are pre-existing Teamplate/Hybrid behaviour, not
  caused by the engine.
