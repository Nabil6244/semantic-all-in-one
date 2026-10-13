# Weather — Phase 3 report: Weather News

Date: 2026-10-13. **Nothing committed.** Only files phase 3 owns were created (contract §5); no existing file was edited.

Weather News adds a radar loop, satellite loops, NHC hurricane cones and tracks, SPC outlooks and storm reports, WPC rain outlooks,
archived NWS warnings that appear at their issue times, counters, and an event footage pool with per-clip licence checks and approval.
The video flow is unchanged: `beats.csv` + `weather_layers.csv` → `python -m weather fetch` → `python -m weather render`.

## Files created
| File | What it does |
|---|---|
| `weather/news/__init__.py` | package doc |
| `weather/news/shapefile.py` | stdlib ESRI shapefile + dBASE reader (points, multipoints, polylines, polygons incl. Z/M variants; outer rings vs holes → pakMap MultiPolygon); reads a whole zip |
| `weather/news/radar_providers.py` | radar provider registry (`iem_n0q` default, `noaa_mapservices` live-only / not XYZ, `none`), IEM scan lists, even frame picking, per-time tile provider records, dBZ ramp + legend words |
| `weather/news/nhc.py` | NHC advisory zip → cone, forecast track, forecast points (kt → mph rounded to 5, Saffir-Simpson, local labels), coastal watches/warnings; best track zip → 6-hourly points + strength-coloured segments |
| `weather/news/spc.py` | SPC categorical outlook GeoJSON (archive + current, issuance fallback), storm reports CSV (convective day, UTC times, in time order) |
| `weather/news/wpc.py` | WPC excessive rainfall outlook: current GeoJSON and archived shapefile zips; WPC colours |
| `weather/news/iem_warnings.py` | IEM storm-based warnings archive (`sbw.geojson`): one record per warning (first polygon, first start, last end), colours from `weather/alerts.py` |
| `weather/news/timeline.py` | UTC windows, real time → narration time (last 15 % holds the end), state/city → time zone |
| `weather/news/rows.py` | row naming in messages; first URL that answers (404 = "not archived", named) |
| `weather/news/sources.py` | NASA Image and Video Library search, Wikimedia Commons search (extmetadata licence/author), YouTube by video ID (metadata via the app's `providers.youtube` backend, imported, never edited) |
| `weather/news/footage_pool.py` | `Event`, `Clip`; relevance rule (date window + event/place named) and licence rule; credit text; `search()` |
| `weather/news/approval.py` | `<project>/weather/clips.json` store (decisions survive a new search; a licence failure can never be approved); ranged ffmpeg download of the used part of NASA/Commons clips; hand-off rows for `beats.csv` (row=clip, asset = local file) and `weather_layers.csv` (footage_credit) |
| `weather/layers/radar.py` | layer types `radar` and `satellite_loop` |
| `weather/layers/storms.py` | layer types `storm_cone`, `storm_track` (advisory or best track), `footage_credit` |
| `weather/layers/severe.py` | layer types `spc_outlook`, `storm_reports`, `wpc_ero`, `warnings_archive` |
| `weather/layers/counters.py` | layer type `counter` |
| `weather-engine/lib/wxu_news_anim.mjs` | pure maths: count-up, report reveal, dBZ scale, panel layouts |
| `weather-engine/lib/layers/radar_legend.mjs` | radar dBZ bar, "LIGHT · MODERATE · HEAVY · HAIL", bottom right |
| `weather-engine/lib/layers/counter.mjs` | big counting number with label and sub line, at a corner |
| `weather-engine/lib/layers/storm_points.mjs` | category-coloured hurricane dots popping in along the track, label chips that avoid each other |
| `weather-engine/lib/layers/storm_reports.mjs` | report dots (tornado red / wind blue / hail green) in time order; legend whose counts tick up; must say PRELIMINARY |
| `weather-engine/lib/layers/storm_credit.mjs` | `footage_credit` chip (`overFootage: true`, see request R3) |
| `weather/testdata/news/*` | recorded real answers (README lists every URL) + two hand-made files marked `_SYNTHETIC` |
| `test_weather_news_parsers.py`, `test_weather_news_layers.py`, `test_weather_news_footage.py` | Python tests (no network) |
| `weather-engine/test/news_unit.test.mjs`, `weather-engine/test/news_render.test.mjs` | engine unit tests + an offline render of every news graphic |

## How to use (sidecar rows)
```csv
beat,vo_anchor,t,id,type,place,data_source,hold,until,extra
b4,Now the radar,,rad,radar,Florida,iem:radar@2022-09-28T14:00Z..2022-09-28T22:00Z#n0q,,,"{""frames"": 17}"
b4,Now the radar,,rad2,radar,TX,iem:radar@latest#n0q,,,"{""provider"": ""iem_n0q"", ""tz"": ""America/Chicago""}"
b1,one picture a day,,sat,satellite_loop,Florida,gibs:truecolor_loop@2022-09-24..2022-09-29,,,
b1,the clouds today,,sat2,satellite_loop,TX,gibs:geocolor_loop@2026-10-12T15:00Z..2026-10-12T21:00Z,,,"{""frames"": 16}"
b3,placed the cone,,cone,storm_cone,Florida,nhc:cone@AL092022#024,,,
b3,Its forecast had,,fc,storm_track,Florida,nhc:track@AL092022#024,,,"{""labels"": 3}"
b2,as the National Hurricane,,best,storm_track,Florida,nhc:track@AL092022#best,,,"{""label_times"": [""2022-09-28T12:00Z"", ""2022-09-28T18:00Z""]}"
b1,put north central Oklahoma,,otl,spc_outlook,Oklahoma,spc:outlook@2024-05-06#day1_1630,,,
b1,the outlook today,,otl2,spc_outlook,US,spc:outlook@latest#day1,,,
b4,These are the storm,,rep,storm_reports,Kansas,spc:reports@2024-05-06,,,
b5,rain outlook for that day,,ero,wpc_ero,Florida,wpc:ero@2022-09-28#day1,,,
b4,Now the radar,,warn,warnings_archive,Florida,"iem:warnings@2022-09-28T14:00Z..2022-09-28T22:00Z#TO,EW",,,"{""states"": [""FL""]}"
b5,In all the National,,ew,counter,Florida,iem:warnings@2022-09-28T12:00Z..2022-09-29T00:00Z#EW,,,"{""states"": [""FL""]}"
b4,The Storm Prediction Center lists,,tcnt,counter,Kansas,spc:reports@2024-05-06#tornado,,,"{""anchor"": ""tl""}"
b6,NASA cameras on,,b6_credit1,footage_credit,,,,,"{""text"": ""VIDEO: NASA · SEP 28, 2022""}"
```
Rules worth knowing:
- **Radar**: `#n0q` only; a window of at most 48 h (UTC, `start..end`); `frames` 2–60 (default 18), picked evenly from the scans IEM
  lists (a gap in IEM's archive stays a gap). Clock chip `RADAR · 3:05 PM EDT` in `extra.tz`, else the place's zone; with the date when
  the window passes 20 h (or `"date": true`). Legend on by default. Only `latest` has a freshness rule (stale after 1 h).
- **Replays stay in step**: radar, satellite loop and `warnings_archive` map their UTC window linearly onto the layer's on-screen time
  (the last 15 % holds the final picture). Give the radar and the warnings the same window and the same beat, and each warning appears
  on the radar frame of its issue time (tested).
- **Satellite loop**: GOES-East GeoColor (`geocolor_loop`, ≤ 24 h, 10-min pictures) is only kept by GIBS for about two months — GIBS
  still *lists* older times, so the fetch probes the first and last tiles and says to use `truecolor_loop` (daily VIIRS, any year)
  when they are gone (verified live: 2022 GeoColor tiles answer 404). Full opacity, under fills. Report lists the picture times.
- **NHC**: `#024` = advisory 24 (three digits; `nhc:cone@...#best` refused). Advisory wind in knots → mph rounded to 5 (NHC's public
  convention, 135 kt → 155 mph); the report keeps the knots and the zip URL. Best track: label the times in `label_times`, default
  the strongest point. Cone opacity 0.35, white outline; coastal watches/warnings as pakMap `line` events in NHC's colours.
- **SPC**: outlook selector `day1|day2|day3[_HHMM]`; without an issuance the archive tries 1300, 1200, 1630 (day 1). Reports: all three
  kinds or `#tornado,hail`; always "PRELIMINARY" (the plugin refuses a legend without it; a report counter's sub line always adds it).
- **Warnings archive**: types `TO SV FF EW MA SQ DS FA FL` (default `TO,SV,FF`); `extra.states` filters with IEM's `states=`.
  Warnings that only touch the window's edges are left out.
- **Counter**: one report kind (`#tornado`) or one warning type (`#EW`); warnings are counted once each and only if *issued* inside
  the window.

## Data checks done live (this machine, 2026-10-12/13)
- **IEM tiles are XYZ**: tile `6/17/27` of `ridge::USCOMP-N0Q-202209281900` shows Ian's eye at ≈26.7N 82.3W; the same area cropped from
  IEM's whole-CONUS `n0q_202209281900.png` (+ world file) matches; the TMS row (`6/17/36`) is an empty 334-byte tile. Template:
  `https://mesonet.agron.iastate.edu/c/tile.py/1.0.0/ridge::USCOMP-N0Q-YYYYMMDDHHMI/{z}/{x}/{y}.png`.
- Scan lists: `https://mesonet.agron.iastate.edu/json/radar?operation=list&product=N0Q&radar=USCOMP&start=..&end=..` (end exclusive);
  latest: `.../data/gis/images/4326/USCOMP/n0q_0.json`.
- NOAA `radar_base_reflectivity_time/ImageServer` has no tile cache (`tileInfo: null`), so it is pictures by bbox only (request R6).
- SPC archive: flat per year, `archive/YYYY/day1otlk_YYYYMMDD_HHMM_cat.nolyr.geojson`; colours are in each feature (`fill`, `stroke`).
- WPC ERO archive: `archives/ero/YYYYMMDD/shp_94e_YYYYMMDDHH.zip` (98e day 2, 99e day 3); colours from WPC's KML.
- NASA: `images-api.nasa.gov` search + `images-assets.nasa.gov/.../collection.json` (renditions `~medium.mp4` 1280×720 etc.).
- **Wikimedia Commons could not be reached from this machine** (DNS blocked; also not on the contract's download list). The Commons
  code is tested on a hand-made answer in the documented MediaWiki shape (`commons_search_SYNTHETIC.json`); it is untested live.

## Numbers (from the fixtures and the E2E data)
- Ian advisory 30 (11 PM EDT Thu Sep 29 2022): first point 30.2N 79.3W, 70 kt → **80 mph, Cat 1**, labelled THU 8 PM.
- Ian advisory 24 (11 AM EDT Wed Sep 28): 12Z position 26.3N 82.5W, 135 kt → **155 mph, Cat 4**; 00Z 105 kt → 120 mph Cat 3;
  12Z Sep 29 60 kt → 70 mph tropical storm.
- Ian best track: peak **140 kt (160 mph), Cat 5 at 12Z Sep 28** (26.0N 82.7W); 18Z Sep 28 **135 kt (155 mph), Cat 4**, 938 mb (26.6N 82.4W).
- IEM warnings, Florida, 12Z Sep 28 – 00Z Sep 29: **5 Extreme Wind Warnings** (all NWS Tampa Bay), 7 Tornado Warnings.
- WPC Day 1 ERO issued 11Z Sep 28: Marginal → **High risk** (High area ≈ 25.9–29.5N, 82.8–80.5W).
- SPC 2024-05-06 reports (preliminary): **46 tornado, 257 wind, 79 hail**; 16:30Z Day 1 outlook had a **High risk** (≈34.8–37.7N,
  98.9–96.3W); **24 tornado warnings** issued in OK + KS between 21Z May 6 and 03Z May 7.

## Tests
| Suite | Result |
|---|---|
| `test_weather_news_parsers.py` | 23 tests OK |
| `test_weather_news_layers.py` | 26 tests OK |
| `test_weather_news_footage.py` | 13 tests OK |
| `test_weather_isolation.py` | 4 tests OK |
| other `test_weather_*.py` (run one by one) | all OK except two not caused by phase 3: `test_weather_sidecar` 1 failure (uses `radar` as its example of an *unknown* type — request R2) and `test_weather_auto_prep` cannot load (phase 2's fixture `weather/testdata/automation/prep_recording.json.gz` is missing in the checkout right now) |
| `weather-engine` `node --test test/*.test.mjs` | **46 / 46** (includes `news_unit` 5 and `news_render` 1) |

What they cover: shapefile records (points, polygons with holes, two outer rings), dbf types, bad files; Ian advisory 30 and best
track values; advisory-time parsing incl. AST, month roll-over of forecast times; SPC outlook colours/times and issuance fallback;
reports in UTC order across midnight; WPC zip + GeoJSON; IEM warnings dedupe, colours, URL; radar scan list, even frames, XYZ template,
provider config (unknown, not-XYZ, none, before 2010); sidecar errors name the row for every news type; fetch errors name the row;
radar labels/tz/legend/source line/report; latest radar freshness; archive never stale; satellite loops (daily, too-old GeoColor
refused with advice, recent GeoColor labels); cone/coast/legend; forecast and best-track labels and their report lines (knots +
URL); SPC/WPC fills and legends; reports reveal order + PRELIMINARY; warnings in step with the radar frame of their issue time;
counters (reports, warnings issued in window, PRELIMINARY forced); each product fetched once; footage relevance (date window, whole-word
names), licence rules for NASA / Commons / YouTube, approval storage, decisions surviving a re-search, licence failures never
approvable, download command (faked ffmpeg), clip and credit rows that the Hybrid CSV and the sidecar accept. Engine: count-up,
reveal, dBZ scale, panel places in frame, validation messages per plugin, and an offline render checking the counter panel and
digits, the legend bar colour, the reports panel and the category-4 dot.

## End-to-end renders
See "E2E" below.

## Known limits
- Commons search untested live (blocked here). YouTube: metadata by ID only; downloading needs the app (R4).
- The footage credit chip is hidden under footage until R3 is in (the credit is in the description credits meanwhile).
- `noaa_mapservices` cannot be drawn until R6. IEM parallel-request limit (4) needs R7.
- Radar tiles are fetched at render time; with no network the radar beat shows the base map (the render goes on).
- Storm surge, wind radii and SPC watch boxes are not drawn (the NHC best-track zip has `windswath`/`radii` layers the reader can read).
- `storm_points` labels avoid each other and other chips, but not pakMap's HUD title.

## Requests for the integrator
### R1 — CSV prompt and sidecar doc
Add the news types to `weather/sidecar.py`'s module doc (the `type` line) and add a Weather News CSV prompt
(`weather/prompts/news_csv_prompt.txt`) listing the rows in "How to use" above, with these rules: radar + warnings_archive share the
window and beat; no number in the script that is not in `python -m weather check`'s report; anchors must not use a storm's name if the
transcriber mishears it (Whisper wrote "Ian" as "iain" — anchor on other words); every data beat has a `source_line`;
footage only from approved clips (`approval.ClipStore.clip_rows`).

### R2 — `test_weather_sidecar.py` uses `radar` as an unknown type
`radar` is now a real type, so `test_every_problem_names_its_row` fails. Change the example type in that test's CSV and its
expected message from `radar` to a name no phase uses, e.g.:
```python
# test_weather_sidecar.py line 44
-            "b1,,1,a,radar,,,,,",                                                     # row 2: unknown type
+            "b1,,1,a,tornado_cam,,,,,",                                               # row 2: unknown type
# line 59
-        for n, words in [(2, "unknown type 'radar'"), ...
+        for n, words in [(2, "unknown type 'tornado_cam'"), ...
```

### R3 — credit chips over footage (`weather-engine/lib/wx_draw.mjs`)
Footage is drawn by pakMap's `media_full` (`cover_ui`) and `createWxOverlay().draw` returns early once footage covers the frame, so
no weather graphic can sit on footage. Proposal: plugins that declare `overFootage: true` are drawn in a last pass, after the footage
check, with `h.footage = true` and full alpha (they fade with their own life only):
```js
// wx_draw.mjs, createWxOverlay: after `const pluginList = ...`
const onFootage = pluginList.filter((p) => p.overFootage);            // e.g. footage_credit (lib/layers/storm_credit.mjs)
const onMap = pluginList.filter((p) => !p.overFootage);
// ... and draw(t) becomes:
    draw(t) {
      if (!wx.length && !rasters.some((r) => r.clock)) return;
      const hide = footageCover(all, t);
      const live = activeAt(wx, t).map((e) => shiftedEvent(e, t, hold));
      if (hide < 1) {
        vis = 1 - hide;
        placed = [];
        ctx.save(); ctx.scale(S, S);
        for (const type of ['alert_legend', ...onMap.filter((p) => (p.order ?? 50) < 50).map((p) => p.type), 'temp_marker', 'now_card', 'forecast_strip',
          ...onMap.filter((p) => (p.order ?? 50) >= 50).map((p) => p.type), 'source_line']) for (const e of live) if (e.type === type) DRAW[type](e, t);
        drawRasterClocks(t);
        ctx.restore();
      }
      if (onFootage.length) {   // on the footage itself: full strength, after everything else
        const hf = { ...helpers, footage: true, vis: () => 1 };
        ctx.save(); ctx.scale(S, S);
        for (const p of onFootage) for (const e of activeAt(wx, t)) if (e.type === p.type) p.draw(e, t, hf);
        ctx.restore();
      }
    },
```
Note `live` for a footage beat: Hybrid shifts map layers under footage (`shiftedEvent`), but a `footage_credit` event's own window is
the footage beat, so it is live exactly while its footage plays. A golden test: render a red `media_full` + a `footage_credit` and
check the chip's panel pixels at `creditRect`.

### R4 — footage sources (`weather/footage.py`) and YouTube downloads
Approved NASA/Commons clips reach `beats.csv` as local files (`kind == "file"`, already allowed). Two additions:
```python
# weather/footage.py
def footage_problems(plan, project_root=None):
    ...
    approved = set()
    if project_root is not None:
        from .news.approval import ClipStore
        approved = {c.local_path for c in ClipStore(project_root).approved() if c.local_path}
        clips_dir = str(ClipStore(project_root).media_dir)
    for ... asset ...:
        kind = _kind(asset)
        if kind == "file" and project_root is not None and str(asset).startswith(clips_dir) and asset not in approved:
            out.append(f"beats.csv beat {b.id}: {what} {asset!r}: this event clip is not approved (weather/clips.json)")
        if kind == "youtube":   # youtube:<video id>, only an approved clip
            vid = str(asset).split(":", 1)[1]
            if f"youtube:{vid}" not in {c.id for c in ClipStore(project_root).approved()}:
                out.append(f"beats.csv beat {b.id}: {what} {asset!r}: YouTube clips must be approved first (weather/clips.json)")
            continue
```
and, in `weather/generate.py` before `generate_hybrid_video`, fetch approved YouTube clips with the app's code and swap the asset for
the file:
```python
from providers.youtube.ytdlp_backend import YtDlpBackend
from providers.youtube.base import VideoCandidate
from .news.approval import ClipStore
store = ClipStore(project.root)
for c in store.approved():
    if c.source == "youtube" and not c.local_path:
        dest = store.media_dir / f"youtube_{c.source_id}_{int(c.start_s)}_{int(c.dur_s)}.mp4"
        YtDlpBackend().download_segment(VideoCandidate(c.source_id, c.page_url, c.title, c.author), c.start_s, c.dur_s or 8, dest, log)
        store.set_local(c.id, dest)
# then clip assets "youtube:<id>" -> the stored local_path when building the plan
```
Also pass `project.root` to `footage_problems(plan, project.root)`.

### R5 — warning colours (`weather/alerts.py`)
Add to `ALERT_COLORS` (NWS map colours) so every Weather layer uses them: `"Extreme Wind Warning": "#FF8C00", "Special Marine Warning": "#FFA500", "Snow Squall Warning": "#C71585"`.
`weather/news/iem_warnings.EXTRA_COLORS` falls back to the same values until then.

### R6 — `noaa_mapservices` (bbox pictures) in `weather-engine/render.mjs`
To draw the federal live radar, the tile server could turn a `{bbox}` template into a per-tile URL (pakMap's `tileUrl` is not edited):
```js
// render.mjs, tile handler, before fetchTile
const merc = (z, x, y) => { const n = 2 ** z, R = 20037508.342789244, s = (2 * R) / n;
  return [-R + x * s, R - (y + 1) * s, -R + (x + 1) * s, R - y * s].join(','); };
const p = provider.urlTemplate.includes('{bbox}')
  ? { ...provider, urlTemplate: provider.urlTemplate.replace('{bbox}', merc(+tile[2], +tile[3], +tile[4])).replace('{time_ms}', provider.time_ms || '') }
  : provider;
buf = await fetchTile(p, tile[2], tile[3], tile[4], spec.cache_dir);
```
then `radar_providers.PROVIDERS["noaa_mapservices"].xyz` can become True and its frames carry `time_ms`.

### R7 — be gentle with IEM (`weather-engine/render.mjs`)
`radar_source_terms.md` proposes at most 4 parallel requests to IEM. MapLibre asks for many tiles at once; a small limiter in the
tile handler for radar providers:
```js
let iemActive = 0; const iemQueue = [];
const iemSlot = () => new Promise((r) => { if (iemActive < 4) { iemActive++; r(); } else iemQueue.push(r); });
const iemDone = () => { const n = iemQueue.shift(); if (n) n(); else iemActive--; };
// around fetchTile:
const limited = /^wx_radar_/.test(tile[1]);
if (limited) await iemSlot();
try { buf = await fetchTile(...); } finally { if (limited) iemDone(); }
```

### R8 — `python -m weather fetch` for news projects (`weather/cli.py`)
`fetch` already works for news-only projects (no NWS request is made unless an NWS row exists; `--contact https://example.invalid`
was enough). Two small changes would help:
```python
f.add_argument("--contact", default="", help="... (needed only when the plan has NWS rows)")
# NwsClient is built only when a row needs it: in generate.fetch
client = client or (NwsClient(contact) if contact else None)
# and print what the news layers fetched
for k, v in snap.extra.items():
    print(f"  {k.split('@')[0]} {k}: {v.get('issued') or v.get('fetched', '')}")
```

### R9 — clip approval in the app (Weather card)
An "Event footage" panel on a News project: event name, dates, places (→ `footage_pool.Event`), YouTube video IDs field; **Search**
(`footage_pool.search` → `ClipStore.save_pool`); a table of clips with source, title, date, licence, credit, status and reasons;
**Approve / Reject** (`ClipStore.decide`, with start and length in seconds), **Preview** (open `page_url`), **Download**
(`approval.download` for NASA/Commons; YouTube through R4), and **Use in beat …** which writes `clip_rows` into `beats.csv` and
`credit_rows` into `weather_layers.csv`. Rejected-by-licence rows show the reason and no Approve button.

## E2E
(filled below)
