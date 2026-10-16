# What If — template library (built 2026-10-16)

Every visual is a small JSON file in `whatif-engine/templates/<family>/<id>.json`. One renderer layer (`tm_template`) draws all of them, so
a new visual needs no new code. All visuals at a glance: `docs/whatif/template_catalog.jpg` (regenerate with `node whatif-engine/catalog.mjs <dir>`,
which runs locally: no network, no credits).

## How it flows (the same path as every What If layer)
```
CSV row: layer, template, id=two_clocks_ratio, label=EARTH, value_from=2, value_to=100, hold=8
  -> whatif/shot_csv.py      checks the id (an unknown one is named, with "did you mean")
  -> whatif/templates.py     fills the slots from the columns, finds the cue words in the narration, makes the plate shot
  -> whatif/planner.py       carves the plate into the timeline (like a diagram row); auto mode may add concept templates itself
  -> whatif/compile.py       puts a fetched photo into the template's photo slot
  -> whatif-engine           tm_template builds the items (lib/tpl.mjs) and draws them (lib/prims.mjs, lib/icons.mjs)
```

## What is in it
| Part | Where | What |
|---|---|---|
| 75 templates | `whatif-engine/templates/` | 27 from V4 (black hole) + 48 suggested, in 9 families: blackhole, physics, forces, time, scale, distance, space, structure, data, story, survival |
| 24 primitives | `lib/prims.mjs` | text, number, ring, disc, line/arrow, path, dot, icon, image, panel, grid (spacetime well), particles (stars, flow, radial, orbit, squiggle, pack, fall/rise, burst), clock, axis (incl. log), rail, bar, band, equation, glow, wave, donut, blackhole (side view), callout |
| 13 motions | `lib/tpl.mjs` | draw, count, move, scale, grow, shrink, pop, fade_out, rotate, stretch, flash, colour, typewriter; plus `anim` keys on any parameter |
| 34 icons | `lib/icons.mjs` | astronaut, human, eye, star, letter (burns), rocket, heart, skull, thermometer, hourglass, satellite, planet, sun, atom ... drawn with canvas paths: nothing to download |
| Mission card | `layers/tm_mission.mjs` | V4's top-right card; CSV `hud` rows `id=mission`, one per beat, joined into one card that counts down |
| Black hole hero shots | `lib/blackhole.mjs` | ray-traced in a shader: `blackhole_disc`, `blackhole_top`, `blackhole_ring`, `blackhole_lensing`, `blackhole_horizon` |

## Adding a visual
1. Write `whatif-engine/templates/<family>/<id>.json`: `id`, `family`, `use` (one line: the CSV prompt shows it), `plate` (true = its own dark
   plate; false = drawn over the shot on screen), `hold`, `cite`, `slots`, `items`. Optional: `triggers` + `"auto": true` (only for a concept
   with no figures of its own), `image_slot`, `max_s`.
2. Slots: `{"default": ..., "from": "label|sub|text|value_from|value_to|format", "kind": "list|pairs|parts", "required": true}`.
3. Items: `{"p": "<primitive>", "at": [x, y], ..., "in": <time>, "m": "<motion>", "dur": 1.2, "anim": {...}, "each": "<list slot>", "stagger": 0.5}`.
   Times: seconds, `"40%"`, `"end-1"`, `"@word"` (when the narrator says it; `"or"` is the fallback). `"={formula}"` does arithmetic.
4. `node --test whatif-engine/test/*.test.mjs` checks every template (valid slots, every frame draws, nothing still for over 6.5 s);
   `node whatif-engine/catalog.mjs <dir> <id>` shows it. The CSV prompt lists it automatically.

## Rules kept
- Auto mode never shows template data as fact: only 14 concept templates (light bending, the spacetime well, the river model ...) are `auto`.
- No per-video assets: icons are drawn, black holes ray-traced; a template photo is the plate's one fetched picture (`image_slot`).
- One photo per template (the plate's asset). A second picture can only be a `file:` path; otherwise the template's fallback is drawn.
