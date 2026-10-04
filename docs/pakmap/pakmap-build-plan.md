# pakMap build plan (v2, after Reference 2)

Plan only, no code. Companion to `pakmap-editing-spec.md`. v2 folds in Reference 2 (`2nd reference.mov`, Kenya).

## 1. Where pakMap goes

**Existing:** `map-engine/` renders one MP4 per map prompt (MapLibre in headless Chromium piped to ffmpeg). `scene_graph/map_nodes.py` uses those clips as full-screen nodes in Overscaled/Exp Solar. Overscaled and Exp Solar run `compile CSV -> resolve media -> retime to voiceover -> layout -> one fixed-canvas render -> EditorialTimeline -> render_video()` (see `scene_graph/app_integration.py`, `pipeline.py`).

**Decision: pakMap is a third, independent pipeline** with the same outer shape and its own CSV, compiler, engine and renderer. It is NOT an Overscaled style preset.
- Map Facts (`map_scene/`, `map-engine/`), Overscaled, Exp Solar, Flow and `render_video()` stay untouched.
- pakMap hands the exporter a plain `EditorialTimeline` (video track + voiceover), as `scene_graph/timeline.py` does.

**New pieces (proposed names):** `pakmap/` (CSV compiler, timeline model, voiceover anchoring, asset resolution, orchestrator), `pakmap-engine/` (Node renderer, own process and tile cache), `composition_styles/pakmap.json` (tokens and timing constants), a pakMap mode in `app.py`.

## 2. Decisions needed from you before Phase 1

1. **Imagery source (biggest gate) - DECIDED: free stack, see section 2a.** Current NASA tiles stop at zoom 8 (about 611 m/px). The free stack replaces them; a licensed key stays an optional later upgrade.
2. **Data layers (new from Reference 2) - DECIDED: bundled open datasets plus user files, see section 2b.**
3. **Sticker library - DECIDED: build the sticker layer, ship v1 without a library.** Reference 1 uses about 10 bespoke 3D stickers; Reference 2 uses none.
4. **Typeface - DECIDED: Montserrat ExtraBold** (open licence). Revisit only if you hold a licence for another face.
5. **Media interludes.** Reuse existing providers (Pexels, YouTube, local, Flow) so there is no new asset pipeline.

## 2b. Data layers: bundled open datasets plus user files

Used by `dot_density` and `value_overlay` (Phase 3). Same free-only rule as imagery; verify each licence in Phase 0.

| Need | Candidate open source | Notes |
|---|---|---|
| People / settlement dots | WorldPop or GHSL population grid | Licences are open with attribution; verify exact terms |
| Rainfall / climate colour layer | CHELSA climatologies or CHIRPS rainfall | Prefer these over WorldClim, whose terms limit commercial use |
| Boundaries and counties | Natural Earth, geoBoundaries | Already in the imagery stack |

How it works:
- **Bundled:** small, coarse versions ship inside the app so common topics work offline. Large full-resolution grids do NOT ship; they download on demand into the existing cache.
- **User files:** the user can point a CSV (lat/lon points, or place + value) or a raster (GeoTIFF) at a layer in the pakMap CSV. User data always wins over bundled data.
- **Missing data:** if neither exists for the region, the plan preview shows a clear error naming the layer and what to supply; the video does not silently drop it.
- **Credits:** each dataset's attribution goes to the video description or end-card, same as imagery.

## 2a. Imagery stack (free) - revised after the Phase 0 look test

Details and images: `phase0/phase0-report.md`.

| Layer | Source | Status |
|---|---|---|
| Global / country base + ocean | NASA GIBS Blue Marble **with Bathymetry** (z8) | Chosen. Closest to the reference at country scale; seafloor detail included |
| Region / close zoom | NASA GIBS **Landsat WELD** annual (30 m, z12) | Chosen. Usable, a little soft, 1998-2000-era imagery, no clouds |
| Sharper close zoom (optional) | EOX Sentinel-2 cloudless (10 m) | **Not cleared.** EOX's current terms need a commercial licence; an older post says CC BY-SA. Ask EOX before using. |
| Rejected | NASA MODIS/VIIRS daily true colour | Clouds and swath gaps |
| Borders / regions | Natural Earth (public domain), geoBoundaries (CC BY 4.0) | Chosen |
| Extra bathymetry (if needed) | GEBCO (public domain) | Optional |
| Globe view | MapLibre built-in globe projection | Free |
| Look | Colour grade in our renderer: darker mids, contrast, slight desaturation, teal ocean | Required |

