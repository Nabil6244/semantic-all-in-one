"""The finishing pass: News Doc's graphics laid over the rendered footage-and-map video, each at its own time.

    composite(base, clips, output) -> (ok, notes)      clips: [(path of a transparent .mov, start seconds)]

One ffmpeg pass (the narration and sound are copied as they are); if a large pass fails it is done in smaller batches; if that
fails too, the video without the graphics is kept and the reason noted — the render never ends without a video."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Sequence, Tuple

BATCH = 14


def _ffmpeg() -> str:
    try:
        from map_scene.render import _ffmpeg as find

        return find()
    except Exception:
        return "ffmpeg"


def _pass(base: Path, clips: Sequence[Tuple[Path, float]], out: Path) -> Tuple[bool, str]:
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", str(base)]
    for path, _t in clips:
        cmd += (["-loop", "1", "-i", str(path)] if str(path).endswith(".png") else ["-i", str(path)])
    parts, last = [], "0:v"
    for k, (path, t) in enumerate(clips, start=1):
        nxt = f"v{k}"
        if str(path).endswith(".png"):   # a still for the whole video (the channel name): looped, ends with the video
            parts.append(f"[{k}:v]format=rgba[o{k}]")
            parts.append(f"[{last}][o{k}]overlay=0:0:shortest=1:format=auto[{nxt}]")
        else:
            parts.append(f"[{k}:v]setpts=PTS-STARTPTS+{t:.3f}/TB,format=rgba[o{k}]")
            parts.append(f"[{last}][o{k}]overlay=0:0:eof_action=pass:repeatlast=0:format=auto[{nxt}]")
        last = nxt
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", "0:a?", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600)
    except Exception as exc:
        return False, str(exc)
    return (r.returncode == 0 and out.is_file() and out.stat().st_size > 1000), r.stderr[-400:]


def composite(base: "str | Path", clips: Sequence[Tuple[Path, float]], output: "str | Path") -> Tuple[bool, List[str]]:
    base, output = Path(base), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    clips = sorted([(Path(p), float(t)) for p, t in clips if p and Path(p).is_file()], key=lambda c: c[1])
    if not clips:
        shutil.copyfile(base, output)
        return True, ["News Doc: no graphics to add"]
    tmp = output.with_name(f".{output.stem}.nd{output.suffix}")
    ok, err = _pass(base, clips, tmp)
    if not ok:   # smaller batches, one after the other
        cur = base
        ok = True
        for k in range(0, len(clips), BATCH):
            step = output.with_name(f".{output.stem}.nd{k}{output.suffix}")
            good, err = _pass(cur, clips[k:k + BATCH], step)
            if cur != base:
                cur.unlink(missing_ok=True)
            if not good:
                ok = False
                break
            cur = step
        if ok:
            cur.replace(tmp)
    if ok:
        tmp.replace(output)
        return True, [f"News Doc: {len(clips)} graphic(s) added"]
    tmp.unlink(missing_ok=True)
    shutil.copyfile(base, output)
    return False, [f"News Doc: the graphics could not be added ({err.strip()[:200]}); the video is kept without them"]
