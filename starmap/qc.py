"""Render QC: after a StarMap video is drawn, find stretches where the picture is frozen and footage that is almost black.
A REPORT only -- it never changes the camera or the video (some quiet shots are meant to be still); it catches dead frames
before a video ships."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FROZEN_S = 1.5            # a stretch with no visible change for longer than this is reported
DARK = 0.01               # footage whose mean brightness is under 1% is reported


@dataclass
class Finding:
    beat: str
    start: float
    end: float
    reason: str

    def text(self) -> str:
        return f"QC beat {self.beat}: {self.start:.1f}-{self.end:.1f} s ({self.end - self.start:.1f} s) {self.reason}"


def _ffmpeg() -> str:
    from map_scene.render import _ffmpeg as find

    return find()


def frozen_stretches(video: Path, *, min_s: float = FROZEN_S, noise: float = 0.0005) -> List[tuple]:
    """(start, end) of every stretch longer than min_s where no frame differs visibly from the last (ffmpeg freezedetect)."""
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(video), "-map", "0:v", "-vf", f"freezedetect=n={noise}:d={min_s}",
                          "-f", "null", "-"], capture_output=True, text=True, check=False).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", out)]
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    total = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else None
    return [(a, ends[i] if i < len(ends) else (total if total is not None else a + min_s)) for i, a in enumerate(starts)]


def brightness(video: Path, at: float) -> Optional[float]:
    """Mean brightness (0-1) of the frame at `at` seconds, or None if it cannot be read."""
    from io import BytesIO

    from PIL import Image, ImageStat

    r = subprocess.run([_ffmpeg(), "-loglevel", "error", "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=160:-2",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=False)
    if not r.stdout:
        return None
    return ImageStat.Stat(Image.open(BytesIO(r.stdout)).convert("L")).mean[0] / 255.0


def _beat_at(beats: Sequence[Any], t: float) -> str:
    for b in beats:
        if b.start - 1e-6 <= t < b.end:
            return b.id
    return beats[-1].id if beats else "?"


def check_render(video: Path, spec: Dict[str, Any], beats: Sequence[Any]) -> List[Finding]:
    """Frozen stretches (with the beat they fall in) and footage under 1% brightness, in time order."""
    found = [Finding(_beat_at(beats, a), a, b, "frozen: no visible change on screen") for a, b in frozen_stretches(Path(video))]
    for f in spec.get("footage", []):
        a, b = float(f.get("start", 0)), float(f.get("end", 0))
        if b - a < 0.5:
            continue
        lum = [x for x in (brightness(Path(video), a + (b - a) * k) for k in (0.25, 0.5, 0.75)) if x is not None]
        if lum and max(lum) < DARK:
            found.append(Finding(_beat_at(beats, a), a, b, f"very dark footage ({100 * max(lum):.1f}% brightness): check the clip"))
    return sorted(found, key=lambda x: x.start)
