"""Multi-listing research storage + property-scoped candidate lookup.

One video can cover several listings. Each listing is researched
independently into its own directory and keeps its own identity, facts,
media and error state — there is deliberately no global "research media
pool", because the one thing that must never happen is Property A's photos
being used for a Property B scene.

Layout (both shapes supported):

    research/research.json                      <- legacy, single property
    research/properties/<property_id>/research.json   <- one dir per listing

The legacy single-property layout is still read exactly as before, so
existing projects keep working untouched (it's simply treated as a
one-listing library).
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from research.models import MediaCandidate, PropertyFact, ResearchResult
from research.package_importer import load_research_result

PROPERTIES_DIRNAME = "properties"


def property_id_for(url: str = "", address: str = "", name: str = "") -> str:
    """Stable, deterministic id for a listing. Derived from the listing URL
    when there is one (canonical by definition), else from address/name.
    Same input always yields the same id, so re-running research for a
    listing updates that listing rather than creating a duplicate."""
    basis = ""
    if (url or "").strip():
        parsed = urlparse(url.strip())
        basis = f"{parsed.netloc.lower()}{parsed.path.rstrip('/').lower()}"
    if not basis:
        basis = re.sub(r"\s+", " ", f"{address} {name}".strip().lower())
    if not basis:
        return ""
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    slug_source = basis.rsplit("/", 1)[-1] or basis
    slug = re.sub(r"[^a-z0-9]+", "-", slug_source.lower()).strip("-")[:40]
    return f"{slug}-{digest}" if slug else digest


def property_dir(research_dir: Path, property_id: str) -> Path:
    return Path(research_dir) / PROPERTIES_DIRNAME / property_id


@dataclasses.dataclass
class PropertyResearch:
    """One listing's complete research state."""

    property_id: str
    result: ResearchResult
    url: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.result and self.result.ok)

    @property
    def error(self) -> Optional[str]:
        return self.result.error if self.result else None

    def usable_media(self) -> List[MediaCandidate]:
        return [m for m in (self.result.media if self.result else []) if m.local_path]


@dataclasses.dataclass
class ResearchLibrary:
    """All listings researched for one project."""

    properties: List[PropertyResearch] = dataclasses.field(default_factory=list)

    def by_id(self, property_id: str) -> Optional[PropertyResearch]:
        for prop in self.properties:
            if prop.property_id == property_id:
                return prop
        return None

    def all_media(self) -> List[MediaCandidate]:
        """Every listing's media, each candidate still carrying its own
        property_id. Callers that resolve a property-scoped scene MUST
        filter by property_id — see ResearchAssetProvider, which does this
        before ranking."""
        out: List[MediaCandidate] = []
        for prop in self.properties:
            out.extend(prop.usable_media())
        return out

    def media_for(self, property_id: str) -> List[MediaCandidate]:
        """Fails closed: an unknown/blank property_id yields NO media rather
        than falling back to some other listing's photos."""
        if not property_id:
            return []
        prop = self.by_id(property_id)
        return prop.usable_media() if prop else []

    def get_media(self, property_id: str) -> List[MediaCandidate]:
        """Explicit fail-closed accessor (alias of media_for) — never returns
        another property's media for an unknown id."""
        return self.media_for(property_id)

    def facts_for(self, property_id: str) -> List["PropertyFact"]:
        if not property_id:
            return []
        prop = self.by_id(property_id)
        return list(prop.result.facts) if prop and prop.result else []

    def facts_dict_for(self, property_id: str) -> Dict[str, str]:
        """Flat {key: value} facts for one listing, in the shape the Property
        Script Analyzer's existing `property_facts` parameter expects."""
        if not property_id:
            return {}
        prop = self.by_id(property_id)
        return prop.result.facts_dict() if prop and prop.result else {}

    def has_media(self) -> bool:
        return any(p.usable_media() for p in self.properties)

    @property
    def property_ids(self) -> List[str]:
        return [p.property_id for p in self.properties]


def _tag_media(result: ResearchResult, property_id: str) -> None:
    """Stamp every candidate with its owning listing. Done at load time so
    no downstream code has to remember to do it."""
    if result is None:
        return
    result.property.property_id = property_id
    for media in result.media:
        media.property_id = property_id
    for fact in result.facts:
        fact.property_id = property_id


def load_research_library(research_dir: Path) -> ResearchLibrary:
    """Loads every researched listing for a project. Never raises."""
    research_dir = Path(research_dir)
    library = ResearchLibrary()
    if not research_dir.is_dir():
        return library

    multi_root = research_dir / PROPERTIES_DIRNAME
    if multi_root.is_dir():
        for child in sorted(p for p in multi_root.iterdir() if p.is_dir()):
            if not (child / "research.json").is_file():
                continue
            result = load_research_result(child)
            pid = child.name
            _tag_media(result, pid)
            library.properties.append(
                PropertyResearch(property_id=pid, result=result, url=result.property.source_url or "")
            )

    # Legacy single-property package written directly into research/ — still
    # fully supported; treated as a one-listing library.
    if (research_dir / "research.json").is_file():
        result = load_research_result(research_dir)
        pid = (
            property_id_for(
                url=result.property.source_url or "",
                address=result.property.address or "",
                name=result.property.name or "",
            )
            or "legacy"
        )
        if library.by_id(pid) is None:
            _tag_media(result, pid)
            library.properties.append(
                PropertyResearch(property_id=pid, result=result, url=result.property.source_url or "")
            )
    return library
