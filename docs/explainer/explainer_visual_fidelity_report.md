# Explainer visual-fidelity pass: report (2026-10-23)

One focused pass on how the boards look, after M4a and its content-quality gate. Nothing here is a human rating: **no reviewer has seen these boards**, and visual quality is not proven.
Evidence: `docs/explainer/m4_visual_fidelity_evidence/` (sheets, frames, metrics, regression, guard). Schema: [v1.3](explainer_cue_schema_v1_3.md). Code is under `explainer/` only.

## 1. Gap analysis

### Verified from the reference frames (R2, t = 24 to 118 s; `reference_frames/`)
1. Flat grey board, no cream cards on the boards inspected.
2. Large illustrations: white circles with a role-coloured ring (blue, green) and a one-word label in the same colour; white rounded tiles with an orange outline and a one-word label below.
3. A navy tilted tag with yellow handwriting ("x3 income"); a dark rounded year chip; a heavy outlined yellow display title with a small subtitle; a large "?"; a cream scroll with brown rods.
4. A diagram: light box, filled box, one big arrow between them.
5. Typed lines, the punchline in a larger red. Labels are 1 to 3 words.
6. Content spreads over most of the area right of the narrator; the narrator is small and on the left.

### Our frames before this pass (`classic`)
Cream rounded cards in four fixed slots, a 3-to-5-word quote in each, mean font 49 to 51 px, peak screen occupancy 0.19 to 0.32, no pictures large enough to read as illustrations, one arrow weight, no title/scroll/tag/diagram.

### My suggestions (design judgement, not observed in the reference)
Pick a layout per sentence by what it says (question, hook/twist, contrast, concept list, list-with-picture); bigger text; shorter labels under pictures; the narrator's pose should not be counted as content change.

## 2. What changed (all under `explainer/`; protected files untouched)
| File | Why |
|---|---|
| `board/styles.py` (new) | tile, circle, box, lite, tag, scroll and typed-line elements, measured and drawn from existing code-drawn icons; nothing generated |
| `board/cues.py`, `board/render.py`, `board/elements.py`, `board/layout.py`, `board/builder.py` | the `visual` cue kind (schema 1.3), free placement with the usual collision checks, arrow width and chip size parameters (defaults byte-identical) |
| `director/compose_ref.py` (new) | reference-look authoring: scroll / title / flow / tiles / split layouts, vertical centring, concept variety, quantity tag, still-gap repair with pictures or synced typed lines |
| `director/options.py`, `plan.py`, `compose.py`, `pacing.py` | `look` option (`reference` default, `classic` keeps the old cards), strict "meaningful" change measure, peak-occupancy and the two still-gap measures |
| `spike/quality_gate.py`, `quality_compare.py`, `verify_m4.py` | evidence tooling; every old M4 check now runs with `look="classic"`, new reference-look checks added |

## 3. Per-topic results (same five synthetic topics; `sheets/`, `quality_before_after.json`)
"Meaningful" counts picture, title, line, box, tag, scroll, chip, arrow, card and caption starts, map layers and camera steps, archive starts and cuts; **not** narrator poses, clears or per-word growth.
| Topic | look | texts | mean words | content coverage | all-change windows | meaningful windows | peak occupancy mean / min | mean px | still gap all / strict (s) | narrator share / longest absence |
|---|---|---|---|---|---|---|---|---|---|---|
| aqueducts | classic | 17 | 5.7 | 0.891 | 1.00 | 0.917 | 0.262 / 0.166 | 50.6 | 3.13 / 3.13 | 0.51 / 13.3 s |
| aqueducts | reference | 23 | 4.0 | 0.880 | 1.00 | 0.917 | 0.378 / 0.145 | 64.3 | 1.76 / **3.53** | 0.51 / 13.3 s |
| coffee | classic | 12 | 5.8 | 0.899 | 1.00 | 0.889 | 0.243 / 0.187 | 48.9 | 2.66 / 2.66 | 0.478 / 9.6 s |
| coffee | reference | 18 | 3.7 | 0.849 | 1.00 | 0.889 | 0.402 / 0.232 | 63.1 | 1.58 / **3.35** | 0.478 / 9.6 s |
| inflation | classic | 13 | 5.9 | 0.870 | 0.944 | 0.778 | 0.256 / 0.166 | 49.7 | 2.55 / 2.55 | 0.511 / 9.0 s |
| inflation | reference | 19 | 3.8 | 0.823 | **0.889** | 0.778 | 0.353 / 0.272 | 61.2 | 2.95 / **3.25** | 0.511 / 9.0 s |
| printing | classic | 12 | 4.8 | 0.781 | 0.938 | 0.875 | 0.319 / 0.195 | 49.8 | 1.76 (own measure) / not recorded | 0.482 / 8.8 s |
| printing | reference | 16 | 3.1 | **0.659** | 0.938 | 0.875 | 0.354 / 0.297 | 61.3 | 2.17 / 2.95 | 0.482 / 8.8 s |
| glaciers | classic | 9 | 6.2 | 0.786 | 0.765 | 0.706 | 0.193 / 0.166 | 49.3 | 2.31 / 2.75 | 0.54 / 10.1 s |
| glaciers | reference | 13 | 4.0 | 0.751 | 0.824 | 0.765 | 0.356 / 0.273 | 63.5 | 2.55 / 2.86 | 0.54 / 10.1 s |

