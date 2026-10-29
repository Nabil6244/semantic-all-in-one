# Health Cinema: handoff prompt for a new Claude session

Paste everything below the line into a new Claude Code session opened in `/Users/muhammadnabil/Downloads/video_generator-main`.

---

You are continuing work on the **Health Cinema** style of the Semantic YT Studio video app (Python package `health_cinema/`, Three.js renderer in `health_cinema/threejs/`). Read this whole brief first, then act.

## Goal
Render a very high quality, engaging 1080p video from my narration `/Users/muhammadnabil/Downloads/76d6e51f44544c4080b17bcd8c6d7757.mp3` (6:03, a heart-attack explainer) using the tool. **Do not burn my credits**: no Gemini calls, no Flow, no YouTube. Free Pexels/Pixabay stock footage only. Do not commit or push anything without my explicit approval. Ask before downloading files.

## Rules of working
- Another Claude session edits other files in this repo at the same time (puppet/paper-cutout work in `health_cinema/app_section.py`, `puppet*.py`, `visual_composer/`, `whatif/`, `explainer/`, `product_trailer/`, `ui/`, `app.py`, `smart_editing.py`, `video_generator.py`, `test_puppet_*.py`, `test_health_cinema_bugfixes.py`). Leave those alone. Four files contain BOTH my edits and theirs (`health_cinema/engine.py`, `planner.py`, `scenes_csv.py`, `docs/health_cinema/CSV_GENERATOR_PROMPT.md`); when committing, stage only my hunks.
- Check `test_fixtures/*_protected.json` before editing shared files (`asset_manager.py` and `providers/stock/*` are protected: do not edit them).
- Verify with real renders and look at the frames. Report problems honestly.

## What exists (committed as 69b5089, plus uncommitted work below)
- Pipeline: `engine.run_health_cinema(...)`; High-end edit = `edit="high_end"` (`health_cinema/edit/*`: director, shots, pipeline, audio, typography, data shots).
- **CSV directs the visuals** (no AI planning): columns `visual` (footage|3d|text|chapter|counter|bar|timeline|stat|flow|youtube), `organ`, `shot` (orbit|zoom|peel|isolate|fatty|inflamed), `footage`, `footage_alt`, `source`. `direction.dscenes_from_rows` builds the plan; `planner.plan_directed` obeys the hints. See `health_cinema/scenes_csv.py` docstring and `docs/health_cinema/CSV_GENERATOR_PROMPT.md`.
- **3D library** `health_cinema/library.py`: organs from prepared models in `~/HealthCinemaTools/bench/` (chest, head, abdomen incl. kidneys from BodyParts3D CC BY 4.0, musculoskeletal), generated journeys `auto:<organ>:<shot>`, procedural illustrations `micro:<blood_flow|plaque|clot|cell|fatty_cell>:<orbit|zoom>` (`threejs/procedural.js`). Prep scripts in `health_cinema/bench/`.
- **Relevance gate** `health_cinema/relevance.py`: stock clips judged by page title / Pixabay tags; wrong body part never shown; retries use the CSV `footage_alt` first.
- Reports: `docs/health_cinema/visual_sources_stage1.md`.

## Uncommitted work done after the commit (keep it, verify it, then ask me to commit)
1. **Footage cut/jump bug fixed** (`edit/director.py`, `edit/shots.py`, `edit/media.py`): the High-end director used to split every stock scene >5.6 s into two shots from the same clip with 0.6 s of source skipped (and reused earlier parts of short clips). Now each stock clip plays straight through; a clip shorter than its scene is slowed up to 2.5x (`speed`), never looped.
2. **Repeating 3D scenes** (`planner.py`, `library.apply_variant`, `clips.template_spec(name, variant)`, `procedural.js`): the n-th use of the same 3D template gets `variant` n (different camera side, seed, flow direction, wall tint, plaque position).
3. **Boring 3D backgrounds fixed**: new `health_cinema/threejs/atmosphere.js` (graded backdrop per theme, depth fog, floating motes, slight camera drift) wired in `page.js`, `render.mjs`, `render_journey.py` CODE_FILES, `packaging.py`; plus out-of-focus background vessels and cells in `procedural.js`. Micro specs carry `theme` and `fog_density`.
4. **Graphic cards from the CSV** (`scenes_csv.py`, `direction.py`, `planner.py`, `edit/director.py`, `clips.py`): `visual=stat` (columns `stat`, `stat_unit`, `stat_label`, `stat_kicker`, `stat_source`), `visual=timeline` (column `events` = `when: what | when: what`, each event appears when its first word is spoken), `visual=chapter` (`card_title`, `card_kicker`). Numbers must come from the narration; the card says "From the narration".
5. Tests: `test_health_cinema_library_csv.py` (incl. `TestCsvCards`, `TestRepeatedScenesDiffer`), `test_health_cinema_edit.py` (continuous footage tests). Run: `python3 -m unittest test_health_cinema_library_csv test_health_cinema_visual_sources test_health_cinema_scenes_csv test_health_cinema_edit test_health_cinema_cache test_health_cinema_journey test_health_cinema_direction.TestDirectedPlanning` (about 3 s; the full Health Cinema suites take about 3.5 minutes).

## The video job (state when I stopped)
- Transcript with word times: `out/hc_video/words.json` (made locally with faster-whisper "small", free). 67 segments.
- Render script: `out/hc_video/render.py` (`python3 out/hc_video/render.py final`; `--plan` writes `out/hc_video/rows.json` only). It builds a 40-row plan from the transcript segments (3D rows, footage rows with `footage_alt`, 3 stat cards: "60 seconds", "100,000 heartbeats", "1122 in Pakistan"; one timeline "What happens to the heart"; 3 chapter cards), strips every Gemini key from the settings, and renders High-end at 1920x1080/24 fps with the app's bundled music and SFX. Output name is set in the script (currently `heart_attack_final_v5.mp4`).
- Earlier results: `out/hc_video/heart_attack_final.mp4`, `_v2`, `_v3` (v3 is the last finished one, 6:03, about 1.2 GB; it still has the footage jump bug, repeating 3D scenes and flat backgrounds). A v5 render was running with all fixes and **I stopped it unfinished**. Re-run it: it takes about 30 minutes (journeys re-render because `procedural.js`/`page.js` changed; footage is cached in `out/hc_video/proj/state/health_cinema/assets`).
- Known weak spots to check in the new render: (a) any stock clip that still looks wrong or jumps (compare frame differences inside each footage scene); (b) "Source needed" text must not appear on cards; (c) 3D scenes that are very short get compressed camera moves (flag `3d_short`), consider merging rows; (d) label legibility on plaque/clot scenes; (e) the heart journey opens on the lungs; (f) clot/plaque are conceptual illustrations, labelled as such.

## What I want now
1. Run the tests above; fix anything that fails.
2. Re-render `out/hc_video/render.py final`, then extract a contact sheet (one frame per scene) and also check **continuity** of every stock scene (no jump, no restart) and that the new cards, typography and 3D backgrounds look cinematic. Fix problems and re-render if needed.
3. Tell me the output path, size, duration and a list of anything still weak.
4. When I approve, commit only my files (not the other session's) without pushing.
