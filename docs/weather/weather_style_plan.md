# Weather Style — Plan

Status: approved for phase 0 (2026-10-13). Phase 0 findings: [phase0_report.md](phase0_report.md).

## 1. Goal and scope
A new **Weather** video style: USA only, English, three formats — **Forecast**, **Weather News**, **Post-Event Report**.

- **Data:** free US government sources, plus IEM (Iowa State) radar tiles, which are public domain.
- **Look:** satellite map with TV-style weather graphics, plus footage.
- **Automation:** daily prep. The user records the voiceover (no TTS); the app does the rest. The user publishes.
- **Units and time:** °F, mph, inches; every issue time shown in the viewer's zone (e.g. "Issued 5:12 AM CT").

## 2. Isolation — existing styles must not change
1. **No edits to existing style code.** Unchanged: `pakmap/` (schema, compile), `hybrid/`, `starmap/`, `pakmap-engine/` (`render.mjs` and all of `lib/`), `starmap-engine/`, `map-engine/`, AssetManager, stock and YouTube search, Flow, the audio mixer, render cache, Visual Plan.
2. **Weather wraps or imports instead:**
   - `weather/schema.py` validates the weather layer types, then hands the remaining rows to the existing pakMap validation unchanged. Weather types are **never** added to `pakmap.schema.LAYER_TYPES`.
   - `weather-engine/` imports `pakmap-engine/lib/*` (raster, tiles, imagery, camera, draw…) read-only. Radar loops, warning areas, the USA frame and weather graphics live only there.
   - YouTube-by-video-ID lives inside `weather/`; shared search is not touched.
   - Hybrid's import / validate / generate are called from outside; any difference is a wrapper in `weather/`.
3. **Shared files get additive, inert edits only** (listed in phase0_report §4): the Weather entry and its wiring in `app.py`, a Weather tab + on/off in Settings, bundling in `VideoGenerator.spec` (and the CI workflow if needed). With Weather off, the app behaves exactly as today.
4. **Separate storage:** own cache folder, logs, prompts, samples, tests. Daily automation runs as its own process.
5. **Proof before every phase approval:**
   - every existing sample (Normal, pakMap, Hybrid, StarMap, Overscaled, Enoch, Enoch Template) compiles byte-identical before/after;
   - one pakMap and one Hybrid video re-render with identical frames;
   - full Python and engine test suites pass; installed-app check passes;
   - `scripts/weather_isolation_check` reports zero changed lines in the protected paths.
6. **Escalation:** if a shared engine change ever seems needed (radar animation, US framing), it is built in `weather-engine/` instead; if that's truly impossible, work stops and the exact change is shown for approval first.
7. **Rollback:** one commit per phase, never committed without asking. Deleting `weather/`, `weather-engine/` and the two added lines restores today's app.

## 3. Architecture
```text
                    ┌──────────────── weather/ (new) ─────────────────┐
schedule / user ──► │ data: NWS·SPC·NHC·WPC·MRMS·GIBS·ACIS·USGS·CPC   │
                    │ cache + provenance + freshness                  │
                    │ story picker (rules) ─► script writer (template)│
                    │ CSV builder (deterministic) ─► footage pool     │
                    └───────────────┬─────────────────────────────────┘
                                    ▼  Hybrid-shaped CSV
            USER records voiceover ─► alignment ─► freshness re-check
                                    ▼
   weather/schema (wraps pakMap validation) ─► spec ─► weather-engine (imports pakmap-engine/lib)
            ─► footage (existing providers, called not changed) ─► sound ─► render ─► QC
```

