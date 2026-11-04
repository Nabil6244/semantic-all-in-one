# Roblox Cinema Engine — handoff (2026-11-04)

Paste the prompt at the bottom into a new session to continue.

## Done (all in `roblox-cinema-engine/`, nothing committed, no file outside this folder touched)

Research: 8 reference videos analysed through vidIQ's automated video-watch tool (not watched frame by frame by Claude):
Mitsi Studio Vietnam War (Lm9OUWWw59Y), Blitzkrieg (eTLq7j7ZrYM), Gulf War (3LiVXSCIvtI); 3/1 Marines Roblox Vietnam film (0b9I_MpHqSo);
banastic "I joined the Vietnam War on Roblox" (Y_l1nkd6w40); W-A Vietnam War cinematic (mZFkN4ezYHo); The Last Guest Roblox movie
(1ZM6ztUlLWY); Kings and Generals First Chechen War (xjIu9pkrIP4, map storytelling). Findings are in the session only — the
reference doc `docs/REFERENCE_ANALYSIS.md` is NOT written yet. Key patterns: R6 blocky rigid-limb bodies with decal faces;
diorama/toy-plastic sets, conical pines, blocky clouds; tabletop relief maps with red arrows and pins; low tracking shots with
vehicles, top-down tactical overviews, sweeping aerial follows; hard cuts on topic shifts, dissolves for time, black title
cards; golden hour / cool blue night fog / desaturated overcast combat; yellow-white subtitles, lower-third name tags;
shot length 2–4 s (comedy) to 3–6 s (documentary). No gore adopted.

Pure-logic engine (Node + browser ES modules, `lib/`), smoke-tested on the sample (17 scenes, 125 s, no errors):
- `rng.mjs` seeded RNG/noise; `csv.mjs` story CSV schema (row=plan/chapter/beat, 21 columns, JSON `extra`) + `validateStory`
- `narration.mjs` sentences, dates (incl. "twenty-fifth of August", "SUMMER 1944"), numbers in words, people with titles,
  event classifier (27 types), action/vehicle/environment/time/weather words, voiceover word alignment, pauses
- `gazetteer.mjs` ~50 places with lon/lat/biome/culture; `eras.mjs` eras, era vehicle substitution, faction kits (no insignia)
- `characters.mjs` data-driven looks for 19 roles, name-stable identities; `animation.mjs` 30 procedural states, blends, breathing layer
- `world.mjs` 22 environments (terrain fn, water, roads, buildings, trees, fields, hedgerows, props, anchors, colliders)
- `vehicles.mjs` 33 kinds + motions (ground-snapped, water bob, air clearance, landing-craft ramp time)
- `stage.mjs` formations, boat riders → wade, paratroopers in the sky, narration actions on the spoken word, `evaluateActor`
- `camera.mjs` 21 behaviours, terrain/roof/line-of-sight collision, jump metric; `fx.mjs` deterministic particle emitters
- `recipes.mjs` 30 scene recipes; `director.mjs` narration → scenes/shots/transitions/HUD/audio plan with reasons;
  `assemble.mjs` shared scene build + camera continuity + effects and their sound cues; `mapproj.mjs`
- Sample story: `samples/dday_1944.csv` (D-Day, 5 chapters, 17 beats, ~2:05 planned)

Browser renderer (`web/`, written, NOT run yet — expect bugs): `gfx.js` (material/geometry/texture cache, face, uniform,
stud, facade textures), `character.js` (rig + poseRig), `vehicle.js`, `world3d.js` (terrain, water, roads, instanced
trees/hedges/props, buildings, interior), `map3d.js` (tabletop map, pins, drawing routes), `fx3d.js` (block particles, rain).
Fonts copied (OFL): Outfit, Inter in `assets/fonts/`.

## Remaining
1. `web/look.js` (light presets day/overcast/storm/dawn/sunset/dusk/night/interior/map, sky dome, clouds, fog, post shader
   with grade + dissolve/dip/cloud-wipe, tone mapping in the shader since it renders to targets).
2. `web/hud.js` (subtitles with word highlight, date tile, place tag, chapter card, stat callouts, map labels + "present-day
   borders, positions approximate" note, music credit at the end) and `web/main.js` (scene runtime cache build/dispose,
   renderFrame(t), transitions between two render targets, stats()) and `web/page.html`.
3. `render.mjs` (serve page + three from `starmap-engine/node_modules/three` incl. `/three/addons/`, Playwright from
   `flow-engine`, GPU Chromium `--use-angle=metal`, crop Natural Earth `map_scene/data/countries.json.gz` per map scene,
   `--plan/--stills/--clip/--preview 720p/--final 1080p`, JPEG pipe to ffmpeg BT.709, perf + memory report, cue list out).
4. Audio tools in `tools/`: `make_vo.py` (macOS `say`, a stand-in test voice — say so), `narration_timing.py`
   (faster-whisper words), `sfx_synth.py` (original synthesized gunfire/engines/explosions/surf), `mix_audio.py`
   (reuse `health_cinema.edit.audio.speech_duck` unchanged, Sonniss ambience beds from `assets/bundled-sfx`, Kevin MacLeod
   music CC BY 4.0 with credit, two-pass loudnorm −14 LUFS / −1 dBTP, measure the final file), `qc_video.py` (frozen frames, jumps).
5. Tests in `test/*.test.mjs` (CSV, narration, characters variation, animation no-freeze, environments, recipes, vehicles on
   ground, camera continuity/clipping, subtitles timing, fx budget/determinism, caching) + Python audio test + app integration test.
6. App integration (additions only, check `test_fixtures/*_protected.json` first): `ui/roblox_cinema_section.py` modelled on
   `ui/product_trailer_section.py`; `ui/style_registry.py` add `ROBLOX_CINEMA` to STANDALONE/GROUPS/EXTRA_BLURBS/EXTRA_CARDS by
   appended lines; `app.py` hook lines next to each Product Trailer site (`_active_style`, style choice activate/deactivate,
   block grid toggle, `_sync_primary_cta`, cta dispatch, project restore deactivate, `_RUN_FLAGS`).
7. Render the 2-minute demo at 720p (and 1080p), inspect the 10 required stills, fix visual problems, measure performance.
8. Docs: `README.md`, `docs/REFERENCE_ANALYSIS.md`, `docs/ARCHITECTURE.md`, final report. Never commit or push.

## Prompt to continue

```
Continue the Roblox Cinema Engine in roblox-cinema-engine/. Read roblox-cinema-engine/docs/HANDOFF.md first: it lists what
is built (lib/ planner, web/ builders, the D-Day sample) and the remaining steps 1–8. Do them in order without asking
questions: finish web/look.js, web/hud.js, web/main.js, web/page.html, then render.mjs, get the page running in headless GPU
Chromium and fix bugs, then the audio tools, tests, app integration (additions only; check test_fixtures/*_protected.json),
the real 720p 2-minute render with inspected stills and measured performance, 1080p if practical, and the docs/final report.
Keep all work inside roblox-cinema-engine/ except the minimal ui/ and app.py registration lines. Do not modify other styles
or engines. Do not commit or push. Report measured results separately from estimates and name every placeholder honestly.
```
