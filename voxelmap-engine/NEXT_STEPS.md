# voxelmap-engine: remaining gaps (handover, 2026-11-04)

State: everything is inside `voxelmap-engine/`, nothing committed. `npm test` 45 pass; audio tests
`../.venv/bin/python -m unittest tools/test_audio_tools.py tools/test_sfx_plan.py` pass.
Samples: `samples/indochina_1954_1965.csv` (2:42), `samples/border_war_1979.csv` (39.5 s).
Latest renders: `out/border2/preview_0_39.5_av.mp4`, `out/indo3/preview_0_162.2_av.mp4` (rendered BEFORE the last
camera fix below).

## First, in the next session

1. **Re-render the Indochina preview.** The last change, coarse-terrain clearance faded near dioramas (render.mjs `clearanceTable` + page.js
   `placeAt` floor), removed the 0.195 jump at 112.7 s (now 0.024 in a 10 s test clip) but the full preview was not
   re-rendered. Command: `node render.mjs samples/indochina_1954_1965.csv --narration out/indo3/audio/vo_timing.json
   --clip 0:162.2 --audio out/indo3/audio/mix.wav --width 1920 --height 1080 --out out/indo3`, then the frame-change and
   loudness checks.
2. **Saigon arrival:** confirm the camera no longer dips between buildings at the end of the descent (the rooftop
   floor now applies from k > 0.02; not yet seen in a render).

## Look and scenes

3. **Landmarks.** Scenes are generic recipes (a battle, a city, a beach), not the real place (Pentagon, palaces,
   bridges). Needs a small landmark-model system.
4. **Forests are thin** at the new 240-block scene size (tree counts were not scaled by area in `lib/props.mjs`).
5. **Beach landings.** The beach is cubic 4.3 m steps, so it reads as a low sea wall from 90 m. Optional: half-height
   sand slabs at the waterline.
6. **The Da Nang camera looks mostly at the sea.** The director frames the scene's centre. It should frame the set's
   focal point (`E.focus` in props) or the land side.
7. **Mid-descent views of the flat outer ring** (e.g. Ap Bac at ~110 s) look plain. The outer ring could carry
   scattered trees and fields.
8. **Globe ending spins Asia away.** The globe_spin outro starts 75 deg west; an outro should pull back and drift
   instead.

## Story and data

9. **Front lines are only per province or drawn polygons**; no automatic front lines from a dataset.
10. **No story CSV writer in the app.** `tools/story_prompt.md` exists (format + rules) and `--check` validates, but
    nothing turns a topic into a CSV automatically.
11. **Other regions.** Korea, Europe, the Middle East etc. need `tools/build_world.py` once each (~10 MB), then
    per-story detail tiles via `--prepare`. Downloads still need the user's OK each time.
12. **Earlier eras** (Roman, medieval, Napoleonic) need their own scene recipes and equipment.

## Sound

13. **Spot sound effects are not synced to on-screen blasts.** Beds and distant gunfire work; `sfx_plan.py --events`
    is ready, but the renderer does not export blast times yet.
14. **The test voiceover is macOS `say`.** Real narration goes through `tools/narration_timing.py`; the app's voice
    provider is not connected.

## Product

15. **Not connected to the app UI.** It is command line only. It also needs a style page and a Generate → Visuals →
    Export flow, like other styles.
16. **No style presets.** One look, one colour grade.
17. **Commit.** Nothing is committed. Ask before committing. The tree has other sessions' uncommitted work outside this
    folder.
