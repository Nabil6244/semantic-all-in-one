# pakMap sound design (Phase 7)

pakMap has its own sound layer: a small set of quiet sound effects tied to things the viewer sees, optional ambience beds that the script asks for, and the narration on top. It is a separate system from the Smart-Editing sound effects, the scene ambience and the zoom-blur sound used by the other styles; none of those play in a pakMap video, and nothing pakMap-specific plays in the other styles.

**Source of the vocabulary.** The sound categories come from the competitor sound-design description supplied for Phase 7. No audio was downloaded or copied from the competitor. Every sound is played from the app's own sound library (`~/.videogen/sfx`, the same library the other styles use). The files were chosen from the library's tags and durations and were **not auditioned by ear** when this was written; see "Fidelity" below and listen before relying on a sound.

## How it works

```
compiled spec (events + camera moves) + the author's sfx / ambience columns
        -> audio_plan   (which sound, when, why; restraint rules)      pakmap/audio_plan.py
        -> resolve      (find a library file for each sound; report gaps)   pakmap/audio_mix.py: resolve_assets
        -> mix          (narration untouched + ducked sound bed -> one WAV)  pakmap/audio_mix.py: mix_pakmap_audio
        -> the existing export (the mixed WAV is given to the exporter as the voiceover)
```

Vocabulary: `pakmap/sounds.py`. Policy: `pakmap/audio_policy.py`. Nothing is random: the same script, narration and library always give the same plan and the same bytes.

## Audio policy

| System | While rendering pakMap |
|---|---|
| Narration | ON (never changed) |
| pakMap sound effects | ON (switch on the pakMap panel, default on) |
| pakMap ambience | ON when the script asks for it |
| Generic Smart-Editing sound effects | OFF (not used) |
| Generic scene ambience | OFF (not used) |
| Zoom-blur sound | OFF (not used) |

Turning the pakMap switch off gives narration only. It never changes the global sound-effects / ambience settings the other styles read, and the other styles never import or call anything from `pakmap`.

## What makes a sound (automatic)

| On screen | Sound | Notes |
|---|---|---|
| title chip (PART / NUMBER) | `deep_thud` | muffled bass hit; synthesized |
| marker with a dot appears | `marker_pop` | a text-only label (zone label) is silent |
| stat chip / counter runs up | `counter_ticks` | ten fast ticks over the 0.6 s count |
| any line draws (flow, river, rail, border trace, divide, connector, reference) | `draw_zap` | thin electronic writing sound over the 0.9 s draw; synthesized |
| reference line (equator) finishes | `equator_ding` | after its zap |
| region fill, dot layer or cluster appears | `bubble_pluck` | synthesized |
| photo card or filmstrip appears | `ui_click` | the library click (the synthesized paper slide was tried and rejected by ear) |
| comparison (ghost) shape slides on | `paper_slide` | synthesized paper friction |
| sticker appears | `subtle_pop` | quieter than the marker pop |
| full-screen footage dissolves in | `soft_transition` | |
| camera `fly_to` of at least 60 km or 0.9 zoom levels (a pan) | `map_slide_whoosh` | normal priority |
| camera `fly_to` of at least 600 km or 1.5 zoom levels | `map_slide_whoosh` (major) | |
| camera `push_in` / `pull_back` of at least 0.9 zoom levels | `map_slide_whoosh` (normal priority) | zoom in / zoom out |
| camera move to or from a global view (zoom under 2.6, change at least 1) | `earth_spin` (major) | |
| wind-streak layer | `rushing_wind` bed for its window | skipped if an ambience bed is already playing |

