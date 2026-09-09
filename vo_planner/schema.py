"""VO-Aware Visual Planner — compact data models (no LLM)."""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

VO_PLANNER_VERSION = 3

COVERAGE_STRATEGIES = frozenset({
    "single_shot",
    "multi_shot",
    "hold",
    "punch_in",
    "image_motion",
    "transition",
})

PROGRESSION_STAGES = (
    "environment",
    "scale",
    "object",
    "person",
    "action",
    "mechanism",
    "consequence",
    "reveal",
)

SHOT_SCALES = ("extreme_wide", "wide", "medium", "close", "detail")
CAMERA_ANGLES = ("eye_level", "high", "low", "overhead", "pov", "oblique")
MOTION_TYPES = ("static", "slow_pan", "push_in", "pull_out", "orbit", "handheld", "ken_burns")
EVIDENCE_TYPES = (
    "establishing",
    "documentary",
    "process",
    "person",
    "object",
    "data",
    "archive",
    "metaphor",
    "consequence",
    "reveal",
)


@dataclasses.dataclass
class AssetMixPreferences:
    """Allocation targets/preferences — not editorial requirements.

    Quality protection always wins: never force a weak visual just to hit %.
    """

    video_pct: float = 60.0
    image_pct: float = 40.0
    stock_video_pct: float = 35.0
    flow_video_pct: float = 15.0
    youtube_video_pct: float = 10.0
    flow_image_pct: float = 15.0
    stock_image_pct: float = 25.0
    # Soft floors/ceilings (0 = unset)
    min_stock_video: int = 0
    max_flow_video: int = 0
    quality_protection: bool = True

    def fingerprint(self) -> dict:
        return dataclasses.asdict(self)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "AssetMixPreferences":
        if not isinstance(data, dict):
            return cls()
        fields = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: data[k] for k in fields if k in data}
        return cls(**kwargs)

    def normalized(self) -> "AssetMixPreferences":
        """Clamp percentages into sensible ranges without inventing content."""
        def clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
            try:
                return max(lo, min(hi, float(v)))
            except (TypeError, ValueError):
                return lo

        return AssetMixPreferences(
            video_pct=clamp(self.video_pct),
            image_pct=clamp(self.image_pct),
            stock_video_pct=clamp(self.stock_video_pct),
            flow_video_pct=clamp(self.flow_video_pct),
            youtube_video_pct=clamp(self.youtube_video_pct),
            flow_image_pct=clamp(self.flow_image_pct),
            stock_image_pct=clamp(self.stock_image_pct),
            min_stock_video=max(0, int(self.min_stock_video or 0)),
            max_flow_video=max(0, int(self.max_flow_video or 0)),
            quality_protection=bool(self.quality_protection),
        )


@dataclasses.dataclass
class VOWord:
    word: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"word": self.word, "start": round(self.start, 3), "end": round(self.end, 3)}


@dataclasses.dataclass
class VOSentence:
    text: str
    start: float
    end: float
    word_count: int
    pause_before: float = 0.0
    pause_after: float = 0.0
    speech_density: float = 0.0  # words per second within sentence span

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "word_count": self.word_count,
            "pause_before": round(self.pause_before, 3),
            "pause_after": round(self.pause_after, 3),
            "speech_density": round(self.speech_density, 3),
        }


@dataclasses.dataclass
class VOAnalysis:
    """Exact VO timing authority derived from Whisper word timestamps."""

    audio_path: str
    audio_duration: float
    words: List[VOWord]
    sentences: List[VOSentence]
    pauses: List[Dict[str, float]]  # {start, end, duration}
    mean_speech_density: float
    whisper_model: str = ""

    def to_dict(self) -> dict:
        return {
            "audio_path": self.audio_path,
            "audio_duration": round(self.audio_duration, 3),
            "word_count": len(self.words),
            "sentence_count": len(self.sentences),
            "mean_speech_density": round(self.mean_speech_density, 3),
            "whisper_model": self.whisper_model,
            "sentences": [s.to_dict() for s in self.sentences],
            "pauses": [
                {
                    "start": round(float(p.get("start", 0)), 3),
                    "end": round(float(p.get("end", 0)), 3),
                    "duration": round(float(p.get("duration", 0)), 3),
                }
                for p in self.pauses
            ],
            # Compact: omit full word list from handoff; keep counts above.
        }

    def words_as_tuples(self) -> List[tuple]:
        return [(w.word, w.start, w.end) for w in self.words]


