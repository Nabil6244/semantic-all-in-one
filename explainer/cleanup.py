"""After an Explainer video is exported and checked, its working files go (owner, 2026-11-24: a 5-minute video left 4.2 GB behind).

Everything deleted here is rebuilt by the next render on its own: board clips from their queue (board/jobs.py pending_boards.pkl), picture clips by
bake.bake_spec / bake_stills, map overlays and the presenter loop by post_render, the map pieces and the sound mix by the map render. Kept: the plan and
reports (json/pkl), the Flow pictures and other fetched media, the final video. Never raises; returns the bytes freed."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

EXPLAINER_PATTERNS = ("board_*.mp4", "board_*.mov", "baked_*.mp4", "still_*.mp4", "*_overlay.mov", "map_narrator_*.mov", "*__boards.mp4", "*.wav", "*.part.mp4")
WORK_FILES = ("pakmap_map.mp4", "pakmap_audio.wav")
WORK_DIRS = (".pakmap_segments", "stub_images/_vg_render_clips")


def _size(p: Path) -> int:
    try:
        return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return 0


def after_export(work: Any, log: Callable[[str], None] = lambda m: None) -> int:
    freed = 0
    try:
        work = Path(work)
        gone = []
        for d in (work / "explainer", work.parent / "explainer"):
            if d.is_dir() and (d / "render_report.json").is_file():
                for pat in EXPLAINER_PATTERNS:
                    gone += [f for f in d.glob(pat) if f.is_file()]
        if not gone:
            return 0                                   # not an Explainer project: nothing else is touched
        gone += [work / n for n in WORK_FILES if (work / n).is_file()]
        for f in gone:
            freed += _size(f)
            f.unlink(missing_ok=True)
        for n in WORK_DIRS:
            d = work / n
            if d.is_dir():
                freed += _size(d)
                shutil.rmtree(d, ignore_errors=True)
        log(f"[Explainer] working files removed after the export ({freed / 1e9:.1f} GB); the next render draws them again")
    except Exception as exc:
        log(f"[Explainer] some working files could not be removed ({str(exc)[:100]})")
    return freed
