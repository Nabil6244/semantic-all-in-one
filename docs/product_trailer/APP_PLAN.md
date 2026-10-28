# Product Trailer: wiring it fully into Semantic YT Studio (plan, 2026-10-27)

## Where it stands

The engine is ahead of the app page. The page (`ui/product_trailer_section.py`, opened from the style picker under Explainers)
has: phone + colour, feature CSV, optional music, "Copy CSV prompt", disclaimer, resolution, 30/60 fps, Generate → Render → Stop,
progress panel, stall watchdog. Nothing starts until Generate.

What the engine can do that the page cannot reach yet:

| Engine feature | On the page today |
|---|---|
| Two paces: fast **Trailer** (reference 1) and slow **Reveal** (reference 2) | no; only via `#pace,reveal` in the CSV |
| Colour per phone from `phones.json` (Navy, Sky Blue, Pink, White, Black) | no; a fixed list of 8 generic names |
| Several colours cycling (Reveal) | no; only via `#colors,...` in the CSV |
| Real 3D model (`assets/models/phones/<id>.glb`) or code-built fallback | not shown; the user cannot tell which one is used |
| Background per CSV row (stars, wash, gradient, horizon, studio, charcoal, image) | CSV only (fine), no help on the page |
| Quality (sub-frame samples) | fixed at 8 |
| Preview before a long render | none: Render is the first time the user sees anything |

Fixed while planning: Render passed the Stop event itself to `render()`, which calls it; now passes `is_set`.

## Plan

### Step 1: make the page match the engine (small, app-only)
1. **Style switch**: `Trailer (fast cuts)` / `Reveal (slow studio)` segmented button → `build_spec(pace=...)`. The CSV's `#pace`
   line wins only when the page is left on its default.
2. **Colours from the phone**: when a phone is picked, fill the Colour box from that preset's `colors` in `phones.json`
   (fall back to the generic list). Reveal shows a multi-pick (up to 4) instead → `build_spec(colours=[...])` (planner: one new
   argument, same as `#colors`).
3. **3D model status** under the phone box: "Real 3D model: galaxy_s25_ultra.glb" or "Code-built model (add a .glb for an exact
   phone)", plus **Add 3D model…** (file picker → copies the .glb into `whatif-engine/assets/models/phones/<id>.glb`) and a link
   to the folder README with the free model list. Read-only check, so it does not break "nothing starts until Generate".
4. **Quality**: `Draft (fast)` = 2 samples, `Final` = 8 → a spec-wide `samples` default.

### Step 2: preview before render
5. After Generate, a **Preview** button renders 6 stills (`WHATIF_STILLS`, one per act) in a few seconds and shows them as a
   contact sheet on the page, with the shot list (time, move, colour, background, text). The user can re-Generate (new seed)
   until it looks right, then Render.

### Step 3: output extras
6. **Description file** beside the video: title, features list, the disclaimer, and the CC-BY credit line of the .glb when a real
   model was used (from `<id>.LICENSE.txt`).
7. **Music**: optional pick from the app's existing music library by mood (`starmap.music`) when no file is chosen; music stays
   optional, the reveal pace works silent.
8. Project restore: remember page options per project (`state/product_trailer/options.json` already holds them).

### Step 4: hardening (before pushing)
9. Tests: page wiring (style/colour/model/quality reach `build_spec`), Stop during Render, preview stills, protected-file tests.
10. Windows: paths in `phone_glb.mjs` / model copy, the GPU check (software GL fallback is already in the What If runner).
11. One full render of each pace from the app (not the CLI) on this Mac, then CI on Windows + both Macs.

### Later (parked)
- 9:16 Shorts cut of both paces.
- AI lifestyle shots from Flow (reference 2's room / hands scenes) mixed between 3D shots.
- Per-shot editing on the shot list (change move, colour, background) before Render.

## Files

| Step | Files |
|---|---|
| 1, 3, 5 | `ui/product_trailer_section.py` (page), `product_trailer/planner.py` (`colours`, `samples` args) |
| 3 | new `product_trailer/models.py` (find / copy .glb, licence note) |
| 5 | `product_trailer/preview.py` (stills + contact sheet) |
| 6 | `product_trailer/render.py` (description file) |
| 9 | `test_product_trailer.py`, new `test_product_trailer_page.py` |

`app.py` needs no change beyond the hooks already added (additions only rule).
