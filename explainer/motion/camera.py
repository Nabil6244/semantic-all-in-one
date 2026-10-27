"""Board camera: ONE global transform on the finished frame (a crop box resampled back to the frame size). Opt-in; "off" never touches a frame.

    box = camera_box("push", n_frames, i, fps, size)       # (x0, y0, x1, y1) floats in source pixels, or None = leave the frame alone
    im  = apply(im, box)                                    # one PIL resize with the float box

Modes: "push" a slow ease-in-out zoom 1.0 -> 1.045; "drift" a constant 1.03 zoom while the window glides side to side; "reframe" the push, while the window centre also eases
from the frame centre to `focus` (fractions of the frame, mid-clip) so a key area is brought toward the middle.
A pure function of (mode, clip length, frame index, size, focus): no randomness, no state. Clips shorter than MIN_SECONDS (4 s) get no camera.

Safe area: the board layout keeps content inside a MARGIN (96 px at 1920x1080). A crop removes the frame edges, and content that sat on the margin moves outward by the zoom. So the window
is clamped every frame to keep the whole SAFE rectangle at least MIN_INSET (40 px at 1920 wide) inside the output frame, and ZOOM_CAP (1.06) is below the zoom at which that is possible
(1.0648 horizontally, 1.063 vertically at 1920x1080). `mapped_safe` returns where the SAFE rectangle lands; the tests check it at every frame, last one included."""

from __future__ import annotations

import math
from typing import Optional, Tuple

from PIL import Image

MODES = ("off", "push", "drift", "reframe")
MIN_SECONDS = 4.0
PUSH_ZOOM = 1.045
DRIFT_ZOOM = 1.03
DRIFT_PAN = 20.0                       # px at 1920 wide, half range
ZOOM_CAP = 1.06
MARGIN = 96                            # board layout margin at 1920x1080 (board/layout.py MARGIN)
MIN_INSET = 40                         # the SAFE rectangle stays at least this far inside the output (at 1920 wide)
REF = (1920, 1080)


def _smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


def _axis(z: float, full: float, scale: float, want_offset: float) -> float:
    """Window start on one axis: the wanted start, clamped inside the frame and so the SAFE span keeps MIN_INSET."""
    w = full / z
    margin, inset = MARGIN * scale, MIN_INSET * scale
    lo = (full - margin) - (full - inset) / z          # right edge of SAFE maps to <= full - inset
    hi = margin - inset / z                            # left edge of SAFE maps to >= inset
    lo, hi = max(lo, 0.0), min(hi, full - w)
    if lo > hi:                                        # cannot happen under ZOOM_CAP; centre rather than fail
        return (full - w) / 2.0
    return min(hi, max(lo, want_offset))


def camera_box(mode: str, n_frames: int, i: int, fps: int, size: Tuple[int, int] = REF, focus: Optional[Tuple[float, float]] = None) -> Optional[Tuple[float, float, float, float]]:
    if mode in (None, "", "off") or mode not in MODES:
        return None
    if n_frames < MIN_SECONDS * fps - 1e-9:
        return None
    W, H = size
    sc = W / REF[0]
    u = i / max(1, n_frames - 1)
    u = min(1.0, max(0.0, u))
    if mode == "drift":
        z = DRIFT_ZOOM
        pan = -math.cos(math.pi * u)                   # -1 -> +1, slow at both ends
        fx, fy = 0.5, 0.5
        cx_off, cy_off = pan * DRIFT_PAN * sc, -pan * DRIFT_PAN * 0.5 * sc
    else:
        z = 1.0 + (PUSH_ZOOM - 1.0) * _smooth(u)
        cx_off = cy_off = 0.0
        fx, fy = 0.5, 0.5
        if mode == "reframe" and focus:
            k = _smooth((u - 0.2) / 0.6)
            fx, fy = 0.5 + (focus[0] - 0.5) * k, 0.5 + (focus[1] - 0.5) * k
    z = min(z, ZOOM_CAP)
    w, h = W / z, H / z
    x0 = _axis(z, W, sc, fx * W - w / 2.0 + cx_off)
    y0 = _axis(z, H, sc, fy * H - h / 2.0 + cy_off)
    return (x0, y0, x0 + w, y0 + h)


def apply(im: Image.Image, box: Optional[Tuple[float, float, float, float]]) -> Image.Image:
    if box is None:
        return im
    return im.resize(im.size, Image.BILINEAR, box=box)


def mapped_safe(box: Tuple[float, float, float, float], size: Tuple[int, int] = REF) -> Tuple[float, float, float, float]:
    """Where the layout's SAFE rectangle (margin 96 at 1920x1080) lands in the output frame for this window."""
    W, H = size
    sc = W / REF[0]
    x0, y0, x1, y1 = box
    kx, ky = W / (x1 - x0), H / (y1 - y0)
    m = MARGIN * sc
    return ((m - x0) * kx, (m - y0) * ky, (W - m - x0) * kx, (H - m - y0) * ky)
