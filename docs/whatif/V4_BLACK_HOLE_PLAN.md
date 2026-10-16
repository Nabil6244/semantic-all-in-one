# What If — new pattern from V4 "What If You Explored a Black Hole?" (plan, 2026-10-16)

Source: `~/Downloads/What If You Explored a Black Hole_.mp4` (1280x720, 24 fps, 9:51). Measured with
`docs/whatif/analysis/measure_reference.py` (raw numbers: scratchpad `bh/ref4.json`, copy into `analysis/ref4.json` when building).
V1-V3 = the three references in `reference_spec.md`. **Built 2026-10-16** as templates + tm_mission + ray-traced black hole scenes (see `TEMPLATES.md`).

## 1. What is the same as V1-V3 (keep)
- -14.0 LUFS, LRA 3.8, true peak -1.7 dBFS, no digital silence (identical to V1-V3).
- Theme: near-black plate, white bold tracked heads, amber/gold mono sub-lines, cyan accents, citation bottom-left with ring / filled dot.
- Title-card look (white line + gold line, glow), dual clocks EARTH / YOU, log time axis, real photo with citation ("REAL IMAGES · EHT COLLABORATION").
- End card: question to the viewer over the hero shot, "TELL ME IN THE COMMENTS", "WHAT IF... · A SCIENCE SERIES" footer.

## 2. What is new in V4 (the new pattern)

