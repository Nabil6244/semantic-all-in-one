# Explainer scorecard (Phase 0)

Status: draft for approval. 26 checks in three tiers. Thresholds marked **P** are provisional: they come from one 2-minute reference segment (R2 0:00 to 1:59.7, [manifest](explainer_reference_manifest.json)), hand-annotated, 640×360, ±0.5 s. They must be re-derived on a second segment before they are treated as targets.

## How scoring works

Three numbers are reported separately and never averaged together.

1. **Gate** (H01 to H08): pass/fail. Any failure means **FAIL**, whatever the other scores are. A beautiful video that stalls, loses an asset, or changes ordinary Hybrid output does not pass.
2. **Style score** (T01 to T13): each check scores 1 (within range), 0.5 (within the tolerance band stated), 0 (outside). Reported as a percentage with weights below. It measures similarity to the reference, not quality.
3. **Human rating** (M01 to M05): 1 to 5, blind, at least three reviewers, one of whom has not seen the reference. Reported as a mean and the lowest single score.

Verdict for a phase: **PASS** only if Gate passes, Style score ≥ the phase's stated floor, and no Human rating mean below 3.0. Floors are set per phase in Phase 0 sign-off (suggested: 50% after Phase 2, 70% after Phase 6, 85% after Phase 7). They are **P**.

Severity: **blocker** (cannot ship), **major** (fix before the phase is closed), **minor** (log and fix when convenient).
Method: **auto** = a script or test can decide it, **manual** = a person decides, **both**.
Required material: **REF-A** = reference segment R2 0:00 to 1:59.7 (shot list in the manifest); **TEST-2** = a 2-minute test render of the same narration; **TEST-10** = a 10-minute render (needed for T01, T05, T13 across a whole video); **BASE** = baseline Hybrid render of the same inputs.

## Tier 1: Hard gates (technical, pass/fail)

| ID | Measures | How | Pass | Method | Material | Severity |
|---|---|---|---|---|---|---|
| H01 | Render completes and plays | Exit status ok; ffprobe reads the output; video and audio streams present | ok = true; duration within 0.1 s of narration | auto | TEST-2, TEST-10 | blocker |
| H02 | No missing assets | Asset resolver report plus the engine dry run (`pakmap/guard.py` `dry_run`, `check_gfx`) | Zero unresolved asset ids; zero rows dropped by the guard that Explainer itself created | auto | TEST-2, TEST-10 | blocker |
| H03 | No blank or black frames | Frame sampler (the repo has `visual_qa/frame_sampler.py`) at 2 fps | No frame with mean luma < 8 or flat colour longer than 0.5 s, except a declared fade | auto | TEST-2, TEST-10 | blocker |
| H04 | Audio intact | Narration level, clipping, A/V drift | Narration present for the whole video; no clipping; drift ≤ 40 ms | auto | TEST-2 | blocker |
| H05 | **Regression**: Explainer off leaves Hybrid unchanged | Compile the same inputs (see baseline plan in the report) with the switch off before and after; compare `hybrid_plan.json`, `hybrid_script.csv` byte for byte and a set of frame hashes at fixed times; run the existing Hybrid tests | Identical plan, CSV and frame hashes; existing Hybrid test files pass | auto | BASE, fixture `test_hybrid_app_plan.json` | blocker |
| H06 | **No per-render asset creation** | Asset manifest of the render: every Explainer asset id resolves to the packaged library with a recorded licence; nothing written under the library during render (directory hash before and after) | 100% from the library; library hash unchanged | auto | TEST-2 | blocker |
| H07 | Legibility and overlap | Draw caption/label masks and test overlap with the narrator and key graphics (the approach in [normal_gfx/captions.py](../../normal_gfx/captions.py)); text inside the safe area | No text clipped; no label over the narrator's face or another label; overlap area ≤ 2% | both | TEST-2 | major |
| H08 | Never-stop and fallbacks | Run the dry run with a deliberately removed asset and an unavailable beat type; the stall watchdog log | Render completes; the fallback is logged in the plan notes; zero stall events | auto | TEST-2 with injected faults | blocker |

## Tier 2: Measurable style targets (similarity to the reference)

Weights add to 100. A check that cannot be run yet is reported "not measured", not 0.

