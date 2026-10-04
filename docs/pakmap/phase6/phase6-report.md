# Phase 6 report: pakMap inside the app

Code: `app.py` (a pakMap section and its hookup), `pakmap/app_integration.py` and `pakmap/engine_runner.py` (the Tk-free generation and the engine launcher), `pakmap/packaging.py` plus `VideoGenerator.spec` (what ships in the installer), `project_workspace.py` (its slot in the project folder). Tests: `python3 -m pytest test_pakmap_*.py` (117 tests, 24 of them driving the real app window) and `cd pakmap-engine && npm test` (106).

## What the user sees
On the **Visual Director** page, under the Overscaled / Exp Solar block, there is a **pakMap (satellite-map videos)** block with:
- a switch "Use pakMap for this generation" (turning it on turns Overscaled off, and the other way round);
- a **CSV** picker;
- a **Channel name** field (the text shown bottom right of the video; empty = none; saved with the project and remembered as the default for the next one);
- a **Check plan** button and a **plan box**: it reads the narration (the project's cached Whisper alignment, or a new transcription with the same model setting as the other styles), compiles the script against it, and shows every layer with the time it lands and what it was matched to ("on \"around nairobi\"", or PROPORTIONAL if it was guessed), the camera moves, warnings and errors, each naming its CSV row;
- a status line.

There is no second Generate button and no second voiceover importer: the **shared main button** drives it. It reads *Import pakMap CSV* until a script is loaded, *Import Voiceover* until there is narration, then *Generate*; while running it is *Stop*. Generate checks the plan again and refuses to start (with the plan box showing why) if the script has problems; otherwise it draws the map video, adds the narration through the app's existing exporter, validates the result (video and audio streams present, length matches the narration), saves it in the project's `final/` folder with the usual naming (re-rendering never overwrites), shows the preview and tells the user where it is.

## Project behaviour
- The script is copied into the project (`csv/pakmap_script.csv`), together with the folder it came from, because its picture and clip paths are relative to that folder. Reopening the project restores the script, the channel name and the mode (unless the project is an Overscaled one).
- The compiled render spec, the plan report and the silent map video are kept under `pakmap/_work/`. The required credits (NASA acknowledgement, "Landsat is historical, not current" when it is used, dataset credits) are written next to the video as `<name> - credits.txt` and echoed to the log, so they are not lost.
- The NASA tiles are cached per user (`.../SemanticYTStudio/pakmap`), downloaded on first use.
- Stop ends the renderer process at once and removes any half-written file.

## Real-speech fixes found by running it end to end
A real voiceover (synthesised from the sample narration) was transcribed with the app's Whisper and fed through the whole chain. This exposed things a typed script hid, all fixed and tested:
- Whisper writes "250" and "2,000" where the script says "two hundred and fifty" / "two thousand": the matcher now understands spoken numbers up to the thousands (and years: "nineteen eighty four" = 1984).
- A name heard as two words ("Marsa Bit") is found; one heard as something else entirely is not guessed, but the error now says what was actually heard and when ("The closest words heard are 'marcebid' at 10.6s: use that spelling in vo_anchor, or give t_start").
- Two bugs of mine in the tests: they were writing the channel name into the real `settings.json`; they now use a throwaway settings file, and the stray value they left was removed.

## Packaging
`VideoGenerator.spec` ships `pakmap-engine/` through `pakmap/packaging.py`: the renderer, its page, the font, the bundled data (2.7 MB), the plan-check tool, the MapLibre runtime files and the GeoTIFF reader with its small dependencies (about 7 MB, 214 files); tests, samples and the dataset build tools stay out. In a packaged app the plan check uses the app's own Node. **I could not build the installer here, so the packaged layout is tested as a file list only, not as a running installed app.**

## A real run, end to end
The sample script (`pakmap-engine/samples/kenya-story.csv`) with a real voiceover (the sample narration spoken by macOS `say`), real Whisper (`base`) word times and the real NASA imagery, through `generate_pakmap_video` (the same function the app's button calls): **ok, 97 s, a 1920x1080 video with audio, 39.02 s long** (video 38.97 s, audio 39.02 s), the credits file written beside it. Spot checks against the spoken words: the Nairobi marker appears at 5.8 s ("around Nairobi" is said at 6.1 s), Part 2's title swaps in at 20.9 s (0.5 s after Part 1's layers clear), the rainfall layer comes on at "Yet the north gets less", and Poland's outline at "Poland is as big" (31.5 s). Files: `real-run-preview.mp4` (960x540 copy), `real-run-frames.jpg`, `real-run-plan.txt`, `real-run-credits.txt`.

## Checked
| Check | Result |
|---|---|
| Mode switching, button states, loading good and bad scripts, channel name saving, full run, failure, Stop, missing voiceover, reopening a project | 24 checks in the real app window, pass |
| Removing the Generate dispatch makes those tests fail | yes (12 failures), then restored |
| Generation without the UI: valid video with narration, spec follows the voiceover and settings, credits file, progress, script problems stop before drawing, renderer failure messages, Stop, wrong inputs | pass |
| The real engine through the runner: render, progress, error message, Stop leaves nothing behind | pass |
| Packaged file list contains what the renderer loads and nothing else | pass |
| The existing Overscaled, map scene and workspace tests | still pass |

## Not done / limits
- **PiP and b-roll from Flow or stock sites.** The plan imagined pakMap pictures coming from the existing Flow/stock providers with per-scene Retry. Phase 6 uses pictures and clips the author supplies (`asset_path` is a file). `stock:` / `flow:` sources were added in Phase 8 (`phase8/sourcing.md`); the Visual Plan table with per-picture Retry is still not built (delete a saved picture to refetch it).
- **The plan box is text**, not the Visual Plan table, because pakMap layers are not scenes with acquired assets.
- **Data-layer pickers** are CSV columns (`data_source`), not a dialog.
- The globe zoom-out defect from Phase 1 was open at this point; fixed in Phase 8.
- An installed (packaged) build was not exercised.