| # | New thing | What it looks like (timestamps approx.) | Exists today? |
|---|---|---|---|
| N1 | **Mission HUD card** (top-right, whole video) | Frosted card: "MISSION · SGR A*" kicker, "DISTANCE TO THE EDGE" (later "...TO THE CENTRE"), big number "208 MILLION KM" → "6.3 MILLION KM" → "2,215 KM" → "0 KM", status line ("FALLING", "HOVERING · TIME ×100 SLOWER", "PAST THE EDGE"), a 5-node progress rail (APPROACH · PHOTON SPHERE · EDGE · INSIDE · SINGULARITY) with the current node lit cyan. Number counts down between shots; appears after the intro (~0:48) and stays to the singularity (~7:40). | No. `tm_survival` is a top-left card with chips; `tm_clock` is a corner instrument. Need a new `tm_mission` layer. |
| N2 | **Stage / chapter structure** | Small cyan kicker "STAGE 1" + white head "THE APPROACH" top-left over the cross-section diagram; stages: Approach, Photon Sphere, Where Time Slows, The Edge, The Singularity. Also "THE MISSION" kicker over the target intro. | Partly: `tm_title` is a centred card. Need a **stage header** variant (top-left kicker + head) and stage tracking in the planner. |
| N3 | **Recurring cross-section diagram ("you are here")** | Same side-view schematic every stage: disc of hot gas (gold lines left/right), photon sphere ring (dashed), event horizon, singularity, cyan "YOU" marker moving inward; labels with leader lines. Re-used 5 times with the marker in a new place. | No. New `tm_blackhole_section` (generic "layered target" diagram: rings + marker + labels) so it also works for planets, stars, the Sun. |
| N4 | **Black hole hero renders** | Interstellar-style lensed disc (edge-on, top-down, close-up of the bright ring), star field warped around the shadow ("Gaia" lensing), red-shifted horizon arc, black frame with a thin bright horizon curve, red point singularity with radial streaks. ~17 % of runtime is picture shots, rest plates. | No. `hero.mjs` only has Venera scenes. Need a lensing shader scene (WebGL in the engine page) + streak scene; NASA Goddard / J. Schnittman visualisations are cited in V4 and could be the real-video fallback. |
| N5 | **Spacetime warp grid** | Curved mesh funnel ("GRAVITY SLOWS TIME", "SPACE + TIME = ONE FABRIC") with a glowing ball, slow orbit of the camera. | No. New `tm_warpgrid` (3D wireframe in canvas). |
| N6 | **Light-path diagrams** | Rays bending round a dark disc ("LIGHT BENDS AROUND IT"), two rays from "A STAR" to an eye icon "YOU", rays bent "UP AND OVER THE TOP / UNDER THE BOTTOM", light orbiting the photon sphere with a cyan arrow. Lines draw on. | No. New `tm_raypaths` (draw-on polylines + eye/star icons + labels). |
| N7 | **Orbit diagram with a real object** | "STAR S2 · ONE ORBIT EVERY 16 YEARS": dashed ellipse, star with comet trail, "SGR A*" target. | Close: `tm_orbitmap` draws circles; add ellipse + trail mode. |
| N8 | **Size-squeeze comparison** | Sun photo with "THE SUN · 1,392,700 KM WIDE", then the number counts down while it shrinks ("SQUEEZING THE SUN · 1,382,183 KM"). | Partly: `tm_metric` + image. Need a **counting metric** (number animates between two values) and an image scale animation. |
| N9 | **Split-screen two points of view** | Two cards "YOU" / "A FRIEND FAR AWAY SEES", astronaut icon, small clock in each, right one slows, turns red, fades ("SLOWS DOWN · TURNS RED · FADES TO BLACK"). | No. `tm_compare` slides two things in; extend to a 2-panel "POV" card with per-panel clock/state. |
| N10 | **Clock-ratio banner** | Dual clocks + big bottom-left banner "1 HOUR FOR YOU = 10 HOURS ON EARTH" that updates (2 → 10 → 100 hours) and a small altitude marker "128,000 KM ABOVE / THE EDGE". | Dual clocks exist (V2). Add the ratio banner + linked hand speeds + mini altitude marker. |
| N11 | **River model / moving walkway** | Wide red-to-dark band full of moving dashes flowing left, "SPACE: A WALKWAY MOVING IN ←", three light dots: "GETS OUT / RUNS ON THE SPOT / CARRIED IN", "EVENT HORIZON · THE WALKWAY MOVES AT LIGHT SPEED". | No. New `tm_flowfield` (generic: particles flowing on a band + labelled tracers). |
| N12 | **Space-time axes (light cone)** | Cross axes TIME / SPACE, "YOU" dot; inside the edge the axis rotates so "IN = YOUR FUTURE", "NO ENGINE CAN TURN YOU AWAY FROM IT". | No. New `tm_axes` (two axes that can rotate + labelled points). |
| N13 | **Character icon** | Simple astronaut figure (white suit) — falling, stretched ("SQUEEZED INTO A THIN BAND AROUND YOUR WAIST"), red when far-away view. | No. Add one SVG astronaut sprite with states (normal / stretched / red / fade). |
| N14 | **Equation moment** | Serif LaTeX-style "G_μν = 8πG T_μν / c⁴ → ∞" with mono sub-line "INFINITE DENSITY: THE THEORY HAS RUN OUT", then cyan "GRAVITY + QUANTUM PHYSICS = ?". | No. New `tm_equation` (serif math font, red arrow, sub-lines). |
| N15 | **Real image pair** | M87* (2019) and Sgr A* (2022) EHT photos side by side, then the second one framed ("OUR DESTINATION"). | Close: `tm_compare` + letterbox photo; add "pair then focus" mode. |
| N16 | **Concept icons** | Burning letter "BURN A LETTER...", information symbols around the shadow, Hawking-radiation dots/squiggles, "SHRINKING...". | No. Small icon set (letter, eye, star, squiggle particles) — sourced once, CC0, not per video. |
| N17 | **Deep-time log axis** | "BLACK HOLES DON'T LAST FOREVER": 10¹⁰…10⁶⁷ years axis, "THE UNIVERSE SO FAR ~14 BILLION YEARS", "SGR A* EVAPORATES ~10⁶⁷ YEARS", bottom line "TODAY: SGR A*'S GLOW = 0.000…01 K". | Close: `tm_logaxis` is light-time only; add a generic unit + superscript labels. |

