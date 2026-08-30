"""Top-level orchestration: plan -> discover -> fetch/extract -> rank ->
dedup -> download -> package.

Bounded concurrency throughout; media is never downloaded before relevance
ranking has selected a small subset, and downloading itself is opt-in
(`download=True`) — a plain `run()` call is a discovery-only pass that
produces ranked candidates with no bytes fetched, matching the `--discover`
vs `--download` split in the CLI.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from app.dedup.media import MediaDeduplicator
from app.dedup.urls import SeenUrls, normalize_url, url_domain
from app.discovery.queries import generate_queries
from app.discovery.search import NullSearchProvider, SearchProvider, SearchResult
from app.domains import DomainAdapter, get_adapter
from app.extraction.facts import FactExtractor, detect_conflicts
from app.extraction.webpage import CrawlProvider, HttpxCrawlProvider, PageExtraction, fetch_and_extract
from app.media.discovery import discover_media
from app.media.downloader import download_media
from app.media.metadata import apply_license_info
from app.models.entity import NormalizedEntity
from app.models.fact import Fact
from app.models.media import MediaAsset, MediaType
from app.models.research import ResearchInput, ResearchPackage
from app.models.source import Source
from app.ranking.confidence import compute_confidence
from app.ranking.relevance import multi_text_similarity
from app.ranking.source import classify_source_type, score_source_quality
from app.research.planner import ResearchPlanner
from app.storage.cache import ResearchCache
from app.storage.package import ensure_output_dirs

# Conservative defaults — the engine should not crawl unbounded even when a
# caller forgets to set limits.
_DEFAULT_MAX_PAGES = 12
_DEFAULT_MAX_MEDIA_PER_PAGE = 20
_DEFAULT_MAX_TOTAL_MEDIA = 30


class Researcher:
    def __init__(
        self,
        crawl_provider: Optional[CrawlProvider] = None,
        search_provider: Optional[SearchProvider] = None,
        fact_extractor: Optional[FactExtractor] = None,
        planner: Optional[ResearchPlanner] = None,
        cache: Optional[ResearchCache] = None,
        fetch_concurrency: int = 5,
        download_concurrency: int = 5,
        max_queries: int = 5,
        max_search_results_per_query: int = 3,
        max_images: int = 12,
        max_videos: int = 6,
        max_pages: int = _DEFAULT_MAX_PAGES,
        max_media_per_page: int = _DEFAULT_MAX_MEDIA_PER_PAGE,
        max_total_media: int = _DEFAULT_MAX_TOTAL_MEDIA,
        max_depth: int = 0,
    ):
        self.crawl_provider = crawl_provider or HttpxCrawlProvider()
        self.search_provider = search_provider or NullSearchProvider()
        self.fact_extractor = fact_extractor  # None => domain adapter drives extraction
        self.planner = planner or ResearchPlanner()
        self.cache = cache
        self.fetch_concurrency = fetch_concurrency
        self.download_concurrency = download_concurrency
        self.max_queries = max_queries
        self.max_search_results_per_query = max_search_results_per_query
        self.max_images = max_images
        self.max_videos = max_videos
        self.max_pages = max_pages
        self.max_media_per_page = max_media_per_page
        self.max_total_media = max_total_media
        # V2 accepts max_depth for forward compatibility with a future
        # link-following pass; V2 itself does not follow links beyond the
        # direct/search-discovered URLs (see README "Known limitations").
        self.max_depth = max_depth

    async def _fetch_page(self, url: str, semaphore: asyncio.Semaphore) -> PageExtraction:
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
            self.cache.set_page_html(
                url, str(page.soup) if page.soup else "", page.final_url, page.status_code,
            )
        return page

    async def _search(self, query: str) -> List[SearchResult]:
        if self.cache is not None:
            cached = self.cache.get_search_results(query)
            if cached is not None:
                return [SearchResult(**r) for r in cached]
        results = await self.search_provider.search(query, max_results=self.max_search_results_per_query)
        if self.cache is not None:
            self.cache.set_search_results(query, [asdict(r) for r in results])
        return results

    async def run(
        self, research_input: ResearchInput, output_dir: Optional[Path] = None, download: bool = False,
    ) -> ResearchPackage:
        start_time = time.perf_counter()
        plan = self.planner.build(research_input)
        adapter: DomainAdapter = get_adapter(plan.resolved_domain)
        queries = generate_queries(
            research_input.topic, plan.entities, plan.resolved_domain, max_queries=self.max_queries
        )

        seen = SeenUrls()
        candidate_urls: List[str] = []
        primary_urls = set(plan.direct_urls)
        for url in plan.direct_urls:
            if seen.add_if_new(url):
                candidate_urls.append(url)

        for query in queries:
            results = await self._search(query)
            for result in results:
                if seen.add_if_new(result.url):
                    candidate_urls.append(result.url)

        candidate_urls = candidate_urls[: self.max_pages]

        semaphore = asyncio.Semaphore(self.fetch_concurrency)
        try:
            pages = await asyncio.gather(*[self._fetch_page(u, semaphore) for u in candidate_urls])
        finally:
            close = getattr(self.crawl_provider, "close", None)
            if close is not None:
                await close()

        sources: List[Source] = []
        facts: List[Fact] = []
        media_candidates: List[MediaAsset] = []
        normalized_entities: List[NormalizedEntity] = []

        for index, (url, page) in enumerate(zip(candidate_urls, pages), start=1):
            source_id = f"source_{index:03d}"
            final_url = page.final_url or url
            source_type = classify_source_type(final_url)
            is_primary = url in primary_urls
            quality = score_source_quality(
                source_type, page.accessible, bool(page.title), final_url.startswith("https"), is_primary,
            )
            sources.append(
                Source(
                    source_id=source_id,
                    source_url=url,
                    source_title=page.title,
                    source_type=source_type,
                    domain=url_domain(final_url),
                    status_code=page.status_code,
                    accessible=page.accessible,
                    access_status=page.access_status,
                    error=page.error,
                    quality_score=quality,
                    normalized_url=normalize_url(url),
                    is_primary=is_primary,
                )
            )

            if not page.accessible:
                continue

            page_facts = (
                self.fact_extractor.extract(page, source_id)
                if self.fact_extractor is not None
                else adapter.extract_facts(page, source_id)
            )
            for fact in page_facts:
                fact.source_type = source_type.value
            facts.extend(page_facts)

            entity = adapter.build_entity(f"entity_{index:03d}", page_facts, page, [source_id])
            if entity is not None:
                normalized_entities.append(entity)

            media = discover_media(page, source_id)[: self.max_media_per_page]
            media = adapter.classify_media(media, page)
            media = apply_license_info(media, page)
            for asset in media:
                asset.source_type = source_type.value
            media_candidates.extend(media)

        conflicts = detect_conflicts(facts)

        resolved_query = research_input.topic or (queries[0] if queries else None) or (
            (research_input.script or "")[:100] or None
        )

        topic_query = " ".join(
            filter(None, [research_input.topic, " ".join(plan.entities.subjects[:5])])
        ) or (research_input.script or "")[:200]

        for asset in media_candidates:
            asset.relevance_score = round(
                multi_text_similarity(topic_query, [asset.title, asset.description, asset.alt, asset.caption]), 4
            )
            provider_bonus = {
                "json_ld": 0.15, "og_image": 0.12, "schema_video_object": 0.15,
                "gallery": 0.08,
            }.get(asset.provider, 0.0)
            role_bonus = 0.1 if asset.role in ("hero", "video", "aerial_video") else 0.0
            size_bonus = 0.0
            if asset.width and asset.height:
                size_bonus = min((asset.width * asset.height) / (1920 * 1080), 1.0) * 0.1
            asset.quality_score = round(
                min(asset.relevance_score + provider_bonus + role_bonus + size_bonus, 1.0), 4
            )

        images = sorted(
            (m for m in media_candidates if m.media_type == MediaType.IMAGE),
            key=lambda m: m.quality_score, reverse=True,
        )
        videos = sorted(
            (m for m in media_candidates if m.media_type == MediaType.VIDEO),
            key=lambda m: m.quality_score, reverse=True,
        )
        selected = _dedup_by_source_url(images)[: self.max_images] + _dedup_by_source_url(videos)[: self.max_videos]
        selected = sorted(selected, key=lambda m: m.quality_score, reverse=True)[: self.max_total_media]

        downloaded: List[MediaAsset] = list(selected)
        if selected and output_dir is not None and download:
            media_dedup = MediaDeduplicator()
            if self.cache is not None:
                # hash -> local_path (not just the bare hashes) so a
                # cross-run duplicate resolves back to the existing file —
                # see downloader._try_reuse_existing.
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

        confidence = compute_confidence(facts, sources, conflicts)
        elapsed = round(time.perf_counter() - start_time, 4)

        statistics = {
            "num_sources": len(sources),
            "num_accessible_sources": sum(1 for s in sources if s.accessible),
            "num_facts": len(facts),
            "num_conflicts": len(conflicts),
            "num_normalized_entities": len(normalized_entities),
            "num_images_discovered": sum(1 for m in media_candidates if m.media_type == MediaType.IMAGE),
            "num_videos_discovered": sum(1 for m in media_candidates if m.media_type == MediaType.VIDEO),
            "num_media_selected": len(downloaded),
            "num_images_downloaded": sum(1 for m in downloaded if m.media_type == MediaType.IMAGE and m.downloaded),
            "num_videos_downloaded": sum(1 for m in downloaded if m.media_type == MediaType.VIDEO and m.downloaded),
            "num_queries": len(queries),
            "elapsed_seconds": elapsed,
        }

        research_id = f"research_{uuid4().hex[:10]}"
        package = ResearchPackage(
            research_id=research_id,
            topic=research_input.topic,
            query=resolved_query,
            domain=plan.resolved_domain,
            facts=facts,
            sources=sources,
            media=downloaded,
            conflicts=conflicts,
            queries=queries,
            entities=plan.entities,
            normalized_entities=normalized_entities,
            confidence=confidence,
            statistics=statistics,
        )
        package.metadata.elapsed_seconds = elapsed
        return package


def _dedup_by_source_url(assets: List[MediaAsset]) -> List[MediaAsset]:
    seen = set()
    result = []
    for asset in assets:
        norm = normalize_url(asset.source_url) if "://" in asset.source_url else asset.source_url
        if norm in seen:
            continue
        seen.add(norm)
        result.append(asset)
    return result
