# Phase 1 report: camera spike

Code: `pakmap-engine/` (new, separate from `map-engine/`, `flow-engine/` and everything else). Nothing outside it was changed for Phase 1. Tests: `cd pakmap-engine && npm test` (29 pass).

Preview: `spike60-preview.mp4` (960x540 copy of the 1920x1080 render) and `spike60-frames.jpg` (ten frames).

## What was built
- **Camera** (`lib/camera.mjs`): one top-down camera for the whole video. `fly_to` (van Wijk curved pan+zoom), `push_in`, `pull_back`, plus always-on idle drift. Deterministic, browser-safe, shared by the renderer page and the tests.
- **Imagery providers** (`lib/imagery.mjs`): replaceable provider records and scale-based layer selection. A provider only declares its native resolution; nothing is keyed to "country" or "close-up". Settings (`max_upsample`, `crossfade_octaves`, `soft_limit_frame_km`, `grade`) are configuration. Two NASA providers are registered: Blue Marble + Bathymetry (base) and Landsat WELD year 2000 (flagged historical).
- **Tile cache** (`lib/tiles.mjs`), **pre-flight plan** (`lib/plan.mjs`: imagery used, narrowest frame, soft warnings, credits), **renderer** (`render.mjs`, `page.js`: one MapLibre instance, frame by frame, tiles awaited, ffmpeg pipe).
- **Output sidecar** `<video>.mp4.pakmap.json`: the NASA acknowledgement text, the "historical, not current" note when Landsat is used, licence status per provider, warnings.

## Results on the 60 s test flight (1920x1080, 30 fps, 1800 frames)
| Check | Result |
|---|---|
| Hard cuts (ffmpeg scene detect at 0.08 and 0.2) | **0** |
| Single-frame pops | **0** |
| Camera reaches every target | yes (Caucasus, Bering Strait land where aimed) |
| Globe to flat blend on zoom-in | clean |
| Same spec renders identical frames twice | yes (integration test) |
| Translucent Russia fill + white borders | working |
| Imagery handover | Blue Marble to Landsat crossfade, no pop |
| Narrowest frame | 21.7 km; one soft-imagery warning (Landsat stretched about 2.5x, 34.9-37.5 s) |

## Defects found and fixed during the spike
1. **Drift dragged the camera off target.** Drift accumulated in world units, so by the time the camera zoomed in it was about 20 degrees off every target (the "Caucasus" shot showed Uzbekistan). Fixed: drift picked up before a move is carried into it and fades out over the move. The new test fails on the old logic (1,250 px off) and passes now.
2. **A move could start at full speed** (pull_back used an ease-out), which reads as a snap. All move types now start gently; a test checks the speed does not jump at move starts.
3. **Phase 0 look-test mislabel.** The "about 20 km local frame" comparison was really about 290 km wide; corrected in the Phase 0 report. Landsat's close-zoom quality is now measured for real (below).

## Globe zoom-out defect: FIXED (Phase 8)
**Root cause and fix:** the 2D compositing canvas kept the previous frame and the globe leaves its sky transparent, so a zoom-out showed the earlier, larger globes through the gap. It is now cleared each frame (see `pakmap-engine/README.md`). The text below is the original Phase 1 finding, kept for the record; the "workarounds" listed there targeted the map and could not have worked.

### Original finding
Zooming OUT into the globe range shows rippled, smeared tiles along the globe horizon (MapLibre 6.11.2); a still at the same camera, or zooming IN, is clean. Repro: `pakmap-engine/samples/globe-outro-repro.json`. Eight workarounds tried and ruled out (listed in `pakmap-engine/README.md`). The sample's final pull-back therefore stops at zoom 3.4. The spec's outro ("pull back to the globe") needs this solved: likely a separate globe-only map instance or our own globe pass. Not blocking the camera and overlay work in Phase 2.

## Imagery findings (real, rendered)
- Blue Marble + Bathymetry carries globe and continental shots well and gives the ocean seafloor look.
- At a 22 km frame (the narrowest shot) Landsat WELD is **soft and washed out** (frame 5 of the sheet): usable as a V1 fallback, as decided, but clearly weaker than the reference. Frames of 70 km and wider look acceptable.
- With the default `max_upsample` of 2, Landsat starts to appear below about a 590 km frame and is fully in below about 300 km. So Landsat covers a wide middle range (around 300 to 70 km), not only "close-ups". If you prefer Blue Marble to carry more of that range at the cost of blur, raise `max_upsample` in the spec; this is a one-number change.
- Landsat black no-data holes are keyed out to transparent so the base shows through.

## Not done in Phase 1 (by design)
Chips, markers, line draws, PiP, data layers (Phase 2 and later); Python-side `pakmap/` package and app integration (Phase 5 and 6); ocean teal grade (an optional lighten tint exists but is off, it also tinted dark land and the space behind the globe).

## Licensing notes carried forward
NASA GIBS acknowledgement text travels in the sidecar. Exact commercial terms for each GIBS layer are still to be verified before distribution (Phase 0 finding). EOX is not used.
