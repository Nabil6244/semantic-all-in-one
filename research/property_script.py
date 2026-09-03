"""Property Script Analyzer — Property Video workflow only.

Deliberately separate from visual_director/ (the normal Script Analyzer):
that module must never learn about research/property context, and this one
never touches its Gemini planning path.

Narration is preserved EXACTLY — beats come from sentence-boundary splitting
only; nothing is rewritten, summarized, merged, reordered or paraphrased.

For every beat this produces a VisualIntent — *what the narration is
visually asking for* — rather than a bare category. That intent, not the raw
narration keywords, is what drives the stock query / Flow prompt, which is
the whole point: "At $209,000, this property..." must never become a stock
search for "$209,000".
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum
from typing import Dict, List, Optional

from research.models import PropertySummary, ResearchResult

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'$])")


class BeatCategory(str, Enum):
    PROPERTY_SPECIFIC = "property_specific"
    GENERIC_CONTEXT = "generic_context"
    CINEMATIC_ATMOSPHERIC = "cinematic_atmospheric"
    FACTUAL_PROPERTY_CONTEXT = "factual_property_context"


class VisualScope(str, Enum):
    """What kind of shot the narration wants.

    The vocabulary mirrors the shot types an actual property-tour edit uses
    (aerial establishing -> approach -> land/water reveal -> structure ->
    construction detail -> interior -> boundary map), rather than a generic
    property/generic/cinematic split."""

    AERIAL_ESTABLISHING = "aerial_establishing"
    APPROACH = "approach"
    LAND = "land"
    WATER = "water"
    STRUCTURE = "structure"
    CONSTRUCTION_DETAIL = "construction_detail"
    PROPERTY_INTERIOR = "property_interior"
    PROPERTY_EXTERIOR = "property_exterior"
    BOUNDARY_MAP = "boundary_map"
    RECREATION = "recreation"
    LOCATION = "location"
    LIFESTYLE = "lifestyle"
    LISTING = "listing"
    GENERIC = "generic"


# The reference edit is continuous gimbal/drone motion — no static
# real-estate tripod shots anywhere. Every generated query/prompt carries a
# motion cue so stock ranking and Flow prompts both favour moving footage.
_MOTION_CUE = "slow cinematic drone aerial"
_WALK_CUE = "smooth gimbal walking shot"

# Applied to the 2nd, 3rd, ... consecutive beat sharing one scope, so a run
# of related narration gets varied framing instead of the same clip twice.
_SHOT_VARIATIONS = ("", "low angle close", "wide establishing", "overhead top down")


# Source names map onto the existing pipeline's providers — no new provider
# is introduced by the Property Video workflow.
SOURCE_RESEARCH = "research"
SOURCE_STOCK = "stock"
SOURCE_FLOW = "flow"
SOURCE_AUTO = ""  # leave to the existing Flow/Stock allocation engine


@dataclasses.dataclass
class VisualIntent:
    """Semantic description of the shot the narration is asking for.

    `flow_prompt` and `stock_query` are two DIFFERENT outputs, not
    alternatives to each other:

      flow_prompt  -> depicts THE ACTUAL researched property
      stock_query  -> depicts geographic / architectural / environmental /
                      lifestyle CONTEXT around it

    A context visual must never be presented as evidence of a specific
    property fact — see `requires_authentic` and
    `research_media_unavailable`.
    """

    subject: str
    scope: VisualScope
    stock_query: str = ""
    """Contextual stock search — derived from property type + location +
    intent, never a raw copy of the narration (no prices, no listing ids,
    no proper-noun soup)."""
    flow_prompt: str = ""
    intent_type: str = ""
    """One of research.property_ontology.IntentType — PROPERTY_* means this
    beat must depict the real property; *_CONTEXT means generic context is
    legitimate here."""
    requires_authentic: bool = False
    """True when only authentic property media can honestly satisfy this
    beat (a specific feature of THIS property)."""
    research_media_unavailable: bool = False
    """Set when `requires_authentic` but no same-property media exists.
    The beat is explicitly marked rather than silently letting generic
    stock stand in for a specific property fact."""
    fact_basis: str = ""
    """Which structured fact licensed this intent, when one did — empty
    when the intent came from the narration alone."""
    visual_purpose: str = ""
    """WHY this beat needs a visual — one of
    research.property_visual_intelligence's PURPOSE_* constants. Empty when
    not yet classified (every caller through analyze_property_script sets
    this; direct build_visual_intent() callers are unaffected)."""
    semantic_tags: List[str] = dataclasses.field(default_factory=list)
    """Fine-grained room/feature tags (kitchen, garage, pool, ...) that
    VisualScope's broader buckets don't distinguish. Additive, never
    replaces `scope`."""
    confidence: str = ""
    """"high" / "medium" / "low" — how directly the chosen source can prove
    this beat, not a property-identity confidence (that stays hard-gated
    elsewhere and is never a matter of degree)."""


@dataclasses.dataclass
class PropertyBeat:
    narration: str
    category: BeatCategory
    reason: str = ""
    property_id: str = ""
    intent: Optional[VisualIntent] = None
    preferred_source: str = SOURCE_AUTO
    fallback_source: str = SOURCE_AUTO


# Reference pacing: one descriptive beat every ~2-3 seconds of narration.
# At a typical ~2.5 words/second VO that's roughly 5-8 words, so a sentence
# materially longer than this gets split at CLAUSE boundaries (never
# mid-phrase, never rewritten) so one long sentence doesn't hold a single
# visual on screen for 8+ seconds.
BEAT_TARGET_WORDS = 9
BEAT_MAX_WORDS = 14

# Clause boundaries, in preference order. The delimiter always stays with
# the LEFT fragment so re-joining the beats with a single space reproduces
# the original narration character-for-character.
_CLAUSE_SPLIT_RE = re.compile(
    r"(?<=[,;:])\s+|\s+(?=\b(?:and|but|with|while|where|which|that|plus|"
    r"including|featuring|known for|surrounded by|overlooking)\b)",
    re.I,
)


def _split_long_sentence(sentence: str) -> List[str]:
    """Break one over-long sentence into clause-level beats. Never alters
    any word; fragments are re-joinable into the exact original."""
    if len(sentence.split()) <= BEAT_MAX_WORDS:
        return [sentence]

    pieces = [p for p in _CLAUSE_SPLIT_RE.split(sentence) if p and p.strip()]
    if len(pieces) <= 1:
        return [sentence]

    # Re-merge fragments that are too small to stand as their own shot, so
    # we get ~BEAT_TARGET_WORDS chunks rather than a spray of 2-word beats.
    merged: List[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if merged and len(merged[-1].split()) < BEAT_TARGET_WORDS // 2:
            merged[-1] = f"{merged[-1]} {piece}"
        elif merged and len(piece.split()) < 3:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged or [sentence]


def split_narration_into_beats(narration: str, *, dense: bool = True) -> List[str]:
    """Sentence-boundary split, then clause-level splitting of long
    sentences when `dense` (the Property Video default) — never rewrites,
    reorders, merges across sentences, or paraphrases. Re-joining the result
    with single spaces reproduces the input exactly.

    `dense=False` restores pure sentence-level beats.
    """
    text = (narration or "").strip()
    if not text:
        return []
    beats: List[str] = []
    for para in re.split(r"\n\s*\n+", text):
        para = para.strip()
        if not para:
            continue
        for line in para.splitlines():
            line = line.strip()
            if not line:
                continue
            for sentence in (s.strip() for s in _SENTENCE_SPLIT_RE.split(line) if s.strip()):
                if dense:
                    beats.extend(_split_long_sentence(sentence))
                else:
                    beats.append(sentence)
    return beats or [text]


# --- intent cues -------------------------------------------------------
# Compact rule table, deliberately NOT an exhaustive keyword dictionary:
# each entry maps a detected signal to an intent subject + the *kind* of
# shot wanted. Everything else falls through to a generic-but-semantic
# phrasing built from the narration's own content words.

_INTERIOR_FEATURES = (
    "fireplace", "kitchen", "bedroom", "bathroom", "living room", "dining room",
    "master suite", "basement", "attic", "closet", "hardwood", "granite",
    "countertop", "layout", "floor plan", "interior", "ceiling", "staircase",
)
_EXTERIOR_FEATURES = (
    "porch", "deck", "patio", "garage", "barn", "roof", "siding", "driveway",
    "fence", "exterior", "facade", "curb appeal", "veranda", "wraparound",
)
_LAND_FEATURES = (
    "acre", "acres", "lot", "yard", "pasture", "field", "meadow",
    "woods", "wooded", "forest", "land", "grounds", "garden", "backyard",
    "clearing", "timber",
    # Grazing/equestrian land.
    "paddock", "paddocks", "corral", "rangeland", "grazing", "hayfield",
)
# Waterfront is its own shot type in a real tour (dedicated creek/pond
# footage), not "some land".
_WATER_FEATURES = (
    "creek", "river", "stream", "pond", "lake", "waterfront", "frontage",
    "shoreline", "brook", "spring", "waterfall",
    # Built water access is still a water beat, not generic context.
    "dock", "pier", "boathouse", "seawall", "boat slip",
)
_APPROACH_FEATURES = (
    "driveway", "drive", "gate", "gated", "entrance", "lane", "road in",
    "winds through", "leads to",
)
_STRUCTURE_FEATURES = (
    "cabin", "cabins", "home", "house", "cottage", "barn", "shed",
    "outbuilding", "garage", "structure", "building",
    # Equestrian/agricultural buildings are property structures too — this
    # workflow is not farmhouse-only.
    "stable", "stables", "stall", "stalls", "arena", "silo", "greenhouse",
    "workshop", "guest house", "carport", "coop",
)
# Close-up material/construction character (log chinking, beams, plank floors).
_CONSTRUCTION_FEATURES = (
    "hand-hewn", "hand hewn", "chinking", "chinked", "log", "logs", "beam",
    "beams", "vaulted", "plank", "hardwood", "timber frame", "stonework",
    "masonry", "craftsmanship", "squared logs",
)
_RECREATION_FEATURES = (
    "fishing", "fish", "muskie", "bass", "trout", "kayak", "canoe",
    "hunting", "deer", "turkey", "trail", "trails", "recreation", "wildlife",
)
# "Our second listing…", "the next property…", "the other home…" — a listing
# switch that never names the property. Ordinal/anaphoric only; a bare "it"
# or "this" deliberately does NOT switch, since those normally continue the
# current listing.
_ADVANCE_LISTING_CUES = re.compile(
    r"\b(second|third|fourth|next|another|other)\s+"
    r"(listing|property|home|house|cabin|place|one)\b"
    r"|\bmoving\s+on\s+to\b|\bnext\s+up\b",
    re.I,
)

_INSIDE_CUES = re.compile(
    r"\b(inside|indoors|interior|great room|living room|dining room|kitchen|"
    r"bedroom|bathroom|upstairs|downstairs|walk in|step into)\b", re.I,
)
_BOUNDARY_CUES = re.compile(
    r"\b(boundary|boundaries|property line|parcel|survey|acreage|"
    r"wraps? (?:the )?propert|three sides|borders?)\b", re.I,
)
_LOCATION_CUES = re.compile(
    r"\b(located|location|near|minutes from|miles from|drive from|access to|"
    r"close to|just outside|nestled in|situated)\b", re.I,
)
_CINEMATIC_CUES = re.compile(
    r"\b(imagine|picture\s+yourself|waking\s+up|envision|close\s+your\s+eyes|"
    r"as\s+the\s+sun|at\s+sunset|at\s+dawn|at\s+dusk|feel\s+the|breathe|"
    r"peaceful|serene|tranquil|escape)\b", re.I,
)
_PRICE_CUES = re.compile(r"(\$[\d,]+(?:\.\d+)?|\b\d[\d,]*\s*(?:dollars|k\b))", re.I)
_MEASUREMENT_CUES = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(acres?|sq\s?ft|square\s+feet|bedrooms?|bathrooms?|"
    r"beds?|baths?|hectares?|square\s+met(?:er|re)s?)\b", re.I,
)

# Words that must never survive into a stock search query: they retrieve
# nothing visual (a price is not a picture) or actively poison results.
_QUERY_NOISE_RE = re.compile(
    r"(\$[\d,]+(?:\.\d+)?|\b\d[\d,]*\b|\b(?:this|that|these|those|it|its|"
    r"the|a|an|of|in|on|at|with|and|or|for|to|is|are|was|were|will|would|"
    r"you|your|we|our|they|their|also|just|only|more|most|very|really)\b)",
    re.I,
)

_PROPER_NOUN_RE = re.compile(r"\b([A-Z][a-z]{2,})\b")


def _content_words(text: str, limit: int = 6) -> List[str]:
    cleaned = _QUERY_NOISE_RE.sub(" ", text)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]{2,}", cleaned)]
    seen, out = set(), []
    for word in words:
        low = word.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(low)
        if len(out) >= limit:
            break
    return out


def _first_match(text_lower: str, options) -> str:
    """Word-boundary match — a plain substring test would fire "land" inside
    "farmland" (turning a generic-countryside line into a property-specific
    one) and "deck" inside "decked"."""
    for option in options:
        if re.search(rf"\b{re.escape(option)}\b", text_lower):
            return option
    return ""


def _place_names(text: str, property_summary: PropertySummary) -> List[str]:
    """Proper nouns that look like places, excluding the property's own
    name (which isn't a searchable public location)."""
    own = {
        (property_summary.name or "").lower(),
        (property_summary.address or "").lower(),
    }
    # A capitalized word at the start of a sentence is usually just a
    # sentence start ("The surrounding area..."), not a place name.
    not_places = {
        "the", "this", "that", "these", "those", "a", "an", "at", "it",
        "families", "imagine", "with", "and", "but", "for", "you", "your",
        "located", "nestled", "just", "situated", "close", "near", "minutes",
        "miles", "drive", "access", "surrounding", "area", "offers", "easy",
    }
    out = []
    for match in _PROPER_NOUN_RE.findall(text):
        low = match.lower()
        if low in not_places:
            continue
        if low in own or any(low in o for o in own if o):
            continue
        out.append(match)
    return out


def build_visual_intent(
    text: str,
    property_summary: PropertySummary,
    *,
    profile=None,
    location=None,
    facts: Optional[dict] = None,
) -> VisualIntent:
    """Decide what shot the narration is asking for, then phrase a stock
    query / Flow prompt from THAT — not from the raw narration.

    `profile` (property type), `location` and `facts` are optional; when
    supplied the intent becomes property-type-aware, location-aware and
    fact-grounded. All three default to None so every existing caller keeps
    working unchanged."""
    base = _build_visual_intent_core(text, property_summary, profile)
    return _enrich_intent(
        base, text=text, property_summary=property_summary,
        profile=profile, location=location, facts=facts,
    )


def _mask_property_name(text: str, property_summary: PropertySummary) -> str:
    """Blank out the listing's own name/address so its words can't be read as
    property features. Returns `text` unchanged when there's nothing to mask."""
    masked = text or ""
    for value in (property_summary.name, property_summary.address):
        value = (value or "").strip()
        if len(value) < 3:
            continue
        masked = re.sub(rf"\b{re.escape(value)}\b", " ", masked, flags=re.I)
    return masked


def _build_visual_intent_core(text: str, property_summary: PropertySummary, profile=None) -> VisualIntent:
    # Architecture/landscape wording comes from the property TYPE, so a
    # suburban kitchen never gets described as a rustic cabin interior.
    arch = getattr(profile, 'architecture', '') or 'residential property'
    scenery = getattr(profile, 'landscape', '') or 'surrounding countryside'
    # Feature detection runs against the narration with the listing's OWN
    # name/address masked out. "Willow Creek Ranch" must not request creek
    # footage and "Cedar Pond Estate" must not request a pond — those are
    # names, not features, and inventing a water feature from a name is
    # exactly the unsupported-claim failure this workflow forbids. A real
    # creek still registers when the narration or a structured fact says so.
    lowered = _mask_property_name(text, property_summary).lower()

    interior = _first_match(lowered, _INTERIOR_FEATURES)
    exterior = _first_match(lowered, _EXTERIOR_FEATURES)
    land = _first_match(lowered, _LAND_FEATURES)
    water = _first_match(lowered, _WATER_FEATURES)
    approach = _first_match(lowered, _APPROACH_FEATURES)
    structure = _first_match(lowered, _STRUCTURE_FEATURES)
    construction = _first_match(lowered, _CONSTRUCTION_FEATURES)
    recreation = _first_match(lowered, _RECREATION_FEATURES)
    is_boundary = bool(_BOUNDARY_CUES.search(text))
    is_location = bool(_LOCATION_CUES.search(text))
    is_cinematic = bool(_CINEMATIC_CUES.search(text))
    is_price = bool(_PRICE_CUES.search(text))
    has_acreage = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*acres?\b", text, re.I))

    # An explicit "we are inside" cue outranks a material/construction word:
    # "Inside, the great room has a vaulted ceiling" is an interior shot that
    # happens to mention a beam, not a close-up of the beam itself.
    if interior and _INSIDE_CUES.search(text):
        return VisualIntent(
            subject=f"{interior} inside this home",
            scope=VisualScope.PROPERTY_INTERIOR,
            stock_query=f"{_WALK_CUE} {interior} {arch} interior natural light",
            flow_prompt=f"cinematic interior gimbal shot of the {interior} in a {arch}",
        )

    # Order matters: the most specific shot type the narration is asking for
    # wins. Construction detail and water beat generic "land"/"structure",
    # because a real edit cuts to those as their own shots.
    if construction:
        return VisualIntent(
            subject=f"close-up construction character: {construction}",
            scope=VisualScope.CONSTRUCTION_DETAIL,
            stock_query=f"close up {construction} cabin construction detail texture",
            flow_prompt=f"extreme close-up of {construction} on a {arch}, shallow depth of field",
        )
    if recreation:
        return VisualIntent(
            subject=f"recreation on the property: {recreation}",
            scope=VisualScope.RECREATION,
            stock_query=f"{recreation} river outdoor recreation nature",
            flow_prompt=f"cinematic shot of {recreation} on a wild creek",
        )
    if water:
        return VisualIntent(
            subject=f"the property's {water}",
            scope=VisualScope.WATER,
            stock_query=f"{_MOTION_CUE} over a {water} rural waterfront flowing water",
            flow_prompt=f"cinematic aerial following a {water} through forested land",
        )
    if is_boundary or (has_acreage and not structure):
        # Acreage/boundary narration is shown as a map/aerial that conveys
        # extent — the reference literally overlays a satellite boundary.
        return VisualIntent(
            subject="property extent / boundary from above",
            scope=VisualScope.BOUNDARY_MAP,
            stock_query=f"{_MOTION_CUE} over large rural acreage property overhead",
            flow_prompt="top-down aerial map view tracing a rural property boundary",
        )
    if approach:
        return VisualIntent(
            subject=f"the approach: {approach}",
            scope=VisualScope.APPROACH,
            stock_query=f"{_WALK_CUE} along a gravel {approach} through trees",
            flow_prompt=f"cinematic tracking shot moving up the {approach} toward a {arch}",
        )
    if interior:
        return VisualIntent(
            subject=f"{interior} inside this home",
            scope=VisualScope.PROPERTY_INTERIOR,
            stock_query=f"{_WALK_CUE} {interior} {arch} interior natural light",
            flow_prompt=f"cinematic interior gimbal shot of the {interior} in a {arch}",
        )
    if exterior:
        return VisualIntent(
            subject=f"the home's {exterior}",
            scope=VisualScope.PROPERTY_EXTERIOR,
            stock_query=f"{_WALK_CUE} residential house {exterior} exterior",
            flow_prompt=f"cinematic exterior orbit around a house {exterior}",
        )
    if structure:
        return VisualIntent(
            subject=f"the {structure} on the property",
            scope=VisualScope.STRUCTURE,
            stock_query=f"{_MOTION_CUE} {structure} {scenery}",
            flow_prompt=f"cinematic reveal of the {structure} set in {scenery}",
        )
    if land:
        return VisualIntent(
            subject=f"the property's {land}",
            scope=VisualScope.LAND,
            stock_query=f"{_MOTION_CUE} over rural {land} open countryside",
            flow_prompt=f"cinematic aerial over rural {land}",
        )
    if is_location:
        places = _place_names(text, property_summary)
        place = places[0] if places else (property_summary.city or property_summary.state or "")
        where = f"{place} " if place else ""
        return VisualIntent(
            subject=f"regional access / setting near {place or 'the area'}",
            scope=VisualScope.LOCATION,
            # Location narration wants travel/access/townscape — NOT
            # generic countryside, and not a bare place-name keyword dump.
            stock_query=f"{where}town road highway travel regional landscape".strip(),
            flow_prompt=f"cinematic establishing shot of the countryside near {place or 'a small town'}",
        )
    if is_price:
        # A price is not a picture: show the listing/home itself, never a
        # stock search containing the number.
        return VisualIntent(
            subject="the home itself as the listing being priced",
            scope=VisualScope.LISTING,
            stock_query="residential home exterior for sale real estate",
            flow_prompt="cinematic establishing shot of a home for sale",
        )
    if is_cinematic:
        words = " ".join(_content_words(text, limit=5))
        return VisualIntent(
            subject=f"atmospheric lifestyle imagery: {words or 'peaceful rural living'}",
            scope=VisualScope.LIFESTYLE,
            stock_query=f"{words} peaceful rural lifestyle golden hour".strip(),
            flow_prompt=f"cinematic atmospheric shot, {words or 'peaceful countryside at golden hour'}",
        )

    words = " ".join(_content_words(text, limit=5))
    return VisualIntent(
        subject=words or "supporting context imagery",
        scope=VisualScope.GENERIC,
        stock_query=words,
        flow_prompt=f"cinematic shot of {words}" if words else "",
    )


# VisualScope -> semantic IntentType. Keeps the existing scope vocabulary
# (which the shot/query generation is built on) while exposing the
# property-vs-context distinction the ontology cares about.
_SCOPE_TO_INTENT = {
    VisualScope.AERIAL_ESTABLISHING: "property_aerial",
    VisualScope.APPROACH: "property_approach",
    VisualScope.LAND: "property_land",
    VisualScope.WATER: "property_water",
    VisualScope.STRUCTURE: "property_structure",
    VisualScope.CONSTRUCTION_DETAIL: "property_construction",
    VisualScope.PROPERTY_INTERIOR: "property_interior",
    VisualScope.PROPERTY_EXTERIOR: "property_structure",
    VisualScope.BOUNDARY_MAP: "property_boundary",
    VisualScope.RECREATION: "property_feature",
    VisualScope.LISTING: "property_specific",
    VisualScope.LOCATION: "geographic_context",
    VisualScope.LIFESTYLE: "lifestyle_context",
    VisualScope.GENERIC: "environmental_context",
}


def _enrich_intent(
    intent: VisualIntent,
    *,
    text: str,
    property_summary: PropertySummary,
    profile=None,
    location=None,
    facts: Optional[dict] = None,
) -> VisualIntent:
    """Applies property-type / location / fact awareness on top of the base
    intent, and strips any unsupported feature claim out of the Flow prompt."""
    from research.property_ontology import (
        IntentType,
        PropertyLocation,
        build_context_query,
        clean_stock_query,
        resolve_property_type,
        unsupported_features,
        visual_hints_from_facts,
    )

    intent_type = _SCOPE_TO_INTENT.get(intent.scope, "environmental_context")
    requires_authentic = IntentType(intent_type).is_property_specific

    if profile is None:
        profile = resolve_property_type(
            property_summary.property_type,
            (facts or {}).get("property_type", ""),
            text,
        )
    if location is None:
        location = PropertyLocation(
            city=property_summary.city or "",
            state=property_summary.state or "",
            country=property_summary.country or "",
        )

    # --- fact grounding -------------------------------------------------
    # A structured fact that matches this beat both licenses the intent and
    # names the shot, so "57 acres" becomes an aerial land reveal because
    # the LISTING says 57 acres — not because of a keyword in the sentence.
    fact_basis = ""
    for fact_key, hint_intent, shot_phrase in visual_hints_from_facts(facts):
        value = str((facts or {}).get(fact_key, "")).lower()
        if not value:
            continue
        tokens = [t for t in re.findall(r"[a-z]{4,}", value)]
        if any(t in text.lower() for t in tokens) or hint_intent == intent_type:
            fact_basis = f"{fact_key}={(facts or {}).get(fact_key)}"
            if hint_intent == intent_type and shot_phrase:
                intent = dataclasses.replace(intent, subject=f"{intent.subject} — {shot_phrase}")
            break

    # --- context-aware stock query --------------------------------------
    # Stock represents CONTEXT: property-type landscape + region, not a
    # restatement of the property's own specifics.
    context_subject = intent.stock_query or intent.subject
    if requires_authentic:
        # Even the fallback context shot for a property beat should look
        # like the right KIND of place, without claiming to be this one.
        context_subject = " ".join(
            w for w in context_subject.split()
            if w.lower() not in ("this", "the", "its", "their")
        )
    stock_query = build_context_query(
        subject=context_subject, profile=profile, location=location,
        # Location narrows well for outdoor/context shots, but hurts for
        # interiors and close-up detail (a "Kentucky vaulted ceiling" is
        # not a thing) — so it is applied only where it genuinely helps.
        use_location=intent.scope not in (
            VisualScope.PROPERTY_INTERIOR, VisualScope.CONSTRUCTION_DETAIL,
        ),
    )

    # --- Flow prompt: authentic property, never invented features -------
    flow_prompt = intent.flow_prompt
    invented = unsupported_features(flow_prompt, text, facts)
    for feature in invented:
        flow_prompt = re.sub(rf"\b\w*\s*{re.escape(feature)}\w*\b", "", flow_prompt, flags=re.I)
    flow_prompt = re.sub(r"\s{2,}", " ", flow_prompt).strip(" ,")
    if profile.architecture and requires_authentic and profile.key != "property":
        if profile.architecture.split()[0].lower() not in flow_prompt.lower():
            flow_prompt = f"{flow_prompt}, {profile.architecture}"

    return dataclasses.replace(
        intent,
        stock_query=clean_stock_query(stock_query),
        flow_prompt=flow_prompt,
        intent_type=intent_type,
        requires_authentic=requires_authentic,
        fact_basis=fact_basis,
    )


def _mentions_property_identity(text: str, property_summary: PropertySummary) -> bool:
    """Word-boundary match only — a naive substring check would let a
    2-letter state abbreviation like "AL" false-match inside "Alabama"."""
    for value in (
        property_summary.name,
        property_summary.address,
        property_summary.city,
        property_summary.state,
        property_summary.property_type,
    ):
        value = (value or "").strip()
        if not value:
            continue
        if re.search(rf"\b{re.escape(value)}\b", text, re.I):
            return True
    return False


def classify_beat(
    text: str,
    property_summary: PropertySummary,
    *,
    property_facts: Optional[dict] = None,
) -> tuple:
    """Returns (BeatCategory, reason)."""
    lowered = text.lower()
    facts_text = " ".join(str(v) for v in (property_facts or {}).values()).lower()

    if _MEASUREMENT_CUES.search(text) or _PRICE_CUES.search(text):
        return BeatCategory.FACTUAL_PROPERTY_CONTEXT, "narration states a concrete listing fact (measurement/price)"

    # Any concrete feature of THIS property — interior, exterior, land,
    # water/frontage, structures, construction character or the approach —
    # is property-specific and should prefer authentic same-property media.
    if (
        _first_match(lowered, _INTERIOR_FEATURES)
        or _first_match(lowered, _EXTERIOR_FEATURES)
        or _first_match(lowered, _LAND_FEATURES)
        or _first_match(lowered, _WATER_FEATURES)
        or _first_match(lowered, _STRUCTURE_FEATURES)
        or _first_match(lowered, _CONSTRUCTION_FEATURES)
        or _first_match(lowered, _APPROACH_FEATURES)
        or _mentions_property_identity(text, property_summary)
    ):
        return BeatCategory.PROPERTY_SPECIFIC, "narration describes a specific feature of this property"

    if facts_text:
        for token in re.findall(r"[a-zA-Z]{4,}", facts_text):
            if token.lower() in lowered:
                return BeatCategory.PROPERTY_SPECIFIC, f"narration matches a researched property fact ('{token}')"

    if _CINEMATIC_CUES.search(text):
        return BeatCategory.CINEMATIC_ATMOSPHERIC, "atmospheric/aspirational framing, not a factual claim"

    return BeatCategory.GENERIC_CONTEXT, "general context, not a claim about this specific property"


def _profile_for(property_summary: PropertySummary, facts: Optional[dict]):
    from research.property_ontology import resolve_property_type

    return resolve_property_type(
        property_summary.property_type,
        (facts or {}).get("property_type", ""),
        property_summary.name,
    )


def _location_for(property_summary: PropertySummary):
    from research.property_ontology import PropertyLocation

    return PropertyLocation(
        city=property_summary.city or "",
        state=property_summary.state or "",
        country=property_summary.country or "",
    )


def _sources_for(
    category: BeatCategory,
    has_property_media: bool,
    *,
    media_matches_beat: Optional[bool] = None,
) -> tuple:
    """Source priority, per the Property Video spec.

    Concrete property facts prefer same-property Research media, then
    relevant Stock — but only when that media plausibly depicts THIS beat,
    not merely because the listing has media at all. `media_matches_beat`
    (research.property_visual_intelligence.property_media_matches_beat) is
    the beat-level evidence gate; omitting it preserves the original
    listing-has-any-media behavior for any other caller.

    Generic context prefers Stock. Cinematic beats are left to the existing
    Flow/Stock allocation engine rather than being forced here."""
    if category in (BeatCategory.PROPERTY_SPECIFIC, BeatCategory.FACTUAL_PROPERTY_CONTEXT):
        matches = has_property_media if media_matches_beat is None else (has_property_media and media_matches_beat)
        if matches:
            return SOURCE_RESEARCH, SOURCE_STOCK
        return SOURCE_STOCK, SOURCE_AUTO
    if category == BeatCategory.GENERIC_CONTEXT:
        return SOURCE_STOCK, SOURCE_AUTO
    return SOURCE_AUTO, SOURCE_AUTO  # cinematic -> existing allocation engine


def analyze_property_script(
    narration: str,
    research_result: Optional[ResearchResult] = None,
    property_facts: Optional[dict] = None,
    *,
    properties: Optional[List[PropertySummary]] = None,
    default_property_id: str = "",
    facts_by_property: Optional[Dict[str, dict]] = None,
) -> List[PropertyBeat]:
    """Top-level Property Script Analyzer.

    `properties` supplies every researched listing so multi-listing scripts
    can switch context when the narration moves to a different property;
    context is otherwise *inherited* from the previous beat, so consecutive
    sentences about the same home stay bound to that home.

    `facts_by_property` maps property_id -> that listing's structured facts.
    Without it every beat would be analyzed using the FIRST listing's facts,
    so a second listing's beats would be classified against another
    property's acreage/features. `property_facts` remains the
    single-listing path and is used as the fallback.
    """
    primary = research_result.property if research_result else PropertySummary()
    known: List[PropertySummary] = list(properties or ([primary] if research_result else []))
    has_media = bool(research_result and research_result.has_media())
    facts_map = dict(facts_by_property or {})

    current_property_id = default_property_id or (primary.property_id if primary else "")
    beats: List[PropertyBeat] = []

    def facts_for(property_id: str) -> Optional[dict]:
        if property_id and property_id in facts_map:
            return facts_map[property_id]
        return property_facts

    for beat_text in split_narration_into_beats(narration):
        # Context switch when this beat names a *different* known listing...
        switched = False
        for candidate in known:
            if candidate.property_id and candidate.property_id != current_property_id:
                if _mentions_property_identity(beat_text, candidate):
                    current_property_id = candidate.property_id
                    switched = True
                    break

        # ...or when it refers to one without naming it ("our second
        # listing", "the next property"). Without this the following beats
        # stay bound to the previous listing, and that listing's authentic
        # photos would be served as evidence for this one's features.
        if not switched and _ADVANCE_LISTING_CUES.search(beat_text):
            ordered = [p.property_id for p in known if p.property_id]
            if len(ordered) > 1:
                try:
                    nxt = ordered.index(current_property_id) + 1
                except ValueError:
                    nxt = 0
                current_property_id = ordered[nxt % len(ordered)]

        active = next(
            (p for p in known if p.property_id == current_property_id),
            primary,
        )
        active_facts = facts_for(current_property_id)
        category, reason = classify_beat(beat_text, active, property_facts=active_facts)
        intent = build_visual_intent(
            beat_text, active,
            profile=_profile_for(active, active_facts),
            location=_location_for(active),
            facts=active_facts,
        )
        # Decision hierarchy step 3: a beat that can only be honestly served
        # by authentic media, with no same-property media available, is
        # MARKED — never quietly satisfied with generic stock pretending to
        # be this property.
        if intent.requires_authentic and not has_media:
            intent = dataclasses.replace(intent, research_media_unavailable=True)

        # Purpose/tag/confidence classification and the beat-level media
        # match gate are deferred imports — property_visual_intelligence
        # imports BeatCategory/VisualScope/PropertyBeat from this module at
        # load time, so importing it back at module scope here would be
        # circular. Same pattern already used for property_ontology below.
        from research.property_visual_intelligence import (
            CAMERA_LANGUAGE_BY_PURPOSE,
            classify_visual_purpose,
            property_media_matches_beat,
            semantic_categories_for,
        )

        purpose = classify_visual_purpose(
            PropertyBeat(narration=beat_text, category=category, reason=reason, intent=intent)
        )
        tags = semantic_categories_for(beat_text)
        media_matches = property_media_matches_beat(research_result, current_property_id, intent.scope)
        preferred, fallback = _sources_for(category, has_media, media_matches_beat=media_matches)

        if preferred == SOURCE_RESEARCH:
            confidence = "high" if media_matches else "medium"
        elif purpose in (
            "feature_proof", "room_proof", "specification_proof", "property_proof", "condition_proof",
        ):
            confidence = "medium"
        else:
            confidence = "low"

        flow_prompt = intent.flow_prompt
        camera_language = CAMERA_LANGUAGE_BY_PURPOSE.get(purpose, "")
        if camera_language and flow_prompt and camera_language.lower() not in flow_prompt.lower():
            flow_prompt = f"{flow_prompt}, {camera_language}"

        intent = dataclasses.replace(
            intent,
            visual_purpose=purpose,
            semantic_tags=tags,
            confidence=confidence,
            flow_prompt=flow_prompt,
        )

        # Shot variety: the reference edit never holds the same framing for
        # consecutive beats. When two beats in a row want the same scope,
        # vary the angle cue so stock/Flow return a genuinely different shot
        # rather than the same clip twice.
        if beats and beats[-1].intent is not None and beats[-1].intent.scope == intent.scope:
            run_len = 1
            for previous in reversed(beats):
                if previous.intent is not None and previous.intent.scope == intent.scope:
                    run_len += 1
                else:
                    break
            variation = _SHOT_VARIATIONS[min(run_len - 1, len(_SHOT_VARIATIONS) - 1)]
            if variation:
                intent = dataclasses.replace(
                    intent,
                    stock_query=f"{intent.stock_query} {variation}".strip(),
                    flow_prompt=f"{intent.flow_prompt}, {variation}".strip(", "),
                )

        beats.append(
            PropertyBeat(
                narration=beat_text,
                category=category,
                reason=reason,
                property_id=(current_property_id if category in (
                    BeatCategory.PROPERTY_SPECIFIC, BeatCategory.FACTUAL_PROPERTY_CONTEXT
                ) else ""),
                intent=intent,
                preferred_source=preferred,
                fallback_source=fallback,
            )
        )
    return beats
