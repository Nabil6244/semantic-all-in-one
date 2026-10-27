# War Documentary style: performance plan (bounded memory, segmented render, graphics cache)

Status: design plus measurements. No existing file and nothing in `cinematic_explainer/` was changed. All experiments ran from a scratch copy (`scratchpad/agent_c/`: `ce_copy/`, `seg_render.py`, `run.py`). Machine: this Mac, 8 cores, 16 GB, ffmpeg 8.1.2. Footage: the repo's `Images/*.mp4`. **Measured** = taken with `/usr/bin/time -l` (maximum resident set size of the largest process, which is ffmpeg) in this session. **Estimated** = my reasoning, not run.

## 1. Cause of the Phase 1 memory growth (confirmed by experiment)

Phase 1 builds one ffmpeg graph for the whole video: `concat` of all shots, then `split`, then one trimmed, blurred copy of the footage per dim span, each laid over the clear footage with `overlay`.

| Experiment (same renderer, 1280x720, x264) | Peak RSS | Verdict |
|---|---|---|
| Demo, 25.4 s, with dim spans (the Phase 1 number) | **2.46 GB** measured (2.3 GB earlier) | reproduces |
| Same demo, dim spans switched off (no `split`, no dim overlays) | **0.58 GB** measured | the dim branch is the cause, not decoding, concat, the pipe or Python |
| Clean footage 15 s then one dim card (gap before the first dim span) | **1.04 GB** | memory follows the clean stretch before a dim span |
| the same with 30 s clean | **1.92 GB** | |
| the same with 60 s clean | **2.76 GB** | |
| Synthetic timeline with a card about every 5 s: 50 s / 75 s / 180 s | 2.39 / 2.52 / **3.00 GB** | looks flat only because gaps are short; still grows slowly |

Mechanism (inferred from these results, not from reading ffmpeg's source): each `overlay` waits for its dimmed branch to deliver its first frame (that branch starts at the span's own start) while the clear footage keeps arriving, so every clear frame before the first dim frame queues in memory. A 1280x720 yuv420p frame is 1.38 MB, 25 per second, so one clean minute is about 2 GB if nothing is dropped. Several chained overlays queue separately. **Consequence:** a long documentary with one long quiet stretch before a card (the style wants quiet stretches) can use many GB; a 14-minute video is not safe in this design. This also means the earlier worry "memory grows with video length" is really "memory grows with the longest clean gap".

## 2. Bounded-memory, segment-compatible design (built and measured)

**Design.** One ffmpeg process per **segment**, a segment being one shot (one footage clip between two hard cuts). Inside a segment the dim plate is made from a **second decode of the same clip** (a second `-i` of the same file with the same `-ss`), not from `split`, so no branch ever waits on another; each dim span in the segment adds one more input of the same file. Cards are still drawn in Python with **global** time `t` and piped as RGBA, so a card frame is the same pixels whichever segment draws it. Segments are encoded with x264, closed GOP (`-g 50 -keyint_min 50 -sc_threshold 0`), a fixed `-video_track_timescale 12800`, exactly `round(duration x 25)` frames, then joined with the concat demuxer and `-c copy` (no re-encode). The prototype is `agent_c/seg_render.py` (about 70 lines).

| Run (segmented prototype) | Peak RSS | Wall time | Video length | Notes |
|---|---:|---:|---:|---|
| Demo, 25.4 s | **0.59 GB** measured | 7.4 s | 25.4 s | monolithic was 2.46 GB / 7.8 s |
| Clean 60 s, then a dim card | **0.52 GB** measured | 9.2 s | 60 s | monolithic: 2.76 GB |
| Synthetic 3 min (36 shots) | **0.61 GB** measured | 51 s | 180 s | monolithic: 3.00 GB / 59 s |
| Synthetic 10 min (120 shots) | **0.62 GB** measured | 166 s | 600 s | monolithic not run at 10 min (would be at least 3 GB, unsafe to test) |

Memory is flat from 25 s to 10 min (0.59 to 0.62 GB), speed is about 3.5x real time on 8 cores (about 15,000 frames in 166 s) and the 3-minute segmented render is as fast as the monolithic one. Peak is per process: with the app's resource governor allowing *w* concurrent ffmpeg workers, expect about *w* x 0.6 GB **(estimated, not run)**.

