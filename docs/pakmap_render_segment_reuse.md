# pakMap / Hybrid Map: re-rendering only what changed (future optimization)

Status: analysis only (2026-10-08). Nothing described here is implemented; current behaviour is unchanged.

## Current behaviour

```text
CSV / Hybrid plan + Visual Plan table
      ↓
fetch pictures and clips      ← reused: every scene whose manifest record is complete (incl. user replacements)
      ↓
compile → pakmap_spec.json    ← cheap, deterministic
      ↓
draw the map, every frame     ← ALWAYS the whole video (the slow part)
      ↓
sound mix                     ← seconds (streaming mixer)
      ↓
final export                  ← re-encodes the whole video with the mixed audio
```

Changing one picture or clip costs no credits (nothing else is fetched; Flow is used only for scenes without a finished
file and the app asks first), but the map renderer redraws every frame. The missing capability is **rendered-segment
reuse**, not asset caching.

Goal: *reuse completed rendered work whenever the inputs for that time range have not changed.*

```text
scene 37 changes → the time range(s) where its file is on screen → redraw only those segments
                 → reuse the other segments → join → mix → export
```

## Findings

### 1. How pakMap determines "scene" boundaries
pakMap has no scenes in the video sense: the map is one continuous shot. A Visual Plan "scene" is a picture or clip named
in the script (`stock_image:…`, `flow_image:…`, …). `pakmap.sourcing.find_occurrences` maps each scene number to its
occurrences `(script line, part)`; `generate_pakmap_video` swaps the fetched file into those occurrences (`media_map`), and
`pakmap.compile.compile_csv` turns each into an event (`pip`, `filmstrip`, `media_full`, `sticker`) with exact `t_in` / `t_out`
taken from the narration word timings. A scene can appear in more than one event.

### 2. How Hybrid determines them
Hybrid beats (MAP / FOOTAGE / MAP+FOOTAGE) carry explicit times in the plan. `hybrid.compile` turns each footage clip into a
`media_full` event whose slot `(a, b)` comes from the plan (`_clip_spans`), never from the clip file. Footage straight after
footage starts one dissolve earlier (`xfade_prev`), inside the new clip's own slot. Hybrid then renders through the same
pakMap generator (`hybrid.generate.generate_hybrid_video` → `generate_pakmap_video`). With `dedupe`, one fetched file can serve
several events.

### 3. Mapping to a timeline
pakMap and Hybrid do **not** use `EditorialTimeline` (that is the Normal / Overscaled / Exp Solar pipeline). Their timeline is
the compiled spec, written to `<work>/pakmap_spec.json` on every run: `duration`, `fps`, `width`, `height`, `pixel_scale`, the
camera moves, the imagery selection and every event with its `t_in` / `t_out` and resolved media path. That file already holds
everything needed to find the time range(s) a scene occupies: the union of the `[t_in, t_out]` of the events that use its
file, widened by the event's enter/exit animation (`lib/anim.mjs` `TIMING`, `lifeAlpha`) and its dissolves.

### 4. Can a time range be rendered on its own?
Yes. `pakmap-engine/render.mjs` calls `window.renderFrame(i / fps)` for each frame `i`, and every frame is a function of `t`
alone:
- the camera is `camera.at(t)`, computed from the start of the camera timeline each time (`lib/camera.mjs`);
- the map is positioned with `jumpTo`, MapLibre runs with `fadeDuration: 0`, and the frame waits until every tile is drawn;
- overlays are drawn by `overlay.draw(t)`; random-looking reveals use a seeded generator (`lib/anim.mjs` `rng`);
- the output canvas is cleared every frame;
- clip frames are picked by time (lazy clips are cut on first use and released after their last use).

So frames `f0..f1` of a separate render are the same images as frames `f0..f1` of the full render.

One exception to handle: tiles that fail to download are remembered for the rest of a render (`invalidTiles` in `page.js`)
and drawn from coarser imagery. A segment rendered later may download that tile successfully and look sharper. This happens
only on failed downloads, and the render log already counts them (`tiles` event).

