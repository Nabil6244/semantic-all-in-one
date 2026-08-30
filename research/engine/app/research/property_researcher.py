"""V3: Property-Centric Media Research pipeline.

The V2 `Researcher` treats a research run as "gather evidence about a
topic." This module answers a narrower, harder question: "find THIS exact
property/listing, and collect media that actually depicts it" — for the use
case of illustrating an existing narration script about one specific
listing.

Pipeline: identify target property -> discover same-property sources ->
extract facts (matching sources only) -> discover + gallery-scope + gate
media by property identity -> merge duplicate/size-variant media -> rank ->
(optional) download, bounded by `max_media_per_property`.

Reuses V2 building blocks throughout (fetch_and_extract, discover_media,
download_media, MediaDeduplicator, classify_source_type/score_source_quality,
compute_confidence, RealEstateAdapter) — this module only adds the
property-identity glue, never duplicates ranking/dedup/download logic.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from app.dedup.media import MediaDeduplicator
from app.dedup.urls import SeenUrls, normalize_url, url_domain
from app.discovery.property_sources import generate_property_queries
from app.discovery.queries import generate_queries
from app.discovery.search import NullSearchProvider, SearchProvider
from app.domains.real_estate import RealEstateAdapter
from app.entities.property_matching import build_property_identity, match_property
from app.extraction.facts import detect_conflicts
from app.extraction.webpage import CrawlProvider, HttpxCrawlProvider, PageExtraction, fetch_and_extract
from app.media.discovery import discover_media
from app.media.downloader import download_media
from app.media.metadata import apply_license_info
from app.media.probe import ProbeCache, ProbeStatus, probe_images
from app.media.variants import group_variants
from app.media.quality import quality_tier, tier_score
from app.media.property_scope import (
    PROPERTY_MATCH_THRESHOLD,
    analyze_gallery_context,
    apply_property_scope,
    classify_rejection_reason,
    merge_same_image_size_variants,
)
from app.models.entity import NormalizedEntity
from app.models.fact import Fact
from app.models.media import MediaAsset, MediaType
from app.models.property import PropertyIdentity, SamePropertyMatch
from app.models.research import PropertyPackage, ResearchInput, ResearchPackage
from app.models.source import Source
from app.ranking.confidence import compute_confidence
from app.ranking.relevance import multi_text_similarity
from app.ranking.source import classify_source_type, score_source_quality
from app.research.planner import ResearchPlanner
from app.storage.cache import ResearchCache
from app.storage.package import ensure_output_dirs

_DEFAULT_MAX_PAGES = 10
_DEFAULT_MAX_QUERIES = 8
_DEFAULT_MAX_MEDIA_PER_PROPERTY = 18
_MIN_MEDIA_BEFORE_ESCALATION = 2
_MAX_TOPIC_FALLBACK_QUERIES = 5
"""Topic-only mode (no URL, no structured PropertyIdentity yet) has nothing
for generate_property_queries() to key off — bounded separately from
max_queries so this fallback stays deliberately small regardless of a
larger configured max_queries."""

# Ranking weights for the property-aware final score (see README):
# final = property_match + role_quality + visual_quality + source_priority + relevance + uniqueness
_ROLE_WEIGHTS = {
    "hero": 1.0, "video": 0.9, "aerial_video": 0.95, "aerial": 0.8,
    "gallery": 0.6, "floor_plan": 0.55, "map": 0.4,
}

# Source match-classification bands, applied to sources that AREN'T the
# target's own defining page (which is always PRIMARY) or a confirmed match
# (SECONDARY_SAME_PROPERTY). Anything scoring below _UNCERTAIN_FLOOR is
# UNRELATED; the band between that and the match threshold is genuinely
# ambiguous evidence rather than a confident rejection.
_UNCERTAIN_FLOOR = 0.2


def classify_source_match(is_target: bool, page_match: Optional[SamePropertyMatch], accessible: bool) -> Optional[str]:
    """PRIMARY / SECONDARY_SAME_PROPERTY / UNRELATED / UNCERTAIN — see README
    V3/V4 sections. Returns None only when accessible with no page_match at
    all (shouldn't normally happen for an accessible page)."""
    if not accessible:
        return "UNCERTAIN"  # couldn't evaluate — not the same as a confident rejection
    if is_target:
        return "PRIMARY"
    if page_match is None:
        return None
    if page_match.is_match:
        return "SECONDARY_SAME_PROPERTY"
    if page_match.match_score >= _UNCERTAIN_FLOOR:
        return "UNCERTAIN"
    return "UNRELATED"


def _tier_histogram(assets: List[MediaAsset]) -> dict:
    """Counts by measured quality tier. `unknown` covers assets whose real
    dimensions could not be measured — deliberately not folded into tier 4,
    since "small" and "unmeasured" are different facts."""
    hist: dict = {}
    for asset in assets:
        if asset.media_type != MediaType.IMAGE:
            continue
        key = f"tier{asset.quality_tier}" if asset.quality_tier else "unknown"
        hist[key] = hist.get(key, 0) + 1
    return hist


def _pseudo_page_from_text(text: str, url: str = "text://input") -> PageExtraction:
    """Wraps raw text (a script or topic string) in a minimal PageExtraction
    so the existing RealEstateAdapter fact-extraction (which only needs
    `.visible_text`/`.title`/`.json_ld`/`.accessible`) can run on it without
    any HTML/network involved."""
    return PageExtraction(
        url=url, final_url=url, accessible=True, status_code=None, error=None,
        title=None, visible_text=text or "", json_ld=[], soup=None,
    )


class PropertyResearcher:
    def __init__(
        self,
        crawl_provider: Optional[CrawlProvider] = None,
        escalation_provider: Optional[CrawlProvider] = None,
        search_provider: Optional[SearchProvider] = None,
        planner: Optional[ResearchPlanner] = None,
        cache: Optional[ResearchCache] = None,
        fetch_concurrency: int = 5,
        download_concurrency: int = 5,
        max_queries: int = _DEFAULT_MAX_QUERIES,
        max_search_results_per_query: int = 3,
        max_pages: int = _DEFAULT_MAX_PAGES,
        max_media_per_property: int = _DEFAULT_MAX_MEDIA_PER_PROPERTY,
        escalation_timeout_seconds: float = 45.0,
        probe_media: bool = False,
        probe_concurrency: int = 8,
        probe_client=None,
    ):
        self.crawl_provider = crawl_provider or HttpxCrawlProvider()
        self.escalation_provider = escalation_provider
        self.escalation_timeout_seconds = escalation_timeout_seconds
        self.search_provider = search_provider or NullSearchProvider()
        self.planner = planner or ResearchPlanner()
        self.cache = cache
        self.fetch_concurrency = fetch_concurrency
        self.download_concurrency = download_concurrency
        self.max_queries = max_queries
        self.max_search_results_per_query = max_search_results_per_query
        self.max_pages = max_pages
        self.max_media_per_property = max_media_per_property
        # Opt-in, mirroring `run(download=...)`: probing performs network
        # I/O, so — like every other network dependency on this class — it
        # is injected/enabled by the caller rather than happening silently.
        # The CLI turns it on for real runs; hermetic tests leave it off.
        self.probe_media = probe_media
        self.probe_concurrency = probe_concurrency
        self.probe_client = probe_client
        self.probe_cache = ProbeCache()
        self.adapter = RealEstateAdapter()

    async def _probe_media(self, assets: List[MediaAsset]) -> dict:
        """Measure real dimensions for image candidates and record them on
        each asset. Returns a small stats dict for the package.

        Preserves the declared values in `declared_*` before overwriting
        `width`/`height` with the measurement, so provenance survives and
        existing consumers of `width`/`height` keep working — they simply
        get a truer number.
        """
        images = [a for a in assets if a.media_type == MediaType.IMAGE and a.source_url]
        for asset in images:
            # Whatever we hold pre-probe is, by definition, declared.
            if asset.declared_width is None and asset.declared_height is None:
                asset.declared_width, asset.declared_height = asset.width, asset.height

        if not self.probe_media or not images:
            for asset in images:
                asset.quality_tier = None
            return {"enabled": bool(self.probe_media), "attempted": 0, "measured": 0, "failed": 0}

        try:
            results = await probe_images(
                [a.source_url for a in images],
                concurrency=self.probe_concurrency,
                http_client=self.probe_client,
                cache=self.probe_cache,
            )
        except Exception:  # noqa: BLE001 - probing is an optimization, never fatal
            return {"enabled": True, "attempted": len(images), "measured": 0, "failed": len(images)}

        measured = 0
        for asset in images:
            result = results.get(asset.source_url)
            if result is None:
                continue
            asset.probe_status = result.status.value
            if result.measured:
                asset.actual_width, asset.actual_height = result.actual_width, result.actual_height
                # `width`/`height` become the best-known values (measured).
                asset.width, asset.height = result.actual_width, result.actual_height
                asset.quality_tier = quality_tier(result.long_side)
                measured += 1

        return {
            "enabled": True,
            "attempted": len(images),
            "measured": measured,
            "failed": len(images) - measured,
            "cache_hits": self.probe_cache.hits,
            "distinct_urls": len(self.probe_cache),
        }

    async def _fetch(self, url: str, semaphore: asyncio.Semaphore) -> PageExtraction:
        if self.cache is not None:
            cached = self.cache.get_page_html(url)
            if cached:
                from bs4 import BeautifulSoup
                from app.extraction.metadata import extract_page_metadata
                from app.extraction.structured_data import parse_json_ld
                from app.models.source import AccessStatus

                html = cached["html"]
                soup = BeautifulSoup(html, "lxml")
                meta = extract_page_metadata(html)
                return PageExtraction(
                    url=url, final_url=cached.get("final_url", url), accessible=True,
                    status_code=cached.get("status_code"), error=None, access_status=AccessStatus.OK,
                    title=meta["title"], description=meta["description"],
                    canonical_url=meta["canonical_url"], published_date=meta["published_date"],
                    visible_text=meta["visible_text"], opengraph=meta["opengraph"],
                    json_ld=parse_json_ld(soup), soup=soup, provider="cache",
                )

        async with semaphore:
            page = await fetch_and_extract(url, self.crawl_provider)
        if self.cache is not None and page.accessible:
            self.cache.set_page_html(url, str(page.soup) if page.soup else "", page.final_url, page.status_code)
        return page

    async def _maybe_escalate(
        self, url: str, page: PageExtraction, media: List[MediaAsset], facts: List[Fact],
    ) -> tuple[PageExtraction, List[MediaAsset], List[Fact]]:
        """Section 7: escalate to a heavier provider (e.g. Crawl4AI) when the
        cheap fetch looks thin for a listing page — suspiciously few media
        candidates, or key listing facts missing — rather than escalating
        every page unconditionally."""
        if self.escalation_provider is None or not page.accessible:
            return page, media, facts

        core_keys = {"price", "acreage", "address", "address_city", "square_feet", "square_footage"}
        has_core_facts = any(f.key in core_keys for f in facts)
        thin_media = len(media) < _MIN_MEDIA_BEFORE_ESCALATION

        if has_core_facts and not thin_media:
            return page, media, facts

        try:
            # Real-world exercise against Crawl4AI found it can hang for
            # 1000+ seconds on a single stubborn page (internal retries past
            # its own 60s navigation timeout) — a hard wall-clock bound here
            # is required so one bad URL can never blow up a bounded run's
            # time budget. Falls back to the cheap result on timeout, same
            # as any other escalation failure.
            escalated_page = await asyncio.wait_for(
                fetch_and_extract(url, self.escalation_provider), timeout=self.escalation_timeout_seconds,
            )
        except Exception:  # noqa: BLE001 - escalation is best-effort, never fatal (includes asyncio.TimeoutError)
            return page, media, facts

        if not escalated_page.accessible:
            return page, media, facts

        escalated_media = discover_media(escalated_page, source_id="__escalation_probe__")
        escalated_facts = self.adapter.extract_facts(escalated_page, "__escalation_probe__")
        if len(escalated_media) > len(media) or (not has_core_facts and any(f.key in core_keys for f in escalated_facts)):
            return escalated_page, escalated_media, escalated_facts
        return page, media, facts

    async def _search(self, query: str) -> list:
        if self.cache is not None:
            cached = self.cache.get_search_results(query)
            if cached is not None:
                from app.discovery.search import SearchResult
                return [SearchResult(**r) for r in cached]
        results = await self.search_provider.search(query, max_results=self.max_search_results_per_query)
        if self.cache is not None:
            from dataclasses import asdict
            self.cache.set_search_results(query, [asdict(r) for r in results])
        return results

    async def run(
        self, research_input: ResearchInput, output_dir: Optional[Path] = None, download: bool = False,
    ) -> ResearchPackage:
        start_time = time.perf_counter()

        seen = SeenUrls()
        candidate_urls: List[str] = []
        primary_urls = set(research_input.urls)
        for url in research_input.urls:
            if seen.add_if_new(url):
                candidate_urls.append(url)

        semaphore = asyncio.Semaphore(self.fetch_concurrency)

        # --- Phase 1: fetch every directly-supplied URL to establish a
        # candidate target identity from each. A real fetched page's
        # structured data is always preferred over script/topic text-only
        # heuristics. (Facts are re-extracted per-source later once source
        # numbering is final; here we only need them to pick the target.)
        direct_pages = await asyncio.gather(*[self._fetch(u, semaphore) for u in candidate_urls])

        candidates_with_identity = []
        for url, page in zip(candidate_urls, direct_pages):
            if not page.accessible:
                continue
            facts = self.adapter.extract_facts(page, "__pending__")
            entity = self.adapter.build_entity("__pending__", facts, page, [])
            identity = build_property_identity(entity, facts) if entity else PropertyIdentity()
            candidates_with_identity.append((url, page, facts, identity))

        text_source = research_input.script or research_input.topic or ""
        weak_identity: Optional[PropertyIdentity] = None
        if text_source:
            pseudo_page = _pseudo_page_from_text(text_source)
            pseudo_facts = self.adapter.extract_facts(pseudo_page, "__script__")
            pseudo_entity = self.adapter.build_entity("__script__", pseudo_facts, pseudo_page, [])
            weak_identity = build_property_identity(pseudo_entity, pseudo_facts) if pseudo_entity else None
            if weak_identity is not None and not weak_identity.city:
                # RealEstateAdapter's address fields are JSON-LD-only — free
                # text like "near Clio, Alabama" never populates city/state
                # through it. Reuse the planner's existing gazetteer/regex
                # location extractor (already used for query generation
                # elsewhere) rather than adding new NLP for this.
                from app.research.planner import extract_locations

                us_states = {
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
                locations = extract_locations(text_source)
                states = [loc for loc in locations if loc.lower() in us_states]
                cities = [loc for loc in locations if loc.lower() not in us_states]
                if states:
                    weak_identity.state = states[0]
                if cities:
                    weak_identity.city = cities[0]
                if weak_identity.city and weak_identity.state:
                    weak_identity.evidence.append(f"location (heuristic): {weak_identity.city}, {weak_identity.state}")
                    weak_identity.confidence = round(min(weak_identity.confidence + 0.1, 1.0), 4)

        # A URL establishes the canonical target property — once any direct
        # URL has produced an identity, search-discovered pages are ONLY
        # ever compared *against* it (below); they never contribute to
        # choosing it. This block intentionally does not change when a URL
        # is present — see has_url_identity.
        strong_candidates = [c for c in candidates_with_identity if c[3].has_strong_identifier()]
        has_url_identity = bool(candidates_with_identity)

        if strong_candidates:
            target_url, target_page, target_facts, target_identity = max(strong_candidates, key=lambda c: c[3].confidence)
        elif candidates_with_identity:
            target_url, target_page, target_facts, target_identity = max(candidates_with_identity, key=lambda c: c[3].confidence)
        else:
            # No URL given at all — resolved below, after search discovery,
            # from among whatever pages search actually finds (a pure-text
            # weak_identity has no address/listing-id/geo/property-name and
            # can never satisfy match_property's has_strong_or_medium gate,
            # so using it directly as the target would silently reject every
            # candidate — see app/entities/property_matching.py).
            target_url, target_page, target_facts, target_identity = None, None, [], PropertyIdentity()

        # --- Phase 2: property-centric discovery of additional sources ---
        if has_url_identity:
            # Existing behavior, unchanged: search for OTHER pages about the
            # already-confirmed target property.
            queries = generate_property_queries(target_identity, max_queries=self.max_queries)
        else:
            # Topic/script-only: nothing to key an address-based query off
            # yet, so discover candidate PROPERTIES first via the general
            # topic-/script-aware query generator (already used by the V2
            # multi-source pipeline) — the target is then chosen from what's
            # actually found, below.
            plan = self.planner.build(research_input)
            queries = generate_queries(
                research_input.topic, entities=plan.entities, domain="real_estate",
                max_queries=min(self.max_queries, _MAX_TOPIC_FALLBACK_QUERIES),
            )

        discovered_urls: List[str] = []
        for query in queries:
            for result in await self._search(query):
                if seen.add_if_new(result.url):
                    candidate_urls.append(result.url)
                    discovered_urls.append(result.url)

        candidate_urls = candidate_urls[: self.max_pages]
        # candidate_urls already includes the directly-fetched ones; fetch
        # only the ones we haven't fetched yet (search-discovered).
        already_fetched_urls = {url for url, *_ in candidates_with_identity}
        to_fetch = [u for u in candidate_urls if u not in already_fetched_urls]
        extra_pages = await asyncio.gather(*[self._fetch(u, semaphore) for u in to_fetch]) if to_fetch else []
        pages_by_url = dict(zip(to_fetch, extra_pages))

        discovered_candidates_with_identity: list = []
        if not has_url_identity:
            # No URL was given — choose the target from among the pages
            # search actually discovered (same "strongest identifier wins,
            # else highest confidence" priority already used for direct
            # URLs above), instead of an under-specified text-only guess.
            for url in discovered_urls:
                page = pages_by_url.get(url)
                if page is None or not page.accessible:
                    continue
                facts = self.adapter.extract_facts(page, "__pending__")
                entity = self.adapter.build_entity("__pending__", facts, page, [])
                identity = build_property_identity(entity, facts) if entity else PropertyIdentity()
                discovered_candidates_with_identity.append((url, page, facts, identity))

            strong_discovered = [c for c in discovered_candidates_with_identity if c[3].has_strong_identifier()]
            if strong_discovered:
                target_url, target_page, target_facts, target_identity = max(strong_discovered, key=lambda c: c[3].confidence)
            elif discovered_candidates_with_identity:
                target_url, target_page, target_facts, target_identity = max(discovered_candidates_with_identity, key=lambda c: c[3].confidence)
            elif weak_identity is not None:
                # Last resort: nothing fetched matched anything usable —
                # keep the text-only identity so the run at least reports
                # what it *thinks* the topic is about, even though (per the
                # gate above) it won't accept any source/media against it.
                target_url, target_page, target_facts, target_identity = None, None, [], weak_identity
            else:
                target_url, target_page, target_facts, target_identity = None, None, [], PropertyIdentity()

        try:
            close = getattr(self.crawl_provider, "close", None)
            if close is not None:
                await close()
        except Exception:  # noqa: BLE001
            pass

        all_page_records = list(zip([c[0] for c in candidates_with_identity], [c[1] for c in candidates_with_identity])) + list(zip(to_fetch, extra_pages))
        # Preserve original candidate_urls order for stable, deterministic source numbering.
        ordered = [(u, dict(all_page_records)[u]) for u in candidate_urls if u in dict(all_page_records)]

        sources: List[Source] = []
        all_facts: List[Fact] = []
        all_media: List[MediaAsset] = []
        normalized_entities: List[NormalizedEntity] = []
        media_candidates_seen = 0
        rejected_media_log: List[dict] = []

        for index, (url, page) in enumerate(ordered, start=1):
            source_id = f"source_{index:03d}"
            final_url = page.final_url or url
            source_type = classify_source_type(final_url)
            is_primary = url in primary_urls
            quality = score_source_quality(source_type, page.accessible, bool(page.title), final_url.startswith("https"), is_primary)

            page_match = None
            page_facts: List[Fact] = []
            page_media: List[MediaAsset] = []

            if page.accessible:
                page_facts = self.adapter.extract_facts(page, source_id)
                page_media_raw = discover_media(page, source_id)
                page, page_media_raw, page_facts = await self._maybe_escalate(url, page, page_media_raw, page_facts)
                # re-tag with the real source_id after a possible escalation swap
                for m in page_media_raw:
                    m.source_id = source_id
                for f in page_facts:
                    f.source_id = source_id
                media_candidates_seen += len(page_media_raw)

                candidate_entity = self.adapter.build_entity(f"entity_{index:03d}", page_facts, page, [source_id])
                candidate_identity = build_property_identity(candidate_entity, page_facts) if candidate_entity else PropertyIdentity()

                if url == target_url:
                    # The page that *defines* the target must always match
                    # itself — running it back through the weighted-evidence
                    # gauntlet is wrong when that page's own data is thin
                    # (e.g. no structured address at all): it could fail to
                    # cross the match threshold against its own fingerprint,
                    # which would silently zero out the entire pipeline.
                    page_match = SamePropertyMatch(
                        is_match=True, confidence=target_identity.confidence, match_score=1.0,
                        reasons=["this page defines the target property"],
                    )
                else:
                    page_match = match_property(candidate_identity, target_identity)

                if page_match.is_match:
                    page_media = self.adapter.classify_media(page_media_raw, page)
                    page_media = apply_license_info(page_media, page)
                    gallery_ctx = analyze_gallery_context(page.soup, page.final_url) if page.soup is not None else None
                    page_media = apply_property_scope(page_media, target_identity, page_match, gallery_ctx)

                    gated, rejected = [], []
                    for m in page_media:
                        (gated if m.property_match_score >= PROPERTY_MATCH_THRESHOLD else rejected).append(m)
                    for m in rejected:
                        rejected_media_log.append({
                            "source_id": source_id, "source_url": m.source_url,
                            "media_type": m.media_type.value,
                            "property_match_score": m.property_match_score,
                            "rejection_reason": classify_rejection_reason(m),
                        })
                    page_media = gated

                    for m in page_media:
                        m.source_type = source_type.value
                        if text_source:
                            m.script_relevance = round(
                                multi_text_similarity(text_source, [m.title, m.alt, m.caption, m.role]), 4
                            )
                    all_facts.extend(page_facts)
                    all_media.extend(page_media)
                    if candidate_entity is not None:
                        normalized_entities.append(candidate_entity)

            sources.append(Source(
                source_id=source_id, source_url=url, source_title=page.title, source_type=source_type,
                domain=url_domain(final_url), status_code=page.status_code, accessible=page.accessible,
                access_status=page.access_status, error=page.error, quality_score=quality,
                normalized_url=normalize_url(url), is_primary=is_primary,
                is_same_property=page_match.is_match if page_match else None,
                property_match_score=page_match.match_score if page_match else None,
                property_match_reasons=page_match.reasons if page_match else [],
                match_classification=classify_source_match(url == target_url, page_match, page.accessible),
            ))

        conflicts = detect_conflicts(all_facts)

        # --- Phase 3: merge same-image size variants (dedup), then rank ---
        source_priority = {s.source_id: s.quality_score for s in sources}

        # --- Phase 3b: MEASURE actual pixel dimensions before ranking ---
        # Until this point every size we have is *declared* by the page (a
        # srcset `w` descriptor, an embedded-JSON width, an <img width>) or
        # inferred from a URL — none of which is proof. Ranking on those
        # picks the wrong variant whenever a CDN lies or the declared value
        # is simply absent. Probing reads each image's own header bytes, so
        # selection below runs on measured fact. Best-effort throughout: an
        # unprobeable image keeps its declared numbers and is scored via the
        # "unknown" tier rather than being dropped.
        #
        # Ordering matters: probing runs on EVERY candidate, before variant
        # election, because electing the largest rendition of a photo is
        # only possible once the renditions have actually been measured.
        # Merging first (the previous order) meant the winner was chosen
        # from declared/guessed sizes — which is how the smallest srcset
        # entry ended up winning.
        # --- Phase 3b2: Zillow derivative upgrade ---
        # Zillow often exposes only a small derivative (<hash>-p_c.jpg,
        # 316x234) while its CDN holds the same photo far larger. Recover the
        # largest GENUINE derivative before probing/election so everything
        # downstream measures and ranks the best available source. Scoped to
        # zillowstatic.com URLs only; never upscales (an upgrade is taken
        # only when measured pixels strictly increase); non-fatal on failure.
        zillow_upgrades = 0
        try:
            from app.media.zillow_derivatives import apply_upgrades, upgrade_zillow_urls

            images_only = [a for a in all_media if a.media_type == MediaType.IMAGE]
            if images_only:
                ups = await upgrade_zillow_urls(
                    [a.source_url for a in images_only],
                    http_client=self.probe_client,
                    cache=self.probe_cache,
                    concurrency=self.probe_concurrency,
                )
                zillow_upgrades = apply_upgrades(images_only, ups)
        except Exception:  # noqa: BLE001 - upgrade is an optimization, never fatal
            zillow_upgrades = 0

        probe_stats = await self._probe_media(all_media)

        # --- Phase 3c: elect one asset per underlying photo ---
        # Variant families collapse on measured size, and every discarded
        # URL is retained on the winner as an alternate source.
        unique_media = group_variants(all_media, source_priority=source_priority)

        for asset in unique_media:
            role_quality = _ROLE_WEIGHTS.get(asset.role or "", 0.3)
            # Measured tier when we have one; otherwise tier_score()'s
            # explicit "unknown" band — never a declared-size number
            # masquerading as a measurement.
            visual_quality = tier_score(asset.quality_tier)
            src_priority = source_priority.get(asset.source_id or "", 0.5)
            relevance = asset.relevance_score or (0.3 if asset.title or asset.alt or asset.caption else 0.0)
            uniqueness = max(0.0, 1.0 - min(len(asset.alternate_sources) * 0.05, 0.2))

            final_score = (
                0.35 * asset.property_match_score
                + 0.20 * role_quality
                + 0.15 * visual_quality
                + 0.15 * src_priority
                + 0.10 * relevance
                + 0.05 * uniqueness
            )
            asset.quality_score = round(min(final_score, 1.0), 4)

        ranked = sorted(unique_media, key=lambda m: m.quality_score, reverse=True)
        selected = ranked[: self.max_media_per_property]

        downloaded: List[MediaAsset] = list(selected)
        if selected and output_dir is not None and download:
            media_dedup = MediaDeduplicator()
            if self.cache is not None:
                # Seed with hash -> local_path (not just the bare hashes) so
                # a duplicate detected on a later run can be resolved back
                # to the file a prior run already saved, instead of being
                # skipped with no usable path (see downloader._try_reuse_existing).
                cached = {h: v.get("local_path") for h, v in self.cache.all_items("media_hash").items()}
                media_dedup.seed(file_hashes=cached)
            dirs = ensure_output_dirs(output_dir)
            downloaded = await download_media(
                selected, dirs["root"] / "media", concurrency=self.download_concurrency, dedup=media_dedup,
            )
            if self.cache is not None:
                for asset in downloaded:
                    if asset.file_hash:
                        self.cache.set("media_hash", asset.file_hash, {"media_id": asset.media_id, "local_path": asset.local_path})

        confidence = compute_confidence(all_facts, sources, conflicts)
        elapsed = round(time.perf_counter() - start_time, 4)

        matching_sources = sum(1 for s in sources if s.is_same_property)
        rejection_reason_counts: dict = {}
        for entry in rejected_media_log:
            reason = entry["rejection_reason"] or "unknown"
            rejection_reason_counts[reason] = rejection_reason_counts.get(reason, 0) + 1

        # When more than one plausible property identity was seen — whether
        # from multiple directly-fetched URLs, or (topic/script-only mode)
        # from multiple search-discovered pages — expose the full ranked
        # list (with confidence) instead of silently picking one. Ambiguity
        # is only meaningful for the URL-less case: a URL is the canonical
        # target by definition (see has_url_identity above), so it's never
        # flagged as ambiguous even if other candidate URLs were also given.
        candidate_properties = sorted(
            (
                {
                    "url": c[0], "confidence": c[3].confidence,
                    "canonical_address": c[3].canonical_address,
                    "property_name": c[3].property_name,
                    "chosen": c[0] == target_url,
                }
                for c in (candidates_with_identity + discovered_candidates_with_identity)
            ),
            key=lambda c: c["confidence"], reverse=True,
        )
        _AMBIGUITY_CONFIDENCE_GAP = 0.15
        property_ambiguous = (
            not has_url_identity
            and len(candidate_properties) > 1
            and (candidate_properties[0]["confidence"] - candidate_properties[1]["confidence"]) < _AMBIGUITY_CONFIDENCE_GAP
        )

        statistics = {
            "properties": 1,
            "candidate_properties": candidate_properties,
            "property_ambiguous": property_ambiguous,
            "sources": len(sources),
            "num_accessible_sources": sum(1 for s in sources if s.accessible),
            "num_same_property_sources": matching_sources,
            "num_rejected_sources": sum(1 for s in sources if s.is_same_property is False),
            "num_uncertain_sources": sum(1 for s in sources if s.match_classification == "UNCERTAIN"),
            "media_candidates": media_candidates_seen,
            "property_scoped_media": len(all_media),
            "rejected_media": len(rejected_media_log),
            "rejection_reasons": rejection_reason_counts,
            "unique_media": len(unique_media),
            "variant_families": len({m.variant_group for m in unique_media if m.variant_group}),
            "variants_collapsed": sum(len(m.alternate_sources) for m in unique_media),
            "media_selected": len(selected),
            "media_probed": probe_stats,
            "zillow_derivative_upgrades": zillow_upgrades,
            "quality_tiers": _tier_histogram(unique_media),
            "selected_quality_tiers": _tier_histogram(selected),
            "num_facts": len(all_facts),
            "num_conflicts": len(conflicts),
            "num_images_downloaded": sum(1 for m in downloaded if m.media_type == MediaType.IMAGE and m.downloaded),
            "num_videos_downloaded": sum(1 for m in downloaded if m.media_type == MediaType.VIDEO and m.downloaded),
            "num_video_references": sum(1 for m in downloaded if m.media_type == MediaType.VIDEO and not m.downloaded and m.provider in ("youtube_embed", "vimeo_embed")),
            "num_download_duplicates": sum(1 for m in downloaded if not m.downloaded and m.download_note and ("duplicate" in m.download_note)),
            "num_download_failed": sum(
                1 for m in downloaded
                if not m.downloaded and m.provider not in ("youtube_embed", "vimeo_embed")
                and not (m.download_note and "duplicate" in m.download_note)
            ),
            "elapsed_seconds": elapsed,
        }

        research_id = f"research_{uuid4().hex[:10]}"
        package = ResearchPackage(
            research_id=research_id,
            topic=research_input.topic,
            query=target_identity.canonical_address or research_input.topic,
            domain="real_estate",
            facts=all_facts,
            sources=sources,
            media=downloaded,
            conflicts=conflicts,
            queries=queries,
            normalized_entities=normalized_entities,
            confidence=confidence,
            property=PropertyPackage(identity=target_identity, confidence=target_identity.confidence),
            statistics=statistics,
        )
        package.metadata.elapsed_seconds = elapsed
        return package
