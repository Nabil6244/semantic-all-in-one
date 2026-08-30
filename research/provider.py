"""The adapter boundary: everything downstream (ResearchAssetProvider, the
Manual Research UI) depends only on this Protocol + ResearchResult — never
on how a concrete implementation talks to the research engine.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Protocol

from research.models import ResearchResult


class ResearchProvider(Protocol):
    def research(
        self,
        topic: str,
        script: Optional[str] = None,
        urls: Optional[List[str]] = None,
        domain: str = "auto",
        max_media_per_property: int = 20,
        output_dir: Optional[Path] = None,
    ) -> ResearchResult:
        """Must never raise. A failure (misconfigured path, subprocess error,
        malformed output) comes back as ResearchResult(ok=False, error=...),
        not an exception — callers treat that identically to "no research
        configured". `output_dir` is where results/media get stored — the
        caller passes the project's `research_dir` so results are reusable
        across sessions (see decision: project-based storage)."""
        ...
