# Explainer major upgrade plan: a 30-minute documentary (2026-10-27)

Planning only. No code, tests or app files were changed. Builds on `explainer_reference2_analysis.md` (phases 10-13) and `explainer_motion_kit_report.md` (stamps and date plates, done). Every phase stays opt-in (a `DirectorOptions` flag, default off), deterministic, and proves "flag off = identical to HEAD" with the recorded-baseline method already in `phase_motion_evidence/`.

## 1. The real problem at 30 minutes

The motion kit proved the mechanism but exposed three limits that a 30-minute video makes obvious:
1. **Repetition.** One slam, 2 textures, 6 tilts, one plate card. Rate-limited only by a 15 s gap. Over 30 minutes it becomes a habit. (Not measured at 30 min: nothing longer than 60 s has been rendered.)
2. **Sameness of shots.** Board beats look alike: narrator + scroll/line + tag. Nothing moves except elements appearing; the analysis measured the reference at a new meaningful element every 1.5-2 s plus camera crop changes on maps.
3. **No long-form control.** Nothing plans variety, pacing or quiet stretches across 30 minutes, and nothing has been timed, memory-checked or resumed at that length.

## 2. Phases (each ends in a review stop; no phase starts without your go)

| # | Phase | What the viewer gets | Main files | Risk / cost |
|---|---|---|---|---|
| A | **Long-form foundation** (do first) | A 30-min dry run (plan only, no render) that reports shot-type histogram, longest still gap, stamp/plate/effect rate per minute, family repeats; a budget system so any effect has a per-minute cap and a "rest" rule; resumable per-beat rendering and a render-time forecast | `director/pacing.py`, `director/plan.py`, new `explainer/spike/longform_check.py` | low; no visuals change |
| B | **Camera + texture layer** | Slow push-in or drift on every shot over 4 s, a reframe on key words, light grain and vignette so boards stop feeling flat | new `motion/camera.py`, `board/render.py` (one global transform), grain sprite in `assets/` | **medium: full-frame affine per frame; the analysis estimated tens of percent more render time and I have not measured it. First task is a 60 s timing probe; abort criterion: > +35 % encode time** |
| C | **Numbers and relations that move** | Count-up numbers that land on the spoken figure, cross-out strokes for negations, grow/draw-on arrows, staged diagrams (plate, then arrows, then labels, one per spoken fact), icon grids | `motion/presets.py` (`count_up`, `cross_out`, `pop`, `draw_on`), `compose_ref.py`, `board/elements.py` | low-medium; code-drawn, no assets |
| D | **Map overlay** | Arrows, a stamp, pin disc, date plate and draw-on country outline composited over the existing map clip, so maps stop being static stretches | new `explainer/beats/overlay.py` (inside the Explainer's own renderer; **no `pakmap/` edit**, read-only use of `pakmap.geo`) | medium: one extra composite pass per map beat; must stay inside the framing proof's view |
| E | **Scene variety and dossier look** | Dark "dossier" stage with a spotlight cone for secret/plan/document beats, dialogue bubbles for quoted speech, split/sort/seesaw layouts for contrasts, a rule that no layout family repeats 3 times in a row | `board/backdrops.py`, `compose_cartoon.py`, `select.py`, `pacing.py` | medium; art effort kept code-drawn (project rule: no per-video asset burden) |
| F | **Effect director for 30 min** | One planner that places stamps, plates, count-ups, camera moves and overlays from a budget, rotating variants (several stamp animations/colours, plate positions, push direction) so the same effect is never the same twice in a row | `director/compose_motion.py` generalised, new `motion/budget.py` | low once A-E exist |

Order: A, then B (so the cost question is answered early), C, D, E, F. A and B can be reviewed together; C-E are independent of each other and could run in parallel worktrees after B.

## 3. Rules every phase obeys

- Opt-in flag per phase, default off; `explainer_<phase>` setting read by `integration.py`; no `app.py`, spec, manifest or `hybrid/`/`pakmap/` edits without separate approval.
- Deterministic: frame = f(plan, time); encoded clips byte-identical across runs; no randomness (tables and CRC picks only).
- Flag-off equivalence proven against recorded HEAD baselines (plan, options, cue specs, clip names) after each phase.
- Assets built once by a `--check`-able script, hashed in a manifest, listed in `packaging.py`, never written during a render.
- Never-stop: a missing asset or a failed placement degrades to the plain look with a logged note, never an error.
- Acceptance is measured on frames and encoded clips (as with the plates), not only in-memory.

## 4. Acceptance for the whole upgrade (30-minute synthetic documentary)

1. Plan-only dry run of 30 min finishes in minutes with 0 problems; report shows: no still gap over 4 s outside deliberate holds, a new visual element every <= 3 s on average, no layout family 3x in a row, stamps <= 1 per 2 min, plates <= 1 per 3 min, every effect variant used at most twice in any 5 minutes.
2. Full render of 30 min completes, resumable after a kill, with measured wall time and peak memory reported (nothing measured today beyond 60 s: 37 s of video took ~14.5 s, ~0.4 s per second, which would be ~12 min of board encoding if all beats were boards; maps and the final assembly are extra).
3. Camera layer: text stays inside the safe area at every frame of a push-in; frame-to-frame difference > 0 during holds.
4. Count-ups end exactly on the spoken number and never show a wrong final value.
5. Map overlay pixels stay inside the framing proof's view; no `pakmap/` diff.
6. Flag-off = HEAD, byte-identical clip hashes; `verify_m1/m2/m3` unchanged.
7. A human look at a real 5-minute excerpt with a real voiceover before any 30-minute claim (I cannot judge quality from synthetic tone audio).

## 5. Not planned (rejected or deferred, as in the analysis)

Simulated 3D, lip-synced or walking actors, per-video bespoke illustrations, a sound-effect layer (reference SFX unverified), copying the reference's art or captions.

## 6. Known gaps and risks

- Quality is unrated by humans; relative claims come from my own frame comparison and the reference analysis (80 of ~120 sampled frames inspected, no audio analysis).
- Camera cost, map-overlay cost and 30-min memory are unmeasured estimates.
- The stale `m4_app_patch.diff` keeps `verify_m4` (2 checks) and Phase 8 (3 tests) red; it should be regenerated before the next verification round, otherwise every phase will carry the same five known failures.
- One Mac only; Windows and the second Mac untested.

## 7. Decisions needed from you

1. Start with A+B (foundation and camera/texture) as proposed, or go straight to C or D?
2. Is a ~35 % encode-time increase acceptable for the camera layer, or must it be cheaper?
3. May I regenerate `m4_app_patch.diff` (a separate small task) so verification is clean?
4. A real voiceover + script (5 minutes) for the human look: can you provide one?
