"""Style Intelligence 3.0 — search strategies + style-aware candidate scoring."""

from __future__ import annotations

import dataclasses
import re
from typing import Dict, List, Optional, Set

from providers.base import SceneRow
from providers.media_clip.queries import expanded_media_queries, unique_media_queries
from providers.media_quality.scoring import ScoreBreakdown, selection_score
from providers.stock.query import build_queries, clean_query

from .schema import ResolvedStyle, VideoStyle
from .visual_profile import SceneVisualProfile, build_scene_visual_profile

_TOKEN = re.compile(r"[a-z0-9]+")

_ROLE_HINTS = {
    "archival_evidence": ("archival", "document", "photograph", "newspaper", "manuscript", "footage"),
    "event": ("event", "footage", "news", "protest", "battle", "launch", "landing"),
    "establishing": ("establishing", "aerial", "wide", "landscape", "cityscape"),
    "person": ("portrait", "person", "face", "speaker", "interview"),
    "character": ("portrait", "leader", "scientist", "astronaut", "president"),
    "location": ("location", "street", "city", "region", "country"),
    "object": ("object", "artifact", "machine", "device", "tool"),
    "process": ("process", "diagram", "animation", "how", "step", "mechanism"),
    "mechanism": ("mechanism", "engine", "gear", "circuit", "internal"),
    "map": ("map", "border", "territory", "atlas"),
    "timeline": ("timeline", "chronology", "era", "century"),
    "comparison": ("comparison", "versus", "scale", "side by side"),
    "scale": ("scale", "size", "comparison", "planet", "galaxy"),
    "data": ("chart", "graph", "data", "statistics"),
    "document": ("document", "letter", "newspaper", "manuscript", "record"),
    "quote": ("quote", "text", "headline", "caption"),
    "atmosphere": ("atmosphere", "mood", "ambient", "broll", "cinematic"),
    "abstract": ("abstract", "concept", "visualization", "metaphor"),
    "reaction": ("reaction", "crowd", "audience", "emotion"),
    "scientific_visualization": ("simulation", "render", "telescope", "nasa", "mission", "spacecraft"),
    "transition": ("transition", "montage", "timelapse"),
}

_GENERIC_STOCK = frozenset({
    "businessman", "businesswoman", "office", "corporate", "generic", "stock",
    "broll", "background", "abstract background", "people walking",
})

_PROVIDER_ALIASES = {
    "pexels": "pexels",
    "pixabay": "pixabay",
    "openverse": "openverse",
    "stock": "pexels",
    "archive": "archive",
    "internet_archive": "archive",
    "nasa": "nasa",
    "youtube": "youtube",
    "flow": "flow",
}


@dataclasses.dataclass
class SelectionHistory:
    used_asset_ids: Set[str] = dataclasses.field(default_factory=set)
    provider_counts: Dict[str, int] = dataclasses.field(default_factory=dict)
    concept_tokens: Set[str] = dataclasses.field(default_factory=set)
    subject_tokens: Set[str] = dataclasses.field(default_factory=set)

    def record(self, *, provider: str, asset_id: str, title: str = "", description: str = "") -> None:
        if asset_id:
            self.used_asset_ids.add(asset_id)
        key = _PROVIDER_ALIASES.get((provider or "").lower(), (provider or "").lower())
        if key:
            self.provider_counts[key] = self.provider_counts.get(key, 0) + 1
        blob = f"{title} {description}".lower()
        for tok in _TOKEN.findall(blob):
            if len(tok) >= 4:
                self.concept_tokens.add(tok)
        for tok in _TOKEN.findall(title.lower()):
            if len(tok) >= 5:
                self.subject_tokens.add(tok)


@dataclasses.dataclass
class SelectionContext:
    profile: SceneVisualProfile
    resolved: Optional[ResolvedStyle] = None
    history: Optional[SelectionHistory] = None
    manual_authority: bool = False


def _tokens(text: str) -> Set[str]:
    return set(_TOKEN.findall((text or "").lower()))


def scene_has_manual_authority(scene: SceneRow) -> bool:
    """Manual CSV rows with explicit asset_type + prompt — do not rewrite queries."""
    if not (scene.asset_type or "").strip():
        return False
    if scene.search_queries:
        return False
    if getattr(scene, "visual_description", ""):
        return False
    return bool((scene.prompt or scene.stock or "").strip())


def build_selection_context(
    scene: SceneRow,
    resolved: Optional[ResolvedStyle] = None,
    history: Optional[SelectionHistory] = None,
) -> SelectionContext:
    manual = scene_has_manual_authority(scene)
    profile = build_scene_visual_profile(scene, resolved)
    return SelectionContext(
        profile=profile,
        resolved=resolved,
        history=history,
        manual_authority=manual,
    )


def _role_suffix(role: str, style: Optional[VideoStyle]) -> str:
    if role == "archival_evidence":
        return "archival footage"
    if role == "document":
        return "historical document"
    if role == "map":
        return "map"
    if role == "scientific_visualization":
        return "NASA mission footage" if style and style.id == "space_documentary" else "scientific footage"
    if role == "scale":
        return "scale comparison"
    if role == "process":
        return "process diagram"
    if role == "event":
        return "historical footage"
    if role == "atmosphere":
        return "cinematic atmosphere"
    return ""


