Resume the Weather style work in /Users/muhammadnabil/Downloads/video_generator-main. Be economical with credits: no subagents, run each check once.

## Rules (from the user, must keep)
- Weather must NOT affect any existing style. Never edit pakmap/, pakmap-engine/, hybrid/, starmap*/, map-engine/, map_scene/, providers/, flow-engine/ or anything in test_fixtures/weather_protected.json.
- app.py, VideoGenerator.spec: additive changes only (already done in phase 1). Weather is off by default (Settings > General).
- No git commits or pushes (ask first). No Meteocons/Census downloads. No OS schedule installed. Python = .venv310/bin/python (3.13).
- Read docs/weather/integration_contract.md for the architecture (layer registry, engine plugins, rasters, ownership).

## Where we are (2026-10-13)
- Phase 1A + 1B DONE and tested: Forecast format with full-screen footage, Weather card in app, Settings, packaging. 3565 tests were green.
- Phase 5 partly done: count-up temps, wind_flow, chip collision, own-clip library (weather/footage_library.py).
- Phases 2, 3, 4 were built by parallel agents that were STOPPED before finishing (nothing integrated yet):
  - Phase 2 automation: weather/automation/ (11 files), weather/layers/trend.py, weather-engine/lib/layers/temp_trend.mjs, tests test_weather_auto_*.py. Report written: docs/weather/agent_phase2.md (read its "requests for the integrator").
  - Phase 3 News: weather/news/ (12 files), weather/layers/{radar,storms,severe,counters}.py, engine layers storm_*.mjs, counter.mjs, radar_legend.mjs, tests test_weather_news_*.py. NO report yet (docs/weather/agent_phase3.md missing).
  - Phase 4 Post-Event: weather/post/ (10 files), weather/layers/{totals,rivers,rainmap,beforeafter,timeline}.py, engine layers post_*.mjs. NO report and possibly no tests yet (test_weather_post_*.py).

## Next steps, in order
1. Run: `.venv310/bin/python -m unittest test_weather_*.py` and `cd weather-engine && node --test test/*.test.mjs`. Fix failures in phase 3/4 files (they are unfinished).
2. Read docs/weather/agent_phase2.md integrator requests; quickly skim weather/news/__init__.py and weather/post/__init__.py for their entry points.
3. Integrate (Weather-owned files only): format choice (Forecast / News / Post-Event) in weather/app_section.py; per-format prompts in weather/prompts/; any sidecar/resolve/events/footage.py changes the agents need; "Prepare today's forecast" button + schedule toggle (install only on user click).
4. Gates: full suite `.venv310/bin/python -m unittest discover -p 'test_*.py'`, test_weather_isolation.py, pakmap/starmap/weather engine tests, `node weather-engine/tools/check_upstream.mjs`.
5. Render one short test video per format (News: Hurricane Ian 2022; Post-Event: Harvey 2017) via `python -m weather render`, check a few frames, show the user.
6. Write a short final report docs/weather/final_report.md and update memory file project_weather_style.md.
