"""Frame-aware placement hints — where the picture can afford to carry text.

Placement was previously blind: it chose a grid cell from style, text length
and aspect ratio alone. `placement.resolve_placement()` already accepts a
`composition` dict with `avoid` / `prefer` keys, but nothing in the pipeline
ever produced one, so those branches never ran and text regularly landed on
a face, a subject, or a clip's own burned-in captions.

This module fills that gap with local analysis only — numpy + Pillow, no
vision API, no extra dependency, deterministic for a given frame.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .placement import PLACEMENTS

# Rows/cols of the analysis grid, matching the 3x3 placement grid.
_ROWS = ("top", "center", "bottom")
_COLS = ("left", "center", "right")

# Busy-ness is judged RELATIVE to the frame, not against a fixed number.
# Absolute thresholds do not survive contact with real footage: a dark space
# plate and a lit interior differ by an order of magnitude in gradient energy,
# so any constant is either always or never tripped. A cell is busy when it
# carries markedly more detail than the frame's own median.
_BUSY_DETAIL_RATIO = 1.45
# ...but ignore the ratio entirely on frames that are flat everywhere, where
# 1.45x of almost nothing is still nothing.
_BUSY_DETAIL_FLOOR = 0.010
# Bright cells wash out white type even through the scrim.
_BRIGHT_MEAN = 0.66
# Burned-in captions / watermarks, again relative to the frame.
_TEXTLIKE_RATIO = 2.0
_TEXTLIKE_FLOOR = 0.015


def _cell_name(row: str, col: str) -> str:
    return "center" if (row == "center" and col == "center") else f"{row}_{col}"


def analyze_frame(image: Any) -> Dict[str, Any]:
    """Score a single frame's 3x3 grid and derive placement hints.

    Returns a dict shaped for `placement.resolve_placement(composition=...)`:
    `avoid` (list of placement ids), `prefer` (best cell), plus the raw
    per-cell scores for logging and tests.
    """
    import numpy as np
    from PIL import Image

    if not isinstance(image, Image.Image):
        image = Image.open(image)
    # Small working copy: placement decisions do not need full resolution,
    # and this keeps the per-scene cost negligible.
    # 384x216 keeps small burned-in captions detectable; 192x108 blurred them
    # away entirely, which is how a clip's own subtitles went unnoticed.
    frame = image.convert("L").resize((384, 216))
    arr = np.asarray(frame, dtype=np.float32) / 255.0

    # Subject map via spectral-residual saliency. A plain gradient mean was
    # measured to be useless here: across real frames every cell scored
    # 0.031-0.056, so no threshold could separate a subject from background
    # texture. Saliency does separate them, at negligible cost (an FFT on a
    # 128x72 image).
    detail = _saliency(arr)
    gy, gx = np.gradient(arr)
    grad = np.hypot(gx, gy)

    h, w = arr.shape
    rh, cw = h // 3, w // 3
    cells: Dict[str, Dict[str, float]] = {}
    for ri, row in enumerate(_ROWS):
        for ci, col in enumerate(_COLS):
            ys = slice(ri * rh, (ri + 1) * rh if ri < 2 else h)
            xs = slice(ci * cw, (ci + 1) * cw if ci < 2 else w)
            patch = arr[ys, xs]
            dpatch = detail[ys, xs]
            gpatch = grad[ys, xs]
            # Burned-in captions and watermarks read as bright pixels with
            # very high local gradient — distinct from general scene texture.
            bright = patch > 0.75
            textlike = float((bright & (gpatch > 0.10)).mean()) if patch.size else 0.0
            cells[_cell_name(row, col)] = {
                "detail": float(dpatch.mean()),
                "mean": float(patch.mean()),
                "variance": float(patch.var()),
                "textlike": textlike,
            }

    import statistics

    detail_median = statistics.median(m["detail"] for m in cells.values()) or 0.0
    textlike_median = statistics.median(m["textlike"] for m in cells.values()) or 0.0
    busy_cut = max(_BUSY_DETAIL_FLOOR, detail_median * _BUSY_DETAIL_RATIO)
    text_cut = max(_TEXTLIKE_FLOOR, textlike_median * _TEXTLIKE_RATIO)

    avoid: List[str] = []
    for name, m in cells.items():
        if (
            m["detail"] >= busy_cut
            or m["mean"] >= _BRIGHT_MEAN
            or m["textlike"] >= text_cut
        ):
            avoid.append(name)

    # Never let the analysis paint the whole frame as unusable — if it does,
    # keep the quietest three cells and treat the rest as avoid.
    ranked = sorted(cells.items(), key=lambda kv: _cost(kv[1]))
    if len(avoid) >= len(PLACEMENTS) - 1:
        keep = {name for name, _ in ranked[:3]}
        avoid = [name for name in cells if name not in keep]

    return {
        "avoid": avoid,
        "prefer": ranked[0][0],
        "cells": cells,
        "thresholds": {"busy": round(busy_cut, 4), "textlike": round(text_cut, 4)},
    }


def _saliency(arr: "Any") -> "Any":
    """Spectral-residual saliency (Hou & Zhang). Pure numpy, no new deps."""
    import numpy as np
    from PIL import Image, ImageFilter

    small = np.asarray(
        Image.fromarray((arr * 255).astype("uint8")).resize((128, 72)),
        dtype=np.float64,
    ) / 255.0
    spectrum = np.fft.fft2(small)
    log_mag = np.log(np.abs(spectrum) + 1e-8)
    phase = np.angle(spectrum)
    kernel = np.ones((3, 3)) / 9.0
    averaged = np.real(
        np.fft.ifft2(np.fft.fft2(log_mag) * np.fft.fft2(kernel, s=log_mag.shape))
    )
    residual = log_mag - averaged
    sal = np.abs(np.fft.ifft2(np.exp(residual + 1j * phase))) ** 2
    peak = float(sal.max()) or 1.0
    sal = np.asarray(
        Image.fromarray((sal / peak * 255).astype("uint8")).filter(
            ImageFilter.GaussianBlur(3)
        ).resize((arr.shape[1], arr.shape[0])),
        dtype=np.float64,
    ) / 255.0
    return sal


def _cost(m: Dict[str, float]) -> float:
    """Lower is a better home for type."""
    return (
        m["detail"] * 3.0
        + max(0.0, m["mean"] - 0.55) * 1.5
        + m["textlike"] * 4.0
        + m["variance"] * 0.5
    )


def analyze_media(
    media_path: Path | str,
    *,
    at_time: float = 0.0,
    ffmpeg: str = "ffmpeg",
    is_video: bool = False,
    scratch_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Composition hints for a still or a video frame. {} if anything fails.

    Placement must never be blocked by analysis: every failure path here
    returns an empty dict, which leaves `resolve_placement` exactly as it
    behaved before.
    """
    try:
        media_path = Path(media_path)
        if not media_path.is_file():
            return {}
        if not is_video:
            return analyze_frame(media_path)

        import tempfile

        # Match the rest of the pipeline: this wrapper suppresses the console
        # window ffmpeg would otherwise flash on Windows, once per scene.
        try:
            from providers import hidden_subprocess as subprocess
        except Exception:
            import subprocess

        target_dir = Path(scratch_dir) if scratch_dir else Path(tempfile.gettempdir())
        target_dir.mkdir(parents=True, exist_ok=True)
        frame_path = target_dir / f"_comp_{abs(hash((str(media_path), round(at_time, 2))))}.png"
        proc = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error",
                "-ss", f"{max(0.0, float(at_time)):.3f}",
                "-i", str(media_path), "-frames:v", "1",
                "-y", str(frame_path),
            ],
            capture_output=True,
        )
        if proc.returncode != 0 or not frame_path.is_file():
            return {}
        try:
            return analyze_frame(frame_path)
        finally:
            try:
                frame_path.unlink()
            except OSError:
                pass
    except Exception:
        return {}


def merge_composition(
    base: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Combine analysis with any composition already on the payload.

    An explicit hint on the effect wins: the analyser is advisory, and a
    deliberate `prefer` from upstream must not be overridden by it.
    """
    out: Dict[str, Any] = dict(base or {})
    if not analysis:
        return out
    avoid: List[str] = list(out.get("avoid") or ())
    if isinstance(out.get("avoid"), str):
        avoid = [out["avoid"]]
    for name in analysis.get("avoid") or ():
        if name not in avoid:
            avoid.append(name)
    if avoid:
        out["avoid"] = avoid
    # Deliberately NOT set as `prefer`: that would override the style/length
    # rules on every scene and relocate text that was already sitting well.
    # This is only the target to relocate TO, used when the style's own
    # choice collides with something in the picture.
    fallback = analysis.get("prefer")
    if fallback in PLACEMENTS and not out.get("fallback"):
        out["fallback"] = fallback
    return out
