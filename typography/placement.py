"""Deterministic text placement — no vision / LLM.

Picks among a 3×3 grid using style, text length, aspect ratio, and optional
scene composition hints already present on the effect payload.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Tuple

from .theme import TypographyTheme

PLACEMENTS = (
    "top_left",
    "top_center",
    "top_right",
    "center_left",
    "center",
    "center_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
)

# Anchor = where the text *block center* sits (x_ratio, y_ratio).
_ANCHORS: Dict[str, Tuple[float, float]] = {
    "top_left": (0.22, 0.16),
    "top_center": (0.50, 0.14),
    "top_right": (0.78, 0.16),
    "center_left": (0.24, 0.46),
    "center": (0.50, 0.44),
    "center_right": (0.76, 0.46),
    "bottom_left": (0.24, 0.78),
    "bottom_center": (0.50, 0.76),
    "bottom_right": (0.76, 0.78),
}

# Style-specific documentary defaults (prefer fewer center collisions).
_STYLE_DEFAULT: Dict[str, str] = {
    "minimal_caption": "bottom_center",
    "question": "center",
    "statement": "center",
    "kinetic_punch": "center",
    "keyword_highlight": "bottom_center",
    "fact_number": "top_right",
    "word_reveal": "bottom_center",
    "quote": "bottom_center",
    "proof_modern": "top_left",
}


# Where to move text when its natural home is occupied. Lower-third first
# (documentary convention), then the top band, then the side columns.
_RELOCATE_ORDER = (
    "bottom_center",
    "top_center",
    "bottom_left",
    "bottom_right",
    "top_left",
    "top_right",
    "center",
)


def _aspect_kind(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "landscape"
    ratio = width / float(height)
    if ratio < 0.85:
        return "vertical"
    if ratio > 1.25:
        return "landscape"
    return "square"


def _stable_bucket(seed: str, n: int) -> int:
    if n <= 1:
        return 0
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % n


def _force_center_column(placement: str) -> str:
    row = "bottom"
    if placement.startswith("top"):
        row = "top"
    elif placement.startswith("center"):
        row = "center"
    return f"{row}_center" if row != "center" else "center"


def resolve_placement(
    style_id: str,
    text: str,
    width: int,
    height: int,
    *,
    fontsize: int = 48,
    theme: Optional[TypographyTheme] = None,
    composition: Optional[Dict[str, Any]] = None,
    effect: str = "",
    forced_placement: Optional[str] = None,
) -> Dict[str, Any]:
    """Pick a placement slot and pixel anchors for the text block center."""
    theme = theme or TypographyTheme()
    text = (text or "").strip()
    words = text.split()
    n_words = len(words)
    n_chars = len(text)
    aspect = _aspect_kind(width, height)
    composition = dict(composition or {})

    # Explicit override from variation planner or scene metadata.
    preferred = str(
        forced_placement
        or composition.get("prefer")
        or composition.get("placement")
        or ""
    ).strip()
    if preferred in PLACEMENTS:
        placement = preferred
    else:
        placement = _STYLE_DEFAULT.get(style_id, "bottom_center")

        # Length / hierarchy rules — long copy stays in lower-third / mid, never corners.
        if n_chars >= 42 or n_words >= 8:
            placement = "bottom_center" if style_id != "question" else "center"
        elif n_chars >= 28 or n_words >= 6:
            if placement.endswith(("_left", "_right")):
                placement = _force_center_column(placement)
            if style_id in ("keyword_highlight", "word_reveal", "minimal_caption", "quote"):
                placement = "bottom_center"
            elif style_id == "statement":
                placement = "center"

        # Short keywords can sit off-center in landscape without covering the hero.
        if (
            style_id == "keyword_highlight"
            and aspect == "landscape"
            and n_words <= 2
            and n_chars <= 16
        ):
            placement = ("bottom_left", "bottom_right")[
                _stable_bucket(f"{text}|{style_id}|kw", 2)
            ]

        if style_id == "fact_number":
            if aspect == "vertical":
                placement = "top_center"
            elif n_chars <= 8:
                placement = ("top_right", "top_left")[
                    _stable_bucket(f"{text}|fact", 2)
                ]
            else:
                placement = "top_center"

        if style_id == "kinetic_punch" and n_words <= 2 and aspect == "landscape":
            placement = "center"

        if style_id == "question" and n_words >= 8:
            placement = "center"

        # Vertical video: avoid left/right columns (narrow safe area).
        if aspect == "vertical" and placement.endswith(("_left", "_right")):
            placement = _force_center_column(placement)

        # Large type relative to frame → prefer center column (except proof style).
        if (
            style_id != "proof_modern"
            and fontsize >= int(height * 0.09)
            and placement.endswith(("_left", "_right"))
        ):
            placement = _force_center_column(placement)

    if composition.get("avoid_center") and placement == "center":
        placement = "bottom_center"
    avoid = composition.get("avoid") or ()
    if isinstance(avoid, str):
        avoid = (avoid,)
    avoid_set = set(avoid)
    if placement in avoid_set:
        # The style's own choice collides with the picture. Relocate to the
        # frame analyser's quietest cell when it offered one, else walk a
        # documentary-sane priority order. Only reached on a real conflict —
        # a placement that does not collide is never second-guessed.
        fallback = str(composition.get("fallback") or "")
        if fallback in _ANCHORS and fallback not in avoid_set:
            placement = fallback
        else:
            for candidate in _RELOCATE_ORDER:
                if candidate not in avoid_set:
                    placement = candidate
                    break
            else:
                placement = "bottom_center"

    if placement not in _ANCHORS:
        placement = "bottom_center"

    ax, ay = _ANCHORS[placement]
    # Safe margins from theme — clamp anchors inward on extreme edges.
    mx = float(theme.margin_x_ratio)
    ax = max(mx + 0.06, min(1.0 - mx - 0.06, ax))
    ay = max(0.12, min(0.86, ay))

    if placement.endswith("left"):
        x_align = "left"
    elif placement.endswith("right"):
        x_align = "right"
    else:
        x_align = "center"

    return {
        "placement": placement,
        "x_align": x_align,
        "anchor_x_ratio": ax,
        "anchor_y_ratio": ay,
        "aspect": aspect,
        "effect": effect,
    }


def compute_xy(
    placement_info: Dict[str, Any],
    width: int,
    height: int,
    text_w: int,
    text_h: int,
    margin_x: int,
) -> Tuple[int, int]:
    """Pixel top-left for a measured text block."""
    ax = float(placement_info["anchor_x_ratio"])
    ay = float(placement_info["anchor_y_ratio"])
    cx = int(width * ax)
    cy = int(height * ay)
    x_align = placement_info.get("x_align") or "center"
    if x_align == "left":
        x = max(margin_x, cx - text_w // 4)
    elif x_align == "right":
        x = min(width - margin_x - text_w, cx - (text_w * 3) // 4)
    else:
        x = cx - text_w // 2
    y = cy - text_h // 2
    x = max(margin_x, min(x, width - margin_x - max(text_w, 1)))
    y = max(int(height * 0.10), min(y, height - text_h - int(height * 0.08)))
    return x, y


def drawtext_x_expr(placement_info: Dict[str, Any], margin_x: int) -> str:
    """ffmpeg drawtext x expression (uses text_w)."""
    x_align = placement_info.get("x_align") or "center"
    if x_align == "left":
        return str(int(margin_x))
    if x_align == "right":
        return f"w-text_w-{int(margin_x)}"
    return "(w-text_w)/2"
