"""Make a look pack's preview pictures from a video made in that look:

    python3 -m agent_kit.make_preview history_toon ~/Downloads/agent_videos/history_toon_test/final.mp4

Writes agent_kit/looks/<pack>/preview.jpg (8 frames, 4 x 2, 1920 wide: the full sheet) and thumb.png (256 x 144: 4 frames
2 x 2, the small picture on the AI Director page). Frames are spread over the video, skipping its first and last 6 %."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _dur(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _frames(video: Path, n: int, width: int, tmp: Path, tag: str, times: list | None = None) -> None:
    d = _dur(video)
    ts = times or [d * (0.06 + 0.88 * (i + 0.5) / n) for i in range(n)]
    for i, t in enumerate(ts):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", str(tmp / f"{tag}{i:02d}.png")], check=True)


def make(pack: str, video: str, times: str = "") -> tuple:
    v = Path(video).expanduser().resolve()
    dst = HERE / "looks" / pack
    if not dst.is_dir():
        raise SystemExit(f"no look pack: {dst}")
    ts = [float(x) for x in times.split(",")] if times else None
    tmp = Path(tempfile.mkdtemp())
    try:
        _frames(v, 8, 480, tmp, "f", ts if ts and len(ts) == 8 else None)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp / "f%02d.png"),
                        "-vf", "tile=4x2:padding=0", "-frames:v", "1", "-q:v", "3", str(dst / "preview.jpg")], check=True)
        _frames(v, 4, 128, tmp, "t", [ts[i] for i in (0, 2, 5, 7)] if ts and len(ts) == 8 else None)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(tmp / "t%02d.png"),
                        "-vf", "scale=128:72,tile=2x2:padding=0", "-frames:v", "1", str(dst / "thumb.png")], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dst / "preview.jpg", dst / "thumb.png"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    for p in make(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""):
        print(p)
