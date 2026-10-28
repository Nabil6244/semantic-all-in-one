# Product film tool: one tool, three film types (plan, 2026-10-27)

Decision: no real host and no real footage. Everything is AI scenes (Flow) plus 3D renders plus generated graphics.

## Three film types, one pipeline

| Type | Reference | Length | Cuts | Look |
|---|---|---|---|---|
| Trailer | Galaxy S27 Ultra trailer | 60 to 90 s | on the beat, 2 to 3 s | 3D phone, stars, washes, big type |
| Reveal | "Introducing" | 2 to 3 min | 6 s, one caption each | AI rooms and hands, 3D lineup, chip |
| Review | iPhone Duo review | 10 to 25 min | 4 to 5 s, burned-in subtitles | AI hands-on and lab scenes, 3D teardown and fold, charts |

Input for every type: phone preset (or a reference render), a script or feature CSV, a voice-over or music file.
Output: mp4 plus a description file. Nothing starts until Generate; a 6-still preview comes first.

## Shot sources (all generated)

| Source | Used for | Cost |
|---|---|---|
| 3D engine (phones, rooms, lineup, chip, teardown, fold) | specs, colour lineups, hinge and crease, X-ray, any shot where the design must be exact | none |
| Flow images from 3D references (AI stills, slow push added by our app) | hands-on, desk and lab b-roll, lifestyle, host stand-in | 0 credits |
| Flow video (Veo Lite, 8 s) | hero moments only | 10 credits per clip |
| Graphics layers (bars, curves, A/B columns, stat callouts, subtitles) | tests, comparisons, numbers | none |
| Presenter | a generated avatar or a voice-only section card (no real host) | decide |

Rules: AI never draws text, numbers or the chip; every AI image is checked against the 3D reference (lens count, pill, plateau) and falls back to a 3D shot on a fail;
two AI shots never back to back in trailers; a review keeps a recurring section card in place of the host.

## Build order (short)

1. **Flow reference images in the engine** (upload + attach to a generation), tested with fakes. Everything AI depends on it.
2. **Reference-render command:** one call makes the five reference images from a phone preset.
3. **Scene pack:** a planner step that turns a script or feature list into scene prompts and generates them with the references (images only, credit estimate shown before any clip).
4. **Mixed planner:** one `mixed` mode for trailer and reveal; a `review` mode with chapters, subtitles and chart slots.
5. **New graphics:** animated curve, triple A/B columns, X-ray and teardown 3D, fold animation.
6. **App page:** film type, phone, script or CSV, voice or music, scene pack panel, preview, credits, Generate, Render.
7. **Checks:** tests, a full render from the app, CI on Windows and both Macs.

## Open decisions
1. Presenter in reviews: a generated avatar, or voice-over plus section cards only?
2. Default S27 design: the reference's or the leak's.
3. Review length target: 10 min first or the full 25.