## 4. Data (`weather/`)
| Data | Source | Used for |
|---|---|---|
| Point forecasts (7-day, hourly), observations | NWS API (`api.weather.gov`, needs a User-Agent with contact — a Settings field the user fills) | forecast strip, city temps, now card |
| Watches / warnings with polygons | NWS alerts | warning areas, banner |
| Hurricanes: track, cone, warnings | NOAA NHC | track and cone |
| Severe outlooks; tornado/hail/wind reports | SPC | outlook areas, report dots |
| Excessive-rain outlook, QPF | WPC | rain maps |
| Radar (live + archive) | NOAA radar via IEM tiles (public domain, archive to the 1990s); NOAA ImageServer only covers ~2 h | radar loop |
| Satellite (GOES; daily true colour) | NASA GIBS | clouds, before/after |
| Observed totals, records | RCC-ACIS | "wettest day since…" |
| River stages / crests | USGS (and NWS water) | flood markers |
| 6–10 / 8–14 day outlooks | CPC | week ahead |

- **Cache:** per project plus a shared weather cache; no refetch inside a product's validity window.
- **Provenance:** every value keeps source, station/grid point and issue time.
- **Freshness:** forecasts older than ~6 h refused for Forecast; re-checked before render.
- SPC storm reports are always labelled **preliminary**.

## 5. On screen
- **Map layers (new, in weather-engine):** city temp markers with icons, radar loop, satellite clouds, temperature and rain colour maps, warning areas coloured by type, storm track and cone, SPC report dots, rain-total contours, river-crest markers.
- **Graphics (designed once):** 5–7 day forecast strip, now card, high/low card, warning banner, record badge, post-event timeline, source + issue-time line on every data shot.
- **USA frame:** lower 48 as the main view; Alaska and Hawaii as insets when relevant.
- **Icons:** one CC0 weather icon set, sourced once.
- **Reused via import:** pakMap titles, markers, numbers, fills, lines, camera moves.

## 6. Footage
| Tier | Source | Used in |
|---|---|---|
| 1 | US government (NOAA, NWS, NHC, NASA, FEMA, USGS, DVIDS), public domain — **checked per clip** (some agency uploads contain third-party footage) | news, post-event |
| 1 | App-made satellite and radar loops | all formats |
| 2 | Creative Commons YouTube (existing CC-only option), Wikimedia | news, post-event |
| 3 | Stock (Pexels, Pixabay) | forecast b-roll only |
| 4 | News / storm-chaser clips | **off** by default |
| — | User's own local library | all, reused |
| ✗ | AI footage | never for real events |

- One footage pool per event; exact moments picked by transcript words and shot changes.
- Relevance: publish date inside the event window; place or event named in the title.
- Fallback: local library first; otherwise the beat stays on the map (no frozen gaps).
- Chips: credit ("Video: NOAA", "CC BY — channel") and date + place on event footage.

## 7. Formats
| Format | Flow | Length |
|---|---|---|
| Forecast | national overview → regions → key cities → days ahead → warnings to know | 2–4 min |
| Weather News | what's happening → where (radar/storm) → who's under warnings → what's next → footage | 3–8 min |
| Post-Event | what happened → timeline → totals and records → before/after → impacts → recovery | 4–10 min |

Coverage: data for national + top-20 metros + active events; the Forecast **video** shows ~8 regions plus 6–8 key cities (top-20 used for data and alert checks).

## 8. Script and voice
- Written to be read aloud: short sentences, numbers as spoken, pronunciation hints, every number from data, certainty words matching the data ("expected", "likely", "preliminary").
- Optional AI polish with numbers locked.
- User records and drops the file in; map and graphics align to the words (as Hybrid/StarMap).
- Small ad-libs fine; bigger changes → edit the script text before render.

## 9. CSV
Same Hybrid/pakMap columns. New `layer_type` values, **validated only by `weather/schema.py`**: `temp_marker`, `forecast_strip`, `now_card`, `alert_area`, `radar`, `satellite`, `temp_map`, `rain_map`, `storm_track`, `storm_cone`, `storm_reports`, `rain_totals`, `river_crest`, `record_badge`, `source_line`.

`data_source` names the data, never the number: `nws:forecast@Dallas,TX#day1-7`, `nws:alerts@TX`, `nhc:AL092026#cone`, `spc:reports@2026-05-20`, `acis:pcpn_total@Houston,TX#2026-08-25..2026-08-29`.

