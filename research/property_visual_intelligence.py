"""Property Visual Intelligence — genuinely new signals only.

This module deliberately does NOT re-implement anything the existing
Property Video pipeline already owns:

  * beat splitting / BeatCategory / VisualScope / VisualIntent   -> property_script.py
  * property-type / location / fact-visual-hint tables           -> property_ontology.py
  * source routing seam (preferred/fallback source per beat)     -> property_script._sources_for()
  * Flow budget, credit cap, image/video split                   -> visual_allocation/budget.py
  * candidate quality/relevance scoring                          -> providers/media_quality/scoring.py
  * style-aware candidate scoring / diversity history             -> style_engine/visual_selection.py

What it adds, that nothing else in the codebase currently answers:

  1. `classify_visual_purpose()` — WHY a beat needs a visual, not just WHAT
     kind of shot (VisualScope already answers WHAT).
  2. `semantic_categories_for()` — fine-grained room/feature tags (kitchen,
     garage, pool, golf_course, ...) that VisualScope's broader buckets
     (PROPERTY_INTERIOR, STRUCTURE, RECREATION, ...) don't distinguish.
  3. `property_media_matches_beat()` — does this LISTING'S media actually
     depict what this beat is about, not just "does the listing have media
     at all". This is the beat-level evidence gate consumed by
     property_script._sources_for().
  4. `analyze_property_story()` — narrative synthesis across the whole
     narration (hero features, story angle, visual gaps) that no per-beat
     function produces.
  5. `fact_visual_mappings()` — thin pass-through exposing which verified
     facts have a visual implication, for reporting/QA use.

Everything here is a pure function of (beats, research_result, facts) —
deterministic, no ML, no new provider, no new scoring system. Every signal
this module produces is consumed by an EXISTING seam (VisualIntent fields,
_sources_for(), _asset_type_for(), _enrich_intent()'s flow prompt, or
visual_description text feeding the existing scorer) — nothing here selects
a final candidate or gates Flow on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from research.models import ResearchResult
from research.property_script import BeatCategory, PropertyBeat, VisualScope

# ---------------------------------------------------------------------------
# 1. Visual purpose — WHY does this beat need a visual.
# ---------------------------------------------------------------------------

PURPOSE_LOCATION_CONTEXT = "location_context"
PURPOSE_PROPERTY_PROOF = "property_proof"
PURPOSE_FEATURE_PROOF = "feature_proof"
PURPOSE_ROOM_PROOF = "room_proof"
PURPOSE_SPECIFICATION_PROOF = "specification_proof"
PURPOSE_CONDITION_PROOF = "condition_proof"
PURPOSE_LIFESTYLE = "lifestyle"
PURPOSE_SCENIC_CONTEXT = "scenic_context"
PURPOSE_COMPARISON = "comparison"
PURPOSE_TRANSITION = "transition"
PURPOSE_ATMOSPHERE = "atmosphere"

_COMPARISON_CUES = re.compile(
    r"\b(compared\s+to|versus|vs\.?|other\s+(?:homes|listings|properties)|"
    r"similar\s+(?:homes|properties)|unlike\s+(?:most|other))\b", re.I,
)
_CONDITION_CUES = re.compile(
    r"\b(recently\s+(?:renovated|updated|remodeled)|move[-\s]?in\s+ready|"
    r"needs?\s+(?:work|updating|tlc)|fixer[-\s]?upper|newly\s+built|"
    r"original\s+condition|well[-\s]?maintained)\b", re.I,
)

_FEATURE_SCOPES = frozenset({
    VisualScope.STRUCTURE, VisualScope.PROPERTY_EXTERIOR, VisualScope.WATER,
    VisualScope.APPROACH, VisualScope.RECREATION, VisualScope.CONSTRUCTION_DETAIL,
})


def classify_visual_purpose(beat: PropertyBeat) -> str:
    """WHY this beat needs a visual — the signal VisualScope/BeatCategory
    don't carry on their own. Purely a function of the existing
    classification (category + scope) plus the beat's own narration text."""
    intent = beat.intent
    scope = intent.scope if intent is not None else None
    text = beat.narration or ""

    if scope == VisualScope.LOCATION:
        return PURPOSE_LOCATION_CONTEXT

    if _CONDITION_CUES.search(text):
        return PURPOSE_CONDITION_PROOF

    if beat.category == BeatCategory.FACTUAL_PROPERTY_CONTEXT:
        return PURPOSE_PROPERTY_PROOF if scope == VisualScope.LISTING else PURPOSE_SPECIFICATION_PROOF

    if beat.category == BeatCategory.PROPERTY_SPECIFIC:
        if scope == VisualScope.PROPERTY_INTERIOR:
            return PURPOSE_ROOM_PROOF
        if scope == VisualScope.LISTING:
            return PURPOSE_PROPERTY_PROOF
        return PURPOSE_FEATURE_PROOF

    if beat.category == BeatCategory.CINEMATIC_ATMOSPHERIC:
        return PURPOSE_LIFESTYLE if scope == VisualScope.LIFESTYLE else PURPOSE_ATMOSPHERE

    # GENERIC_CONTEXT
    if _COMPARISON_CUES.search(text):
        return PURPOSE_COMPARISON
    if len(text.split()) <= 3:
        return PURPOSE_TRANSITION
    return PURPOSE_SCENIC_CONTEXT


