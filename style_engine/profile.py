"""ContentProfile — internal multi-signal understanding for AUTO style scoring."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Lexical families — soft signals; never sole decision.
_HIST = re.compile(
    r"\b(histor(?:y|ical)|ancient|empire|roman|greek|medieval|dynasty|war|wwii|"
    r"archaeology|civilization|manuscript|archival|centur(?:y|ies)|colonial|pharaoh|"
    r"kingdom|treaty|revolution|artifact|chronicle|reign)\b",
    re.I,
)
_SPACE = re.compile(
    r"\b(space|cosmos|cosmic|galax(?:y|ies)|nebulae?|planets?|astronom(?:y|ical)|astronaut|nasa|"
    r"orbit(?:al|s)?|black\s*holes?|universe|solar|mars|jupiter|saturn|telescope|"
    r"astrophysics|stellar|interstellar|spacecraft|stars?)\b",
    re.I,
)
_SCI = re.compile(
    r"\b(science|scientific|physics|chemistry|biology|quantum|molecule|"
    r"experiment|hypothesis|data|research|laboratory|theory)\b",
    re.I,
)
_EVID = re.compile(
    r"\b(evidence|documents?|maps?|records?|archives?|sources?|proof|"
    r"discovered|excavation|inscription|photograph)\b",
    re.I,
)
_CHRON = re.compile(
    r"\b(in\s+\d{3,4}|by\s+\d{3,4}|during the|years? of|timeline|"
    r"century|decade|era|period|before|after the|billions of years)\b",
    re.I,
)
_EXPLAIN = re.compile(
    r"\b(imagine|explained|explainer|how to|here's why|let's|you will|"
    r"step by step|tips|hack|secret|in this video|waking up|discovering|"
    r"faceless|subscribe|top \d|number \d)\b",
    re.I,
)
_CINE = re.compile(
    r"\b(cinematic|immersive|landscape|wildlife|portrait|atmosphere|"
    r"disappearance|climate|arctic|ocean|forest|investigat)\b",
    re.I,
)
_EMOTE = re.compile(
    r"\b(feel|emotion|hope|fear|tragic|beauty|awe|wonder|loss|love|"
    r"devastat|transform|changed everything)\b",
    re.I,
)
_ABSTRACT = re.compile(
    r"\b(concept|idea|theory|metaphor|imagine|visualize|abstract|"
    r"compared with|scale|ratio|process|system)\b",
    re.I,
)
_HOOKY = re.compile(
    r"\b(imagine|secret|shocking|you won't|what if|changed everything|"
    r"nobody|hidden|revealed)\b",
    re.I,
)


@dataclass
class ContentProfile:
    domain: str = "general"
    narrative_type: str = "documentary"
    presentation: str = "narration_led"
    emotional_intensity: float = 0.4
    educational_density: float = 0.4
    scientific_density: float = 0.2
    historical_density: float = 0.2
    cinematic_potential: float = 0.45
    abstract_concept_density: float = 0.3
    visualization_need: float = 0.4
    evidence_density: float = 0.3
    hook_intensity: float = 0.45
    chronology_density: float = 0.2
    explainer_density: float = 0.25
    astronomy_density: float = 0.1
    archival_visual_need: float = 0.2
    word_count: int = 0
    scene_count: int = 0
    source_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ContentProfile":
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def vector(self) -> Dict[str, float]:
        return {
            "historical_density": self.historical_density,
            "evidence_density": self.evidence_density,
            "archival_visual_need": self.archival_visual_need,
            "chronology_density": self.chronology_density,
            "cinematic_potential": self.cinematic_potential,
            "emotional_intensity": self.emotional_intensity,
            "educational_density": self.educational_density,
            "scientific_density": self.scientific_density,
            "astronomy_density": self.astronomy_density,
            "abstract_concept_density": self.abstract_concept_density,
            "visualization_need": self.visualization_need,
            "explainer_density": self.explainer_density,
            "hook_intensity": self.hook_intensity,
            "narration_led": 1.0 if self.presentation == "narration_led" else 0.4,
        }


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _density(text: str, pattern: re.Pattern, scale: float = 8.0) -> float:
    if not text:
        return 0.0
    hits = len(pattern.findall(text))
    words = max(1, len(re.findall(r"\w+", text)))
    return _clamp(hits / max(1.0, words / scale))


def _gather_text(
    script: str = "",
    visual_plan: Any = None,
    rows: Optional[List[dict]] = None,
    title: str = "",
) -> Tuple[str, str, int]:
    parts: List[str] = []
    if title:
        parts.append(title)
    if script:
        parts.append(script)
    topic = ""
    scene_n = 0
    if visual_plan is not None:
        topic = str(getattr(visual_plan, "topic", "") or "")
        if not topic and isinstance(visual_plan, dict):
            topic = str(visual_plan.get("topic") or "")
        parts.append(topic)
        scenes = getattr(visual_plan, "scenes", None)
        if scenes is None and isinstance(visual_plan, dict):
            scenes = visual_plan.get("scenes")
        scenes = list(scenes or [])
        scene_n = max(scene_n, len(scenes))
        for s in scenes[:60]:
            if hasattr(s, "visual_goal"):
                parts.append(str(getattr(s, "visual_goal", "") or ""))
                parts.append(str(getattr(s, "visual_description", "") or ""))
                parts.append(str(getattr(s, "visual_treatment", "") or ""))
                parts.append(str(getattr(s, "narration", "") or "")[:200])
            elif isinstance(s, dict):
                parts.append(str(s.get("visual_goal") or ""))
                parts.append(str(s.get("visual_description") or ""))
                parts.append(str(s.get("visual_treatment") or ""))
                parts.append(str(s.get("narration") or s.get("script_segment") or "")[:200])
    for r in list(rows or [])[:100]:
        parts.append(str(r.get("script_segment") or "")[:200])
        parts.append(str(r.get("prompt") or r.get("stock") or "")[:100])
        scene_n = max(scene_n, 1)
    if rows:
        scene_n = max(scene_n, len(rows))
    blob = " ".join(parts)
    return blob, topic, scene_n


def content_source_hash(
    script: str = "",
    visual_plan: Any = None,
    rows: Optional[List[dict]] = None,
    title: str = "",
) -> str:
    blob, topic, n = _gather_text(script, visual_plan, rows, title)
    payload = {
        "t": topic[:200],
        "n": n,
        "h": hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def build_content_profile(
    *,
    script: str = "",
    visual_plan: Any = None,
    rows: Optional[List[dict]] = None,
    title: str = "",
) -> ContentProfile:
    blob, topic, scene_n = _gather_text(script, visual_plan, rows, title)
    words = len(re.findall(r"\w+", blob))
    hist = _density(blob, _HIST, 6.0)
    space = _density(blob, _SPACE, 5.0)
    sci = _density(blob, _SCI, 7.0)
    evid = _density(blob, _EVID, 6.0)
    chron = _density(blob, _CHRON, 7.0)
    expl = _density(blob, _EXPLAIN, 5.0)
    cine = _density(blob, _CINE, 7.0)
    emote = _density(blob, _EMOTE, 8.0)
    abstr = _density(blob, _ABSTRACT, 6.0)
    hook = _density(blob[:800] if blob else "", _HOOKY, 4.0)

    # Structural signals
    avg_len = words / max(1, scene_n) if scene_n else words
    if scene_n >= 12 and avg_len <= 45:
        expl = _clamp(expl + 0.18)
    if chron >= 0.15 and hist >= 0.1:
        hist = _clamp(hist + 0.12)
        evid = _clamp(evid + 0.08)
    if space >= 0.12:
        sci = _clamp(sci + 0.1)
    # Opening-hook bias for first ~120 words
    opening = " ".join((blob or "").split()[:120])
    if _EXPLAIN.search(opening) and _HOOKY.search(opening):
        expl = _clamp(expl + 0.15)
        hook = _clamp(hook + 0.12)
    if title:
        th = _density(title, _HIST, 2.0)
        ts = _density(title, _SPACE, 2.0)
        te = _density(title, _EXPLAIN, 2.0)
        tc = _density(title, _CINE, 2.0)
        hist = _clamp(hist + th * 0.2)
        space = _clamp(space + ts * 0.2)
        expl = _clamp(expl + te * 0.2)
        cine = _clamp(cine + tc * 0.2)

    # Domain pick — multi-signal, not single keyword
    # "NASA" alone is weak; require astronomy density or supporting sci+abstr.
    space_domain = space * 0.55 + sci * 0.2 + abstr * 0.15
    if space < 0.08 and "nasa" in blob.lower():
        space_domain *= 0.55
    domain_scores = {
        "history": hist * 0.55 + evid * 0.25 + chron * 0.2,
        "space": space_domain,
        "science": sci * 0.55 + abstr * 0.25 + evid * 0.2,
        "explainer": expl * 0.6 + hook * 0.25 + abstr * 0.15,
        "nature_doc": cine * 0.5 + emote * 0.3 + sci * 0.2,
        "general": 0.15,
    }
    domain = max(domain_scores, key=domain_scores.get)

    presentation = "narration_led"
    if cine >= 0.25 and expl < 0.2:
        narrative = "cinematic_documentary"
    elif hist >= 0.25 or domain == "history":
        narrative = "documentary"
    elif expl >= 0.28 or domain == "explainer":
        narrative = "explainer"
    else:
        narrative = "documentary"

    archival = _clamp(hist * 0.5 + evid * 0.4 + chron * 0.2)
    viz = _clamp(abstr * 0.45 + expl * 0.35 + space * 0.25 + sci * 0.2)

    return ContentProfile(
        domain=domain,
        narrative_type=narrative,
        presentation=presentation,
        emotional_intensity=_clamp(emote * 0.7 + hook * 0.3 + 0.15),
        educational_density=_clamp(expl * 0.4 + evid * 0.3 + sci * 0.3 + 0.1),
        scientific_density=_clamp(sci * 0.6 + space * 0.35),
        historical_density=_clamp(hist),
        cinematic_potential=_clamp(cine * 0.55 + emote * 0.25 + 0.2),
        abstract_concept_density=_clamp(abstr),
        visualization_need=_clamp(viz),
        evidence_density=_clamp(evid),
        hook_intensity=_clamp(hook * 0.7 + expl * 0.2 + 0.15),
        chronology_density=_clamp(chron),
        explainer_density=_clamp(expl),
        astronomy_density=_clamp(space),
        archival_visual_need=_clamp(archival),
        word_count=words,
        scene_count=scene_n,
        source_hash=content_source_hash(script, visual_plan, rows, title),
    )


# Default compatibility weights per built-in style (overridden by JSON intelligence.weights).
DEFAULT_STYLE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "history_documentary": {
        "historical_density": 0.35,
        "evidence_density": 0.25,
        "archival_visual_need": 0.2,
        "chronology_density": 0.12,
        "educational_density": 0.05,
        "cinematic_potential": 0.03,
    },
    "premium_documentary": {
        "cinematic_potential": 0.32,
        "emotional_intensity": 0.22,
        "educational_density": 0.12,
        "evidence_density": 0.1,
        "visualization_need": 0.08,
        "scientific_density": 0.08,
        "historical_density": 0.08,
    },
    "ai_narration": {
        "explainer_density": 0.3,
        "narration_led": 0.18,
        "hook_intensity": 0.18,
        "visualization_need": 0.16,
        "abstract_concept_density": 0.1,
        "educational_density": 0.08,
    },
    "space_documentary": {
        "astronomy_density": 0.4,
        "scientific_density": 0.22,
        "abstract_concept_density": 0.12,
        "visualization_need": 0.12,
        "cinematic_potential": 0.1,
        "emotional_intensity": 0.04,
    },
}


def score_styles(
    profile: ContentProfile,
    *,
    style_weights: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[Tuple[str, float]]:
    """Return [(style_id, score 0..1), ...] sorted descending.

    First entry's score is the AUTO confidence (relative margin + absolute fit).
    Remaining entries keep raw compatibility scores.
    """
    vec = profile.vector()
    weights_map = dict(DEFAULT_STYLE_WEIGHTS)
    if style_weights:
        for sid, w in style_weights.items():
            weights_map[sid] = dict(w)
    scored: List[Tuple[str, float]] = []
    for sid, weights in weights_map.items():
        total_w = sum(abs(float(v)) for v in weights.values()) or 1.0
        raw = sum(float(weights.get(k, 0.0)) * float(vec.get(k, 0.0)) for k in weights)
        prior = 0.08 if sid == "premium_documentary" else 0.04
        # Domain soft boost (never sole decision)
        if profile.domain == "history" and sid == "history_documentary":
            raw += 0.06 * total_w
        elif profile.domain == "space" and sid == "space_documentary":
            raw += 0.06 * total_w
        elif profile.domain == "explainer" and sid == "ai_narration":
            raw += 0.06 * total_w
        elif profile.domain == "nature_doc" and sid == "premium_documentary":
            raw += 0.05 * total_w
        score = _clamp(raw / total_w + prior)
        scored.append((sid, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    if scored:
        top = scored[0][1]
        second = scored[1][1] if len(scored) > 1 else 0.0
        margin = top - second
        conf = _clamp(0.42 + top * 0.4 + margin * 1.6)
        # Ambiguous: keep confidence moderate but stable
        if margin < 0.06:
            conf = _clamp(0.45 + top * 0.25)
        scored[0] = (scored[0][0], conf)
    return scored


def reason_for_style(style_id: str, profile: ContentProfile) -> str:
    reasons = {
        "history_documentary": (
            "Historical narrative with strong archival and evidence-driven content."
            if profile.historical_density >= 0.25
            else "Evidence- and chronology-leaning documentary storytelling."
        ),
        "premium_documentary": (
            "Cinematic factual storytelling with emotional and visual depth."
            if profile.cinematic_potential >= 0.35
            else "Measured documentary narration suited to premium composition."
        ),
        "ai_narration": (
            "Narration-led explainer with high visual-support and hook energy."
            if profile.explainer_density >= 0.25
            else "Faceless / concept-driven narration that needs active visual explanation."
        ),
        "space_documentary": (
            "Astronomy and cosmic-scale scientific storytelling."
            if profile.astronomy_density >= 0.2
            else "Science visualization with scale and awe potential."
        ),
    }
    return reasons.get(style_id, "Best available match for this content profile.")


def load_cached_profile(state_dir: Optional[Path], source_hash: str) -> Optional[ContentProfile]:
    if state_dir is None:
        return None
    path = Path(state_dir) / "content_profile.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if str(data.get("source_hash") or "") != source_hash:
            return None
        return ContentProfile.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_cached_profile(state_dir: Optional[Path], profile: ContentProfile) -> None:
    if state_dir is None:
        return
    path = Path(state_dir) / "content_profile.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile.to_dict(), indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
