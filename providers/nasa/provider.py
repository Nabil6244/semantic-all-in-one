"""NASA media library clip provider — asset_type=nasa_video."""

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

from .api_backend import NasaCandidate, NasaMediaBackend
from .test_pattern import is_test_pattern

DEFAULT_CLIP_DURATION = 3.5
# A window that is black from start to end (a launch video's dark middle gave What If render 024 a black 8.8 s shot) is cut again from
# these other points of the same video before the next search result is tried.
RETRY_POINTS = (0.25, 0.75, 0.10)
BLANK_EDGE = 0.05            # edge density no sampled frame of a blank cut reaches (dark space footage sits at 0.3+)


def is_blank_clip(path: Path) -> bool:
    """True when no frame (2 a second) of the cut shows any edge: black or an even fade, nothing to see. Unknown = False."""
    import re
    import subprocess

    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-an", "-vf",
                            "fps=2,scale=320:-2,format=gray,edgedetect=low=0.08:high=0.2,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except Exception:
        return False
    vals = [float(v) for v in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", (r.stderr or "") + (r.stdout or ""))]
    return bool(vals) and max(vals) < BLANK_EDGE


def clip_windows(duration, clip_duration: float) -> list:
    """(start, length) windows to cut, the usual one first, then RETRY_POINTS (those that overlap one before are left out)."""
    first = compute_clip_window(compute_fallback_timestamp(duration, clip_duration), duration, clip_duration)
    out = [first]
    if duration and duration > clip_duration * 2:
        for k in RETRY_POINTS:
            w = compute_clip_window(duration * k, duration, clip_duration)
            if all(abs(w[0] - o[0]) >= clip_duration for o in out):
                out.append(w)
    return out


class NasaProvider(AssetProvider):
    name = "nasa"
    source = AssetSource.NASA_VIDEO

    def __init__(
        self,
        backend: Optional[NasaMediaBackend] = None,
        clip_duration: float = DEFAULT_CLIP_DURATION,
        max_results: int = 8,
    ):
        self.backend = backend or NasaMediaBackend(max_results=max_results)
        self.clip_duration = clip_duration
        self.should_stop_scene = None

    def _scene_stopped(self, scene: SceneRow) -> bool:
        cb = getattr(self, "should_stop_scene", None)
        return bool(callable(cb) and cb(str(scene.scene_number)))

    def _search(self, scene: SceneRow, log: LogFn, exclude_ids: Set[str]) -> List[NasaCandidate]:
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
        sn = scene.scene_number
        primary = queries[0] if queries else ""
        pooled: List[NasaCandidate] = []
        seen_ids: Set[str] = set()
        for index, query in enumerate(queries, start=1):
            if self._scene_stopped(scene):
                return []
            if query.lower().startswith("nasa:"):
                ident = query.split(":", 1)[1].strip()
                log(f"[NASA] Scene {sn} -> direct id \"{ident}\"")
                cand = self.backend.resolve_nasa_id(ident)
                if cand and cand.asset_id not in exclude_ids and cand.asset_id not in seen_ids:
                    pooled.append(cand)
                    seen_ids.add(cand.asset_id)
                continue
            log(f"[NASA] Scene {sn} -> searching query {index}/{len(queries)}: \"{query}\"")
            try:
                hits = self.backend.search(query)
            except Exception as exc:
                log(f"[NASA] Scene {sn} -> search failed: {exc}")
                continue
            for c in hits:
                if c.asset_id in exclude_ids or c.asset_id in seen_ids:
                    continue
                pooled.append(c)
                seen_ids.add(c.asset_id)
        if not pooled:
            return []
        return rank_by_text(
            pooled,
            primary,
            lambda c: (c.title, c.description, c.nasa_id),
            script_segment=scene.script_segment,
            visual_description=getattr(scene, "visual_description", "") or scene.prompt,
            provider="nasa",
            url_fn=lambda c: c.download_url,
            duration_fn=lambda c: c.duration,
            asset_id_fn=lambda c: c.asset_id,
            provider_use_counts=getattr(history, "provider_counts", None) if history else None,
            selection_context=ctx,
            log=log,
        )

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
                error="No search query given for this nasa_video scene.",
            )
        candidates = self._search(scene, log, exclude_ids)
        if not candidates:
            return AssetResult(
                scene.scene_number, None, None, self.source, SceneStatus.FAILED,
                error="NASA media search exhausted — no usable video results.",
            )
        last_error: Optional[str] = None
        for idx, candidate in enumerate(candidates, start=1):
            if self._scene_stopped(scene):
                return AssetResult(
                    scene.scene_number, None, None, self.source, SceneStatus.CANCELLED,
                    error="Cancelled.",
                )
            log(f"[NASA] Candidate {idx} -> \"{candidate.title}\" ({candidate.nasa_id})")
            duration = candidate.duration or probe_duration(candidate.download_url)
            n = int(str(scene.scene_number).strip())
            target_path = Path(images_dir) / f"{n:03d}.mp4"
            path = None
            for start, clip_len in clip_windows(duration, self.clip_duration):
                if self._scene_stopped(scene):
                    break
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
                    path = None
                    break
                if sniff_media_kind(path) == "video" and is_blank_clip(path):
                    log(f"[NASA] Candidate {idx} is black at {start:.0f}s; cutting another part of the same video")
                    path.unlink(missing_ok=True)
                    last_error = "The cut is black from start to end"
                    path = None
                    continue
                break
            if path is None:
                continue
            if sniff_media_kind(path) != "video":
                path.unlink(missing_ok=True)
                last_error = "Downloaded file is not video"
                continue
            if is_test_pattern(path):
                path.unlink(missing_ok=True)
                last_error = "The cut is a colour-bars test card"
                log(f"[NASA] Candidate {idx} cut is a colour-bars test card; trying the next one")
                continue
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
                },
            )
        return AssetResult(
            scene.scene_number, None, None, self.source, SceneStatus.FAILED,
            error=f"NASA candidates exhausted. Last error: {last_error}",
        )
