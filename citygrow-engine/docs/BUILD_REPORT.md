# City Timelapse — build report (2026-11-06)

All 7 steps of `docs/city_timelapse/PLAN.md` are built in one session. Nothing is committed.

## What was built, step by step

| Step | Built | Checked |
|---|---|---|
| 1 City world | `tools/build_city.py`: metre grid around a centre; Terrarium z14 elevation (bilinear, cached); OSM coastline as a barrier with the sea flood-filled from deep cells; lakes and river areas with **their own water level** from their banks (the Tiber stays at ~15 m, no gorge); ponds under ~3,000 m² dropped; OSM streets cut at water; offline fallbacks; hillshade `preview.png` | 9 Python tests (synthetic tiles/OSM, no network). Real worlds: Istanbul (Golden Horn, Bosphorus, historic peninsula; 6,290 streets) and Rome (Tiber; 11,398 streets), ~1–2 min each, first time only |
| 2 Low-poly look | `page.js`: flat-shaded triangle ground, sea plane and river/lake surfaces with faceted waves and glint, faceted trees, soft sun shadows fitted to the view, haze, tilt-shift + grade + vignette pass, ground ring outside the world | stills at every altitude |
| 3 Growing city | `lib/growth.mjs`: lots along every street (≤130k), growth rank from district cores (founding year matters), people per lot by period and city size, shrink from the edge, fires/sieges clear and regrow, trees cleared by the city, streets appear with their first house; houses rise house by house, period styles swap house by house through a skip | Node tests; 20 s clip: no jumps (largest frame change 0.048; a cut is > 0.3) |
| 4 Landmarks | `lib/landmarks.mjs`: 19 kinds built in code; path kinds (walls, harbours, aqueducts, bridges); plinth at the highest ground under the footprint; houses/trees under a footprint give way from its year; rise from the ground when built, sink when gone | stills: Hippodrome, Hagia Sophia, Galata Tower, Colosseum, Castel Sant'Angelo, St Peter's, Aurelian Wall |
| 5 HUD | `lib/hud.mjs`: year (BC/AD), population counter, era flag drawn from a spec (no image files) + name with cross-fade, opening title, era title cards, captions; Montserrat + Cormorant Garamond (OFL, from the repo) | stills |
| 6 Story CSV + timing | `lib/story.mjs`, `lib/timeline.mjs`, `render.mjs --plan/--stills/--clip/--out`; event captions join the next era; the era's new landmark becomes its close orbit; camera never still; `tools/story_prompt.md` for any city | 13 Node tests (incl. "camera moves every 0.5 s through the whole film") |
| 7 Music + app | `tools/music_bed.py` (bundled Kevin MacLeod track, crossfade loop, fades, -14 LUFS two-pass; optional voice ducks it), `runner.py`, `ui/city_timelapse_section.py`, style registry (Maps group), app.py hooks | runner tests (3), app wiring tests (6, incl. "app.py lines only added" and "world download only after asking"); 300 s bed measured -14.0 LUFS, -1.5 dBFS peak |

## Samples
- `samples/rome_timelapse.csv` — the first real film: 12 eras, 753 BC → 2025, 11 landmarks, the AD 64 fire, 2:48.
- `samples/istanbul_dev.csv` — development only (the reference's own city; not for publishing).

## Outputs (in `citygrow-engine/out/`, git-ignored)
- `rome_timelapse_720p.mp4` + `.credits.txt` — full Rome film through the app's runner (see measurements below)
- `rome_timelapse_t*.jpg`, `istanbul_dev_t*.jpg` — stills; `istanbul_dev_clip_22-42.mp4` — 20 s clip

## Measured (Apple M2)
- Plan (no browser): 0.4–0.6 s for 93k–130k lots.
- Page start: ~1.5 s. 720p frames: 28 ms average, 41 ms p95 (Istanbul clip, 600 frames in 18 s).
- Full Rome film through `runner.render` (720p, 30 fps): 5,039 frames, 168 s of video made in 174 s wall time including plan,
  music and mux; frames 31 ms average, 45 ms p95, 247 ms max. Audio -14.0 LUFS integrated, -1.4 dBFS peak; video and audio both 168.0 s.
  1080p was not rendered in this session (expect roughly 2x the frame time).

## App wiring (app.py: 23 lines added, none changed or removed)
`_ct_` hooks next to each Voxel Map hook: import, active style, running guard, pick/leave, block show/hide, CTA routing,
CTA sync, project open (deactivate + resume), run flags. `ui/style_kit.py`: "City Timelapse" added to the own-steps tuple.
`ui/style_registry.py`: appended block. The page itself was **not opened in the real app** in this session.

## Not done / open
- The page has not been seen in the running app (only import, syntax and wiring tests).
- Not in `VideoGenerator.spec` (Voxel Map is not either): runs from the source checkout.
- Houses only line real streets; old periods use today's street pattern (the plan's "Greek/Roman grid" period layouts are not built).
- Forests are thinner than the reference; the old-town look relies on terracotta roofs.
- No smoke/fire particles for event rows (the area clears and regrows; the caption tells it).
- The paused scheduled task "city-timelapse-build" is no longer needed (delete it in the Scheduled sidebar).
- Nothing committed or pushed.

## Reference-gap pass (2026-11-14, How Cities Grew "Constantinople" study)
All 9 gaps from the comparison were built:
1. Landmarks: domes on window-ringed drums, arched window rows, buttresses, narthex/atrium (mosque: domed courtyard),
   hippodrome tiers + arcade + obelisks, palace second court and gardens, amphitheatre arcades; every model is merged
   into one mesh per material (few draw calls).
2. Hero shots: closer, lower landmark orbits, a new `street` shot among the roofs, a tighter `low_track`.
3. Events: an event between two eras stops the clock in its year (`tl.stops`, camera `event` shot, its caption there).
   Fire spreads from the centre, houses become charred ruins, flames and smoke columns; quake dust; siege camp (tents,
   engines that fire, banners in the next era's colour), shelling on the walls, a fleet (`lib/fx.mjs` planEvent).
4. Forest denser (spacing 15 m, clumps); farm fields (`makeFields`) tilled when the city nears, built over later.
5. Old towns packed: block infill lots (`infill`, pre-modern `dense` styles only); narrow lanes not drawn there.
6. House variety: ~3 % big public buildings, taller old core, district roof tones, wider wall jitter.
7. Water: turquoise shallows, foam line and deep blue from a shore-distance texture; 140 sea lanes, ships by population.
8. Walls: towers every 55 m with battlements and banners, brick courses, battlements, gatehouses where streets cross.
9. Lighting: stronger sun, contact shading at the foot of walls and trees, softer shadows.
New buildings rise inside scaffolding (clipping plane) and finish halfway through their era's hero shot (max 8 s).
Measured: Istanbul plan 0.7 s; 720p frames 32–35 ms avg (was 28–31). Tests: 23 Node, runner 4.
