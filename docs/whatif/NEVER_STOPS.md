# What If never stops (2026-10-16)

The same approach as Weather (`weather/guard.py`, `weather/stress.py`) and StarMap (`starmap/heal.py`): a mistake in a CSV, a missing
picture or a GPU hiccup is repaired or left out and written to the log. It never ends Generate.

## The layers of protection
| Stage | What can go wrong | What happens now | Where |
|---|---|---|---|
| Load CSV (panel) | semicolons, no header, Excel encoding | accepted; repaired at Generate | `whatif/heal.py` `read_text`, `looks_usable` |
| Plan | row/kind/source/scene/model/texture typos, broken `extra` JSON, words in number columns, NaN/inf, unknown layer/template/diagram/hud ids, annotate without x/y, layers before shots | repaired (aliases, closest match) or the row is left out; the rest is read again | `whatif/heal.py` `heal`, `read_healed` |
| Plan | a layer row that cannot be drawn (compare with one side, template missing a required value ...) | that row is left out | `shot_csv.layers_from_rows(notes=...)` |
| Plan | no usable shot at all / the planner fails on the CSV | planned from the narration alone | `app_integration.plan_from` |
| Plan | no transcript | the CSV's shots are spread evenly over the voiceover | `heal.read_healed` |
| Compile | a graphic with a broken number | left out; if compiling still fails, compiled again with only captions/titles/numbers | `compile._finite_layers`, `generate_whatif_video` |
| Render: shots | unknown kind or hero scene, missing file, corrupt clip, 3D model missing, WebGL fails | that shot is drawn as a plate | `lib/shots.mjs` `sanitizeShots`, `page.js` `drawShot`, `render.mjs`, `cutter.mjs` |
| Render: graphics | unknown layer type, bad layer data, a layer that throws while drawing | left out / switched off for the rest of the video | `lib/layers.mjs` (lenient `instantiate`, guarded `runLayers`) |
| Render: templates | a slot value the template cannot use, a CSV value starting with "=" | defaults for that slot / shown as written; a broken item is switched off | `layers/tm_template.mjs`, `lib/tpl.mjs` |
| Render: frames | one frame fails twice | the frame before it is repeated | `render.mjs` |
| Render: whole run | browser / GPU failure | retried once with 3D on the CPU (SwiftShader) | `generate_whatif_video`, `engine_runner.render_spec(software_gl=True)` |
| Sound | sound design or loudness fails | narration only / not normalised (already) | `generate_whatif_video` |

Every repair is logged (`[What If] ...`, `[What If] the renderer will repair: ...`) and shown by **Check plan**, which now runs the full
dry run (`whatif/preflight.py`: plan -> compile -> `whatif-engine/tools/check_spec.mjs`, the page's checks in node with no browser).

## Measured
`python -m whatif.stress ~/Downloads/VideoGenerator/Video_2026-10-16_013_nnnn --mutants 800 --seed 9` (25 row mutations + 5 text
mutations + an early-ending transcript; bases: project 013 and a built-in black hole journey with templates and the mission card):

| | broken plans | stopped |
|---|---|---|
| before (the strict reader, `--baseline`) | 300 | 229 (76 %) |
| after | 1,200 (seed 2) + 1,600 (seed 9) | **0** |

A real browser render of a deliberately broken spec (missing picture, missing and corrupt clips, unknown hero scene, missing 3D model,
unknown layer type, bad template values, a mission card with a word for its number) finished, with every repair reported.

## StarMap
`python -m starmap.stress <projects>` (new) runs the same kind of test through StarMap's read -> resolve -> compile with its repairs.
First run on projects 011, 012, 014: 19 of 300 stopped, from two gaps in `starmap/heal.py` (a semicolon/tab CSV was not recognised;
a broken `extra` on the plan row looped until the reader gave up). Both fixed and tested (`test_starmap_heal.py`); rerun with new seeds: **0 of 300** stopped.

## When a new stop shows up in a real project
Add the way it broke as a mutation in `whatif/stress.py` (or `starmap/stress.py`), fix it in `heal.py` / the renderer guard, rerun the
stress test until it reports 0.
