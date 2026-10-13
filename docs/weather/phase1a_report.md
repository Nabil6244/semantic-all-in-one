# Weather — Phase 1A report (new folders only)

Date: 2026-10-13 (work done 2026-10-12 UTC). Base commit `84700a7`. **Nothing committed.** No existing file changed; `git status` shows only new, untracked paths:
- `weather/`, `weather-engine/`;
- `test_weather_*.py` (5 files), `test_fixtures/weather_protected.json`;
- `docs/weather/`.

## What was built
| Part | Files | What it does |
|---|---|---|
| Data | `weather/nws.py`, `cache.py`, `resolve.py`, `alerts.py`, `cities.py`, `tz.py`, `provenance.py` | NWS forecasts, observations and alerts; GOES-East GeoColor time from GIBS; own per-user cache; provenance on every value; 6 h freshness rule at prep and at render; US time zones without tzdata |
| Plan | `weather/sidecar.py`, `timing.py`, `events.py` | `weather_layers.csv` (the Hybrid beat CSV is untouched), layer timing on the narration with pakMap's matcher, events plus the numbers report |
| Render | `weather/render.py`, `generate.py`, `cli.py` | Hybrid's generator called unchanged, with Weather's renderer passed through its existing `render=` option; `python -m weather fetch / check / render / prompt` |
| Engine | `weather-engine/render.mjs`, `page.js`, `page.html` (copies), `lib/wx_draw.mjs`, `wx_icons.mjs`, `wx_layout.mjs` | timed satellite layer; temperature markers, 5-day strip, now card, alert legend, source line; icons drawn in code; hidden under footage; chips avoid each other; off-screen markers reported |
| Drift | `weather-engine/UPSTREAM.json`, `tools/check_upstream.mjs`, `test_weather_upstream.py` | read-only report on the copied files, the pakMap modules, and every JS and Python name Weather imports |
| Isolation | `test_weather_isolation.py`, `test_fixtures/weather_protected.json` | 397 protected files hashed at `84700a7` |
| Prompt, packaging | `weather/prompts/forecast_csv_prompt.txt`, `weather/packaging.py` | manual CSV prompt; list of shipped files for 1B |

No new dependencies: the Python side uses only the standard library, and the engine has no npm dependencies of its own. Nothing was downloaded: icons are drawn in code, and the county shapes are the ones already bundled.

## Tests
| Suite | Baseline `84700a7` | After 1A |
|---|---|---|
| Python, `.venv310` (3.13) `scripts/run_tests_parallel.py` | 3509 tests / 198 modules OK | **3557 / 203 OK** (+48 Weather tests in 5 modules) |
| `pakmap-engine` `node --test` | 133 / 133 | **133 / 133** |
| `starmap-engine` `npm test` | 54 / 54 | **54 / 54** |
| `weather-engine` `node --test` (new) | — | **17 / 17** |

What the Weather tests cover:
- **Data**, from recorded NWS and GIBS responses with no network:
  - US daylight-saving switch times;
  - °C→°F rounding and icon wording;
  - contact required, retries, the 4xx fail-fast, and the cache window;
  - forecast day/night pairing and provenance;
  - station fallback, including a 404 station;
  - polygon versus county alerts, with marine alerts reported;
  - the satellite "latest" time and a gap in its listing;
  - the snapshot round trip;
  - the 6 h forecast rule at prep and at render;
  - ended alerts refused.
- **Sidecar:** every error names its row; the data-source grammar; unknown columns.
- **Timing:** a layer placed on its beat's words (not on the same words spoken in another beat); hold, until end, and a missing anchor.
- **Events:** every on-screen number appears in the numbers report with its URL and issue time; small chances of rain are hidden; alert areas become pakMap `fill` events; one satellite provider per picture time; source-line wording.
- **Generator:** the weather layers reach the renderer next to Hybrid's own options. The merged spec passes **pakMap's own rule check** and Weather's. Stale data, sidecar errors, or no fetch yet stop the run before anything renders.
- **Engine:**
  - **fidelity**: a spec without weather renders frame-for-frame the same through weather-engine as through pakmap-engine;
  - golden pixels for the strip, now card and source line;
  - graphics hidden under full-screen footage;
  - off-screen marker warning;
  - chip collision avoidance;
  - layout inside the frame;
  - event checks;
  - the drift check reports, flags a missing export as broken, and changes no file.
- **Isolation:** protected hashes unchanged; no new file in a protected folder; no line removed from `app.py` or `VideoGenerator.spec`; no existing module imports Weather. Enoch Template's guard still passes.

## Isolation proof (§10 of the proposal)
- **Sample compiles, baseline versus working tree, byte for byte:** the baseline tree was exported with `git archive 84700a7`, with no change to git state. **All 12 identical:**
  - pakMap Kenya;
  - StarMap Apollo 8, 11 and 13, Artemis 1, Chandrayaan-3, Chang'e 4 and Voyager 1;
  - the Hybrid test plan;
  - Overscaled, Exp Solar and the local planner samples.
  
  Enoch Template has no compile step of its own; it is covered by its own phase-0 guard and suite, both green, and no Enoch file was touched.
- **Render, baseline versus working tree:** pakMap's Kenya sample (10 s, 300 frames, real imagery) gave **identical `framemd5` for every frame**. A Hybrid render was not repeated separately: it needs stock clips. Hybrid's code is byte-identical (hash check), its plan compiles identically, and the fidelity test shows weather-engine itself draws pakMap's layers frame-for-frame.
- **Upstream drift:** `node weather-engine/tools/check_upstream.mjs` → "No drift".

## End-to-end video (6 cities)
`python -m weather fetch` then `render` on a scratch project:
- **Inputs:** 8 beats; 23 weather layers; Dallas, Houston, Chicago, New York, Los Angeles and Miami; live NWS data and GOES-East GeoColor.
- **Voiceover:** a **test voice made with macOS `say`**, used only for this test (2 min 19 s; the target was about 3 min). Your own recording is the real acceptance step.
- **Output:** 1920×1080 H.264 + AAC, with sound design. Render took about 5.7 min on this Mac. The numbers report lists 37 on-screen numbers, each with its NWS URL and issue time.
- **Frame review:** fixed during review —
  - satellite tiles outside the GOES picture logged 404s; now answered quietly with 204;
  - two chips overlapped in the national shot; chips now avoid each other.
  
  **Authoring lessons, not code bugs:**
  - `type=hold` on a beat keeps the camera where it is, so a wrap-up beat must leave `type` empty to fly to its place. The new off-screen warning catches this.
  - My test script said "cooler air in Chicago" on an 84°F day. In phase 2 the script is written from the data, so this cannot happen.
- **Known limits:**
  - the "United States" place frames Alaska too, so the national shot uses `38.5,-97.5` with frame `continental`;
  - "New York" means the state, so the city is `city:New York`.
  
  Both are now written into the CSV prompt, with when to use `type=hold`.

## Notes for you
- **NWS contact:** development fetches used the placeholder contact `https://example.invalid`, never your email. Real use needs your own contact (an email or a website), entered in Weather settings in 1B, or passed with `--contact` on the command line now.
- **Satellite history:** GIBS keeps GOES-East GeoColor for about two months, so past events (phases 3–4) will use the daily VIIRS/MODIS layers.
- **Rollback for 1A:** delete `weather/`, `weather-engine/`, `test_weather_*.py`, `test_fixtures/weather_protected.json`, and optionally `docs/weather/`. No existing file needs restoring.