No phrase in either look ends or starts on a function word (0 in all ten rows). The reference look has 4 to 6 single-word labels per topic (picture labels, by design).

### Regressions, not hidden
- **Content coverage fell** in every topic (printing most, 0.781 to 0.659): labels are shorter than quotes.
- **Inflation all-change windows fell** 0.944 to 0.889; the inflation all-change still gap rose 2.55 to 2.95 s.
- **Strict still gaps are above the 3 s target in three topics** (aqueducts 3.53, coffee 3.35, inflation 3.25 s). They measure gaps where only a narrator pose, a clear or already-shown words change. In "all-change" terms five of five are within 3 s. The earlier "aqueducts 3.13 s" figure was the classic measure; the two looks were not comparable before this pass (they used different measures) and now both are reported.
- **Meaningful change did not improve** in four of five topics (identical to classic). The pass changed what the boards look like, not how often something new happens. Only glaciers improved (0.706 to 0.765). **The 95% target is not met by anyone and I do not claim it.**

### Answers
- **Glaciers 88% to 76% (M4a gate).** Reproduced (classic still 0.765). The 76% is two consecutive map beats (0 to 10.1 s), whose windows take no caption layer, plus the last board with a 2.3 s gap. The earlier 88% came from 10 cards on boards; fewer, longer quotes removed some appearances. The reference look recovers part (0.824 all-change, 0.765 meaningful) because pictures and titles add appearances on the boards; the map beats are unchanged.
- **Aqueducts still gap.** In classic, beat e4 has 3.13 s in which the words shown are already shown and the narrator is absent. In the reference look e4 has an all-change gap of 1.76 s and a strict gap of 3.53 s. Strict repair is limited to 3 repairs per beat and to layouts that pass collision; it did not close it.
- **Why boards look sparse.** Peak occupancy is 0.35 to 0.40 on average (0.19 to 0.32 before); minimum 0.145 (a single title). A sentence gets one idea by design (one thought per board, cleared at the next sentence), so a short sentence yields a lone scroll or title (`frames/inflation_pair_t15.0.jpg`). Only the meaningful content of that sentence is shown; no filler was added to raise occupancy.
- **Fixed slots / generic.** The classic look used four fixed slots. The reference look measures each element and places it freely, but it picks among five layout families by rules, so boards vary by sentence type and still repeat within a video. It is rule-based variety, not authored composition.

## 4. Evidence that nothing else moved
| Check | Result |
|---|---|
| `verify_m1` / `verify_m2` | all checks true; every SHA-256 field equal to the recorded evidence (2 and 20 fields) |
| `verify_m3` | 115 of 115 true; the plan hash differs because the plan file contains the work-folder path (a different folder than the recorded run); the clip hashes equal |
| `verify_builder`, `verify_splice` | all checks true |
| `verify_m4` | **253 of 253** true: existing M4a checks under `look="classic"` plus new reference-look checks (both dissolve settings x five topics: plan valid, tiling, gates, clips exist with exact frame counts, every label and line a contiguous quote, independent replay equal byte for byte, cue frames on the frame rule, no network, two folders identical) |
| Off-mode snapshot | identical to the earlier evidence |
| `app.py`, `VideoGenerator.spec`, `settings.json`, `hybrid/` | unchanged against HEAD; same SHA-256 prefixes as before |
| `m4_app_patch.diff` | still applies cleanly (`git apply --check`); not applied |
| Official guard `python3 -B -m unittest test_weather_isolation` | **OK, 4 tests**, but **only against the dirty manifest**: another session refreshed `test_fixtures/weather_protected.json`, so this is not proof against HEAD. I did not refresh it |
| `git status` | the same set of paths as at the start; nothing staged, committed or pushed |

## 5. Remaining differences and what cannot be verified
- The reference's lettering and drawn art are hand-made; ours is Patrick Hand and code-drawn icons. No cartoon scenes, no second character, no real map imagery (Phase 7). The narrator is a single code-drawn cartoon character (not a stick figure like the reference's), with six poses.
- Map beats carry no layers over the pictures and cannot be repaired when short; archive beats count as one change.
- Strict still gaps above 3 s remain in three topics; meaningful density below 95% everywhere.
- Single-sentence boards stay sparse; occupancy was not measured on the reference, so no like-for-like occupancy claim.
- Not verified: independent human ratings, real-voice timing, cross-OS runs, the GUI, packaging, Inter's licence. Phase 8 (M4b app integration) and Phase 7 have not started.
