# Weather Style — Phase 0 feasibility report

Date: 2026-10-13. Read-only: no app code changed (`git status` shows only `docs/weather/`). All probes ran from this Mac; samples and the test render live in the session scratchpad, except the frame strip in `phase0/`.

## Verdict
**Feasible, with zero edits to existing style code.** Every data source answered, archives reach back far enough for the past-event rebuilds, the licences allow commercial video use, and the existing pakMap engine already draws real warning polygons. One architecture decision and four smaller ones are listed at the end.

## 1. Data sources (live calls)
| Source | Endpoint probed | Result | Notes |
|---|---|---|---|
| NWS points → forecast | `api.weather.gov/points/32.78,-96.80` → `gridpoints/FWD/89,104/forecast` | 200, 0.6 s | Dallas: grid FWD 89,104, zone America/Chicago; periods carry temp °F, short text, icon URL, `updateTime` (issue time for provenance) |
| NWS observations | `stations/KDFW/observations/latest` | 200 | values in °C → convert to °F |
| NWS alerts | `alerts/active` (all US) | 200, 927 KB, 1.2 s | **202 alerts, only 16 carry a polygon**; the rest list zones/counties → zone shapes needed (`/zones/county/…` returns a Polygon, 200) |
| NHC | `CurrentStorms.json` | 200 | live: Hurricane Simon (EP) with track/cone/warnings as KMZ + shapefile zips |
| NHC archive | `gis/forecast/archive/al092022_5day_030.zip` (Ian), best track | 200 | shapefiles: track line, cone polygon, points, watches/warnings |
| SPC outlook | `day1otlk_cat.nolyr.geojson` | 200 | GeoJSON with VALID/ISSUE times |
| SPC reports | `climo/reports/yesterday.csv`, `240506_rpts_filtered.csv` | 200 | CSV with lat/lon/comments; archive works (2024-05-06 outbreak) |
| WPC ERO | `exper/eromap/geojson/Day1_Latest.geojson` | 200 | GeoJSON with ISSUE/START/END times |
| RCC-ACIS | `StnData?sid=DFW…maxt,mint,pcpn` | 200 | daily obs (e.g. DFW 3.47" on 2026-10-01) |
| USGS | `nwis/iv … 08057000 … 00065` | 200 | Trinity River at Dallas 11.88 ft, flagged "P" (provisional) |
| CPC 6–10 day | NOAA `mapservices…/cpc_6_10_day_outlk/MapServer` | 200 | temp + precip outlook layers |
| Radar, live | IEM tile `nexrad-n0q-900913` | 200 PNG 256² | |
| Radar, live (federal) | NOAA `radar_base_reflectivity_time/ImageServer` | 200 | **time window only ~1.9 h** → no use for past events |
| Radar, archive | IEM `ridge::USCOMP-N0Q-201708260300` tile + full CONUS composite PNG (12200×5400 + world file) | 200 | Harvey landfall reachable; archive back to the 1990s |
| MRMS raw | `noaa-mrms-pds` on AWS (reflectivity, 72 h QPE) | 200 | GRIB2 — needs a decoder; only for phase 4 rain totals |
| Satellite | GIBS MODIS true colour (2017-08-25), GOES-East visible (2026-10-12 18Z), IMERG precip (2017) | 200 | daily and sub-daily imagery for before/after and cloud loops |

## 2. Licences
- **NWS/NOAA:** public domain; may not (1) claim it as yours, (2) imply NOAA/NWS endorsement, (3) present modified content as official. → On-screen wording "Data: National Weather Service", **no NWS/NOAA logos** on our graphics.
- **IEM (Iowa State):** "in the public domain and may be used freely by anyone for any lawful purpose"; attribution appreciated. → **IEM radar is acceptable as the primary radar source** (plan §16.6 resolved), credited "Radar: NOAA via Iowa Environmental Mesonet".
- **NASA GIBS:** CC0 unless marked; acknowledge NASA, no implied endorsement. The engine already carries the GIBS acknowledgement.

## 3. Engine (pakmap-engine, read only)
| Need | Existing support | Verdict |
|---|---|---|
| Warning areas, SPC/WPC outlook areas, hurricane cone | `fill` events accept arbitrary `polys` (MultiPolygon) | **works as-is** — test render drew 16 live NWS warning polygons + the SPC thunder area (`phase0/us_test_strip.jpg`) |
| Temperature / rain colour maps, CPC outlooks | `value_overlay` (grid + colour ramp, clipped) | works as-is; weather ramps (°F, inches) are new data, not code |
| City markers, numbers, titles, lines (storm track) | `marker`, `stat`, `hud_title`, `line` in `draw.mjs` | works as-is |
| **Radar / satellite loop** (image changing over time) | image sources are static; no per-frame swap | **new code needed** |
| Forecast strip, now card, warning banner, source line | not present | new 2D graphics |
| State borders | only country borders (`countries.json.gz`) | needs US state shapes (Census cartographic boundaries, public domain, sourced once) |
| USA framing | camera works; at zoom 3.55 CONUS sits on the globe (looks good but small) | national shot ≈ zoom 4.0; flat map from regional shots in |
| Speed | 3 frames in 13 s including browser start, 0 tile failures | fine |

**Why a fork is needed for the new parts:** `render.mjs` runs on import (no exports) and serves `page.js`/`lib/` from its own folder; `page.js` keeps the map private. So a new layer cannot be plugged in from outside. Two ways:

- **A — Fork (recommended, matches the isolation rule):** `weather-engine/render.mjs` and `weather-engine/page.js` start as copies (~520 lines) and import the unchanged `pakmap-engine/lib/*.mjs` and its MapLibre. Radar loops and weather graphics are added only there. Zero shared edits. Cost: future fixes to pakMap's `render.mjs`/`page.js` don't flow in automatically → a test that flags when those two files change upstream, so I review and port.
- **B — Tiny hook in pakMap:** ~5 lines in `page.js`/`render.mjs` (expose the map, load an optional plugin). Less copying, but it edits shared files — requires your explicit approval and identical-render proof.

## 4. Shared-file edits — corrected count
The plan said "two additive edits". The code shows more places, all **additive** and inert while Weather is off:
1. `app.py` — Weather in `STYLE_CHOICES`, its description/icon, the mode map, and stepping other styles aside when Weather is picked (StarMap needed the same ~6 spots).
2. Settings — Weather tab + on/off.
3. `VideoGenerator.spec` — bundle `weather-engine/` and `weather/` data.
4. `.github/workflows/build-desktop.yml` — install `weather-engine` deps (if it has its own; with option A it can reuse pakmap-engine's `node_modules` and need none).

## 5. Icons
No CC0 weather set exists among the established ones:
- **Meteocons** (basmilius/weather-icons) — **MIT**, animated SVG/Lottie, broadcast look. Recommended; needs one licence line in credits.
- Erik Flowers Weather Icons — SIL OFL font; static, older look.
- Makin-Things weather-icons — MIT, small set, last updated 2022.
- NWS's own icons — public domain but photo-style, low resolution.
Nothing downloaded yet (needs your OK).

## 6. Other findings that change the build
- Alerts without polygons (≈92% today) need county/zone shapes: fetch per zone from NWS (cached) or bundle Census county shapes once.
- NWS observations are metric → convert; forecasts already °F.
- USGS values are provisional ("P") → label like SPC "preliminary".
- NHC/SPC/WPC each carry their own issue times → feeds the on-screen source line directly.
- Rain totals for post-event: ACIS station totals work today; gridded MRMS totals need a GRIB2 decoder (phase 4 decision; IEM may offer ready PNGs — to check then).

## 7. Decisions needed before phase 1
1. **Engine:** A (fork, recommended) or B (5-line hook in pakMap).
2. **Shared edits in §4:** approve these additive edits.
3. **Icons:** Meteocons (MIT) OK? Then I'll ask before downloading.
4. **State + county shapes:** bundle US Census cartographic boundaries once (public domain, ~2–5 MB)? Ask before downloading.
5. Plan §16 defaults 1–5 still stand unless you change them.
