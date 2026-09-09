"""Normalize graphic semantic metadata from role / intent / narration cues."""

from __future__ import annotations

from typing import Any, Tuple

from .schema import (
    EMPHASIS_LEVELS,
    IMPORTANCE_LEVELS,
    SEMANTIC_PURPOSES,
    TEXT_ROLES,
)

_ROLE_ALIASES = {
    "PERSON": "NAME",
    "SPEAKER": "NAME",
    "SUBJECT": "NAME",
    "TECHNICAL": "TECHNICAL_LABEL",
    "ANNOTATE": "ANNOTATION",
    "FACT": "STATISTIC",
    "NUMBER": "STATISTIC",
    "PLACE": "LOCATION",
    "GEO": "LOCATION",
    "HISTORICAL": "DATE",
    "YEAR": "DATE",
}

_ROLE_PURPOSE = {
    "LOCATION": "orient",
    "NAME": "identify",
    "LOWER_THIRD": "identify",
    "STATISTIC": "quantify",
    "DATE": "establish",
    "CHAPTER": "transition",
    "QUOTE": "emphasize",
    "EMPHASIS": "emphasize",
    "CALLOUT": "explain",
    "EVIDENCE": "explain",
    "ANNOTATION": "explain",
    "TECHNICAL_LABEL": "explain",
    "COMPARISON": "compare",
    "TITLE": "establish",
    "CAPTION": "explain",
    "LABEL": "identify",
    "DATA_LABEL": "quantify",
}

_ROLE_EMPHASIS = {
    "STATISTIC": "strong",
    "CHAPTER": "strong",
    "EMPHASIS": "strong",
    "QUOTE": "normal",
    "LOCATION": "subtle",
    "LABEL": "subtle",
    "TECHNICAL_LABEL": "subtle",
    "ANNOTATION": "subtle",
    "DATE": "subtle",
    "CAPTION": "subtle",
    "LOWER_THIRD": "normal",
    "NAME": "normal",
    "CALLOUT": "normal",
}


def normalize_role(role: str) -> str:
    key = str(role or "LABEL").strip().upper().replace(" ", "_").replace("-", "_")
    key = _ROLE_ALIASES.get(key, key)
    return key if key in TEXT_ROLES else "LABEL"


def normalize_importance(raw: Any, *, role: str = "", confidence: float = 0.6) -> str:
    key = str(raw or "").strip().lower()
    if key in IMPORTANCE_LEVELS:
        return key
    role_u = normalize_role(role)
    if role_u in ("STATISTIC", "CHAPTER") and confidence >= 0.7:
        return "high"
    if role_u in ("EMPHASIS",) and confidence >= 0.75:
        return "high"
    if role_u in ("LOCATION", "LABEL", "TECHNICAL_LABEL", "ANNOTATION", "DATE"):
        return "low"
    if confidence >= 0.85:
        return "high"
    if confidence < 0.45:
        return "low"
    return "medium"


def normalize_emphasis(raw: Any, *, role: str = "", importance: str = "medium") -> str:
    key = str(raw or "").strip().lower()
    if key in EMPHASIS_LEVELS:
        return key
    role_u = normalize_role(role)
    base = _ROLE_EMPHASIS.get(role_u, "normal")
    if importance == "critical":
        return "dramatic" if base in ("strong", "dramatic") else "strong"
    if importance == "high" and base == "normal":
        return "strong"
    if importance == "low" and base == "strong":
        return "normal"
    return base


def normalize_purpose(raw: Any, *, role: str = "") -> str:
    key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key in SEMANTIC_PURPOSES:
        return key
    return _ROLE_PURPOSE.get(normalize_role(role), "identify")


def infer_semantics(
    *,
    role: str,
    importance: Any = None,
    emphasis: Any = None,
    purpose: Any = None,
    confidence: float = 0.6,
    decision: str = "",
    intent: Any = None,
) -> Tuple[str, str, str, str]:
    """Return (role, importance, emphasis, semantic_purpose)."""
    role_u = normalize_role(role)
    if intent is not None:
        if isinstance(intent, dict):
            pacing = str(intent.get("pacing") or "").lower()
            reveal = bool(intent.get("reveal"))
        else:
            pacing = str(getattr(intent, "pacing", "") or "").lower()
            reveal = bool(getattr(intent, "reveal", False))
        if pacing == "impact" and not importance:
            importance = "high"
        if pacing in ("hold", "reflective") and not emphasis:
            emphasis = "subtle"
        if reveal and not purpose:
            purpose = "reveal"

    if decision.upper() == "STATISTIC":
        role_u = "STATISTIC"
    elif decision.upper() == "LOWER_THIRD":
        role_u = "LOWER_THIRD" if role_u not in ("NAME", "LOWER_THIRD") else role_u

    imp = normalize_importance(importance, role=role_u, confidence=confidence)
    emp = normalize_emphasis(emphasis, role=role_u, importance=imp)
    purp = normalize_purpose(purpose, role=role_u)
    return role_u, imp, emp, purp
