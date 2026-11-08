# War Documentary: front-line maps and the 20-30 minute engine (plan, 2026-11-08)

## 1. What already exists (audit)

`cinematic_explainer/war/` is a complete, isolated style (~15k lines):

| Area | Module | State |
|---|---|---|
| Narration semantics | `semantics.py` | entities, numbers, quotes, citations, motion "from A to B", **territorial verbs** (captured, retook, withdrew...), claims/disputes, dated clauses |
| Planner | `planner.py` | footage first, then evidence > attributed figure > statistic > equipment > institution > territory/map > timeline > comparison; every choice logged |
| Direction pass | `direction.py` | 16 rules on top (tactical map, stamps, big numbers, chapters only when the narration says "Chapter N", speakers, icons, no-empty-stretch, graphic floor, CSV graphic column) |
| Map stretches | `map_build.py` | one political map that builds with the narration across footage-less runs |
| Maps | `maps.py` (`map_card`, `map_inset`), `maps_tactical.py` (`tac_map`, `tac_route`), `map_fx.py`, `geo_data.py` | deterministic PIL on the app's Natural Earth data; camera push/pan per named place, routes (advance/retreat/strike), glyphs, oblast highlights, flags, locator, scale bar, label placer |
| Control data | `maps.py control_snapshots`, planner `config["snapshots"]` | **a hook with no data**: validated (date + source), never filled by anything; the direction pass upgrades plain maps to `tac_map`, which had no control layer at all |
| Cards / layouts | `cards.py`, `cards_kit.py`, `cards_motion.py`, `layouts.py` | figure hero/pair, equipment hero/compare, stat split, timeline, claim, inset, logistics, big number, versus, recap, stamps, badges |
| Assets | `catalog.py` + `data/` (equipment, figures, institutions, places, portraits, equipment images), `portraits.py`, `equipment_images.py`, `footage_discovery.py`, `footage_match.py` | offline catalogue; footage matched to narration with rejections logged |
| Honesty | `provenance.py`, `registry.py` | licence/author per asset, credits file, "rights not established" list |
| Render | `segments.py`, `integration.py`, `app_section.py` | bounded-memory segmented renderer with cache; app section + scenes CSV |

Gap: no source of territorial-control data, and no way to draw it on the map the pipeline actually uses (`tac_map`).

## 2. Data sources

| Source | What | Licence / terms | Verdict |
|---|---|---|---|
| UK MoD Defence Intelligence updates | dated situation maps (images) | Open Government Licence v3.0, commercial reuse with attribution | **Best clean licence.** Images only: polygons must be traced by hand per date (a derived work is allowed under OGL). Sparse dates. |
| Wikimedia Commons "Russo-Ukrainian War" maps (Viewsridge et al.) | SVG control maps, frequent revisions with history | CC BY-SA 4.0 | **Usable** with attribution + share-alike on the derived data. Community-made from ISW and other sources: mark as "assessed (Wikipedia contributors, after ISW)". |
| ISW / Critical Threats | daily assessed control layers (ArcGIS) | copyrighted; no open licence found | **Only with written permission.** Most authoritative; ask ISW. |
| DeepStateMap | daily layers, history API | own licence: visual content may be reused with a credit/link; API commercial use needs prior approval; no redistribution of the API | **Use only with their approval** for API data; Ukrainian-sourced (label it so). |
| Natural Earth | borders, oblasts (already in the app) | public domain | base map (in use) |
| Copernicus Sentinel-2 / NASA Landsat | satellite imagery | Copernicus open licence (credit "contains modified Copernicus Sentinel data"); NASA public domain | for the satellite-imagery cards (stage 4) |
| kremlin.ru / president.gov.ua | leader photos | CC BY 4.0 (site-wide notices) | for the leader library (stage 4) |
| DVIDS | equipment photos/video | US public domain (most) | equipment library (stage 4) |

Rule: the app ships **no** front-line data. Snapshots are added by the user (per-user folder) with their own source, licence and date; anything without all three is rejected.

## 3. Front-line renderer (stage 1, built)

`cinematic_explainer/war/frontline.py`, drawn by `maps_tactical._render` when `params["frontline"]` is set.

- Snapshot file `war.frontline/1` (JSON or .json.gz): `as_of`, `source`, `licence`, `status` (assessed / claimed / disputed), `side`, `areas`, optional `source_url`, `claimant`, `test_data`.
- `import_geojson(...)` converts a GeoJSON export, provenance passed explicitly (never read from the file), simplified (Douglas-Peucker).
- Drawing: controlled area tint clipped to Ukraine's recognised borders (Crimea included); the **contact line** is computed as the rim of the area where it meets the other side's land (no line along the coast or the state border); glow + dark halo + bright core. Claimed / disputed areas are hatched with a dashed edge.
- Compare mode: the old line stays as a dashed ghost, gains sweep outward from the held area, losses roll back toward it, then each change is measured from the data (km², 0.01° area-weighted raster) and labelled "RUSSIAN GAINS ~N KM²" / "UKRAINIAN GAINS ~N KM²".
- Always on screen: badge "SOURCED CONTROL MAP · NOT LIVE", a data stamp (what, as-of date or date-to-date, source; amber "MAY HAVE CHANGED SINCE" when stale; amber "TEST DATA" + watermark for synthetic files), and the source + licence in the corner line and the credits file.

