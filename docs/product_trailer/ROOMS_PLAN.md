# Product Trailer: real-looking rooms with a four-phone lineup (hybrid plan, 2026-10-27)

Reference: `Introducing The Galaxy S27 Ultra.mp4` (184 s, 720p30, ~30 shots of ~6 s, music only, bottom-centre captions, one spec per shot).
What it does that the current reveal pace does not:

| Reference | Today |
|---|---|
| Four phones (black / blue / pink / white) together in almost every shot, matching ripple wallpapers | One phone per shot, colours cycled across shots |
| Photoreal rooms (loft, lake terrace, studio with lights and camera, window table), shallow depth of field | Charcoal fog, stars, washes |
| Hands holding the phones (AI footage) | none |
| Chip close-up on a circuit board + gold streak | chip package shot, no board |
| 3 minutes | 87 s |

Decision (2026-10-27): **hybrid**. Flow makes *empty* room plates; our 3D four-phone lineup is composited on top with contact shadows.
AI never draws the phone (inconsistent lens layouts, wrong design); the 3D model stays the single source of truth for the phone.

## The rule that shapes it: a plate library, made once

"No per-video asset burden": plates are NOT generated per render. A library of 12 to 20 empty rooms is made once (Flow images), checked
once, annotated once, and reused by every phone video. A new video costs no Flow calls.

## 1. Plates (Flow images, once)

Prompt template (per room): "empty [room], a [wooden table | concrete plinth | marble shelf] in the lower third, centre, completely
bare, camera at table height, 35 mm, shallow depth of field, soft [window | studio] light from the [left | right], photoreal, no people,
no phones, no text, no logos". Rooms: loft with city view, lake terrace, studio with softbox and cine camera, window table, white gallery,
dark showroom, living room, desk setup, balcony, tech lab, garden courtyard, concrete atrium. 3 candidates each, keep the best.

Quality gate (per plate): no people, no phones, no text or logos, a clear flat surface, no strong tilt. Auto-check (OCR for text, a
person/phone detector if cheap) plus a human look at one contact sheet. Rejects are regenerated.

Metadata per plate (JSON beside the image), measured once: surface front edge y and back edge y (fractions of the frame), horizon y,
light direction and warmth, average colour, blur level, safe area for captions, mood tags (display, camera, battery, chip, durability, design).

Open risk: Flow image size (~1344x768) is below 1080p. Shallow depth of field hides softness; add matched grain. The 4K footage plan's
upscaler decision is separate.

## 2. Compositing in the engine

A new backdrop kind `plate` (the existing `image` backdrop is a flat camera-facing picture with no floor and no shadow):

1. **Matched camera.** Camera height, pitch and FOV come from the plate metadata so the table's perspective agrees with the phones'.
2. **Shadow catcher.** An invisible floor at the table height that only receives shadow: a soft contact shadow under each phone plus a faint,
   blurred, fading reflection when the surface is glossy.
3. **Matched light.** One key light from the plate's light direction and warmth; the studio environment tinted by the plate's average colour; exposure
   matched so the phones do not glow or sink.
4. **Matched finish.** The phones get the plate's depth of field (the far phones slightly soft), the same grain and vignette; edge softening so
   no cut-out halo.
5. **Locked camera.** A flat plate has no parallax, so the 3D camera does not orbit. Motion comes from the phones (turn, slide in, power-on
   one by one) plus one slow push (1 to 4 percent) applied to plate and camera together. Orbits and macros stay on the studio / fog shots.

## 3. The four-phone lineup (3D)

New object `lineup`: four phones from one preset, colours from the preset (Black, Blue, Pink, White), spaced in a row with small depth
stagger. Poses: all backs (camera plateaus), all fronts (wallpapers), one forward and three behind, a gentle fan. Each phone has its own ripple wallpaper
in its colour (plus the crystal "Gorilla" variant and a wave variant). Motions: reveal turn (back to front), staggered power-on, slide-in
from the side. Cost: 4x the geometry, so roughly 4 to 6 minutes of render per 90 s, about 12 minutes for 3 minutes.

## 4. Special shots

- **Opening:** charcoal fog studio, one phone (already built).
- **Chip on a board:** a 3D circuit board (green-black, traces, gold pads) under the chip package, gold light streak, depth of field.
  Chip logo: generic badge unless real logos are approved.
- **Hands:** parked for v1. AI hands would show a different phone. If wanted later, defocused, screen-toward-camera hands shots from Flow video.

## 5. Planner changes (reveal pace, longer)

- Feature list to ~30 beats of ~6 s (3 minutes), one caption each, bottom-centre, as the reference.
- Each feature picks a plate by mood tag: display = bright gallery, camera = studio with camera gear, battery or charging = living room,
  chip = board scene, durability = concrete, design = loft or terrace.
- Rules: no plate twice within 4 shots; at most 3 uses of a plate per video; lineup pose never the same twice in a row; the first shot is the fog studio and
  the last is the title card.

## 6. App

A "Backdrop library" panel on the Product Trailer page: thumbnails, mood tags, add/replace plate, regenerate a plate through Flow, per-video
exclude. Preview renders 6 stills (one per act) before the full render. Nothing starts until Generate.

## Phases and stop points

| Phase | Work | Done when |
|---|---|---|
| 0 | Test 6 plate prompts through Flow images (uses a Flow account, agent mode, a few images) | You judge the plates good enough |
| 1 | Engine: `plate` backdrop, shadow catcher, matched light/finish, `lineup` object. 3 stills on 3 plates | Side by side with the reference reads as a photo |
| 2 | Library of 12 to 20 plates with metadata + QA; planner rules; 3-minute pacing | One CSV gives a 3-minute film, no hand edits |
| 3 | Chip board, colour-switch moves, polish | The special shots match the reference |
| 4 | App panel, preview, tests, full render from the app, CI on Windows and both Macs | You approve the render |

## Risks

- "Sticker" look if perspective or light do not match: only gentle camera angles, plates generated for eye-level, manual tuning knobs per plate.
- Flow plates may contain stray objects or fake brand text: the quality gate.
- Flow reliability (anti-abuse hold on video in September; images worked in agent mode on 2026-10-06 and are only needed once).
- Phone design: the reference phone is a fan design (full-width plateau, two stacked lenses + pill) and the CAD leaks show a horizontal bar with three
  cameras. One design per video, labelled as a concept.
- Render time with four phones and sub-frame samples; draft quality (2 samples) for previews.

## Decisions needed

1. Which S27 design is the default: the reference's (`galaxy_s27_video`) or the leak (`galaxy` horizontal bar)?
2. Real brand logos (user-supplied) or generic badges and plain wordmarks?
3. Hands: skip for v1?
4. Phase 0 go-ahead: which Flow account, and how many test images?
5. Output size: 1080p at 30 fps (reference is 720p30)?
