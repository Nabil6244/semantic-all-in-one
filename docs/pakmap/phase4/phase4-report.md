# Phase 4 report: rich media

Code: `pakmap-engine/` (tests: `cd pakmap-engine && npm test`, 104 pass). Preview: `rich-media-preview.mp4` (960x540 copy); side by side with the reference: `reference-vs-ours.jpg`. Demo spec: `pakmap-engine/samples/rich-media-kenya.json`; its pictures are synthetic placeholders made by `tools/make_demo_media.py`, so no third-party photo ships in the repo.

## What exists now
| Layer | Event | What it does |
|---|---|---|
| Photo card | `pip` | One framed picture or video clip: 420 x 303 landscape (also square, portrait, or any width), white 5 px border, shadow. **Snaps in** from 115 % size and 40 % opacity, settling in 0.17 s from slightly up and right, border appearing during the settle; **fades out** plainly over 0.45 s (no shrink, no slide). Optional yellow label chip under it, optional leader line to a map point, and a **crossfade between several images** inside the same frame (`images: [a, b]`, `every_s`). Follows the map (it keeps drifting with the camera); can also be pinned to a map point (`at`). |
| Filmstrip | `filmstrip` | 3-7 labelled cards in a row along the bottom; cards shrink as they multiply (3 cards 420 px wide, 6 cards 240 px on a 256 px pitch, as in the references); they arrive one after another (0.25 s apart); `align`: center, left or right. |
| Sticker | `sticker` | A PNG with transparency standing on a map point (40-42 % of the frame high, bottom-centre anchored), popping in within 0.2 s, plain fade out, no shadow (the picture brings its own base). Follows the map. |
| Full-screen interlude | `media_full` | A picture or video clip covering the frame with a 0.5 s linear cross-dissolve in and out. The HUD, stat chips, captions and photo cards stay on top. **The map holds still under it** (camera and drift frozen) and returns at exactly the same position. |
| Zone label | `marker` with `"dot": false` | A county/zone name sitting on its region (white or yellow chip, 52 px high, no dot). |
| Stat chip placement | `stat` with `pos: {x, y}` | The references move stat chips per shot; `pos` places one anywhere (the anchors stay as presets). |

Layer order, bottom to top: map, fills, map data layers, markers, stickers, full-screen media, photo cards and filmstrip, stat chips, captions, HUD, watermark.

## Rules enforced before any browser starts
- A sticker and a photo card or filmstrip are never on screen together (the references show one rich picture at a time).
- Only one interlude at a time; a camera move cannot run under an interlude (the map is held still there), with a message saying to move it before or after.
- A filmstrip needs 3-7 cards; every card needs a picture; a pip needs media; a sticker needs a map position.
- Missing or wrong files are a clear error naming the layer: "pip "x": picture not found: nope.jpg (looked in ...)", "not a picture or video file", "could not read frames from ...".

## How clips are handled
Video clips are cut into JPEG frames at the render's frame rate before the render starts, and each output frame uses the matching clip frame (holding the last frame, or looping with `loop`). That keeps renders deterministic and avoids relying on browser video timing. Pictures are served as they are.

## Measured against the references
| Item | Reference | Ours |
|---|---|---|
| Card (3-card filmstrip size) | 419 x 303 | 420 x 303 (tested within 3 px) |
| 6-card filmstrip | cards 240 wide, 255 pitch | 240 wide, 256 pitch (tested) |
| Label chip | yellow, 42 px high, just under the card | 42 px, 6 px under (tested) |
| Entry | 115 %, 40 % opacity, 0.15-0.20 s | exactly those values (tested) |
| Exit | plain fade, 0.4-0.5 s | 0.45 s fade, no shrink (tested) |
| Interlude | 0.4-0.6 s cross-dissolve, map returns where it left | linear dissolve, camera held, position identical before and after (tested to 1.6 px) |
| Cards over footage | allowed | drawn above the footage (tested) |
| Same spec, same frames | n/a | the earlier determinism tests still pass |

A deliberate break (landscape card 380 px instead of 420) makes the card test fail.

## Bugs found and fixed on the way
- `cardRect`: the anchor `"center"` ends in "r", so it was placed at the right margin. Fixed and tested for all seven anchors.
- A cross-dissolve reused the ease-out fade; it is now linear both ways, as a dissolve should be.

## Honest limits
- **Card positions are presets plus offsets.** The references place cards by eye; the engine does not yet avoid covering the subject (that is the Phase 8 collision work).
- **Filmstrip alignment:** the 6-card strip in Reference 2 starts at the left (x about 76) while the 3-card strip is centred. Both are possible (`align`); there is no automatic rule, so the author picks.
- **Photo cards on a globe view** are positioned from the screen at the moment they appear; behind-the-horizon cases are not handled.
- Sticker art is the author's job (a library was deferred in the plan); this phase only draws it.
- Not in this phase: narration anchoring and name resolution (Phase 5), the globe zoom-out defect (open since Phase 1).
