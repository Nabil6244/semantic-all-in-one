# Phase 8: SFX update (first reference video's sound design)

Source: the sound-effects breakdown of the first reference video supplied by the author (five groups). No audio was downloaded or copied. The library has no recording for about half of it, so Phase 8 adds `pakmap/synth.py`: original sounds generated in code (deterministic, labelled "synthesized"). Animal calls are not synthesized (they would not be convincing); they are declared and reported as missing.

| Group | Reference sound | Now |
|---|---|---|
| 1 Map and camera | organic whooshes on every pan/zoom | `map_slide_whoosh` on pans (fly_to of ≥ 60 km) and zooms (≥ 0.9 levels); drift stays silent |
| | paper slides for photo overlays and country comparisons | `paper_slide` (synthesized) on ghost (comparison) shapes only. Photo cards and filmstrips keep the library `ui_click`: the synthesized paper slide on cards was rejected after listening |
| | deep cinematic thud for NUMBER / titles | `deep_thud` (synthesized) on every title chip |
| 2 Data and UI | digital ticking on counters | `counter_ticks`: ten fast ticks over the counter ramp |
| | pops and plucks for dots and regions | `bubble_pluck` (synthesized) on fills, dots, clusters; `marker_pop` on markers |
| | zaps for border lines being drawn | `draw_zap` (synthesized) on every line draw |
| 3 Ambience | cold wind, industrial hum, nature accents | `cold_wind`, `industrial_hum` (synthesized), `water_lapping`, `birds_chirping` (synthesized), `ice_crack` (synthesized) |
| 4 Fact-specific | steam engine, airplane, car on gravel, explosion, metal clang, cash register, sizzle, splintering wood | `steam_chug`, `airplane_hum`, `car_gravel`, `muffled_explosion`, `metal_clang`, `cash_register`, `boil_sizzle`, `wood_splinter`: all synthesized, used with `sfx=` |
| 5 Comparison and animals | vacuum drone, mammoth, polar bear, clock chime/ticking | `space_drone` (library, low-passed), `clock_chime` (synthesized), `clock_ticking` (library); **`mammoth_trumpet` and `polar_bear_growl` missing** |

Other changes: density cap raised from 6 to 8 sounds per 10 s (the reference is busier); a title lands before its fill or line, so those lose the 0.35 s overlap to the thud (the report lists what was dropped).

Verified: 63 audio tests (determinism of every generator, spectral character, vocabulary resolution, mapping, mixing) plus the app and generate tests; the Kenya demo re-rendered (`docs/pakmap/phase7/demo-with-sound-preview.mp4`): 13 effects and 3 beds, each effect between about -17 and -23 dBFS against narration peaks near -5 dBFS.

Not verified: by ear. Synthesized sounds in particular are simple models; judge them by listening. Earlier in this project I measured the two reference videos and found no designed sound; this update follows the supplied description instead.
