# Roblox Cinema Engine

History told in a block-toy 3D world, planned from narration and rendered in code. A story (a CSV, or plain narration) becomes scenes, a cast of
different block people, vehicles, camera moves, tabletop maps, effects, on-screen text, and a sound mix, cut to a voice-over. Nothing is
downloaded per video: every model, texture and sound effect is built in code or taken from the app's bundled, licensed library.

## Use it

From the app: pick **Roblox Cinema** in the style picker (Documentary group), choose a story CSV or paste narration, optionally a voice-over,
click **Generate** (plans the film, shows scenes/duration/notes), then **Render**. Nothing starts before Generate.

From a terminal (repo root = `video_generator-main`):

```bash
cd roblox-cinema-engine
python3 tools/make_vo.py samples/dday_1944.csv out/vo.wav                      # stand-in test voice (macOS `say`) -- PLACEHOLDER
python3 tools/narration_timing.py out/vo.wav out/words.json base               # word times (faster-whisper, local)
node render.mjs --csv samples/dday_1944.csv --words out/words.json --out out/film_silent.mp4 --preview   # 720p; --final = 1080p
python3 tools/mix_audio.py out/film_silent.mp4 --voice out/vo.wav --video out/film_silent.mp4 --final out/film.mp4
python3 tools/qc_video.py out/film.mp4 out/film_silent.mp4.plan.json           # frozen frames, jumps, black frames
```

Useful flags: `--plan-only` (plan + cue list, no render), `--stills 3,12.5` (JPEGs of those moments), `--clip 20,30`, `--soft` (software GL),
`--no-music`, `--credit "text"`. `render.mjs` prints one JSON event per line (progress, perf, warnings, done).

## The story CSV

One row per plan / chapter / beat; only a beat's `text` is required, everything else is inferred (and shown with its reason in the plan) unless you
fill it in. Columns: `row, id, chapter, text, date, location, event, environment, time, weather, characters, actions, vehicles, props, effects,
camera, subtitle, audio, transition, duration, extra` (full description at the top of `lib/csv.mjs`). Example row:

```
beat,b12,,"At Omaha Beach, the landing craft dropped their ramps under heavy fire.",,Omaha Beach,landing_operation,beach,,overcast,"soldier*24",,"landing_craft*4>approach_beach",,,"tracers_in; explosions",,,,
```

Vocabulary: 28 event recipes, 22 environments, 33 vehicles, 30 animation states, 21 camera behaviours, 7 transitions (all listed in `lib/*.mjs`;
`validateStory` reports unknown names by line). Plain narration works too: `# Title` lines are chapters.

## What is where

| Folder | |
|---|---|
| `lib/` | Pure logic (Node and browser ES modules): CSV, narration reading, gazetteer, eras, characters, animation, worlds, vehicles, stage, camera, effects, recipes, the director. Same input -> same output everywhere. |
| `web/` | The three.js page: asset cache, characters, vehicles, worlds, tabletop map, effects, light/sky/post, HUD, runtime. |
| `render.mjs` | Local server + headless Chromium on the GPU + frame pipe to ffmpeg; plan, stills, clips, perf report, cue list. |
| `runner.py` | The app's entry (plan / render / mix). |
| `tools/` | `make_vo.py`, `narration_timing.py`, `sfx_synth.py`, `mix_audio.py`, `qc_video.py`, `sheet.py`. |
| `samples/dday_1944.csv` | The 2-minute demo story (D-Day, 5 chapters, 17 beats). |
| `test/` | `node --test test/*.test.mjs` and `python3 -m unittest discover -s roblox-cinema-engine/test` (from the repo root). |
| `docs/` | `ARCHITECTURE.md`, `REFERENCE_ANALYSIS.md`, `HANDOFF.md` (history), `FINAL_REPORT.md` (measured results). |

## Honest limits

* The sound effects are procedural stand-ins (filtered noise and envelopes), not studio recordings. The ambience beds are the app's bundled library.
* The test voice-over (`make_vo.py`, macOS `say`) is a placeholder for the app's real voice step; it exists to give real word timing.
* Maps use present-day Natural Earth borders and approximate city positions; the film says so on screen. Historical borders are not drawn.
* Insignia and flags are not drawn; factions are told apart by uniform colour and kit only. No gore.
* Transport aircraft read best by day; at night their model is dark and thin. Snow has fog and grade but no falling flakes yet.
* The `mix_audio.py` step runs with the Python that runs the app (it needs numpy, ffmpeg, the app's `health_cinema` ducking function).
* Music: Kevin MacLeod tracks bundled with the app (CC BY 4.0); the credit is drawn at the end of the film.
