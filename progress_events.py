"""Structured progress events (Semantic YT Studio 2.0 — Batch 1, PHASE 9).

Replaces free-text log-line progress inference with a typed event the UI
can consume directly. Uses the EXISTING `_ui_queue` architecture (a plain
``queue.Queue`` of ``(kind, payload)`` tuples, drained by app.py's
``_poll_queue``) — this module does not introduce a new threading or
communication mechanism, only a new, structured payload shape for the
existing ``"progress"`` kind.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ProgressEvent:
    phase: str  # e.g. "assets", "whisper", "editorial", "rendering", "mux"
    current: int
    total: int
    status: str = "running"  # "running" | "done" | "error"
    message: str = ""
    scene_id: Optional[str] = None
    eta_seconds: Optional[float] = None

    @property
    def percent(self) -> float:
        try:
            if self.total <= 0:
                return 0.0
            return max(0.0, min(100.0, 100.0 * self.current / self.total))
        except (TypeError, ZeroDivisionError):
            return 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["percent"] = self.percent
        return d


# Human-readable phase labels, shared so app.py's UI and any future
# consumer render the same names as the (already-established) pipeline
# stage prints, e.g. "Generating Assets", "Aligning Voiceover".
PHASE_LABELS = {
    "assets": "Generating Assets",
    "whisper": "Aligning Voiceover",
    "editorial": "Compiling Editorial",
    "rendering": "Rendering",
    "mux": "Finalizing Video",
}


class EtaEstimator:
    """Simple, dependency-free ETA: average time-per-unit so far, applied to
    the remaining units. Never raises; returns None when there isn't enough
    data yet (fewer than 1 completed unit) rather than a misleading guess."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    def reset(self) -> None:
        self._start = time.monotonic()

    def estimate(self, current: int, total: int) -> Optional[float]:
        try:
            if current <= 0 or total <= 0 or current >= total:
                return None
            elapsed = time.monotonic() - self._start
            per_unit = elapsed / current
            return per_unit * (total - current)
        except (TypeError, ZeroDivisionError):
            return None


def make_event(
    phase: str,
    current: int,
    total: int,
    *,
    status: str = "running",
    message: str = "",
    scene_id: Optional[str] = None,
    eta: Optional[EtaEstimator] = None,
) -> ProgressEvent:
    """Convenience constructor used by producers (video_generator.py,
    app.py) so every call site builds the event the same way."""
    eta_seconds = eta.estimate(current, total) if eta is not None else None
    return ProgressEvent(
        phase=phase,
        current=int(current),
        total=int(total),
        status=status,
        message=message or PHASE_LABELS.get(phase, phase),
        scene_id=str(scene_id) if scene_id is not None else None,
        eta_seconds=eta_seconds,
    )