Avoid: Google, Bing, Mapbox satellite, Esri World Imagery, GADM.
Known limits: Landsat is 1:1 only for frames about 73 km wide and is stretched about 2.9x at 25 km (estimate; measured in Phase 1). Reference 1's 5 km shot stays optional. Selection is by scale (see Phase 1 notes), never by a "country"/"close-up" label.
Delivery: tiles download on first use into the existing cache (not bundled). Credits (NASA GIBS acknowledgement text, geoBoundaries, dataset credits) go in the video description or end-card.

Phases: Phase 0 = done (look test + licence check); Phase 1 = tile sources, cache, grade; Phase 8 = optional licensed/EOX imagery setting.

## 3. Phases (S = days, M = 1-2 weeks, L = longer)

**Phase 0 - Lock the contract (S).**
- CSV schema and constants drafted: `phase0/csv-schema.md`, `phase0/pakmap.draft.json`.
- Measurements done (see report): `PART` chip, subtitle chip, word-by-word reveal rate, dot-density reveal, blue hex. Still unknown: exact typeface file, Reference 1 reveal style, exact dot count.
- Cut test fixtures (short clips + frames) from both references.
- **Imagery look test: DONE** (Kenya frame, five sources). **Licence check: DONE** with open items (EOX conflict, primary-source confirmation for WorldPop, GHSL, CHIRPS, CHELSA, and NASA commercial wording). See `phase0/phase0-report.md`.
- Done when: schema, constants and fixtures are agreed.

**Phase 1 - Engine spike: one continuous camera (M). STATUS: DONE; the globe zoom-out defect was fixed in Phase 8. See `phase1/phase1-report.md`.** Riskiest piece, so first.
- One long-lived map instance driven by a keyframe timeline (position, zoom, easing, duration).
- Moves: idle drift (0.4-0.9 % of frame width/s), fly-to, push-in, pull-back, globe for intro/outro and for bridge shots.
- Top-down only, no tilt or rotation. Deterministic frame-by-frame render, wait for tiles.
- Translucent fills, colour tokens, white borders, stylised ocean.
- **Imagery stack (section 2a):** new tile sources (GIBS + Sentinel-2 cloudless), local tile cache through the existing cache manager, bathymetry shading for the ocean, colour grade, and attribution text for the description/end-card. Replaces the maxzoom-8 NASA-only source.
- Done when: a 60 s clip shows a smooth continuous flight with no per-scene cuts.

**Phase 2 - Overlay vocabulary (L). STATUS: DONE (chips, markers, lines, dots, rules); see `phase2/phase2-report.md`.** All 2D drawing in one compositor pass.
- Authored HUD chips: top-left chip text and subtitle are free text (`NUMBER 14`, `PART 1`, anything); typewriter subtitle; watermark. **HUD may be absent (cold open) or start late.**
- Stat chips with ease-out number counters, four anchors plus bottom-centre over footage, two at once.
- Caption chip (text only) with an optional tiny source line (`MUNDAY ET AL. 2022`).
- Markers with typewriter label, value, sub-chip, colour roles, pulse ring.
- Line-draw engine: route, river, rail, border, divide, dashed reference line (can span oceans and link two distant markers), connector; head-first draw in 0.9 s, easing out.
- Point clusters (small) **and a dot-density layer** (thousands of dots from point data, staggered reveal).
- Text-measurement pass so chips size to content and never reflow while typing.
- Done when: golden-frame tests match measured geometry.

**Phase 3 - Data layers (M, new). STATUS: DONE; see `phase3/phase3-report.md`.**
- `value_overlay`: colour-ramp raster (rainfall-style) clipped to a region, with a counting chip and no legend.
- `dot_density`: point source (bundled population grid or user CSV) rasterised to dots, with a counter chip. Source and fallback rules per section 2b.
- `ghost_shape_compare`: move a country/region polygon onto another area at true scale, translucent, with an area chip.
- `streak_overlay`: decorative drawn streak family for "invisible force" beats.
- Done when: a Kenya-style slice (dots to 54 % region fill to rainfall layer) renders deterministically offline from bundled test data.

**Phase 4 - Rich media (M). STATUS: DONE; see `phase4/phase4-report.md`.**
- PiP card: snap-in (about 115 % scale and 40 % opacity settling in 0.15-0.20 s), 0.4-0.5 s fade out, white border and shadow, 2-image crossfade, map-anchored, optional yellow label chip.
- **Filmstrip PiP:** 3-7 small labelled cards along one edge, growing in sequence.
- Sticker layer (static PNG, map-anchored, on a base). One rich object at a time: PiP or sticker.
- Full-screen media dissolves of 0.4-0.6 s with HUD and any stat chip kept on top; the map returns with the same camera and overlay state.
- Video PiPs and b-roll are pre-extracted to frames for determinism.
- Open choice: composite dissolves inside the renderer (recommended) vs separate map and HUD layers joined in ffmpeg.

