# Weather Style — Phase 1 proposal (Forecast MVP)

Status: **proposal, awaiting approval. Nothing here is implemented.** Nothing is committed.
Baseline: commit `84700a7` (master), clean working tree for every path below (`git status` shows only untracked `docs/weather/`, `graphics_overlays/`, `smart_text_overlays/`).
Related: [plan](weather_style_plan.md), [phase 0 report](phase0_report.md), [radar terms](radar_source_terms.md).

## 0. Approvals this proposal asks for
1. Phase **1A** — new folders only (`weather/`, `weather-engine/`, new tests, new fixtures, docs). **No existing file changes.**
2. Phase **1B** — the additive integration edits in `app.py` and `VideoGenerator.spec` listed in §6. Approved and done separately, only after 1A passes its acceptance tests.
3. No downloads. Meteocons and Census boundaries are **not needed** for phase 1 (see §8).

## 1. Scope
**In:**
- **Data:** NWS point forecasts (7-day), latest observations, and active alerts for land areas (polygon or county); cache; provenance; freshness rule (forecast older than 6 h refused).
- **Coverage for the acceptance video:** 6 cities — Dallas, Houston, Chicago, New York, Los Angeles, Miami. The city list is a data file.
- **Weather layers:**
  - `temp_marker` — a city temperature with a drawn icon;
  - `forecast_strip` — 5 days;
  - `now_card` — current observation;
  - `alert_area` — drawn with the engine's existing `fill` event;
  - `satellite` — a NASA GIBS daily true-colour layer for the date of the forecast;
  - `source_line` — "Data: National Weather Service · Issued 5:12 AM CT".
- **Rendering:** a separate `weather-engine/` (option A) that reuses `pakmap-engine/lib/*.mjs` and its MapLibre by import.
- **Pipeline:** a Hybrid beat CSV (unchanged contract) plus a Weather sidecar (§4). Your voiceover, aligned as in Hybrid. Hybrid's existing generator is called, with Weather's renderer passed in through its existing `render=` option.
- **Command line:** `python -m weather fetch …` / `python -m weather render …`, so 1A can be tested end to end without touching the app.
- **Prompt:** a manual Weather CSV prompt text, used through the command line in 1A and from the Weather card in 1B.
- **Checks:** the upstream-drift check (§9) and the isolation guard (§10).
- **App (1B only):** the Weather card, the on/off switch, and installer bundling.

**Out (later phases):** radar; NHC, SPC, WPC, ACIS, USGS and CPC; daily automation and scheduling; story picker; footage pool; YouTube by video ID; marine alerts; Alaska and Hawaii insets; Meteocons icons; clip approval.

## 2. How a phase-1 video is made
```text
weather_layers.csv (sidecar) ──┐
beats.csv (Hybrid beat CSV) ───┤
voiceover (yours) ─► words ────┤
                               ▼
weather.generate.generate_forecast_video()
   1. weather.resolve: each data_source ─► values with provenance (NWS, cached)  ─► freshness check (refuse > 6 h)
   2. hybrid.beat_csv / hybrid.generate.generate_hybrid_video(..., render=weather.render.render_spec)   [imported, unchanged]
        └─ pakmap.app_integration.generate_pakmap_video  [unchanged; already accepts render=]
             └─ weather.render.render_spec(spec, out, …)
                  adds the weather events (sidecar rows resolved to times by the same word matcher) to the spec,
                  then runs node weather-engine/render.mjs
   3. numbers report: every number on screen ─► source, station/grid, issue time   (weather_numbers.txt next to the video)
```
**Why this needs no edits to Hybrid or pakMap:**
- `generate_pakmap_video` already takes `render: Optional[Callable]` and calls it as `render(spec, silent, progress=…, cancel_check=…, log=…)`;
- `generate_hybrid_video` passes `**kw` through to it.

`spec_extra` can't be used, because Hybrid already sets it. So the weather events travel inside Weather's `render` callable instead.