Automation builds the CSV from data in code; manual videos get a Weather CSV prompt built from the data registry.

## 10. Automation
```text
DAILY PREP (5:30 AM CT, separate process)
  fetch → story picker (hurricane > severe outbreak > extreme heat/cold > heavy rain > routine)
  → script → CSV → footage pool + loops → notify "script ready"
USER: read, record, drop in voiceover
AFTER RECORDING
  align → freshness re-check (changed numbers / new warnings → re-record line or keep with original issue time)
  → render → QC → ready to publish (user publishes)
POST-EVENT: warnings expired + reports in → suggested report → user approval → prep as above
```
- The machine must be awake: phase 2 chooses an OS-scheduled task (macOS + Windows) and/or a catch-up run when the app opens.
- Clip approval: always for News and Post-Event; Forecast uses stock/library b-roll automatically.

## 11. Interface (Weather card only)
Format and coverage; prep status; changes since prep; clip approval (source + licence per clip); Settings: on/off, schedule time, city list, NWS contact.

## 12. Trust and legal
"Expected" wording plus issue time and source on screen; never contradict official warnings; always point viewers to their local NWS office; observed data only in post-reports, "preliminary" where it is; licence and credit recorded per clip.

## 13. Testing and acceptance
- Recorded API responses (no network in tests); every number in a test video checked against its source.
- Each format rebuilt from a real past event: a hurricane, a severe outbreak, a flood, a heatwave.
- Isolation proof (§2) at every phase.
- Freshness: a changed forecast and a new warning are caught before render.
- Visual frame strips reviewed per format; never claim a pass from unit tests alone.

## 14. Phases
| Phase | Build | Done when |
|---|---|---|
| 0. Checks (read-only) | call every API from this machine; radar tile terms; can the engine animate image layers and draw warning polygons (via import only); USA framing; icon set | feasibility report, no code changes |
| 1. Forecast MVP | `weather/` data, cache, provenance (NWS, alerts); temp markers, forecast strip, now card, satellite, source line; Weather card; manual CSV prompt; isolation-check script | 3-min forecast for 6 cities, numbers verified, isolation proof |
| 2. Forecast automation | story picker, script template, CSV builder, schedule, notification, alignment, freshness check | 3 consecutive daily runs with the user's recordings |
| 3. Weather News | radar loop, warning areas, NHC track/cone, SPC/WPC, event footage pool, YouTube by video ID (inside `weather/`) | a past hurricane and a past outbreak rebuilt |
| 4. Post-Event | SPC reports, ACIS totals/records, MRMS totals, GIBS before/after, USGS crests, timeline, post-event suggestion | a past flood and a past tornado outbreak rebuilt |
| 5. Polish | wind-flow animation, smoother radar, clip-approval screen, library reuse | user review |

## 15. Risks
| Risk | Mitigation |
|---|---|
| Radar tile terms / uptime | phase 0 check; NOAA map services fallback |
| NWS outages / rate limits | cache + retries; prep stops cleanly; no stale publishing |
| Prep → recording delay | freshness re-check; issue times on screen |
| YouTube rights | official + CC first, per-clip check; tier 4 off; credits |
| Scarce event footage | app-made loops; beats stay on the map |
| Engine can't do radar/US frame via import | build in `weather-engine/`; else stop and ask (§2.6) |
| Effect on existing styles | §2 rules and proof |

## 16. Decisions
1. Coverage: national + top-20 metros + active events (video shows ~8 regions + 6–8 cities). *Default, confirm.*
2. News / storm-chaser clips: off.
3. App-made satellite and radar loops as footage: yes.
4. Clip approval: always for News and Post-Event; Forecast automatic.
5. Daily prep: 5:30 AM Central.
6. Radar source: IEM (resolved in phase 0).
7. Engine approach (fork vs hook), icons, boundary shapes: see phase0_report §7.
