"""The Mac's video engine for H.264 (Apple VideoToolbox), shared by every Explainer encode that is not the final export.

Measured on an M2: about 4.5x real time for 1080p whatever the number of jobs, SSIM 0.998 against the source (x264 crf 10 gives 0.9986), and almost no CPU,
so the cores stay free for drawing and the machine stays cool. Anywhere it cannot run (Windows, Linux, a build without it) the caller's software encoder is used.
EXPLAINER_NO_HW_ENCODE=1 turns it off."""

from __future__ import annotations

import os
import subprocess
from typing import Dict, List

H264 = ["-c:v", "h264_videotoolbox", "-b:v", "40M", "-profile:v", "high"]
WORKERS = 3                    # one engine: more jobs do not make it faster, a few keep it fed while the cores decode
_OK: Dict[str, bool] = {}


def h264_ok() -> bool:
    """True when ffmpeg can encode H.264 on the video engine here (tried once per process on a tiny clip)."""
    if "ok" not in _OK:
        if os.environ.get("EXPLAINER_NO_HW_ENCODE") == "1":
            _OK["ok"] = False
        else:
            try:
                r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x180:d=0.2", *H264, "-pix_fmt", "yuv420p", "-f", "null", "-"],
                                   capture_output=True, timeout=30)
                _OK["ok"] = r.returncode == 0
            except Exception:
                _OK["ok"] = False
    return _OK["ok"]


def h264_args(software: List[str]) -> List[str]:
    """The video engine's arguments when it is there, else `software` (the caller's x264 arguments)."""
    return list(H264) if h264_ok() else list(software)