## 3. Data and network
- **Endpoints:** `api.weather.gov` (points, gridpoint forecast, station observations, alerts) and `gibs.earthdata.nasa.gov` (one daily true-colour layer). Nothing else.
- **NWS contact:** the NWS asks callers to send contact details with each request. These come from a setting, `weather_nws_contact`, that you fill in. **Weather refuses to fetch while it is empty.** Your account email is never filled in automatically.
- **Cache:** per-user `…/SemanticYTStudio/weather/` (same pattern as pakMap's tile cache, own folder), with entries keyed by URL. Each NWS product's `Expires` header (or 1 h when absent) decides when it's fetched again. Each project's resolved values are written to `<project>/weather/resolved.json` (the snapshot the video is built from).
- **Provenance per value:** value, unit, source product URL, grid point or station, `updateTime`/`generatedAt`, fetched-at.
- **Units:** observations come in °C and are converted to °F, rounded half-up. Forecast values are used as given (already °F).
- **Freshness:** the forecast's `updateTime` must be within 6 h at prep and again right before render. Otherwise the render stops with a message naming the product and its age. There's no silent override.

## 4. CSV contract — sidecar, not a schema change
Inspection result:
- `hybrid/beat_csv.py` rejects unknown columns (`unknown column …`) and validates layer types;
- `pakmap/schema.py` rejects unknown `layer_type`s.

Adding weather types or columns to either would change how existing CSVs are checked. So:
- **`beats.csv`** — an ordinary Hybrid beat CSV: beats, camera, standard layers, clips. It loads in the Hybrid card unchanged, showing the map without the weather layers.
- **`weather_layers.csv`** — Weather's own sidecar, validated only by `weather/sidecar.py`:

| column | meaning |
|---|---|
| `beat` | beat id in `beats.csv` it belongs to |
| `vo_anchor` / `t` | the narrator's words it appears on, or seconds — same matcher as Hybrid (imported) |
| `id` | layer id (unique) |
| `type` | `temp_marker`, `forecast_strip`, `now_card`, `alert_area`, `satellite`, `source_line` |
| `place` | city (`Dallas, TX`) or state (`TX`) |
| `data_source` | what data, never the number: `nws:forecast@Dallas,TX#day1-5`, `nws:obs@KDFW`, `nws:alerts@TX`, `gibs:truecolor@2026-10-13` |
| `hold` / `until` | how long it stays (same meaning as Hybrid) |
| `extra` | JSON for rarely used options |

Errors name the sidecar row (spreadsheet numbering), as Hybrid's do. Inspection did **not** show that a schema change is necessary.

## 5. Files to create (phase 1A)
| Path | Purpose |
|---|---|
| `weather/__init__.py` | package doc; nothing imported at app start |
| `weather/__main__.py`, `weather/cli.py` | `fetch`, `check` (sidecar + freshness), `render` |
| `weather/nws.py` | NWS client: User-Agent, retries with backoff, `Expires`-aware |
| `weather/cache.py` | per-user file cache (own folder) |
| `weather/provenance.py` | `Sourced` value type; numbers report |
| `weather/cities.py`, `weather/data/cities.json` | city → lat/lon/station/time zone (6 for phase 1; NWS `points` fills grid and station) |
| `weather/alerts.py` | alert → MultiPolygon: own polygon, else county shapes by SAME/FIPS from the **already bundled** `map_scene/data/us_counties.json.gz`; marine alerts skipped and reported |
| `weather/sidecar.py` | read/validate `weather_layers.csv` |
| `weather/resolve.py` | `data_source` → `Sourced` values |
| `weather/events.py` | resolved rows → engine events (`fill` for alert areas; weather types for the rest) |
| `weather/render.py` | `render_spec(...)` compatible with `generate_pakmap_video(render=)`; runs `weather-engine` using `map_scene.render` helpers (imported) |
| `weather/generate.py` | `generate_forecast_video(...)` (§2) |
| `weather/prompts/forecast_csv_prompt.txt` | manual Weather CSV prompt (beats + sidecar, numbers never in the text) |
| `weather/packaging.py` | which Weather files ship (used by the spec in 1B; unit-tested) |
| `weather/testdata/*.json` | trimmed recorded NWS/GIBS responses (public domain) |
| `weather-engine/render.mjs` | **copy** of `pakmap-engine/render.mjs` @`84700a7`, changed only to: serve `/lib/` from `../pakmap-engine/lib`, `/wlib/` from `weather-engine/lib`, MapLibre from `../pakmap-engine/node_modules`, fonts from `../pakmap-engine/assets` |
| `weather-engine/page.html`, `weather-engine/page.js` | **copy** of pakMap's page, plus the weather layers and the satellite raster source |
| `weather-engine/lib/wx_draw.mjs` | forecast strip, now card, temp markers, source line (2D canvas, 1920×1080 design scaled) |
| `weather-engine/lib/wx_icons.mjs` | weather icons drawn in code (sun, cloud, rain, storm, snow, fog, wind) — no downloaded set |
| `weather-engine/UPSTREAM.json` | fork record for the drift check (§9) |
| `weather-engine/tools/check_upstream.mjs` | drift report (read-only) |
| `weather-engine/test/*.test.mjs` | unit + golden-frame tests for the weather layers |
| `weather-engine/package.json` | `"type": "module"`, **no dependencies**; `node --test` script |
| `test_weather_data.py`, `test_weather_sidecar.py`, `test_weather_render.py`, `test_weather_generate.py` | Python tests (run by `scripts/run_tests_parallel.py`, which already discovers `test_*.py`) |
| `test_weather_isolation.py` + `test_fixtures/weather_protected.json` | isolation guard (§10), same pattern as Enoch Template's |
| `test_weather_upstream.py` | runs the drift check; reports only (§9) |

Phase 1B adds `weather/app_section.py` (the card UI and handlers, so `app.py` only delegates).

## 6. Existing files to edit (phase 1B only) — exact list
**Baseline (git blob at `84700a7`, sha256 of file):**
| File | git blob | sha256 |
|---|---|---|
| `app.py` | `1801edce8779` | `af3650cfead69bfb5b837627e6f204cb54259ef50afe1f36594954fa0280be6a` |
| `VideoGenerator.spec` | `12e491e2cd61` | `c68d39cad6027cecdb96f987a8a27b11b6d984d0d3520f7e02174a4222039a26` |

**`app.py`** (line numbers at baseline). Every Weather branch runs only when `generation_mode == "weather"`, which can only be set from the Weather card, and the card exists only when Weather is enabled:

| # | Where | Change | Kind |
|---|---|---|---|
| 1 | after line 1050 (`_build_starmap_section(...)`) | `if self._weather_on(): self._build_weather_section(..., row=5)` | added |
| 2 | `STYLE_BLURBS`, `STYLE_CARDS` (2892–2916) | one `"Weather"` entry each (dict entries; `STYLE_CHOICES` **unchanged**) | added |
| 3 | lines 2942 and 2986 (`for … in self.STYLE_CHOICES`) | `for … in self._style_choices()` (= `STYLE_CHOICES` + `("Weather",)` only when enabled) | **2 modified lines**, identical result when disabled |
| 4 | `_active_style` before line 3021 | `if mode == "weather": return "Weather"` | added |
| 5 | `_on_style_pick` after the running guard (3044–3048) | weather-running guard; `if choice != "Weather": self._weather_deactivate()`; `elif choice == "Weather": self._weather_activate()` | added |
| 6 | `_sync_style_picker` after line 3102 | show or hide `_weather_block` if it exists | added |
| 7 | `_set_scenes_empty_text` before line 3554 | Weather's empty message | added |
| 8 | primary-action dispatch near line 6348 | `weather_*` actions | added |
| 9 | `_sync_primary_cta` near line 7061 | `if self.generation_mode == "weather": self._sync_primary_cta_weather(); return` | added |
| 10 | project restore after line 7801 (`_restore_starmap(ws)`) | `self._restore_weather(ws)` | added |
| 11 | near line 9411 | Weather owns the table: `return` | added |
| 12 | near line 10718 | Weather's images folder (`<project>/weather/_work/media`) | added |
| 13 | generate dispatch near line 13475 | `self._run_weather_generation()` | added |
| 14 | `_on_fix_all_visual_issues` near line 14592 | same refusal message for Weather | added |
| 15 | new block after the StarMap block (~line 5282) | thin methods `_weather_on`, `_style_choices`, `_build_weather_section`, `_weather_activate`, `_weather_deactivate`, `_restore_weather`, `_sync_primary_cta_weather`, `_run_weather_generation` — each delegates to `weather.app_section` through a guarded import; **an import failure means Weather is off**, never an app crash | added |
| 16 | Settings → General tab, end of section (`_open_settings`, ~line 12360+) | "WEATHER (BETA)" heading, one switch (`weather_enabled`, default **off**), the NWS contact field, and the note "takes effect after restart" | added |

- **No new Settings tab:** `test_settings_tabs.py` pins exactly four tabs.
- **Per-project state** lives in `<project>/weather/` (`beats.csv`, `weather_layers.csv`, `weather.json`, `resolved.json`, `_work/`). **`project_workspace.py` is not edited.**

**`VideoGenerator.spec`** — one block after line 170 (StarMap's), mirroring it:
```python
# Weather: weather-engine/ (its own page + weather layers; imports pakmap-engine/lib and MapLibre, which ship above)
# and the weather package's data and prompts (see weather/packaging.py, which is unit-tested).
from weather.packaging import data_files as weather_data_files  # noqa: E402

datas += weather_data_files(ROOT)
```
- **`.github/workflows/build-desktop.yml`: no change.** `weather-engine` has no npm dependencies.
- **Not edited:** `project_workspace.py`, `app_csv_prompts.py`, `composition_styles/`, `pakmap/`, `pakmap-engine/`, `hybrid/`, `starmap/`, `starmap-engine/`, `map-engine/`, `map_scene/`, `providers/`, `flow-engine/`, search, mixer — nor any of the 228 files under Enoch Template's guard.

## 7. Dependencies
- **Python:** standard library only (`urllib`, `json`, `csv`, `gzip`, `zoneinfo`). No new pip packages.
- **Node:** none new. MapLibre comes from `pakmap-engine/node_modules` and Playwright from `flow-engine` (the same lookup pakMap uses). `geotiff` isn't used.
- **Imported, read-only:**
  - `hybrid.beat_csv`, `hybrid.generate`;
  - `pakmap.app_integration` (via Hybrid), `pakmap.engine_runner` (exception types only);
  - `map_scene.render` (`_find`, `_node`, `_ffmpeg`, `_ensure_browser`, `_browser_channel`);
  - `pakmap-engine/lib/*.mjs`.
  
  Private helpers are imported by name, so the drift check (§9) also confirms those names still exist.
- **Runtime network:** `api.weather.gov`, `gibs.earthdata.nasa.gov`, plus pakMap's existing GIBS base tiles.

## 8. Assets and packaging
- **Icons:** drawn in code (`wx_icons.mjs`). No download, no licence entry. Meteocons stays a later option, pending your approval.
- **Boundaries:** US states (Natural Earth admin1) and US counties (Census `cb_2023_us_county_5m`, with FIPS) are **already bundled** in `map_scene/data/` and shipped by the existing spec, so no Census download is needed. Phase 0 check: all 54 land alerts without their own polygon mapped fully to bundled counties; the 132 that didn't were marine (out of scope).
- **Fonts:** pakMap's bundled font, served by path.
- **Installer additions (1B):**
  - `weather-engine/{render.mjs,page.html,page.js,package.json,UPSTREAM.json}` and `weather-engine/lib/*.mjs`;
  - `weather/data/*.json`, `weather/prompts/*.txt`.

  Total under 300 KB. `weather/*.py` is bundled by PyInstaller's import analysis, but only once `app.py` imports it (1B). `weather/testdata/` doesn't ship.

## 9. Upstream-drift check (report only)
- **`weather-engine/UPSTREAM.json`** records:
  - the fork commit (`84700a7`);
  - the sha256 of each copied file (`render.mjs`, `page.js`, `page.html`);
  - for each imported `pakmap-engine/lib` module: its sha256 and the export names Weather uses;
  - the Python names imported from `map_scene.render`, `hybrid.*` and `pakmap.*`.
- **`node weather-engine/tools/check_upstream.mjs`** (and `test_weather_upstream.py`, which calls it):
  - compares current hashes against the record;
  - for each changed copied file, prints `git diff 84700a7 -- pakmap-engine/<file>` when git is available, otherwise names the file;
  - lists changed imported modules;
  - checks that every used export or name still exists.
- **It never writes any file**, and never touches `weather-engine/`. Porting a change is a separate, approved step that updates `UPSTREAM.json` deliberately.
- **Outcome:**
  - **content drift** → printed report; the test passes, with the report shown.
  - **missing export or name** (Weather would crash) → the test fails, naming the missing name. That's a correctness failure, not drift.

## 10. Isolation guard
- **`test_fixtures/weather_protected.json`** (same format as `enoch_template_protected.json`): the sha256 (line endings normalised) of every file under `pakmap/`, `pakmap-engine/` (except `node_modules`), `hybrid/`, `starmap/`, `starmap-engine/`, `map-engine/`, `map_scene/`, `composition_styles/`, `providers/`, `flow-engine/` (except `node_modules`), plus `project_workspace.py`, `app_csv_prompts.py`, `asset_manager.py` and `video_generator.py`. Base commit `84700a7`.
- **`test_weather_isolation.py`:**
  1. no protected file changed or disappeared;
  2. no new module inside a protected folder;
  3. `app.py` and `VideoGenerator.spec`: every line removed versus `84700a7` must be one of the approved modified lines in §6 (rows 3 and 15). Anything else fails, naming the line;
  4. with `weather_enabled` absent or false: `_style_choices() == STYLE_CHOICES` and no `_weather_block` is built.
- **Manual proof, run before each approval (results written to `docs/weather/phase1_isolation_report.md`):**
  - **compiles identically:** compile every committed sample at `84700a7` (exported with `git archive` into a temp folder) and on the working tree, then compare the JSON byte for byte:
    - pakMap `pakmap-engine/samples/kenya-story.csv`;
    - Hybrid (the beat CSVs in the Hybrid tests' fixtures);
    - StarMap `starmap/samples/*_beats.csv` (8);
    - Overscaled `overscaled_sample.csv`;
    - local planner `local_planner_sample.csv`;
    - Enoch Template (its own phase-0 test fixtures);
  - **renders identically:** the pakMap Kenya sample (10 s cut) and one Hybrid fixture, rendered on both trees and compared with `ffmpeg -f framemd5`;
  - **full Python suite and engine suites:** same results as baseline (§12).

## 11. Disabled by default
- **The switch:** `weather_enabled` is absent from `settings.json` until you switch it on, and absent means off. When off:
  - the picker shows the same 8 cards;
  - no Weather section is built;
  - `generation_mode` can never become `"weather"`;
  - no Weather code is imported (the guarded imports run only from Weather's own methods);
  - no network call is made.
- **Old projects** are unaffected: Weather only reads `<project>/weather/`.
- **A project saved with Weather active, opened while Weather is off,** opens as Normal video. Its Weather files stay on disk.

## 12. Acceptance tests
**1A (no app changes):**
1. **Data (recorded fixtures, no network):** parsing of points, forecast, observations and alerts; °C→°F; rounding; provenance fields; forecast older than 6 h refused at prep and at render; cache honours `Expires`; empty NWS contact refuses to fetch; retries with backoff (simulated 5xx); alert → county shapes, with marine alerts reported.
2. **Sidecar:** valid file; unknown type; bad `data_source` grammar; missing beat; duplicate id. Each error names the row.
3. **Engine (`node --test`):**
   - golden frames for strip, card, marker, source line and icons, at 1080p and 4K;
   - alert area drawn via `fill`;
   - satellite layer present and behind the overlays;
   - `check_upstream` runs.
4. **End to end (command line):**
   - a ~3-min forecast for the 6 cities from `beats.csv` + `weather_layers.csv` + a voiceover;
   - the numbers report lists every on-screen number, and each is checked against `resolved.json` (automated);
   - a frame strip for your review (never claimed as passed from unit tests alone).
   
   Your own recording is used for the final check. Automated runs use a short test voiceover with known words (as the Hybrid tests do).
5. **Freshness:** a fixture whose forecast is 7 h old blocks the render with a clear message.
6. **Isolation:** §10 guard green; protected-hash check green; Enoch's guard still green.
7. **Suites:** full Python suite (`.venv310`, Python 3.13 — the 3.9 `.venv` can't run this codebase) and the `pakmap-engine` and `starmap-engine` tests give **the same results as the baseline below**.

**1B (after app edits):**
1. `test_style_picker.py` and `test_settings_tabs.py` unchanged and green.
2. New `test_weather_app.py`, with Weather disabled (default) and enabled:
   - card present only when enabled;
   - picking Weather steps every other style aside, and picking any other style steps Weather aside;
   - project restore;
   - Generate routes to Weather;
   - a running render keeps its style.
3. §10 manual proof repeated: compile and render identity, full suites.
4. **Installer check:** a local PyInstaller build with `.venv-build`. The app starts with Weather off (identical picker), and with Weather on renders the 6-city sample. `weather/packaging.py` unit test lists every shipped file.

**Baseline results (recorded 2026-10-13 at `84700a7`):** see §15.

## 13. Rollback
- **Before any commit (the state you control):**
  - delete `weather/`, `weather-engine/`, `test_weather_*.py` and `test_fixtures/weather_protected.json`;
  - `git checkout -- app.py VideoGenerator.spec` (1B only).
- **After an approved commit:** `git revert <commit>`. Phase 1A and 1B are proposed as separate commits, so the app wiring can be reverted while keeping the library.
- **Leftovers that do nothing once the code is gone:** the `weather_enabled` / `weather_nws_contact` keys in `settings.json` (ignored), `<project>/weather/` folders (ignored), and the per-user cache `…/SemanticYTStudio/weather/` (safe to delete).
- **Verification after rollback:** the isolation guard and the §10 manual proof match the baseline again.

## 14. Order of work after approval
1. 1A, steps in order: data + tests → sidecar + tests → engine fork + drift check + golden tests → render/generate + command line → end-to-end 6-city video → your review.
2. Isolation report for 1A, then I ask before any commit.
3. 1B on your approval: app wiring → app tests → isolation proof → installer check → your review → ask before commit.

## 15. Baseline test results at `84700a7`
Recorded 2026-10-13 on this Mac, clean tree at `84700a7`:
| Suite | Command | Result |
|---|---|---|
| Python | `.venv310/bin/python scripts/run_tests_parallel.py` (Python 3.13.13) | **3509 tests in 198 modules — OK** (300 s) |
| pakmap-engine | `node --test test/*.test.mjs` | **133 / 133 pass** |
| starmap-engine | `npm test` | **54 / 54 pass** |
| Python with `.venv` (3.9.6) | same runner | not a valid baseline: ~170 modules fail on Python 3.10+ syntax (`type \| None`); CI uses 3.12 |

Every phase-1 acceptance run must reproduce these numbers (plus the new Weather tests).
