# Phase 5 report: CSV compiler and narration timing

Code: new Python package `pakmap/` (stdlib plus the repo's existing `map_scene` place data) and engine additions in `pakmap-engine/`. Tests: `python3 -m pytest test_pakmap_*.py` (56 pass, including a real render of a compiled script) and `cd pakmap-engine && npm test` (106 pass). Author guide: `../csv-reference.md`. Preview: `story-preview.mp4`; frames: `story-frames.jpg`; what the compiler prints: `plan-report-sample.txt`.

## What it does
`python3 -m pakmap compile script.csv --words words.json --out spec.json [--watermark "Channel"]` reads the one-row-per-event CSV and the narration's word timestamps (the Whisper `(word, start, end)` shape the app already uses; `python3 -m pakmap words narration.txt` makes an estimated list when no audio exists yet) and writes the render spec for the engine, plus a plan report.

- **Anchoring to words.** `vo_anchor` is a phrase from the narration; the layer appears on its first word (`|end` for the last, `offset_s` to nudge). Matching ignores case and punctuation, accepts plurals, small spelling variants and one extra spoken word, treats "forty seven" and "47" as the same, and searches forward so a name said twice is found where the script says it. A phrase that can't be found is an error naming the row; going backwards in the narration is a warning.
- **The reference's timing rules.** The title lands 0.14 s before the item's first word; a fixed 0.5 s clear beat ends one item's layers before the next item's first event; the last item runs to the end. Layers get the default hold times from the spec unless the row says otherwise, and are cut at the clear beat with a warning that says why.
- **Unanchored rows** are spread evenly between their neighbours and marked PROPORTIONAL in the report.
- **Places.** `geo_ref` accepts `lat,lon`, ISO codes, countries, states, counties, named regions (the existing `map_scene` data) and 7,342 cities (new name index built from Natural Earth). A bare name is a city for markers/routes/stickers and an area for fills/overlays/dots, so "Nairobi" does the right thing in both. Misspellings suggest the closest name.
- **Camera.** `camera_action` on any row (or camera-only rows): start, fly_to, push_in, pull_back, drift, framed by place + `frame` (globe, continental, country, region, local) or lat/lon/zoom. Overlapping moves are shortened with a warning; moves too close together, or a move without a target, are errors.
- **One set of rules.** The compiler runs the renderer's own validator (`pakmap-engine/tools/validate_spec.mjs`), so the limits (2 stat chips, 5 text layers, sticker vs photo card, interlude vs camera, 5 s silence) live in one place. The errors now name the layers involved ("6 text layers are on screen at 14.64s ...: hud (2), nbo, vic, north, z1. Shorten one with hold or t_end.").
- **Every row problem names its row**, as a spreadsheet shows it, and a comma inside an unquoted cell is explained instead of silently shifting columns.

## Added to the engine for this
A `fill` event (a translucent region with an outline, timed like any layer; from a country code or from inline polygons, so counties and named regions work), the city name index (`data/places_index.json.gz`), and the validator tool.

## Checked
| Check | Result |
|---|---|
| Events land on the spoken words (to 10 ms) | yes, including `offset_s`, `|end`, explicit times |
| Title leads by 0.14 s; clear beat is 0.5 s; last item runs to the end | yes (tested) |
| Same words used by two rows; repeated phrase; out-of-order; spelling variant; spoken numbers | yes |
| Every error names its row; every layer type compiles to what the renderer expects | yes (28 compiler tests) |
| Renderer rules reached from Python and shown with layer names | yes |
| The sample script (Kenya, 2 items, 21 events, 1 camera move) compiles, validates, and renders through the real engine with all its layer types | yes (a Python test renders it) |
| Earlier suites | the 82 earlier engine tests and the map-scene tests still pass |

## Honest limits
- **Timing comes from the transcript you give it.** The sample uses estimated word times (`pakmap words`); with the real Whisper words each layer lands on the spoken word. The app has to hand over those words (Phase 6).
- **Spoken numbers beyond 0-99** ("two hundred and fifty" works because each word matches; "four point four million" is matched word by word, not as a quantity). Anchor on a nearby plain word if a number won't match.
- **Cities need the Natural Earth list** (7,342 places); a village not in it needs `lat,lon`. There is no online or AI lookup (a wrong map is worse than no map).
- **Sub-country regions for data layers:** fills accept any area the map data knows, but `value_overlay`, `ghost_shape` and the `dots` region filter work with countries (or a bounding box for dots).
- **No automatic layout checks yet:** the compiler does not detect two chips covering each other or a card covering the subject (Phase 8). The CSV-writing prompt (turning a script into rows) is also Phase 8.
- The globe zoom-out defect from Phase 1 was open when this phase was written (the compiler warned when a pull-back ended in the globe range). Fixed in Phase 8; the warning is gone.
