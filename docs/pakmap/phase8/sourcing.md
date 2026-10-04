# Phase 8: pakMap pictures go through the Visual Plan tab

**Problem.** pakMap fetched its own Flow / stock / YouTube pictures in a private folder the Visual tab could not see: no Retry, no Change source, no per-picture errors, only CSV edits.

**What the Visual tab expects (inspected, not assumed).** `app._scene_rows`: a list of `SceneRow` (scene number, text, `asset_type`, prompt), with state restored from an `AssetManifest` (`.asset_manifest.json`) in an images folder. Every per-scene action (Retry, Change source, Skip, Local clip, Flow batch) runs on the real `AssetManager` for the folder `_scene_action_images_dir()` names, and a manual pick is stored as `user_override`, which `AssetManager._cache_hit` keeps on later runs. Overscaled already uses this by filling `_scene_rows` and pointing the folder at its own.

**What pakMap does now.**
- Loading the script lists every `stock_image:` / `flow_image:` / `youtube_video:` ... reference as a Visual Plan row (`pakmap/sourcing.py`: one numbered row per use, in script order). The row text names the layer and the narration it is tied to; Check plan puts the second in front.
- The folder is `<project>/pakmap/_work/media` (`ProjectWorkspace.pakmap_images_dir`); `_scene_action_images_dir()` returns it in pakMap mode, so the existing actions write there.
- Generate passes the table rows as the user left them (a changed source included) to `fetch_scenes`, which calls the existing `video_generator.resolve_scene_assets`; saved and replaced pictures are reused, not fetched. Each picture is read back by scene number and swapped into the script at compile time (`media_map` keyed by CSV row and part). The CSV file is never edited.
- Live progress uses the same queue messages the other styles use (`scene_busy`, `scene_asset`), so rows go Queued → Generating → Ready / Needs action while it runs; Stop also stops the picture batch.
- Errors: a picture that cannot be found stops the run before drawing, shows as Needs action in the table, names the picture, and opens the Visual Plan tab. Retry / Change source / Skip work as in every style; Skip leaves that layer out with a warning. Compiler problems are shown tied to the layer ("Row 12 (marker NAIROBI): ...") with the raw text kept under "Technical details" and in the log.
- Flow credits: the app asks before generating anything new with Flow; saved pictures cost nothing.
- Map layers (fills, markers, lines, dots) are not rows: they have nothing to replace and stay in the plan text. They are deliberately not given `asset_type=map`, which would route to the Map Facts renderer.
- Switching pakMap off, or switching to another style, takes pakMap's rows out of the shared table.

**Not changed:** `video_generator.py`, `asset_manager.py`, `providers/*`, `scene_graph/*` (Overscaled, Exp Solar), `map_scene/*` and `map-engine/*` (Map Facts), `pakmap-engine/*` (renderer), pakMap audio. In `app.py`: pakMap hooks only, plus one optional argument on `_hydrate_overscaled_assets_from_manifest` (the default is unchanged, so Overscaled behaves as before).

**Limits.**
- The CSV is still what the AI writes and what you import; the Visual Plan holds your picture choices on top of it (in the manifest), so the CSV itself is not rewritten. Editing the CSV text of a picture after you replaced it keeps your replacement (the same rule as the other styles).
- Local-file pictures are the author's own and are not rows.
- Only pictures are Visual Plan rows. Changing a place, a number or a camera move is still a CSV edit; there is no automatic repair of compiler problems yet.
- The renumbering rule: rows are numbered by position, so inserting a picture row in the middle of an already-fetched script renumbers the later ones (their saved files are matched by number and by the prompt recorded with them; a mismatch is fetched again).
- Run against fake and stub providers only; not against the real Flow, stock or YouTube in this phase.

**Tests:** `test_pakmap_sourcing.py` (37) and the Visual Plan section of `test_pakmap_app_integration.py`. Including: the real `AssetManager` honouring a replacement with no provider; its real Change source (Flow, YouTube) and Local clip and Retry actions, with stub providers, each followed by a real fetch that returns the replacement; a replacement reaching the compiled spec; a real render with the real engine showing the user-placed picture inside the card; the table rows, folder, live callbacks and error navigation in the live app.