**Equivalence to the Phase 1 renderer (measured, with lossless FFV1 output so the encoder is not a factor):** same frame count (635 = 25.4 s) and same duration. **Not bit-identical:** all 635 frames differ; mean PSNR 46.4 dB, clean frames about 54-56 dB, worst 38.4 dB (35 frames below 45 dB, the lowest at the first frame after a cut with a dim ramp, 4.64 s, and 10.2 to 10.4 s). 38 to 46 dB is not visible to the eye but it means **a frame-hash baseline cannot be shared between the two renderers**; the segmented renderer would get its own hashes. I did not isolate the cause (candidates: the monolithic graph converts yuv420p to an alpha format and back for its pass-through overlays; a one-frame offset in the fade ramp). In the plan the monolithic renderer is retired once the segmented one is accepted, so this matters only for the Phase 1 demo's saved scorecard.

**Cuts, keyframes, audio sync (measured on the x264 demo):**
- every segment join (4.6, 10.4, 15.2, 20.6 s) lands on a keyframe, plus one every 2 s; the monolithic file had 6 keyframes in the whole 25 s. `-c copy` joins therefore cut cleanly.
- total frames 635 in both; no dropped or duplicated frame at joins.
- video-only (`-an`). Voiceover and music are mixed by the app's existing mixer and attached at final export, as for every other style, so the segmented video does not change audio sync as long as every segment is a whole number of frames. **Rule:** the planner must round shot boundaries to frames (`round(t x 25)`); the prototype would drift by one frame per segment otherwise.
- a dim ramp that would start before the cut is clipped at the cut in this prototype (the style already starts dimmed at the first frame of a card shot); the planner should put dim spans inside shots (ramp start >= shot start), which the demo already does.

## 3. How a segment plugs into the existing app, without changing shared behaviour

Read from `video_generator.py`, `render_cache.py`, `scene_graph/render.py`, `test_render_segmented.py`, `test_render_cache.py`, `docs/pakmap_render_segment_reuse.md`:

- **Normal/Overscaled/Exp Solar path** (`video_generator.render_video`): each scene becomes one clip via `_render_scene_clip`, encoded by up to `_scene_render_workers()` threads (governor budget, 1 to 4), cached per project in `<project>/state/render_cache.json` and `state/render_cache/clips/scene_<n>_<key16>.mp4` by `RenderCache.get(scene_key, cache_key)` / `put(...)` (schema version 3), then clips are joined. `build_scene_cache_key` hashes the source file identity, timing, overlay PNGs by content, edit decision and encoder args; any doubt is a miss.
- **Overscaled/Exp Solar scene-graph renderer** (`scene_graph/render.py`): already splits one video into bounded ffmpeg processes (`_MAX_SEGMENT_INPUTS = 96`, `_MAX_SEGMENT_ARGV_CHARS = 28000`, because a 10-minute project in one process hit the 4,096 threads limit and a 478 KB command line) and joins them, tested frame-exact against single pass (`test_render_segmented.py`).
- **pakMap/Hybrid** cuts at about 30 s pieces keyed by their own layers and joins without re-encoding (`.pakmap_segments/`, `engine_runner.py`).

