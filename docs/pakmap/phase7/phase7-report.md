# pakMap Phase 7 report: competitor sound design

Nothing is committed. Phase 8 has not been started.

## 1. Implementation summary

A pakMap-only, event-driven sound layer. Visual events in the compiled spec (plus the script's optional `sfx` / `ambience` columns) become a list of sound cues; the cues are resolved to files in the app's existing sound library; a pakMap-only mixer builds narration + ducked sound bed into one WAV; that WAV is handed to the existing exporter as the voiceover.

| New / changed | What |
|---|---|
| `pakmap/sounds.py` (new) | The vocabulary: 20 effects (incl. 1 composite) and 7 ambience beds, each with library candidates, a fidelity label, volume, length cap, fades, optional filter |
| `pakmap/audio_plan.py` (new) | Event → cue planner, explicit overrides, ambience beds, anti-stacking rules; pure and deterministic |
| `pakmap/audio_mix.py` (new) | Finds library files (reports missing/approximate), levels them, builds the ducked bus, writes the mix; never changes the narration |
| `pakmap/audio_policy.py` (new) | The per-mode audio policy |
| `pakmap/schema.py`, `compile.py` | `sfx` and `ambience` columns, `sound` row type, validated per row; hints returned with the compile result |
| `pakmap/app_integration.py` | `plan_pakmap_sound`, `generate_pakmap_video(sound_design=...)`, graceful fallback to narration-only if the mixer fails |
| `app.py` | "pakMap sound design" switch (default on, saved per project and as the default); Check plan shows the sound plan; missing sounds are logged |
| `pakmap/__main__.py` | `check` / `compile` print the sound plan (`--no-sound` to hide) |
| Docs | `docs/pakmap/sound-design.md`, a Sound section in `csv-reference.md`, the build plan's Phase 7 note updated |

Not touched: Map Facts, Overscaled, Exp Solar, Flow, stock, `smart_editing`, `video_generator`, the global mixers and their settings.

Policy while rendering pakMap: narration ON, pakMap SFX ON, pakMap ambience ON (when the script asks), generic SFX OFF, generic ambience OFF, zoom-blur sound OFF. The pakMap switch off = narration only.

## 2. SFX vocabulary

20 effects. Full table with the library file each one plays on this machine, priority, level and length cap: `docs/pakmap/sound-design.md`.

map_slide_whoosh, ui_click, data_tick, marker_pop, subtle_pop, directional_whoosh, earth_spin, equator_ding, record_scratch, paper_slide, marker_clack, shimmer_riser, bone_tap, steam_chug, construction_impact, camera_shutter, fast_whoosh, final_chime, soft_transition, and the composite archival_texture (paper_slide + record_scratch).

## 3. Ambience vocabulary

geographic_atmosphere, desert_wind, rushing_wind, water_ambience, historical_texture, railway_texture, electrical_hum. Beds run only when the script asks (`ambience=...` on a row), until the next ambience row or `none`, looped with cross-fades; a wind-streak layer brings its own `rushing_wind` bed unless a bed is already playing.

## 4. Event → sound mappings

Automatic: zoom in (`push_in`) and zoom out (`pull_back`) of ≥ 0.9 zoom levels → map_slide_whoosh (normal priority) · marker with dot → marker_pop · stat → data_tick (3 ticks) · flow/river/connector line → directional_whoosh · reference line → equator_ding when the draw ends · photo card / filmstrip → ui_click · sticker → subtle_pop · full-screen footage → soft_transition · fly_to/pull_back of ≥ 600 km or ≥ 1.5 zoom → map_slide_whoosh (major) · move to or from a global view → earth_spin (major) · wind streak → rushing_wind bed.

Silent by default: drift, camera moves or zooms that change the zoom by less than 0.9 levels, titles, captions, fills, dots, overlays, ghost shapes, text-only zone labels, rail/border/divide lines.

Needs an explicit `sfx=` (no automatic trigger because the script has no visual event that means it): record_scratch, paper_slide, archival_texture, marker_clack, shimmer_riser, bone_tap, steam_chug, construction_impact, camera_shutter, fast_whoosh, final_chime, and the ambience beds other than the wind layer's.

Overrides: `sfx=none`, `sfx=<vocabulary id>`, `sfx=catalog:<library id>`, the same on `camera` rows, `sound` rows, `ambience=<id>` / `ambience=none`. Bad ids fail with the row number and a suggestion. Note: the brief's examples `map_whoosh_02` / `desert_wind_01` are not ids in this vocabulary; the equivalents are `map_slide_whoosh` / `desert_wind`, or `catalog:whoosh_02` for the exact library file.

## 5. Mixing and ducking

Priority narration > major > normal > ambience. Library files are levelled first (effects to peak 1.0, ambience to RMS 0.2) so vocabulary volumes (effects 0.09-0.16, ambience 0.04-0.08) are meaningful. Under speech effects dip 35%, ambience 60%; ambience dips a further 50% under a major effect. Narration is never gain-changed; if the sum would clip only the bed is reduced. Anti-stacking: 0.6 s same-sound cooldown, 0.35 s minimum gap, normal cues under a major cue dropped, max 6 per 10 s, nothing in the last 0.1 s. Dropped cues are listed with the reason.

## 6. Tests and results

`test_pakmap_audio.py`: 55 tests, plus 6 new live-app checks in `test_pakmap_app_integration.py`.

| Area | Covered |
|---|---|
| Vocabulary | all listed sounds exist, levels under speech, no music, one-shots have length caps, no fake file for a sound the library lacks |
| Event mapping | each event type's sound and time; silent cases; major vs minor camera moves; drift and small zooms stay silent; push_in / pull_back of a normal zoom step make the soft whoosh |
| Determinism | same plan and byte-identical mixed file on two runs |
| Anti-stacking / priority | burst thinning, cooldown, major-over-normal both orders, density cap, end margin, explicit never thinned |
| Overrides | `none`, named, camera row, sound row, `catalog:`, CSV hints end to end, bad values row-numbered |
| Ambience | none unless asked, bed boundaries, last bed ends with the video, wind layer vs bed, catalog bed |
| Missing assets | missing sound reported and the rest plays; composite plays what it has; missing bed warned; empty library; approximations labelled |
| Mixer | nothing-to-add returns the narration file; speech ducking measured (35% / 60%); major ducking measured; narration unchanged even when clipping; quiet-narration region identical; length; loop; levelling of loud/quiet files |
| Policy / isolation | policy flags, generic flags forced off for pakMap only and input unmutated, no other style imports `pakmap`, pakMap never references the generic mixers/planners, the shared catalog is not modified, the generic mixers are not called during a pakMap run |
| Generate run | mixed WAV exported when on, narration untouched when off, mixer failure still produces the video with a warning, missing sounds in warnings |
| App | switch default, reaches the generator both ways, saved per project, restored on reopen, global SFX/ambience settings unchanged |

Mutation checks (each break was caught by a test): no SFX ducking, no major ducking, generic flags left on, no cooldown, a camera-motion guard (drift).

Results: full Python suite **2,580 passed, 2 skipped, 0 failed** (2,525 before Phase 7); pakmap-engine 106/106. No Node or engine code changed.

## 7. Real-render demonstration

The Kenya sample story with a macOS `say` voiceover, real Whisper timing and real NASA imagery, through the real `generate_pakmap_video` (real mixer, the real `~/.videogen/sfx` library, the real exporter). The script is `demo-script-with-sound-columns.csv`: ambience `geographic_atmosphere` from the start, `desert_wind` for the dry-north section, `sfx=none` on the Lodwar marker, `ambience=none` at the wind caption.

Files in `docs/pakmap/phase7/`: `demo-with-sound-preview.mp4` and `demo-narration-only-preview.mp4` (960×540 copies; the full 1080p renders were 39.02 s, 73 s to produce), `demo-sound-plan.txt`.

Plan: 8 effects (data_tick ×3, marker_pop ×3, ui_click, equator_ding) and 3 beds (geographic_atmosphere 0-25.3 s, desert_wind 25.3-33.9 s, rushing_wind 33.9-38.9 s), 0 dropped, no missing sounds. The Lodwar marker is silent as requested; no sound for the fill, dots, titles or captions.

Measured on the exported audio (difference between the two renders): peak of each effect about -20 dBFS and about 26 dB above the bed just before it; the bed averaged about 27 dB below the narration (measured before the post-review fixes below; the desert-wind section is now quieter, about -55 dB at 27-29 s) (it is ducked all the time because the TTS narration has no pauses); the narration itself is unchanged (integrated loudness identical, -16.3 LUFS).

This sample has one small camera move, so it shows no whoosh; the whoosh and earth-spin cues are covered by the unit tests only. These are measurements, not a listening test.

## 7b. Post-review fixes (after listening feedback)

1. **Zoom sound missing.** `push_in` was deliberately silent and `pull_back` only sounded at a zoom change of 1.5 or more, while default zoom steps are 1.0. Now a `push_in` / `pull_back` that changes zoom by 0.9 or more plays the soft `map_slide_whoosh` (normal priority) at the move's start; drift and smaller zooms stay silent. Measured in a short render at about -20 dBFS, like the other effects.
2. **Weird sound at 00:27-00:29.** The `desert_wind` bed (25.3-33.9 s in the demo) played `ambience_wind_01`, a night-forest recording with ~99% of its energy above 2.5 kHz; the low-pass did not remove the hiss. `desert_wind` now uses the low rumble `ambience_06`. The long demo was re-rendered: at 27-29 s the energy above 2.5 kHz is 2.8% (was ~99%) and the section is about 9 dB quieter. Previews in this folder are the re-rendered ones. The demo has no push-in or pull-back, so the zoom whooshes are shown by the short fix render and the unit tests only.

Focused audio, app and generate tests pass (83 passed, 30 subtests); the full suite figure above predates these two fixes and was not re-run.

## 8. Missing assets

- `record_scratch`: the library has no record-scratch recording, so there is no file for it. Using it reports `MISSING record_scratch` and plays nothing for that part.
- Approximations (a library file of the same family, or one with a fixed filter), all listed with their file in `sound-design.md` and flagged in the plan report: earth_spin (whoosh_07 + low-pass), desert_wind (a low wind rumble, ambience_06), equator_ding and final_chime (a ping), paper_slide (a text swipe), shimmer_riser (tension riser), bone_tap (soft impact), steam_chug and railway_texture (a train/station recording), electrical_hum, geographic_atmosphere, historical_texture, rushing_wind, camera_shutter.
- The files were chosen from library tags and durations; **none were auditioned by ear.**

## 9. Known limitations

- **Listening check needed.** I cannot hear. Sound choice, the overall balance (ambience about 27 dB under the narration on average, effects about 16 dB under speech peaks) and the loop joins are untested by ear. The levels are constants at the top of `audio_mix.py` and `sounds.py`.
- Earlier in this project I measured the two reference videos and found no designed sound in them (Reference 2 is silent). Phase 7 follows the supplied competitor sound description; I cannot confirm it against the references.
- The exporter normalises loudness, so absolute levels in the final file differ from the WAV; the balance between narration and bed is kept.
- Sound is tied to when a layer starts, not to its exact animation (only the equator line is offset by its draw time). Rhythmic sounds (data_tick ×3, construction_impact ×3) are repeated hits, not recordings of a clock or machinery.
- Ambience is never inferred from content (no "desert detection"): the script asks for it. The wind-streak layer is the one automatic bed.
- Camera cues look at the move's size only (distance and zoom change); there is no per-place "global view" notion beyond zoom 2.6.
- A mixer failure silently-but-reported falls back to narration only; it does not fail the render.
- The globe zoom-out rendering artifact from earlier phases was still open and unrelated to this phase (fixed afterwards in Phase 8).