def expand_search_strategies(
    scene: SceneRow,
    profile: SceneVisualProfile,
    style: Optional[VideoStyle] = None,
    *,
    manual: bool = False,
) -> List[str]:
    """Multiple query strategies — metadata search only, no downloads."""
    if manual:
        base = unique_media_queries(scene) or profile.search_terms
        return base[:5]

    seen: Set[str] = set()
    out: List[str] = []

    def add(raw: str) -> None:
        q = clean_query(raw)
        if not q:
            return
        key = q.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(q)

    narration = (scene.script_segment or "").strip()
    entities = profile.entities or []
    years = profile.time_period

    for term in profile.search_terms:
        add(term)
        for variant in build_queries(term):
            add(variant)

    for ent in entities[:3]:
        add(ent)
        if years:
            add(f"{ent} {years}")
        suffix = _role_suffix(profile.visual_role, style)
        if suffix:
            add(f"{ent} {suffix}")
        if profile.visual_role == "archival_evidence":
            add(f"{ent} archival photograph")
            add(f"{ent} historical footage")

    if narration and len(out) < 4:
        words = [w for w in _tokens(narration) if len(w) > 3][:6]
        if words:
            add(" ".join(words[:4]))
            if years:
                add(f"{' '.join(words[:3])} {years}")

    if style and style.search_guidance.query_expansion:
        for term in style.search_guidance.prefer_terms[:4]:
            add(term)
            if entities:
                add(f"{entities[0]} {term}")

    if profile.visual_role == "scientific_visualization" and "nasa" not in seen:
        for ent in entities[:2]:
            add(f"{ent} NASA" if ent else "NASA mission footage")

    for base in expanded_media_queries(scene):
        add(base)

    return out[:12]


def smart_media_queries(
    scene: SceneRow,
    resolved: Optional[ResolvedStyle] = None,
    *,
    manual: bool | None = None,
) -> List[str]:
    manual = scene_has_manual_authority(scene) if manual is None else manual
    profile = build_scene_visual_profile(scene, resolved)
    style = resolved.style if resolved else None
    queries = expand_search_strategies(scene, profile, style, manual=manual)
    return queries or expanded_media_queries(scene) or unique_media_queries(scene)


def visual_role_score(role: str, candidate_text: str, style: Optional[VideoStyle]) -> float:
    hints = _ROLE_HINTS.get(role, ())
    hay = candidate_text.lower()
    hits = sum(1 for h in hints if h in hay)
    base = min(1.0, hits * 0.22) if hints else 0.15
    if style and style.visual_roles.weights:
        weight = float(style.visual_roles.weights.get(role, 0.0))
        base += weight * 0.35
        for avoid in style.visual_roles.avoid:
            if avoid.replace("_", " ") in hay or avoid in hay:
                base -= 0.25
    return max(0.0, min(1.0, base))


def style_fit_score(
    candidate_text: str,
    style: Optional[VideoStyle],
    profile: SceneVisualProfile,
) -> float:
    if style is None:
        return 0.0
    hay = candidate_text.lower()
    score = 0.0
    for term in style.search_guidance.prefer_terms:
        if term.lower() in hay:
            score += 0.12
    for term in style.search_guidance.avoid_terms:
        if term.lower() in hay:
            score -= 0.2
    for term in profile.avoid_terms:
        if term.lower() in hay:
            score -= 0.15
    if style.selection_rules.avoid_generic_when_specific and profile.entities:
        generic_hits = sum(1 for g in _GENERIC_STOCK if g in hay)
        entity_hits = sum(1 for e in profile.entities if e.lower() in hay)
        if generic_hits and not entity_hits:
            score -= 0.35
    bias = style.search_guidance.evidence_bias
    if profile.evidence_level == "high" and bias == "high":
        if any(w in hay for w in ("archival", "document", "footage", "photograph", "mission", "map")):
            score += 0.2
    elif profile.evidence_level == "low" and bias == "low":
        if any(w in hay for w in ("atmosphere", "cinematic", "ambient", "abstract")):
            score += 0.15
    return max(-0.5, min(1.0, score))


def source_preference_score(provider: str, style: Optional[VideoStyle], profile: SceneVisualProfile) -> float:
    ranked = []
    if style:
        ranked = [str(x).lower() for x in (style.source_preferences.ranked or style.assets.preferred or [])]
    if profile.preferred_sources:
        ranked = ranked or [str(x).lower() for x in profile.preferred_sources]
    if not ranked:
        return 0.05
    key = _PROVIDER_ALIASES.get((provider or "").lower(), (provider or "").lower())
    avoid = {str(x).lower() for x in (style.source_preferences.avoid if style else [])}
    if key in avoid:
        return -0.2
    try:
        idx = ranked.index(key)
    except ValueError:
        for alias, canonical in _PROVIDER_ALIASES.items():
            if canonical == key and alias in ranked:
                idx = ranked.index(alias)
                break
        else:
            return 0.02
    return 0.08 + 0.06 * (len(ranked) - idx) / max(len(ranked), 1)