**Phase 5 - CSV compiler and narration timing (M). STATUS: DONE; see `phase5/phase5-report.md` and `csv-reference.md`.**
- One row per visual event, grouped by item; validation: one title per item (when the HUD is on), a clear row at boundaries, at most 2 stat chips and 5 text layers at once, monotonic times.
- Anchor events to narration phrases using Whisper word timestamps (the `WhisperWord` shape in `voiceover_sync.py`); fall back to proportional timing.
- Title chip lands about 0.14 s before the item's first word with a fixed 0.5 s clear beat (Reference 1; re-check on Reference 2).
- Place/polygon resolution reuses `places.py`, `ai_places.py`, `detect.py`; sub-region sets (counties) need an admin-boundary source.
- New row types for the Reference 2 layers (dot_density, value_overlay, ghost_shape, streak, filmstrip, caption).

**Phase 6 - App integration (M). STATUS: DONE (Flow/stock sourced pictures added in Phase 8; an installed-build check is still open); see `phase6/phase6-report.md`.**
- pakMap mode in `app.py`: CSV browse, plan preview, generate; reuse progress, cancel, resume, project workspace, Visual Plan table and per-scene Retry for PiP/b-roll assets.
- Data-layer picker (bundled dataset or user file), with the missing-data error from section 2b.
- **Channel name** setting (text, bottom right or bottom left): the watermark is already an engine option (`watermark.text`, `position`); the app only has to expose it and save it with the project.
- Hand off to `render_video()` as an `EditorialTimeline`.

**Phase 7 - Audio (S). STATUS: DONE (sound design, with two post-review fixes); see `phase7/phase7-report.md` and `sound-design.md`.**
- **Superseded in Phase 7** by the supplied competitor sound-design data: pakMap has its own quiet SFX + ambience system (see `sound-design.md`); the generic SFX, generic ambience and zoom-blur sounds stay off for pakMap. (Original note: the two reference videos measured as having no designed sound.)

**Phase 8 - Polish (M, ongoing). STATUS: NOT STARTED.**
- Carried over from earlier phases: ~~fix the globe zoom-out rendering artifact (Phase 1)~~ **DONE**: cleared the 2D canvas each frame; regression test added; the compiler's pull-back warning removed; ~~Flow/stock-sourced pictures for pakMap (Phase 6)~~ **DONE** (`stock_image:` / `flow_image:` ... in `asset_path`; now rows of the existing Visual Plan tab, see `phase8/sourcing.md`); check the installed (packaged) build (Phase 6).
- Optional "use my licensed imagery key" setting; collision-aware chip placement, leader lines, stacked/zone chips, polar-globe shot, sticker library, CSV-writing prompt like the Overscaled one, source-credit helpers.

## 4. Testing
- Unit tests on measured constants (chip sizes, 0.9 s draw, 0.5 s clear beat, drift range).
- Determinism: same spec gives identical frames.
- Constraint tests: concurrency caps, PiP/sticker exclusivity, HUD-optional cold open.
- Regression: existing suites pass unchanged; a test proves pakMap never imports or edits Map Facts, Overscaled or Exp Solar paths.
- Offline: imagery-off and data-fixture mode, no network, zero Flow credits.
- Acceptance: render a roughly 60 s slice of each reference topic and compare side by side.

## 5. Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Imagery quality and licence | NASA-only stack goes soft below about 25 km frame width and Landsat is year-2000 imagery; EOX licence unresolved | Cap deepest zoom; ask EOX; optional licensed/EOX imagery setting later |
| Data availability (dots, rainfall, admin boundaries) | Layers need real data per topic | Bundled coarse datasets, on-demand downloads, user files win; clear error when missing |
| Render time for 13-minute videos | Long renders | Tile cache, per-item segment cache, resume |
| Globe vs flat projection | Shapes differ slightly | MapLibre globe for intro/outro/bridge, flat otherwise |
| Stickers cannot come from a CSV row | Fewer 3D moments | Library later |
| Chip placement by eye | Occasional overlaps | Collision pass + Retry loop |
| Unmeasured details | Slightly off feel | Phase 0 measurement pass |

## 6. What changed from v1
- Added Phase 3 (data layers) and moved later phases down one.
- HUD text is authored, and the HUD can be absent or start late.
- Added caption chip with source line, filmstrip PiP, pulse ring, ocean-spanning reference line, globe bridge shot.
- Added decision 2 (data sources).
- Removed "no heatmaps" and "no mid-video globe" from the do-not-build list.
- Audio: Reference 2 is silent, so it adds no evidence; sound design stays "none".

## 7. First step
Phase 0, then the Phase 1 spike. If a continuous deterministic camera is not smooth on the current stack, nothing else holds.