### 5. Do transitions overlap neighbouring scenes?
Inside a picture's own window only: card enter/exit fades, Hybrid's clip dissolves (`dissolve_s`, `xfade_prev` starts the
new clip earlier, inside its slot), and Ken Burns (`kenburns: "auto"`, decided from the file type). A replaced clip's
*length* only changes its playback rate inside its slot (`fit: "slow"`, `loop`), never the slot. Layout does not depend on
the picture: cards use a fixed aspect (`lib/layout.mjs`); only a sticker uses its own image's aspect, for itself.
To be safe, a dirty range should be the event window plus its fades, rounded out to whole segments.

### 6. Does audio timing stay the same?
Yes, when only a file changes. Sound cues come from event times and types (`pakmap.audio_plan`), not from file contents, so
the sound plan is identical. The mix takes seconds and can simply be redone.

### 7. Does the camera depend on the previous / next scene?
The camera depends on the whole camera timeline (moves, drift) and on the footage windows (`freezeWindows`: the camera holds
still during `media_full` events), all of which are times, not files. Replacing a picture or clip changes none of them.
Editing the script or plan (text, timing, beats) changes the spec, and then everything after the first change must be
treated as dirty (or the whole video, which is today's behaviour).

### 8. Identical output at segment boundaries?
The frames are identical (point 4). The encoded files are not bit-identical to a single pass: x264 rate control and
lookahead differ at a segment's first frames. At `-crf 18` that is not visible, and the final export re-encodes anyway.

### 9. Joining without unnecessary re-encoding
`render.mjs` encodes one H.264 file (`libx264 -preset medium -crf 18 -pix_fmt yuv420p`, default GOP). Segments with the same
settings that each start on a keyframe can be joined with the ffmpeg concat demuxer and `-c copy` (no re-encode). The final
export (`scene_graph.app_integration._export_via_existing_renderer` → `video_generator.render_video`) re-encodes the whole
video with the audio regardless. That is a single ffmpeg pass, far cheaper than drawing the map, and could later become a
stream copy plus audio mux.

### 10. What can tell an unchanged segment?
Existing information:
- `pakmap_spec.json` (per run): every input of every frame except file contents. If the spec, the engine version and the
  output settings are unchanged, only changed files can make a segment dirty.
- The asset manifest (`Images/.asset_manifest.json`, `asset_manager._record_from_result`): per scene `local_path`,
  `resolved_at`, `source`, `provider_asset_id`, `user_override`. A replacement updates `resolved_at`, but no content hash is
  stored, and a replacement may keep the same file name.
- `pakmap_map.mp4` (the previous silent render) is kept in the work folder until the next run overwrites it.

Missing: a per-segment record of what it was drawn from, i.e. a fingerprint of (spec fields active in the range + content of
the files used in the range, by size+mtime or hash + engine version + resolution/fps/pixel scale), and segment files kept
between runs instead of one overwritten `pakmap_map.mp4`.

## Verdict

The existing structures are sufficient to implement this later without a dependency graph:
1. split the timeline into fixed segments (e.g. 30 s, frame-aligned);
2. per segment, fingerprint the spec content active in it plus the files it uses (from `pakmap_spec.json`);
3. redraw only segments whose fingerprint changed (`render.mjs` given a frame range), keep the rest;
4. join with the concat demuxer (`-c copy`), mix the audio, export as today.

The only new data needed is the per-segment fingerprint and keeping segment files between runs. Script or plan edits
that shift timing make every later segment dirty, which falls back to today's full render, so correctness never depends on
the cache being clever.

Risks to test when implementing: failed tile downloads (point 4), GPU/driver differences if segments are rendered on a
different Mac than the one that made the cached ones (fingerprint should include the machine), and lazy clip extraction
for a segment that starts in the middle of a clip.
