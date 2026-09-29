"""Zoom-blur transition (the reference style's fast zoom with blur and red/blue
colour fringes, plus a whoosh) — used only at big moments, never on every cut:

  * into or out of a map scene,
  * at the start of each countdown fact ("34. The Roof of Florida").

The effect is a short pass on the two finished scene clips either side of the
cut (see apply_zoom_blur): the outgoing clip zooms into a blur over its last
~0.27 s, the incoming one snaps out of a blur over its first ~0.27 s, and the
cut sits in the middle. Duration-preserving, so the timeline never shifts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

ZOOM_BLUR = "zoom_blur"
DURATION_S = 0.27
_MIN_CLIP_S = 0.9  # a clip shorter than this keeps a plain cut (the effect would be most of it)


def mark_zoom_blur_transitions(plan, *, map_scene_numbers: Iterable[str] = (),
                               narrations_by_scene: Optional[dict] = None) -> List[str]:
    """Set transition_in = "zoom_blur" on qualifying scenes of an EditorialPlan
    (in place). Returns the marked scene numbers."""
    scenes = list(getattr(plan, "scenes", None) or [])
    if len(scenes) < 2:
        return []
    maps = {str(s) for s in map_scene_numbers}
    fact_starts = set()
    try:
        from .countdown import detect_countdown

        full = narrations_by_scene or {}
        countdown = detect_countdown([full.get(str(s.scene_number)) or getattr(s, "narration_excerpt", "")
                                      for s in scenes])
        if countdown is not None:
            # Only a heading said at the very start of its scene lines up with the cut.
            fact_starts = {f.scene_index for f in countdown.facts if f.offset <= 0.25}
    except Exception:
        fact_starts = set()
    marked: List[str] = []
    for i in range(1, len(scenes)):
        prev, cur = scenes[i - 1], scenes[i]
        if not (str(cur.scene_number) in maps or str(prev.scene_number) in maps or i in fact_starts):
            continue
        if float(cur.duration) < _MIN_CLIP_S or float(prev.duration) < _MIN_CLIP_S:
            continue
        cur.transition_in = ZOOM_BLUR
        marked.append(str(cur.scene_number))
    return marked


def zoom_blur_scene_numbers(plan) -> List[str]:
    return [str(s.scene_number) for s in (getattr(plan, "scenes", None) or [])
            if str(getattr(s, "transition_in", "") or "") == ZOOM_BLUR]


def _probe_duration(path: Path) -> float:
    try:
        from media_duration import probe_media_duration

        return float(probe_media_duration(path, log_failures=False) or 0.0)
    except Exception:
        return 0.0


def zoom_blur_filter(duration: float, *, head: bool, tail: bool, width: int, height: int, fps: int,
                     d: float = DURATION_S) -> str:
    """-vf chain: zoom ramp + two-stage blur + two-stage red/blue split on the
    first ``d`` s (head: resolving out of the blur) and/or last ``d`` s (tail:
    zooming into it)."""
    t0 = max(0.0, duration - d)
    half = d / 2.0
    zoom_terms = []
    if head:
        zoom_terms.append(f"if(lt(it,{d:.4f}),1.0*pow(1-it/{d:.4f},1.5),0)")
    if tail:
        zoom_terms.append(f"if(gte(it,{t0:.4f}),1.3*pow((it-{t0:.4f})/{d:.4f},1.5),0)")
    z = "1+" + "+".join(zoom_terms) if zoom_terms else "1"
    parts = [
        f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps}",
        "format=gbrp",
    ]
    strong_w, weak_w = [], []
    if head:
        strong_w.append(f"lt(t,{half:.4f})")
        weak_w.append(f"between(t,{half:.4f},{d:.4f})")
    if tail:
        weak_w.append(f"between(t,{t0:.4f},{t0 + half:.4f})")
        strong_w.append(f"gte(t,{t0 + half:.4f})")
    for w in weak_w:
        parts.append(f"gblur=sigma=5:enable='{w}'")
        parts.append(f"rgbashift=rh=-22:bh=22:edge=smear:enable='{w}'")
    for w in strong_w:
        parts.append(f"gblur=sigma=16:enable='{w}'")
        parts.append(f"rgbashift=rh=-48:bh=48:rv=8:bv=-8:edge=smear:enable='{w}'")
    parts.append("format=yuv420p")
    return ",".join(parts)


def apply_zoom_blur(clip: Path, *, head: bool, tail: bool, width: int, height: int, fps: int,
                    ffmpeg: str = "ffmpeg", encode_args: Sequence[str] = ("-c:v", "libx264", "-preset", "veryfast",
                                                                         "-crf", "18")) -> bool:
    """Apply the effect to a finished scene clip in place. False (clip left
    untouched) when it's too short or ffmpeg fails — a plain cut is the
    fallback, never a broken clip."""
    clip = Path(clip)
    if not (head or tail) or not clip.is_file():
        return False
    duration = _probe_duration(clip)
    if duration < _MIN_CLIP_S:
        return False
    out = clip.with_name(f"{clip.stem}_zb{clip.suffix}")
    vf = zoom_blur_filter(duration, head=head, tail=tail, width=width, height=height, fps=fps)
    cmd = [ffmpeg, "-y", "-v", "error", "-i", str(clip), "-map", "0:v", "-map", "0:a?", "-vf", vf,
           *encode_args, "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "copy", str(out)]
    try:
        from providers import hidden_subprocess as hs

        result = hs.run(cmd, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        out.unlink(missing_ok=True)
        return False
    if result.returncode != 0 or not out.is_file() or abs(_probe_duration(out) - duration) > 0.1:
        out.unlink(missing_ok=True)
        return False
    out.replace(clip)
    return True
