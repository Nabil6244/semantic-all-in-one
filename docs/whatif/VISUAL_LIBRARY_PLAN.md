# What If — Visual Library plan (for hundreds of visuals, 2026-10-16)

**Status: built 2026-10-16** (uncommitted): steps 1-9 done, step 10 (reference harvester) not built. See `TEMPLATES.md` and `template_catalog.jpg`.

Follows `V4_BLACK_HOLE_PLAN.md`. Today every visual is its own hand-written layer (`whatif-engine/layers/tm_*.mjs`, 22 of them,
registered in `layers/index.mjs`, each chosen by name in `whatif/planner.py`). That works for 22 visuals, not for 200: every new one
costs a new file, planner code, CSV prompt text and tests. The plan below makes a new visual **a small data file**, not new code.

## 1. The idea: primitives + motions + templates

```
primitives  (≈25, code, built once)   ring, disc, line, path, arrow, dot, label, number, icon, image, panel, grid, mesh, particles,
                                       clock, axis, rail, bar, band, equation, sprite, glow, mask, star-field, frame-text
motions     (≈15, code, built once)   draw-on, count, move-along, orbit, pulse, flash, scale, fade, rotate, flow, shrink,
                                       stretch, colour-shift, reveal-by-word, camera-push
templates   (hundreds, JSON data)      "photon_sphere", "two_clocks_ratio", "moving_walkway", "light_bends", "squeeze_object" ...
                                       = primitives placed on the 1280x720 frame + motions timed to narration words + slots
```

A template has **slots** the CSV fills (`{target}`, `{value_from}`, `{value_to}`, `{label}`, `{image}`), so one template serves every topic:
"squeeze_object" is the Sun into a black hole, Earth into a marble, a person into a neutron star.

Example (shape only):
```json
{ "id": "two_clocks_ratio", "family": "time", "slots": ["left_label", "right_label", "ratio_from", "ratio_to"],
  "items": [
    {"p": "clock", "at": [0.21, 0.55], "r": 0.07, "label": "{left_label}", "speed": 1},
    {"p": "clock", "at": [0.42, 0.55], "r": 0.07, "label": "{right_label}", "speed": "{ratio}", "accent": "cyan"},
    {"p": "frame-text", "at": [0.0, 0.88], "text": "1 HOUR FOR YOU = {ratio} HOURS ON EARTH", "m": "count", "from": "{ratio_from}", "to": "{ratio_to}"} ],
  "builds_every_s": 5 }
```

## 2. What gets built (in order, test-first, no renders without your OK)

| Step | Work | Done when |
|---|---|---|
| 1 | `whatif-engine/lib/prims/` — the primitives, drawn with the existing `tm_theme` colours/fonts | each primitive has an engine unit test |
| 2 | `whatif-engine/lib/motions.mjs` — the motions with easing; word-timed triggers (`on: "word:photon"`) | unit tests on frame values |
| 3 | `tm_template` — ONE layer that loads a template JSON, fills slots, runs it | renders any template; old `tm_*` untouched |
| 4 | `whatif-engine/templates/<family>/<id>.json` + schema check (`templates/schema.json`) | bad template fails a test, never a render |
| 5 | Port the V4 visuals as the first ~20 templates (N1-N17 in the V4 plan) | each has a still next to its V4 frame (with your OK) |
| 6 | Auto-catalog: a script renders one still per template into `docs/whatif/catalog/` + `catalog.html` contact sheet | you can browse every visual |
| 7 | Planner picks templates by **tags** (`time`, `distance`, `size`, `danger`, `light`, `inside`), not hard-coded names | new template = picked with no Python change |
| 8 | CSV prompt (`composition_styles/whatif_csv_prompt.txt`) gets the catalog list auto-generated from the template files (id, slots, one-line use) | prompt never goes out of date |
| 9 | "Long plate must build every ≤ 6 s" check across templates (`builds_every_s`) | no still screens |
| 10 | Reference harvester: for each new reference video → contact sheets + measured rhythm + a gap list "visuals with no template yet" | adding reference #5, #6... is a routine |

Existing 22 `tm_*` layers stay as they are; they can be moved onto templates later, one by one, only where it is cheaper.

## 3. Shared assets (sourced once, never per video)
- Icon/sprite set (CC0): astronaut (normal / stretched / red / fading), eye, star, letter, rocket, satellite, human, heart, brain, cell,
  atom, thermometer, clock, skull, plane, ship, car, city, tree, wave.
