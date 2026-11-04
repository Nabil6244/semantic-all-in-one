# voxelmap-engine (experimental proof of concept)

A block-world history map renderer, built to test whether the "voxel war map" style (docs: Voxel War Map Bible) can be
made automatically. It is separate from every existing style: nothing outside this folder imports it, and it does not use
pakMap's 2D camera. Everything is generated from data and a story CSV; nothing is built by hand.

    python3 tools/build_world.py --id indochina --bbox 92,5,112,25 --res 0.025     # once per region (reusable asset)
    node render.mjs samples/indochina_1954_1965.csv --plan                          # timeline + warnings, no browser
    node render.mjs samples/indochina_1954_1965.csv --stills 2,20,45                # preview stills
    node render.mjs samples/indochina_1954_1965.csv --clip 5:31                     # a preview piece (not the full video)
    python3 tools/narration_timing.py vo.wav out/narration.json                     # follow a real voiceover:
    node render.mjs story.csv --narration out/narration.json --stills ...
    python3 tools/mix_audio.py vo.wav music.wav out/mix.wav                         # ducked, rising music bed
    npm test

## What is in it

| Part | File | How |
|---|---|---|
| World asset | `tools/build_world.py` | Terrarium elevation tiles (AWS Open Data, fetched once into `cache/`), the app's Natural Earth land and province shapes (`map_scene/data`). Writes `worlds/<id>/` (height, land mask, region ids, meta). The Indochina world is 800×800 blocks, 216 provinces, 5 MB of tiles |
| Block terrain | `lib/terrain_mesh.mjs`, `page.js` | Cells → block heights (420 m per step, ~6.6× vertical exaggeration), biome colours, chunk meshes of top faces plus walls (sea runs merged). A custom shader draws block edges, sun shading, fog and the territory tint |
| 3D camera | `lib/camera3d.mjs` | Height, pitch (follows altitude: top-down for maps, 58° on the ground), heading, orbit, drift. Moves rise in an arc for long hops; ground speed is proportional to altitude, so a move never jerks |
| Territory | `lib/territory.mjs` | Rules per province (country, latitude band) → a 256-entry tint texture; changes fade over 1.4 s |
| Sets and props | `lib/props.mjs` | Recipes: village, city, airfield, battle, beach_landing, jungle. Generated from a seed; smoke, fire, blasts and planes animate from t alone. Sets appear only when the camera is near (detail pop-in); the terrain sinks into a shallow bowl around them |
| Narration-aware timing | `lib/timeline.mjs` | Every move flies inside the silence before its beat's first sentence. With no voiceover the silences are planned from the move's length; with a real one (`--narration`) the moves fit its pauses, and a pause too short is reported |
| HUD | `lib/hud.mjs` | Date box with legend (steps through months on a time skip), caption log (two lines, older greyed, cleared in long silences), chapter cards in the silence before each chapter, progress bar with chapter ticks, place tags, letterbox on the ground |
| Story CSV | `lib/beats_csv.mjs` | Same row-type convention as Hybrid's beat CSV (`row` = plan / chapter / beat, extra JSON), with its own columns. Hybrid's parser is not reused: its rows carry Hybrid modes that mean nothing here |
| Audio | `tools/mix_audio.py` | Reuses `health_cinema.edit.audio.speech_duck` unchanged (−9 dB duck), adds a +6 dB build over the film |

## Phase 2: cinematic upgrade

    node render.mjs story.csv --prepare                    # plan + build the detail tiles the camera needs (once per story)
    node render.mjs story.csv --bench                      # high / mid / low altitude timings + one still per band
    node render.mjs story.csv --clip 0:146.4 --audio out/audio/mix.wav --narration out/audio/vo_timing.json   # preview with sound
    python3 tools/make_test_vo.py out/timeline.json ...    # a local test voiceover (macOS `say`) placed on the timeline
    python3 tools/mix_audio.py vo.wav music.opus mix.wav --stems out/audio/stems    # two-pass loudness
    python3 tools/audio_qc.py ...                           # loudness, peak, clarity, ducking, silences, sync

