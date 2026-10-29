"""The narrator standing over the map (the reference shows the same presenter on map beats as on boards). Hybrid's map is drawn by pakmap-engine (not ours to change), so the presenter is laid
over the FINISHED map video with ffmpeg, only where no footage or board covers the map. Nothing here touches hybrid/ or pakmap-engine/.

The Explainer director leaves `map_narrator.json` ({"style": ...}) beside its board clips; `pakmap.app_integration` asks `apply_if_marked` right after the map is drawn. Never raises: on any
failure the map video is used as it is."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MARKER = "map_narrator.json"
HEIGHT = 440                    # px on the 1080-high frame
MARGIN_X, MARGIN_BOTTOM = 36, 0
LOOP_S = 1.2
MIN_WINDOW_S = 1.6              # a map stretch shorter than this shows no narrator (he would pop in and out)
EDGE_S = 0.35                   # keep clear of the dissolve into and out of a covering clip
FPS = 30
MOUTHS = ("closed", "open", "wide", "open", "closed", "o", "open", "closed")


def marker_path(folder: "str | Path") -> Path:
    return Path(folder) / MARKER


def write_marker(folder: "str | Path", style: str) -> None:
    Path(folder).mkdir(parents=True, exist_ok=True)
    marker_path(folder).write_text(json.dumps({"style": style}), encoding="utf-8")


def clear_marker(folder: "str | Path") -> None:
    try:
        marker_path(folder).unlink()
    except OSError:
        pass


def map_windows(spec: Dict[str, Any]) -> List[Tuple[float, float]]:
    """Seconds of the video where the map itself is on screen: the whole video minus the spans a media_full clip covers."""
    dur = float(spec.get("duration") or 0.0)
    covers = sorted((float(e["t_in"]), float(e["t_out"])) for e in spec.get("events", []) if e.get("type") == "media_full")
    out: List[Tuple[float, float]] = []
    cur = 0.0
    for a, b in covers + [(dur, dur)]:
        if a - cur > 1e-6:
            out.append((cur, min(a, dur)))
        cur = max(cur, b)
    res = []
    for a, b in out:
        a2, b2 = a + (EDGE_S if a > 0 else 0.0), b - (EDGE_S if b < dur - 1e-6 else 0.0)
        if b2 - a2 >= MIN_WINDOW_S:
            res.append((round(a2, 3), round(b2, 3)))
    return res


def build_loop(style: str, path: "str | Path") -> Tuple[int, int]:
    """A short looping alpha clip of the presenter talking (mouth cycle, a slight sway). Returns its (width, height)."""
    from ..narrator import rig
    base_h = rig.canvas_size(style)[1]
    pct = max(10, round(100 * HEIGHT / base_h))
    frames = int(LOOP_S * FPS)
    sp0 = rig.sprite("point", "open", "closed", pct, True, style)
    w, h = sp0.size
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-an", "-c:v", "qtrle", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(frames):
        mouth = MOUTHS[(i * len(MOUTHS)) // frames]
        eyes = "blink" if i == frames // 2 else "open"
        pose = "explain" if (i // 12) % 2 else "point"
        p.stdin.write(rig.sprite(pose, eyes, mouth, pct, True, style).tobytes())
    p.stdin.close()
    if p.wait(timeout=600) != 0:
        raise RuntimeError("could not build the presenter loop")
    return w, h


def apply(video_in: "str | Path", video_out: "str | Path", windows: Sequence[Tuple[float, float]], style: str, work: "str | Path") -> int:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_in)], capture_output=True, text=True, timeout=120).stdout.strip())
    loop = Path(work) / f"map_narrator_{style}.mov"
    w, h = build_loop(style, loop)
    when = "+".join(f"between(t,{a},{b})" for a, b in windows)
    x, y = 1920 - w - MARGIN_X, 1080 - h - MARGIN_BOTTOM
    fc = f"[1:v]format=rgba[n];[0:v][n]overlay={x}:{y}:enable='{when}':eof_action=repeat:shortest=1:format=auto[v]"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video_in), "-stream_loop", "-1", "-i", str(loop), "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "14",
           "-pix_fmt", "yuv420p", "-preset", "medium", "-c:a", "copy", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(video_out)]
    return subprocess.run(cmd, timeout=7200).returncode


def apply_if_marked(video: "str | Path", spec: Dict[str, Any], work: "str | Path", log=lambda m: None) -> Optional[Path]:
    """Looks for the director's marker beside `work` (the Hybrid work folder) or in it. Returns the new video's path, or None (nothing marked, no map stretch, or a failure)."""
    try:
        work = Path(work)
        mk = next((m for m in (marker_path(work.parent / "explainer"), marker_path(work / "explainer")) if m.exists()), None)
        if mk is None:
            return None
        style = json.loads(mk.read_text(encoding="utf-8")).get("style", "serious")
        wins = map_windows(spec)
        if not wins:
            return None
        out = Path(video).with_name(Path(video).stem + "_presenter.mp4")
        if apply(video, out, wins, style, work) != 0 or not out.exists():
            log("[Explainer] the presenter could not be laid over the map; the map is used as it is")
            return None
        log(f"[Explainer] the presenter stands over the map for {sum(b - a for a, b in wins):.0f} s")
        return out
    except Exception as exc:
        log(f"[Explainer] the presenter could not be laid over the map ({str(exc)[:100]}); the map is used as it is")
        return None
