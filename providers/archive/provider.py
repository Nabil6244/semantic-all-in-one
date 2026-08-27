"""Internet Archive clip provider — asset_type=archive_video."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from providers.base import (
    AssetProvider,
    AssetResult,
    AssetSource,
    LogFn,
    MediaType,
    SceneRow,
    SceneStatus,
    sniff_media_kind,
)
from providers.media_clip.ffmpeg_clip import download_clip, probe_duration
from providers.media_clip.queries import expanded_media_queries
from providers.media_clip.ranking import rank_by_text
from providers.youtube.base import compute_clip_window, compute_fallback_timestamp

from .ia_backend import ArchiveCandidate, InternetArchiveBackend

DEFAULT_CLIP_DURATION = 3.5
DEFAULT_MAX_RESULTS = 8


class ArchiveProvider(AssetProvider):
    name = "archive"
    source = AssetSource.ARCHIVE_VIDEO

    def __init__(
        self,
        backend: Optional[InternetArchiveBackend] = None,
        clip_duration: float = DEFAULT_CLIP_DURATION,
        max_results: int = DEFAULT_MAX_RESULTS,
    ):
        self.backend = backend or InternetArchiveBackend(max_results=max_results)
        self.clip_duration = clip_duration
        self.should_stop_scene = None

    def _scene_stopped(self, scene: SceneRow) -> bool:
        cb = getattr(self, "should_stop_scene", None)
        return bool(callable(cb) and cb(str(scene.scene_number)))

    def _search(self, scene: SceneRow, log: LogFn, exclude_ids: Set[str]) -> List[ArchiveCandidate]:
        resolved = getattr(self, "resolved_style", None)
        history = getattr(self, "selection_history", None)
        ctx = None
        if resolved is not None or history is not None:
            from style_engine.visual_selection import build_selection_context

            ctx = build_selection_context(scene, resolved, history)
        if ctx and not ctx.manual_authority:
            from style_engine.visual_selection import smart_media_queries

            queries = smart_media_queries(scene, resolved)
        else:
            queries = expanded_media_queries(scene)
        if not queries:
            return []
        sn = scene.scene_number
        primary = queries[0]
        pooled: List[ArchiveCandidate] = []
        seen_ids: Set[str] = set()
        for index, query in enumerate(queries, start=1):
            if self._scene_stopped(scene):
                return []
            if query.startswith("identifier:"):
                ident = query.split(":", 1)[1].strip()
                log(f"[ARCHIVE] Scene {sn} -> direct identifier \"{ident}\"")
                cand = self.backend.resolve_identifier(ident)
                if cand and cand.asset_id not in exclude_ids and cand.asset_id not in seen_ids:
                    pooled.append(cand)
                    seen_ids.add(cand.asset_id)
                continue
            log(f"[ARCHIVE] Scene {sn} -> searching query {index}/{len(queries)}: \"{query}\"")
            try:
                hits = self.backend.search(query)
            except Exception as exc:
                log(f"[ARCHIVE] Scene {sn} -> search failed: {exc}")
                continue
            for c in hits:
                if c.asset_id in exclude_ids or c.asset_id in seen_ids:
                    continue
                pooled.append(c)
                seen_ids.add(c.asset_id)
        if not pooled:
            return []
        ranked = rank_by_text(
            pooled,
            primary,
            lambda c: (c.title, c.description, c.collection, c.identifier),
            script_segment=scene.script_segment,
            visual_description=getattr(scene, "visual_description", "") or scene.prompt,
            provider="archive",
            width_fn=lambda c: c.width,
            height_fn=lambda c: c.height,
            url_fn=lambda c: c.download_url,
            duration_fn=lambda c: c.duration,
            asset_id_fn=lambda c: c.asset_id,
            provider_use_counts=getattr(history, "provider_counts", None) if history else None,
            selection_context=ctx,
            log=log,
        )
        log(f"[ARCHIVE] Scene {sn} -> {len(ranked)} candidate(s) after ranking")
        return ranked

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        return self._resolve(scene, images_dir, log, exclude_ids=set())

    def regenerate(
        self, scene: SceneRow, images_dir: Path, exclude: Optional[dict] = None, log: LogFn = print
    ) -> AssetResult:
        exclude_ids: Set[str] = set()
        if exclude and exclude.get("provider_asset_id"):
            exclude_ids.add(str(exclude["provider_asset_id"]))
        return self._resolve(scene, images_dir, log, exclude_ids=exclude_ids)

    def _resolve(
        self, scene: SceneRow, images_dir: Path, log: LogFn, exclude_ids: Set[str]
    ) -> AssetResult:
        if not scene.prompt and not scene.search_queries:
            return AssetResult(
                scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                error="No search query given for this archive_video scene.",
            )
        candidates = self._search(scene, log, exclude_ids)
        if not candidates:
            return AssetResult(
                scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                error="Internet Archive search exhausted — no usable results.",
            )
        match_text = f"{scene.script_segment} {scene.prompt}".strip()
        last_error: Optional[str] = None
        for idx, candidate in enumerate(candidates, start=1):
            if self._scene_stopped(scene):
                return AssetResult(
                    scene.scene_number, None, None, self.source, SceneStatus.CANCELLED,
                    error="Cancelled.",
                )
            log(f"[ARCHIVE] Candidate {idx} -> \"{candidate.title}\" ({candidate.identifier})")
            duration = candidate.duration
            if duration is None and candidate.download_url:
                duration = probe_duration(candidate.download_url)
            target = compute_fallback_timestamp(duration, self.clip_duration)
            start, clip_len = compute_clip_window(target, duration, self.clip_duration)
            n = int(str(scene.scene_number).strip())
            target_path = Path(images_dir) / f"{n:03d}.mp4"
            try:
                path = download_clip(
                    candidate.download_url,
                    target_path,
                    start,
                    clip_len,
                    log=log,
                    should_stop=lambda: self._scene_stopped(scene),
                )
            except Exception as exc:
                last_error = str(exc)
                log(f"[ARCHIVE] Candidate {idx} -> clip failed: {last_error}")
                continue
            actual = sniff_media_kind(path)
            if actual != "video":
                path.unlink(missing_ok=True)
                last_error = f"Downloaded file is not video ({actual})"
                continue
            log(f"[ARCHIVE] Scene {scene.scene_number} -> downloaded {path.name}")
            return AssetResult(
                scene_number=scene.scene_number,
                path=path,
                media_type=MediaType.VIDEO,
                source=self.source,
                status=SceneStatus.READY,
                metadata={
                    "provider": self.name,
                    "provider_asset_id": candidate.asset_id,
                    "title": candidate.title,
                    "source_url": candidate.source_url,
                    "clip_start": start,
                    "clip_duration": clip_len,
                    "selection_method": "text_rank",
                    "matched_text": match_text[:200],
                },
            )
        return AssetResult(
            scene.scene_number, None, None, self.source, SceneStatus.FAILED,
            error=f"Internet Archive candidates exhausted. Last error: {last_error}",
        )
