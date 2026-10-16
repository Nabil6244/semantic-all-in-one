# What If — reference-to-implementation gap matrix (2026-10-17)

Status key: **N** not implemented · **I** implemented, not integrated · **U** integrated, not visually verified · **D** working but visibly different · **M** closely matched and verified.
"Verified" means compared on rendered frames against the reference. This pass changed code only (rendering needs your permission), so everything
changed below is **U** until the stills you approve are compared; the evidence column says what the code now does and where the reference shows it.

| # | Feature | Reference evidence | Before | After this pass (code) | Root cause / change | Test |
|---|---|---|---|---|---|---|
| 1 | Cut placement vs narration | 65-82 % of cuts in a pause, 18-35 % inside speech (measured, `analysis/cuts_vs_speech.py`) | D: 0 % inside speech | U | `planner.cut_points`: 25 % of cuts on a content word (golden-ratio sequence, deterministic) | `test_cuts_follow_the_references_pause_policy`, `test_mid_speech_cuts_land_on_content_words...` |
| 2 | Shot rhythm | median 6.4 / 9.1 / 9.8 s, 4.6-7.5 cuts/min | M (planner), D on dense scripts | U | unchanged targets; plates trimmed to fit | `test_pacing_is_the_references` |
| 3 | Hero scene: Venera lander on the plain | V1 0:01.5: craft 26 % wide, horizon 70 %, orange sky, dark ground with slabs | D: grey photoreal Flow image, wrong composition | U | new `whatif-engine/lib/hero.mjs` (procedural lander, ground, slabs, sky, shadow, hover); planner chooses it for Venera | `test_venera_gets_the_composed_hero_scene...`, `hero needs a scene` (engine) |
| 4 | Hero scene: descent under parachute | V1 3:00-5:30 | N (Flow image) | U | `venera_descent` scene (striped dome, lines, capsule) | same |
| 5 | Hero scene: airship over clouds, ship with engines (V3) | V1 5:40, V3 | D (Flow only) | D | not built; Flow remains | - |
| 6 | Real photo composition | V1 6:40: letterboxed strip over a blurred copy, caption centred below | D: cover-cropped | U | `page.js` `compose: letterbox`; `tm_caption` size `photo` | `test_real_photographs_are_letterboxed...` |
| 7 | Citation line | x 3.6 %, y 94 %; ring for illustration/diagram, filled blue dot for a real photo; "REAL PHOTO · VENERA 14 · NASA/NSSDCA/COURTESY OF THE USSR" | D | U | `tm_cite` geometry + dot; `compile.citation` text | same test |
| 8 | Name lockup | centred bottom (y 88/92 %) under hero shots; big left for 3D craft | D: always left | U | `tm_caption` anchor `bc`; planner picks per shot kind | - |
| 9 | Number callouts | "464 °C" x 12.5 % y 35 %; "92 BAR" x 55 % y 18 %; "55 KM UP" centre; heavy shadow + soft glow | D: always top-centre | U | `tm_metric` anchors + shadow; planner rotates anchors | - |
| 10 | Survival clock | scene: centred 42x49 % card, chips flash red x3, "SECONDS" blurs in with cyan border; then corner 19x22 % at (3.4 %, 5.6 %) | D: corner only, wrong size | U | `tm_survival` rewritten (box interpolation, intro, chip flash); planner inserts the plate scene | `test_survival_clock_opens_as_its_own_scene...` |
| 11 | Title cards | two centred lines, white + gold, glow + dark shadow | U | U | unchanged | - |
| 12 | Altitude gauge | right edge, zones with labels, node + readout | D: no zones in auto mode | D | not done (needs zone data from the script) | - |
| 13 | Light-from-Earth dial clock + date (V3) | V3 0:10-8:00 | I: layer exists, planner never uses it | I | not wired | - |
| 14 | Dual clocks (V2) | EARTH TIME / TRAVELLER cards | U | U | - | - |
| 15 | Log light-time axis | V2 | U; labels clipped at edges | U | label clamp | - |
| 16 | Diagram + feathered photo disc (V2 0:22) | JWST deep field as a masked disc | N | N | - | - |
| 17 | Deep-space craft shot | dense Milky Way sky, craft small and low | D: sparse stars | U | 9000 stars + Milky Way band in `scene3d.mjs` | - |
| 18 | Photo annotation ring + label (V1 6:40) | cyan ring, amber label on the photo | N | N | - | - |
| 19 | Loudness | -14.0 LUFS integrated, LRA ~4, true peak ~-1.5 | N: unnormalised | U (measured on synthetic audio: -14.7 LUFS, peak -1.2) | `sound.normalize_loudness` two-pass loudnorm in the export path | `test_final_audio_is_set_to_the_references_loudness` |
| 20 | Music bed level | 13.8 / 15.3 / 18.9 dB under speech | D: 20.4 dB (measured on our last mix) | U | `MUSIC_GAIN` 0.2 -> 0.36 for What If | measured, not unit-tested |
| 21 | Sound effects | clicks at HUD/number changes, low thuds at titles | U | U | cue sets unchanged; exact reference event timing not measurable | - |
| 22 | Flow image look | calm warm CG | D: toy / photoreal | D | prompt tuned twice; the hero scene replaces it for Venera | - |
| 23 | Real archive source for Venera | V1 | D: NASA has none; Commons untested | D | NASA -> Commons -> labelled AI illustration chain | `test_a_nasa_miss_is_never_filled_by_stock...` |
| 24 | App integration (style card) | - | U | U | never opened in the running app | - |
| 25 | Flow video | - | N | N | needs your permission | - |

## What needs your permission to verify
Stills from the engine (hero scene, survival card, callouts, photo letterbox, craft + Milky Way) and, after that, a preview render; Flow video generation.
