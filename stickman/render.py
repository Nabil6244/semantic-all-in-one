"""Render a stickman plan to mp4, drawing frames on all cores.

python3 -m stickman.render PLAN.json OUT.mp4 [--preview] [--workers N]
--preview renders 1280x720 for a fast look.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import multiprocessing as mp
from pathlib import Path

from . import draw, looks, timeline

_G = {}


def _init(spec):
    _G["spec"] = spec
    _G["look"] = looks.get(spec.get("look", "ink_paper"))


def _frame(fr):
    return draw.frame(fr, _G["spec"], _G["look"])


def load(path, preview=False):
    spec = json.loads(Path(path).read_text())
    spec.setdefault("size", [1920, 1080])
    if preview:
        spec["size"] = [1280, 720]
    return spec


class Stopped(RuntimeError):
    pass


def render(spec, out, workers=None, log=print, progress=None, cancel=None):
    """progress(frac, msg) is called now and then; cancel() returning True stops the render (raises Stopped)."""
    t0 = time.time()
    frames = timeline.simulate(spec)
    W, H = spec["size"]
    fps = int(spec.get("fps", 30))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = workers or max(1, (os.cpu_count() or 2) - 1)
    stopped = False
    pool = None
    try:
        try:   # spawn: the same worker start the packaged app uses for Rep Theory; one core if workers can't start
            pool = mp.get_context("spawn").Pool(n, initializer=_init, initargs=(spec,)) if n > 1 else None
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"stickman: drawing on one core ({type(e).__name__}: {e})")
        if pool is None:
            _init(spec)
            frames_out = map(_frame, frames)
        else:
            frames_out = pool.imap(_frame, frames, chunksize=4)
        for i, buf in enumerate(frames_out):
            if cancel is not None and cancel():
                stopped = True
                break
            proc.stdin.write(buf)
            if (i + 1) % fps == 0:
                if progress:
                    progress((i + 1) / len(frames), f"drawing {i + 1}/{len(frames)} frames")
                if log and (i + 1) % (fps * 5) == 0:
                    log(f"  {i + 1}/{len(frames)} frames")
    finally:
        if pool is not None:
            pool.terminate() if stopped else pool.close()
            pool.join()
        proc.stdin.close()
        if stopped:
            proc.kill()
        rc = proc.wait()
    if stopped:
        out.unlink(missing_ok=True)
        raise Stopped("Stopped.")
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}) writing {out}")
    if log:
        log(f"stickman: {len(frames)} frames -> {out} in {time.time() - t0:.1f} s")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan")
    ap.add_argument("out")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--workers", type=int)
    a = ap.parse_args(argv)
    try:
        render(load(a.plan, a.preview), a.out, a.workers)
    except timeline.TimelineError as e:
        print(f"plan problem: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
