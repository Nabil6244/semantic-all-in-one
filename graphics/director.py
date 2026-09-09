"""Graphics Director — decides WHETHER a graphic is needed and WHAT kind.

AI / EditorialIntent answers WHAT / WHY.
This layer enforces restraint: simplest treatment that improves comprehension.
Does not invent charts/maps without data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence

from .design_system import DocumentaryDesignSystem, get_design_system
from .extract import (
    extract_locations,
    extract_name_title,
    extract_statistics,
    narration_signals,
)
from .schema import GraphicDecision


@dataclass
class GraphicDirective:
    """Soft decision for one beat — before concrete TextOverlaySpec."""

    decision: GraphicDecision
    role: str
    reason: str
    confidence: float
    priority: int  # 1=simplest … 7=complex
    text_hint: str = ""
    secondary_hint: str = ""
    tertiary_hint: str = ""
    payload: dict | None = None

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "role": self.role,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "priority": self.priority,
            "text_hint": self.text_hint,
            "secondary_hint": self.secondary_hint,
            "tertiary_hint": self.tertiary_hint,
            "payload": dict(self.payload or {}),
        }


# Priority ladder from the brief (§27)
_PRIORITY = {
    "NO_GRAPHIC": 0,
    "TEXT": 2,
    "STATISTIC": 3,
    "CALLOUT": 4,
    "LABEL": 2,
    "LOCATION": 2,
    "LOWER_THIRD": 2,
    "QUOTE": 2,
    "CHAPTER": 2,
    "PROGRESS": 5,
    "PROCESS": 5,
    "TIMELINE": 6,
    "COMPARISON": 6,
    "CHART": 6,
    "MAP": 6,
    "DOCUMENT": 5,
}


def decide_graphic(
    *,
    narration: str,
    scene_number: str = "",
    purpose: str = "context",
    intent: Any = None,
    design: DocumentaryDesignSystem | None = None,
    existing_smart_text: bool = False,
) -> List[GraphicDirective]:
    """Return 0–2 directives. Empty / NO_GRAPHIC means skip.

    Restraint rules:
    - Do not decorate.
    - Prefer no graphic when footage + narration already communicate.
    - Prefer text over chart/map/process unless geography/process/data clearly need it.
    - Skip when Smart Editing already covers the same emphasis (unless statistic/lower-third).
    """
    del design  # reserved for future density budgets
    text = (narration or "").strip()
    if not text or len(text.split()) < 3:
        return []

    signals = narration_signals(text)
    intent_text = _intent_text_strategy(intent)
    intent_graphic = _intent_graphic_strategy(intent)
    intent_role = _intent_visual_role(intent)
    intent_conf = _intent_confidence(intent)
    purpose_l = (purpose or "context").lower()

    # Explicit AI: no text / no graphic
    if intent_conf >= 0.55 and intent_text == "none" and intent_graphic == "none":
        if not (
            signals["has_statistic"]
            and intent_role in ("statistic", "data", "scale")
        ):
            return []

    candidates: List[GraphicDirective] = []

    # --- STATISTIC (meaningful numbers only) ---
    stats = extract_statistics(text)
    want_stat = bool(stats) and (
        purpose_l in ("evidence", "scale", "comparison")
        or intent_text in ("statistic", "data_graphic")
        or intent_graphic in ("chart", "data_graphic", "statistic")
        or intent_role in ("statistic", "data", "scale")
        or signals["has_statistic"]
    )
    # Don't turn every number into a giant statistic — require meaning.
    if want_stat and stats and stats[0].meaningful:
        st = stats[0]
        # If AI asked for chart but we have no series data → fall back to statistic text.
        decision: GraphicDecision = "STATISTIC"
        if intent_graphic == "chart" and intent_conf >= 0.7:
            # No fabricated series — stay on statistic treatment.
            decision = "STATISTIC"
        candidates.append(
            GraphicDirective(
                decision=decision,
                role="STATISTIC",
                reason=f"Meaningful statistic in narration ({st.display})",
                confidence=max(0.65, intent_conf),
                priority=_PRIORITY["STATISTIC"],
                text_hint=st.display,
                secondary_hint=st.label,
                payload={"value": st.value, "unit": st.unit, "raw": st.raw},
            )
        )

    # --- LOWER THIRD / NAME (preferred documentary text treatment) ---
    named = extract_name_title(text)
    if named and (
        purpose_l in ("character", "historical", "context", "explanation", "hook")
        or intent_text in ("name", "emphasis", "callout", "lower_third")
        or intent_role == "person"
        or (len(named.name.split()) >= 2 and bool(named.title))
    ):
        candidates.append(
            GraphicDirective(
                decision="LOWER_THIRD",
                role="LOWER_THIRD",
                reason=f"Identify subject: {named.name}",
                confidence=max(0.62, intent_conf),
                priority=_PRIORITY["LOWER_THIRD"],
                text_hint=named.name,
                secondary_hint=named.title,
            )
        )

    # --- LOCATION label ---
    locs = extract_locations(text)
    if locs and (
        purpose_l == "location"
        or intent_text == "location"
        or intent_role == "geography"
        or intent_graphic == "map"
    ):
        # Map only when geography is the point AND we have ≥2 places or explicit map intent.
        # Phase 5 will render maps; for now emit LOCATION text (or MAP decision stub).
        if intent_graphic == "map" and intent_conf >= 0.7 and len(locs) >= 2:
            candidates.append(
                GraphicDirective(
                    decision="MAP",
                    role="MAP",
                    reason="Multi-location geography — map preferred when data available",
                    confidence=intent_conf,
                    priority=_PRIORITY["MAP"],
                    text_hint=locs[0].name,
                    secondary_hint=locs[1].name if len(locs) > 1 else "",
                    payload={"markers": [l.name for l in locs]},
                )
            )
        else:
            candidates.append(
                GraphicDirective(
                    decision="LOCATION",
                    role="LOCATION",
                    reason=f"Establish place: {locs[0].name}",
                    confidence=max(0.55, locs[0].confidence, intent_conf * 0.9),
                    priority=_PRIORITY["LOCATION"],
                    text_hint=locs[0].name,
                )
            )

    # --- PROCESS / PROGRESS (decision only; Phase 4/8 render later) ---
    if signals["has_process"] and (
        purpose_l == "process"
        or intent_role == "process"
        or intent_graphic in ("diagram", "process")
    ):
        # Prefer a simple callout/label over a full process diagram unless AI insists.
        if intent_conf >= 0.7 and intent_role == "process":
            candidates.append(
                GraphicDirective(
                    decision="PROCESS",
                    role="PROCESS",
                    reason="Narration explains a system/process",
                    confidence=intent_conf,
                    priority=_PRIORITY["PROCESS"],
                    text_hint=_short_phrase(text, 36),
                )
            )
        elif signals["has_progress"]:
            candidates.append(
                GraphicDirective(
                    decision="PROGRESS",
                    role="PROGRESS",
                    reason="Narration describes progress/completion",
                    confidence=0.6,
                    priority=_PRIORITY["PROGRESS"],
                    text_hint=_short_phrase(text, 28),
                )
            )

    # --- TIMELINE chronology ---
    if signals["has_chronology"] and (
        purpose_l == "timeline"
        or intent_role == "historical"
    ):
        candidates.append(
            GraphicDirective(
                decision="TIMELINE",
                role="TIMELINE",
                reason="Chronology is editorially important",
                confidence=max(0.55, intent_conf),
                priority=_PRIORITY["TIMELINE"],
                text_hint=_short_phrase(text, 40),
            )
        )

    # --- QUOTE / CHAPTER / EMPHASIS from intent ---
    if intent_conf >= 0.55:
        if intent_text == "quote":
            candidates.append(
                GraphicDirective(
                    decision="QUOTE",
                    role="QUOTE",
                    reason="Intent: quote treatment",
                    confidence=intent_conf,
                    priority=_PRIORITY["QUOTE"],
                    text_hint=_quote_phrase(text),
                )
            )
        elif intent_text == "chapter":
            candidates.append(
                GraphicDirective(
                    decision="CHAPTER",
                    role="CHAPTER",
                    reason="Intent: chapter card",
                    confidence=intent_conf,
                    priority=_PRIORITY["CHAPTER"],
                    text_hint=_short_phrase(text, 28),
                )
            )
        elif intent_text in ("emphasis", "callout") and not candidates:
            candidates.append(
                GraphicDirective(
                    decision="CALLOUT",
                    role="CALLOUT",
                    reason="Intent: emphasis/callout",
                    confidence=intent_conf,
                    priority=_PRIORITY["CALLOUT"],
                    text_hint=_short_phrase(text, 32),
                )
            )
        elif intent_text == "caption" and not existing_smart_text:
            candidates.append(
                GraphicDirective(
                    decision="TEXT",
                    role="CAPTION",
                    reason="Intent: caption",
                    confidence=intent_conf,
                    priority=_PRIORITY["TEXT"],
                    text_hint=_short_phrase(text, 48),
                )
            )

    # --- Reveal ---
    if intent is not None and getattr(intent, "reveal", False) and not candidates:
        candidates.append(
            GraphicDirective(
                decision="TEXT",
                role="EMPHASIS",
                reason="Reveal beat — restrained emphasis text",
                confidence=max(0.5, intent_conf),
                priority=_PRIORITY["TEXT"],
                text_hint=_short_phrase(text, 28),
            )
        )

    if not candidates:
        return []

    # Prefer simplest: sort by priority then confidence.
    candidates.sort(key=lambda c: (c.priority, -c.confidence))

    # If Smart Editing already punches text, skip generic TEXT/EMPHASIS/CALLOUT
    # but keep STATISTIC / LOWER_THIRD / LOCATION / MAP.
    keep_always = {"STATISTIC", "LOWER_THIRD", "LOCATION", "MAP", "PROCESS", "TIMELINE", "CHART", "PROGRESS"}
    if existing_smart_text:
        candidates = [
            c for c in candidates
            if c.decision in keep_always or c.role in keep_always
        ]

    # At most one primary graphic per beat (plus optional location under stat).
    if not candidates:
        return []
    primary = candidates[0]
    out = [primary]
    for c in candidates[1:]:
        if primary.decision == "STATISTIC" and c.decision == "LOCATION":
            out.append(c)
            break
        if primary.decision == "LOWER_THIRD" and c.decision == "LOCATION":
            out.append(c)
            break
    return out


def decide_for_scenes(
    scenes: Sequence[Any],
    *,
    intents: Optional[Mapping[str, Any]] = None,
    design: DocumentaryDesignSystem | None = None,
) -> dict[str, List[GraphicDirective]]:
    design = design or get_design_system()
    intents = intents or {}
    out: dict[str, List[GraphicDirective]] = {}
    recent: List[float] = []
    for scene in scenes:
        sn = str(getattr(scene, "scene_number", "") or "")
        intent = intents.get(sn) or intents.get(sn.zfill(3))
        narration = str(getattr(scene, "narration_excerpt", "") or "")
        purpose = str(getattr(scene, "purpose", "context") or "context")
        directives = decide_graphic(
            narration=narration,
            scene_number=sn,
            purpose=purpose,
            intent=intent,
            design=design,
        )
        # Density: skip low-priority if too many graphics recently.
        start = float(getattr(scene, "start", 0.0) or 0.0)
        recent = [t for t in recent if start - t < 30.0]
        if len(recent) >= design.max_graphics_per_30s:
            directives = [d for d in directives if d.priority <= 3 and d.confidence >= 0.75]
        if directives and recent and (start - recent[-1]) < design.min_gap_between_graphics:
            if directives[0].priority >= 4:
                directives = []
        if directives:
            recent.append(start)
        out[sn] = directives
    return out


def _intent_text_strategy(intent: Any) -> str:
    if intent is None:
        return "none"
    if isinstance(intent, dict):
        return str(intent.get("text_strategy") or "none").lower()
    return str(getattr(intent, "text_strategy", "none") or "none").lower()


def _intent_graphic_strategy(intent: Any) -> str:
    if intent is None:
        return "none"
    if isinstance(intent, dict):
        return str(intent.get("graphic_strategy") or "none").lower()
    return str(getattr(intent, "graphic_strategy", "none") or "none").lower()


def _intent_visual_role(intent: Any) -> str:
    if intent is None:
        return ""
    if isinstance(intent, dict):
        return str(intent.get("visual_role") or "").lower()
    return str(getattr(intent, "visual_role", "") or "").lower()


def _intent_confidence(intent: Any) -> float:
    if intent is None:
        return 0.0
    if isinstance(intent, dict):
        try:
            return float(intent.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(getattr(intent, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _short_phrase(text: str, max_chars: int) -> str:
    words = (text or "").strip().split()
    if not words:
        return ""
    # Prefer a short clause before punctuation.
    first = text.split(".")[0].split("?")[0].strip()
    if len(first) <= max_chars:
        return first
    out: List[str] = []
    for w in words:
        trial = (" ".join(out + [w])).strip()
        if len(trial) > max_chars:
            break
        out.append(w)
    return " ".join(out).rstrip(",;:")


def _quote_phrase(text: str) -> str:
    m = __import__("re").search(r'[“"]([^”"]+)[”"]', text or "")
    if m:
        return m.group(1).strip()[:56]
    return _short_phrase(text, 48)
