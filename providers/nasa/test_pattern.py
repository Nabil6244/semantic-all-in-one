"""Detect a broadcast test card (SMPTE colour bars, a slate) in a cut clip: archive reels start with one, and a segment cut near the
start of "Apollo 11 B roll" showed "KSCTV HD" bars over a Voyager launch."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List

W, H = 64, 36


def _frames(path: Path, count: int = 3) -> List["object"]:
    import numpy as np

    out = []
    for i in range(count):
        try:
            raw = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{0.5 + i * 1.7:.2f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={W}:{H}",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, timeout=30).stdout
        except Exception:
            continue
        if len(raw) == W * H * 3:
            out.append(np.frombuffer(raw, dtype=np.uint8).reshape(H, W, 3).astype(float))
    return out


def frame_is_color_bars(rgb) -> bool:
    """The top two thirds are 5+ flat vertical bands of clearly different colour: columns barely change down the frame, the row changes a lot."""
    import numpy as np

    top = rgb[: int(H * 0.6)]
    if float(top.std(axis=0).mean()) > 14:                 # columns are not flat down the frame
        return False
    row = top.mean(axis=0)                                  # W x 3
    jumps = np.abs(np.diff(row, axis=0)).sum(axis=1) > 90   # a band edge
    return int(jumps.sum()) >= 4


def is_test_pattern(path: Path) -> bool:
    try:
        frames = _frames(Path(path))
    except Exception:
        return False
    return bool(frames) and sum(frame_is_color_bars(f) for f in frames) * 2 >= len(frames)
