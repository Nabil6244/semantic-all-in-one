"""Short real cross-dissolve clips between two shots (only where continuity.py asked for one: time / lighting moves on, near-identical pictures).

    make_link(a_clip, a_from_frame, b_clip, frames, fps, size, out, cancel=None) -> path   frames of A (from a_from_frame on) eased into frames of B (from 0)
    link_name(shot_id, frames) / link_frames(path)                                          '<id>+link_<k>f.mp4' <-> k
    build_links(pairs, clips, out_dir, fps, size, state, log, cancel, workers) -> {"<id>+link": path}

The link REPLACES the first k frames of the next shot in the timeline (runner.assemble_timeline), so the film length never changes and the cut still
lands on the sentence boundary: the picture of A simply dissolves into B over its first 0.27 s instead of dipping through black.
A's clip has 0.3 s of margin past its shot end, so the frames after the cut exist. Cached (content key in the state file), atomic, cancel-safe;
any failure just leaves no link (the timeline then keeps the plain cut)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional

CODE_VERSION = "sf-bridge-2"
_FRAMES = re.compile(r"_(\d+)f\.mp4$")


class BridgeCancelled(Exception):
    pass


def link_name(shot_id: str, frames: int) -> str:
    return f"{shot_id}+link_{int(frames)}f.mp4"


def link_frames(path: str) -> int:
    m = _FRAMES.search(str(path))
    return int(m.group(1)) if m else 0


def _ffmpeg() -> str:
    try:
        from health_cinema.puppet import motion
        return motion._ffmpeg()
    except Exception:       # noqa: BLE001
        return shutil.which("ffmpeg") or "ffmpeg"


def _ok(p) -> bool:
    try:
        return bool(p) and os.path.isfile(p) and os.path.getsize(p) > 1000
    except OSError:
        return False


def _sig(p: str) -> str:
    try:
        st = os.stat(p)
        return f"{os.path.basename(p)}:{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return "?"


def link_key(a_clip, a_from, b_clip, frames, fps, size) -> str:
    return hashlib.sha1(json.dumps([_sig(a_clip), int(a_from), _sig(b_clip), int(frames), int(fps), list(size), CODE_VERSION]).encode()).hexdigest()[:24]


def make_link(a_clip: str, a_from_frame: int, b_clip: str, frames: int, fps: int, size, out: str, cancel: Optional[Callable] = None) -> str:
    """Smoothstep cross-dissolve of `frames` frames: A from frame a_from_frame, B from its first frame. Raises on any ffmpeg trouble."""
    if cancel and cancel():
        raise BridgeCancelled("cancelled")
    w, h = int(size[0]), int(size[1])
    k = int(frames)
    t_a = max(0.0, a_from_frame / float(fps))
    dur = (k + 2) / float(fps)
    part = str(out) + f".{os.getpid()}.part.mp4"
    # the blend weight is a smoothstep of the frame's position inside the link: never a frame of pure A or pure B at the ends
    p = f"((N+0.5)/{k})"
    s = f"({p}*{p}*(3-2*{p}))"
    fc = (f"[0:v]fps={fps},scale={w}:{h},format=yuv420p,setpts=PTS-STARTPTS,trim=end_frame={k}[a];"
          f"[1:v]fps={fps},scale={w}:{h},format=yuv420p,setpts=PTS-STARTPTS,trim=end_frame={k}[b];"
          f"[a][b]blend=all_expr='A*(1-{s})+B*{s}',format=yuv420p[v]")
    cmd = [_ffmpeg(), "-v", "error", "-y", "-nostdin", "-ss", f"{t_a:.5f}", "-t", f"{dur:.4f}", "-i", str(a_clip), "-t", f"{dur:.4f}", "-i", str(b_clip),
           "-filter_complex", fc, "-map", "[v]", "-frames:v", str(k), "-r", str(fps), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", part]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if cancel and cancel():
            raise BridgeCancelled("cancelled")
        if r.returncode != 0 or not _ok(part):
            raise RuntimeError("ffmpeg link failed: " + r.stderr.decode("utf-8", "replace")[-300:])
        os.replace(part, out)
    finally:
        try:
            if os.path.exists(part):
                os.unlink(part)
        except OSError:
            pass
    return str(out)


def build_links(pairs: Dict[str, dict], clips: Dict[str, str], out_dir: str, fps: int, size, a_frames: Dict[str, int], state: Optional[dict] = None,
                save_state: Optional[Callable] = None, log: Optional[Callable] = None, cancel: Optional[Callable] = None, workers: int = 2) -> Dict[str, str]:
    """pairs {A id: {"to": B id, "frames": k}}; clips {shot id: mp4}; a_frames {A id: its length in frames on the timeline (= where its margin starts)}.
    Returns {"<A id>+link": path} for every pair that could be made. Never raises except BridgeCancelled."""
    log = log or (lambda *a, **k: None)
    state = state if state is not None else {}
    out: Dict[str, str] = {}
    todo = []
    for a, pr in pairs.items():
        b, k = pr["to"], int(pr["frames"])
        ca, cb = clips.get(a), clips.get(b)
        if not (_ok(ca) and _ok(cb)) or a not in a_frames:
            continue
        todo.append((a, b, k, ca, cb))
    if not todo:
        return out

    def one(item):
        a, b, k, ca, cb = item
        if cancel and cancel():
            raise BridgeCancelled("cancelled")
        path = os.path.join(out_dir, link_name(a, k))
        key = link_key(ca, a_frames[a], cb, k, fps, size)
        rec = state.get(a + "+link") or {}
        if rec.get("key") == key and _ok(path):
            return a, path
        try:
            make_link(ca, a_frames[a], cb, k, fps, size, path, cancel=cancel)
            state[a + "+link"] = {"key": key, "status": "done", "path": path}
            if save_state:
                save_state()
            return a, path
        except BridgeCancelled:
            raise
        except Exception as e:      # noqa: BLE001
            log(f"{a}+link: no dissolve clip ({type(e).__name__}: {e}); plain cut kept")
            return a, None

    if workers <= 1 or len(todo) == 1:
        results = [one(t) for t in todo]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            results = list(ex.map(one, todo))
    for a, p in results:
        if p:
            out[a + "+link"] = p
    return out
