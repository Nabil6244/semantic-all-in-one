"""Property visual ontology — property-video only.

Answers three questions the raw narration cannot, without becoming a giant
hardcoded keyword list:

1. What KIND of property is this? (farmhouse vs ranch vs horse property vs
   development land — the same word needs different visuals for each.)
2. WHERE is it? (so "Kentucky rural countryside" beats "rural countryside",
   but only when location genuinely helps the search.)
3. What does a given structured FACT imply visually? ("57 acres" is an
   aerial/boundary shot; "pond" is a dedicated water shot.)

Everything here is data-driven and extensible: adding a property type is one
entry in PROPERTY_TYPES, adding a fact mapping is one entry in
FACT_VISUAL_HINTS. Nothing here is US-specific — US coverage is the priority
but the mechanism (type + location + facts) is country-agnostic, and an
unknown type/location degrades to the generic behavior rather than failing.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


class IntentType(str, Enum):
    """Semantic visual intent. PROPERTY_* means "must depict the actual
    researched property"; *_CONTEXT means "generic context is legitimate
    here". This distinction is the whole point — they are not
    interchangeable, and a *_CONTEXT visual must never be presented as
    evidence of a specific property fact."""

    PROPERTY_SPECIFIC = "property_specific"
    PROPERTY_STRUCTURE = "property_structure"
    PROPERTY_INTERIOR = "property_interior"
    PROPERTY_LAND = "property_land"
    PROPERTY_WATER = "property_water"
    PROPERTY_FEATURE = "property_feature"
    PROPERTY_CONSTRUCTION = "property_construction"
    PROPERTY_APPROACH = "property_approach"
    PROPERTY_AERIAL = "property_aerial"
    PROPERTY_BOUNDARY = "property_boundary"
    GEOGRAPHIC_CONTEXT = "geographic_context"
    ARCHITECTURAL_CONTEXT = "architectural_context"
    ENVIRONMENTAL_CONTEXT = "environmental_context"
    LIFESTYLE_CONTEXT = "lifestyle_context"
    CINEMATIC = "cinematic"

    @property
    def is_property_specific(self) -> bool:
        return self.value.startswith("property_")


@dataclasses.dataclass(frozen=True)
class PropertyTypeProfile:
    """How one kind of property should be shown."""

    key: str
    aliases: Tuple[str, ...]
    landscape: str
    """Terrain/setting phrase used to build CONTEXT stock queries."""
    architecture: str
    """Architectural phrase for structure/exterior context."""
    signature_shots: Tuple[str, ...] = ()
    """Shot types this property type is characteristically sold on."""
    supports: Tuple[str, ...] = ()
    """Features that are *typical* for this type. Never treated as proof —
    only structured facts or the narration itself can license a specific
    feature claim (see feature_is_supported)."""


# Ordered: the first profile whose alias matches wins, so more specific
# types (log cabin, horse property) precede broader ones (cabin, rural).
PROPERTY_TYPES: Tuple[PropertyTypeProfile, ...] = (
    PropertyTypeProfile(
        "log_cabin", ("log cabin", "log home", "hand-hewn", "hand hewn"),
        landscape="wooded forest countryside", architecture="rustic log cabin",
        signature_shots=("wooded approach", "cabin exterior", "log construction detail"),
        supports=("logs", "chinking", "porch", "woodstove"),
    ),
    PropertyTypeProfile(
        "cabin", ("cabin", "chalet", "lodge"),
        landscape="wooded countryside", architecture="rustic cabin",
        signature_shots=("wooded approach", "cabin exterior", "interior wide"),
        supports=("porch", "fireplace"),
    ),
    PropertyTypeProfile(
        "horse_property", ("horse property", "equestrian", "stable", "paddock", "horse farm"),
        landscape="open pasture paddock countryside", architecture="barn and stable buildings",
        signature_shots=("pasture aerial", "barn exterior", "paddock fencing"),
        supports=("barn", "stable", "paddock", "pasture", "fencing", "arena"),
    ),
    PropertyTypeProfile(
        "hunting_property", ("hunting", "hunting land", "game land", "deer lease"),
        landscape="dense woodland habitat", architecture="rustic hunting cabin",
        signature_shots=("woodland trail", "wildlife habitat", "food plot"),
        supports=("trails", "blind", "woods"),
    ),
    PropertyTypeProfile(
        "ranch", ("ranch", "cattle ranch", "working ranch"),
        landscape="open rangeland wide grassland", architecture="ranch house and outbuildings",
        signature_shots=("rangeland aerial", "ranch house exterior", "fence line"),
        supports=("barn", "corral", "pasture", "livestock", "fencing"),
    ),
    PropertyTypeProfile(
        "agricultural", ("farmland", "cropland", "agricultural", "row crop", "orchard", "vineyard"),
        landscape="working farmland fields", architecture="farm buildings",
        signature_shots=("field aerial", "crop rows", "farm buildings"),
        supports=("fields", "barn", "irrigation"),
    ),
    PropertyTypeProfile(
        "farmhouse", ("farmhouse", "farm house", "country home", "homestead"),
        landscape="rolling rural farmland", architecture="classic farmhouse",
        signature_shots=("farmhouse exterior", "surrounding fields", "porch"),
        supports=("porch", "barn", "fields"),
    ),
    PropertyTypeProfile(
        "waterfront", ("waterfront", "lakefront", "riverfront", "creekfront", "lake house", "river house"),
        landscape="water's edge shoreline", architecture="waterfront home",
        signature_shots=("water edge reveal", "dock", "aerial over water"),
        supports=("dock", "shoreline", "water frontage"),
    ),
    PropertyTypeProfile(
        "coastal", ("coastal", "beachfront", "oceanfront", "beach house"),
        landscape="coastal shoreline ocean", architecture="coastal home",
        signature_shots=("coastline aerial", "beach access", "ocean view"),
        supports=("beach", "shoreline", "ocean view"),
    ),
    PropertyTypeProfile(
        "mountain", ("mountain", "alpine", "ski", "high country"),
        landscape="mountain range alpine terrain", architecture="mountain home",
        signature_shots=("mountain aerial", "valley view", "timber exterior"),
        supports=("views", "timber", "deck"),
    ),
    PropertyTypeProfile(
        "desert", ("desert", "high desert", "arid"),
        landscape="desert landscape arid terrain", architecture="desert home",
        signature_shots=("desert aerial", "rock formations", "wide horizon"),
        supports=("views", "xeriscape"),
    ),
    PropertyTypeProfile(
        "wooded", ("wooded", "timberland", "forested", "woodland"),
        landscape="dense woodland forest", architecture="home among trees",
        signature_shots=("forest canopy aerial", "wooded trail", "tree line"),
        supports=("woods", "trails", "timber"),
    ),
    PropertyTypeProfile(
        "recreational", ("recreational", "retreat", "getaway", "camp"),
        landscape="natural recreation land", architecture="retreat cabin",
        signature_shots=("recreation activity", "trail", "wide land reveal"),
        supports=("trails", "water", "campfire"),
    ),
    PropertyTypeProfile(
        "development_land", ("development land", "vacant land", "raw land", "buildable", "lot for sale", "acreage lot"),
        landscape="open vacant land parcel", architecture="surrounding neighborhood development",
        signature_shots=("parcel aerial", "road frontage", "boundary map"),
        supports=("road frontage", "utilities", "parcel"),
    ),
    PropertyTypeProfile(
        "luxury_estate", ("luxury estate", "estate", "manor", "mansion", "gated estate"),
        landscape="manicured estate grounds", architecture="grand estate architecture",
        signature_shots=("gated entrance", "estate aerial", "formal grounds"),
        supports=("gates", "grounds", "motor court"),
    ),
    PropertyTypeProfile(
        "rural_estate", ("rural estate", "country estate", "acreage estate"),
        landscape="expansive rural countryside", architecture="country estate home",
        signature_shots=("estate aerial", "tree-lined drive", "wide land reveal"),
        supports=("grounds", "drive", "acreage"),
    ),
    PropertyTypeProfile(
        "suburban", ("suburban", "subdivision", "single family home", "single-family", "townhouse"),
        landscape="suburban residential neighborhood", architecture="suburban family home",
        signature_shots=("street view", "front elevation", "backyard"),
        supports=("yard", "driveway", "garage"),
    ),
    PropertyTypeProfile(
        "urban", ("urban", "condo", "loft", "apartment", "downtown"),
        landscape="city skyline urban streets", architecture="modern urban residence",
        signature_shots=("skyline", "building exterior", "interior wide"),
        supports=("balcony", "views"),
    ),
)

_DEFAULT_PROFILE = PropertyTypeProfile(
    "property", (), landscape="surrounding countryside", architecture="residential property",
    signature_shots=("aerial overview", "exterior", "interior wide"),
)


def resolve_property_type(*sources: Optional[str]) -> PropertyTypeProfile:
    """First matching profile across the given text sources (property_type
    fact, narration, listing title...). Falls back to a neutral profile —
    an unrecognized type degrades gracefully instead of guessing."""
    blob = " ".join(s for s in sources if s).lower()
    if not blob.strip():
        return _DEFAULT_PROFILE
    for profile in PROPERTY_TYPES:
        for alias in profile.aliases:
            if re.search(rf"\b{re.escape(alias)}\b", blob):
                return profile
    return _DEFAULT_PROFILE


@dataclasses.dataclass(frozen=True)
class PropertyLocation:
    city: str = ""
    state: str = ""
    country: str = ""

    @property
    def has_any(self) -> bool:
        return bool(self.city or self.state or self.country)

    def context_phrase(self, *, prefer: str = "region") -> str:
        """Location words for a stock query.

        Deliberately prefers the REGION (state/province) over the city: a
        city name over-restricts stock search ("Vanceburg" returns nothing),
        while a region reliably returns representative landscape. The city is
        only used when there is no region at all."""
        if prefer == "region" and self.state:
            return self.state
        if self.state:
            return self.state
        if self.city:
            return self.city
        return self.country or ""


# What a structured fact implies visually. Keys are matched against the
# fact KEY first, then the fact VALUE, so both {"lot_size": "57 acres"} and
# {"feature": "pond"} resolve. Extending this is one line per fact type.
FACT_VISUAL_HINTS: Tuple[Tuple[str, str, str], ...] = (
    # (pattern, intent_type value, shot phrase)
    (r"\b(lot_size|acreage|acres?|hectares?)\b", "property_aerial", "aerial wide land reveal showing full acreage"),
    (r"\b(pond|lake)\b", "property_water", "dedicated pond reveal shot"),
    (r"\b(creek|river|stream|frontage|waterfront)\b", "property_water", "creek and water frontage shot"),
    (r"\b(barn|stable|outbuilding|shed)\b", "property_structure", "outbuilding exterior shot"),
    (r"\b(cabin|cabins|cottage)\b", "property_structure", "cabin exterior reveal"),
    (r"\b(pasture|paddock|field|meadow)\b", "property_land", "open pasture wide shot"),
    (r"\b(fireplace|kitchen|great\s?room|living\s?room|bedroom|bathroom)\b", "property_interior", "interior wide shot"),
    (r"\b(log|logs|chinking|hand[-\s]?hewn|timber\s?frame|beam)\b", "property_construction", "close construction detail"),
    (r"\b(driveway|gate|gated|entrance|lane)\b", "property_approach", "driveway approach shot"),
    (r"\b(porch|deck|patio|veranda)\b", "property_structure", "porch and exterior living shot"),
    (r"\b(dock|pier|boat)\b", "property_water", "dock and water access shot"),
    (r"\b(trail|trails|hunting|fishing|recreation)\b", "property_feature", "recreation on the land"),
    (r"\b(boundary|parcel|survey|plat)\b", "property_boundary", "boundary map overhead"),
    (r"\b(pool|spa|hot\s?tub)\b", "property_feature", "pool and outdoor living shot"),
    (r"\b(garage|carport)\b", "property_structure", "garage exterior shot"),
    (r"\b(view|views|overlook|vista)\b", "property_land", "scenic view from the property"),
)


def visual_hints_from_facts(facts: Optional[Dict[str, str]]) -> List[Tuple[str, str, str]]:
    """[(fact_key, intent_type, shot_phrase), ...] for every structured fact
    that carries a visual implication. Facts with no visual meaning (price,
    listing id, agent) are simply absent — never forced into a shot."""
    out: List[Tuple[str, str, str]] = []
    for key, value in (facts or {}).items():
        haystack = f"{key} {value}".lower()
        for pattern, intent_type, phrase in FACT_VISUAL_HINTS:
            if re.search(pattern, haystack, re.I):
                out.append((key, intent_type, phrase))
                break
    return out


# Features that must never be claimed unless the facts or the narration
# actually support them — the classic hallucination set for property video.
GUARDED_FEATURES: Tuple[str, ...] = (
    "pool", "garage", "barn", "stable", "dock", "fireplace", "basement",
    "mountain view", "ocean view", "waterfront", "acreage", "guest house",
    "horse", "vineyard", "elevator", "wine cellar", "tennis court",
)


def feature_is_supported(feature: str, narration: str, facts: Optional[Dict[str, str]]) -> bool:
    """True when a guarded feature is backed by the narration itself or by a
    structured fact. Anything else must not appear in a generated prompt."""
    feature = (feature or "").strip().lower()
    if not feature:
        return False
    if re.search(rf"\b{re.escape(feature)}", (narration or "").lower()):
        return True
    blob = " ".join(f"{k} {v}" for k, v in (facts or {}).items()).lower()
    return bool(re.search(rf"\b{re.escape(feature)}", blob))


def unsupported_features(text: str, narration: str, facts: Optional[Dict[str, str]]) -> List[str]:
    """Guarded features present in `text` that nothing supports — used to
    strip invented claims out of a generated prompt before it is used."""
    found = []
    lowered = (text or "").lower()
    for feature in GUARDED_FEATURES:
        if re.search(rf"\b{re.escape(feature)}", lowered) and not feature_is_supported(feature, narration, facts):
            found.append(feature)
    return found


# Stock queries describe CONTEXT, never the specific property. Commercial
# metadata is useless for finding a picture and actively poisons search.
_STOCK_NOISE_RE = re.compile(
    r"(\$[\d,]+(?:\.\d+)?|\b\d[\d,]*\b|\bmls\b|\blisting\s?id\b|\bzpid\b|"
    r"\bfor\s+sale\b|\brealtor\b|\bbroker\b|\bagent\b|\boffer\b|\bprice[ds]?\b)",
    re.I,
)


def clean_stock_query(query: str, *, max_words: int = 12) -> str:
    """Strips prices/ids/commercial metadata, removes repeated words, and
    caps length.

    Deduping matters: the landscape phrase is contributed by both the
    property-type profile and the per-shot subject, so without this a query
    reads "Florida open pasture paddock countryside ... open pasture paddock
    countryside" — burning half the search terms on a repeat."""
    cleaned = _STOCK_NOISE_RE.sub(" ", query or "")
    seen: set = set()
    words: List[str] = []
    for word in re.split(r"\s+", cleaned):
        word = word.strip()
        if not word:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        words.append(word)
        if len(words) >= max_words:
            break
    return " ".join(words)


def build_context_query(
    *,
    subject: str,
    profile: PropertyTypeProfile,
    location: PropertyLocation,
    use_location: bool = True,
) -> str:
    """Contextual stock query: location + property-type landscape + subject.

    Produces "Kentucky wooded forest countryside creek" rather than either a
    narration echo or a bare keyword."""
    parts: List[str] = []
    if use_location and location.has_any:
        place = location.context_phrase()
        if place:
            parts.append(place)
    if profile.landscape:
        parts.append(profile.landscape)
    if subject:
        parts.append(subject)
    return clean_stock_query(" ".join(parts))