# ---------------------------------------------------------------------------
# 2. Secondary semantic tags — fine-grained room/feature words VisualScope's
#    broader buckets don't distinguish. Deliberately short: only tags that
#    the existing coarse role_detail vocabulary (interior/exterior/structure/
#    recreation/...) collapses together and that a real edit would treat as
#    different shots.
# ---------------------------------------------------------------------------

_SEMANTIC_TAG_CUES: Tuple[Tuple[str, str], ...] = (
    ("kitchen", r"\bkitchens?\b"),
    ("bedroom", r"\bbedrooms?\b"),
    ("bathroom", r"\bbathrooms?\b"),
    ("garage", r"\bgarages?\b"),
    ("basement", r"\bbasements?\b"),
    ("pool", r"\bpools?\b"),
    ("hot_tub", r"\bhot\s?tubs?|jacuzz"),
    ("golf_course", r"\bgolf\s?courses?|golf\s?frontage"),
    ("fireplace", r"\bfireplaces?\b"),
    ("dining_room", r"\bdining\s?rooms?\b"),
    ("living_room", r"\bliving\s?rooms?|great\s?rooms?\b"),
    ("deck_patio", r"\bdecks?|patios?|verandas?\b"),
)


def semantic_categories_for(text: str) -> List[str]:
    """Fine-grained tags found in `text`, in priority order. Additive to
    VisualScope, never a replacement for it — a kitchen beat is still
    scope=PROPERTY_INTERIOR; "kitchen" is the extra tag that lets media
    matching and Flow prompts be specific about *which* interior."""
    lowered = (text or "").lower()
    return [tag for tag, pattern in _SEMANTIC_TAG_CUES if re.search(pattern, lowered)]


# ---------------------------------------------------------------------------
# 3. Property-media beat matching — does the listing's own media plausibly
#    depict what THIS beat is about, not just "does the listing have media".
#    Consumed by property_script._sources_for() as the gate on preferring
#    SOURCE_RESEARCH; the existing ResearchAssetProvider ranking still picks
#    the best candidate once routed there.
# ---------------------------------------------------------------------------

# Only scopes with a clear, existing role_detail vocabulary (see
# research/engine/app/domains/real_estate.py::_ROLE_PATTERNS) are gated.
# Scopes with no clean mapping (LAND, GENERIC, LIFESTYLE, LISTING) are left
# permissive — unknown is never treated as "doesn't match", matching the
# existing ResearchAssetProvider convention (_tier_rank/_role_rank rank
# unknown mid, never reject).
_SCOPE_TO_ROLE_DETAILS: Dict[VisualScope, frozenset] = {
    VisualScope.PROPERTY_INTERIOR: frozenset({"interior"}),
    VisualScope.PROPERTY_EXTERIOR: frozenset({"exterior", "structure"}),
    VisualScope.STRUCTURE: frozenset({"structure", "exterior"}),
    VisualScope.CONSTRUCTION_DETAIL: frozenset({"construction_detail"}),
    VisualScope.WATER: frozenset({"water", "waterfront"}),
    VisualScope.APPROACH: frozenset({"approach"}),
    VisualScope.BOUNDARY_MAP: frozenset({"boundary_map", "map", "aerial"}),
    VisualScope.RECREATION: frozenset({"recreation"}),
    VisualScope.AERIAL_ESTABLISHING: frozenset({"aerial", "map"}),
}


def property_media_matches_beat(
    research_result: Optional[ResearchResult],
    property_id: str,
    scope: Optional[VisualScope],
) -> bool:
    """True when same-property media is plausibly usable evidence for this
    beat's scope. Permissive by design: only returns False when every
    candidate for this property carries a KNOWN, incompatible role_detail —
    a candidate with no role_detail at all can never be ruled out, the same
    way the existing ranker treats an unlabelled photo as "unknown, not bad".
    """
    if not research_result or not research_result.media:
        return False
    wanted = _SCOPE_TO_ROLE_DETAILS.get(scope) if scope is not None else None
    if not wanted:
        return True  # no clean vocabulary for this scope -> don't gate

    if property_id:
        candidates = [c for c in research_result.media if (c.property_id or "") == property_id]
        if not candidates:
            return False  # media exists, but none of it belongs to THIS listing
    else:
        candidates = list(research_result.media)

    for candidate in candidates:
        detail = (candidate.role_detail or "").strip().lower()
        if not detail or detail in wanted:
            return True
    return False


# ---------------------------------------------------------------------------
# 4. Property story synthesis — narrative rollup, not per-beat classification.
# ---------------------------------------------------------------------------

