# Weather — integration contract for phases 2–5 (parallel work)

Several people/agents build at once in ONE checkout. Nothing is committed. The rules below keep the work from colliding and keep the
existing app unchanged. Read `weather_style_plan.md`, `phase1_proposal.md` and `phase1a_report.md` first.

## 0. Hard rules (everyone)
1. **Edit only the files you own** (§5). Everything else is read-only. If you need a change in a file you do not own, write it as a
   request in your report (§7); the integrator makes it.
2. **Never edit existing app code**: `app.py`, `VideoGenerator.spec`, `pakmap/`, `pakmap-engine/`, `hybrid/`, `starmap/`, `starmap-engine/`,
   `map-engine/`, `map_scene/`, `providers/`, `flow-engine/`, `composition_styles/`, `project_workspace.py`, `app_csv_prompts.py`,
   `asset_manager.py`, `video_generator.py`, or any file listed in `test_fixtures/weather_protected.json` or
   `test_fixtures/enoch_template_protected.json`. You may IMPORT from them. `test_weather_isolation.py` must stay green.
3. **No git commits, no git state changes** (no add/commit/stash/checkout/branch). No installing software, no system settings, no OS
   schedules installed on this machine.
4. **Downloads**: only public data the feature needs (NWS, NOAA, NASA, IEM, USGS, RCC-ACIS, SPC, NHC, WPC) and small recorded copies of
   real responses as test fixtures (public domain). No icon packs, no fonts, no third-party libraries, no YouTube downloads in tests.
5. **Python: standard library only** (plus what the app already has: numpy is available). **Node: no new npm packages.**
6. **Truth**: every number on screen comes from data and is added to the numbers report (`out.report.add(...)`) with its source URL and
   issue/valid time. Preliminary data (SPC storm reports, USGS provisional values, NWS observations) is labelled "preliminary" on screen.
   Never generated (Flow/AI) footage. Stock b-roll is never presented as a real event.
7. **Tests**: no network in tests (record real responses into fixtures). Use `.venv310/bin/python` (Python 3.13). Run your own tests plus
   `test_weather_isolation.py` and `cd weather-engine && node --test test/*.test.mjs` before you report.
8. Code reads like the code around it: same comment density, names, plain-English messages that name the row/layer.

## 1. Python layer types (`weather/layers/`)
A new layer type is one module in `weather/layers/` that calls `register(LayerType(...))` at import (see `weather/layers/__init__.py`).
The sidecar, the resolver and the event builder find it automatically.

```python
from weather.layers import LayerType, register, Raster, Frame

def fetch(row, ctx):          # ctx.snap (Snapshot), ctx.now, ctx.nws (NwsClient or None), ctx.get_text(url), ctx.get_bytes(url)
    key = f"radar:{row.data_source.target}"
    if key not in ctx.snap.extra:              # fetch each product once
        ctx.snap.extra[key] = {...}            # JSON-serialisable; namespaced by your prefix
def build(row, snap, window, out):            # window.t_in / window.t_out (narration seconds)
    out.events.append({"id": f"wx_{row.id}", "type": "my_graphic", "t_in": window.t_in, "t_out": window.t_out, ...})
    out.fills.append({...pakMap fill event...})          # areas (MultiPolygon in "polys")
    out.rasters.append(Raster(...).to_dict())            # timed tile loops
    out.report.add(row.id, "label", "shown text", Sourced(...))   # EVERY number shown
    out.credit("Radar: NOAA NEXRAD via Iowa Environmental Mesonet")
    out.shown[row.id] = [{"kind": "text", "text": "Radar: NOAA/NWS via IEM, 4:35 PM CDT"}]  # what source lines name
register(LayerType(name="radar", products=[("iem", "radar")], extra_keys=frozenset({"opacity"}), fetch=fetch, build=build))
```
- `data_source` grammar: `provider:product@target#selector`, e.g. `iem:radar@2024-05-06T21:00Z..2024-05-07T03:00Z#n0q`,
  `nhc:cone@AL092022#030`, `spc:reports@2024-05-06`, `acis:pcpn_total@Houston,TX#2017-08-25..2017-08-30`,
  `usgs:stage@08074000#2017-08-25..2017-09-02`, `gibs:truecolor@2017-08-24`. Your `check(row)` validates your own targets/selectors
  and raises `ValueError` with a plain message (the sidecar adds the row number).
- Freshness: only "now" products (forecasts, observations, live alerts, live radar) have a `fresh(snap, now)` rule. Archive products of a
  past event do not go stale.
- Times on screen: `weather.tz.clock(utc, "America/Chicago")` (no zoneinfo; Windows has no tz database).
- Places: cities via `weather.cities.find_city("Houston, TX")`; areas via the bundled shapes (`weather.alerts.county_shapes()`, the US states
  in `map_scene/data/admin1.json.gz`); point locations as lon/lat.
- Provenance: `weather.provenance.Sourced(value, unit, product, url, where, issued, fetched)`.

