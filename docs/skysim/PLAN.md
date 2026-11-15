# Sky Sim — build plan

A new editing style based on the Lightbound channel (@LightboundSpace: 16 long videos, 2.1K subscribers,
top videos 711K / 294K / 223K / 131K views). We take its **patterns**, not its look: our own fonts,
colours and names (see the "adopt patterns, not a fixed style" rule).

Studied 2026-11-14: frames from all 16 videos.

---

## 1. What the channel does

### The core idea
**One place, one change.** Each video holds one scene and changes a single thing step by step:
the distance, the planet, the star or the depth. The change itself is the story, and the scene is
never still. There are almost no hard cuts and no stock b-roll.

### The title is a ladder
"at different distances", "from every planet", "every star", "closest vs farthest", "1 hour = 7 years".
Each rung is one **step** of 15–40 s with 2–6 narration lines.

### The six looks (all 16 videos)

| Look | What's on screen | Videos |
|---|---|---|
| **A. Landscape sky** | Drawn mountains, a lake with reflections, rock or desert ground. The sky object is lit to match: sky colour, lit cliffs, burning forest, lava ground. | TON 618 (711K), Night sky elsewhere in the galaxy, Smallest vs largest star, Sunset on every planet, Miller's Planet (ocean + black hole above it) |
| **B. City photo + sky object** | A real skyline photo (London, Dubai, Paris, Rio, Singapore, Sydney) with a planet, star or rings composited into the sky, plus water reflection and a scene tint. | Planets replaced the Moon 1 & 2, Sun replaced by other stars, Earth had rings |
| **C. Space dark** | A black star field with a lit globe or Sun in the middle, a big spaced title ("U R A N U S") and a stats block. Collision sims with debris spirals. | Sun from every planet (294K), Earth crashed into every planet, Sun replaced (frozen blue Earth) |
| **D. Moon-surface view** | Cratered ground in the foreground with the parent planet in the sky at its true size. A tiny object gets a label with a leader line. | Closest vs farthest moon of every planet |
| **E. Journey** | The camera flies outward past planets, stars and galaxies, with a distance readout and a light-travel-time readout. | Trip to Uranus, Journey to Andromeda |
| **F. Helmet POV descent** | A helmet-visor frame with a cyan HUD (altitude/depth, %, pressure + °C, warnings), and the atmosphere colour shifting as you sink. | Fell into Saturn (131K), Fell into Jupiter |

### Text kit (same across every video, very sparse)
- **Stats block** top-left: a tiny spaced-caps label above a larger value, 1–4 rows
  (`DISTANCE FROM THE SUN / 0.39 AU · 58 MILLION KM`, `SIZE IN THE SKY / 40× THE MOON`,
  `BRIGHTNESS / 7,300× THE FULL MOON`, `LIGHT TRAVEL TIME / 3 MIN 13 S`).
- **Single readout** top-right: `DISTANCE / 50 ly`, `STARS VISIBLE / ~1,000,000`, `SUNSET LASTS / almost a day`,
  `SINCE IMPACT / 2 days`.
