# Roblox Cinema Engine — final report (2026-11-04)

Nothing was committed or pushed. All engine work is inside `roblox-cinema-engine/`; outside it only the registration lines listed at the end.

## Delivered

| Step | State |
|---|---|
| `web/look.js` (10 light presets, sky dome, sun + shadow window, fog, blocky clouds, post: tone map/grade/vignette, dissolve/dip/cloud-wipe) | done |
| `web/hud.js`, `web/main.js`, `web/page.html` | done |
| `render.mjs` (server, GPU Chromium, Natural Earth crop per map scene, `--plan-only/--stills/--clip/--preview/--final`, perf + memory report, cue list) | done |
| Page run in headless GPU Chromium, bugs fixed | done (list below) |
| `tools/`: `make_vo.py`, `narration_timing.py`, `sfx_synth.py`, `mix_audio.py`, `qc_video.py` (+ `sheet.py`), `runner.py` | done |
| Tests | 23 Node tests + 9 Python tests, all passing |
| App integration | done (additions only) |
| D-Day 117 s demo at 720p and 1080p, stills inspected, performance measured | done |
| Docs: `README.md`, `docs/REFERENCE_ANALYSIS.md`, `docs/ARCHITECTURE.md`, this report | done |

## Measured (this Mac: Apple M2, headless Chromium, ANGLE Metal; one run each)

Film: `samples/dday_1944.csv`, 17 scenes, 117.02 s at 24 fps = 2,809 frames, timed to the placeholder voice-over.

| | 720p | 1080p |
|---|---|---|
| Render wall time (frames drawn + JPEG screenshot + x264) | **97.8 s** (35 ms/frame, ≈1.2× real time) | **119.9 s** (43 ms/frame) |
| Mean time in `renderFrame` (draw call issue, not GPU wait) | 3.3 ms | 3.7 ms |
| Mean screenshot (where the GPU wait lands) | 31.1 ms | 37.9 ms |
| Slowest frame / slowest scene build | 265 ms / 219 ms (scene builds, once per scene) | 266 ms / 231 ms |
| Peak draw calls / triangles per frame | 3,389 / 4.37 M | same |
| Peak live particles | 363 (cap tested < 700) | same |
| Browser-side JS heap | 29 MB, flat across the film | 33 MB, flat |
| Node process RSS | 170–285 MB, no growth trend | 170–245 MB |
| GPU resources held at the end | 1,063 geometries, 432 textures (shared caches; scenes two behind are freed) | same |
| File | 62 MB, H.264 + AAC | 125 MB |
| Final loudness (measured on the muxed file) | **−14.16 LUFS**, true peak **−1.49 dBTP**, LRA 3.5 | identical |
| QC (`qc_video.py`) | 0 unplanned jumps, 0 frozen runs, 0 black runs | same |

Not measured: GPU memory in MB (WebGL gives no number; only resource counts), other machines, Windows/Intel Macs, the hardware encoder.
**Estimates, not measurements:** a 10-minute film would take ≈8–10 min at 720p and ≈10–12 min at 1080p if frame cost stays like the demo's; crowds of
several hundred bodies or dense cities would cost more (the 70-actor city scene is the densest tested).
The renderer is single-browser; `--range` renders a frame range, so parts could run in parallel, but a parallel render was **not** built or tested.

## Bugs found by running it, and fixed

* HUD elements never showed (CSS `display:none` beat the inline `''`); map pin labels likewise.
* Instanced trees/hedges rendered near-black (instance colour multiplied the material colour twice).
* Night and dusk scenes were unreadably dark; night/dusk/overcast presets re-lit. Sea scenes were fogged to white (fog scaled for sea).
* Camera sat inside the transport planes in the night drop → camera now pushed out of every vehicle's bounding sphere, aircraft formations are framed from a distance.
* **Camera jump** in the beach battle (found by `qc_video.py` and the new camera test): the "front of the group" subject was an argmax that switched person from one frame to the next → now a soft-max that glides.
* A subtitle card with one orphan word ("streets.") → the last card never has fewer than 3 words.
* Map framing put the pins under the subtitles → focus shifted, labels decluttered and kept out of the subtitle band.
* A chapter card and a statistic box overlapped → the chapter card has the screen to itself.
* Audio: a cue placed at a negative time crashed the mix; short loops crashed the cross-fade; true peak overshot −1 dBTP in one test → limiter ahead of loudnorm.
* Animation blends lengthened from 0.3 to 0.4 s.

## Placeholders and known weaknesses (all of them)

* **The voice-over is a stand-in**: macOS `say` (Daniel), used only to give real word timing and a mix target. The real voice comes from the app's voice step.
* **Sound effects are procedural** (filtered noise, envelopes): gunfire, explosions, flak, ship guns, engines, marching, thunder, bells, clock, whooshes. Passable under a mix, not studio quality. The ambience beds are the app's bundled library.
* Night transport planes read as dark thin slabs (the model's wings are 0.5 studs thick and the formation overlaps); the night-drop opening is the weakest shot.
* Barbed-wire coils render as hollow wire cylinders; the sea's far edge shows a faint diagonal seam in some high shots.
* Snow weather has fog and grade only (no falling flakes). Cloud-wipe transitions go fully white for ~0.3 s by design.
* Maps are present-day borders with approximate positions (stated on screen); no historical borders. No insignia, no flags, no gore.
* Everyone's faces are a small set of decal expressions; lip movement is a two-state mouth flap while "talking", not synced to phonemes.
* `mix_audio.py` is launched with the app's Python (`sys.executable`); a frozen build would need that step moved in-process. The app section was import-checked and its registration tested, but **not clicked through in the running app UI**.
* The reference analysis came from vidIQ's automated video-watch tool, not from Claude watching frames (stated in `REFERENCE_ANALYSIS.md`).
* Not done: parallel rendering, hardware encoding, a Windows run.

## Outside `roblox-cinema-engine/` (the only edits)

* `ui/roblox_cinema_section.py` — new file.
* `app.py` — 22 added lines, 0 removed (import, `_active_style`, run-guard, style choice activate/deactivate, block grid toggle, cta dispatch, `_sync_primary_cta`, project restore, `_RUN_FLAGS`). `test_weather_isolation.py` / `test_enoch_template_phase0.py`: 21 pass; the 1 failure (`test_no_existing_module_imports_weather`) is caused by `product_trailer/news_footage.py` and `test_product_trailer_looks.py` (other, uncommitted work), not by these edits.
* `ui/style_registry.py` — 8 appended lines (style, group, blurb, card).
* `ui/style_kit.py` — **one existing line changed**: `"Roblox Cinema"` added to the tuple of styles that build their own steps (`wrap_style`). Not in any protected manifest.

## Outputs (in `out/`, untracked)

`dday_720p_final.mp4`, `dday_1080p_final.mp4`, their `.plan.json`/`.cues.json`/`.mix.json`, `qc/` contact sheets, `vo.wav` + `words.json` (placeholder voice and its word times).
