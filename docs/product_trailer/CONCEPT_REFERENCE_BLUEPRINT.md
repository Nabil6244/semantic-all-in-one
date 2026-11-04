# Concept-trailer reference blueprint

Source: three fan concept films from `Tech 2/` (iPhone 20 Pro Deep Red, Galaxy S26 Ultra Unboxing, Nothing Phone (2)).
Method: cut times (ffmpeg scene > 0.12), luma and frame-difference motion sampled at 4 fps, dense 4 fps sheets of each opening shot.
These are patterns to adopt, not assets to copy. No watermarks, logos or end cards from the sources.

Tooling: metadata is stripped, so the 3D software is unknown. Look is consistent with a path-traced or PBR renderer (Blender Cycles/Eevee, C4D, or equivalent). We do not need to know it.

## Measured structure

| Film | Length | Shot length | Mean luma | Motion (4 fps diff) |
|---|---|---|---|---|
| iPhone 20 Pro | 115 s | ~7.4 s (cuts at 7.0, 14.5, 21.9, 30.2, 47.9, 55.7, 63.2, 70.4, 77.9) | 16 (near black) | 6-9 for first 50 s, then 0.2-2 (slow tail) |
| S26 Unboxing | 98 s | ~7.5 s (15.5, 31.2, 39.9, 47.4, 54.8, 62.2, 69.4, 75.5) | 121 (white studio) | 8-17 first 40 s, 1-3 later |
| Nothing Phone (2) | 54 s | 1-3 s, bursts of 2-4 frame flashes at 16.6, 19.6, 31.1 | 90, swings 3 to 225 | 10-24 throughout |

Last ~15-20 s of the two long films is a static disclaimer card (motion 0, luma 0-3). Not copied.

## Shot grammar (dense-frame findings)

1. **Opening = fade up from black over ~1 s (4 frames) into an extreme macro of an edge** (S26: box + pen side profile; iPhone: button edge). Camera is a slow pull-back/orbit; the object slowly reveals itself over 6-7 s and ends as a full-device hero. Each shot is one continuous move, ease-in-out, no cuts inside.
2. **Edge highlight is the lighting.** Dark films: black void, red/magenta rim light along the chamfer, prismatic colour fringe on the first frames (thin-film/anisotropic look) that settles to a clean rim as the camera pulls back. Studio films: near-white cyclorama, soft contact shadow, no hard lights.
3. **Floating object, no table** in dark films. Reflections only from the rim; body gets a vertical gradient (lit top, falls to dark) so the phone seems to emerge from the void.
4. **Shot ends by fading to black**, not a cut (iPhone shot 1 darkens in the last 3 frames). Studio shots cut to a new angle.
5. **Nothing Phone**: the opposite rhythm. Short shots, object rotates on its own axis (side profile → back, tilting ~15-20°), a camera punch-in (~2x scale in 0.25 s), glow-line animation on the back (ring draws on), flash-white transitions, exploded glass layers, black-to-white background swap. Gives energy, but cuts are masked by flashes.
6. **Hero pairs (S26)**: two colourways side by side + box, then top-down and 3/4 views; closing with a large macro on the camera module.
7. **Title lockup** (S27): handwritten script over drifting outline art on black. Optional.

## Rules to implement (generic, per `feedback_fix_code_not_video`)

- Shot planner: default shot length 6.5-7.5 s for "premium reveal" looks; 1-3 s with flash masks for "energetic" looks.
- Move per shot = single eased camera path: macro edge → pull back → hero. Never static for more than ~1 s (see `feedback_no_still_screens`).
- Fade-from-black over ~1 s for the first shot; fade-to-black on dark-look shots.
- Dark look: black void, rim light along edges, vertical body gradient, brief fringe highlight on first 0.5 s only.
- Studio look: white cyc, soft contact shadow, slight overexposed background.
- Per-shot motion budget: mean frame-diff 6-17 during the first half, calmer second half, so the film breathes.
- Colourway pair shot + macro camera-module shot as standard beats for phone films.
- Nothing-style flash/ring-draw transitions as an opt-in "energetic" look.

## Not yet checked

- Which of these patterns `product_trailer/` and `whatif-engine/layers/pt_*` already do. Do that comparison before building (see `feedback_keep_existing_features`).
- The iOS concept films (3D phone + 2D UI screen recordings) were only seen at 24 frames each; no dense pass. The macOS, iOS 18 and iPhone 18 Pro sheets were not viewed.
- Audio (music, whoosh timing) was not analysed.

## Engine comparison (2026-11-03, by reading `whatif-engine/lib/product*.mjs` headers and grepping; nothing rendered)

Already there (real three.js product studio, PBR metal, env lighting):
- Camera moves: island, monolith, hero, profile, orbit, screen, edge, flip, rise, port, buttons, chip, chip_macro, reveal; near-constant-speed travel.
- Fade from/to dark: `dim_in` / `dim_out` ease key/rim/env lights.
- Backdrops: stars, wash, horizon, studio (dark cyc), charcoal, daylight (bright seamless studio).
- Rim and sweep lights, bloom, screen power-on, live lock screen, iridescent lens glass.
- Colourway lineup room (`product_room.mjs`), x-ray with explode (`product_xray.mjs`), fold phone.

