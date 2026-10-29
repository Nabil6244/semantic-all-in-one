# What If / StarMap Cinema: the references, and how they are balanced

Every reference teaches HOW a video is made; none is the content. A new reference ADDS to this table; it never replaces a row. The planner's mix
(`visual_composer/apply.py` `BALANCE`, reported as `plan: balance:` notes) is the blend of all of them.

| Ref | Video | What it contributes | Where it lives |
|---|---|---|---|
| V1 | How Long Could You Survive on Venus? | hero CG lander on the plain, parachute descent, letterboxed real photo + blurred copy, survival clock, centred lockups, type moments ("464 °C"), title cards | `lib/hero.mjs`, `tm_survival`, `tm_caption`, `tm_title`, compile `compose: letterbox` |
| V2 | What If You Traveled at the Speed of Light? | NASA model small in a Milky Way sky, disc-map plate (Earth + deep field), dual clocks, light-time axis | craft shots, `tm_discmap`, `tm_clock` |
| V3 | What If You Tried to Travel One Light-Year? | slow evolving shots, gauge/HUD, light-from-Earth clock, long holds | `tm_gauge`, `tm_dial`, merge_beats |
| V4 | black-hole video | ray-traced black hole hero shots | `lib/blackhole.mjs` |
| V5 | space settlements | spinning habitat scenes | `lib/habitat.mjs` |
| V6 | What If You Fell Into Jupiter? (2026-10-29) | a unique 3D scene per line (descent through clouds, cutaway interior with labels, field lines), depth ruler HUD, atom lattice, big-number/comparison cards, end question | `lib/scene_gen.mjs`, `templates/descent/`, `visual_composer/` |

## Balance (share of shots, auto plans)
- real photos: never replaced by a generated scene (`upgrade_scenes` skips REAL IMAGE / nasa_image / file shots)
- NASA models + globes 10-30 %, hero CG 0-12 %, generated scenes 10-30 % (hard cap 30 %), all 3D together <= 50 %, diagram plates 10-35 %
- a sentence that names a real craft or world keeps the NASA model / real texture (V1-V3); a generated scene is for what has no model (V6)
- graphics composed per sentence (`enrich`) are additive and never cover an existing callout
