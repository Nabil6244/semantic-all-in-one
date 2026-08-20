"""Typography render diagnostics (opt-in via VIDEOGEN_TYPOGRAPHY_DEBUG=1)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def typography_debug_enabled() -> bool:
    return os.environ.get("VIDEOGEN_TYPOGRAPHY_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def typography_proof_enabled() -> bool:
    """Force the unmistakable proof style on every overlay (verification only)."""
    return os.environ.get("VIDEOGEN_TYPOGRAPHY_PROOF", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def log_typography_event(
    *,
    raw_text: str,
    display_text: str,
    style_id: str,
    font: Optional[str],
    fontsize: int,
    position: str,
    effect: str,
    filter_or_overlay: str,
) -> None:
    if not typography_debug_enabled():
        return
    print(
        "[TYPOGRAPHY DEBUG]\n"
        f"raw_text: {raw_text!r}\n"
        f"display_text: {display_text!r}\n"
        f"style_id: {style_id}\n"
        f"font: {font}\n"
        f"fontsize: {fontsize}\n"
        f"position: {position}\n"
        f"effect: {effect}\n"
        f"filter: {filter_or_overlay}"
    )


def log_ffmpeg_filter(filter_complex: str) -> None:
    if not typography_debug_enabled():
        return
    # Keep readable but complete for overlay / drawtext chains.
    print("[TYPOGRAPHY DEBUG] FINAL ffmpeg filter_complex:")
    print(filter_complex)
