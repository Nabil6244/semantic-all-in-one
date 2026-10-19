# Performance baseline (2026-10-19, Apple Silicon, 8 cores, Python 3.13 venv)

Measured on the overnight branch (after the Tools page), with the real app built the way `scripts/ui_audit.py` builds it.

| What | Result |
|---|---|
| `import app` | 0.51 s |
| Window built (incl. dismissing the project picker) | 0.83 s |
| Widgets at startup / after visiting every page | 1,514 / 2,955 |
| All eager Visual Director builders together | ~150 ms (StarMap 57, style picker 37, Script 23, Weather 21, What If 12, Hybrid 8, pakMap 5, Overscaled 5) |
| Page switch, first visit (lazy pages build here) | 17-141 ms (Visual Director 141, Audio 137, Research 119) |
| Page switch, again | 29-114 ms |
| Whisper `small`, 30 s of real voiceover (#023) | ~14-18 s per call; model reuse saves ~1-3 s per call (4be4b7a) |
| Full test suite | 4,710 tests / 285 modules, 340 s (run_tests_parallel) |

## What this rules out
- **Lazy style panels:** the whole eager build is ~150 ms; not worth the risk of changing when each style's controls exist.
- **"Large numbers of widgets slow startup":** 1.5k widgets build in under a second; earlier CTk fixes (`ui/ctk_perf.py`) hold.
- **"Unbounded log panel":** already batched (50 ms) and capped at 20k lines when a project is open (`app.py` `_flush_log_ui`).

## Still worth measuring (needs a real run, owner approval)
- Long renders: segment reuse hit rate, manifest lookups on 200+ scene projects.
- Log panel with no project open (no cap in that case) during a long run.
