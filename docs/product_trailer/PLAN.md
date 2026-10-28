# Product Trailer style — plan (2026-10-27)

Reference: `Samsung Galaxy S27 Ultra Trailer Official Look Launch.mp4` (87 s, 1280x720 @ 60, music only, a fan "concept trailer").
Goal: from a short feature list + a music track, render a trailer that reads like that reference, with the phone built in code
(no model download, no per-video assets).

## What the reference does

~38 cuts in 87 s (one every ~2.3 s), cut on the music. Night-sky star field behind almost every shot. Four acts:

| Time | Act | What is on screen |
|---|---|---|
| 0–17 s | Cold open | No text. Macro across the lens island, low "monolith" angle up the back (twice), flat edge-on profile, back corner turning. |
| 18–51 s | Features | One feature per 3–4 s, text beside the phone: lock screen clock → "Slimmer. Stronger" → "The next-gen / 200MP / main sensor" → "50MP ultrawide" → "Aluminum Frame" on a red/orange swoosh → "Android 17" on a purple aurora → back with wordmark over a night horizon (city lights) → chip logo in a gold spark burst. |
| 51–78 s | Second pass | Faster moves: profile, island macro, giant "120Hz" over a screen macro, side edge with buttons, flat back, port/edge macro, front with lock screen. |
| 78–87 s | Reveal + card | "Introducing / Galaxy S27 Ultra" beside the island; then a plain-text disclaimer card ("conceptual trailer, not affiliated..."). |

Text look: white, bold condensed sans; a small kicker above a huge figure, a small line under it; placed in the empty half of the frame,
never over the phone. Colour washes are full-frame, the phone floats over them.

## What already exists (uncommitted)

- `whatif-engine/lib/product.mjs` — `kind: "product"` shot: code-built phone/iphone/chip, studio reflections, glow, bloom,
  moves `island, monolith, hero, profile, orbit, screen, edge, chip, chip_macro`, lock-screen texture.
- `whatif-engine/layers/pt_bench.mjs` — benchmark bars layer.
- Wiring in `scene3d.mjs`, `shots.mjs`, `page.js`, `layers/index.mjs`.

Cold-open moves are mostly covered. The gaps are below.

## Gaps

1. **Phone design parameters**: camera layout (Ultra: 3 big lenses + 1 small + flash, no bar), flat frame, colour, wordmark on the back,
   buttons/ports on the edge. Make `galaxy` a real object (`placement()` already checks for it but `PRODUCT_OBJECTS` doesn't list it).
2. **Backdrops**: star field ✓, plus `wash` (red/orange swoosh, purple aurora) and `horizon` (dark land + distant city lights).
3. **Text layers** (product-film type, `pt_` prefix):
   - `pt_feature`: kicker / big figure / sub line, auto-placed in the empty side.
   - `pt_tagline`: one short line ("Slimmer. Stronger").
   - `pt_bigtype`: huge word over or behind a macro ("120Hz").
   - `pt_reveal`: "Introducing" + product name.
   - `pt_card`: plain end card (disclaimer).
4. **Badge burst**: a generic chip badge with a gold spark burst (no real logo by default).
5. **Music-cut timing**: detect beats/onsets in the track, snap cuts to them, ~2–3 s shots, faster in act 3.
6. **Planner**: feature list → spec. Feature type picks the move (camera → island/monolith, frame → edge/wash, display → screen/bigtype,
   chip → badge, thin → profile, OS → wash + front). Variety rules: no move twice in a row, alternate front/back, cold open has no text.
7. **App**: its own style page (picker → Product Trailer) reusing the What If renderer. Nothing starts until Generate.

## Phases

**Phase 1: look match (no planner).** Gaps 1–4. A hand-written 20 s spec, rendered and compared frame by frame with the reference
(contact sheets side by side). Done when the side-by-side reads as the same kind of film.

**Phase 2: music + planner.** Gaps 5–6. Input = feature CSV + music file → spec → render. Done when a full ~60–90 s trailer comes out
of one CSV with no hand edits, cuts on the beat, and no repeated moves back to back.

**Phase 3: app.** Gap 7: style page, CSV prompt text (like `docs/whatif/WhatIf_CSV_prompt.txt`), Generate → Render, disclaimer card on by default.

**Later / parked**: voice-over mode, 9:16 Shorts cut, other products (watch, tablet, laptop, earbuds).

## Feature CSV (draft)

```
order,feature,kicker,value,sub,look
1,camera,The next-gen,200MP,main sensor,
2,camera,,50MP,ultrawide,
3,frame,,Aluminum Frame,,wash:red
4,os,,Android 17,,wash:purple
5,chip,,Snapdragon 8 Elite Gen 6,,badge
6,display,,120Hz,,bigtype
```
Plus one header row with product name, colour, wordmark, lock-screen date/time, and the disclaimer text.

## Research decisions (2026-10-27)

- **3D route:** parametric three.js phone generator (`whatif-engine/lib/phone_models.mjs` + `data/phones.json` presets), spending
  effort on lighting/shading: physical glass (transmission), anisotropic metal, accumulated sub-frame supersampling + motion blur.
  Step-ups if it still reads "game engine": Poly Haven CC0 studio HDRIs bundled once (`studio_small_09`, `photo_studio_loft_hall`,
  `monochrome_studio_02`), then three-gpu-pathtracer for macro hero shots, then headless Blender/EEVEE. Keep the phone spec engine-neutral JSON.
- **Not used:** AI video for the hero phone (inconsistent lens layout); free GLB models (patchy, licence risk); scraping GSMArena (ToS forbids).
- **Spec data:** user/LLM fills the CSV from official spec pages (CSV prompt), plus layout archetypes per brand.
- **Music:** user supplies the track (YouTube Audio Library safest). Beats via ffmpeg decode + numpy onset detection; librosa optional.
- **App:** Semantic YT Studio (CustomTkinter). New style registered through `ui/style_registry.py` + `ui/style_pages.py`; `app.py` additions only.

## Open decisions

- Music-only (like the reference), or a voice-over option from the start?
- Real brand logos/wordmarks (user-supplied images), or generic badges only?
- Output size: 1920x1080 @ 30, or @ 60 like the reference (60 doubles render time)?
