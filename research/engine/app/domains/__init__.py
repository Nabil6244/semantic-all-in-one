"""Domain adapter architecture.

A `DomainAdapter` adds domain-specific fact extraction, entity
normalization, and media role classification on top of the generic
(domain-agnostic) pipeline in `extraction/` and `media/`. The core engine
(researcher, ranking, dedup, storage, CLI) only ever talks to the
`DomainAdapter` interface — it never imports a specific adapter — so adding
a new domain means adding one file here and a registry entry, nothing else.

V2 ships two real adapters: `general` (the fallback — just the existing
domain-agnostic rule-based extraction) and `real_estate` (the first deep
adapter). The remaining files (products, travel, automotive, news, science)
register the *pattern* for future adapters without deep logic yet, per the
brief: "Do NOT implement every domain deeply yet."
"""
from __future__ import annotations

from typing import Dict, List, Optional, Protocol

from app.extraction.webpage import PageExtraction
from app.models.entity import NormalizedEntity
from app.models.fact import Fact
from app.models.media import MediaAsset


class DomainAdapter(Protocol):
    domain: str

    def extract_facts(self, page: PageExtraction, source_id: str) -> List[Fact]: ...

    def build_entity(
        self, entity_id: str, facts: List[Fact], page: PageExtraction, source_ids: List[str]
    ) -> Optional[NormalizedEntity]: ...

    def classify_media(self, assets: List[MediaAsset], page: PageExtraction) -> List[MediaAsset]: ...


_REGISTRY: Optional[Dict[str, DomainAdapter]] = None


def _build_registry() -> Dict[str, DomainAdapter]:
    from app.domains.automotive import AutomotiveAdapter
    from app.domains.general import GeneralAdapter
    from app.domains.news import NewsAdapter
    from app.domains.products import ProductsAdapter
    from app.domains.real_estate import RealEstateAdapter
    from app.domains.science import ScienceAdapter
    from app.domains.travel import TravelAdapter

    return {
        "real_estate": RealEstateAdapter(),
        "products": ProductsAdapter(),
        "travel": TravelAdapter(),
        "cars": AutomotiveAdapter(),
        "automotive": AutomotiveAdapter(),
        "news": NewsAdapter(),
        "science": ScienceAdapter(),
        "general": GeneralAdapter(),
    }


def get_adapter(domain: Optional[str]) -> DomainAdapter:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY.get(domain or "general", _REGISTRY["general"])
