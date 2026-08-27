"""Deterministic SceneVisualProfile — no new AI dependency."""

from __future__ import annotations

import dataclasses
import re
from typing import List, Optional

from providers.base import SceneRow

from .schema import ResolvedStyle, VideoStyle
from .visual_roles import VISUAL_ROLES

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-2][0-9])\b")
_EVIDENCE = re.compile(
    r"\b(evidence|document|manuscript|archive|photograph|inscription|records?|"
    r"discovered|excavation|footage|mission|launch|landing|data shows?)\b",
    re.I,
)
_HISTORICAL = re.compile(
    r"\b(war|empire|ancient|century|president|depression|apollo|nasa|mission|"
    r"revolution|treaty|dynasty|archaeolog)\b",
    re.I,
)
_PROCESS = re.compile(
    r"\b(how|process|step|mechanism|works?|because|explained|demonstrat)\b",
    re.I,
)
_SCALE = re.compile(
    r"\b(scale|compared|versus|larger|smaller|billions|light[- ]years|size of)\b",
    re.I,
)
_MAP = re.compile(r"\b(map|border|region|territory|continent)\b", re.I)
_PERSON = re.compile(
    r"\b(he|she|they|scientist|astronaut|president|leader|named|called)\b",
    re.I,
)
_ABSTRACT = re.compile(
    r"\b(concept|idea|metaphor|philosoph|meaning|imagine|social jet lag|"
    r"biological clock|consciousness)\b",
    re.I,
)
_ATMOS = re.compile(
    r"\b(feel|mood|atmosphere|quiet|dark|silence|beauty|awe|wonder)\b",
    re.I,
)
_SPACE = re.compile(
    r"\b(planet|galaxy|orbit|spacecraft|rocket|nasa|telescope|pluto|mars|moon)\b",
    re.I,
)
_OCEAN = re.compile(r"\b(ocean|marine|sea|coral|whale|submarine|hydrothermal|deep sea)\b", re.I)
_CRIME = re.compile(r"\b(crime|murder|investigat|detective|evidence|suspect|forensic)\b", re.I)


@dataclasses.dataclass
class SceneVisualProfile:
    topic: str = ""
    entities: List[str] = dataclasses.field(default_factory=list)
    location: str = ""
    time_period: str = ""
    event: str = ""
    concept: str = ""
    visual_role: str = "establishing"
    evidence_level: str = "medium"
    style_requirements: List[str] = dataclasses.field(default_factory=list)
    search_terms: List[str] = dataclasses.field(default_factory=list)
    avoid_terms: List[str] = dataclasses.field(default_factory=list)
    preferred_sources: List[str] = dataclasses.field(default_factory=list)
    preferred_media_type: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _years(text: str) -> List[str]:
    return _YEAR.findall(text or "")


def _detect_role(text: str) -> str:
    if _SPACE.search(text):
        if _SCALE.search(text):
            return "scale"
        return "scientific_visualization"
    if _EVIDENCE.search(text) and _HISTORICAL.search(text):
        return "archival_evidence"
    if _MAP.search(text):
        return "map"
    if _SCALE.search(text):
        return "scale"
    if _PROCESS.search(text):
        return "process"
    if _PERSON.search(text) and _HISTORICAL.search(text):
        return "character"
    if _CRIME.search(text):
        return "event"
    if _OCEAN.search(text):
        return "location"
    if _ABSTRACT.search(text):
        return "abstract"
    if _ATMOS.search(text) and not _EVIDENCE.search(text):
        return "atmosphere"
    if _HISTORICAL.search(text):
        return "event"
    return "establishing"


def _evidence_level(text: str, role: str) -> str:
    if role in ("archival_evidence", "document", "data", "event") and _EVIDENCE.search(text):
        return "high"
    if _HISTORICAL.search(text) or _CRIME.search(text):
        return "high"
    if role in ("abstract", "atmosphere", "reaction"):
        return "low"
    if _PROCESS.search(text) or role == "scientific_visualization":
        return "medium"
    return "medium"


def _extract_entities(text: str) -> List[str]:
    caps = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", text or "")
    out: List[str] = []
    for c in caps:
        if c.lower() in {"the", "and", "but", "for"}:
            continue
        if c not in out:
            out.append(c)
    return out[:6]


def build_scene_visual_profile(
    scene: SceneRow,
    resolved: Optional[ResolvedStyle] = None,
) -> SceneVisualProfile:
    narration = (scene.script_segment or "").strip()
    prompt = (scene.prompt or scene.stock or "").strip()
    visual = (getattr(scene, "visual_description", None) or prompt or "").strip()
    text = f"{narration} {visual} {prompt}".strip()
    role = _detect_role(text)
    if role not in VISUAL_ROLES:
        role = "establishing"
    years = _years(text)
    time_period = years[0] if years else ""
    entities = _extract_entities(narration)
    topic = entities[0] if entities else (prompt.split()[0] if prompt else "")

    queries: List[str] = []
    for q in (getattr(scene, "search_queries", None) or []):
        q = str(q).strip()
        if q and q not in queries:
            queries.append(q)
    if prompt and "||" in prompt:
        for p in prompt.split("||"):
            p = p.strip()
            if p and p not in queries:
                queries.append(p)
    elif prompt and prompt not in queries:
        queries.append(prompt)
    elif visual and visual not in queries:
        queries.append(visual)

    avoid: List[str] = []
    preferred_sources: List[str] = []
    style_reqs: List[str] = []
    if resolved and resolved.style:
        style: VideoStyle = resolved.style
        sg = style.search_guidance
        avoid = list(sg.avoid_terms or [])
        preferred_sources = list(style.source_preferences.ranked or style.assets.preferred or [])
        if sg.evidence_bias == "high" or style.selection_rules.prefer_evidence_when_factual:
            style_reqs.append("evidence_first")
        for term in sg.prefer_terms or []:
            if term not in queries:
                queries.append(term)

    profile = SceneVisualProfile(
        topic=topic,
        entities=entities,
        time_period=time_period,
        event=topic if role in ("event", "archival_evidence") else "",
        concept=visual[:120] if role == "abstract" else "",
        visual_role=role,
        evidence_level=_evidence_level(text, role),
        style_requirements=style_reqs,
        search_terms=queries,
        avoid_terms=avoid,
        preferred_sources=preferred_sources,
        preferred_media_type=scene.asset_type or "",
    )
    return profile