## 4. Integration with the War engine

`direction.apply` ends with `frontline.attach(plan, rows, cfg)` (config `frontline`, default on):
- only tactical maps the pipeline already chose (never adds a map, never moves one);
- the sentence must be about territory (front line, control, captured, advanced, withdrew ...);
- dates come from the narration (ISO, "12 March 2024", "late September 2022", "in 2023"); a date carries to the next 3 sentences ("Within days ...");
- two dates -> compare; one period + a change verb -> before/after compare; one date -> the snapshot for it;
- the snapshot must be within `max_gap_days` (45) of the date, so an old line is never shown as a later date;
- no date -> a line only if the sentence speaks of now ("today", "currently"...): the latest snapshot with its own date, and "may have changed since" when older than `stale_days` (14);
- undated history ("Russian forces captured the town.") gets no line (logged in `stats.direction.frontline.skipped`);
- every attached map gets `dir:frontline` in the scene log; sources go to the credits.

Config keys: `frontline` (bool), `frontline_snapshots` (inline list), `frontline_dirs`, `stale_days`, `max_gap_days`, `reference_date`.

## 5. Testing without slowing every video

- With no snapshots (the default) `attach` returns at once and no map changes: existing renders are pixel-identical (the renderer's new branch runs only when `params["frontline"]` exists).
- `test_war_frontline.py` (15 tests, ~2 s) uses synthetic `test_data` snapshots only.
- Cost: ~0.09 s per frame extra, only on frames of maps that carry a front line (numpy dilation instead of PIL rank filters; masks cached per camera view).
- Sample: `out/frontline_samples/frontline_compare_TESTDATA.mp4` (8 s, synthetic, watermarked).

## 6. Next stages (not built)

2. **Front-line timeline sequence**: one map stepping through several snapshots across a chapter (date ticker, line morph per step), map_build stretches that carry the line, oblast/salient focus with camera moves to the changed area, key-town status chips from the data (inside / outside the area as of date).
3. **Strategic locations layer**: curated, sourced points (bridges, dams, plants, ports, airbases) in `data/`, each with source + date; strike rings only when the narration names them.
4. **Graphics library**: leaders (CC BY 4.0 official portraits into the existing portraits pipeline), equipment (DVIDS PD), satellite before/after cards (Sentinel-2/Landsat with crop, date and credit), document screenshot cards with highlight boxes, evidence highlight (circle/zoom on footage), animated statistic and timeline cards from the existing kit.
5. **30-minute structure**: chapters only where the narration opens one; a pacing pass that balances footage / maps / graphics per 3-minute window and caps YouTube fetches to the scenes footage actually wins (no bulk downloads); one long render test on a real script.

## 7. Direction change (2026-11-08) and stage 2 (built)

Source of truth = script / CSV / narration. The engine represents what the script states; it does not verify battlefield claims.
Sourced snapshot data (frontline.py) stays as an optional, replaceable layer.

| Built | Module | What it does |
|---|---|---|
| Script-driven control events | `map_events.py` | "In February 2024, Russian forces captured Avdiivka" -> the town's zone sweeps from the previous holder's colour to the new one, advance arrow lands (withdrawal arrow for "withdrew from"), chip "RUSSIAN FORCES CAPTURED · FEBRUARY 2024" in the narration's words, camera pushes in close as the place is named. Unknown actor -> no event. Regions (oblasts) work too. Badge: ILLUSTRATIVE MAP · AS DESCRIBED IN THE NARRATION. |
| Strategic locations | `data/strategic.json`, `map_events.sites_in` | 21 sites (nuclear plants, dams, bridges, naval/air bases, ports, refinery, Azovstal, Snake Island, Hostomel) with typed diamond markers + pictograms + type tag; resolve before the nearby town. |
| Front-line sequence | `frontline.py` mode "sequence" | a map that stays up across several dated sentences steps through their snapshots as each date is spoken: big date ticker, step dots, dashed ghost of the previous line, gains/losses measured on the last step; ticker leaves 3 s after the history is told. |
| Map-to-map continuity | `map_events.continuity`, `maps_tactical` `enter_from` | consecutive maps (<= 9 s apart, similar scale and area) travel on from the last frame instead of a new establishing shot. |
| Graphics library | `graphics_lib.py` | `lay_satellite` (before/after slider, dates, focus box, credit), `lay_document` (screenshot or typeset narration words on a desk, marker highlight, outlet/date/quote side panel), `kit_chart` (bars / percent / line / donut from the script's own labelled figures), `kit_flyover` (drone / missile / jet crossing the frame with trail and label). |
| Wiring | `direction.py`, `app_section.py`, `integration.py`, `war_csv_prompt.txt` | CSV graphic names chart / article / flyover / satellite (+ optional `images` column before|after); auto: 3+ labelled figures -> chart instead of one big number; a cited report -> document page (one per 30 s); captures/sites/continuity on every tactical map. |

Samples (synthetic data, watermarked): out/frontline_samples/ — capture_avdiivka.mp4, frontline_sequence_TESTDATA.mp4, war_stage2_demo.mp4
(the real War pipeline end to end), gfx_*.png.

Still open: footage-first balance and pacing pass for 20-30 min (a footage-less run still becomes one long map_build map, by design of the
existing reference study), leader portrait/footage library, animated equipment beyond pictograms, real snapshot data import.
