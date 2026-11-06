# City Timelapse style — plan

Status: all 7 steps built 2026-11-06 (uncommitted). See citygrow-engine/docs/BUILD_REPORT.md.

Reference: YouTube channel How Cities Grew (Constantinople 680 BC → AD 1453, Stockholm 800 → 2025,
London 60 BCE → 2025). Studied by watching frames, not by copying. Our version is our own code and our own
look; we take the format, not their assets.

## 1. What the format is

| Element | What we saw |
|---|---|
| Subject | One city, one fixed piece of ground, 1,000–2,500 years. Terrain and coast stay; the city grows, shrinks, burns, gets rebuilt |
| Look | Soft low-poly 3D: faceted trees, small box houses with terracotta roofs, flat blue water, warm sun, soft shadows, tilt-shift blur at the edges |
| Landmarks | A handful of hero buildings modelled in more detail (Hagia Sophia, Hippodrome, walls, palace) — this is what makes a video feel like that particular city |
| Camera | Always moving: slow orbits, drifts, low passes over streets, occasional wide pull-out to show the whole site |
| HUD | Year bottom-right (big bold), population top-right with an icon ("c. 450,000"), era flag + era name bottom-left, a centred serif title card for big eras ("Eastern Rome — THE GOLDEN AGE"), short serif captions fading in at the bottom |
| Sound | Music only. No voiceover |
| Length | 3.5–8.5 min |

## 2. Where it lives

A new engine folder, `citygrow-engine/`, built the same way as `voxelmap-engine/` (Node + headless Chromium +
three.js page, `runner.py` for the app, story CSV in, mp4 out). It does **not** change Voxel Map.

Reused (imported or copied, unchanged where possible):

| From | What |
|---|---|
| `voxelmap-engine/lib/camera3d.mjs`, `lib/director.mjs` | Camera rig, arc moves, shot vocabulary (establishing, orbit, flyover, pullback, low_track), never-repeat rule |
| `voxelmap-engine/render.mjs` | Frame loop, `--plan` / `--stills` / `--clip`, motion blur, encode |
| `voxelmap-engine/tools/mix_audio.py`, `audio_qc.py` | Music bed to −14 LUFS; QC |
| `voxelmap-engine/tools/build_world.py` | Terrarium elevation fetch + cache (new scale, see below) |
| `visual_bridge.py` | Output goes through Visuals → Export like every style |

New, because the scale is different: Voxel Map's finest block is 175 m; a city needs ~2–5 m. So the city
engine has its own smooth terrain and its own building layer.

## 3. Build steps (each one ends testable)

### Step 1 — City world (ground only)
- `tools/build_city.py --id istanbul --center 28.97,41.01 --size 8km`
- Elevation: Terrarium zoom 14–15 (≈5–10 m), cached once.
- Coast and water: OSM coastline / water polygons (free, Overpass or Geofabrik extract, fetched once).
- **Old coastlines:** optional `shore_offsets` per era in the CSV (e.g. a filled-in harbour), drawn as a
  polygon swap. Most cities need none.
- Output `worlds/<id>/` (height, water mask, meta). Git-ignored like Voxel Map worlds.
- Test: a still of bare Istanbul ground with water.

### Step 2 — Low-poly look
- Flat-shaded triangle terrain (no blocks), grass/sand/rock by slope and height, faceted water with gentle
  waves and sun glint.
- Soft shadow map from one warm sun, light fog, tilt-shift depth-of-field pass, one grade pass.
- Trees: 3–4 faceted shapes (round, cone, cypress, bush) instanced, scattered by seed on free land; cleared
  where the city stands in a given year.
- Test: stills at high / mid / low altitude; compare against the reference frames side by side for feel only.

### Step 3 — Buildings that grow over time (the core)
Each building is a record: `footprint, height, roof, born, died, kind`. The renderer shows a building only
between `born` and `died`, rising in over ~0.6 s of screen time (scaffold → walls → roof), fading/collapsing
on `died`. Roads, walls, harbours, aqueducts use the same record.

Where the records come from, in order:
1. **Today's city:** OSM building footprints + road lines inside the area (fetched once).
2. **Aging backwards** (automatic): a growth model gives every footprint a `born` year from distance to the
   old core(s), main roads and walls, plus a seeded jitter, so the city grows outward along roads, the way real
   cities do. Districts from the CSV override it ("Galata district 1300", "Old town to 1650").
3. **Older periods with no matching modern layout:** generated low-poly blocks of houses filling the CSV's
   district polygons at the era's density (houses per hectare from population), on a street grid or organic
   lanes per era style (Greek grid, Roman grid, medieval organic, modern blocks).
