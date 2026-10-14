# Weather Intelligence — where we are and the remaining phases (written 2026-10-14)

Use this file to pick the work up on another machine. The master brief is the "MASTER IMPLEMENTATION PROMPT — Weather Intelligence
Autonomous Data & Graphics Engine" (phase-gated; ask before every commit; never modify PakMap; never invent data).

## 1. State right now

| Phase | Status | Commit |
|---|---|---|
| Gate 0 audit + Phase 1 (engine foundation) | done | `81acb3b` |
| Phase 2 (hurricanes, validated on Ian 2022) | done | `e25d6a4` |
| Phase 3 (severe weather / tornado) | built and tested; **final full-suite run and SC-only re-render not finished** | uncommitted until approved |
| Phase 4 (flood / post-event, Harvey 2017) | not started (most graphics already exist from earlier Weather work) | — |
| Phase 5 (forecast, heat, winter, extra graphics) | not started | — |
| Phase 6 (full verification + final report) | not started | — |

Phase 3 files (uncommitted at the time of writing): `weather/news/dat.py`, `weather/layers/survey.py`, `weather/layers/explainer.py`,
`weather/motion.py`, `weather-engine/lib/layers/explainer.mjs`, `weather-engine/test/explainer.test.mjs`, changes in
`weather/intel/{catalog,planner,engine,report,understand,sources}.py`, `weather/generate.py`, `test_weather_intel.py`,
`weather/testdata/intel/` (DAT + coverage fixtures), `docs/weather/intelligence_phase3.md`, `docs/weather/intelligence/*`.

Docs to read first: `docs/weather/intelligence_phase1.md`, `intelligence_phase2.md`, `intelligence_phase3.md`.

### How to run things
* Tests: `.venv310/bin/python scripts/run_tests_parallel.py` (Python 3.13 venv; `.venv` is 3.9 and fails ~170 modules).
  Weather only: `.venv310/bin/python -m unittest test_weather_intel` (offline, recorded official answers in `weather/testdata/intel`).
  Engines: `cd pakmap-engine && npm test` (133), `cd weather-engine && npm test` (62 with phase 3).
  Known flake: `test_flow_agent_connection` can fail in the parallel run and pass alone (not Weather).
* Engine on a project: `python -m weather auto --project DIR --voiceover F --words W [--dry-run] [--export-csv FILE]`
  → `DIR/intel/{auto_plan.json,evidence.json,report.md}` + `DIR/resolved.json`.
* Render: `PEXELS_API_KEY=… python -m weather render --project DIR --voiceover F --words W --out OUT.mp4` (~25 min for 9 min of narration).

### Test projects (NOT in git — they live on the first Mac)
* Real tornado project (your voiceover): `~/Downloads/VideoGenerator/Video_2026-10-13_003_token` — never modified; always work on a copy
  without `weather/weather_layers.csv` for Mode A.
* Ian / Harvey test projects were in the session scratchpad (`/private/tmp/...`) and will not survive. To rebuild: a project folder with
  `beats.csv` (Hybrid beat CSV), a voiceover and `words.json` (`python -c "import video_generator as vg; …transcribe_audio…"`).
  The offline tests do not need them.

## 2. Finish Phase 3 (first thing to do)
1. Run the full suite + both npm suites; fix anything red.
2. Re-run the engine and re-render the tornado copy: confirm the surveyed-track layers draw only the 6 tracks that start in SC
   (v5 still drew 3 Georgia + 2 North Carolina tracks from a snapshot saved before the filter; the build-time filter now fixes it).
3. Measure stillness again (frames compared twice a second; target: no still stretch over ~7 s) and inspect frames at the track
   beats (b7 ~83 s, b20 ~297 s, b22 ~315 s, b33 ~494 s), the radar (~260 s) and the explainer (~444 s).
4. Ask for approval → commit Phase 3.

## 3. Phase 4 — floods and post-event (validate Hurricane Harvey 2017)
Already working (phase 1 dry runs on Harvey with no CSV matched the hand-made plan): rain map (MRMS) on the narrated dates, gauge
totals (6 stations), Houston record (16.07 in vs 10.34 in 1989), Buffalo Bayou 08074000 + San Jacinto 08072050 crests found by name,
before/after (Aug 22 / Aug 31), event timeline, best track.
To build:
1. **Flood progression map**: the MRMS daily grids already fetched, shown day by day (a timed raster sequence like the radar loop),
   with the day label; spec placed where the narration walks through the days.
2. **Flash-flood warnings** for flood stories (`warnings_archive` #FF/FA with the event window; counter only when a count is said).
3. **City comparison bars** (observed totals vs each other — exists as `rain_total` bars) and, where a forecast is available
   in the archive, observed-vs-forecast (WPC QPF archive — verify the endpoint before relying on it).
4. **River crest timeline** marks from several gauges (event_timeline already reads USGS crests).
5. Validate on Harvey: Mode A (no CSV) and Mode B (the hand-made sidecar must be preserved); render; inspect frames; motion check.
6. Docs `intelligence_phase4.md`, tests, ask before commit.

## 4. Phase 5 — forecast, heat, winter, extra graphics
1. **Forecast stories** (current): connect the engine to the existing forecast automation (`weather/automation/`) — the engine must
   only fill gaps there (forecast strip, now card, temp trend, wind, active alerts); needs the NWS contact.
2. **Heat**: record highs (exists), temperature anomaly vs normals (ACIS normals — verify), heat index (NWS forecast grids — verify).
3. **Winter**: snow/ice totals (ACIS `snow` element; extend `rain_total` or a sibling), winter warnings (add WS/BZ/IS/WW to the IEM
   warning type list after checking IEM's phenomena codes), wind chill.
4. **Atmospheric context** only where a reliable archive exists (WPC surface analysis / fronts — verify first; skip if not).
5. Items left from phases 2–3: advisory timeline / several cones over time; GOES 10-min loops for current storms; warning + report
   timeline; counter of surveyed tornadoes when a count is said; DAT damage points / EF swaths (optional).
6. App: a report panel in the Weather card, an overrides editor (event, exclude, accept), a recording-date field; click through the
   live GUI once (Check plan → Generate on a no-CSV project).

## 5. Phase 6 — full verification
1. Full suite, `test_weather_isolation.py`, PakMap fidelity, upstream drift (`test_weather_upstream.py`), packaging
   (`weather/packaging.py` + a scratch PyInstaller build), both npm suites.
2. Render each acceptance event (tornado Oct 11 2026, Ian 2022, Harvey 2017; a forecast day) in Mode A and Mode B; inspect frames;
   stillness check; numbers report vs narration (claims section).
3. Final evidence-based report: what the engine found, what it could not, sources and coverage, with frame sheets.

## 6. Rules that still apply
* Ask before every commit and push. Weather must not change PakMap / Hybrid / StarMap files (isolation test guards it).
* Never invent data; a number the sources do not show is reported "not verified", never "wrong".
* User files (`beats.csv`, `weather_layers.csv`, `plan.csv`, `intel/overrides.json`) are read only; conflicts are reported.
* Your feedback: the screen must not stand still on one scene for long — check stillness on every render.