@dataclasses.dataclass
class AlignedBeat:
    """Semantic beat from Script Analyzer, timed to actual VO."""

    beat_id: int
    narration: str
    start: float
    end: float
    align_confidence: float
    visual_goal: str = ""
    visual_description: str = ""
    importance: str = "medium"
    asset_type: str = ""
    provider_preference: str = ""
    search_queries: List[str] = dataclasses.field(default_factory=list)
    fallbacks: List[str] = dataclasses.field(default_factory=list)
    visual_treatment: str = ""
    transition: str = "cut"
    minimum_quality: str = "1080p"
    # Derived
    narrative_importance: float = 0.5
    visual_opportunity: float = 0.5
    speech_density: float = 0.0
    pause_before: float = 0.0
    pause_after: float = 0.0
    # Mid-beat pause starts (absolute seconds) — natural change opportunities
    internal_pauses: List[float] = dataclasses.field(default_factory=list)
    opportunity_tags: List[str] = dataclasses.field(default_factory=list)
    idea_count: int = 1

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "narration": self.narration,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "align_confidence": round(self.align_confidence, 3),
            "importance": self.importance,
            "narrative_importance": round(self.narrative_importance, 3),
            "visual_opportunity": round(self.visual_opportunity, 3),
            "speech_density": round(self.speech_density, 3),
            "visual_goal": self.visual_goal,
            "pause_before": round(self.pause_before, 3),
            "pause_after": round(self.pause_after, 3),
            "internal_pauses": [round(p, 3) for p in self.internal_pauses],
            "opportunity_tags": list(self.opportunity_tags),
            "idea_count": self.idea_count,
        }


@dataclasses.dataclass
class CoverageUnit:
    unit_id: str
    beat_id: int
    start: float
    end: float
    strategy: str  # single_shot | multi_shot | hold | punch_in | image_motion | transition
    visual_purpose: str
    evidence_type: str
    subject: str
    shot_scale: str
    camera: str
    motion: str
    specificity: float
    visual_importance: float
    novelty: float
    repetition_risk: float
    generic_risk: float
    strong_opportunity: bool
    quality_target: str
    change_trigger: str
    previous_relationship: str = ""
    next_relationship: str = ""
    avoid: List[str] = dataclasses.field(default_factory=list)
    progression_stage: str = "environment"
    intentional_callback: bool = False
    opportunity_tags: List[str] = dataclasses.field(default_factory=list)
    quality_requirements: Dict[str, Any] = dataclasses.field(default_factory=dict)
    location: str = ""
    meaningful_action: str = ""
    editability: str = "medium"

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "beat_id": self.beat_id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "strategy": self.strategy,
            "visual_purpose": self.visual_purpose,
            "evidence_type": self.evidence_type,
            "subject": self.subject,
            "location": self.location,
            "shot_scale": self.shot_scale,
            "camera": self.camera,
            "motion": self.motion,
            "meaningful_action": self.meaningful_action,
            "specificity": round(self.specificity, 3),
            "visual_importance": round(self.visual_importance, 3),
            "novelty": round(self.novelty, 3),
            "repetition_risk": round(self.repetition_risk, 3),
            "generic_risk": round(self.generic_risk, 3),
            "strong_opportunity": self.strong_opportunity,
            "quality_target": self.quality_target,
            "quality_requirements": dict(self.quality_requirements),
            "editability": self.editability,
            "change_trigger": self.change_trigger,
            "previous_relationship": self.previous_relationship,
            "next_relationship": self.next_relationship,
            "avoid": list(self.avoid),
            "progression_stage": self.progression_stage,
            "intentional_callback": self.intentional_callback,
            "opportunity_tags": list(self.opportunity_tags),
        }


@dataclasses.dataclass
class CoverageContract:
    beat_id: int
    total_duration: float
    required_units: int
    unit_durations: List[float]
    unit_purposes: List[str]
    change_triggers: List[str]
    previous_visual_relationship: str
    next_visual_relationship: str
    avoid: List[str]
    strategy: str

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "total_duration": round(self.total_duration, 3),
            "required_units": self.required_units,
            "unit_durations": [round(d, 3) for d in self.unit_durations],
            "unit_purposes": list(self.unit_purposes),
            "change_triggers": list(self.change_triggers),
            "previous_visual_relationship": self.previous_visual_relationship,
            "next_visual_relationship": self.next_visual_relationship,
            "avoid": list(self.avoid),
            "strategy": self.strategy,
        }