4. **Destruction events:** CSV `event` rows (fire, siege, earthquake) remove a district and let it regrow.

Roof/wall colours per era style (terracotta, timber, stone, modern grey/glass) so 600 BC and 1900 look
different without any per-video art.
- Test: synthetic city, 3 eras, check counts per year and that nothing pops in a frame (largest frame change
  check, as in Voxel Map).

### Step 4 — Landmark library (made once, reused)
Low-poly hero models built in code (like `props.mjs`), parameterised, so one model covers many cities:
- dome church/basilica, mosque + minarets (count param), cathedral (towers param), Greek temple, Roman
  forum, amphitheatre/arena, hippodrome/circus, castle/keep, palace complex, city wall + towers (follows a
  polyline), harbour + moles, aqueduct (polyline), bridge (polyline), lighthouse, tower/skyscraper.
- Placed from the CSV with lat/lon, rotation, `born`/`died`, and optional changes (e.g. `minarets: 1 @1453,
  4 @1600`).
- No downloads, no per-video assets (see the no-per-video-asset rule).
- Test: one still per model; one composite still.

### Step 5 — HUD
Add to the city engine HUD (own file, borrowed layout code from `voxelmap-engine/lib/hud.mjs`):
- Year bottom-right, counts through the years during time skips (BC/AD handled; "c." for approximate).
- Population top-right with person icon, eased between era values.
- Era badge bottom-left: flag/emblem image + era name. Flags drawn in code or from a small free (CC0/PD) set
  sourced once.
- Era title card: centred serif, small kicker line above, fades in/out in calm moments.
- Captions: one or two serif lines at the bottom, fade in, held long enough to read (words/2.5 s minimum).
- Free serif + sans fonts (OFL), stored once in `assets/fonts/`.

### Step 6 — Story CSV + timing
One row per era/beat. Columns:

| column | example |
|---|---|
| `row` | `plan` / `era` / `event` / `landmark` / `district` |
| `year` | `-658`, `540`, `1453` |
| `hold` | seconds on screen (else auto from captions) |
| `era_name` | `GREEK BYZANTION` |
| `flag` | `byzantine_eagle` |
| `title` / `kicker` | `THE GOLDEN AGE` / `Eastern Rome` |
| `population` | `450000` |
| `caption` | short sentence |
| `shot` | optional: `orbit`, `flyover`, `pullback`, `low_track` |
| `focus` | optional: lat,lon or a landmark id |
| `extra` | JSON (district polygon, event kind, landmark params) |

- Time runs continuously between years; the camera never stops (no-still-screens rule). Each era gets at
  least one move; big eras open with a pull-out, then descend to a landmark.
- `--plan` prints the timeline and warnings (year going backwards, caption too long for its hold, landmark
  outside the area) without rendering.
- A CSV run makes zero Gemini calls.

### Step 7 — Music + app page
- Music bed from the app's existing music library, looped/crossfaded to length, −14 LUFS.
  Optional soft ambience (sea, birds, bells) from the curated beds, low under music.
- App: a "City Timelapse" style page (same grouped picker as the other styles). Pick city CSV → Generate
  (builds the world after a yes/no if missing, like Voxel Map) → Render → Visuals → Export.
  Nothing starts before Generate.
- Script/CSV prompt doc so the user can get a CSV from a chat model for any city.

## 4. Order and size

| Step | Size | Can be seen after |
|---|---|---|
| 1 City world | small | bare-ground still |
| 2 Low-poly look | medium | stills that already "feel" like the style |
| 3 Growing buildings | large — the core | a 30 s synthetic growth clip |
| 4 Landmarks | medium | model stills |
| 5 HUD | small | stills with full HUD |
| 6 CSV + timing | medium | first real city preview clip |
| 7 Music + app page | small | full video from the app |

Suggested first real city: Istanbul (the reference topic) is fine to test with, but the first finished video
should be a different city so ours does not look like a copy of theirs.

## 5. Risks

- **Old layouts are guesses.** Aging today's map backwards gives a believable growth pattern, not history.
  District rows and landmarks in the CSV carry the real facts; the generated filler only needs to look right.
- **Render time.** A whole city of instanced houses at low altitude is heavy. Use instancing + distance LOD
  (far houses merge into textured blocks), measured on the M2 like Voxel Map before going further.
- **OSM data size.** Big cities have 100k+ footprints; clip to the area and simplify once at build time.
- **Licence.** OSM data is ODbL: add "© OpenStreetMap contributors" in the video description template.