## 2. Engine graphics plugins (`weather-engine/lib/layers/*.mjs`)
One file per graphic type, found automatically (the page imports `/weather-engine/plugins.mjs`, which lists the folder):
```js
export default {
  type: 'storm_counter',
  order: 60,                      // < 50: drawn under the temperature markers; >= 50: over the strip and cards
  validate(e) { return e.value ? [] : ['storm_counter needs value']; },   // strings; the engine names the event
  draw(e, t, h) {                 // 1920x1080 reference units (h.S already applied); t = narration seconds
    const a = h.lifeAlpha(t, e.t_in, e.t_out, h.TIMING.chipIn, h.TIMING.chipOut) * h.vis(); if (a <= 0) return;
    const { ctx } = h; ctx.save(); ctx.globalAlpha = a; h.panel(x, y, w, h_, 14); h.text('42', x, y, 48, h.COLORS.white, 'left', 800); ctx.restore();
  },
};
```
Helpers `h`: `ctx, project(lon,lat)->{x,y}|null (frame px; divide by h.S for reference units), measure(text,px,weight), text(str,x,y,px,color,align,weight,spacing),
panel(x,y,w,h,r[,fill]), titleChip(x,y,h,px,label), roundRect, font, drawIcon(ctx,kind,cx,cy,size), S, W, H, FRAME, WX (layout constants),
COLORS, TIMING, clamp01, easeOut, lifeAlpha, vis() (1 - footage cover: multiply every alpha by it), placed() (chip rects already drawn this frame)`.
Every `*.mjs` in `weather-engine/lib/layers/` is loaded as a plugin, so put shared pure maths (testable without a canvas) in
`weather-engine/lib/wxu_<area>_<name>.mjs` (you own the `wxu_<area>_*` files you create; `<area>` = auto, news or post).

## 3. Timed tile loops (radar, satellite loops)
`out.rasters.append(Raster(id, t_in, t_out, frames=[Frame(at, provider, label)], opacity, crossfade_s, above_fills, clock).to_dict())`.
- `provider = {"id": "<unique per picture time>", "title", "urlTemplate": ".../{z}/{x}/{y}.png", "format": "png", "tileSize": 256, "maxNativeZoom": 8}`.
  The tile cache is keyed by `id`: an id must change whenever the picture changes (put the time in it). `{z}/{x}/{y}` are XYZ (Google)
  tile numbers; for TMS services that number y from the south, put the right template (IEM's `/cache/tile.py/1.0.0/<layer>/{z}/{x}/{y}.png`
  is XYZ-compatible, as phase 0 showed).
- `at` = seconds into the layer; frames in order. `label` (e.g. "RADAR · 4:35 PM CDT") shows in a chip when `clock` is true.
- Radar: `above_fills=True` (over warning areas). Satellite pictures: `above_fills=False`.
- A missing tile shows the base map (never stops the render); a transparent tile is fine.

## 4. Footage
Full-screen footage is Hybrid's footage beats in `beats.csv` (`row=clip`, `asset=stock_video:<description>` or a file path). The app's
providers fetch it; the Visual Plan table lists it. `weather/footage.py` decides which sources a Weather video may use. Event footage
(phase 3) adds sources there — through the integrator (it is a shared file); the source code for fetching lives in your own module.

## 5. Ownership
| Owner | May create / edit |
|---|---|
| **Integrator** (lead) | everything under `weather/` and `weather-engine/` not listed below; `weather/app_section.py`, `weather/sidecar.py`, `weather/resolve.py`, `weather/events.py`, `weather/footage.py`, `weather/generate.py`, `weather/cli.py`, `weather-engine/page.js`, `render.mjs`, `lib/wx_*.mjs`; `app.py`/`VideoGenerator.spec` (additive only, approved list); docs reports; `test_weather_app.py`, `test_weather_isolation.py`, `test_fixtures/weather_protected.json` |
| **Phase 2 — automation** | `weather/automation/**`, `weather/layers/trend.py`, `weather-engine/lib/layers/temp_trend.mjs`, `weather-engine/lib/wxu_auto_*.mjs`, `weather/data/metros.json` (new), `weather/testdata/automation/**`, `test_weather_auto_*.py`, `weather-engine/test/auto_*.test.mjs`, `docs/weather/agent_phase2.md` |
| **Phase 3 — news** | `weather/news/**`, `weather/layers/radar.py`, `weather/layers/storms.py` (NHC), `weather/layers/severe.py` (SPC/WPC, archived warnings), `weather/layers/counters.py`, `weather-engine/lib/layers/storm_*.mjs`, `weather-engine/lib/layers/counter.mjs`, `weather-engine/lib/layers/radar_legend.mjs`, `weather-engine/lib/wxu_news_*.mjs`, `weather/testdata/news/**`, `test_weather_news_*.py`, `weather-engine/test/news_*.test.mjs`, `docs/weather/agent_phase3.md` |
| **Phase 4 — post-event** | `weather/post/**`, `weather/layers/totals.py` (ACIS), `weather/layers/rivers.py` (USGS), `weather/layers/rainmap.py` (MRMS), `weather/layers/beforeafter.py` (NASA daily), `weather/layers/timeline.py`, `weather-engine/lib/layers/post_*.mjs`, `weather-engine/lib/wxu_post_*.mjs`, `weather/testdata/post/**`, `test_weather_post_*.py`, `weather-engine/test/post_*.test.mjs`, `docs/weather/agent_phase4.md` |

## 6. Done means
- Unit tests for every module (recorded fixtures, no network), every error message names its row/layer.
- At least one engine render test for each new graphic (offline is fine: `imagery_enabled: false`; tile loops need network, so test their
  maths in a unit test and render them once for real in your report).
- A sample `weather_layers.csv` snippet in your report for each new type, and a frame (PNG) of each graphic from a real render.
- `test_weather_isolation.py`, all `test_weather_*.py`, and `weather-engine` tests green.

## 7. Your report (`docs/weather/agent_phaseN.md`)
Files created; how to use each type (sidecar rows); tests and results (paste the counts); frames rendered; known limits; and
**requests for the integrator** (changes needed in files you do not own, with the exact code you propose).
