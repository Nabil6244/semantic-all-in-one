"""Lay rendered gfx-core sequences over a finished video, in one ffmpeg pass, without touching video_generator.py.

    composite(video, placed, out, width, height, fps, log=print) -> bool

`placed` = [(start_seconds, Result)] (normal_gfx.runner.Result: a folder of 00001.png ...). The sequences are strung into ONE transparent layer
(ffmpeg concat list: a transparent frame for every gap, each rendered frame for 1/fps) so a long video with many graphics still has one extra input.
Order matches the render: video_generator draws captions first and graphics above them, so the graphics go over the finished picture, captions included.
The audio stream is copied untouched. Video is re-encoded with the app's own documentary encoder settings (providers.ffmpeg_runner.encode_argv);
size and frame rate are those of the input. On any failure the original file is left exactly as it was and False is returned.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Sequence, Tuple

from .runner import Result


def _ffmpeg() -> str:
    from map_scene.render import _ffmpeg

    return _ffmpeg()


def build_layer_list(placed: Sequence[Tuple[float, Result]], total: float, fps: int, blank: Path, out_list: Path) -> int:
    """Write the concat list; returns the number of frames in the layer. Overlapping entries: the later one is dropped."""
    lines = ["ffconcat version 1.0"]
    frame = 1.0 / fps
    cursor = 0          # frames written so far
    n_total = int(round(total * fps))
    for start, res in sorted(placed, key=lambda p: p[0]):
        first = int(round(start * fps))
        if first < cursor or first >= n_total or not res.ok:
            continue
        gap = first - cursor
        if gap > 0:
            lines += [f"file '{blank.as_posix()}'", f"duration {gap * frame:.6f}"]
            cursor += gap
        count = min(res.frames, n_total - cursor)
        for i in range(count):
            lines += [f"file '{res.frame(i).as_posix()}'", f"duration {frame:.6f}"]
        cursor += count
    if cursor == 0:
        return 0
    lines += [f"file '{blank.as_posix()}'"]      # concat needs the last file repeated (its duration is ignored)
    out_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cursor


def composite(video: "str | Path", placed: Sequence[Tuple[float, Result]], out: "str | Path", width: int, height: int, fps: int, total: float,
              log: Callable[[str], None] = print) -> bool:
    video, out = Path(video), Path(out)
    placed = [(s, r) for s, r in placed if r.ok]
    if not placed or not video.is_file():
        return False
    try:
        from PIL import Image
        from providers import hidden_subprocess as hs

        try:
            from providers.ffmpeg_runner import encode_argv

            enc = list(encode_argv(quality="documentary"))
        except Exception:
            enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        with tempfile.TemporaryDirectory(prefix="gfxlayer_") as tmp:
            tmp = Path(tmp)
            blank = tmp / "blank.png"
            Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(blank)
            lst = tmp / "layer.ffconcat"
            frames = build_layer_list(placed, total, fps, blank, lst)
            if not frames:
                return False
            tmp_out = out.with_name(out.stem + ".gfx_tmp" + out.suffix)
            cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(video), "-f", "concat", "-safe", "0", "-i", str(lst),
                   "-filter_complex", f"[1:v]fps={fps},format=rgba[g];[0:v][g]overlay=format=auto:eof_action=pass:repeatlast=0,format=yuv420p[v]",
                   "-map", "[v]", "-map", "0:a?", *enc, "-c:a", "copy", "-movflags", "+faststart", str(tmp_out)]
            r = hs.run(cmd, capture_output=True, text=True)
            if r.returncode != 0 or not tmp_out.is_file() or tmp_out.stat().st_size < 1024:
                log(f"[GFX] composite failed, the video is left without the template graphics: {(r.stderr or '')[-300:].strip()}")
                tmp_out.unlink(missing_ok=True)
                return False
            os.replace(tmp_out, out)
        return True
    except Exception as exc:
        log(f"[GFX] composite failed, the video is left without the template graphics: {exc}")
        return False
