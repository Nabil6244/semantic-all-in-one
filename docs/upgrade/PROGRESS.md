# Overnight progress (resume point)

Worktree: `/Users/muhammadnabil/Downloads/video_generator-main/.worktrees/upgrade`
Branch: `upgrade/overnight-2026-10-19` (from bf3e566). Plan: `docs/upgrade/OVERNIGHT_PLAN.md`.
Python: `/Users/muhammadnabil/Downloads/video_generator-main/.venv310/bin/python`.

Status: IN PROGRESS

## Items
- [ ] 0.1 branch point recorded
- [ ] 0.2 inventory
- [ ] 0.3 real-bug log report
- [ ] 0.4 baseline (tests, ui audit, timing)
- [ ] 1 real bugs RB-01..RB-10 + siblings
- [ ] 2 fault-injection hunt
- [ ] 3 workflow and navigation
- [ ] 4 shared action bar and feedback
- [ ] 5 code smoothness and measured speed
- [ ] 6 full QA + MORNING_REPORT.md

## Known baseline (bf3e566, full suite 05:15)
- 4710 tests / 285 modules, 340 s. FAILED before any change: test_enoch_template_phase0 and test_weather_isolation
  (protected-file manifests not refreshed after bf3e566 changed providers/nasa/*, app_csv_prompts.py, composition_styles/*,
  app.py lines; OWNER DECISION, do not refresh), test_whatif_script_guard (needed pytest; fixed in e27b627).
- Flaky: test_uhd_footage.TestFirstSecondsDownload (1 of 3 runs, bytes-served bound), test_flow_agent_connection (known).

## Real-bug register status
- RB-01 Hybrid compile traceback: ALREADY FIXED at bf3e566 (hybrid/local_fix.clamp_layers); replayed #021's real plan.json:
  2 compile problems before clamp, 0 after.
- RB-04 Flow prompt as stock query: ALREADY FIXED in c15cf1e (providers/base._search_words); log predates it.
- RB-11 (new) Pixabay API key written into generation.log + 400 on >100-char queries: FIXED e27b627.
- RB-02 "beat 2: type": source CSV "plan (1).csv" not on disk, log from 10-14 (pre never-stops work); not reproduced.

- RB-03/RB-06 Retry on CSV errors repeats the failure: FIXED b4fbc4f (Copy fix prompt for plan errors; live-checked).
- Static inventory (0.2): 144 controls, all wired; 4 dead helpers from the old project menu (_on_project_menu,
  _on_failed_check, _open_folder_path, inner _on_scroll) left alone. "Most buttons missing" is NOT what the code shows:
  the gaps are discoverability and workflow.

- RB-05 What If "stock_image provider is not configured" (97 scenes, #013/#015/#016): not in any 10-18/19 project;
  `_make_asset_manager` now always builds the stock provider with Openverse (no key). Not reproduced.
- RB-12 (new, LIVE in #021-#023) stock "first 30 s" download: 'certificate verify failed' with the bundled ffmpeg:
  FIXED 8fbca64, reproduced old-fails/new-works on the same Pexels clip.
- Latent (not changed): providers/media_clip/ffmpeg_clip._tls_opts adds -ca_file for plain http:// too; ffmpeg rejects it
  for an http server that does not redirect to https. Real sources are https; listed for the owner.
- Perf baseline: docs/upgrade/PERF_BASELINE.md (startup 1.3 s, all style panels ~150 ms: lazy panels NOT justified).
- Transcription model reuse 4be4b7a (identical words on real audio; saving ~1-3 s per call with 'small').
- 124 silent `except Exception: pass` in app.py: not mass-edited (merge risk with other sessions' app.py work); for the owner.

## Log
- 06:20 e42cfc5 Tools page in the sidebar (+ fit at 1100x700). b4fbc4f error-dialog fix prompt. Tests: test_tools_view,
  test_error_actions, test_ui_audit, test_phase2_ui, test_stress_keyboard_nav, test_ui_design_system, test_premium_ui,
  test_ux_consistency, test_terms_acknowledgement, test_keyboard_access, *_app_integration (hybrid/pakmap/starmap),
  test_generation_tracking, test_visual_plan_lifecycle_audit: all OK.
- 2026-10-19 00:10 plan written, worktree created.
- 05:40 e27b627 RB-11 fix + pytest-free guard test. Tests: test_stock_secret_redaction, test_whatif_script_guard,
  test_asset_pipeline, test_select_by_source, test_retry_change_source, test_commons_provider OK; test_uhd_footage flaky (see above).
