"""War Footage Director, Stage 7: capture the chosen moment and prove the file shows it.

docs/war/FOOTAGE_DIRECTOR_PLAN.md. The shared capture pool is CALLED, never changed:
providers.youtube.acquisition.browser_client.get_client().acquire(video_id, start, seconds, dest) (at most 8 s, seek within about 1.25 s, no
actual start reported), then providers.youtube.strategies.validate_clip (a real video of the right length). War's own checks follow:

  moment     frames of the captured file are matched against the storyboard tiles around the requested second (dHash); most frames must
             match. A miss means an ad, a wrong seek or another video was recorded: the capture is thrown away.
  picture    the captured frames are classified like storyboard tiles: a pillarboxed phone video, a text screen or black frames fail.

write_record() stores the clip in the scene's manifest record with its provenance (channel, URL, id, upload date, cut second, authenticity),
so the Visuals tab shows it and Render uses it like any fetched clip.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from . import director_frames as F

MATCH_DIST = 14            # dHash distance at which a captured frame shows a storyboard tile
MATCH_SHARE = 0.5          # share of captured frames that must match a tile around the requested second
SEARCH_PAD_S = 6.0         # storyboard tiles this far either side of the window are allowed to match (seek slack, tile spacing)


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def frames_of(path: str, fps: float = 2.0, w: int = 160, h: int = 90) -> List[np.ndarray]:
    r = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-"],
                       capture_output=True)
    raw = r.stdout
    n = len(raw) // (w * h * 3)
    return [np.frombuffer(raw[i * w * h * 3:(i + 1) * w * h * 3], np.uint8).reshape(h, w, 3) for i in range(n)]


def verify(frames: Sequence[np.ndarray], tiles: Sequence[F.Tile], start: float, seconds: float) -> Dict[str, Any]:
    """{ok, matched, offset, kinds, reasons}: do the captured frames show the storyboard tiles of [start, start+seconds]?"""
    near = [t for t in tiles if start - SEARCH_PAD_S <= t.t <= start + seconds + SEARCH_PAD_S]
    reasons: List[str] = []
    if not frames:
        return {"ok": False, "matched": 0.0, "offset": None, "kinds": {}, "reasons": ["no frames in the captured file"]}
    hits, offs = 0, []
    for i, f in enumerate(frames):
        h = F.dhash(f)
        best = min(near, key=lambda t: F._hd(t.hash or F.dhash(t.img), h), default=None)
        if best is not None and F._hd(best.hash or F.dhash(best.img), h) <= MATCH_DIST:
            hits += 1
            offs.append(best.t - (start + i * 0.5))
    share = hits / len(frames)
    kinds: Dict[str, int] = {}
    prev = None
    for f in frames:
        k, _d, _fl = F.classify(f, prev)
        kinds[k] = kinds.get(k, 0) + 1
        prev = f
    bad = {k: v for k, v in kinds.items() if k in F.BAD}
    colour = None
    if near and share < MATCH_SHARE and _fast(frames):
        # a moving camera / timelapse changes every frame, so no fingerprint ever matches a tile 1-2 s away (Moskva 045: the stamp-queue
        # timelapse, the right picture, matched 0%). Colour decides there: the chosen stretch's palette, not another video's (an ad)
        colour = _colour_match(frames, near, [t for t in tiles if t not in near])
        if colour["near"] >= COLOUR_MIN and colour["near"] >= colour["far"] - 0.02:
            share = max(share, MATCH_SHARE)
    if near and share < MATCH_SHARE:
        reasons.append(f"moment: only {share:.0%} of the captured frames show the chosen stretch (an ad or a wrong seek)")
    if sum(bad.values()) > len(frames) * 0.3:
        reasons.append(f"picture: {', '.join(f'{k} {v}' for k, v in bad.items())} of {len(frames)} frames")
    offset = round(float(np.median(offs)), 2) if offs else None
    return {"ok": not reasons, "matched": round(share, 3), "offset": offset, "kinds": kinds, "reasons": reasons,
            "checked_against_storyboard": bool(near), **({"colour": colour} if colour else {})}


FAST_CHANGE = 25.0          # median mean-abs change (0-255) between frames 0.5 s apart above which the picture is a moving camera
COLOUR_MIN = 0.7            # palette overlap with the chosen stretch: the right moment ~0.82, another video ~0.33-0.52 (measured, Moskva 045)


def _fast(frames: Sequence[np.ndarray]) -> bool:
    ch = [float(np.abs(frames[i].astype(np.float32) - frames[i - 1].astype(np.float32)).mean()) for i in range(1, len(frames))
          if frames[i].shape == frames[i - 1].shape]
    return bool(ch) and float(np.median(ch)) > FAST_CHANGE


def _palette(img: np.ndarray) -> np.ndarray:
    q = (np.asarray(img)[::2, ::2] >> 5).astype(np.int32)
    h = np.bincount(((q[..., 0] << 6) | (q[..., 1] << 3) | q[..., 2]).ravel(), minlength=512).astype(np.float32)
    return h / max(h.sum(), 1.0)


def _colour_match(frames: Sequence[np.ndarray], near: Sequence[F.Tile], far: Sequence[F.Tile]) -> Dict[str, float]:
    """Median best palette overlap of the captured frames with the chosen stretch's tiles and with the rest of the video."""
    pn = [_palette(t.img) for t in near]
    pf = [_palette(t.img) for t in far[::max(1, len(far) // 40)]]
    fs = [_palette(f) for f in frames]
    best = lambda ps: float(np.median([max(float(np.minimum(f, p).sum()) for p in ps) for f in fs])) if ps else 0.0  # noqa: E731
    return {"near": round(best(pn), 3), "far": round(best(pf), 3)}


def longest_uncut(frames: Sequence[np.ndarray], fps: float = 2.0) -> tuple:
    """(start s, end s) of the longest stretch without a hard cut in a captured clip's frames."""
    if not frames:
        return 0.0, 0.0
    cuts = [0]
    for i in range(1, len(frames)):
        a, b = F._same_size(frames[i].astype(np.float32), frames[i - 1].astype(np.float32))
        if F._hd(F.dhash(frames[i]), F.dhash(frames[i - 1])) > F.CUT_HASH and float(np.abs(a - b).mean()) > F.CUT_DIFF:
            cuts.append(i)
    cuts.append(len(frames))
    best = max(zip(cuts[:-1], cuts[1:]), key=lambda ab: ab[1] - ab[0])
    return best[0] / fps, best[1] / fps


def _trim(src: Path, dst: Path, a: float, b: float) -> bool:
    r = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{a:.2f}", "-i", str(src), "-t", f"{b - a:.2f}", "-c:v", "libx264", "-crf", "16",
                        "-preset", "fast", "-c:a", "aac", "-movflags", "+faststart", str(dst)], capture_output=True)
    return r.returncode == 0 and dst.is_file()


def capture(video_id: str, start: float, seconds: float, dest: Path, tiles: Sequence[F.Tile],
            acquire: Optional[Callable[..., Dict[str, Any]]] = None, validate: Optional[Callable[[Path, float], Optional[str]]] = None,
            log: Callable[[str], None] = lambda m: None, storyboard: bool = True) -> Dict[str, Any]:
    """Capture [start, start+seconds] of the video into dest and verify it. {ok, path, reasons, verify, seconds}."""
    seconds = max(F.MIN_S, min(8.0, float(seconds)))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".director.mp4")
    if acquire is None:
        from providers.youtube.acquisition.browser_client import get_client
        acquire = get_client().acquire
    if validate is None:
        from providers.youtube.strategies import validate_clip
        validate = lambda p, d: validate_clip(p, d, log)  # noqa: E731
    t0 = time.time()
    try:
        res = acquire(video_id, float(start), seconds, tmp) or {}
    except Exception as exc:  # noqa: BLE001 - a failed capture moves on to the next candidate
        res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if not res.get("ok") or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return {"ok": False, "path": "", "reasons": [f"capture: {res.get('error') or res.get('kind') or 'failed'}"], "seconds": round(time.time() - t0, 1)}
    bad = validate(tmp, seconds)
    if bad:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "path": "", "reasons": [f"file: {bad}"], "seconds": round(time.time() - t0, 1)}
    frames = frames_of(str(tmp))
    if not storyboard:
        # no storyboard to compare with (age-restricted video, previewed from thumbnails): the clip is judged on its own frames, and a cut
        # inside it is never kept as a fragment: the longest cut-free stretch of at least MIN_S stays, else the capture is dropped
        v = verify(frames, [], start, seconds)
        a, b = longest_uncut(frames)
        v["inspection"] = "captured frames (no storyboard)"
        if v["ok"] and b - a < F.MIN_S:
            v["ok"], v["reasons"] = False, [f"picture: no cut-free stretch of {F.MIN_S:g} s in the capture"]
        if v["ok"] and (a > 0.01 or b < len(frames) / 2.0 - 0.01):
            cut = tmp.with_name(tmp.stem + ".trim.mp4")
            if _trim(tmp, cut, a, b):
                cut.replace(tmp)
                v["trimmed"] = [round(a, 2), round(b, 2)]
    else:
        v = verify(frames, tiles, start, seconds)
        if v["ok"]:
            # storyboard tiles are 2-5 s apart: a quick edit inside the source can hide between them (render 041: a 0.2 s fragment).
            # The capture's own frames decide: keep the longest cut-free stretch, drop the clip when that is under MIN_S
            a, b = longest_uncut(frames)
            full = len(frames) / 2.0
            if b - a < F.MIN_S:
                v["ok"], v["reasons"] = False, [f"picture: the source cuts inside the capture; longest cut-free stretch {b - a:.1f} s"]
            elif a > 0.01 or b < full - 0.01:
                cut = tmp.with_name(tmp.stem + ".trim.mp4")
                if _trim(tmp, cut, a, b):
                    cut.replace(tmp)
                    v["trimmed"] = [round(a, 2), round(b, 2)]
    if not v["ok"]:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "path": "", "reasons": v["reasons"], "verify": v, "seconds": round(time.time() - t0, 1)}
    tmp.replace(dest)
    return {"ok": True, "path": str(dest), "reasons": [], "verify": v, "seconds": round(time.time() - t0, 1),
            "width": res.get("width"), "height": res.get("height")}


