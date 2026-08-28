"""Flow-specific QA heuristics."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List


def check_flow_temporal_quality(frame_paths: List[Path]) -> tuple[float, list[str]]:
    """Detect obvious frozen/duplicate frames in Flow output."""
    warnings: list[str] = []
    if len(frame_paths) < 2:
        return 0.85, warnings
    hashes = []
    for fp in frame_paths:
        p = Path(fp)
        if not p.is_file():
            continue
        hashes.append(hashlib.md5(p.read_bytes()).hexdigest())
    if len(hashes) >= 2 and len(set(hashes)) == 1:
        warnings.append("Flow: frozen or static frames detected")
        return 0.35, warnings
    if len(hashes) >= 3 and len(set(hashes)) <= 1:
        warnings.append("Flow: severe temporal artifact")
        return 0.25, warnings
    return 0.88, warnings
