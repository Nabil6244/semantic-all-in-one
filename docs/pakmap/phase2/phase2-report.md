# Phase 2 report: overlay vocabulary

Code: `pakmap-engine/` (still separate from every other engine). Tests: `cd pakmap-engine && npm test` (60 pass). Preview: `overlays-preview.mp4` (960x540 copy of the 1080p render); side by side with the reference frames: `reference-vs-ours.jpg`.

## What exists now
| Layer | Status | Notes |
|---|---|---|
| HUD title + subtitle chip | done | Free text (`PART 1`, `NUMBER 14`, anything); optional (cold open = no event). Subtitle chip grows, title pops in, words appear one by one. |
| Stat chip | done | Counter eases out, formats `12.6M`, `17,700`, minus sign, `1/5`, `2c`, `445x`, `M8.8`; anchors br, bl, tr, tl, bc, center; two at once. |
| Caption chip | done | Yellow text on dark chip, 1-2 lines, optional tiny source line. |
| Marker | done | Ring dot + label chip, optional value and sub-chip, roles dark (default), neutral, featured, subject, compare; label side chosen once and never flips. |
| Line draw | done | route/flow (arrowhead), river, rail, border trace, divide, reference (dashed), connector (dashed); head-first, 0.9 s, ease-out. |
| Dot density | done | Thousands of 6 px dots, linear reveal over 3.1 s, fixed random order. Points inline, generated (demo), or from a user CSV (`points_files`). |
| Point cluster | done | Staggered pop, 45 ms apart. |
| Watermark | done | Off unless the spec sets one (the reference's `EXPLAINS-IT` is its channel's brand, not ours). |
| Timeline rules | done | Refused before any browser starts: more than 2 stat chips, more than 5 text layers, two HUD titles at once, unknown types, missing fields, events ending after the video. Silence over 5 s is a warning. |

## Measured against the references (golden-frame tests, real renders)
| Item | Reference | Ours |
|---|---|---|
| Title chip | 67 px high at (45, 37) | 67 px at (45, 37) |
| Subtitle chip | 39 px high, 8-9 px under title, x=44 | passes (+-2 px) |
| Stat chip with sub-line | 156 px high, 63 px from right, 66 from bottom | passes (+-5 / +-3 px) |
| Stat number | 60 px caps | passes (+-4) |
| Caption chip | 44 px caps, 108 px high | passes (+-4) |
| Marker chip | 52 px high, 27 px from the dot, white text on dark | passes |
| Line draw | already drawing on the first frame, finished at 0.9 s | passes |
| Dot reveal | linear over 3.1 s | passes (+-12 %) |
| Same spec, same frames twice (with overlays) | n/a | passes |

A deliberate break (shrinking the stat chip's bottom padding) makes the stat-chip test fail, so the tests do notice drift.

## Corrections made during the phase (from measuring the reference at full resolution)
- **Marker labels are dark chips with white text**, not white chips. White chips are for zone/county labels (kept as the `neutral` role).
- **Captions are large**: 63 px text, not the 34 px I first guessed.
- The subtitle reveal is **word by word** (Reference 2 measurement), not a character typewriter.

## Not done (belongs to later phases)
- Narration anchoring: events carry explicit times; a CSV compiler that places them from the voiceover is Phase 5.
- Real data: dots here are generated demo points; bundled population data and user rasters are Phase 3. Place names resolve to coordinates in Phase 5; today events carry lon/lat.
- Value-overlay colour layer, ghost-shape comparison, streaks (Phase 3); PiP cards, filmstrip, stickers, full-screen dissolves (Phase 4).
- Collision-aware placement beyond "pick a side with room" (Phase 8); overlapping markers can still collide.
- The globe zoom-out defect from Phase 1 is still open.

## How to use it
`node pakmap-engine/render.mjs <spec.json>`; see `pakmap-engine/samples/overlays-kenya.json` for every layer type. The spec's `events` array is the contract the Phase 5 CSV compiler will produce.
