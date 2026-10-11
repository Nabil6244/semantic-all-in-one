# Enoch Template — test baseline (before any Enoch Template code)

Recorded 2026-10-11 as Phase 0 of the Enoch Template work. Purpose: a fixed point to compare every later phase against.

| | |
|---|---|
| Commit the baseline was taken on | `05cfb49` (master) — "StarMap: Jupiter's moons, camera checks, auto short prompt, no silent picture gaps." |
| Working tree at the time | clean for tracked files; untracked: `graphics_overlays/`, `smart_text_overlays/` |
| Machine / interpreter | macOS (Darwin 24.3.0), `python3` = miniconda Python 3.13.13 (CI uses 3.12) |
| Command | `python3 scripts/run_tests_parallel.py` (same tests as `python -m unittest discover -s . -p "test_*.py"`, one process per module) |
| Result | **Ran 3343 tests in 186 modules in 210 s — OK**, exit code 0 |
| Runtime | 3 min 29.7 s wall, 762.5 s user, 95.2 s system (408 % CPU) |
| Skipped / failing modules | none reported. (`test_flow_agent_connection`, which is intermittent on its own, passed in this run.) |
| Files changed by the run | none tracked; no new untracked files |

## Phase 0 tests (added after the baseline run, so they are not part of the 3,343)

`python3 -m unittest test_enoch_template_phase0 -v` → **Ran 18 tests — OK**.

| Group | Tests | What it guards |
|---|---|---|
| `BookOfEnochUnchanged` | 2 | `styles/book_of_enoch.json` and `docs/styles/book_of_enoch_visual_guide.md` hash as recorded (sha256 of the file with CRLF normalised to LF). Book of Enoch sha256: `93e318447adbb417a4234012064f1ef844d7475cdd86d031481600f77385443a` |
| `ProtectedFiles` | 3 | the 228 files in `test_fixtures/enoch_template_protected.json` are unchanged and present; no new `.py` module inside a protected package; every other style file is covered |
| `StyleRegistry` | 3 | style ids = the 19 baseline ids plus at most `enoch_template`; Book of Enoch and Enoch Template are never chosen by auto-detection; Book of Enoch keeps empty detection weights |
| `ZeroCostSentinel` | 6 | `enoch_template_testutil.NoPaidCalls` refuses external network, DNS, Node/Chrome launches, Flow and AI-router calls, allows this machine and local programs, and restores everything afterwards |
| `HookSitesStillWhereTheSpecSays` | 4 | the `app.py` / `app_csv_prompts.py` insertion points of the specification exist; the render audio chain still has no loudness stage |

## Protected files

Packages and files that the Enoch Template work must not modify: `styles/` (every existing style), `docs/styles/book_of_enoch_visual_guide.md`, `modern_tech/`, `style_engine/`, `visual_allocation/`, `editorial/`, `graphics/`, `typography/`, `providers/`, `production/`, `ai_router/`, `flow-engine/`, `video_generator.py`, `asset_manager.py`. If one of them must change for a legitimate reason, the work stops and the exact diff is reported; the hashes are never refreshed to make a test pass.

## Re-running

```
python3 scripts/run_tests_parallel.py
python3 -m unittest test_enoch_template_phase0 -v
```
