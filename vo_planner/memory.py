"""Visual memory — rolling record of what has already been shown."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .schema import CoverageUnit, VisualMemoryEntry

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "over",
    "under", "about", "when", "what", "which", "their", "there", "have",
    "been", "were", "will", "would", "could", "should", "than", "then",
})

_SCALE_LADDER = ["extreme_wide", "wide", "medium", "close", "detail"]
_CAMERA_OPTS = ["eye_level", "high", "low", "oblique", "pov", "overhead"]
_MOTION_OPTS = ["static", "slow_pan", "push_in", "pull_out", "orbit", "handheld", "ken_burns"]
_STRATEGY_OPTS = ["single_shot", "multi_shot", "hold", "punch_in", "image_motion", "transition"]


def _tokens(text: str) -> Set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOP and len(t) > 2}


class VisualMemory:
    """Tracks subjects, locations, concepts, grammar across the whole video."""

    def __init__(self) -> None:
        self.entries: List[VisualMemoryEntry] = []
        self._subjects: List[str] = []
        self._locations: List[str] = []
        self._concepts: List[str] = []
        self._categories: List[str] = []
        self._scales: List[str] = []
        self._cameras: List[str] = []
        self._motions: List[str] = []
        self._purposes: List[str] = []
        self._stages: List[str] = []
        self._strategies: List[str] = []
        self._token_bags: List[Set[str]] = []

    def remember(self, entry: VisualMemoryEntry, *, strategy: str = "") -> None:
        self.entries.append(entry)
        if entry.subject:
            self._subjects.append(entry.subject.lower())
        if entry.location:
            self._locations.append(entry.location.lower())
        if entry.concept:
            self._concepts.append(entry.concept.lower())
        if entry.category:
            self._categories.append(entry.category.lower())
        if entry.shot_scale:
            self._scales.append(entry.shot_scale)
        if entry.camera:
            self._cameras.append(entry.camera)
        if entry.motion:
            self._motions.append(entry.motion)
        if entry.purpose:
            self._purposes.append(entry.purpose)
        if entry.progression_stage:
            self._stages.append(entry.progression_stage)
        if strategy:
            self._strategies.append(strategy)
        self._token_bags.append(set(entry.tokens) if entry.tokens else _tokens(
            f"{entry.subject} {entry.location} {entry.concept} {entry.purpose}"
        ))

    def semantic_repetition(self, subject: str, concept: str, purpose: str) -> float:
        toks = _tokens(f"{subject} {concept} {purpose}")
        if not toks or not self._token_bags:
            return 0.0
        best = 0.0
        for bag in self._token_bags[-12:]:
            if not bag:
                continue
            j = len(toks & bag) / len(toks | bag)
            best = max(best, j)
        subj = (subject or "").lower()
        if subj and subj in self._subjects[-8:]:
            best = max(best, 0.55)
        return round(min(1.0, best), 3)

    def visual_repetition(
        self,
        scale: str,
        camera: str,
        motion: str,
        stage: str,
        *,
        strategy: str = "",
    ) -> float:
        score = 0.0
        recent = 4
        if scale and self._scales[-recent:].count(scale) >= 2:
            score += 0.35
        if camera and self._cameras[-recent:].count(camera) >= 2:
            score += 0.25
        if motion and self._motions[-recent:].count(motion) >= 2:
            score += 0.2
        if stage and self._stages[-recent:].count(stage) >= 2:
            score += 0.25
        if strategy and self._strategies[-recent:].count(strategy) >= 2:
            score += 0.2
        # Identical grammar triple
        if (
            scale
            and camera
            and motion
            and any(
                e.shot_scale == scale and e.camera == camera and e.motion == motion
                for e in self.entries[-6:]
            )
        ):
            score = max(score, 0.75)
        return round(min(1.0, score), 3)

    def last_entry(self) -> Optional[VisualMemoryEntry]:
        return self.entries[-1] if self.entries else None

    def avoid_list(self, *, limit: int = 10) -> List[str]:
        avoids: List[str] = []
        for label, values in (
            ("subject", self._subjects),
            ("location", self._locations),
            ("scale", self._scales),
            ("camera", self._cameras),
            ("motion", self._motions),
            ("stage", self._stages),
            ("strategy", self._strategies),
        ):
            if not values:
                continue
            last = values[-1]
            if values[-4:].count(last) >= 2:
                avoids.append(f"repeat_{label}:{last}")
        for subj in self._subjects:
            if self._subjects.count(subj) >= 3 and f"overused_subject:{subj}" not in avoids:
                avoids.append(f"overused_subject:{subj}")
        for loc in self._locations:
            if self._locations.count(loc) >= 3 and f"overused_location:{loc}" not in avoids:
                avoids.append(f"overused_location:{loc}")
        return avoids[:limit]

    def intentional_callback_ok(
        self,
        subject: str,
        *,
        narrative_importance: float,
        purpose_changed: bool = False,
        min_gap: int = 4,
    ) -> bool:
        """Allow callback when editorially justified (importance + gap, or purpose shift)."""
        subj = (subject or "").lower()
        if not subj:
            return False
        idxs = [i for i, s in enumerate(self._subjects) if s == subj]
        if not idxs:
            return False
        gap = len(self._subjects) - idxs[-1]
        if narrative_importance >= 0.7 and gap >= min_gap:
            return True
        # Purpose change can justify a callback with a slightly smaller gap
        if purpose_changed and narrative_importance >= 0.55 and gap >= max(2, min_gap - 1):
            return True
        return False

    def evolve_grammar(
        self,
        scale: str,
        camera: str,
        motion: str,
        *,
        strategy: str = "",
        force: bool = False,
    ) -> Tuple[str, str, str, str]:
        """When repeating a subject/look, evolve scale/camera/motion/strategy."""
        rep = self.visual_repetition(scale, camera, motion, "", strategy=strategy)
        if not force and rep < 0.45:
            return scale, camera, motion, strategy

        def pick(current: str, options: List[str], recent: List[str]) -> str:
            for cand in options:
                if cand != current and recent[-3:].count(cand) == 0:
                    return cand
            for cand in options:
                if cand != current:
                    return cand
            return current

        new_scale = pick(scale, _SCALE_LADDER, self._scales)
        new_cam = pick(camera, _CAMERA_OPTS, self._cameras)
        new_motion = pick(motion, _MOTION_OPTS, self._motions)
        new_strat = strategy
        if strategy and self._strategies[-3:].count(strategy) >= 2:
            new_strat = pick(strategy, _STRATEGY_OPTS, self._strategies)
        return new_scale, new_cam, new_motion, new_strat

    def summary(self) -> Dict:
        def top(values: List[str], n: int = 8) -> List[str]:
            seen: Dict[str, int] = {}
            for v in values:
                seen[v] = seen.get(v, 0) + 1
            return [k for k, _ in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

        return {
            "units_recorded": len(self.entries),
            "subjects": top(self._subjects),
            "locations": top(self._locations),
            "concepts": top(self._concepts),
            "categories": top(self._categories),
            "shot_scales": top(self._scales),
            "cameras": top(self._cameras),
            "motions": top(self._motions),
            "purposes": top(self._purposes),
            "stages": top(self._stages),
            "strategies": top(self._strategies),
        }


def entry_from_unit(
    unit: CoverageUnit,
    *,
    location: str = "",
    concept: str = "",
    category: str = "",
) -> VisualMemoryEntry:
    loc = location or unit.location or ""
    return VisualMemoryEntry(
        beat_id=unit.beat_id,
        unit_id=unit.unit_id,
        subject=unit.subject,
        location=loc,
        concept=concept or unit.evidence_type,
        category=category or unit.visual_purpose,
        shot_scale=unit.shot_scale,
        camera=unit.camera,
        motion=unit.motion,
        purpose=unit.visual_purpose,
        progression_stage=unit.progression_stage,
        tokens=sorted(_tokens(
            f"{unit.subject} {loc} {unit.visual_purpose} {unit.evidence_type} {unit.meaningful_action}"
        )),
    )
