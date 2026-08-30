"""General-purpose domain adapter — the fallback for any domain without a
dedicated adapter. Pure passthrough onto the existing domain-agnostic
extraction (`RuleBasedFactExtractor`), plus a light JSON-LD `@type` mapping
for entity typing."""
from __future__ import annotations

from typing import List, Optional

from app.extraction.facts import RuleBasedFactExtractor
from app.extraction.webpage import PageExtraction
from app.models.entity import EntityType, NormalizedEntity
from app.models.fact import Fact
from app.models.media import MediaAsset

_JSONLD_TYPE_TO_ENTITY_TYPE = {
    "person": EntityType.PERSON,
    "organization": EntityType.ORGANIZATION,
    "corporation": EntityType.ORGANIZATION,
    "localbusiness": EntityType.ORGANIZATION,
    "ngo": EntityType.ORGANIZATION,
    "place": EntityType.PLACE,
    "touristattraction": EntityType.PLACE,
    "product": EntityType.PRODUCT,
    "vehicle": EntityType.PRODUCT,
    "car": EntityType.PRODUCT,
    "event": EntityType.EVENT,
    "article": EntityType.ARTICLE,
    "newsarticle": EntityType.ARTICLE,
    "blogposting": EntityType.ARTICLE,
    "scholarlyarticle": EntityType.ARTICLE,
    "videoobject": EntityType.VIDEO,
    "realestatelisting": EntityType.PROPERTY,
    "house": EntityType.PROPERTY,
    "singlefamilyresidence": EntityType.PROPERTY,
    "apartment": EntityType.PROPERTY,
    "accommodation": EntityType.PROPERTY,
    "residence": EntityType.PROPERTY,
}


def infer_entity_type(page: PageExtraction) -> EntityType:
    for entity in page.json_ld:
        raw_type = entity.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        for t in types:
            if not t:
                continue
            mapped = _JSONLD_TYPE_TO_ENTITY_TYPE.get(str(t).lower())
            if mapped:
                return mapped
    return EntityType.UNKNOWN


class GeneralAdapter:
    domain = "general"

    def extract_facts(self, page: PageExtraction, source_id: str) -> List[Fact]:
        return RuleBasedFactExtractor().extract(page, source_id)

    def build_entity(
        self, entity_id: str, facts: List[Fact], page: PageExtraction, source_ids: List[str]
    ) -> Optional[NormalizedEntity]:
        if not page.accessible:
            return None
        attributes = {}
        for fact in facts:
            attributes.setdefault(fact.key, fact.value)
        return NormalizedEntity(
            entity_id=entity_id,
            entity_type=infer_entity_type(page),
            name=page.title,
            location=None,
            attributes=attributes,
            source_ids=source_ids,
        )

    def classify_media(self, assets: List[MediaAsset], page: PageExtraction) -> List[MediaAsset]:
        return assets