def evidence_level_score(candidate_text: str, profile: SceneVisualProfile, style: Optional[VideoStyle]) -> float:
    hay = candidate_text.lower()
    high_markers = ("footage", "document", "photograph", "archive", "mission", "map", "newspaper", "manuscript")
    low_markers = ("broll", "generic", "abstract background", "stock video", "placeholder")
    high = any(m in hay for m in high_markers)
    low = any(m in hay for m in low_markers)
    if profile.evidence_level == "high":
        if high:
            return 0.35
        if low:
            return -0.25
    elif profile.evidence_level == "low":
        if low and not high:
            return 0.1
    return 0.05 if high else 0.0


def repetition_penalties(
    *,
    candidate_text: str,
    asset_id: str,
    provider: str,
    history: Optional[SelectionHistory],
    style: Optional[VideoStyle],
) -> tuple[float, float, float]:
    """Returns (duplicate, provider_rep, concept_rep)."""
    dup = 0.0
    prov = 0.0
    concept = 0.0
    if history is None:
        return dup, prov, concept
    rules = style.selection_rules if style else None
    rep = rules.repetition_penalty if rules else 0.35
    prov_pen = rules.provider_repetition_penalty if rules else 0.25
    concept_pen = rules.concept_repetition_penalty if rules else 0.4

    if asset_id and asset_id in history.used_asset_ids:
        dup = 5.0
    key = _PROVIDER_ALIASES.get((provider or "").lower(), (provider or "").lower())
    count = history.provider_counts.get(key, 0)
    if count > 0:
        prov = min(prov_pen * count, 1.2)
    cand_tokens = _tokens(candidate_text)
    overlap = len(cand_tokens & history.concept_tokens)
    if overlap >= 3:
        concept = min(concept_pen * (overlap / 5.0), 1.0)
    subj_overlap = len(cand_tokens & history.subject_tokens)
    if subj_overlap >= 2:
        concept = max(concept, min(concept_pen * 0.8, 0.8))
    _ = rep  # duplicate uses hard reject via selection_score
    return dup, prov, concept


def smart_selection_score(
    *,
    query: str,
    script_segment: str = "",
    visual_description: str = "",
    title: str = "",
    description: str = "",
    extra_text: str = "",
    width: int = 0,
    height: int = 0,
    download_url: str = "",
    provider: str = "",
    media_type: str = "video",
    duration: Optional[float] = None,
    used_asset_ids: Optional[Set[str]] = None,
    asset_id: str = "",
    provider_use_counts: Optional[dict[str, int]] = None,
    is_archival: Optional[bool] = None,
    context: Optional[SelectionContext] = None,
    required_duration: Optional[float] = None,
) -> ScoreBreakdown:
    base = selection_score(
        query=query,
        script_segment=script_segment,
        visual_description=visual_description,
        title=title,
        description=description,
        extra_text=extra_text,
        width=width,
        height=height,
        download_url=download_url,
        provider=provider,
        media_type=media_type,
        duration=duration,
        used_asset_ids=used_asset_ids,
        asset_id=asset_id,
        provider_use_counts=provider_use_counts,
        is_archival=is_archival,
    )
    if base.reject_reason or context is None:
        return base

    profile = context.profile
    style = context.resolved.style if context.resolved else None
    blob = " ".join([title, description, extra_text, visual_description])
    role_s = visual_role_score(profile.visual_role, blob, style)
    style_s = style_fit_score(blob, style, profile)
    source_s = source_preference_score(provider, style, profile)
    evidence_s = evidence_level_score(blob, profile, style)
    _, prov_rep, concept_rep = repetition_penalties(
        candidate_text=blob,
        asset_id=asset_id,
        provider=provider,
        history=context.history,
        style=style,
    )

    base.visual_role_score = role_s
    base.style_fit_score = style_s
    base.source_score = source_s
    base.evidence_score = evidence_s
    base.concept_repetition_penalty = concept_rep
    base.provider_repetition_penalty = max(base.provider_repetition_penalty, prov_rep)
    if required_duration and duration:
        base.duration_fit_score = duration_fit_score(required_duration, duration, allow_pairing=True)
    return base


def duration_fit_score(
    required_duration: Optional[float],
    candidate_duration: Optional[float],
    *,
    allow_pairing: bool = True,
) -> float:
    """Coverage-aware duration signal — complements relevance, never dominates."""
    req = float(required_duration or 0)
    dur = float(candidate_duration or 0)
    if req <= 0 or dur <= 0:
        return 0.0
    if dur >= req * 0.92:
        return 0.35
    if dur >= req * 0.75:
        return 0.2
    if dur >= req * 0.55:
        return 0.08
    if allow_pairing and dur >= req * 0.35:
        return 0.02  # short but pairable
    return -0.08
