# Health Cinema render performance (measured 2026-10-31)

All numbers come from the real heart-attack project (`heart-attack-scenes-v3.csv`, its voiceover, the clips its Visuals tab holds).
Settings and machine are the same for every run: 1280x720 preview, 24 fps, same visual quality, Apple M2 / 16 GB. The video runs 489.7 s.
"Old" is commit `c65022f`, run from its own checkout. Harness: `hc_bench.py`, which attaches timers from outside, so the old code runs unchanged.

## Result

| Run | Wall time | x real time | 3D scenes | Cache hits | Peak RAM |
|---|---|---|---|---|---|
| Old, cold | 594 s | 1.21 | 24 (22 the same heart journey) | 0 / 109 | 1.1 GB |
| Old, warm | 6.1 s | 0.01 | 24 | 108 / 109 | 0.4 GB |
| New engine, old plan, cold (render speed alone) | 182 s | 0.37 | 25 | 0 / 109 | 4.0 GB |
| **New engine + new plan, cold** | **136 s** | **0.28** | **18 (8 different scenes)** | 0 / 119 | 3.7 GB |
| New engine + new plan, warm | 5.0 s | 0.01 | 18 | 119 / 119 | 0.1 GB |

- Cold render: about 4.4x faster (594 s to 136 s). The rendering changes alone account for 3.3x (594 s to 182 s, same plan).
- An earlier cold run of the old code took 982 s, while other work and a nearly full disk competed with it. The 594 s run had the same
  conditions as the new runs, so it is the baseline here.
- Warm render (no input changed) is about 5-6 s for both. Every scene comes from its cached clip.
- Peak RAM is higher because two browsers and four encoders run at the same time. It is well inside 16 GB. `HEALTH_CINEMA_3D_WORKERS` and
  `HEALTH_CINEMA_CPU_WORKERS` lower it.

## Where the old time went (old, cold, per stage)

| Stage | Duration | Calls |
|---|---|---|
| CSV parsing | 0.01 s | 1 |
| Semantic planning | 0.05-0.14 s | 1 (0 Gemini calls: a CSV run never calls Gemini) |
| Visuals table (asset resolution) | 0.13 s | 1 |
| 3D: camera path sampling | 20-35 s | 24 |
| 3D: browser frames | 152-218 s | 24 (a new Node + Chromium each time) |
| 3D: labels + encode | 328-552 s | 24 (a full-frame layer composited on every frame, the font reloaded every frame, a second PNG written per frame) |
| Footage clips | 60-106 s | 56 (one after another) |
| Cards | about 10 s | 29 |
| Join + voiceover mux | 5 s | 2 |

3D took about 88% of the render, at about 5 s of work per second of 3D on screen. Planning and Gemini were never the cost.

## What changed

1. **Plan once, globally** (`planner.py`). A CSV row that asks for 3D of a broad organ ("heart") but describes a process gets that process's scene:
   cholesterol and atherosclerosis get plaque, platelets get the clot scene, blood flow, cells. Skin scenes never stand in for an artery. One 3D
   scene appears at most `MAX_SAME_3D` (3) times per video and never twice in a row. Extra uses become the blood-flow scene where it fits, else
   footage searched with the row's own words. The plan is deterministic, so Generate scenes and Render plan the same video. The heart journey went
   from 22 uses to 3.
2. **Asset index** (`asset_index.py`). Model, anchors and illustration-library files are read once while they are unchanged (size + mtime).
   Template readiness persists in `~/.semantic_yt_studio/health_cinema/asset_index.json`; a changed file is re-checked on its next use. A warm
   plan reads 0 files. Planning: 1.09 s to 0.33 s.
3. **Camera path once per clip** (`journey.camera_path`). Each camera key's fitting search ran on every frame. It now runs once per clip
   (sampling: 20-35 s to 0.2-0.6 s). The frames are identical (tested).
4. **Labels without full-frame layers** (`overlay.py`). Labels and cards are drawn straight onto the frame, and a frame with no labels is left
   alone. Fonts load once per size. Captions are drawn once and pasted from a cached crop (6.2 ms to 0.3 ms per frame, identical pixels).
5. **Frames piped to ffmpeg** (`overlay.run`). Frames are drawn on 4 threads and piped to ffmpeg while it encodes; there is no second PNG per
   frame on disk. This halves the temporary disk use of a 3D scene.
6. **One browser for many clips** (`threejs/render_worker.mjs`, `render_journey.pooled_frames`). A small pool of workers keeps Chromium open
   between clips (each clip still gets a fresh page). The engine closes the pool when the render ends; cancel kills the worker and its browser.
7. **Bounded parallel scheduler** (`engine.render_scenes`). 3D scenes run in a pool of 2 (GPU); footage and cards run in a pool of half the
   cores, at most 4 (CPU). Both run at the same time and the scene order is kept. Identical 3D clips are made once (a per-clip lock). Puppet
   scenes stay serial.
8. **Stage timings in every report** (`timings` in `<video>.health_cinema.json`). Planning, footage, scenes (by kind), join, mux, total,
   x real time, cache-hit rate and worker counts.

Also fixed on the way:
- `cond:` templates now load on the classic render path; every condition scene used to fall back to a text card.
- A video placed in an illustration-card row is skipped, not fatal. Render no longer files a video as a card picture.
- Card prompts name the organ, not the template id.

## Visual intent (CSV)

- New optional CSV columns: `visual_subject`, `visual_intent`, `biological_process`, `visual_action`. `shot` may now be a described
  perspective (internal_cross_section ...). An unknown shot is kept as `shot_desc` and is never an error.
- The subject and process choose the 3D scene before the organ.
- Rows merge only while the same subject and process continue.
- A scene that already showed one process is never reused, with only another camera, for a different one; that row gets footage instead.
- Checked once when the CSV is read (`scenes_csv.intent_notes`): runs of organ-only 3D rows, a 3D subject with no intent or action, and one
  subject used for different processes are logged as notes.
- The copied CSV prompt teaches the rules, the wrong/correct examples and the final validation. Old CSVs load and plan as before.

## Not done / limits

- **Footage in the benchmark:** the new plan sends 16 extra rows to footage. This benchmark used the project's existing Visuals tab, so those
  rows had no clip and showed text cards. In real use, Generate scenes fetches them first.
- **Worker counts:** 2 / 4 were chosen from the M2's core count and checked by these runs. A sweep over other worker counts was not run.
- **Frame transfer:** frames still leave the browser as PNG. A raw-pixel path could save more browser time, but was not measured, so it was
  not built.
- **GPU use:** not measured; macOS gives no per-process GPU figure without extra tools.
- **Card overlaps:** CSV cards are still placed on the right and can cover a label. One cell scene has two labels overlapping.
- **Final quality:** final (1920x1080) renders use the same code path. Only preview was benchmarked here; a final cold render takes about
  2.25x the pixels per frame.
