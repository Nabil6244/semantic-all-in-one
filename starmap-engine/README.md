# StarMap engine

An astronomical renderer for space documentaries: the real sky, real positions and rotations, a camera that flies from
a landing site to the edge of the galaxy, generic graphics layers, and full-screen footage between map scenes. three.js in
headless Chromium (Playwright from `../flow-engine`), frame by frame to ffmpeg. StarMap shares no code with the other
renderers.

```
node render.mjs samples/apollo11-phase3.json out.mp4      # a video
STARMAP_STILLS="3,12.5,40" node render.mjs spec.json out.mp4   # just those moments, as JPEGs
STARMAP_GL=software node render.mjs spec.json out.mp4      # no graphics card (SwiftShader), the slow worst case
npm test
```

## A spec

| block | what it is | where |
|---|---|---|
| `width height fps duration` | the video | |
| `clock` | narration seconds -> universe date (`keys`), `met_zero` for the mission clock | `lib/clock.mjs` |
| `world` | bodies as data: parent, radius, offset (`ephemeris`, `galactic`, `orbit`...), `rotation: "iau"`, textures | `lib/world.mjs` |
| `camera` | `start` shot and timed `moves` (target, distance or fill, az/el, light, orbit) | `lib/camera.mjs` |
| `layers` | everything drawn over the universe, by generic type (below) | `lib/layers.mjs`, `layers/` |
| `footage` | full-screen clips and photos between map scenes | `lib/footage.mjs`, `cutter.mjs` |
| `watermark` | `{"text": "My Channel"}`, the channel name (PakMap's setting) | `layers/channel_name.mjs` |
| `media_dir` | where photos, clips and models are (default `media/` next to the spec) | |

Every time in a spec is **narration seconds**. A spec without `layers` gets the Phase 1 look (labels, distance, clock,
title).

## Layers

World (attached to something in space): `body_labels`, `marker`, `region`, `orbit`, `trajectory`, `spacecraft`,
`atmosphere`. Screen: `title`, `stat_chip`, `mission_clock`, `distance`, `photo_card`, `caption`, `channel_name`.
Each module's header documents its fields. Every layer takes `start`, `end`, `fade_in`, `fade_out`, `opacity`, `z`, and
`over_footage` (stay on screen over footage; `channel_name` does by default).

A new layer type is one module `{ type, space, create(def, ctx), update?(inst, frame), draw?(inst, frame) }` registered in
`layers/index.mjs`. The renderer names no mission, craft or place (a test enforces it): Apollo 11 and the Mars test
mission are content in `samples/`.

**Trajectories** are time-stamped samples relative to a body (`km` inertial, or `lla` on the turning surface). Real flight
data replaces the illustrated `generate` blocks (`orbit_arc`, `surface_track`, `transfer`) without renderer changes.
Illustrated paths say so (`"source": "illustrated"`).

## Footage

```json
"footage": [ { "id": "launch", "file": "launch.mp4", "start": 12, "end": 20, "in_s": 3, "credit": "NASA" },
             { "id": "flag", "image": "as11-40-5875.jpg", "start": 40, "end": 46, "ken_burns": { "to": [0.5, 0.4, 1.12] } } ]
```

As in Hybrid Map: map time stops while footage is up and carries on after it (the universe clock, camera moves and drift,
layer animations), so nothing jumps; layer starts/ends stay in narration time (an end under footage is held until the map
returns + 0.8 s; a start under footage waits for the map). Transitions are 0.5 s dissolves centred on the boundary (or
`"cut"`); footage after footage dissolves over the previous clip. Beats under 2 s, overlaps, missing files and unknown
types stop the render; short beats and keys/moves under footage are warnings. Clips are cut to frames just before their
beat and deleted after it; frames fully under footage skip the 3D render.