| Part | File | How |
|---|---|---|
| Terrain levels | `lib/lod.mjs`, `lib/world_data.mjs`, `tools/build_detail.py`, `page.js` | Level 0 = the world (2.8 km blocks, always drawn). Level 1 = 40×40-cell tiles at 700 m blocks (Terrarium zoom 9), within 50 cells of the camera. Level 2 = 10×10-cell tiles at 175 m blocks (zoom 10), within 12 cells. Only the tiles a story's camera reaches are built (`--prepare` samples the camera every 0.2 s). Raw tile data is loaded once; meshes are built on demand and kept in a 72-tile cache that never drops a tile the frame uses. A level fades in with a screen-door dither while its parent is cut away by the same dither, so there is no double drawing and no pop; tile edges carry skirts below sea level, so there are no cracks. Real elevation per level; Natural Earth coastlines rasterised at each level's resolution; rivers from D8 flow accumulation on the real elevation |
| Light | `lib/terrain_mesh.mjs` | Per-corner block occlusion, wall-foot darkening, and baked sun shadows (a march over the height field toward the sun), all per vertex: no shadow-map cost |
| Environments | `lib/props.mjs` | 10 recipes (village, city, airfield, lz, battle, fortress, beach_landing, jungle, trail, delta) and generic equipment (tank, APC, truck, jeep, howitzer, helicopter with spinning rotor, jet, cargo plane, landing craft, patrol boat, sampan, ship, bicycle). Sets sit on the real fine terrain and read it: no buildings on water or steep ground, paddies only on flat land near water, trees denser in forest, boats only on water; contact shadows. Seeded from the beat's own id, place and date, rotated per seed |
| Camera director | `lib/director.mjs`, `lib/camera3d.mjs` | Shots: establishing, pullback, aerial_track, orbit, low_track, flyover; moves between them: travel, descent, ascent, hop, reframe. Chosen from rung, set recipe, chapter position and the narration ("falls", "only beginning" → pullback); never the same shot twice in a row when another fits; `extra.shot` overrides, `extra.path` gives an aerial track. Collision: a 10 Hz clearance table from the finest terrain along the line of sight, smoothed 1.5 s ahead and behind, so the camera rises over a ridge early instead of being pushed |
| Finishing | `page.js` | Sky dome, distance haze with desaturation and valley haze, animated water (ripple normal, tight sun glint, sky reflection, shore band), territory tint faded out below 60 km (ground scenes keep natural colours), motion blur by sub-frame accumulation only when the camera moves (1–8 sub-frames, 180° shutter), one grade pass (S-curve, warm/cool split, vignette, dither) |
| Audio | `tools/mix_audio.py`, `tools/audio_qc.py`, `tools/make_test_vo.py` | Two-pass loudnorm with a gain correction if linear mode misses, alimiter only if needed; QC report with pass/fail thresholds; the app's `speech_duck` reused unchanged |

### Measured (Apple M2, ANGLE Metal; the 2:26 Indochina sample)

| | 720p | 1080p |
|---|---|---|
| Full preview, sequential, with audio | 4,392 frames in 101 s; 22 ms avg, 39 ms p95, 110 ms max | 4,392 frames in 174 s; 38 ms avg, 63 ms p95, 222 ms max |
| Motion-blur sub-frames (avg) | 3.2 | 3.5 |
| Bench, high altitude (8 frames, out of order) | 50 ms avg | 39 ms avg |
| Bench, mid altitude | 231 ms avg (6.3 sub-frames, cold tile meshes) | 152 ms avg |
| Bench, low altitude (15 L1 + 14 L2 tiles active) | 247 ms avg | 135 ms avg |
| GPU terrain memory (peak) | 199 MB | 199 MB |
| Chromium resident memory at the end | 680 MB | 398 MB |
| Node process peak resident | 641 MB | 670 MB |
| Detail tiles | 169 loaded for the story; 145 meshes built in the sequential render (1.5 s in total) | same |
| Jumps in the final 720p preview | none: largest frame change 0.155 at 107.9 s (a particle burst vanishing), a cut scores > 0.3 | — |
| Audio (muxed file) | −14.0 LUFS, −1.8 dBTP | −14.0 LUFS, −1.8 dBTP |
| Audio QC (mix) | clarity 17.7 dB (worst 11.7), ducking 7.8 dB, music in every silence (min −34.6 dBFS), no dead air; A/V streams both 146.4 s | |

Bench numbers render moments out of order, so tile meshes are often cold; the sequential preview is the production case.
Data downloaded for this story: 202 + 86 zoom-9 and 99 zoom-10 Terrarium tiles (30 MB, cached); 111 L1 + 97 L2 tile files built (26 MB).

## Phase 2b: fixes and the block-game look

