"""Conflict rules between Smart Text and timeline graphics.

Documentary rule: one text treatment at a time. Prefer the lower-third /
panel graphic over floating Smart Text punches when both cover the same beat.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Sequence, Set, Tuple


def _tokens(text: str) -> Set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9']+", (text or "").lower())
        if len(t) >= 3
    }


def graphic_text_blob(spec: Any) -> str:
    parts: List[str] = []
    text = getattr(spec, "text", None)
    if text is not None:
        parts.append(str(getattr(text, "text", "") or ""))
        parts.append(str(getattr(text, "secondary_text", "") or ""))
        parts.append(str(getattr(text, "tertiary_text", "") or ""))
    parts.append(str(getattr(spec, "source", "") or ""))
    payload = getattr(spec, "payload", None) or {}
    if isinstance(payload, dict):
        parts.append(str(payload.get("text") or ""))
    return " ".join(p for p in parts if p)


def graphic_local_window(
    spec: Any,
    *,
    scene_start: float,
    scene_end: float,
) -> Tuple[float, float]:
    t0 = max(0.0, float(getattr(spec, "start", 0.0)) - float(scene_start))
    t1 = max(t0 + 0.05, float(getattr(spec, "end", t0)) - float(scene_start))
    scene_dur = max(0.05, float(scene_end) - float(scene_start))
    return (min(t0, scene_dur), min(t1, scene_dur + 0.01))


def smart_text_conflicts_with_graphics(
    fx: dict,
    graphics: Sequence[Any],
    *,
    scene_start: float,
    scene_end: float,
    overlap_pad_s: float = 0.15,
) -> bool:
    """True when a Smart Text effect should be skipped for a graphic already planned."""
    if not graphics:
        return False
    fx_t0 = float(fx.get("local_start") or 0.0)
    fx_t1 = float(fx.get("local_end") or fx_t0 + 0.3)
    if fx_t1 <= fx_t0:
        fx_t1 = fx_t0 + 0.12
    fx_tokens = _tokens(str(fx.get("text") or ""))

    for spec in graphics:
        role = str(getattr(spec, "role", "") or "").upper()
        decision = str(getattr(spec, "decision", "") or "").upper()
        # Only suppress against real on-screen text graphics.
        if role in ("",) and decision in ("NO_GRAPHIC",):
            continue
        g0, g1 = graphic_local_window(spec, scene_start=scene_start, scene_end=scene_end)
        # Time overlap (with small pad so near-adjacent punches still drop).
        if fx_t1 + overlap_pad_s < g0 or fx_t0 - overlap_pad_s > g1:
            # No time overlap — still suppress if same key tokens (name punches).
            g_tokens = _tokens(graphic_text_blob(spec))
            if fx_tokens and g_tokens and (fx_tokens & g_tokens):
                return True
            continue
        # Any overlapping documentary graphic wins over Smart Text.
        if role in (
            "LOWER_THIRD", "NAME", "CALLOUT", "EMPHASIS", "LABEL",
            "STATISTIC", "LOCATION", "QUOTE", "CHAPTER", "CAPTION",
        ) or decision in (
            "LOWER_THIRD", "TEXT", "STATISTIC", "CALLOUT", "LOCATION", "QUOTE",
        ):
            return True
        g_tokens = _tokens(graphic_text_blob(spec))
        if fx_tokens and g_tokens and (fx_tokens & g_tokens):
            return True
    return False


def filter_smart_text_for_graphics(
    effects: Iterable[dict],
    graphics: Sequence[Any],
    *,
    scene_start: float,
    scene_end: float,
) -> List[dict]:
    """Drop Smart Text effects that would double-up with preferred graphics."""
    out: List[dict] = []
    for fx in effects or []:
        if not isinstance(fx, dict):
            continue
        if smart_text_conflicts_with_graphics(
            fx, graphics, scene_start=scene_start, scene_end=scene_end
        ):
            continue
        out.append(fx)
    return out
