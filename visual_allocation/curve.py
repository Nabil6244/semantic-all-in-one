"""Progressive visual curve — soft video/image bias by script position."""

from __future__ import annotations

VISUAL_CURVE_BANDS = (
    (0.00, 0.10, 0.88),  # first 10% — very video-heavy
    (0.10, 0.25, 0.78),
    (0.25, 0.40, 0.65),
    (0.40, 0.60, 0.52),
    (0.60, 0.75, 0.38),
    (0.75, 1.00, 0.28),  # final 25% — more image-heavy
)

STRATEGY_OFFSET = {
    "automatic": 0.0,
    "video_heavy": 0.18,
    "balanced": 0.0,
    "image_heavy": -0.22,
}


def position_ratio(index: int, total: int) -> float:
    if total <= 1:
        return 0.0
    return max(0.0, min(1.0, index / max(total - 1, 1)))


def curve_video_bias(position: float, visual_strategy: str = "automatic") -> float:
    """Return 0–1 preference for video vs image at this script position."""
    pos = max(0.0, min(1.0, float(position)))
    base = 0.5
    for lo, hi, bias in VISUAL_CURVE_BANDS:
        if lo <= pos < hi or (hi >= 1.0 and pos >= lo):
            base = bias
            break
    offset = STRATEGY_OFFSET.get(visual_strategy, 0.0)
    return max(0.05, min(0.95, base + offset))
