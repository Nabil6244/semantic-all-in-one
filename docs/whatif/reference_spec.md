# What If — reference specification (measured, 2026-10-17)

Sources: the three reference videos in ~/Downloads (1280x720, 24 fps, 10:46 / 11:15 / 10:50):
**V1** How Long Could You Survive on Venus?, **V2** What If You Traveled at the Speed of Light?, **V3** What If You Tried to Travel One Light-Year?
Scripts: `docs/whatif/analysis/measure_reference.py`, `cuts_vs_speech.py`; raw numbers `analysis/ref{1,2,3}*.json`. The Google AI Studio report is
supporting only; where it disagrees with the video, the video wins (table at the end).

## 1. Measured rhythm and audio

| Measure | V1 Venus | V2 Light | V3 Light-year | Note |
|---|---|---|---|---|
| Hard cuts per minute | 7.5 | 5.7 | 4.6 | Google report said 12-18 |
| Hard-cut shot length: median / p10 / p90 (s) | 6.4 / 3.0 / 14.6 | 9.1 / 4.5 / 17.1 | 9.8 / 4.1 / 29.7 | p90 long holds = graphics that evolve inside one shot |
| Any visual change (graphic build, HUD, callout) per minute | 9.7 | 7.5 | 10.3 | median gap 5.0 / 6.8 / 4.8 s |
| Cuts that land in a narration pause | 82 % | 65 % | 80 % | random baseline 42 / 35 / 29 % |
| Cuts inside speech | 18 % | 35 % | 20 % | the reference DOES cut mid-speech, on a word start |
| Visual changes in a pause | 74 % | 66 % | 59 % | |
| Pauses >= 0.2 s per minute / median length | 26 / 0.55 s | 24 / 0.55 s | 21 / 0.50 s | |
| Integrated loudness / loudness range / true peak | -14.0 LUFS / 3.9 / -1.7 dBFS | -14.0 / 4.2 / -1.4 | -14.0 / 3.8 / -1.6 | all three normalised to -14 LUFS |
| Music+ambience bed below speech (5th vs 70th percentile of 50 ms RMS) | 13.8 dB | 15.3 dB | 18.9 dB | the report's 14-18 dB is right |
| True silence >= 0.4 s at -55 dB | none (only the last 0.4 s) | none | none | "silence" moments are fades/low bed, not digital silence |

Not measurable from the mixed audio (narration continuous): the exact sound-effect events. Observed by ear/waveform around graphics: soft
clicks at HUD/number changes, a low muffled thud at titles and at the survival verdict. Sound-effect timing stays an estimate.

## 2. Shot types seen (with timestamps; frames in scratchpad `ref/`)

| Type | Evidence | Composition facts (fractions of the 1280x720 frame) |
|---|---|---|
| Hero CG, ground | V1 0:01.5 Venera 13 lander hovering over the plain | lander centred, 26 % of width x 54 % of height; horizon at 70 % height; warm orange sky gradient with faint vignette; dark brown ground with scattered thin rock slabs; soft contact shadow below the craft; simple smooth-shaded CG (not photoreal, not a toy) |
| Hero CG, ground (wide) | V1 0:16 "464 °C" | same lander tiny (8 % width) on the horizon right of the number; camera low; haze band at the horizon |
| Hero CG, close | V1 0:26 "92 BAR" (second tile row of the intro strip) | lander fills the left half; number at the right; matte wooden-brown material |
| Cloud-top / descent | V1 3:00-5:30 | parachute + capsule in orange sky; altitude gauge on the right edge |
| Real photo | V1 6:40 Venera 14 panorama | image shown as a **letterboxed strip** (full width, ~48 % height, centred), the same photo blurred and darkened fills the frame behind; two-line caption centred below: bold grey line + mono line; citation with a **filled blue dot** "● REAL PHOTO · VENERA 14 · NASA/NSSDCA/COURTESY OF THE USSR"; a ring + label annotation on the photo |
| Deep space + model | V2 0:31, V3 0:20 | Voyager NASA model small and low in a dense Milky Way sky photo (ESO/S. Brunier); a bright star point; citation "○ ILLUSTRATION · NASA 3D MODEL OF VOYAGER · SKY: ESO/S. BRUNIER" |
| Diagram plate | V2 0:22 | near-black plate; Earth disc (5 % of width, #2F6BDF) at the left edge with an amber "EARTH" label under it and a cyan node on a short line; JWST deep field as a **feather-masked disc** on the right; citation "○ DIAGRAM · GALAXIES: NASA, ESA, CSA, STSCI" |
| Survival clock scene | V1 0:25.5-0:31 | dark warm plate; the card **centred**, 42 % wide x 49 % high; later 19 % x 22 % in the top-left corner (x 3.4 %, y 5.6 %) |
| Title card | V1 0:46, V3 1:06 | two centred lines in the upper third; line 1 white (cap height ~3.6 % of height), line 2 warm gold (#F5A640), a little larger, soft glow + dark offset shadow; over Venus (V1) or the star field (V3) |
| Type moment | V1 0:16 / 0:26 / 0:44 | "464 °C": upper-left (x 12-46 %, y 35 %), white, heavy dark drop shadow + soft glow; "92 BAR" upper-right of a close shot with a mono sub-line "≈ 90 × EARTH'S AIR PRESSURE"; "55 KM UP": small, centre, plain white |

Survival-clock behaviour (V1 0:24-0:32, 2 fps strip): card fades in centred showing "—"; the three lethal chips (AIR, TEMPERATURE, PRESSURE) flash
red on/off (about 3 flashes) while ACID stays an outlined white chip; the verdict "SECONDS" blurs in red with a cyan border glow; hard cut to the
next scene; the card then lives at the top-left for the act.

Lockups: craft/date lockup is **centred at the bottom** (V1 0:01.5: "VENERA 13" bold, "1 MARCH 1982" mono below, y 88-92 %), not lower-left.
Citation: bottom-left, x 3.6 %, y 93.6 %, mono ~12 px at 1280, grey 60 %; hollow ring for illustration/diagram, filled blue dot for a real photo.

## 3. Where the Google report was wrong
- "12-18 cuts/min, 4.2 s average shot": measured 4.6-7.5 cuts/min, median 6.4-9.8 s.
- "Never cut mid-syllable / cut only in pauses": 18-35 % of cuts are mid-speech.
- "Text lower-left lockups": the craft lockup is centred at the bottom.
- "Real archival photos on a full frame": they are letterboxed over a blurred copy of themselves.
