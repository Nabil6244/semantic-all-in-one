"""Script/topic-aware planning: entity extraction + domain detection.

V1 uses rule-based (regex/heuristic) extraction only — no LLM required.
`EntityExtractor` is the seam for a future LLM-backed extractor: it must
return the same `ExtractedEntities` shape so `research/researcher.py` and
`discovery/queries.py` don't need to change when one is added.

We deliberately do NOT rewrite or summarize the script — only pull structured
signals out of it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from app.models.research import ExtractedEntities, ResearchInput

# --- domain detection ---------------------------------------------------

_DOMAIN_KEYWORDS = {
    "real_estate": ("acre", "bedroom", "bathroom", "sqft", "square feet", "listing", "for sale", "farmhouse", "realtor", "mls"),
    "travel": ("itinerary", "destination", "flight", "hotel", "visa", "tourist", "trip", "vacation"),
    "cars": ("engine", "horsepower", "mpg", "sedan", "suv", "trim", "msrp", "0-60"),
    "products": ("price", "review", "specs", "warranty", "sku", "add to cart"),
    "history": ("century", "war", "empire", "dynasty", "ancient", "historical"),
    "science": ("research", "study", "hypothesis", "experiment", "journal", "peer-reviewed"),
    "companies": ("ceo", "headquarters", "founded", "revenue", "acquisition", "ipo"),
    "news": ("breaking", "reported", "according to", "sources say", "press release"),
    "biographies": ("born", "career", "biography", "life of", "died"),
}

_VISUAL_CUE_WORDS = (
    "aerial", "drone", "footage", "image of", "photo of", "shot of", "view of",
    "interior", "exterior", "landscape", "close-up", "b-roll", "footage of",
)

# minimal built-in gazetteer; good enough for heuristic location tagging
# without pulling in a full NER model.
_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
}

_DATE_RE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}/\d{1,2}/\d{2,4}"
    r"|\b(?:19|20)\d{2}\b)"
)
_NUMBER_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\s*[a-zA-Z%$]*\b")
_PROPER_NOUN_RE = re.compile(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def guess_domain(text: str) -> str:
    lowered = (text or "").lower()
    scores = {domain: sum(lowered.count(kw) for kw in kws) for domain, kws in _DOMAIN_KEYWORDS.items()}
    best_domain, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_domain if best_score > 0 else "unknown"


def extract_dates(text: str) -> List[str]:
    return sorted(set(_DATE_RE.findall(text)))


def extract_numbers(text: str) -> List[str]:
    return sorted(set(m.strip() for m in _NUMBER_RE.findall(text)))


def extract_locations(text: str) -> List[str]:
    found = set()
    lowered = text.lower()
    for state in _US_STATES:
        if state in lowered:
            found.add(state.title())
    # "in <Proper Noun>" / "near <Proper Noun>" is a decent location cue.
    for match in re.finditer(r"\b(?:in|near|at|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})", text):
        found.add(match.group(1))
    return sorted(found)


def extract_proper_nouns(text: str) -> List[str]:
    candidates = {m.strip() for m in _PROPER_NOUN_RE.findall(text)}
    # drop single common sentence-starter words picked up without context
    return sorted(c for c in candidates if len(c) > 2)


def extract_claims(text: str) -> List[str]:
    sentences = _SENTENCE_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if s.strip() and _NUMBER_RE.search(s)]


def extract_visual_requirements(text: str) -> List[str]:
    sentences = _SENTENCE_SPLIT_RE.split(text)
    hits = []
    lowered_sentences = [(s, s.lower()) for s in sentences]
    for original, lowered in lowered_sentences:
        if any(cue in lowered for cue in _VISUAL_CUE_WORDS):
            hits.append(original.strip())
    return hits


class EntityExtractor(Protocol):
    """Interface for pluggable entity extraction. `RuleBasedEntityExtractor`
    is the V1 default; an LLM-backed implementation can be dropped in later
    without changing planner/researcher code."""

    def extract(self, text: str) -> ExtractedEntities: ...


class RuleBasedEntityExtractor:
    def extract(self, text: str) -> ExtractedEntities:
        if not text:
            return ExtractedEntities()
        proper_nouns = extract_proper_nouns(text)
        locations = extract_locations(text)
        subjects = [p for p in proper_nouns if p not in locations][:15]
        return ExtractedEntities(
            entities=proper_nouns[:25],
            locations=locations,
            dates=extract_dates(text),
            numbers=extract_numbers(text)[:25],
            subjects=subjects,
            claims=extract_claims(text)[:25],
            visual_requirements=extract_visual_requirements(text),
        )


@dataclass
class ResearchPlan:
    research_input: ResearchInput
    resolved_domain: str
    entities: ExtractedEntities
    direct_urls: List[str] = field(default_factory=list)


class ResearchPlanner:
    def __init__(self, entity_extractor: Optional[EntityExtractor] = None):
        self.entity_extractor = entity_extractor or RuleBasedEntityExtractor()

    def build(self, research_input: ResearchInput) -> ResearchPlan:
        source_text = " ".join(filter(None, [research_input.topic, research_input.script]))
        entities = self.entity_extractor.extract(source_text)

        domain = research_input.domain
        if not domain or domain == "auto":
            domain = guess_domain(source_text) if source_text else "unknown"

        return ResearchPlan(
            research_input=research_input,
            resolved_domain=domain,
            entities=entities,
            direct_urls=list(research_input.urls),
        )