## 3. Measured rhythm — V4 is slower and more diagram-driven

| Measure | V1 | V2 | V3 | **V4** |
|---|---|---|---|---|
| Hard cuts / min | 7.5 | 5.7 | 4.6 | **3.8** |
| Shot median / p90 (s) | 6.4 / 14.6 | 9.1 / 17.1 | 9.8 / 29.7 | **9.5 / 37.8** (max 71 s) |
| Visual changes / min (median gap) | 9.7 (5.0 s) | 7.5 (6.8 s) | 10.3 (4.8 s) | **7.3 (5.8 s)** |
| Plate share of runtime | — | — | — | **83 %** (picture 17 %) |

So V4 holds one diagram for a long time but keeps it alive: the HUD number ticks, the marker moves, labels build. The rule "change every ~6 s"
still holds, but it comes from builds inside a plate, not cuts. This fits [[no still screens]]: a 40-70 s plate is only allowed when it builds
at least every ~6 s.

## 4. Plan (smallest steps, test-first, no renders without asking)

**Phase A — the spine (gives every What If video the V4 feel, any topic)**
1. `tm_mission` HUD card (N1): kicker, label, counting number with units, status line, N-node rail; the number tweens between beats. Planner: a
   "journey" episode (distance or depth falling toward a target) gets one mission value per beat, parsed from the narration (reuse
   `narration.py` number parsing) or from new CSV columns `mission_value`, `mission_stage`.
2. Stage headers (N2): `tm_title` variant `stage` (top-left kicker + head). Planner splits the script into stages from CSV `stage` or headings.
3. Recurring section diagram (N3): `tm_section`-like layer with rings from a small JSON spec (black hole, planet, star), marker position per stage.
4. Counting metric (N8) in `tm_metric` (`from`/`to`) + image scale tween.
5. Long-plate guard: a plate over 15 s must carry a build every ≤ 6 s (HUD tick, label, marker) — add to `empty_plates()` / check report.

**Phase B — new diagram layers (reusable, not black-hole only)**
6. `tm_raypaths` (N6), `tm_warpgrid` (N5), `tm_flowfield` (N11), `tm_axes` (N12), `tm_equation` (N14).
7. Extend existing: `tm_orbitmap` ellipse + trail (N7), dual clocks ratio banner + mini altitude (N10), `tm_compare` POV panels (N9) and
   photo pair → focus (N15), `tm_logaxis` generic units/superscripts (N17).
8. Astronaut sprite + small CC0 icon set (N13, N16), sourced once (see [[no per-video asset burden]]).

**Phase C — hero pictures**
9. Black-hole lensing scene in the engine (WebGL shader: shadow, lensed disc edge-on / top-down / close ring, warped star background),
   singularity streak scene, horizon arc. Fallback chain: NASA SVS (Goddard/Schnittman) video → engine render → Flow image.
10. Real images: EHT M87*/Sgr A*, ESO/GRAVITY Galactic Centre via the existing NASA → Commons chain.

**Phase D — writer side**
11. `composition_styles/whatif_csv_prompt.txt`: add the V4 vocabulary (stage, mission_value, shot kinds raypaths / warpgrid / flowfield /
    axes / equation / pov / section) and the rule "one diagram held long but building".
12. Add V4 to `reference_spec.md` / `gap_matrix.md` / `reference_targets.json` (pacing targets become a range: V4 = "journey" profile).

**Tests:** one unit test per new layer (engine `layers.test.mjs`), planner tests for mission tween / stage split / long-plate guard in
`test_whatif.py`. Then (with your OK) stills of each new layer next to the matching V4 frame, then one short preview render.

## 5. Questions for you
- Build order: Phase A first (works on every topic) — or the black-hole hero render first?
- Should the mission HUD be automatic for any "journey" script, or only when the CSV asks for it?