- Real-image index per subject (NASA / ESA / ESO / EHT / Commons) with citations, reused by every video on that subject.
- Hero scenes in the engine: black hole (lensed disc), star, neutron star, planet surface, ocean surface, deep space; each with 3-4 camera presets.
- Math font for equations; a units table (km, light-years, °C, bar, g, years, ×10ⁿ).

## 4. Suggested new visuals (beyond V4) — ~60, grouped by family

**Scale & size**
1. Size ladder: objects step up in size, camera pulls back (human → city → Earth → Sun → star → black hole).
2. "Fits inside" — small discs packed into a big one ("1.3 MILLION EARTHS FIT IN THE SUN").
3. Squeeze / expand an object with a counting width (generalises the V4 Sun squeeze).
4. Map overlay: the object drawn over a known place ("THE EVENT HORIZON OVER EUROPE").
5. Powers-of-ten zoom with a ×10 ticker.
6. Density cube: same box, the mass changes ("A TEASPOON WEIGHS 4 BILLION TONNES").

**Distance & journey**
7. Mission HUD card (V4) — every journey video.
8. Route line from A to B with the craft dot and an ETA counter.
9. "Light travel" race: light vs a car / plane / rocket on one line.
10. Signal delay: message leaves Earth, counter of minutes until it arrives, reply comes back.
11. Fuel / energy meter emptying across a journey.
12. Escape velocity cone: speed needed shown as a bar that keeps rising as you go deeper.

**Time**
13. Dual clocks with ratio banner (V4/V2).
14. Deep-time log axis with events (V4).
15. Cosmic calendar: the whole history squeezed into one year, "humans appear at 11:59 PM".
16. Age counter: your age vs Earth's years ticking on two counters.
17. Hourglass draining at different speeds side by side.
18. "Time-lapse" day/night strip speeding up.

**Forces & physics**
19. Spacetime warp grid (V4) — also for stars, planets, a person.
20. Tidal stretch: body stretched by arrows, "spaghettification" meter.
21. Light paths bending (V4).
22. Field lines around a magnet / planet / star.
23. Force arrows on a body (gravity vs thrust vs drag), arrow lengths live.
24. Pressure crush: a sphere/can denting as a bar counter rises.
25. Wave on a line (sound, light, gravitational wave), wavelength stretching (redshift).
26. Spectrum bar with a marker sliding (visible → infrared → radio).
27. Particle collision / decay with labelled particles.
28. Equation moment (V4) and "variable highlight": one term of the equation lights up as it is spoken.

**Danger & survival (body)**
29. Survival clock (V1) — already built.
30. Body silhouette with organs lighting up red as each fails.
31. Vital signs monitor: heart rate / O₂ / temperature lines going flat.
32. Danger zones: concentric rings around the target ("LETHAL RADIATION", "SAFE").
33. Thermometer / pressure gauge with labelled human limits.
34. "Seconds left" countdown with a cause line under it.

**Inside / structure**
35. Cross-section "you are here" with stage marker (V4) — planets, stars, ocean, Earth's core.
36. Layer peel: outer layer lifts away to show the next.
37. Composition ring / donut (what it is made of).
38. Cutaway of a craft / suit with callouts.

**Comparison & data**
39. Two-panel POV (V4).
40. Real photo pair → focus (V4).
41. Bar race (values animating to final ranks).
42. Before / after wipe on one image.
43. Ranking ladder (the 5 most extreme...), each step reveals.
44. Scatter of real objects (mass vs size) with "YOU ARE HERE".
45. Probability / odds dial ("1 IN 10 MILLION").

**Space-specific**
46. Orbit with trail and period (V4 S2) — moons, comets, exoplanets.
47. Star map: constellation with the target highlighted and a zoom into it.
48. Galaxy top-down with "YOU ARE HERE" and the target, distance line.
49. Light curve dip (exoplanet transit) with the planet crossing.
50. Lensing of a background image (V4 hero) — any massive object.
51. Planet sky view: what the sky looks like from there (sun size compared to ours).
52. Day length / year length dials for another world.

**Story & structure**
53. Stage headers (V4) + a chapter strip at the top showing progress.
54. Question card ("BUT WHAT HAPPENS NEXT?") between acts.
55. Myth vs fact card (strike-through on the myth).
56. "Scientists disagree" split with two named theories.
57. Timeline of discovery with photos of real people/instruments (names + years).
58. Quote card from a real scientist with citation.
59. End-card question to the viewer (V4) — already in the look.
60. Recap strip: the stages flash past in 5 seconds before the end card.

## 5. Questions for you
- Go with the template system first (steps 1-4), then port V4 — or build the V4 visuals directly as layers first and move to templates later?
- Which families matter most for your next videos (space / body survival / Earth / physics)? That decides which suggested visuals go first.
