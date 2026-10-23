# Milestone 1 report: board foundation

Date: 2026-10-22. Scope: cream cards, growing arrows, column headers, `chip` cue, 8 code-drawn icons, fixed-slot layout with margins and collision checks.
**Nothing committed, staged or pushed. No protected file, `app.py`, spec, settings, UI, manifest or installer was touched.** Schema: [explainer_cue_schema.md](explainer_cue_schema.md) (frozen v1, written before the code).
Evidence: [m1_evidence/](m1_evidence/). Run on one Mac, offline, synthetic narration (word times by rule, not a human voice).

## Files changed
New (all untracked, under `explainer/` and `docs/explainer/`): `explainer/board/{icons,layout,elements}.py`, `explainer/spike/verify_m1.py`, `docs/explainer/explainer_cue_schema.md`, this report, `docs/explainer/m1_evidence/` (15 files).
Edited (themselves untracked from earlier phases): `explainer/board/cues.py` (new kinds, fields, arrow dependency check, schema version), `render.py` (placement, drawing dispatch), `builder.py` (layout runs before the strict check; manifest `schema_version`), `splice.py` (layout problems caught before anything is drawn), `explainer/spike/measure_render.py` (optional `probe` pixel, default unchanged).
Edit-by-edit: legacy kinds `type | pop | title | clear` keep their code paths; new kinds are skipped in the legacy loop and placed afterwards.

## Results
**Unit checks: 21 of 21 true** (every new problem path, strict vs non-strict, legacy positions unchanged by new cues, slot reuse after a clear, schema version, determinism).

**Cue-by-cue, 10 s fixture (beat 7.0 to 17.0 s), rendered through the unmodified `generate_hybrid_video`, read back from pixels** ([verify_m1.json](m1_evidence/verify_m1.json), [onset sheets](m1_evidence/cue_onsets_d0_0.jpg)):

| Cue | Kind | Slot | Word + offset | Latency after word, hard cut / dissolve 0.5 | Detected vs clip map (frames) |
|---|---|---|---|---|---|
| h1 | header | H1 | prices +0.0 | 0.000 / 0.033 s | 0 / 0 |
| c1 | card + icon | C1 | rose +0.1 | 0.106 / 0.139 | 0 / 0 |
| c2 | card + icon | C2 | homes +0.1 | 0.121 / 0.121 | 0 / 0 |
| a1 | arrow c1→c2 | gap | homes +0.3 | 0.321 / 0.321 | 0 / 0 |
| x1 | clear | | meanwhile | 0 frames vs sentence start | 0 / 0 (measured on c1) |
| h2 | header (H1 reused after the clear) | H1 | gold +0.0 | 0.006 / 0.039 | 0 / 0 |
| i1 | icon | C1 | flowed +0.2 | 0.212 / 0.245 | 0 / 0 |
| c3 | card | C2 | crown +0.1 | 0.115 / 0.148 | 0 / 0 |
| a2 | arrow i1→c3 | gap | crown +0.4 | 0.415 / 0.448 | 0 / 0 |
| x2 | clear | | nobody | | 0 / 0 (measured on c3) |
| c4 | card + icon | C1 | counted +0.1 | 0.106 / 0.139 | 0 / 0 |
| k1, k2 | chip | K1, K2 | 1545, 100,000 +0.1 | 0.103 / 0.136, 0.115 / 0.148 | 0 / 0 |

Summary: 11 of 11 drawable cues and both clears detected; **max error vs the clip's own frame map 0 frames in both modes**; vs the builder's ideal plan 0 frames (hard cut) and 1 frame (dissolve, the known pipeline rounding); held frames 0, skipped frames 0, one board run per render, 720 video frames (24.0 s). Render 15 s per variant.
First measurement note: my first run showed arrows 3 and 6 frames early. Cause: the detection box included the far end, which touched a card still scaling in. Fixed in the box (first 60 px of the shaft), not by loosening the check; re-run gives 0.

**Layout** ([layout_check.json](m1_evidence/layout_check.json)): 11 items, 0 outside the 96 px margins, 0 overlaps between elements visible at the same time, no arrow crossing a third element. Safe-area checks use box geometry, not pixels; the narrator zone (x < 640) stays empty.

**Before/after on legacy cues** (the themed Phase 1 results vs now): `verify_builder` cue rows (expected, detected, errors, latencies) identical; all checks true; board clip bytes identical (both dissolve modes); `verify_splice`: all checks true, board clips and the final render byte-identical (hard cut), variants identical apart from paths and timing. Legacy latency range unchanged (+0.006 to +0.233 s).

