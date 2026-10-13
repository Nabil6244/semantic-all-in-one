# Weather — Phase 4 report (Post-Event Report)

Date: 2026-10-13. **Nothing committed.** Only files owned by phase 4 (contract §5) were created; no shared file was edited.

## Files created
| Area | Files |
|---|---|
| Data (`weather/post/`) | `__init__.py`, `fmt.py` (dates, spans, "no digits in author text", row-naming wrapper), `acis.py` (RCC-ACIS: values M/T/S/A, totals, top-N period-of-record ranking, station table), `usgs.py` (USGS IV gage height, provisional flags, crest + gap detection, NWS water flood categories and historic crests), `mrms.py` (IEM-archived MRMS 24 h PNGs: stdlib+numpy PNG decoder, IEM index→mm encoding, day sums, `.asc` writer), `gibs.py` (daily MODIS/VIIRS providers + DescribeDomains check), `besttrack.py` (NHC HURDAT2 landfalls), `products.py` (fetch-once into `snap.extra["post:..."]`), `timeline.py` (marks read from data), `suggest.py` (post-event suggestion rule) |
| Layer types (`weather/layers/`) | `totals.py` (`rain_total`, `record`, `temp_extreme`), `rivers.py` (`river_crest`), `rainmap.py` (`rain_map`), `beforeafter.py` (`before_after`), `timeline.py` (`event_timeline`) |
| Engine plugins | `weather-engine/lib/layers/post_chip.mjs`, `post_bars.mjs`, `post_record.mjs`, `post_hydrograph.mjs`, `post_rainlegend.mjs`, `post_timeline.mjs`, `post_beforeafter.mjs`; shared pure maths `weather-engine/lib/wxu_post_charts.mjs` |
| Tests | `test_weather_post_data.py`, `test_weather_post_layers.py`, `test_weather_post_suggest.py`; `weather-engine/test/post_unit.test.mjs`, `weather-engine/test/post_render.test.mjs` |
| Fixtures | `weather/testdata/post/` (248 KB): real ACIS, USGS, NWPS, GIBS, HURDAT2 answers (`urls.json` maps each file to its URL); MRMS: the 7 real Harvey 24 h grids **cropped** to Houston (indices unchanged, re-encoded PNG, world file adjusted — the full CONUS PNGs are 3 MB each) |