Fact-specific sounds are never automatic (the script's pictures do not say what the fact is). Ask for them with `sfx=` on the row or a `sound` row: `steam_chug` (railway), `airplane_hum`, `car_gravel`, `muffled_explosion` (a blast), `metal_clang`, `cash_register`, `boil_sizzle`, `wood_splinter`, `ice_crack`, `birds_chirping`, `clock_ticking` + `clock_chime`, `bone_tap`, and the two animal calls (not available, see below). Ambience for `ambience=`: `cold_wind`, `industrial_hum`, `water_lapping`, `space_drone`, `desert_wind`, `geographic_atmosphere`, and the rest of the table.

Never makes a sound by itself: camera drift, camera moves or zooms that change the zoom by less than 0.9 levels (and pans under 60 km), captions, value overlays. There is no camera-motion-only effect and nothing is random.

## Restraint (anti-stacking)

Applied to the automatic sounds, in order: the same sound is not repeated within 0.6 s; two sounds closer than 0.35 s keep the higher priority (major, then normal, then the earlier one); a normal sound that would start under a major one (from 0.1 s before it to 0.5 s after) is dropped; at most 8 sounds in any 10 s; nothing in the last 0.1 s. The plan report lists every dropped sound and why. An explicit `sfx=` from the script is never dropped by these rules.

## Mixing and ducking

Priority is **narration > major effects > normal effects > ambience**.

- Every library file is levelled before use (effects to a peak of 1.0, ambience to an RMS of 0.2), so a vocabulary volume means the same for every file. Volumes: effects 0.09-0.16, ambience 0.04-0.08.
- While the narrator speaks, effects dip by 35% and ambience by 60% (a measured speech envelope with a 50 ms attack and 350 ms release). Under a major effect the ambience dips a further 50% (smoothed).
- The narration is never gain-changed. If narration plus the bed would clip (above 0.97), only the bed is turned down.
- With sound design off, or when the plan has nothing to add, the original narration file is exported untouched.

## Script columns (all optional)

| Column / row | Meaning |
|---|---|
| `sfx` on a layer row | `none` = no sound for that layer; a sound id replaces the automatic one; `catalog:<library id>` plays that exact library file |
| `sfx` on a `camera` row | the same, for that camera move (`none` silences a whoosh; a sound id adds one to any move) |
| `layer_type=sound` row | places the sound named in `sfx` (or starts the bed named in `ambience`) at the row's time; no picture is added |
| `ambience` on any row | starts that bed at the row's time; it runs until the next `ambience` row or the end; `none` ends it |

Unknown ids are errors with the row number and a "did you mean". An ambience id in the `sfx` column (or the reverse) says which column to use.

## Vocabulary and what each one plays on this machine

Fidelity: *close* = the library describes this kind of sound; *approximate* = the nearest thing in the library; *processed* = a library file with a fixed filter.

### Sound effects

| Id | Reference sound | Used for | Source on this machine | Priority / level |
|---|---|---|---|---|
| `map_slide_whoosh` | soft map 'slide' whoosh | smooth, major map repositioning (never a loud cinematic whoosh) | `whoosh_02` (close) | major, vol 0.15, ≤1.3s |
| `ui_click` | subtle UI click / appearance sound | a photo card, image overlay or filmstrip appearing | `ui_click_01` (close) | normal, vol 0.13, ≤0.35s |
| `data_tick` | ticking clock | numbers and densities building up | `ui_tick_01` (close) | normal, vol 0.1, ≤0.25s |
| `marker_pop` | soft pop | a marker, county or region highlight, a data point | `ui_pop_01` (close) | normal, vol 0.13, ≤0.45s |
| `subtle_pop` | soft pop (quieter) | a sticker appearing | `ui_pop_01` (close) | normal, vol 0.09, ≤0.45s |
| `directional_whoosh` | subtle directional whoosh | a migration line, path or moisture arrow drawing | `whoosh_05` (close) | normal, vol 0.11, ≤0.9s |
| `earth_spin` | deep low-pass 'earth spin' | the camera heading to or from a global view | `whoosh_07` (processed: lowpass=f=420) | major, vol 0.16, ≤2.2s |
| `equator_ding` | subtle ding | the equator / reference line finishing its draw | `ui_ping_01` (approximate) | normal, vol 0.09, ≤1.1s |
| `record_scratch` | muffled historical 'record scratch' | historical portraits and archival material | **MISSING** | normal, vol 0.1, ≤0.8s |
| `paper_slide` | paper slide | archival material sliding in | synthesized (`paper_slide`) | normal, vol 0.12, ≤0.9s |
| `marker_clack` | marker 'clack' | a dam or location marker being revealed | `tech_click_01` (close) | normal, vol 0.13, ≤0.4s |
| `shimmer_riser` | shimmer / magical riser | a major visual transition (for example the Green Sahara) | `riser_05` (approximate) | major, vol 0.12, ≤3s |
| `bone_tap` | bone tap | a fossil or bone visual | `impact_01` (approximate) | normal, vol 0.12, ≤0.5s |
| `steam_chug` | low-volume steam-engine chug | a railway being revealed | synthesized (`steam_chug`) | normal, vol 0.09, ≤3.2s |
| `construction_impact` | rhythmic construction impact | a construction visual (kept low) | `impact_03` (close) | normal, vol 0.12, ≤0.6s |
| `camera_shutter` | camera-shutter-like appearance sound | an infrastructure icon appearing | `tech_click_01` (approximate) | normal, vol 0.11, ≤0.3s |
| `fast_whoosh` | fast-paced whooshing transition | the fast transition into the summary | `whoosh_01` (close) | major, vol 0.16, ≤1s |
| `final_chime` | restrained final impact chime | the final reveal (kept quiet) | `ui_ping_01` (approximate) | major, vol 0.14, ≤2s |
| `soft_transition` | soft transition | a full-screen picture or clip dissolving in | `whoosh_06` (close) | normal, vol 0.12, ≤1.4s |
| `deep_thud` | deep cinematic hit (muffled bass thud) | a title or a fact number landing | synthesized (`deep_thud`) | normal, vol 0.16, ≤0.9s |
| `draw_zap` | thin electronic 'writing' zap | a line or border being drawn | synthesized (`draw_zap`) | normal, vol 0.08, ≤0.9s |
| `bubble_pluck` | high-pitched bubble / pluck | a region fill or a dot layer appearing | synthesized (`bubble_pluck`) | normal, vol 0.12, ≤0.3s |
| `counter_ticks` | high-speed mechanical tick (counters rapidly increasing) | a counter running up | `ui_tick_01` (close) | normal, vol 0.1, ≤0.06s |
| `clock_ticking` | timeline ticking | a time-difference explanation | `ui_click_01` (close) | normal, vol 0.08, ≤0.1s |
| `clock_chime` | clock chime | a time-difference explanation | synthesized (`clock_chime`) | normal, vol 0.12, ≤1.8s |
| `cash_register` | cash register 'cha-ching' | a sale or a price (for example the Alaska sale) | synthesized (`cash_register`) | normal, vol 0.13, ≤1.5s |
| `metal_clang` | metal clang | a metal object (for example a borehole cover) | synthesized (`metal_clang`) | normal, vol 0.13, ≤1.3s |
| `muffled_explosion` | muffled explosion | a blast (for example the Tunguska event) | synthesized (`muffled_explosion`) | major, vol 0.17, ≤2.4s |
| `boil_sizzle` | bubbling / sizzling | boiling water or a hot reaction | synthesized (`boil_sizzle`) | normal, vol 0.09, ≤2.2s |
| `wood_splinter` | splintering wood | trees flattening | synthesized (`wood_splinter`) | normal, vol 0.12, ≤1.4s |
| `ice_crack` | ice cracking | the Arctic coast | synthesized (`ice_crack`) | normal, vol 0.11, ≤1.2s |
| `car_gravel` | car tires on gravel | a drive along a border road | synthesized (`car_gravel`) | normal, vol 0.09, ≤3.2s |
| `birds_chirping` | birds chirping | forests | synthesized (`birds_chirping`) | normal, vol 0.07, ≤3.6s |
| `mammoth_trumpet` | muffled mammoth trumpeting | Wrangel Island | **MISSING** | normal, vol 0.1, ≤2.5s |
| `polar_bear_growl` | polar bear growl | the Arctic | **MISSING** | normal, vol 0.1, ≤2s |
| `archival_texture` | historical transition/material (record scratch + paper slide) | historical material appearing | plays `paper_slide` + `record_scratch` | - |

### Ambience beds

| Id | Reference sound | Used for | Source on this machine | Priority / level |
|---|---|---|---|---|
| `geographic_atmosphere` | geographic atmosphere | a quiet bed under a whole geographic section | `ambience_43` (approximate) | ambience, vol 0.05 |
| `desert_wind` | ambient desert wind / low wind rumble | desert and arid sections | `ambience_06` (approximate) | ambience, vol 0.07 |
| `rushing_wind` | rushing wind | wind-flow visualisation | `ambience_06` (approximate) | ambience, vol 0.08 |
| `water_ambience` | soft bubbling / water ambience | lakes, rivers, hydrography | `ambience_27` (close) | ambience, vol 0.07 |
| `historical_texture` | historical texture | archival sections | `ambience_55` (approximate) | ambience, vol 0.04 |
| `railway_texture` | low-volume steam/railway texture | railway sections | `ambience_33` (approximate) | ambience, vol 0.05 |
| `cold_wind` | cold wind / arid drone | Siberia and the Arctic: isolation | `ambience_06` (processed: highpass=f=90) | ambience, vol 0.07 |
| `industrial_hum` | industrial / urban hum | Norilsk, trains: human infrastructure | synthesized (`industrial_hum`) | ambience, vol 0.05 |
| `airplane_hum` | airplane engine hum | flying over trees | synthesized (`airplane_hum`) | ambience, vol 0.06 |
| `space_drone` | deep hollow 'vacuum' drone | space comparisons (for example Pluto) | `ambience_52` (processed: lowpass=f=400) | ambience, vol 0.07 |
| `water_lapping` | water lapping | a lake shore (for example Lake Baikal) | `ambience_27` (close) | ambience, vol 0.07 |
| `electrical_hum` | subtle electrical hum | electricity and infrastructure sections | `ambience_20` (approximate) | ambience, vol 0.04 |

Missing on this machine: `record_scratch` (no record-scratch recording), `mammoth_trumpet` and `polar_bear_growl` (an animal call needs a real recording; they are not synthesized). Using one reports the gap and plays nothing for that part; `archival_texture` still plays its `paper_slide` part.

**Synthesized sounds** (Phase 8): where the library has no recording, `pakmap/synth.py` generates an original, deterministic sound from sine/noise/envelope maths (no copied or downloaded audio). They are labelled `synthesized` in the plan report. They are simple approximations: listen before relying on one.

Approximations worth a listen: `earth_spin` (a whoosh with a low-pass), `desert_wind` (a low wind rumble; the library's other wind file, `ambience_wind_01`, is a bright night-forest hiss with nothing under 2.5 kHz and was removed as a candidate), `shimmer_riser`, `bone_tap`, `steam_chug` and `railway_texture` (a train/station recording, not a steam engine), `final_chime` and `equator_ding` (a ping, not a chime), `electrical_hum`, `paper_slide`.

## Reporting

- **Check plan** (and `python3 -m pakmap check`) prints the sound plan after the picture plan: every sound with its time and reason, dropped sounds with the reason, the beds, and `MISSING` lines.
- A render writes `pakmap_sound_plan.txt` in the work folder, logs approximations, and returns missing sounds in the result's warnings (the app logs them as `Missing sound ...`).
- If the mixer fails for any reason the video is still made with the narration only, and the result says so.