**Deterministic builds**: same process, two builds: clip bytes, frame MD5s and manifests identical, plain and instrumented. Across two separate runs of `verify_m1`: both clip SHA-256 identical (plain `aca2cd87…edd`, instrumented `4cfaf4c2…380`). Sample clip 272,903 bytes.

## Protection and off-mode
| Check | Result |
|---|---|
| Official guard `test_weather_isolation` (4 tests), before and after | **OK both times**, but see the caveat |
| Caveat | The manifest is dirty: another session refreshed `weather_protected.json` to match its own edits to 4 protected files (`composition_styles/starmap_beats_prompt.txt`, `composition_styles/whatif_csv_prompt.txt`, `starmap-engine/page.js`, `starmap/cinema.py`). So the guard proves nothing in the protected scope changed **relative to that dirty manifest**, not relative to HEAD. I added no file to any protected folder and edited none. I did not edit the manifest |
| `git status` and `git diff` of tracked files, before vs after | identical (10 modified files, all other sessions') |
| Off-mode snapshot (original fixture compiled by unmodified Hybrid, twice) | plan/rows/spec hashes, protected-scope hashes (571 files), folder census (1,331), HEAD identical to the splice-stage snapshot |
| `settings.json` hash | **differs** from the splice-stage snapshot. The file is git-ignored and was modified at 18:43:08, between two of my runs, not during one (my verification runs ended 18:42:20 and the next began later). I did not write it; I cannot prove who did (the running app or another session is likely). Contents not read or printed (it holds API keys). Not a protected file; flagged for you |
| Bytecode in `explainer/` | none |

## Visual scorecard against the reference (Phase 0 scorecard IDs)
| ID | Result | Notes |
|---|---|---|
| H07 legibility/overlap | PASS on geometry; no narrator mask yet | text fitted at 40 to 52 px; 0 overlaps; not tested on captions or maps |
| T03 change density | 5 of 5 two-second windows have at least 1 change (counts 2, 5, 1, 5, 2) | target ≥ 95% of windows; n = one 10 s fixture |
| T08 latency | 0.0 to 0.45 s after the word; none early. **9 of 11 within 0 to 0.4 s**; the two arrows (0.415, 0.448) are over because I set +0.4 s offsets | the provisional offsets are mine; ≥ 70% target met |
| T09 type-on | headers at 30 characters per second (the reference value) | one cue type; no caption policy yet |
| T10 palette/type | board #C0C0C0 exact, cream #F0E8C8, body Patrick Hand, titles Kalam Bold, chips Inter; role colours declared, `ink` for arrows | no ΔE measure on a rendered frame; role table not enforced across a video |
| M03 designed look | not rated (needs three reviewers) | my own read: clean, but see differences |
| T01, T02, T04 to T07, T11 to T13, M01, M02, M04, M05 | not applicable yet | need narrator, maps, director |

**Unresolved visual differences from the reference** (my reading of the shot list, not measured): cards are plain rounded rectangles with a colour tab (the reference's objects are drawn illustrations and cream scrolls with wooden rods); icons are 8 simple shapes, not illustrated objects; arrows are straight only (the reference also uses curved and crossing arrows); no narrator; headers are text with an underline, not two-column labels with dividers; layout is a fixed 2x2 grid plus rows, so every board looks alike; cards keep one shape. No regressions found among the checks above.

## Font and packaging status
Patrick Hand and Kalam Bold: OFL 1.1 texts stored beside the fonts; sources noted. **Inter: licence text still unverified** (the repo's `assets/fonts/` has none). Arrow glyph absent in all three fonts; arrows are drawn shapes. **Installers not changed; the new font folder and `explainer/` are not in the PyInstaller spec, so a packaged app would not contain them. Windows and macOS packaging: not tested.**

## Unresolved (unchanged)
`tail_frames=2` (not used here; no held frames appeared with 0 tail frames in this fixture, which does not settle it); Whisper word-time accuracy (this fixture uses rule-made word times); per-beat dissolve (still plan-wide).

## Remaining limitations
Fixed slots only (no free placement, no variable card sizes); at most 4 cards or icons visible at once; arrows straight, between two elements only; icon set is 8; text wraps at 3 lines; the sample renders with the instrumented overlay for measurement, the plain clip is [m1_sample_board.mp4](m1_evidence/m1_sample_board.mp4); [m1_full_frame.png](m1_evidence/m1_full_frame.png) is a separate demo frame with all kinds on one screen (different cue text).

## Next smallest step
M2 (narrator): freeze the narrator asset index and pose list on top of this schema (`params` is reserved), then draw the narrator layers once. Waiting for your approval.
