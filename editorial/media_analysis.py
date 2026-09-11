"""Deterministic media editability analysis.

No LLM — duration, media kind, and heuristic potentials only. Frame-level
motion analysis is optional when ffprobe/ffmpeg are available; failures fall
back to safe defaults so planning never blocks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .edit_decision import MediaEditability

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _probe_duration(path: Path) -> float:
    try:
        from media_duration import probe_media_duration

        d = probe_media_duration(path)
        return float(d) if d else 0.0
    except Exception:
        return 0.0


def analyze_media_editability(
    path: Optional[Path | str],
    *,
    known_duration: Optional[float] = None,
    asset_type: str = "",
) -> MediaEditability:
    """Score how flexibly a source can be edited to cover narration.

    When a video file exists on disk, probed duration is authoritative.
    Stale short ``known_duration`` metadata must not force multi-shot replay
    of an 8s Flow/stock clip into 2s loops.
    """
    media_path = Path(path) if path else None
    kind = "unknown"
    known = float(known_duration or 0.0)
    native = known

    if media_path and media_path.is_file():
        ext = media_path.suffix.lower()
        if ext in _VIDEO_EXTS:
            kind = "video"
            probed = _probe_duration(media_path)
            if probed > 0:
                # Delivered file wins over stale/short manifest metadata.
                native = probed
            elif native <= 0:
                native = 0.0
        elif ext in _IMAGE_EXTS:
            kind = "image"
            native = 0.0  # stills have no native duration
        else:
            # Guess from asset_type hint
            at = (asset_type or "").lower()
            if "video" in at:
                kind = "video"
                probed = _probe_duration(media_path)
                if probed > 0:
                    native = probed
                elif native <= 0:
                    native = 0.0
            elif "image" in at or at in ("image", "stock_image", "flow_image"):
                kind = "image"

    if kind == "unknown":
        at = (asset_type or "").lower()
        if "video" in at:
            kind = "video"
        elif "image" in at:
            kind = "image"

    if kind == "image":
        return MediaEditability(
            native_duration=0.0,
            usable_duration=0.0,
            media_kind="image",
            motion_level=0.0,
            loopability=0.0,
            crop_potential=0.85,
            reframe_potential=0.9,
            punch_in_potential=0.9,
            slow_motion_potential=0.0,
            speed_change_tolerance=0.0,
            visual_complexity=0.45,
            editability_score=0.82,
            notes="still — Ken Burns / punch-in / reframe preferred over freeze",
        )

    # Video — keep almost all of the delivered length for coverage decisions.
    # A tiny handle is fine for endpoints; it must not make an 8s clip look like
    # it cannot cover a 5s VO (that triggered same-shot 2s×3 replay).
    usable = native
    if native > 0:
        handle = min(0.15, native * 0.02)
        usable = max(0.4, native - handle)

    motion = 0.55
    loopability = 0.15
    if native >= 8.0:
        loopability = 0.35
        motion = 0.6
    if native < 2.5:
        loopability = 0.05
        motion = 0.4

    punch = 0.75 if native >= 2.0 else 0.45
    reframe = 0.7
    speed_tol = 0.12 if native >= 3.0 else 0.06
    slow_mo = 0.35 if native >= 4.0 else 0.15

    # Aggregate: longer usable + punch/reframe potential
    score = 0.35
    if usable >= 4.0:
        score += 0.25
    elif usable >= 2.0:
        score += 0.15
    score += punch * 0.2
    score += reframe * 0.1
    score += min(0.15, loopability)
    score = round(min(1.0, max(0.05, score)), 3)

    notes = "video — prefer multi-shot / punch-in over blind loop"
    if known > 0 and native > 0 and known + 0.35 < native:
        notes = (
            f"video — probed {native:.1f}s overrides stale known {known:.1f}s; "
            "single-shot when file covers narration"
        )

    return MediaEditability(
        native_duration=round(native, 3),
        usable_duration=round(usable, 3),
        media_kind="video",
        motion_level=motion,
        loopability=loopability,
        crop_potential=0.7,
        reframe_potential=reframe,
        punch_in_potential=punch,
        slow_motion_potential=slow_mo,
        speed_change_tolerance=speed_tol,
        visual_complexity=0.5,
        editability_score=score,
        natural_endpoint=round(usable, 3) if usable > 0 else None,
        notes=notes,
    )
