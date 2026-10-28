# 3-minute "Introducing" reveal film from the all-3D rooms (plan, 2026-10-27)

Built on `whatif-engine/lib/product_room.mjs` (object `lineup`, rooms loft / gallery / studio / terrace). Reference:
`Introducing The Galaxy S27 Ultra.mp4` (184 s, ~30 shots of ~6 s, one caption per shot, music only).
Status: the 10 s clip (slow push + reveal turn) renders in 14 s at 1080p30, so the engine is not the bottleneck.

## Shape of the film (about 180 s)

| Act | Time | What |
|---|---|---|
| Opening | 0 to 18 s | Fog studio (existing `charcoal` + fog + `reveal` move): back, turn, screen powers on; second colour; third colour. Title "Samsung Galaxy S27 Ultra". |
| Features | 18 to 150 s | 20 feature shots of ~6 s: room lineup or a macro, one caption each (bottom centre). |
| Chip | two of those | 3D circuit board under the chip package + gold light streak (existing chip + `badge` burst, board is new). |
| Close | 150 to 180 s | Full lineup, slow pull-back, "Introducing" + name card, then the disclaimer card (3 s). |

## Shot recipe (one per feature)

Each feature row becomes one shot: room, pose, push, caption, and what the lineup does. Rotation rules (checked by the planner):

- Room: no room twice in a row; each of the 4 rooms used at most 6 times in 20 shots.
- Pose: alternate back / front / mixed / fan; a "turn" (back to front) at most every 4th shot.
- Push: always a slow push of 8 to 12 percent; direction alternates (in / out); cam_x drifts a little left or right.
- Caption: bottom centre, white, one line, appears 0.6 s after the cut, gone 0.4 s before the next cut.

Draft feature order and look (from the reference; every spec is a rumour or concept, labelled):

| # | Caption | Room | Pose / move |
|---|---|---|---|
| 1 | New Design | loft | back, turn to front |
| 2 | 6.9" 120Hz Display | gallery | fronts, wallpapers lit, staggered power-on |
| 3 | Improved Privacy Display | studio | fan, one phone forward |
| 4 | 200MP Primary Camera | loft | backs, push toward the camera bars |
| 5 | 50MP Ultrawide Camera | terrace | backs |
| 6 | 16MP Selfie Camera | gallery | fronts |
| 7 | Snapdragon 8 Elite Gen 6 | chip board | streak + badge (generic, no real logo by default) |
| 8 | Gorilla Armor 3 | studio | fronts, crystal wallpaper variant |
| 9 | Up to 16GB RAM | loft | mixed |
| 10 | Up to 1TB Storage | terrace | backs |
| 11 | 5,700 mAh Battery | fog studio | single phone, glow |
| 12 | 60W Fast Charging | gallery | fan |
| 13 | WiFi 7 | terrace | fronts |
| 14 to 20 | Bluetooth 6, Ultra Slim Bezel, New Camera Module, Brand New Colours, Titanium frame, AI features, Software updates | rotate | rotate |

(The first sample, `docs/product_trailer/samples/galaxy_s27_ultra_reveal.csv`, already has most of these rows.)

## What has to be built

1. **Lineup shot in the planner.** `product_trailer/planner.py` (other session's code, add a mode, do not rewrite): a `rooms` pace that maps feature rows
   to `object: "lineup"` shots with the rotation rules above. Keep `reveal` and `trailer` paces unchanged.
2. **Staggered power-on and per-phone wallpapers.** Today every phone shows its ripple wallpaper from frame 0. Add `power_on` per phone (0.3 s apart) and
   a black-glass state, like the reference's reveal.
3. **Circuit-board chip shot.** A board under the existing chip: green-black PCB, traces, gold pads, small components, depth of field, gold light streak.
4. **Better realism items parked from the room pass:** distance-fading reflection, a softer sun, room-specific colour grade, a thinner table edge so the phones fill more
   of the frame (camera 6.3 to 5.6, or a tighter spacing), an optional fog layer in the rooms.
5. **Design choice per video.** Preset `galaxy_s27_ultra` (the reference's design) or a leak-based preset; one per video, with the concept disclaimer.
6. **Wordmark off by default** (`SAMSUNG` is on the backs today); on only if you supply and approve a logo.
7. **Captions and music.** Existing `pt_caption`; music from your file or the app's library, cuts snapped to beats (the planner already has beat detection).

## Render budget

Measured: 10 s of lineup at 1080p30 = 14 s. A 3-minute film is about 4 to 6 minutes of engine time, 10 minutes with the chip scenes and fog studio. Draft quality (720p) is
about 4x faster, so a draft pass first is cheap.

## Phases and stop points

| Phase | Work | Done when |
|---|---|---|
| A | Staggered power-on, tighter framing, reflection fade, wordmark off, per-room grade | 4 stills you accept |
| B | Planner `rooms` pace + CSV rules; a 60 s draft (10 shots) | The draft reads as the reference's rhythm |
| C | Board chip shot, opening fog sequence, close and cards | The special shots match |
| D | Full 3-minute draft at 720p with music, then final at 1080p | You approve the film |
| E | App wiring (pace choice on the Product Trailer page), tests, CI | Windows and both Macs pass |

## Risks and open decisions

- **Realism ceiling.** All-3D rooms read as clean CG. If that is not enough, the Flow plate route (`ROOMS_PLAN.md`) is the upgrade and the lineup object is reusable there.
- **Coordination.** `scene3d.mjs`, `product.mjs` and the planner are edited by another session. New code stays in new files; hooks stay one line; check before any commit.
- **Logos.** Real brand marks or generic badges only.
- **Design.** Which S27 design is the default?
- **Length.** 3 minutes with 30 beats, or a shorter 90 s cut first?
