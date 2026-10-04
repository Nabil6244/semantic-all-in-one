# Hybrid Map H1 report: hand-authored plan, compile, render (no AI)

Not committed. Files: `docs/hybrid/h1/` (contact sheet, plan, compiled pakMap script, 960x540 preview).

## Built
- `hybrid/plan.py` (plan model, JSON, technical validation), `hybrid/compile.py` (plan to pakMap rows with explicit times, lifetime rules, clip hand-over, `rows_to_csv`), `hybrid/generate.py` (plan + voiceover to video through the existing pakMap generator).
- Engine, all behind flags a PakMap script never sets: `lib/hybrid.mjs` (pure logic) and small edits to `lib/draw.mjs`, `lib/events.mjs`, `page.js`:
  - `spec.hybrid.pause_overlays`: the map layers' clocks stop under footage and resume on return;
  - `media_full.cover_ui`: footage draws over chips, cards, captions and the title (they dissolve with the map);
  - `media_full.xfade_prev`: a clip dissolves in over the previous clip, which stays opaque (no map flash);
  - `media_full.kenburns`: slow push-in on a still.
- PakMap plumbing: an optional `spec_extra` argument on the compiler and generator (nothing passes one for PakMap).

## Map-state continuity (as you specified)
The exact state is captured at footage entry by stopping each layer's animation clock, held through the footage, and restored on return; the layer's planned end stays in narration time. The camera is continuous (the engine already stops moves and drift under footage). One policy choice I made: a layer whose planned end falls under footage is held `return_grace_s` (0.8 s) after the map returns and then leaves, so the viewer sees the map resume; a layer that ends at the footage boundary leaves under the dissolve. A setting of 0 gives the strict original lifecycle.

## Evidence
- Engine (lossless render, byte comparison): the frame when footage ends equals the frame when it began, with a line mid-draw and a counter mid-count (and with camera drift on); the control without the option differs; footage covers the caption and stat chip; a PakMap-style interlude still leaves them on top; the dissolves are half-way at the middle; two clips hand over with no green map in the mix; ken burns moves a pattern while the map still restores.
- Real render (`h1-contact-sheet.jpg`, `h1-preview.mp4`): real NASA imagery and voiceover. Frame at 9.0 s versus 15.0 s: 1.1% of pixels differ, almost all the title chip that left by design; outside it 0.08%, scattered, at the same level as frame-to-frame encoder noise. The marker, the 47-million chip and the camera sit at the same pixels.
- Tests: pakmap-engine 124/124 (107 existing, unchanged, plus 17 new); full Python 2656 passed, 2 skipped; `test_hybrid.py` 28 tests. No existing test file was edited.

## Observations from the render (for your review)
1. The footage in this render is the repo's placeholder art, so footage quality is not judged here.
2. The title chip ("PART 1") leaves under the dissolve and does not return, by design (it belongs to its map beat).
3. Sound: a map to footage dissolve gets the soft transition; so does the clip-to-clip hand-over at 11.75 s (probably unwanted); the return to the map has none. Not changed in H1.
4. The dissolve-in and dissolve-out sit inside the footage beat's first and last 0.5 s, so footage beats are slightly shorter on screen than their span.
5. Not exercised yet: real stock/Flow/YouTube clips in a Hybrid plan (the Phase 8 machinery handles them; wired in H3), footage with its own audio (muted), long footage beats.