| ID | Weight | Measures | How | Target (REF-A value) | Tolerance band (0.5) | Method | Material | Severity |
|---|---|---|---|---|---|---|---|---|
| T01 | 10 | Layer mix: share of runtime for cartoon / board / map / archival | Sum of beat seconds by `mode` from the plan | cartoon 33%, board 33%, map 27%, archival 8% **P**; accept each of cartoon, board, map in 25 to 40% over TEST-10 | ±10 percentage points of REF-A on TEST-2 | auto | TEST-2 and TEST-10 | major |
| T02 | 8 | Shot length distribution | Beat durations from the plan; cross-check with a scene-change detector (it undercounts light-to-light cuts, so the plan is the primary source) | Median 4.6 s; 90% of shots between 2.0 and 8 s; no shot > 12 s without a change event **P** | Median 3.5 to 6.0 s | auto | TEST-2 | major |
| T03 | 8 | Change density | Count of annotated change events (text typed, object added, label, camera step) per 2 s window from the plan's layer start times | ≥ 1 change per 2 s in ≥ 95% of windows (REF-A: 58 of 60 windows by hand) **P** | ≥ 85% of windows | auto | TEST-2 | major |
| T04 | 6 | Unintentional static time | Longest run of nearly identical frames (frame difference) not declared as a hold | ≤ 3 s **P** | ≤ 5 s | auto | TEST-2 | major (the standing "no still screens" rule) |
| T05 | 6 | Narrator presence and return interval | Narrator presence from the plan; share of runtime and longest absence | Share about 50% (REF-A: ≈ 50% estimated); longest absence ≤ 30 s (REF-A: 25.8 s) **P** | Share 35 to 60%; absence ≤ 40 s | auto | TEST-2 and TEST-10 | minor to major |
| T06 | 7 | Narrator consistency and mouth activity | Asset id of the narrator layer set is the same in every beat; at least 4 distinct poses used per 2 minutes; mouth open frames vs speech activity from word times | One narrator asset id 100%; mouth moving during ≥ 90% of speech seconds and ≤ 10% of silence **P** | 80% / 20% | auto | TEST-2 | major |
| T07 | 8 | Cut alignment to speech | Beat start times vs sentence and clause starts from the word list (the same analysis done in Phase 0) | ≥ 70% of cuts within ±0.3 s of a sentence or clause start (REF-A: 16/22 to 17/22 within 0.25 s = 73 to 77%) **P** | ≥ 55% | auto | TEST-2 | major |
| T08 | 8 | Object and title latency | Layer start time minus the time of its cue word (`gfx_templates.find_cues`) | 0 to +0.4 s after the cue word; none earlier than −0.2 s (REF-A: +0.0 to +0.3 s, n = 3) **P** | ≥ 70% inside the window | auto | TEST-2 | major |
| T09 | 6 | Caption policy and type-on speed | Words per caption; characters per second of type-on | Captions are key phrases: ≥ 80% ≤ 8 words; type-on 15 to 40 characters per second (REF-A: ≈ 30, n = 1) **P** | ≥ 60% / 10 to 50 | auto | TEST-2 | minor |
| T10 | 8 | Palette and type adherence | Board background within ΔE 6 of #C0C0C0 (reference value is ±8 per channel); text colours restricted to the declared role table; body face is the approved font | Board ΔE ≤ 6; 100% of text in declared roles; 100% approved fonts **P** | ΔE ≤ 10 | auto | TEST-2 | minor |
| T11 | 8 | Map and archival relevance | Every map label and pin is a place in the narration window; every archival image has a `reason` and its subject appears in the window | ≥ 95% of map labels match; 100% of archival have a reason | ≥ 85% | both (auto for labels, manual for images) | TEST-2 | major |
| T12 | 8 | Metaphor and colour-role continuity | Declared colour roles never swapped inside a video; a declared signature metaphor keeps the same asset ids on each recurrence | 100% role consistency; ≥ 3 recurrences per 10 minutes for a declared metaphor **not yet measured in the reference**, so this number is a placeholder | role swaps = 0 | both | TEST-10 | major |
| T13 | 9 | Structure present | Plan labels: hook within 30 s, a puzzle or question stated within 2 minutes, a stated reversal or twist, an aphorism or conclusion; one primary idea per beat (LLM judge plus manual) | All four present in TEST-2; ≥ 90% of sampled beats judged one-idea. Recap and callback frequency: **UNRESOLVED** (needs a whole-video pass over the references) | 3 of 4 | both | TEST-2 (hook, puzzle), TEST-10 (recap, callback) | major |

Not made unconditional: a 7 to 8 s change interval (the reference's real shot rate is 5 s and its visible change rate is about one per second), "narrator every 2 to 3 beats" (the reference has a 25.8 s gap), "a recap every 8 minutes" (not supported by anything measured yet).

## Tier 3: Subjective human judgment

Rated 1 to 5 against the reference segment, blind and in random order, at least three reviewers.

| ID | Question | Pass | Material | Severity if below pass |
|---|---|---|---|---|
| M01 | Does this look like it belongs to the same family as the reference? | mean ≥ 4.0, no score below 3 | TEST-2 next to REF-A | major |
| M02 | Is the narrator appealing and recognisably the same character throughout? | mean ≥ 4.0 | TEST-2 | major |
| M03 | Do the board and cartoon compositions look designed (spacing, hierarchy, no clutter)? | mean ≥ 3.5 | TEST-2 | major |
| M04 | Is the argument clear without the voice-over text? Does each picture help the sentence? | mean ≥ 4.0 | TEST-2, TEST-10 | major |
| M05 | Would you publish this? | mean ≥ 4.0 and no "no" | TEST-10 | blocker for release only |

## Open threshold questions

These cannot be set honestly yet. Each needs measurement, not a guess.
1. Whole-video layer mix (T01): only the first two minutes were shot-listed. Needs the TEST-10 reference pass.
2. Recap and callback frequency (T13) and signature-metaphor recurrence (T12): not measured.
3. Narrator mouth behaviour (T06): whether it follows the audio is not known; the 90% / 10% figures are a design choice.
4. Latency windows (T08, T09): n = 3 and n = 1 fine measurements. A 10 fps pass over 20 more cues is needed.
5. Phase style-score floors (50 / 70 / 85%): a guess until the first test renders exist.
6. Frame-difference threshold for "static" (T04): to be set on the first real render, not on the reference.