## Sources (verified from this Mac, 2026-10-13)
- **RCC-ACIS** `StnData`/`MultiStnData`/`StnMeta` as GET `?params=<json>`. Records use ACIS's own summary `{"reduce": "max", "add": "date", "n": 10}` over `sdate: por .. edate: <the day>` (so a day is ranked against what came before it, inclusive), or `interval: [1,0,0]` for a calendar-date record. Threaded records (`IAHthr 9` "Houston Area", 1888→) for city records; airport stations for totals.
- **USGS** IV for past years redirects to `https://nwis.waterservices.usgs.gov/nwis/iv/` (used directly). Buffalo Bayou 08074000: crest 41.90 ft (approved, revised) 2017-08-28 01:00 CDT, inside a gap of ~7 h in the record → screen shows the **day** only, report says the time is uncertain.
- **NWS water (NWPS)** `https://api.water.noaa.gov/nwps/v1/gauges/<USGS id>` works with the USGS number: flood categories (today's) and historic crests (with an `olddatum` flag). Optional: without it the crest still shows.
- **MRMS**: IEM tile layers only go to p72h, and a 72 h index caps at 495 mm (Harvey exceeds it). So `rain_map` sums the archived **24 h** PNGs (`/archive/data/YYYY/MM/DD/GIS/mrms/p24h_YYYYMMDD1200.png`, 0.01°, available since 2015; verified for Aug 2017). Encoding from IEM's `make_mrms_rasters.py`: 0–99 ×0.25 mm, 100–179 25+×1.25, 180–254 125+×5, 254 = ≥495 mm, 255 missing. Check against gauges (Aug 25 12Z–Sep 1 12Z vs ACIS calendar days): IAH 38.5 vs 31.26, Hobby 40.5 vs 37.01, Port Arthur 53.0 vs 47.48, Galveston 24.0 vs 22.84 — consistent (MRMS is a radar estimate; windows differ). Capped cells are tracked; a capped peak is printed "AT LEAST n" (floored, never rounded up).
- **GIBS**: `MODIS_Terra_CorrectedReflectance_Bands721` (`falsecolor`) shows flood water dark blue; Terra 2017-08-22 and 2017-08-31 are mostly clear over SE Texas. `{z}/{y}/{x}` order, Level9.
- **NHC HURDAT2** (newest file found from the folder listing). The ATCF b-deck does **not** flag landfalls; HURDAT2 rows with `L` do. Harvey has 5 `L` rows (2 in the Caribbean on Aug 18), so a timeline's `#n` counts landfalls **inside the timeline's days**.

## How to use each type (`weather_layers.csv`)
```csv
beat,vo_anchor,t,id,type,place,data_source,hold,until,extra
b3,This map adds up,,rm,rain_map,,mrms:total@2017-08-25..2017-09-01,,,"{""bbox"": [-98, 27.5, -93, 31.5], ""peak"": true}"
b4,Between August 25,,bars,rain_total,,"acis:pcpn_total@BPT|HOU|IAH|GLS|SGR|CXO#2017-08-25..2017-09-01",,,"{""title"": ""RAIN GAUGE TOTALS""}"
b4,Houston Intercontinental,,iah,rain_total,,"acis:pcpn_total@Houston,TX#2017-08-25..2017-09-01",,,"{""side"": ""l""}"
b5,At Houston,,rec,record,,"acis:record@Houston,TX#pcpn#2017-08-27",,,
b5,At Phoenix,,phx,temp_extreme,,"acis:record@Phoenix,AZ#maxt#2023-07-19",,,
b6,Buffalo Bayou,,bb,river_crest,,usgs:crest@08074000#2017-08-25..2017-09-05,,,"{""chart"": true, ""anchor"": ""l""}"
b7,Here is August 22,,ba,before_after,,gibs:falsecolor@2017-08-22|2017-08-31,,,"{""switch"": 4.5, ""crossfade"": 1.5}"
b2,Here is the timeline,,tl,event_timeline,,post:timeline@2017-08-24..2017-09-01,,,"{""marks"": [{""from"": ""nhc:landfall@AL092017#1""}, {""from"": ""acis:peak_day@Houston,TX#2017-08-25..2017-09-01""}, {""from"": ""usgs:crest@08074000#2017-08-25..2017-09-05""}, {""from"": ""nhc:landfall@AL092017#3"", ""title"": ""LOUISIANA LANDFALL""}]}"
```
- `rain_total`: one place → map chip (count-up); `|`-separated places (≤ 8) → bar chart (sorted, bars grow, values count up). Place = `City, ST` (table in `acis.PLACES`) or an ACIS id. extra: `show` (chip/bars), `labels` (words), `title`, `decimals` (0–2), `sort`, `anchor`, `side`. Missing days → "N DAYS MISSING" on screen and "at least" in the report; data < 90 days old → PRELIMINARY.
- `record` / `temp_extreme`: `#pcpn|snow|maxt|mint[:date]#YYYY-MM-DD`. Badge: headline ("WETTEST DAY ON RECORD", "3RD WETTEST…", "TIED: 4TH HOTTEST…", "WETTEST AUG 27 ON RECORD"), place, value + date, the old record (or the #1 it did not beat), "RECORDS SINCE 1888". A day outside the top 10 is refused ("leave this record out").
- `river_crest`: chip "BUFFALO BAYOU 41.9 FT · CREST AUG 28 · MAJOR FLOOD"; tag PROVISIONAL (USGS "P") or RECORD CREST (above every crest NWS lists). extra `chart: true` adds the hydrograph (gaps stay gaps; NWS stage lines; crest marked). Categories are labelled in the report as NWS's **current** stages.
- `rain_map`: value_overlay of the summed grid (cells under `min_in`, default 1 in, left clear) + legend (stops in inches, period in local time; optional `peak`). Refuses a box where < 55 % of cells reach `min_in` (pakMap would refuse < 50 % coverage at render).
- `before_after`: two GIBS frames in one Raster (crossfade; `clock` off) + the `post_beforeafter` label (BEFORE/AFTER · date) top right.
- `event_timeline`: marks from `nhc:landfall@`, `acis:peak_day@`, `usgs:crest@`, `acis:record@`; author may change a mark's **words** only (digits are refused).
- Every row fills `out.shown` (a `kind: text` source string), `out.credit(...)`, and adds every on-screen number to the report with its URL.

## Suggestion rule (`weather/post/suggest.py`)
`suggest(alerts, reports, now, already=())` — pure. Episodes = runs of significant warnings per state (each within 48 h of the run). Offered when every warning ended ≥ 24 h ago, none is in force in the state, it was big enough (hurricane/tropical warning, ≥ 3 warnings, or ≥ 10 storm reports), severe-storm episodes have SPC reports with the last ≥ 24 h old, it ended ≤ 30 days ago, and its id was not offered before. Returns title ("Hurricane aftermath in Texas, Aug 24–31, 2017: what happened"), kind, state, dates, reasons.

## Tests
| Suite | Result |
|---|---|
| `test_weather_post_data.py` | 27 OK |
| `test_weather_post_layers.py` | 22 OK |
| `test_weather_post_suggest.py` | 7 OK |
| `weather-engine/test/post_unit.test.mjs` | 8 / 8 |
| `weather-engine/test/post_render.test.mjs` (offline renders: every plugin, footage cover, broken event named) | 3 / 3 |
| `test_weather_isolation.py` | 4 OK |
| other `test_weather_*.py` | see "Suite status" below |

## End-to-end: Hurricane Harvey, Houston (Aug 25 – Sep 1, 2017)
Project: `/private/tmp/claude-501/-Users-muhammadnabil-Downloads-video-generator-main/7e9a9c8f-0a58-475c-bf65-5f5a8ffc9148/scratchpad/post_e2e/` (`script.txt`, `beats.csv`, `weather_layers.csv`, `resolved.json` from `weather.resolve.prepare(rows, None)` — no NWS product, no contact needed; `vo.wav` is a macOS `say` **test voice**). See "E2E result" below for the video path, frames and review notes.

## Requests for the integrator
1. **`python -m weather fetch` without an NWS contact** (post-event plans need no NWS product; `prepare` already raises a clear error when one is needed). `weather/cli.py`:
   ```python
   f.add_argument("--contact", default="", help="your email or website, sent to the NWS as it asks (only needed for NWS products)")
   ```
   `weather/generate.py` `fetch`:
   ```python
   snap = prepare(rows, client or (NwsClient(contact) if contact else None), now=now, **kw)
   ```
   and print `len(snap.extra)` products in the CLI summary (`print(f"  other products: {len(snap.extra)}")`).
2. **Misleading pakMap credit for the rain grid.** pakMap's `resolveEvent` adds "Grid data: mrms_<hash>.asc (supplied by the author)". In `weather-engine/render.mjs`, replace `plan.credits.attribution.push(...resolved.credits);` with
   ```js
   plan.credits.attribution.push(...resolved.credits.filter((c) => !/^Grid data: mrms_[0-9a-f]{16}\.asc \(supplied by the author\)$/.test(c)));
   ```
   (the MRMS credit itself arrives through `spec.weather.credits`).
3. **Where layer files live.** `build(row, snap, window, out)` has no project folder, so `rain_map` writes its `.asc` grid to `cache_root()/post_grids/` (content-addressed, absolute `file:` path). Optional: add `work_dir: Optional[Path] = None` to `WeatherPayload` and set `payload.work_dir = project.work_dir` in `generate.plan_layers` before `build`; `rainmap.grid_folder()` would then prefer it.
4. **Wipe for before/after (proposal; crossfade works today).** A wipe needs per-layer clipping MapLibre raster layers do not have. Proposed, in `page.js` `renderFrame`: for a raster with `r.wipe`, draw the map twice — once with frame k, once with frame k+1 — and composite the second through a clip rect `x < W * mix` on the 2D canvas. Costs a second `waitDrawn` per frame during the wipe only; not built (shared file).
5. **Post-event CSV prompt** — add `weather/prompts/post_event_csv_prompt.txt` (text below) and list it in the Weather card's prompt menu.
6. **App UI**: a "Post-Event" format in the Weather card: (a) "Suggested reports" list from `weather.post.suggest.suggest(alerts, reports, now, already=<ids saved in Weather settings>)` fed by NWS alert history (`/alerts?area=XX&start=...`, needs the NWS contact) and phase 3's SPC report parser; (b) on approval, create a project folder with the CSV prompt prefilled with title/state/dates; (c) clip approval is always on for this format (plan §16.4). No footage source is added by phase 4 (beats stay on the map).
7. `test_weather_sidecar.test_every_problem_names_its_row` now fails because phase 3 registered `radar` (the test expects "unknown type 'radar'"); not phase 4's, noted for the merge.

### Proposed `weather/prompts/post_event_csv_prompt.txt`
```
You write a Weather POST-EVENT REPORT plan: what happened -> timeline -> totals and records -> before/after -> impacts -> recovery
(4-10 minutes). Output two CSVs: beats.csv (Hybrid beat CSV, map beats only unless the user gives public-domain footage files) and
weather_layers.csv (columns beat,vo_anchor,t,id,type,place,data_source,hold,until,extra).
RULES
- Observed data only. Never type a number into a label or the script that the data does not give; numbers come from the layers.
- Say "radar estimate" for rain_map, "observed" for station totals, "provisional"/"preliminary" when the screen says so.
- Flood stages are the NWS's current categories ("the major flood stage the Weather Service uses today").
- One big panel at a time on the right (rain_total bars, record, hydrograph with anchor r); the timeline uses the bottom band, so
  do not show it with the rain legend. Every data beat gets a source_line row.
TYPES
- rain_map        mrms:total@YYYY-MM-DD..YYYY-MM-DD   extra {"bbox": [w,s,e,n]} (<= 12x10 degrees, 2015 or later)
- rain_total      acis:pcpn_total@<City, ST | ACIS id>[|...]#YYYY-MM-DD..YYYY-MM-DD  (one place: map chip; several: bar chart)
- record          acis:record@<City, ST>#pcpn|snow|maxt|mint[:date]#YYYY-MM-DD
- temp_extreme    acis:record@<City, ST>#maxt|mint#YYYY-MM-DD
- river_crest     usgs:crest@<USGS site>#YYYY-MM-DD..YYYY-MM-DD   extra {"chart": true} for a hydrograph
- before_after    gibs:falsecolor|truecolor@YYYY-MM-DD|YYYY-MM-DD   extra {"switch": seconds, "crossfade": seconds}
- event_timeline  post:timeline@YYYY-MM-DD..YYYY-MM-DD   extra {"marks": [{"from": "nhc:landfall@AL092017#1"},
                  {"from": "acis:peak_day@City, ST#range"}, {"from": "usgs:crest@site#range"}, {"from": "acis:record@..."}]}
CAMERA: the first beat may start continental and push in (camera rows: start place "lat,lon" frame continental, then push_in with
extra {"zoom_delta": 4}); later beats use type=hold, or a camera row with vo_anchor (camera t is narration seconds, not beat seconds).
Whisper writes numbers as digits: anchors must use "August 22", not "August twenty-second".
```
