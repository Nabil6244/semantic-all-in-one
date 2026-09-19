"""Lightweight, failure-safe performance instrumentation for the render pipeline.

Design constraints (Semantic YT Studio 2.0 — Batch 1):
  - Uses time.monotonic() only (never wall-clock) so timing is immune to
    system clock adjustments.
  - Every public entry point swallows its own exceptions: instrumentation
    must never be able to break rendering. A failure here is silently
    absorbed and simply produces a missing/zero measurement, never a crash.
  - Structured events (PerfEvent dataclasses), not raw log strings, so a
    future UI/analytics layer can consume them without string parsing.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PerfEvent:
    """One measured span. `extra` carries span-specific structured fields
    (e.g. for a scene render: scene_id, cache_hit, encoder, output_duration)."""

    name: str
    duration_s: float
    extra: dict = field(default_factory=dict)


class PerfRecorder:
    """Collects PerfEvents for one pipeline run. Never raises.

    Usage:
        perf = PerfRecorder()
        with perf.timer("whisper"):
            transcribe_audio(...)
        with perf.timer("scene_render", scene_id="007", cache_hit=False):
            render_one_scene(...)
        print(perf.summary())
    """

    def __init__(self) -> None:
        self.events: list[PerfEvent] = []
        # Cache hit/miss tally, kept separately since it's reported as a
        # single aggregate line ("Cache: N hits / M misses"), not per-event.
        self.cache_hits = 0
        self.cache_misses = 0

    @contextmanager
    def timer(self, name: str, **extra):
        start = time.monotonic()
        try:
            yield
        finally:
            try:
                elapsed = time.monotonic() - start
                self.events.append(PerfEvent(name=name, duration_s=elapsed, extra=dict(extra)))
            except Exception:
                # Recording the measurement must never surface as a pipeline error.
                pass

    def record(self, name: str, duration_s: float, **extra) -> None:
        """Non-context-manager form, for spans measured by hand (e.g. across
        two separate call sites where a `with` block doesn't fit cleanly)."""
        try:
            self.events.append(PerfEvent(name=name, duration_s=float(duration_s), extra=dict(extra)))
        except Exception:
            pass

    def note_cache(self, hit: bool) -> None:
        try:
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1
        except Exception:
            pass

    def total_for(self, name: str) -> float:
        """Sum of durations for all events with this name (e.g. every
        'scene_render' span) — 0.0 if none recorded or on any error."""
        try:
            return sum(e.duration_s for e in self.events if e.name == name)
        except Exception:
            return 0.0

    def count_for(self, name: str) -> int:
        try:
            return sum(1 for e in self.events if e.name == name)
        except Exception:
            return 0

    def total_elapsed(self) -> float:
        """Best-effort total: sum of every recorded span. Spans that overlap
        (e.g. a scene_render span nested inside a broader "rendering" span)
        would double-count here — callers building the summary use each
        named phase's own total, not this, for the headline number; this is
        exposed for callers that only record non-overlapping top-level spans."""
        try:
            return sum(e.duration_s for e in self.events)
        except Exception:
            return 0.0

    def summary(self, phase_order: Optional[list[str]] = None) -> str:
        """Render a human-readable "Performance Summary" block.

        `phase_order` is an ordered list of phase names to report as
        top-line totals (e.g. ["assets", "whisper", "editorial",
        "rendering", "mux"]) — any event name not in this list is omitted
        from the top-line section but still counted toward the grand total.
        Never raises; returns a best-effort string even if some events are
        malformed.
        """
        try:
            lines = ["Performance Summary"]
            phases = phase_order or []
            grand_total = 0.0
            for phase in phases:
                total = self.total_for(phase)
                grand_total += total
                count = self.count_for(phase)
                suffix = f" ({count} clip(s))" if phase == "scene_render" and count else ""
                lines.append(f"  {_label(phase)}: {_fmt_seconds(total)}{suffix}")
            # Anything recorded outside the known phase_order still counts
            # toward the grand total so "Total" is never an undercount.
            named = set(phases)
            for e in self.events:
                if e.name not in named:
                    grand_total += e.duration_s
            lines.append(f"  Total: {_fmt_seconds(grand_total)}")
            if self.cache_hits or self.cache_misses:
                lines.append(f"  Cache: {self.cache_hits} hits / {self.cache_misses} misses")
            return "\n".join(lines)
        except Exception:
            return "Performance Summary\n  (unavailable — instrumentation error)"


def _label(phase_name: str) -> str:
    return {
        "project_load": "Project load",
        "csv_parse": "CSV parsing",
        "asset_discovery": "Asset discovery",
        "asset_generation": "Assets",
        "media_probe": "Media metadata probing",
        "whisper": "Whisper",
        "editorial": "Editorial",
        "graphics_prep": "Graphics prep",
        "scene_render": "Rendering",
        "mux": "Mux",
    }.get(phase_name, phase_name.replace("_", " ").capitalize())


def _fmt_seconds(value: float) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if value < 60:
        return f"{value:.2f}s"
    minutes, seconds = divmod(value, 60)
    return f"{int(minutes)}m {seconds:.1f}s"
