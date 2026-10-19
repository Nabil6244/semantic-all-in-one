# Overnight upgrade plan (2026-10-19)

One program: UI/UX upgrade + real-bug hunt + debugging + code smoothness + QA. Run unattended on branch
`upgrade/overnight-2026-10-19` in the worktree `.worktrees/upgrade`. Progress and the resume point live in
`docs/upgrade/PROGRESS.md`; any session (this one or the auto-resume task) continues from there.

## Owner approvals (given 2026-10-19, in chat)

| Action | Allowed |
|---|---|
| Edit code in the worktree | yes |
| Commit | yes, on `upgrade/overnight-2026-10-19` only, one commit per finished item |
| Push / merge into master | **no** (owner reviews in the morning) |
| Full test suite | yes, in the background, once per step (`.venv310/bin/python scripts/run_tests_parallel.py`) |
| Renders | short golden samples only; no long renders, no Flow, no paid API calls |
| Protected-file manifests (`test_fixtures/*_protected.json`) | **never** |
| Destructive actions, the main checkout, other sessions' files | **never** |
| Real projects in `~/Downloads/VideoGenerator` | read only; experiments run on copies in a temp folder |

## Hard rules

1. Preserve every feature, style, provider, template and setting. No placeholders, no "simplified" versions.
2. Never assume: trace the full path before calling something broken or working.
3. Every bug fix gets a test that fails before and passes after, and is checked against the real project data that
   showed it, when such data exists.
4. A step whose tests fail twice is stopped, left uncommitted on a `wip/` note in PROGRESS.md, and the next
   independent item starts. Nothing broken is committed.
5. Report honestly: "ran and passed", "ran and failed", or "not run". Never claim untested work.
6. Do not edit the main checkout. Another session is editing `gfx_templates.py`, `test_gfx_planner_selection.py`
   and `test_gfx_templates.py` there; avoid those three files entirely to keep the morning merge clean.
7. Keep `app.py` diffs small and local; other sessions also change it.

## How real bugs are found (method copied from the other sessions)

The other sessions fix real bugs because they start from a real symptom in a real project, not from reading code:
symptom -> reproduce on a copy -> root cause -> smallest fix -> test -> verify on the real data -> honest report.
Tonight's hunt uses the same loop, fed by evidence that already exists on disk:

- `~/Downloads/VideoGenerator/*/logs/generation.log` (23 projects) and `state/production_events.jsonl`,
- each project's plan files (`whatif/visual_plan.json`, `beats.csv`, manifests) replayed through the dry-run /
  check / heal entry points (no network),
- fault injection with fixtures: damaged mp3, missing media file, mismatched CSV vs voiceover, locked file,
  empty provider config, offline network.

### Real failures already seen in the logs (starting register)

| ID | Evidence (count) | Suspected defect | Class |
|---|---|---|---|
| RB-01 | `HybridCompileError` raised through `_on_generate -> _run_hybrid_generation` inside a Tk callback (18x) | validation error escapes as a traceback instead of a message | silent/crash path |
| RB-02 | `[WEATHER] Generation failed: beat 2: type` | unreadable error text | confusing message |
| RB-03 | same CSV error repeated after 3 Generate presses | no jump-to-row / auto-repair from the error | workflow gap |
| RB-04 | `pixabay search failed for "Cinematic, realistic CG for a serious space documentary..."` | a Flow prompt is used as a stock search query in fallback | wrong behaviour |
| RB-05 | `stock_image provider is not configured for this run` (49x) | run starts without a provider the plan needs; no pre-check | pre-flight gap |
| RB-06 | `vo_anchor ... is not in the narration` / `only spoken before the previous row` | anchors out of order; error lists rows but offers no fix | workflow gap |
| RB-07 | `What If render failed: frame missing at N s` | render-time missing frame | broken |
| RB-08 | `stock asset exceeded ...`, Pexels I/O errors, Commons 404 | download failures with no alternative tried | resilience |
| RB-09 | Flow `PUBLIC_ERROR_UNUSUAL_ACTIVITY` (110x) per scene | each scene retries a restricted account; log spam | resilience/UX |
| RB-10 | `Exception in Tkinter callback` in `_hybrid_accept_import` / `finish` (1x) | uncaught callback error | crash path |

Bug classes the other sessions have fixed recently (look for siblings of each in other styles):
CSV/voiceover mismatch, media saved under the wrong scene key, unrelated media chosen (colour-bars clip, NASA
fallback), stale clips reused after a fix, overlays drifting early (anchor vs beat timing), clipped place boundaries,
damaged audio stopping PyAV, transcription model reloaded per call with a 4-thread cap, same-clip restart, manifest
race and Windows file locks, settings window forgetting state, ambience silence/loops.

## Steps

Each step: work -> focused tests -> commit -> PROGRESS.md update. Full suite at the end of steps 1, 3, 5, 6.

### Step 0 - Safety net and baseline (no behaviour change)
- 0.1 Record branch point (bf3e566) and the three files owned by the other session.
- 0.2 Static inventory of every button, menu item, switch and binding -> handler -> backend
  (`docs/upgrade/INVENTORY.md`), with orphan handlers and backend features with no UI.
- 0.3 Log mining report (`docs/upgrade/REAL_BUGS.md`): every distinct error across the 23 projects, grouped.
- 0.4 Baseline: full test suite result (known failures listed), `scripts/ui_audit.py` result, startup/page-switch timing.

### Step 1 - Real bugs and broken actions (highest value)
- RB-01..RB-10 in order of user impact, plus siblings of each class in the other styles.
- Every Generate path: exceptions become a readable message with the next action, never a traceback.
- Every unwired/no-feedback control found in 0.2.

### Step 2 - Fault-injection bug hunt
- Per style (Normal, Overscaled/Exp Solar, pakMap, Hybrid, StarMap, What If, Weather, Enoch): damaged audio,
  missing media, CSV vs voiceover mismatch, empty provider config, offline network, cancel mid-run.
- Expected result for each: clear message, nothing lost, Retry works. Each failure found -> fix + test.

### Step 3 - Workflow and navigation
- Sidebar Tools group (CSV Generator, Learning, Ratings, Activity); overflow entries stay.
- Pre-flight checklist before Generate (inputs, providers, CSV/voiceover match, anchors) with fix buttons.
- Validation errors show the row and a "copy repair prompt" / auto-repair action where one exists.
- Disabled controls say why.

### Step 4 - Shared action bar and feedback
- One component: Plan, Generate, Cancel, Retry failed, Open folder, Open log; only actions the style supports.
- Cancel for styles that lack it, where the backend can stop safely (verify What If, Weather, Normal).
- "What we fixed" summary after guards/repairs.

### Step 5 - Code smoothness and measured speed
- Broad `except Exception: pass` in user-facing paths: add logging, no behaviour change.
- Lazy build of style panels, deferred startup work, log cap without a workspace - only if the baseline shows a cost.
- Transcription: reuse the loaded model, thread count from the governor (timing must be identical in output words).
- No large `app.py` extraction tonight (merge risk with other sessions); list candidates for the owner.

### Step 6 - Full QA and report
- Full suite, UI audit (both themes, 3 sizes), per-style dry runs on real project copies.
- `docs/upgrade/MORNING_REPORT.md`: what changed, commits, tests run with results, what failed, what was skipped and why,
  decisions for the owner, and how to merge.