_HIGH_VALUE_FACT_KEYS = (
    "bedrooms", "bathrooms", "lot_size", "acreage", "waterfront",
    "garage", "pool", "renovation_year", "year_built", "price",
)


@dataclass
class PropertyStoryAnalysis:
    hero_features: List[str] = field(default_factory=list)
    """The 1-3 facts most worth building the visual story around."""
    primary_story_angle: str = ""
    """One phrase describing what this property is fundamentally selling."""
    strongest_visual_opportunities: List[str] = field(default_factory=list)
    """Fact keys that have real matching media to help prove them."""
    visual_gaps: List[str] = field(default_factory=list)
    """Fact keys worth showing that currently have no property media at all
    — a candidate list for what Flow/stock has to cover honestly."""
    confidence: float = 0.0


def _fact_value(facts: Dict[str, str], key: str) -> str:
    return str(facts.get(key, "") or "").strip()


def analyze_property_story(
    research_result: Optional[ResearchResult] = None,
    facts: Optional[Dict[str, str]] = None,
) -> PropertyStoryAnalysis:
    """Synthesizes a story angle and hero features from verified facts only
    — never invents a buyer persona or a claim the facts don't support."""
    facts = dict(facts or {})
    if not facts and research_result is not None:
        facts = research_result.facts_dict()

    hero: List[str] = []
    for key in _HIGH_VALUE_FACT_KEYS:
        value = _fact_value(facts, key)
        if value:
            hero.append(f"{key}={value}")
    hero = hero[:3]

    profile_key = ""
    if research_result is not None and research_result.property is not None:
        profile_key = (research_result.property.property_type or "").strip().lower()

    if hero:
        primary = f"a {profile_key or 'residential'} property defined by {hero[0].split('=')[0].replace('_', ' ')}"
    else:
        primary = f"a {profile_key or 'residential'} property"

    matched: List[str] = []
    gaps: List[str] = []
    has_media = bool(research_result and research_result.has_media())
    if research_result is not None:
        from research.property_ontology import visual_hints_from_facts

        for fact_key, _intent_type, _phrase in visual_hints_from_facts(facts):
            (matched if has_media else gaps).append(fact_key)

    confidence = 0.0
    if hero:
        confidence += 0.4
    if has_media:
        confidence += 0.4
    if matched:
        confidence += 0.2
    confidence = min(1.0, confidence)

    return PropertyStoryAnalysis(
        hero_features=hero,
        primary_story_angle=primary,
        strongest_visual_opportunities=matched,
        visual_gaps=gaps,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# 5. Fact -> visual mapping — thin pass-through for reporting/QA.
# ---------------------------------------------------------------------------

@dataclass
class FactVisualMapping:
    fact_key: str
    fact_value: str
    intent_type: str
    shot_phrase: str
    has_matching_media: bool


def fact_visual_mappings(
    facts: Optional[Dict[str, str]],
    research_result: Optional[ResearchResult] = None,
) -> List[FactVisualMapping]:
    """Which verified facts have a visual implication, and whether this
    listing has ANY media that could plausibly prove them. Delegates
    entirely to property_ontology.visual_hints_from_facts — no parallel
    fact table."""
    from research.property_ontology import visual_hints_from_facts

    facts = dict(facts or {})
    has_any_media = bool(research_result and research_result.has_media())

    out: List[FactVisualMapping] = []
    for fact_key, intent_type, phrase in visual_hints_from_facts(facts):
        out.append(FactVisualMapping(
            fact_key=fact_key,
            fact_value=str(facts.get(fact_key, "")),
            intent_type=intent_type,
            shot_phrase=phrase,
            has_matching_media=has_any_media,
        ))
    return out


# ---------------------------------------------------------------------------
# 6. Flow camera-language enrichment — a small, purpose-keyed phrase table
#    consumed by property_script._enrich_intent(), not a second prompt
#    builder. property_script owns fact-grounding/hallucination-stripping;
#    this only supplies the extra camera-direction phrase for a purpose.
# ---------------------------------------------------------------------------

CAMERA_LANGUAGE_BY_PURPOSE: Dict[str, str] = {
    PURPOSE_LOCATION_CONTEXT: "wide establishing shot conveying geography and access",
    PURPOSE_FEATURE_PROOF: "cinematic reveal emphasizing the specific feature",
    PURPOSE_ROOM_PROOF: "gimbal interior walkthrough, natural light",
    PURPOSE_SPECIFICATION_PROOF: "wide aerial shot conveying scale and extent",
    PURPOSE_PROPERTY_PROOF: "cinematic establishing shot of the home itself",
    PURPOSE_LIFESTYLE: "atmospheric golden-hour lifestyle shot",
    PURPOSE_SCENIC_CONTEXT: "atmospheric wide shot of the surrounding setting",
    PURPOSE_CONDITION_PROOF: "clean, well-lit documentary shot",
}