- **Twin clocks** top-right (Miller's Planet): `TIME ON MILLER'S PLANET 00:05:51` / `TIME ON EARTH 249 d 22 h`.
- **Spaced title** for each step: `NEPTUNE`, `THE SUN FROM MERCURY`.
- **Scale ring**: a dashed circle labelled `THE SUN FROM EARTH` drawn over the bigger disc.
- **Leader-line label** for objects too small to see (`URANUS ——`).
- **Subtitles**: centred, white, one short sentence, no highlight words.
- **Helmet HUD** (look F only).

### Pace and sound
- 3–10 minutes; a step every 15–40 s; crossfades or continuous camera moves, nearly no hard cuts.
- Short calm sentences, one fact each: "Ten light-years. Still brighter than the full Moon."
- A soft ambient music bed with low swells on reveals.
- Nothing is ever frozen: the camera drifts, the object approaches, the water ripples, stars twinkle,
  clouds move.

---

## 2. What we already have (reuse)

- `whatif-engine/` Three.js page renderer, `lib/scene3d.mjs`, `lib/scene_gen.mjs` (procedural worlds:
  gas/rock/ice/ocean/lava/sun/haze, camera paths, particles), `lib/blackhole.mjs` (ray-traced disc,
  lensing, horizon — covers TON 618 and Miller's Planet), `lib/hero.mjs` (descent scenes).
- Textures in `whatif-engine/assets/textures`: Sun, all planets, Earth day/night, Moon LROC,
  Milky Way. Planet GLBs in `assets/models`.
- HUD-ish layers: `tm_metric`, `tm_gauge`, `tm_clock`, descent `depth_ruler`.
- Python side to copy the shape of: `whatif/` (narration, planner, heal, preflight, stress, compile,
  sound, engine_runner, app_integration).
- `starmap/music.py` `ambient` mood.

## 3. What is new

### 3.1 `skysim/physics.py` — numbers are computed, never typed
- angular size (deg, "× the Moon", "× the Sun from Earth") from radius + distance
- brightness (× full Moon, × sunlight, magnitude), visible-star count by place in the galaxy
- light travel time, sunset length (rotation + atmosphere), time dilation (Miller-type clocks)
- surface temperature from star luminosity + distance (frozen Earth: "−130 °C")
- formats: `58 MILLION KM`, `0.39 AU`, `10.8 billion ly`, `249 d 22 h`
- **The readouts come from here**, so the CSV only names the object and distance and the values are always right.

### 3.2 Step CSV (one row per step, not per shot)
```
step,look,place,object,distance,readouts,title,camera,narration
1,landscape,lake_valley,ton618,10.8e9 ly,distance,,drift,"Somewhere up there is TON 618..."
2,landscape,lake_valley,ton618,1000 ly,distance,,drift,"And for the first time it isn't just a point of light."
```
- `look`: landscape | city | space | moon_surface | journey | helmet
- `object`: sun, any star (`star:betelgeuse`, or a type + radius + temperature), planets, moons, rings,
  `blackhole:ton618`, galaxy
- `readouts`: names from physics.py (`distance,size,brightness,light_time,stars_visible,clock_pair,...`)
- The same place across rows = the same held scene with the object changing (look A/B rule).
- `heal.py`/`preflight.py` repair it like What If, so a bad row never stops the render.

### 3.3a Realistic scenes come from Blender (2026-11-14)
The 2D canvas landscape looked fake next to the reference, so looks that need a believable place are rendered in Blender:
- `skysim/blender/valley.py`: a real 3D valley (terrain, CC0 rock/grass/mud textures, conifers, mirror lake, HDRI day sky,
  camera-only stars, haze, fire, lava, compositor glare). The light ladder drives it exactly like the 2D look.
  The black hole is the What If engine's ray-traced `blackhole_disc`, rendered once (no stars) and set in the sky on a camera-facing card.
- `skysim/blender_runner.py`: each held landscape scene becomes one clip (frames at 15 fps, blended to 30), and its steps become
  the engine's `video` shots with the sky object's screen position, so the sk_* text layers still draw on top.
- `skysim/compile.py render()`: Blender clips -> What If engine (text, crossfades) -> voice mux.
- Assets: `python -m skysim.tools.fetch_assets` (Poly Haven CC0, 39 MB, git-ignored `skysim/assets/`).
- No Blender, or a scene that fails in it: that scene falls back to the 2D look, and the video still finishes.

### 3.3 Engine: `whatif-engine/lib/skysim/` + shot kind `sky`
Added inside whatif-engine so the renderer, frame pipeline and never-stop guards come for free.
1. **landscape.mjs** (look A): procedural ridges from noise plus a lake plane with reflection and ripple,
   ground presets (lake, desert, cracked rock, ocean, ice). **Sky model**: sky colour/brightness from the
   object's light, the object rendered at its true angular size with bloom and a diffraction spike, and the
   terrain lit by it. Heat stages (glow → burning forest embers → lava ground) are driven by flux.
2. **city.mjs** (look B): a photo plate plus a sky mask (alpha PNG), the object placed in the sky and
   reflected in the water band, a scene tint/exposure from the object's light, and a slow push-in.
3. **space.mjs** (look C): reuses globe + Sun shaders, the spaced title and the dashed scale ring.
   `collide`: a debris spiral built from scene_gen particles.
4. **moonsurface.mjs** (look D): crater-ground foreground plus the planet at its true size, with a leader label when it's under 0.5°.
5. **journey.mjs** (look E): a log-scale fly-out (planets → heliopause → stars → Milky Way → Andromeda),
   with the readout driven by camera distance.
6. **helmet.mjs** (look F): a visor frame (drawn, not a photo), a cyan HUD, depth-driven atmosphere colour,
   haze and particles, and warning text.
7. Black hole steps call the existing `blackhole.mjs`.

### 3.4 Text kit layers `sk_*`
`sk_stats` (top-left block), `sk_readout` (top-right single), `sk_clocks` (twin counters),
`sk_title` (spaced caps), `sk_scalering`, `sk_leader`, `sk_subtitle`, `sk_hud`.
Values count up/down smoothly between steps. Use our own font, not theirs.

### 3.5 City photo library (look B), sourced once
- About 40 free-licence skyline photos (Unsplash/Pexels/Wikimedia CC) at dusk, night and day, with
  water in front where possible.
- Sky mask + horizon line + water band made **once** per photo by a one-off tool
  (`skysim/tools/make_masks.py`, colour/gradient sky segmentation + manual fix file).
- Stored with credits. No per-video asset work.

### 3.6 Sound
An ambient bed (`starmap.music` ambient), a soft low swell on each step change and on big reveals, and
no whooshes on every line. Voice-led mix like What If (−14 LUFS).

### 3.7 Never-still guard
Every step must have live motion: object approach/scale, camera drift ≥ a minimum speed, water/cloud/star
motion, counters. Preflight flags any 4 s window with no change. This follows the "no still screens" rule.

### 3.8 App + prompt
- A "Sky Sim" style card (style pages pattern): upload voiceover/script + step CSV → Generate.
- `composition_styles/skysim_csv_prompt.txt`: makes the step CSV from a script, picks the look per
  title type, lists the objects and readouts.
- Script helper notes: short one-fact sentences, one rung per step.
- Zero Flow and zero stock video by default: everything is drawn, apart from the look B photos.

---

## 4. Build order

| # | Step | Done when |
|---|---|---|
| 1 | `skysim/physics.py` + tests | Numbers match the reference readouts (Sun from Mercury 2.6×, 6.7×, 3 min 13 s; Mars as Moon 2×) |
| 2 | Step CSV + heal/preflight + planner (steps → spec) | Sample CSV plans with 0 problems |
| 3 | Look C space + text kit `sk_*` | Still frames of "Sun from every planet" |
| 4 | Look A landscape + sky model + heat stages | TON 618 distance ladder stills (dot → blue sky → burning → disc) |
| 5 | Look D moon surface, look F helmet | Stills |
| 6 | Look B city + photo/mask library | 5 photos masked, Jupiter-over-skyline still |
| 7 | Look E journey | Fly-out stills |
| 8 | Sound + never-still guard + compile/render | 60 s test render |
| 9 | App card + CSV prompt + tests | Generate from the app works end to end |

First test video: **"What the Sun looks like from every planet"** (looks C + D, needs the fewest new parts).
Second: **TON 618-type distance ladder** (look A, the 711K format).

## 5. Rules while building
- Grep `test_fixtures/*_protected.json` before touching shared whatif-engine files (page.js, shots.mjs, layers/index.mjs).
- Keep What If working exactly as it does now: Sky Sim is a new kind/style, not a change to What If.
- Ask before renders, test suites, fetches and commits; run only the touched tests.
