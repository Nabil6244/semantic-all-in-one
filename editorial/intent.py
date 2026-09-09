"""EditorialIntent — AI/deterministic soft guidance for the editing machinery.

Maps onto existing Purpose / VisualRole / pacing / reveal / attention concepts.
Never contains clip ranges, FFmpeg filters, or absolute timeline placements.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional

# Allowed enums (normalized lowercase)
VISUAL_ROLES = frozenset(
    {
        "evidence",
        "explanation",
        "process",
        "geography",
        "person",
        "object",
        "scale",
        "comparison",
        "historical",
        "atmosphere",
        "reveal",
        "consequence",
        "cause",
        "effect",
        "cause_effect",
        "data",
        "document",
        "metaphor",
        "context",
        "claim_evidence",
        "statistic",
    }
)

VISUAL_STRATEGIES = frozenset(
    {
        "single",
        "process_sequence",
        "cause_effect",
        "evidence",
        "atmosphere",
        "reveal",
        "comparison",
        "scale_progression",
        "illustration",
    }
)

SHOT_STRATEGIES = frozenset({"auto", "single", "multi", "dual"})
EVIDENCE_LEVELS = frozenset({"none", "low", "medium", "high"})
PACING_VALUES = frozenset(
    {"hold", "normal", "build", "fast", "impact", "reflective", "reset"}
)
TEXT_STRATEGIES = frozenset(
    {
        "none",
        "caption",
        "emphasis",
        "statistic",
        "name",
        "location",
        "quote",
        "callout",
        "chapter",
        "data_graphic",
        "lower_third",
        "label",
        "title",
    }
)
GRAPHIC_STRATEGIES = frozenset(
    {
        "none",
        "chart",
        "map",
        "document",
        "data_graphic",
        "label",
        "statistic",
        "process",
        "diagram",
        "timeline",
        "comparison",
        "progress",
        "callout",
        "lower_third",
    }
)
SOUND_STRATEGIES = frozenset(
    {
        "none",
        "ambience",
        "action_sfx",
        "transition_sfx",
        "impact",
        "silence",
        "music_lift",
        "music_drop",
        "music_hold",
    }
)
EMOTIONAL_STATES = frozenset(
    {
        "curiosity",
        "understanding",
        "anticipation",
        "tension",
        "surprise",
        "impact",
        "emotional_weight",
        "relief",
        "reset",
        "new_curiosity",
    }
)
REVEAL_PHASES = frozenset(
    {"none", "setup", "build", "withhold", "reveal", "emphasize"}
)

# Map AI visual_role → existing planner VisualRole / purpose hints
ROLE_TO_PLANNER: Dict[str, str] = {
    "evidence": "claim_evidence",
    "claim_evidence": "claim_evidence",
    "document": "claim_evidence",
    "data": "statistic",
    "statistic": "statistic",
    "explanation": "explanation",
    "process": "process",
    "geography": "geography",
    "person": "person",
    "object": "object",
    "scale": "scale",
    "comparison": "comparison",
    "historical": "historical",
    "atmosphere": "atmosphere",
    "reveal": "reveal",
    "consequence": "cause_effect",
    "cause": "cause_effect",
    "effect": "cause_effect",
    "cause_effect": "cause_effect",
    "metaphor": "metaphor",
    "context": "context",
}

ROLE_TO_PURPOSE: Dict[str, str] = {
    "evidence": "evidence",
    "claim_evidence": "evidence",
    "document": "evidence",
    "data": "evidence",
    "statistic": "evidence",
    "explanation": "explanation",
    "process": "process",
    "geography": "location",
    "person": "character",
    "scale": "scale",
    "comparison": "comparison",
    "reveal": "reveal",
    "atmosphere": "emotion",
    "historical": "context",
    "cause_effect": "explanation",
    "consequence": "explanation",
}

PACING_TO_BIAS: Dict[str, str] = {
    "hold": "slow",
    "reflective": "slow",
    "reset": "slow",
    "normal": "normal",
    "build": "normal",
    "fast": "fast",
    "impact": "fast",
}

REASONER_VERSION = "1"


def _norm_enum(raw: object, allowed: frozenset, default: str) -> str:
    key = str(raw or default).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "causeeffect": "cause_effect",
        "cause_and_effect": "cause_effect",
        "b_roll": "atmosphere",
        "broll": "atmosphere",
        "multi_shot": "multi",
        "dual_asset": "dual",
        "no_text": "none",
        "no_sound": "none",
        "sfx": "action_sfx",
        "whoosh": "transition_sfx",
        "hit": "impact",
        "stat": "statistic",
        "numbers": "statistic",
        "chart": "data_graphic",
    }
    key = aliases.get(key, key)
    return key if key in allowed else default


def _norm_confidence(raw: object) -> float:
    try:
        v = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0 and v <= 100.0:
        v = v / 100.0
    return round(min(1.0, max(0.0, v)), 3)


@dataclasses.dataclass
class EditorialIntent:
    """Soft editorial guidance for one beat (AI or deterministic)."""

    scene_number: str
    visual_role: str = "context"
    visual_strategy: str = "single"
    evidence_level: str = "low"
    shot_strategy: str = "auto"
    pacing: str = "normal"
    reveal: bool = False
    reveal_phase: str = "none"
    text_strategy: str = "none"
    graphic_strategy: str = "none"
    sound_strategy: str = "none"
    emotional_state: str = "understanding"
    preferred_asset_ids: List[str] = dataclasses.field(default_factory=list)
    primary_claim: str = ""
    viewer_goal: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    source: str = "deterministic"  # ai | deterministic | fallback

    def planner_visual_role(self) -> str:
        return ROLE_TO_PLANNER.get(self.visual_role, self.visual_role or "context")

    def purpose_hint(self) -> Optional[str]:
        return ROLE_TO_PURPOSE.get(self.visual_role)

    def pacing_bias(self) -> str:
        return PACING_TO_BIAS.get(self.pacing, "normal")

    def prefer_dual(self) -> bool:
        return self.shot_strategy == "dual" or self.visual_strategy in (
            "process_sequence",
            "cause_effect",
            "scale_progression",
        )

    def prefer_multi(self) -> bool:
        return self.shot_strategy == "multi" or self.prefer_dual()

    def prefer_single(self) -> bool:
        return self.shot_strategy == "single" or self.pacing in ("hold", "reflective")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EditorialIntent":
        if not isinstance(data, dict):
            return cls(scene_number="")
        prefs = data.get("preferred_asset_ids") or data.get("preferred_assets") or []
        if not isinstance(prefs, list):
            prefs = []
        prefs_out = [str(p) for p in prefs if str(p).strip()][:6]
        reveal = bool(data.get("reveal"))
        phase = _norm_enum(data.get("reveal_phase"), REVEAL_PHASES, "none")
        if reveal and phase == "none":
            phase = "reveal"
        return cls(
            scene_number=str(data.get("scene_number") or data.get("beat") or ""),
            visual_role=_norm_enum(data.get("visual_role"), VISUAL_ROLES, "context"),
            visual_strategy=_norm_enum(
                data.get("visual_strategy"), VISUAL_STRATEGIES, "single"
            ),
            evidence_level=_norm_enum(
                data.get("evidence_level"), EVIDENCE_LEVELS, "low"
            ),
            shot_strategy=_norm_enum(data.get("shot_strategy"), SHOT_STRATEGIES, "auto"),
            pacing=_norm_enum(data.get("pacing"), PACING_VALUES, "normal"),
            reveal=reveal,
            reveal_phase=phase,
            text_strategy=_norm_enum(data.get("text_strategy"), TEXT_STRATEGIES, "none"),
            graphic_strategy=_norm_enum(
                data.get("graphic_strategy"), GRAPHIC_STRATEGIES, "none"
            ),
            sound_strategy=_norm_enum(
                data.get("sound_strategy"), SOUND_STRATEGIES, "none"
            ),
            emotional_state=_norm_enum(
                data.get("emotional_state"), EMOTIONAL_STATES, "understanding"
            ),
            preferred_asset_ids=prefs_out,
            primary_claim=str(data.get("primary_claim") or "")[:240],
            viewer_goal=str(data.get("viewer_goal") or "")[:240],
            confidence=_norm_confidence(data.get("confidence")),
            reasoning=str(data.get("reasoning") or data.get("reason") or "")[:400],
            source=str(data.get("source") or "ai").strip().lower() or "ai",
        )


# Confidence thresholds for applying AI guidance
CONF_HIGH = 0.75
CONF_MEDIUM = 0.55
CONF_LOW = 0.40