The Cinematic Explainer segment is the same idea as a "scene clip", so the plan reuses these pieces and **adds only new files**:
1. `cinematic_explainer/segments.py` (new): `plan_segments(shots, layers)` (one per shot; very long shots are cut at keyframe-safe 10 s pieces with a card never straddling a cut), `render_segment(...)` (the prototype's `render_segment`), `segment_key(...)`.
2. Caching uses the **existing `RenderCache` class unchanged**: `RenderCache(state_dir).get("ce_<index>", key)` and `.put(...)`; only the *key function* is new (the existing `build_scene_cache_key` has no slot for cards). `render_cache.py` is not edited. The key reuses its helpers `_content_identity` (private, so copy 10 lines rather than import).
3. The join (`concat -c copy`) is a new 6-line function in the new module; it does not touch `video_generator`'s joins.
4. Hook into the app only through the optional look-pack switch (Phase 2 design, the Doc Style extension point the research recommends); that hook is the single edit in an existing file (`app.py`, additions only) and needs approval; protected manifests must be re-checked before it (see the test plan).

**Segment cache key (sha256 of canonical JSON):** pack version string; `look.py` constants hash (colours, timings, brightness, shrink); canvas size and fps; encoder args; the shot's clip **content identity** (size, mtime, and a hash of the first 16 MB as `_content_identity` does), `seek`, frame count; for every layer overlapping the segment: `kind`, start/end rounded to the frame, the **canonical hash of its params**, and for portraits the **content hash of the portrait file** (never the PIL object); the dim spans. Changing one card changes only its segment's key, so one edit re-renders about 5 s of video. Wrong-portrait reuse is prevented because the key contains the portrait file's content hash, so two people never share an entry.

## 4. Graphics: do not regenerate per frame

**Measured** card draw cost in the prototype (Pillow, 1280x720): source 4.3 ms, number 1.0, list 2.0, portrait 3.7, kicker 0.2, shot headline 0.7 per frame; converting an RGBA frame to bytes and compositing costs 5.6 ms. At 25 fps (40 ms budget) the drawing is already cheap; the risk is only scale (15,000 frames for 10 min). Cards are also **static most of the time**: number/portrait/kicker/headline produce **1 distinct frame** over a settled 0.8 s window, the source card 13 (words darkening), the list 9 (rows appearing).

Proposal, in order of value, all inside the new package:
1. **State key per frame, reuse the last bytes.** A card exposes `state(t, dur, params)` returning a small tuple of the quantities that change the picture (fade level, counted number, number of words darkened, rule length); if the tuple equals the previous frame's, the previous frame's bytes are written again without redrawing or compositing. Estimated saving: more than 80 % of card frames (static holds), about 5 ms each. Not built, the numbers above are the evidence.
2. **Static layer + parametric animation:** draw the settled card once into an RGBA PNG (what `graphics/doc_style.py` already does for Doc Style cards, with the fade done by the pipeline) and animate only alpha, slide and the few moving parts; cache the PNG in `<project>/state/ce_layers/<key16>.png` under the same key rules as above. Needed for the more expensive Phase 2 cards (map callouts, diagrams, portraits with cutouts).
3. **Shared blank frame** (already in the prototype) and a single reused `bytes` object for repeated blanks.
4. **Portrait cut-out and resize cached by (file content hash, size)**; today the prototype resizes every frame during the 0.3 s entrance (1 ms-class, but a 4 K source photo would be slower).
5. Expensive effects (blur plate) stay inside ffmpeg (already the case: the plate is scale-down/scale-up, no per-frame Python).

## 5. Bounded-memory budgets to enforce (proposed numbers)

| Limit | Value | Why |
|---|---|---|
| Peak RSS of any single ffmpeg process | **<= 1.0 GB** (measured 0.62 GB at 10 min, +60 % margin) | enforced by test |
| Concurrent segment processes | the governor's `recommend_ffmpeg_workers()` (1 to 4) | existing budget, not a new one |
| Inputs per segment process | 1 + number of dim spans in the segment, hard cap 8, else split the shot | stays far under `_MAX_SEGMENT_INPUTS` |
| Segment length | a shot, or 10 s pieces for longer shots | keeps GOPs short and re-renders small |
| Python peak | < 300 MB (not measured separately; the child maximum above is ffmpeg) | **to measure** |
| Temp disk | segments deleted after join; the work folder removed on failure (as `test_render_segmented` requires) | existing convention |

## 6. Risks that remain
- Segmented x264 uses a separate rate control per segment: tiny bitrate steps at joins are possible (**not measured**; visual check needed on a real 10-minute project).
- Frame-accurate footage cuts need `-ss` placement and a source with a keyframe near the seek point; all fixtures were fine, long-GOP 4K sources are **not tested**.
- Output is silent; the real audio join (voiceover words shifting a shot start) is untested.
- Not tested: 4K, 30/60 fps projects, Windows (path quoting in the concat list uses `file '<path>'`; the app's `ffmpeg_concat_path_text` handles Windows, the prototype does not).
