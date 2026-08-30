"""Multi-property research jobs: several listings, researched independently.

One video can cover several listings. Each URL is researched as its OWN
complete pipeline run with its OWN target `PropertyIdentity`, into its OWN
output directory. There is deliberately no global media pool: the single
thing that must never happen is property A's photographs being offered for a
scene about property B.

Isolation is structural, not a filter applied afterwards:

- Each property gets a separate `PropertyResearcher.run()`. The existing
  per-page `match_property` gate then works FOR isolation instead of against
  it — when researching A, a page about B simply fails A's identity match
  and contributes nothing. (Passing both URLs to one run does the opposite:
  one becomes the target and the other is discarded as UNRELATED.)
- Each property writes to `properties/<property_id>/`, so packages cannot
  overwrite or read each other.
- Every asset is stamped with its owning `property_id`, so an asset stays
  traceable even if a consumer later merges packages.
- Lookups FAIL CLOSED: an unknown or blank `property_id` returns nothing.
  Returning "everything" for a missing key is precisely the bug this module
  exists to make impossible.

Backward compatibility: a single-URL run is untouched — same
`PropertyResearcher`, same root-level `research.json`. The per-property
directory layout is used only for genuine multi-property jobs.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from app.models.fact import Fact
from app.models.media import MediaAsset
from app.models.research import ResearchInput, ResearchPackage

PROPERTIES_DIRNAME = "properties"
JOB_FILENAME = "research_job.json"


def property_id_for(url: str = "", address: str = "", name: str = "") -> str:
    """Stable, deterministic id for one listing.

    Derived from the listing URL when there is one (a URL is canonical by
    definition), else from address/name. The same input always yields the
    same id, so re-running research for a listing UPDATES that listing
    rather than creating a duplicate.

    This intentionally mirrors the identical helper on the consumer side
    (Semantic YT Studio's research/library.py) byte for byte, so ids agree
    across the process boundary. Changing one without the other would
    silently split a listing into two.
    """
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


@dataclass
class PropertyResult:
    """One listing's complete, self-contained research state."""

    property_id: str
    source_url: str
    package: Optional[ResearchPackage] = None
    output_dir: Optional[Path] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.package is not None

    def media(self) -> List[MediaAsset]:
        return list(self.package.media) if self.package else []

    def facts(self) -> List[Fact]:
        return list(self.package.facts) if self.package else []


@dataclass
class PropertyResearchJob:
    """All listings researched together. Lookups are keyed by property_id
    and FAIL CLOSED."""

    job_id: str = field(default_factory=lambda: f"job_{uuid4().hex[:10]}")
    properties: List[PropertyResult] = field(default_factory=list)

    # --- lookups (fail closed) -------------------------------------------

    def by_id(self, property_id: str) -> Optional[PropertyResult]:
        if not property_id or not str(property_id).strip():
            return None
        wanted = str(property_id).strip()
        for prop in self.properties:
            if prop.property_id == wanted:
                return prop
        return None

    def get_media(self, property_id: str) -> List[MediaAsset]:
        """Media for exactly one listing.

        FAILS CLOSED: a blank, missing, or unknown `property_id` returns an
        EMPTY list — never every asset. A caller that has lost track of
        which listing it is talking about must get nothing, because the
        alternative is silently illustrating one house with another."""
        prop = self.by_id(property_id)
        return prop.media() if prop is not None else []

    def get_facts(self, property_id: str) -> List[Fact]:
        """Facts for exactly one listing. Fails closed, as `get_media`."""
        prop = self.by_id(property_id)
        return prop.facts() if prop is not None else []

    @property
    def property_ids(self) -> List[str]:
        return [p.property_id for p in self.properties]

    def ok_properties(self) -> List[PropertyResult]:
        return [p for p in self.properties if p.ok]

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "properties": [
                {
                    "property_id": p.property_id,
                    "source_url": p.source_url,
                    "ok": p.ok,
                    "error": p.error,
                    "output_dir": str(p.output_dir) if p.output_dir else None,
                    "research_json": (
                        f"{PROPERTIES_DIRNAME}/{p.property_id}/research.json" if p.ok else None
                    ),
                    "media_manifest": (
                        f"{PROPERTIES_DIRNAME}/{p.property_id}/metadata/media_manifest.json"
                        if p.ok else None
                    ),
                    "num_media": len(p.media()),
                    "num_facts": len(p.facts()),
                    "canonical_address": (
                        p.package.property.identity.canonical_address if p.ok else None
                    ),
                }
                for p in self.properties
            ],
        }


def property_dir(output_dir: Path, property_id: str) -> Path:
    return Path(output_dir) / PROPERTIES_DIRNAME / property_id


def _stamp(package: ResearchPackage, property_id: str, source_url: str) -> None:
    """Tag every asset and fact with its owning listing."""
    for asset in package.media:
        asset.property_id = property_id
    package.statistics["property_id"] = property_id
    package.statistics["source_url"] = source_url


async def run_property_job(
    urls: List[str],
    researcher_factory: Callable[[], "object"],
    output_dir: Optional[Path] = None,
    download: bool = False,
    topic: Optional[str] = None,
    script: Optional[str] = None,
    write_package_fn: Optional[Callable] = None,
    write_manifest_fn: Optional[Callable] = None,
) -> PropertyResearchJob:
    """Research each URL as an independent property.

    `researcher_factory` returns a FRESH researcher per property — a new
    pipeline, a new target identity, a new probe cache. Sharing one
    researcher across properties would be the easiest way to reintroduce
    exactly the cross-contamination this module prevents.

    One listing failing never invalidates the others: its error is recorded
    on its own `PropertyResult` and the job continues.
    """
    job = PropertyResearchJob()
    seen: Dict[str, str] = {}

    for url in urls:
        url = (url or "").strip()
        if not url:
            continue
        property_id = property_id_for(url=url)
        if not property_id:
            continue
        if property_id in seen:
            # The same listing given twice is one listing, not two.
            continue
        seen[property_id] = url

        target_dir = property_dir(output_dir, property_id) if output_dir else None
        result = PropertyResult(property_id=property_id, source_url=url, output_dir=target_dir)
        try:
            researcher = researcher_factory()
            package = await researcher.run(
                ResearchInput(urls=[url], topic=topic, script=script),
                output_dir=target_dir,
                download=download,
            )
            _stamp(package, property_id, url)
            result.package = package
            if target_dir is not None:
                if write_package_fn is not None:
                    write_package_fn(package, target_dir)
                if write_manifest_fn is not None:
                    write_manifest_fn(package, target_dir, property_id, url)
        except Exception as exc:  # noqa: BLE001 - one listing must not sink the job
            result.error = f"{type(exc).__name__}: {exc}"
        job.properties.append(result)

    return job
