"""Boards baked onto their pictures before the render (the owner's idea, 2026-11-04).

A board over a Flow picture used to be two things: the picture as a full-screen still in the map render, and the board as a see-through clip laid over the
finished video in a second pass over the whole video (explainer.integration.post_render). Here, just before the render, each such picture is turned into one
ordinary clip that already carries its board: the picture with the engine's own slow push-in (cover crop, 1 -> 1 + KENBURNS_ZOOM around the centre, even over
the picture's time on screen, as pakmap-engine/lib/hybrid.mjs kenBurnsScale), the board laid on frame for frame. The render then shows that clip instead of the
still (its fast path copies video frames without the browser), and the second pass has no board left to lay on.

`bake_spec(spec, work, log)` changes the spec in place and returns how many pictures were baked; anything that cannot be baked keeps the old way. Never raises."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

KENBURNS_ZOOM = 0.06           # pakmap-engine kenBurnsScale default (kenburns_zoom ?? 0.06)
FPS = 30
W, H = 1920, 1080
BAKED_LIST = "baked_boards.json"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _report(work: Any) -> Optional[Path]:
    return next((p for p in (Path(work) / "explainer" / "render_report.json", Path(work).parent / "explainer" / "render_report.json") if p.is_file()), None)


def _cover(iw: int, ih: int) -> Tuple[float, float, float, float]:
    """The engine's coverCrop: the largest source rectangle with the frame's shape, centred."""
    if iw / ih > W / H:
        sh = ih
        sw = ih * W / H
    else:
        sw = iw
        sh = iw * H / W
    return (iw - sw) / 2.0, (ih - sh) / 2.0, sw, sh


def _frames(picture: str, n: int, fps: float):
    """The picture as the engine draws it, frame by frame: cover crop, then the push-in around the frame centre. Each frame is one bilinear resize of a
    sub-pixel crop box (the browser scales pictures bilinearly too): smooth, with no stair-step jitter, ~29 ms a frame on an M2 (an affine transform took 200)."""
    from PIL import Image
    with Image.open(picture) as im:
        src = im.convert("RGB")
    sx, sy, sw, sh = _cover(*src.size)
    span = max(1e-6, n / fps)
    for i in range(n):
        k = 1.0 + KENBURNS_ZOOM * max(0.0, min(1.0, (i / fps) / span))
        w, h = sw / k, sh / k
        box = (sx + (sw - w) / 2.0, sy + (sh - h) / 2.0, sx + (sw + w) / 2.0, sy + (sh + h) / 2.0)
        yield src.resize((W, H), Image.BILINEAR, box=box).tobytes()


def bake_one(picture: str, mov: Optional[str], n: int, out: Path, fps: float = FPS) -> bool:
    """One clip: `n` frames of the picture with its push-in and the board `mov` laid on from frame 0 (no board: the picture alone).
    Drawn under a temporary name, renamed when complete."""
    from . import hwenc as HW
    part = out.with_name(out.stem + ".part" + out.suffix)
    if mov:
        layers = ["-i", str(mov), "-filter_complex", f"[0:v]format=yuv420p[b];[1:v]scale={W}:{H},format=yuva420p[o];[b][o]overlay=0:0:eof_action=pass[v]", "-map", "[v]"]
    else:
        layers = []
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps:g}", "-i", "-", *layers, "-frames:v", str(n), "-an",
           *HW.h264_args(["-c:v", "libx264", "-crf", "14", "-preset", "veryfast"]), "-pix_fmt", "yuv420p", "-r", f"{fps:g}", "-movflags", "+faststart", str(part)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for fr in _frames(picture, n, fps):
            p.stdin.write(fr)
        p.stdin.close()
        rc = p.wait(timeout=1800)
    except BaseException:
        p.kill()
        p.wait(timeout=30)
        part.unlink(missing_ok=True)
        return False
    if rc == 0 and part.is_file():
        os.replace(part, out)
        return True
    part.unlink(missing_ok=True)
    return False


def _key(picture: str, mov: Optional[str], n: int) -> str:
    st_p = os.stat(picture)
    st_m = os.stat(mov) if mov else None
    raw = json.dumps([str(picture), st_p.st_size, int(st_p.st_mtime), str(mov or ""), st_m.st_size if st_m else 0, int(st_m.st_mtime) if st_m else 0, n, KENBURNS_ZOOM, W, H],
                     sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def plan_bakes(spec: Dict[str, Any], work: Any) -> List[Dict[str, Any]]:
    """[{event, picture, mov, n, out}] for each full-screen picture an Explainer board is laid over (its board starts with the picture)."""
    rr = _report(work)
    if rr is None:
        return []
    details = json.loads(rr.read_text(encoding="utf-8"))["report"].get("beat_details") or {}
    boards = [(float(i["board_overlay"]["start"]), str(i["board_overlay"]["mov"])) for i in details.values() if (i or {}).get("board_overlay")]
    pics = [e for e in spec.get("events") or [] if e.get("type") == "media_full" and str(e.get("media", "")).lower().endswith(IMAGE_EXT)]
    out: List[Dict[str, Any]] = []
    for start, mov in boards:
        ev = next((e for e in pics if abs(float(e.get("t_in", -99)) - start) < 0.05), None)
        if ev is None or not Path(mov).is_file() or not Path(str(ev["media"])).is_file():
            continue
        n = max(1, round((float(ev["t_out"]) - float(ev["t_in"])) * FPS))
        out.append({"event": ev, "picture": str(ev["media"]), "mov": mov, "n": n, "out": rr.parent / f"baked_{_key(str(ev['media']), mov, n)}.mp4"})
    return out


def bake_spec(spec: Dict[str, Any], work: Any, log: Callable[[str], None] = lambda m: None) -> int:
    try:
        jobs = plan_bakes(spec, work)
    except Exception as exc:
        log(f"[Explainer] boards are laid on after the render as before ({str(exc)[:100]})")
        return 0
    if not jobs:
        _write_list(work, {})                       # a list from an earlier render never hides a board this render did not bake
        return 0
    from . import hwenc as HW
    from .board.jobs import clip_ok
    todo = [j for j in jobs if not clip_ok(j["out"])]
    workers = max(1, min(6, (os.cpu_count() or 4) - 1)) if HW.h264_ok() else max(1, min(8, (os.cpu_count() or 4) - 1))
    if todo:
        log(f"[Explainer] baking {len(todo)} board(s) onto their pictures on {workers} core(s)…")
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(lambda j: bake_one(j["picture"], j["mov"], j["n"], j["out"]), todo))
    baked: Dict[str, str] = {}
    for j in jobs:
        if clip_ok(j["out"]):
            j["event"]["media"] = str(j["out"])
            j["event"]["kenburns"] = False          # the push-in is in the clip
            baked[j["mov"]] = str(j["out"])
    left = len(jobs) - len(baked)
    _write_list(work, baked)
    log(f"[Explainer] {len(baked)} board(s) baked onto their pictures" + (f"; {left} laid on after the render as before" if left else ""))
    return len(baked)


def plan_stills(spec: Dict[str, Any], work: Any) -> List[Dict[str, Any]]:
    """[{event, picture, n, out}] for each full-screen picture still drawn by the map page with the default push-in (no board on it)."""
    rr = _report(work)
    if rr is None:
        return []
    out: List[Dict[str, Any]] = []
    for e in spec.get("events") or []:
        pic = str(e.get("media", ""))
        if e.get("type") != "media_full" or not pic.lower().endswith(IMAGE_EXT) or e.get("kenburns") not in (True, "auto"):
            continue
        if e.get("kenburns_zoom") not in (None, KENBURNS_ZOOM) or not Path(pic).is_file():
            continue                                    # a push-in this file does not reproduce: the page draws it as before
        n = max(1, round((float(e["t_out"]) - float(e["t_in"])) * FPS))
        out.append({"event": e, "picture": pic, "n": n, "out": rr.parent / f"still_{_key(pic, None, n)}.mp4"})
    return out


def bake_stills(spec: Dict[str, Any], work: Any, log: Callable[[str], None] = lambda m: None) -> int:
    """Each full-screen picture still becomes a clip with the engine's push-in in it (cached by key), so the map page never draws a picture: the render's fast path
    copies the clip frames and the browser draws only where the map shows. Changes the spec in place; returns how many. Never raises."""
    try:
        jobs = plan_stills(spec, work)
        if not jobs:
            return 0
        from . import hwenc as HW
        from .board.jobs import clip_ok
        todo = [j for j in jobs if not clip_ok(j["out"])]
        workers = max(1, min(6, (os.cpu_count() or 4) - 1)) if HW.h264_ok() else max(1, min(8, (os.cpu_count() or 4) - 1))
        if todo:
            log(f"[Explainer] turning {len(todo)} picture(s) into clips so the map is drawn only where it shows…")
            with ThreadPoolExecutor(workers) as ex:
                list(ex.map(lambda j: bake_one(j["picture"], None, j["n"], j["out"]), todo))
        done = 0
        for j in jobs:
            if clip_ok(j["out"]):
                j["event"]["media"] = str(j["out"])
                j["event"]["kenburns"] = False          # the push-in is in the clip
                done += 1
        if done < len(jobs):
            log(f"[Explainer] {len(jobs) - done} picture(s) are drawn by the map page as before")
        return done
    except Exception as exc:
        log(f"[Explainer] pictures are drawn by the map page as before ({str(exc)[:100]})")
        return 0


INTERMEDIATE_X264 = {"x264_preset": "ultrafast", "crf": 15}   # the map render's own file is encoded again later (post_render, final export): cheap to write


def fast_intermediate(spec: Dict[str, Any]) -> None:
    """The map render writes its in-between file quickly: x264 'faster' was what kept the cores busy (about 50 frames a second at 1080p, picture frames included)."""
    for k, v in INTERMEDIATE_X264.items():
        spec.setdefault(k, v)


def _write_list(work: Any, baked: Dict[str, str]) -> None:
    try:
        rr = _report(work)
        if rr is not None:
            (rr.parent / BAKED_LIST).write_text(json.dumps(baked), encoding="utf-8")
    except Exception:
        pass


def baked_movs(folder: Any) -> Dict[str, str]:
    """The boards already baked into their pictures (post_render leaves them out)."""
    try:
        return json.loads((Path(folder) / BAKED_LIST).read_text(encoding="utf-8"))
    except Exception:
        return {}
