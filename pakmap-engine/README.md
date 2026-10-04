# pakmap-engine (Phase 1 camera spike)

Renders one continuous, top-down geographic camera as an MP4. Part of the pakMap niche (see `docs/pakmap/`). Separate process from `map-engine/` (Map Facts) and `flow-engine/`; nothing outside this folder imports it yet.

    node render.mjs <spec.json>        # progress as JSON lines on stdout
    npm test                           # unit + integration tests (node --test)

- `lib/camera.mjs`: the camera. `start` + `moves` (`fly_to`, `push_in`, `pull_back`) + always-on `drift`. Pure, deterministic, shared by the page and the tests.
- `lib/imagery.mjs`: replaceable imagery providers and **scale-based** layer selection. No source is tied to a place name; a provider only declares its native resolution. Settings (`max_upsample`, `crossfade_octaves`, `soft_limit_frame_km`, `grade`) live in the spec's `imagery` block.
- `lib/tiles.mjs`: tile fetch with an on-disk cache (`cache_dir`), 404s remembered.
- `lib/plan.mjs`: pre-flight pass over the camera path: which imagery is used, the narrowest frame, soft-imagery warnings, required credits.
- `samples/spike-60s.json`: the 60 s Phase 1 test flight.

Output: `<output>.mp4` plus `<output>.mp4.pakmap.json` (credits that must go in the video description or end card, warnings, imagery used). Landsat WELD is year-2000 imagery and is reported as historical.

Shot imagery is NASA GIBS only for now; verify each layer's exact terms and attribution before distribution (see `docs/pakmap/phase0/phase0-report.md`).

## Fixed: globe zoom-out
Zooming OUT into the globe range used to show rippled bands along the globe's edge. Cause: the globe leaves the sky around it transparent, and the 2D compositing canvas (`out` in `page.js`) kept the previous frame, so on a zoom-out (a smaller globe each frame) the earlier, larger globes showed through the gap. Zooming in hid it because each new globe covers the old one; a single still has no earlier frame. Fix: the canvas is filled with the space colour before each frame is drawn. Regression test: `test/render.integration.test.mjs` ("zooming out into the globe leaves clean space"). `samples/globe-outro-repro.json` is now a clean zoom-out. The eight workarounds tried earlier (tile reload, projection reset, double render, cache size 0, 512 px tiles, nearest resampling, warm-up frame, back-to-front) were all aimed at the map and could not have worked.

## Imagery selection (scale-based)
Each provider declares its native resolution only. A layer is stretched on screen by `native m/px / shot m/px`; when that exceeds `imagery.max_upsample` (default 2) the next finer provider fades in over `imagery.crossfade_octaves`. Nothing is keyed to "country" or "close-up". With the current two NASA layers this means Landsat starts to appear once a frame is narrower than about 590 km and is fully in below about 300 km; raise `max_upsample` to keep Blue Marble longer (blurrier), lower it to hand over sooner. `soft_limit_frame_km` (25) only produces a warning in the sidecar.

## Overlays (Phase 2)
The spec's `events` array draws the pakMap layers on top of the map: `hud_title`, `stat`, `caption`, `marker`, `line`, `dots`, `cluster` (plus an optional `watermark`). See `samples/overlays-kenya.json`. Timing, geometry and colours live in `lib/style.mjs`; drawing in `lib/draw.mjs`; everything else (`format`, `anim`, `layout`, `events`, `geom`, `points`) is pure and unit tested. The timeline is validated before rendering (max 2 stat chips and 5 text layers at once, one HUD title at a time; silence over 5 s is a warning). Font: Montserrat (OFL), `assets/fonts/`.

Channel name: set `"watermark": {"text": "MY CHANNEL", "position": "br" | "bl", "opacity": 0.6}` in the spec. The text is upper-cased and drawn with a small play-triangle; it is off when no text is given. The references use the bottom right; `bl` puts it bottom left. In the app this becomes a plain "Channel name" setting.

## Data layers (Phase 3)
`value_overlay`, `dots` (with `data`), `ghost_shape`, `streak`; see `samples/data-layers-kenya.json`. Data is named `bundled:<id>` (`rainfall_chirps`, `populated_places`, in `data/`) or `file:<path>` (GeoTIFF in EPSG:4326, ESRI ASCII grid, `lon,lat,value` CSV; `lat,lon` CSV for dots). Missing data or data that does not cover the region is a clear error. Rebuild the bundled data with `python3 tools/build_datasets.py`. Facts you may want to quote (areas, data ranges, dot counts) are in the render's `plan` event and the sidecar under `layer_facts`; dataset credits are added to the sidecar automatically.

## Rich media (Phase 4)
`pip` (photo card, optional `images` crossfade, `label`, `leader`), `filmstrip` (3-7 cards), `sticker` (PNG with transparency on a map point), `media_full` (picture or clip covering the frame; the map holds still under it), and `"dot": false` markers as zone labels. `media` paths are relative to the spec file (or `base_dir`); pictures are .png .jpg .jpeg .webp .gif .bmp, clips .mp4 .mov .m4v .webm .mkv (cut into frames up front). See `samples/rich-media-kenya.json` (placeholders from `tools/make_demo_media.py`). A sticker and a photo card never share the screen; a camera move cannot run under an interlude.
