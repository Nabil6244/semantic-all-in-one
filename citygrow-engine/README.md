# citygrow-engine — City Timelapse

A low-poly 3D city growing over the centuries on its real ground and water, from a story CSV. The format comes from
studying the "3D timelapse" city videos (one city, one fixed area, many years; music only; year, population, era flag and
serif captions). The code, models and look are our own. Separate from every other style; nothing outside this folder
imports it except `ui/city_timelapse_section.py`.

    python3 tools/build_city.py --id rome --center 12.4823,41.8955 --size 8      # once per city (reusable world)
    node render.mjs samples/rome_timelapse.csv --plan                            # timeline + warnings, no browser
    node render.mjs samples/rome_timelapse.csv --stills 8,50,128                 # preview stills (out/)
    node render.mjs samples/rome_timelapse.csv --clip 40:60                      # a short preview piece
    python3 -c "import runner; runner.render('samples/rome_timelapse.csv', 'out/w', output='rome.mp4')"   # the film + music
    npm test && python3 test/test_build_city.py && python3 test/test_runner.py

## Parts

| Part | File | How |
|---|---|---|
| World | `tools/build_city.py` | A metre grid (default 8 km, 8 m cells) around the city centre. Elevation: Terrarium tiles zoom 14, bilinear, cached in `cache/`. Water: OpenStreetMap coastline (a barrier, the sea flood-filled from deep cells), lakes and river areas; rivers and lakes keep their own surface level taken from their banks; ponds under ~3,000 m² are dropped. Streets: OSM highways (motorway…pedestrian), cut at water. Offline: the sea is low ground joined to the edge and the city lays out its own lanes. Writes `worlds/<id>/` (height.f32, water.u8, water_level.f32, roads.json, meta.json, preview.png) |
| Ground | `lib/terrain.mjs` | Shared by Node and the page: the fine grid smoothed (city elevation includes rooftops) and sampled every 2 cells; `heightAt` interpolates on the same triangles the page draws, so houses sit exactly on the drawn ground |
| Growth | `lib/growth.mjs` | Lots along every street (up to 3 rows deep, no overlaps, off water and steep ground), up to 130k. Each lot gets a rank from its distance to the district cores (a later core counts as further), main streets first and clumpy noise; a year's population says how many lots stand (people per lot: 7 for old towns, denser for huge pre-modern cities, apartment blocks for modern ones). A shrinking city loses its edge first. Fires/sieges clear an area and it regrows from the edge in. Trees are cleared when the city reaches them; a street appears with its first house |
| Story | `lib/story.mjs` | CSV rows: plan, district, era, landmark, event (see `tools/story_prompt.md`). Years in any common form (BC/BCE/AD/c.) |
| Timeline + camera | `lib/timeline.mjs` | Opening title over the first view; each era = a time skip (year counts, city grows, camera rises to see it) then a hold (title card, captions). A landmark that appears with an era becomes its close orbit; otherwise orbit / push / flyover / pullback / low track, never the same twice in a row; an always-on drift, so no frame is still |
| Landmarks | `lib/landmarks.mjs` | 19 kinds built in code (dome church, mosque with n minarets, cathedral, temple, forum, amphitheatre, hippodrome, castle, palace, tower, skyscraper…; walls, harbours, aqueducts, bridges along a path). On a plinth at the highest ground under the footprint; houses and trees under the footprint give way from its year; it rises out of the ground when built and sinks when gone |
| Look | `page.js` | Flat-shaded triangle ground, sea plane + river/lake surface with faceted waves and sun glint, instanced houses with gable or flat roofs (colours and heights per period, `lib/styles.mjs`, swapped house by house through a skip), faceted trees, soft sun shadows fitted to the view, haze, then one pass for tilt-shift blur, grade and vignette |
| Text | `lib/hud.mjs` | Year, population (counts through skips), era flag (drawn from a spec, no images) and name with a cross-fade, centred serif titles, captions. Fonts: Montserrat + Cormorant Garamond (OFL, already in the repo) |
| Sound | `tools/music_bed.py` | One bundled Kevin MacLeod track (CC BY 4.0), looped with a crossfade when needed, faded, -14 LUFS; an optional voice-over ducks it. Credits are written next to the video |
| App | `runner.py`, `../ui/city_timelapse_section.py` | check → (build the world after a yes/no) → plan → render. Nothing starts until Generate |

## Credits a video must carry
Written to `<video>.credits.txt`: the music line, "© OpenStreetMap contributors (ODbL)" and the Terrain Tiles credit.
