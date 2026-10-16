# "What If" style — build plan (one pass)

Goal: a new, separate editing style whose output is indistinguishable in editing language from the three reference videos
(How Long Could You Survive on Venus? / What If You Traveled at the Speed of Light? / What If You Tried to Travel One
Light-Year?). It is NOT StarMap: no 3D universe as the base, no StarMap camera, no StarMap look.

## 0. Separation from StarMap
- New packages: `whatif/` (Python pipeline) and `whatif-engine/` (Node + headless Chromium renderer, frame-by-frame to ffmpeg).
- New style card "What If" in the style picker, its own tab section, own CSV prompt, own project settings.
- The Cosmic Telemetry additions made inside StarMap on 2026-10-16 are moved out: the tm_* graphics, telemetry.py logic and
  word alignment go to the new style; StarMap goes back to Classic only (only those additions removed; the other uncommitted
  StarMap work is untouched).

## 1. Measure the references (targets, not guesses)
Shot-by-shot log of all three videos (cut detection at a low threshold + frame sheets every 1 s, classified by hand):
shot type, length, what in the narration triggered it, graphic on screen, HUD state, citation text, transition.
Output `docs/whatif/reference_targets.json`: average / median shot length, shot-type mix per act, % runtime with graphics,
HUD per act, callouts per minute, fade-to-black count, colour palettes per subject (Venus warm, deep space slate).
Every later check compares against this file.

## 2. The five shot types (what each sentence can become)
| Type | Reference examples | How we make it |
|---|---|---|
| A. Hero CG scene | Venera on the ground, parachute in clouds, airship, ship with engines | Flow image (free) in a locked "house render" style, then Flow video for motion where available; else the still with slow parallax push. Same craft reused across shots (first image as reference) |
| A2. Real craft hero | Voyager in a starfield, DSN dish | NASA public-domain 3D model (GLB) rendered in whatif-engine over a star field, slow drift; real photos where they exist |
| B. World plate | Venus globe, Earth vs Venus, Jupiter, Milky Way | NASA real image (cited REAL IMAGE · MISSION, YEAR · AGENCY) or textured globe render; Flow for views no probe took |
| C. Diagram plate | light-time log axis, bars, curve, cross-section, dial gauge, timeline, comparison cards, particle boxes, waveform flatline, instrument grid, phase diagram, orbit-from-above with YOU path | whatif-engine diagram layers (tm_* moved + the missing ones) |
| D. Archive | Venera panoramas, Pale Blue Dot, launch film, test chamber | NASA image/video library matched on the exact craft/event; stock only for generic Earth context; never a generic rocket for a named craft |
| E. Type moment | "464 °C", "1.4 SECONDS / AT THE SPEED OF LIGHT", title card, closing question | typography layers over A/B/C |

Persistent per act: survival clock, Earth/traveller clocks, light-from-Earth dial clock, altitude gauge, date top-right.
Always: monospaced citation bottom-left (ILLUSTRATION / DIAGRAM · … / REAL IMAGE · …).

## 3. Shot planner (the core)
Narration (Whisper words, aligned back to the script so "4.2" and "96.5%" stay exact) -> clauses -> one shot per clause
group, ~4.2 s average, cuts only at clause ends / pauses, visual 0.1 s before the word. Rules from the references:
- named craft / mission / place -> that exact thing (A2 / D / A), never generic
- a process or mechanism -> diagram (C); a number -> callout (E) on the current shot; a ratio -> comparison plate;
  a light-time distance -> log axis; years of events -> timeline; a composition -> composition bar
- sequence grammar per idea: context (wide) -> mechanism (diagram) -> proof (archive) -> consequence (HUD change / fade)
- no base asset repeated within 90 s; a revisited world changes framing (globe -> cloud tops -> surface)
- survival / descent / light-speed stories pin their instrument for the act
- death or silence -> fade to black in the pause
Two ways in, same as the other styles: the AI writes a shot CSV from the new prompt (one row per shot), and the planner
fills and checks it automatically (missing callouts, holds over 6.5 s, wrong-type shots).

## 4. Assets (one-time library, never per video)
Downloads approved 2026-10-16: NASA 3D Resources GLB models (Voyager, Cassini, Juno, New Horizons, Parker Solar Probe,
Perseverance, Curiosity, JWST, Hubble, ISS, Apollo CSM/LM, SLS/Orion where available) and NASA planet textures, each
listed with size and credit in `whatif-engine/assets/CREDITS.txt`. Inter + Montserrat already bundled; JetBrains Mono (OFL)
for the data/citation line. Flow images: free, used for every type-A shot. Flow videos: used for type-A motion where the
account allows (known Google hold risk: falls back to the still + parallax, never blocks a render, never retried in a loop).

## 5. Renderer (whatif-engine)
Shots in sequence with hard cuts (85%), push/zoom transition into a world (10%), fade to black (5%, death only); every
still drifts 1.00 -> 1.04; grade per reference (desaturated, lifted slate blacks, warm for hot worlds); film grain + soft
vignette; HUD and citation layers; GLB craft scenes; frame cache per shot so an edit re-renders only its shot.

## 6. Sound
Ambient drone-led music bed ducked ~15 dB under the voice; soft UI ticks on data, sub-bass on huge objects, low muffled
hit + low-pass on blackouts; no bright trailer whooshes.

## 7. Validation (in the same pass)
Three 60–90 s test videos on the three reference topics (my own scripts, TTS narration), through the real app pipeline.
Each checked against reference_targets.json (shot length, type mix, graphic coverage, HUD, citations) and by side-by-side
frame strips with the matching reference moments; fixes until they match. Regression: StarMap and the other styles' tests.

## 8. Order of work (one go)
1 measure -> 2 separate from StarMap -> 3 whatif-engine (shots, cuts, drift, grade, layers moved + new diagrams, GLB scene)
-> 4 downloads -> 5 planner + shot CSV + prompt -> 6 Flow image/video + NASA asset routing -> 7 app card/tab -> 8 sound
-> 9 tests -> 10 three test renders + comparison -> fixes -> report. Nothing committed without asking.