@dataclasses.dataclass
class VisualMemoryEntry:
    beat_id: int
    unit_id: str
    subject: str
    location: str
    concept: str
    category: str
    shot_scale: str
    camera: str
    motion: str
    purpose: str
    progression_stage: str
    tokens: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class QCIssue:
    code: str
    severity: str  # error | warning | info
    message: str
    beat_id: Optional[int] = None
    unit_id: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class VoAwarePlan:
    """Compact VO-aware plan for Claude handoff + pipeline bridge."""

    topic: str
    planner_version: int
    audio_duration: float
    beats: List[AlignedBeat]
    units: List[CoverageUnit]
    contracts: List[CoverageContract]
    memory_summary: Dict[str, Any]
    progression: List[str]
    qc_issues: List[QCIssue]
    asset_mix: AssetMixPreferences
    vo_summary: Dict[str, Any]
    warnings: List[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "planner": "vo_aware",
            "planner_version": self.planner_version,
            "topic": self.topic,
            "audio_duration": round(self.audio_duration, 3),
            "vo_summary": self.vo_summary,
            "beats": [b.to_dict() for b in self.beats],
            "coverage_units": [u.to_dict() for u in self.units],
            "coverage_contracts": [c.to_dict() for c in self.contracts],
            "memory_summary": self.memory_summary,
            "progression": list(self.progression),
            "qc_issues": [i.to_dict() for i in self.qc_issues],
            "asset_mix_preferences": self.asset_mix.to_dict(),
            "warnings": list(self.warnings),
        }

    def compact_handoff(self) -> dict:
        """Minimal JSON Claude needs — timing, coverage, constraints, not prose."""
        return {
            "planner": "vo_aware",
            "v": self.planner_version,
            "topic": self.topic,
            "audio_s": round(self.audio_duration, 2),
            "mix": {
                **self.asset_mix.to_dict(),
                "targets_only": True,
                "quality_protection": True,
            },
            "qc": [
                {"code": i.code, "sev": i.severity, "msg": i.message, "beat": i.beat_id}
                for i in self.qc_issues
                if i.severity in ("error", "warning")
            ],
            "beats": [
                {
                    "id": b.beat_id,
                    "t": [round(b.start, 2), round(b.end, 2)],
                    "dur": round(b.duration, 2),
                    "narr": b.narration,
                    "goal": b.visual_goal,
                    "pref": b.provider_preference or b.asset_type or None,
                    "narr_imp": round(b.narrative_importance, 2),
                    "vis_opp": round(b.visual_opportunity, 2),
                    "tags": list(b.opportunity_tags),
                    "ideas": b.idea_count,
                }
                for b in self.beats
            ],
            "units": [
                {
                    "id": u.unit_id,
                    "beat": u.beat_id,
                    "t": [round(u.start, 2), round(u.end, 2)],
                    "dur": round(u.duration, 2),
                    "what": u.subject,
                    "where": u.location or None,
                    "why": u.visual_purpose,
                    "action": u.meaningful_action or None,
                    "strat": u.strategy,
                    "evidence": u.evidence_type,
                    "scale": u.shot_scale,
                    "cam": u.camera,
                    "motion": u.motion,
                    "stage": u.progression_stage,
                    "importance": round(u.visual_importance, 2),
                    "novelty": round(u.novelty, 2),
                    "generic_risk": round(u.generic_risk, 2),
                    "rep_risk": round(u.repetition_risk, 2),
                    "strong": u.strong_opportunity,
                    "quality": u.quality_target,
                    "req": u.quality_requirements,
                    "editability": u.editability,
                    "trigger": u.change_trigger,
                    "prev": u.previous_relationship,
                    "next": u.next_relationship,
                    "avoid": u.avoid,
                    "callback": u.intentional_callback,
                    "tags": list(u.opportunity_tags),
                }
                for u in self.units
            ],
            "contracts": [c.to_dict() for c in self.contracts],
            "progression": list(self.progression),
            "memory": self.memory_summary,
            "shown": {
                "subjects": list((self.memory_summary or {}).get("subjects") or [])[:10],
                "locations": list((self.memory_summary or {}).get("locations") or [])[:8],
                "scales": list((self.memory_summary or {}).get("shot_scales") or [])[:6],
                "stages": list((self.memory_summary or {}).get("stages") or [])[:8],
            },
            "avoid_global": sorted(
                {
                    a
                    for u in self.units
                    for a in u.avoid
                }
            )[:40],
        }
