# Story character (one protagonist, same in every picture)

`story_character.py` is machinery plus a dry-run planner. It makes no Flow call by itself; the live run is described below and needs approval.

## API

| Function | What it does |
|---|---|
| `character_sheet(p)` | `{"sentence", "key", "reference_key", ...}`. The sentence is the fixed, verbatim character description (face-less engraved look, age, era, clothing, silhouette, props, palette words sepia / terracotta / rust / cream, "engraved sepia paper-collage illustration, ink outlines, hand-cut paper edges"). `key` changes when any wording changes. |
| `reference_prompts(p)` | 4 reference pictures: `front34`, `fullbody`, `sidewalk`, `hands`, each on a plain cream background, each starting with the sheet sentence. |
| `select_references(shot, refs)` | At most 3 (Flow's limit): `front34`, `fullbody`, then `sidewalk` (movement) or `hands` (handling). |
| `build_character_request(shot, p, refs, ordinal=)` | One request dict: `shot_id`, `scene_number` (= shot_id), `script_segment`, `asset_type: "image"`, `prompt`, `reference_images`, `settings` (`mediaKind`, `aspectRatio`, `referenceImages`), `prompt_key`, `uses_character`. `character == false` returns `prompt_en` untouched, no references. For a character shot: `sheet sentence + prompt_en + composition hint` (character on the left/right third, alternating per character shot or `shot["character_side"]`, feet visible on a floor line, open scenery so a figure can walk in or out). |
| `to_scene_row(req)` | `providers.base.SceneRow` for the request. |
| `ReferenceStore.for_project(project, p)` | `project/state/story/character/<reference_key>/` with `front34.png` ... and `manifest.json` (prompt hash, sheet key, bytes, sha1). `add`, `list`, `validate` (exists, not empty, <= 10 MB, decodes, >= 256 px, unchanged since recorded), `is_current`. |
| `ensure_references(p, generator, store)` | Makes missing or stale references: `front34` alone, then the others with `front34` attached. Cached by prompt hash (prompt + front34's hash), so a stopped run resumes and a changed character sheet regenerates. `generator(req) -> path`. |
| `make_flow_generator(client, out_dir)` | Wraps a Flow client (`client.generate` + `wait_for`, the same protocol as `product_trailer.scenepack.generate_scene_pack`) as that generator. Tested only with a fake client. |
| `consistency_check(images, bboxes=None, sheet_path=)` | Palette histogram intersection (cream paper ignored) of each picture or its bbox against the mean of the others; flags outliers; writes a contact sheet (red frame on flagged). |
| `plan_generation(shots, p, budget, store=)` | Dry-run plan and text `report`. |

## What the consistency check can and cannot do

It compares colour palettes only. It catches a blue coat where a rust coat should be or a picture with no character colours. It cannot see a different face, cut of the coat, age, proportions or pose. The contact sheet exists so a person can look at all character pictures at once; real consistency is judged by eye. The reference pictures plus the repeated sentence are what keep the character the same, not the check.

## Plan rules

* Pictures to make: `picture == "new"` or `character == true` (a character shot always gets its own picture).
* Order: missing references (`front34` first), character shots, other new pictures. `budget={"max_images": N}` cuts the tail; references are never cut; cut shots are listed as `deferred`.
* Runs: one Flow GENERATE per identical reference set; each run is cut into agent requests of at most 24 scenes / 12000 characters (`flow-engine/config.js` `agent.maxBatch`, `maxMessageChars`; the engine may step down to 8 per request by itself).
* Cost: Flow image generation consumes no credits (`orchestrator.js`: "Only VIDEO consumes Flow credits"); the app has no per-image cost constant, so the cost is the count.

## How the live run would be done (needs approval first)

1. Settings: Flow agent mode on (Settings > Flow, `generationMode: "agent"`); any request with `referenceImages` is forced by the engine (`withReferenceSettings`) onto the UI agent route (`agentViaUi: true`, `agentFallback: false`, `agentMinScenes: 1`) and needs a signed-in Flow tab. Aspect `IMAGE_ASPECT_RATIO_LANDSCAPE`.
2. Engine running, client from `providers.flow.client` (as `product_trailer.studio` gets it).
3. `store = ReferenceStore.for_project(project_dir, protagonist)`; `refs = ensure_references(protagonist, make_flow_generator(client, project_dir/"state/story/character/_flow"), store)`. LOOK at the 4 pictures (contact sheet via `consistency_check(list(refs.values()), sheet_path=...)`) before going on; delete and regenerate a bad one by removing it from the store.
4. `plan = plan_generation(shots, protagonist, budget, store=store)`; print `plan["report"]`.
5. For each run in `plan["runs"]`: `client.generate(prompts, settings={"mediaKind":"image","aspectRatio":..., "referenceImages": run["references"], "outputDir": ...}, prompt_keys=[shot_ids])`, then `wait_for(GENERATE_DONE)`, collect `PROMPT_RESULT.path` per index. This is `generate_scene_pack`'s loop, and is the supported way because it sets references per run. The runs with `references == []` (non-character pictures) go through the same loop, or through the normal `FlowProvider` path unchanged.
6. Run `consistency_check` over the character pictures, view the contact sheet, regenerate odd ones (same `prompt_key` needs `confirmResubmitKeys`, see `FlowProvider.confirming_resubmit`).

## Gaps found in the existing reference support

1. Max 3 references per request (`MAX_REFERENCES`), not 4: the 4th reference is only used by swapping (`select_references`).
2. References are per run (settings), not per scene: `FlowProvider._resolve_batch_locked` does `settings = {..., **self.flow_settings}` for the whole batch, so a single `resolve_batch` cannot give shot 5 the hands picture and shot 6 the side view. Per-shot reference choice therefore means several runs (one per distinct reference set; `plan["runs"]` shows how many). With the typical selection (walk shots vs hands shots) it is 2 runs, but it fragments batches. Either accept 2-3 runs, or always attach the same 3 references (simplest, better dedupe; loses the hands/side specialisation).
3. `AssetManager` / `FlowProvider` have no path that carries `referenceImages` per scene; only `product_trailer.scenepack` bypasses the provider and talks to the client. A normal-style run that wants this must call the client loop itself (step 5) and place files by `shot_id` (the provider's output naming and Visual QA are skipped).
4. Every agent request re-attaches the references through the UI picker (an attached asset leaves the picker), so a 24-shot request pays several UI steps; a failed attach aborts the request with "nothing was sent" (good, no silent fallback), but a run of 60 character shots is 3 attach rounds.
5. Ledger key: `referenceKeyOf` is built from file basename + size only. Names like `front34.png` repeat across projects and a regenerated reference of exactly the same byte size would keep the key and could be treated as a duplicate. Store files are named by kind, so after regenerating a reference, also change the filename (or the prompt text) if the ledger might hold the old run.
6. No control of how strongly Flow follows a reference. A cream-background reference may leak a flat cream background into scenes; the composition hint asks for open scenery, but this must be judged on the first live batch.
7. Nothing validates image content: `validateReferenceImages` checks extension, size and existence only (the store adds decode and minimum size).
8. Live testing is blocked by Google's anti-abuse hold (see project memory); the UI attach path was exercised only in the 2026-10-28 trailer work.

## Weaknesses of this module

* Palette check only; see above.
* The sheet is long (~400 characters) and sits in front of every character prompt; Flow may weigh it above the scene content, so scene action text is repeated after it, not replaced.
* A face-less sepia figure is what the wording asks for; Flow may still draw faces. Unverified without a live run.
* `character_side` alternation is naive: it does not know the next shot's walking direction (Agent D's links can pass `character_side`).
