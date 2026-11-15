# 2D TV-cartoon cast (Kids stories) — plan

User decision 2026-11-15: drop the slow 3D cast for kids stories; make **2D characters that look like a real cartoon show** (clean lines, proper hands, natural mouth and body movement). Art source: **free character packs + Flow images** (Flow pictures only — still no Flow video for kids).

## Why
- 3D renders ~0.75 s/frame: a 1-minute video takes ~20 min. 2D puppet renders ~real time (1 min for 1 min).
- The current 2D puppet (from the user's one picture) looks stiff: arms, hands and mouths are drawn by code.
- Fix: every part a character needs is a real drawing, not code.

## What each character needs (a "cut-out rig", like TV 2D shows)
| Part | Count |
|---|---|
| Head, front + 3/4 left + 3/4 right | 3 |
| Mouths (Rhubarb A–H + X, plus smile, laugh, "oh") | 12 |
| Eyes: open, half, closed, happy closed, look left/right | 6 |
| Brows: neutral, up, worried | 3 |
| Body/torso, front + 3/4 | 2 |
| Upper arm, forearm (per side) | 4 |
| Hands: open, point, fist, wave, thumbs up, clap | 6 per side |
| Legs + shoes, standing, jump tuck | 2 sets |

## Where the art comes from
1. **Flow images (main source):** one character design picture per character, then matching sheets for mouths, eyes, hands, arm poses and head turns, all "same character, same style, white background". Our existing cut-out tool (`cartoon3d-engine/tools/puppet_prep.py`) cuts parts to clean PNGs.
2. **Free packs (structure + backup):** Kenney *Toon Characters 1* (CC0, separate limbs, 45 poses) and the heosphorus *Chibi template* (11 lip-sync mouths, licence to check) give the rig layout, joint points and mouth sets as a fallback. A pack is only used as-is if its look passes the user.

## Steps (each ends with stills for the user's OK)
1. **Design pictures** — Miss Molly + Lily + Ollie, one Flow picture each, same show style. *Gate: user picks looks.*
2. **Part sheets** — Flow sheets per character; cut into parts; a contact sheet of every part. *Gate: consistent faces/hands.*
3. **Rig** — extend `web/puppet2d.js` from one cut-out picture to a layered rig: joint pivots, part swaps (mouths, eyes, hands, head turns), squash on jumps, secondary motion (hair, clothes).
4. **Acts** — the same per-line acts already added to the 3D path (wave, cheer, jump, clap, count, giggle, point, open) as 2D poses; Rhubarb mouths; blinks.
5. **Playland background** — a flat painted room (Flow picture), parallax layers, simple camera pans/zooms.
6. **1-minute test** — the written script `cartoon3d-engine/authoring/sets/scenes/scene2_jump_colours.json` (trim from 85 s to ~60 s), cards + music + effects via kids_audio.

## Open
- Flow image credits per character: ~6–10 pictures each.
- Lily keeps the look of the user's girl picture (pink headband, ponytail, pink tee, overalls)?