def write_record(manifest: Any, scene_no: str, row_text: str, prompt: str, pick: Dict[str, Any]) -> Dict[str, Any]:
    """The scene's manifest record for a director clip (same keys as the YouTube provider's, plus the director's provenance)."""
    c = pick["candidate"]
    w = pick["window"]
    v = pick.get("verify") or {}
    start = float(w["start"])                 # the requested second; the measured offset is stored beside it
    rec = {
        "status": "complete", "type": "video", "source": "youtube_video", "asset_type": "youtube_video", "strategy": "browser_playback",
        "local_path": pick["path"], "video_id": c.video_id, "provider_asset_id": c.video_id,
        "source_url": f"https://www.youtube.com/watch?v={c.video_id}", "video_title": c.title, "channel": c.channel,
        "author": c.channel, "license": None, "upload_date": (c.details or {}).get("upload_date") or "",
        "clip_start": round(start, 2), "clip_duration": round(float(w["end"]) - float(w["start"]), 2),
        "timestamp_end": round(float(w["end"]), 2), "duration": round(float(w["end"]) - float(w["start"]), 2),
        "selection_method": "war_director", "script_segment": row_text, "prompt": prompt,
        "authenticity": pick.get("authenticity", "unverified"), "authenticity_reasons": pick.get("authenticity_reasons", []),
        "relevance_score": pick.get("score"), "channel_tier": pick.get("tier", ""), "director_queries": pick.get("queries", []),
        "frame_flags": pick.get("frame_flags", []), "tile_hashes": list(w.get("hashes") or []),
        "match_level": pick.get("level", ""), "inspection": w.get("inspection", "storyboard"),
        "content_warning": getattr(c, "content_warning", "") or "", "metadata_blocked": bool(getattr(c, "blocked", False)),
        "moment_verified": bool(v.get("ok") and v.get("checked_against_storyboard")), "moment_match": v.get("matched"),
        "moment_offset": v.get("offset"), "resolved_at": time.time(), "error": None,
    }
    manifest.set(str(scene_no), rec)
    return rec