Gaps vs the three references (not found in code; verify before building):
1. Unboxing: no retail box object or box + phone + pen composition (S26).
2. Stylus / pen part on the phone (S26, S27).
3. Nothing-style glow-line "ring draws on" animation on the back, and exploded display glass layers (x-ray explodes internals only).
4. White-flash / hard-cut-masking transitions for the energetic look.
5. Thin-film colour fringe on the frame edge in the first 0.5 s of a macro (iridescence exists on lens glass only).
6. A single "extreme macro edge, pull back to hero" move as one continuous path (macro moves exist; the combined pull-back is unverified).
7. Handwritten script title lockup over drifting outline art (not checked in the layers).

## UI-concept films (iOS 17/18/19, iOS 19 Concept, macOS), contact sheets only

Viewed 24-frame sheets, no dense pass. Observed:
- Alternating backgrounds: black/deep-purple and near-white, switching per feature block.
- Each feature = a kinetic title (blur-in, 1-2 words, gradient-tinted text, e.g. "Dynamic Dock", "Lock Screen") then a phone or laptop that tilts in 3D with the 2D UI on its screen, then a macro close-up of the interface (menu, widget, toggle list) filling the frame.
- Opens on a notification or boot screen; closes with a logo outro / "not real software" card (not copied).
- iOS 19 Concept ends with an After Effects timeline screen recording at the end: the UI motion is made in After Effects. The 3D device is likely a separate 3D render. This is the only direct evidence of tools in all 11 files.
- iPhone 18 Pro (Technizo) is the same grammar as the other Technizo films: dark gradient, rim light, macro camera module, slow orbit, black disclaimer at the end.
- The iPhone 20 Pro Deep Red sheet (file 11) was never viewed as a sheet; its dense pass was done earlier.

## UI-concept films, dense pass (2026-11-03)

Method: 10 fps luma/motion over all five films (iOS 17, iOS 18, Meet iOS 19, iOS 19 Concept, macOS), true hard cuts at scene > 0.3, and one 4 fps sheet of a full feature block for iOS 18, macOS, iOS 19 Concept and iOS 17 (iOS 17's sheet was made but not viewed; Meet iOS 19 was not sheeted).

| Film | Hard cuts | Dark share | Background swaps |
|---|---|---|---|
| iOS 17 | 5 | 47% | 6 (about every 7-20 s) |
| iOS 18 | 22 | 40% | ~every 7 s |
| Meet iOS 19 | 33 | 34% | ~every 1.7 s in the middle section |
| iOS 19 Concept | 7 | 12% (mostly light) | 3 |
| macOS | 13 | 53% | ~every 6.5 s |

Most of the "cuts" are not cuts: they are dissolves, scale-ins and blur crossfades. The frames are almost never a straight cut.

### One feature block (about 7 s, seen in iOS 18 and macOS)
1. 0.0-1.3 s: the title types on word by word (about 4 words per second), small gradient-tinted text near the top of an empty background. Dark block: pale purple text on near black. Light block: purple text on off-white.
2. 1.3-2.0 s: the title slides to the top, the device rises in below it (phone or the dock), and the UI is already live.
3. 2.0-6.0 s: the demo plays on the device while the device scales up so the UI fills most of the frame (iOS 18: phone grows from ~35% to ~60% of frame height; macOS: crop to the dock and a folder popup, mouse cursor visible).
4. 6.0-7.4 s: the whole frame dissolves into the next block's background (light to dark or dark to light) and the next title starts typing before the old device has fully gone.

### iOS 19 Concept (light, 3D device plus layers)
- Wall of phones (6-8 lock screens, each a different wallpaper) drifting vertically, then one phone isolates and shrinks.
- The phone blur-dissolves into the next title ("Apps Redesigned", "For Years Ahead"): title fades up first from a blurred ghost of the phone, so the phone becomes the text.
- Next block: the phone tilts in 3D (~25-35° yaw) while the UI exploded into layered cards ("Settings" with Glitch Lab, Airplane Mode, Wi-Fi, Bluetooth rows) separated in depth and settling flat as the phone turns to face the camera.
- Dock/icons get an icon construction grid reveal at the start (thin lines drawing a squircle).

### Engine implications (append to the gap list)
8. Word-by-word typed title with gradient tint and blur-in, per feature block (check `pt_bigtype`, `pt_subtitle`, `tm_title`).
9. Dark/light block alternation and a whole-frame dissolve between blocks.
10. Device scale-up so the UI fills the frame during a demo, with a visible cursor.
11. UI layers exploded in depth and settling flat as the phone turns (cards at different z, tilt 25-35°).
12. Phone-to-title blur transform and phone-wall (6-8 lock screens drifting).
13. Icon construction-grid line reveal.
Not seen: any audio analysis; the unviewed iOS 17 and Meet iOS 19 blocks.