| Change | Where | What |
|---|---|---|
| Wider world | `worlds/indochina` (84–124°E, 0–30°N, 1600×1200 blocks, 428 provinces) | The widest shots no longer reach the world's edge. The detail tiles were carried over (the origin moved by whole tiles; province numbers remapped by name), so nothing was rebuilt |
| Camera aim | `render.mjs` (groundTable), `page.js` | The camera aims at a smoothed ground height (patch average, eased over a second) instead of the raw block under its target, which stepped and made the frame jump (the 0.16 spike at 107.9 s) |
| Particle bursts | `lib/props.mjs`, `page.js` | Emitters are budgeted once per set by their worst case (none drops in or out because another is busy); cube particles shrink to nothing as they fade; blasts grow in over 0.1 s; parachutes open and collapse; fly-bys start and end far off the set |
| Tight pauses | `lib/timeline.mjs` | A move first gives up its margins, then may run up to 15% faster (reported as a note); only a move that still does not fit runs into the narration (a warning) |
| Block textures | `page.js` shader, `lib/terrain_mesh.mjs` | 16×16-texel faces drawn procedurally per material: grass with a ragged fringe over dirt, leaf canopies, sand, cracked stone, snow over stone, water. Texels fade out below a pixel. Set blocks get the same texel grain |
| HUD | `lib/hud.mjs`, `page.html` | Monocraft (SIL OFL 1.1, `assets/fonts/`) everywhere; beveled pixel panels; hard pixel shadows; chunky caption lines; a hotbar-style chapter timeline (one slot per chapter, the current one selected and filling) with time left |

Measured after Phase 2b (M2, the 2:26 sample with sound): 720p 4,392 frames in 114 s (25 ms avg, 45 ms p95, 131 ms max);
1080p in 198 s (43 / 72 / 181 ms); GPU terrain 289 MB; largest frame-to-frame change 0.042 (the reference's own maximum
is 0.064); muxed audio -14.0 LUFS, -1.8 dBTP; audio and video both 146.4 s. 35 tests pass.

The look is our own drawing in the block-game style: no game textures, logos or interface files are used, and nothing
implies an official connection to any game.

## Phase 3: closing the gaps to the reference

| Gap | Where | What |
|---|---|---|
| Globe | `tools/build_globe.py`, `lib/globe.mjs` | The whole Earth as ~633k voxels (Terrarium zoom 3, 5 MB once) with block clouds; `rung: globe` opens (film title) and ends (credits, end card) a film; a dithered hand-over to the flat world between 3,800 and 2,600 km |
| Human-scale ground | `lib/diorama.mjs` | Under every ground scene, a ~1.4 km patch rebuilt at ~4.3 m per block from the real elevation, coast and rivers, inside a ~7 km outer ring at 4x coarser blocks; cut into every coarser level as the camera drops below 3 km; ground shots fly 90–160 m up |
| Soldiers and crowds | `lib/figures.mjs`, `lib/props.mjs` | Block humanoids (5 kinds, 5 poses, 9 faction uniforms, skin tones), formations (ranks, column, line, crowd, scatter, around), marching columns; `factions`, `names`, `signs` per beat |
| Sound | `tools/sfx_plan.py`, `tools/mix_audio.py` | Scene beds and distant gunfire from the app's bundled library, ducked under the voice; two-pass loudness with a true-peak fallback |
| Light | `lib/lighting.mjs` | day, dawn, sunset, night, fog per beat, blended |
| Map effects | `lib/map_effects.mjs` | blasts, smoke, fires, aircraft at map scale; fade out below 8 km |
| Front lines | `lib/territory.mjs`, `page.js` | territory rules with `polygon` are painted into a world mask, blended between states |
| Museum | `page.js`, `lib/hud.mjs` | a turning model on a plinth in an inset, an item bar that fills through the film |
| Writing stories | `tools/story_prompt.md`, `render.mjs --check` | the CSV format and rules for any writer; the checker reports errors, length and the download a story would need |

Sample: `samples/border_war_1979.csv` (globe opening, descent onto Lang Son at dawn, Chinese and Vietnamese troops,
museum tank, globe ending with credits): 39.5 s at 1080p in about 70 s, 57 ms per frame average, 45 JS tests and the audio
tests pass.

## Known limits

- **Sets are generic.** They read as a battle, a city or a beach on the real terrain, not as the real place; landmarks need models.
- **Spot sound effects are not synced to on-screen blasts yet** (the beds and distant gunfire are; `sfx_plan.py --events` is ready for it).
- **The Indochina sample wants 13 more detail tiles (~0.7 MB)** for its new low shots; those spots use coarser terrain until fetched.
- **Test voiceover is macOS `say`.** Real narration goes through `tools/narration_timing.py`.
- **Front lines follow provinces.** Territory changes are per province (or latitude band), not hand-drawn front lines.

Credits for anything published from it: elevation from Terrain Tiles on AWS Open Data (Mapzen Terrarium; SRTM, GMTED2010,
ETOPO1); Natural Earth (public domain); Monocraft font by Idrees Hassan (SIL OFL 1.1); music from the app's bundled
library (assets/music).
