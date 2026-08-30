"""
Stock subsystem shared types + StockProvider — the piece AssetManager actually
calls. Individual stock websites (Pexels, later Pixabay, ...) only need to
implement StockBackend.search(); StockProvider owns the whole
query -> search -> filter -> rank -> download pipeline once, identically, no
matter how many backends are configured.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import List, Optional, Set

from ..base import (
    AssetProvider,
    AssetResult,
    AssetSource,
    LogFn,
    MediaType,
    SceneRow,
    SceneStatus,
    sniff_media_kind,
)
from .cache import StockCache
from .downloader import download_candidate
from .query import build_queries
from .ranking import filter_candidates, rank_candidates


@dataclasses.dataclass
class Candidate:
    provider: str  # "pexels", later "pixabay", ...
    asset_id: str
    media_type: MediaType
    url: str  # best-quality direct download URL
    width: int
    height: int
    duration: Optional[float] = None  # seconds, videos only
    author: str = ""
    source_url: str = ""  # human-viewable page on the provider's site
    thumbnail_url: str = ""
    extra: dict = dataclasses.field(default_factory=dict)

    @property
    def orientation(self) -> str:
        if self.height <= 0:
            return "unknown"
        ratio = self.width / self.height
        if ratio > 1.05:
            return "landscape"
        if ratio < 0.95:
            return "portrait"
        return "square"


class StockBackend:
    name = "base"

    def search(self, query: str, media_type: str = "all", per_page: int = 15) -> List[Candidate]:
        raise NotImplementedError


class StockProvider(AssetProvider):
    name = "stock"
    source = AssetSource.STOCK

    def __init__(self, backends: List[StockBackend], cache: Optional[StockCache] = None):
        if not backends:
            raise ValueError("StockProvider needs at least one backend (e.g. PexelsBackend)")
        self.backends = backends
        self.cache = cache or StockCache()
        self.should_stop_scene = None

    def _scene_stopped(self, scene_number: str) -> bool:
        cb = getattr(self, "should_stop_scene", None)
        return bool(cb and cb(scene_number))

    def _search_all(self, query: str, media_type: str, log: LogFn) -> List[Candidate]:
        candidates: List[Candidate] = []
        for backend in self.backends:
            cached = self.cache.get_search(backend.name, query, media_type)
            if cached is not None:
                candidates.extend(cached)
                continue
            try:
                results = backend.search(query, media_type=media_type)
            except Exception as exc:
                log(f"[STOCK] {backend.name} search failed for \"{query}\": {exc}")
                results = []
            self.cache.set_search(backend.name, query, results, media_type)
            candidates.extend(results)
        return candidates

    def _pick(self, scene: SceneRow, log: LogFn, exclude_ids: Optional[Set[str]] = None) -> Optional[Candidate]:
        exclude_ids = exclude_ids or set()
        media_type = scene.stock_media_type  # "image" | "video" | "all" — see SceneRow
        resolved = getattr(self, "resolved_style", None)
        history = getattr(self, "selection_history", None)
        ctx = None
        if resolved is not None or history is not None:
            from style_engine.visual_selection import build_selection_context

            ctx = build_selection_context(scene, resolved, history)
        if ctx and not ctx.manual_authority:
            from style_engine.visual_selection import smart_media_queries

            queries = smart_media_queries(scene, resolved, manual=False)
        else:
            queries = build_queries(scene.stock)
        for i, query in enumerate(queries):
            if self._scene_stopped(scene.scene_number):
                return None
            suffix = " (broadened)" if i else ""
            log(f"[STOCK] Scene {scene.scene_number} -> searching {media_type} \"{query}\"{suffix}")
            candidates = [c for c in self._search_all(query, media_type, log) if c.asset_id not in exclude_ids]
            # Defense in depth: backends are expected to honor media_type already,
            # but never let a wrong-kind candidate through the picker regardless.
            if media_type != "all":
                candidates = [c for c in candidates if c.media_type.value == media_type]
            filtered = filter_candidates(candidates)
            if not filtered:
                continue
            ranked = rank_candidates(
                filtered,
                query,
                self.cache.used_asset_ids(),
                scene=scene,
                provider_use_counts=self.cache.provider_use_counts(),
                selection_context=ctx,
                required_duration=getattr(self, "required_duration", None),
                # Opt-in only (0.0 = off): set by the Property Video
                # workflow, where an unrelated clip is worse than none.
                # The normal YouTube workflow never sets this, so its
                # behavior is byte-for-byte unchanged.
                min_relevance=getattr(self, "min_stock_relevance", 0.0),
                log=log,
            )
            if ranked:
                return ranked[0]
        return None

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        source = scene.stock_source
        if not scene.stock:
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error="No stock keywords given for this scene.",
            )
        best = self._pick(scene, log)
        if best is None:
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error=f"No suitable stock {scene.stock_media_type} result found for \"{scene.stock}\".",
            )
        return self._download(scene, best, images_dir, log)

    def regenerate(
        self, scene: SceneRow, images_dir: Path, exclude: Optional[dict] = None, log: LogFn = print
    ) -> AssetResult:
        exclude_ids: Set[str] = set()
        if exclude and exclude.get("provider_asset_id"):
            exclude_ids.add(str(exclude["provider_asset_id"]))
        best = self._pick(scene, log, exclude_ids=exclude_ids)
        if best is None:
            return AssetResult(
                scene.scene_number, None, None, scene.stock_source, SceneStatus.FAILED,
                error=f"No alternative stock {scene.stock_media_type} result found for \"{scene.stock}\".",
            )
        return self._download(scene, best, images_dir, log)

    def _download(self, scene: SceneRow, candidate: Candidate, images_dir: Path, log: LogFn) -> AssetResult:
        source = scene.stock_source
        log(f"[STOCK] Scene {scene.scene_number} -> selected {candidate.provider} asset {candidate.asset_id} ({candidate.width}x{candidate.height})")
        try:
            path = download_candidate(
                candidate,
                images_dir,
                scene.scene_number,
                log=log,
                should_stop=lambda: self._scene_stopped(scene.scene_number),
            )
        except Exception as exc:
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error=f"Download failed: {exc}",
            )

        # Hard content check — don't trust the candidate's advertised media_type
        # or the downloaded filename's extension alone. If asset_type explicitly
        # demands image/video, the actual bytes must match or this must fail,
        # not silently accept the wrong kind of file for the scene.
        expected = scene.stock_media_type
        if expected != "all":
            actual = sniff_media_kind(path)
            if actual is not None and actual != expected:
                path.unlink(missing_ok=True)
                return AssetResult(
                    scene.scene_number, None, None, source, SceneStatus.FAILED,
                    error=(
                        f"Stock provider returned a {actual} for a stock_{expected} scene "
                        f"(expected {expected.upper()}, got {actual.upper()}) — not using it."
                    ),
                )

        self.cache.record_used(candidate.asset_id)
        log(f"[STOCK] Scene {scene.scene_number} -> downloaded {path.name}")
        return AssetResult(
            scene_number=scene.scene_number,
            path=path,
            media_type=candidate.media_type,
            source=source,
            status=SceneStatus.READY,
            metadata={
                "provider": candidate.provider,
                "provider_asset_id": candidate.asset_id,
                "author": candidate.author,
                "source_url": candidate.source_url,
                "width": candidate.width,
                "height": candidate.height,
                "duration": candidate.duration,
            },
        )
