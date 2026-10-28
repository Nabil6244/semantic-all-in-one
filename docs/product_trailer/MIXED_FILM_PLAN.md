# Mixed film: AI scenes + 3D lineup + chip shots (plan, 2026-10-27)

Tested today: Flow images with our 3D renders as references keep the phone design (scenes A, B, C). Images cost 0 credits; an 8 s Veo 3.1 Lite
clip costs 10 (daily allowance 50). Our 3D rooms render a 10 s clip in 14 s.

## Mix for a 3-minute film (about 30 shots of ~6 s)

| Source | Shots | Why |
|---|---|---|
| AI still + slow push (our app does the push, 0 credits) | 12 | lifestyle looks: hands, loft row, window table, macro |
| AI video clip (Veo Lite, 10 credits each) | 4 | the hero moments: hands fan, reveal, one macro, closing lineup |
| 3D lineup in our rooms | 8 | colour lineups, reveal turn, staggered power-on (no drift, no credits) |
| 3D chip + board + macros | 4 | chip, battery, camera detail, anything with specs or numbers |
| Cards (title, disclaimer) | 2 | |

Credits: 4 clips = 40 credits, one day. Stills and 3D are free.

## Rules (the planner enforces them)

- AI never does text, numbers or chips; 3D does those.
- Two AI shots never back to back; cut AI to 3D on every spec change.
- One S27 design per film, labelled a concept; one colour order everywhere.
- Every AI image is checked against the 3D reference (lens count, pill, plateau); a fail falls back to a 3D shot.

## Fast path (build order)

1. **Scene pack** (today, no code): Flow images for 12 scenes from the 3 reference sets, 2 candidates each, keep the best. One session, 0 credits.
2. **Stills as shots:** the What If engine already plays an image with a slow push (`image` shot); add them to the spec by data only.
3. **Planner `mixed` pace:** one new mode in `product_trailer/planner.py` that interleaves AI stills, 3D lineups, chip shots and captions. This is the only code.
4. **Clips:** generate the 4 hero clips (40 credits), drop in as `video` shots.
5. **Render 720p draft, then 1080p.** About 10 minutes of engine time. Music from your file.

## Decisions

1. Default S27 design: the reference's (what the AI scenes use) or the leak? Keep the AI scenes and 3D on the same one.
2. Logos: none (the renders show a faint wordmark; remove it in the 3D presets).
3. Music: your track or the app's library.
