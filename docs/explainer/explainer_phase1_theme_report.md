# Phase 1: board theme

Date: 2026-10-22. Nothing committed, staged or pushed. Companion to [explainer_phase1_font_check.md](explainer_phase1_font_check.md).

## What was built
| File | Change |
|---|---|
| `explainer/assets/fonts/` | New: `PatrickHand-Regular.ttf`, `Kalam-Bold.ttf`, both OFL texts, `README.txt` (sources, roles). Both licences are SIL OFL 1.1 (headers read) |
| `explainer/board/theme.py` | New: `Theme` (board #C0C0C0, ink, cream paper #F0E8C8, yellow title, dark chip, role colours, sizes, tracking), font loader, tracked-text helpers, `draw_chip`, `draw_object` |
| `explainer/board/render.py` | Changed: default look is now the theme (Patrick Hand body with 6% tracking; Kalam Bold yellow title with dark-brown outline and overshoot; flat role-coloured discs with a thin dark outline and a hand-lettered label). An explicit `font_path` still selects the old placeholder look |
| `explainer/board/builder.py` | Changed: `font_path=None` now means the theme (it used to mean a placeholder Inter face) |

Chips: Inter SemiBold is read from `assets/fonts/` (not copied). That folder has no licence text, so Inter's licence file is **unverified**.
Cue timing code is untouched; only drawing changed.

## Checked
- Rendered a sample frame ([board_theme_frame.png](phase1_evidence/board_theme_frame.png)): two typed lines (with accents, digits, dash), three objects with labels, title, chip. Reads cleanly on the grey.
- Re-ran the existing verification on the themed look ([verify_builder_themed.json](phase1_evidence/verify_builder_themed.json), [verify_splice_themed.json](phase1_evidence/verify_splice_themed.json)): all checks true; cues detected, 0 frames of error against the clip map in both dissolve modes; latency +0.006 to +0.233 s; builds deterministic (clip bytes identical). The one-held-frame-in-hard-cut finding from the splice report still reproduces (1 held frame in one run), as expected.
- `git status` identical before and after the verification runs; no bytecode created; no protected file, fixture, manifest or setting touched.

## Not done / open
- Not yet a `chip` cue kind (helper only); objects are still placeholder discs (icons are Phase 3); no cream-paper card, arrows or column headers; no narrator (Phase 2).
- Lower-case body text is a flag (`body_lower`), off by default so proper nouns keep capitals.
- Tracking, title colours and object colours are provisional; no side-by-side with a reference crop and no three-reviewer rating yet.
- Inter licence unverified; shipping the new fonts in installers is not wired (no spec or app change made).
- Text is placed at fixed default positions; no collision or margin checks.
