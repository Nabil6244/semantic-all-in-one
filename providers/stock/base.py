"""
Stock subsystem shared types + StockProvider — the piece AssetManager actually
calls. Individual stock websites (Pexels, later Pixabay, ...) only need to
implement StockBackend.search(); StockProvider owns the whole
query -> search -> filter -> rank -> download pipeline once, identically, no
matter how many backends are configured.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
import threading
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
from . import downloader as _dl
from .downloader import MAX_BYTES, UHD_MAX_BYTES, DownloadCancelled, download_candidate, download_first_seconds
from .query import build_queries
from .ranking import filter_candidates, rank_candidates

_PICK_LOCK = threading.Lock()

_URL_SECRET = re.compile(r"((?:[?&]|\b)(?:key|api_key|apikey|access_token|token|client_secret)=)[^&\s'\"]+", re.IGNORECASE)


def redact_url_secrets(text: str) -> str:
    """An error text with every key/token URL parameter value hidden: a backend error can quote its request URL, and the log is a file."""
    return _URL_SECRET.sub(r"\1REDACTED", text or "")


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
    # Set by StockProvider.set_uhd: pick 4K files when the project accepts Ultra HD footage.
    uhd = False

    def search(self, query: str, media_type: str = "all", per_page: int = 15) -> List[Candidate]:
        raise NotImplementedError


COMMONS_TIMEOUT_S = 15.0        # the extra Wikimedia search for period pictures must never hold a scene for long
COMMONS_MAX_FAILURES = 2


class StockProvider(AssetProvider):
    name = "stock"
    source = AssetSource.STOCK

    def __init__(self, backends: List[StockBackend], cache: Optional[StockCache] = None):
        if not backends:
            raise ValueError("StockProvider needs at least one backend (e.g. PexelsBackend)")
        self.backends = backends
        self.cache = cache or StockCache()
        self.should_stop_scene = None
        # The project's "Accept Ultra HD (4K) footage" switch (see set_uhd).
        self.uhd = False

    def set_uhd(self, on: bool) -> None:
        """Pick 4K files when they exist (1 GB per clip cap, 1080p fallback) — or go back to HD-sized files."""
        on = bool(on)
        if on == self.uhd:
            return
        self.uhd = on
        for backend in self.backends:
            backend.uhd = on
        self.cache.clear_searches()   # results picked under the other setting point at other files

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
                log(f"[STOCK] {backend.name} search failed for \"{query}\": {redact_url_secrets(str(exc))}")
                results = []
            self.cache.set_search(backend.name, query, results, media_type)
            candidates.extend(results)
        return candidates

    def _period_commons(self, scene: SceneRow, media_type: str, log: LogFn) -> List[Candidate]:
        """Stock sites hold almost no period artwork. For an Explainer period request ("... historical painting") Wikimedia Commons (through Openverse, no key) is searched as well, for the subject
        plus the kind of art, and its results join the pool; the period gate then keeps only what says it is artwork of that subject. Never raises; any other request returns nothing."""
        if media_type == "video" or any(getattr(b, "source", "") == "wikimedia" for b in self.backends):
            return []
        try:
            from explainer.director import compose_pictures as cp
            from .openverse import OpenverseBackend
        except Exception:
            return []
        year = cp.request_year(scene.stock)
        if year is None:
            return []
        query = f"{cp.request_subject(scene.stock)} {'painting' if year < 1500 else 'engraving'}"
        cached = self.cache.get_search("wikimedia", query, "image")
        if cached is not None:
            return list(cached)
        if getattr(self, "_commons_failures", 0) >= COMMONS_MAX_FAILURES:
            return []                                    # a 40-minute video asks for dozens of period pictures: once the service has failed twice it is not asked again in this run
        try:
            backend = OpenverseBackend(source="wikimedia")
            backend.timeout = COMMONS_TIMEOUT_S
            results = backend.search(query, media_type="image", per_page=20)
            self._commons_failures = 0
        except Exception as exc:
            self._commons_failures = getattr(self, "_commons_failures", 0) + 1
            log(f"[STOCK] wikimedia search failed for \"{query}\": {redact_url_secrets(str(exc))}")
            return []
        for r in results:
            r.extra["collection"] = "wikimedia"
        self.cache.set_search("wikimedia", query, results, "image")
        return results

    def _period_gate(self, scene: SceneRow, candidates: List[Candidate], log: LogFn) -> List[Candidate]:
        """An Explainer picture request for a time before 1800 ends with era words ("... historical painting"). Only results whose own text says they are period artwork of that subject
        (not a toy army, a reenactment or a modern photo of ruins) may be picked; the rest are dropped here, so the next-best real result wins. Any other request is untouched."""
        if scene.stock_media_type == "video" or not candidates:
            return candidates
        try:
            from explainer.director import compose_pictures as cp
        except Exception:
            return candidates
        year = cp.request_year(scene.stock)
        if year is None:
            return candidates
        keep = []
        for c in candidates:
            meta = {"source_url": c.source_url, "alt": c.extra.get("alt", ""), "tags": c.extra.get("tags", ""), "title": c.extra.get("title", "")}
            if cp.vet_picture(meta, year, cp.request_subject(scene.stock), curated=c.extra.get("collection") == "wikimedia")[0]:
                keep.append(c)
        log(f"[STOCK] Scene {scene.scene_number} -> period gate kept {len(keep)} of {len(candidates)} results")
        return keep

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
        if (scene.asset_type or "").lower() in ("commons_image", "commons_video"):
            # a real subject (What If's second source after NASA): never broadened to one word -- "Saturn rings ringlets Voyager 1"
            # ended as "Saturn" and "Voyager", and took a portrait of a person (#016)
            queries = [q for k, q in enumerate(queries) if k == 0 or len(q.split()) >= 2]
        fallback = None
        for i, query in enumerate(queries):
            if self._scene_stopped(scene.scene_number):
                return None
            suffix = " (broadened)" if i else ""
            log(f"[STOCK] Scene {scene.scene_number} -> searching {media_type} \"{query}\"{suffix}")
            candidates = [c for c in self._search_all(query, media_type, log) if c.asset_id not in exclude_ids]
            if i == 0:
                candidates += [c for c in self._period_commons(scene, media_type, log) if c.asset_id not in exclude_ids]
            # Defense in depth: backends are expected to honor media_type already,
            # but never let a wrong-kind candidate through the picker regardless.
            if media_type != "all":
                candidates = [c for c in candidates if c.media_type.value == media_type]
            filtered = filter_candidates(candidates)
            filtered = self._period_gate(scene, filtered, log)
            if resolved is not None:
                from style_engine.visual_selection import style_candidate_gate

                filtered = style_candidate_gate(filtered, resolved)
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
                uhd=self.uhd,
                # Opt-in only (0.0 = off): set by the Property Video
                # workflow, where an unrelated clip is worse than none.
                # The normal YouTube workflow never sets this, so its
                # behavior is byte-for-byte unchanged.
                min_relevance=getattr(self, "min_stock_relevance", 0.0),
                log=log,
            )
            if ranked:
                with _PICK_LOCK:
                    # A picture already used in this project is the last choice, not just a lower score: with 50 scenes asking for
                    # similar things the same few top results kept winning. Scenes picking at the same time see each other's choice.
                    used = self.cache.used_asset_ids()
                    fresh = [c for c in ranked if c.asset_id not in used]
                    if fresh:
                        self.cache.record_used(fresh[0].asset_id)
                        return fresh[0]
                fallback = fallback or ranked[0]   # everything it found was used already: try the broader query, keep this if nothing better turns up
        return fallback

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

    def _rescue(self, scene: SceneRow, candidate: Candidate, images_dir: Path, log: LogFn, exc: Exception) -> AssetResult:
        """A file that was too big, too slow or broken, with no smaller file offered: keep only the first seconds of the clip
        (copied, no re-encode), else take the next best result once. The scene fails only when all of that fails."""
        stopped = lambda: self._scene_stopped(scene.scene_number)  # noqa: E731
        problems = [str(exc)]
        if candidate.media_type == MediaType.VIDEO:
            keep = _dl.UHD_KEEP_SECONDS
            log(f"[STOCK] Scene {scene.scene_number} -> {exc}; keeping only the first {keep:.0f}s of the clip instead")
            try:
                path = download_first_seconds(candidate, images_dir, scene.scene_number, keep, max_bytes=MAX_BYTES, should_stop=stopped,
                                              timeout_s=300.0)   # a stalled server must not hold the scene (or Generate) for long
                return self._finish(scene, candidate, path, candidate.width, candidate.height, min(candidate.duration or keep, keep), log)
            except DownloadCancelled as exc2:
                return AssetResult(scene.scene_number, None, None, scene.stock_source, SceneStatus.FAILED, error=f"Download failed: {exc2}")
            except Exception as exc2:
                problems.append(f"the first {keep:.0f}s failed too: {exc2}")
                log(f"[STOCK] Scene {scene.scene_number} -> the first {keep:.0f}s could not be kept either ({exc2})")
        if not getattr(self, "_rescuing", False) and not stopped():
            other = self._pick(scene, log, exclude_ids={str(candidate.asset_id)})
            if other is not None:
                log(f"[STOCK] Scene {scene.scene_number} -> {problems[0]}; trying the next result instead")
                self._rescuing = True
                try:
                    got = self._download(scene, other, images_dir, log)
                finally:
                    self._rescuing = False
                if got.status != SceneStatus.FAILED:
                    return got
                problems.append(f"the next result failed too: {got.error}")
        return AssetResult(scene.scene_number, None, None, scene.stock_source, SceneStatus.FAILED, error="Download failed: " + "; ".join(problems))

    def _download(self, scene: SceneRow, candidate: Candidate, images_dir: Path, log: LogFn) -> AssetResult:
        source = scene.stock_source
        log(f"[STOCK] Scene {scene.scene_number} -> selected {candidate.provider} asset {candidate.asset_id} ({candidate.width}x{candidate.height})")
        stopped = lambda: self._scene_stopped(scene.scene_number)  # noqa: E731
        width, height, duration = candidate.width, candidate.height, candidate.duration
        fallback = candidate.extra.get("hd_fallback") or {}
        try:
            if self.uhd and fallback.get("url") and _dl.free_bytes(images_dir) < UHD_MAX_BYTES + _dl.RENDER_MARGIN_BYTES:
                raise IOError(f"less than {(UHD_MAX_BYTES + _dl.RENDER_MARGIN_BYTES) // 2**30} GB free on the disk")
            keep = _dl.UHD_KEEP_SECONDS
            if self.uhd and candidate.media_type == MediaType.VIDEO and (candidate.duration or 0) > keep + 1:
                log(f"[STOCK] Scene {scene.scene_number} -> keeping the first {keep:.0f}s of a {candidate.duration:.0f}s clip")
                path = download_first_seconds(
                    candidate, images_dir, scene.scene_number, keep, max_bytes=UHD_MAX_BYTES, should_stop=stopped,
                )
                duration = keep
            else:
                path = download_candidate(
                    candidate,
                    images_dir,
                    scene.scene_number,
                    log=log,
                    should_stop=stopped,
                    max_bytes=UHD_MAX_BYTES if self.uhd else MAX_BYTES,
                )
        except DownloadCancelled as exc:
            return AssetResult(
                scene.scene_number, None, None, source, SceneStatus.FAILED,
                error=f"Download failed: {exc}",
            )
        except Exception as exc:
            # A large (4K) file that was too big, too slow or broken: take the same clip's HD file instead of failing the scene.
            if not fallback.get("url"):
                return self._rescue(scene, candidate, images_dir, log, exc)
            log(f"[STOCK] Scene {scene.scene_number} -> {width}x{height} download failed ({exc}); using the {fallback.get('width')}x{fallback.get('height')} file instead")
            try:
                path = download_candidate(
                    candidate, images_dir, scene.scene_number, log=log, should_stop=stopped,
                    max_bytes=MAX_BYTES, url=fallback["url"],
                )
            except Exception as exc2:
                return AssetResult(
                    scene.scene_number, None, None, source, SceneStatus.FAILED,
                    error=f"Download failed: {exc}; the HD fallback failed too: {exc2}",
                )
            width, height = int(fallback.get("width") or 0), int(fallback.get("height") or 0)
            duration = candidate.duration
        return self._finish(scene, candidate, path, width, height, duration, log)

    def _finish(self, scene: SceneRow, candidate: Candidate, path: Path, width, height, duration, log: LogFn) -> AssetResult:
        """A downloaded file checked and recorded as the scene's asset."""
        source = scene.stock_source
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
                "width": width,
                "height": height,
                "duration": duration,
            },
        )
