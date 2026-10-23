"""The one entry point the application would call (Milestone 4b, after approval): never raises, returns the plan or the reasons it could not make one."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

from .director import DirectorOptions, direct


def cartoon_share(settings: Optional[Dict[str, Any]]) -> float:
    """The only setting read: `explainer_cartoon_share`, the largest share of the runtime the director may turn into cartoon beats. Missing, unreadable or negative means 0 (none); at most 0.5."""
    try:
        v = float((settings or {}).get("explainer_cartoon_share", 0.0) or 0.0)
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return 0.0 if v != v or v <= 0 else min(v, 0.5)


def direct_plan(words: Sequence, script: Optional[str], settings: Dict[str, Any], *, work_dir: str, duration: Optional[float] = None, places: Sequence[str] = (),
                archive_dir: Optional[str] = None, dissolve_s: float = 0.0, log: Callable[[str], None] = lambda m: None) -> Dict[str, Any]:
    """Returns {"plan": dict | None, "problems": [...], "warnings": [...], "report": {...}}. `settings` is the application's settings dict (read only; the one key read is `explainer_cartoon_share`, default 0)."""
    opt = DirectorOptions(work_dir=work_dir, places=list(places), archive_dir=archive_dir, dissolve_s=float(dissolve_s), cartoon_share=cartoon_share(settings))
    r = direct(words, script, opt, duration=duration, log=log)
    return {"plan": r.plan, "problems": r.problems, "warnings": r.warnings, "report": r.report}
