"""
AssetManager: routes each CSV scene to LocalProvider / StockProvider / FlowProvider,
caches results in a per-project manifest (Images/.asset_manifest.json), and hands the
existing renderer nothing but ordinary files at Images/00N.<ext>. Nothing downstream of
this module (Whisper alignment, video_generator.render_video) knows or cares which
provider produced which scene's asset.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import video_generator as vg
from media_duration import annotate_actual_duration, cached_duration
from providers.base import (
    AssetError,
    AssetResult,
    AssetSource,
    LogFn,
    MediaType,
    SceneRow,
    SceneStatus,
)
from scene_recovery import PLACEHOLDER_PNG, SceneRecoveryTracker, mark_needs_action, scene_key
from providers.local_provider import LocalProvider
from providers.router import SceneAssetRouter

DEFAULT_PARALLEL_SCENES = max(1, min(8, int(os.environ.get("ASSET_PARALLEL_SCENES", "4"))))

# Candidate-side relevance floor applied to stock searches in the Property
# Video workflow (0.0 elsewhere). Deliberately modest: it rejects clips with
# no meaningful overlap with the query at all, without second-guessing the
# existing ranking for genuinely on-topic candidates.
PROPERTY_VIDEO_MIN_STOCK_RELEVANCE = float(
    os.environ.get("PROPERTY_VIDEO_MIN_STOCK_RELEVANCE", "0.2")
)
SceneStartCallback = Callable[[SceneRow, AssetSource], None]
SceneCompleteCallback = Callable[[SceneRow, AssetResult], None]

MANIFEST_NAME = ".asset_manifest.json"

# Primary documentary sources that should honor declared fallbacks on failure.
_FALLBACK_ELIGIBLE_SOURCES = frozenset({
    AssetSource.YOUTUBE_VIDEO,
    AssetSource.ARCHIVE_VIDEO,
    AssetSource.NASA_VIDEO,
    # Flow image is now the primary image source, so a genuine Flow failure
    # must fall through to its declared stock_image fallback instead of
    # dead-ending. FLOW_VIDEO is deliberately NOT here: paid video keeps its
    # existing quota-aware Flow-image retry path untouched.
    AssetSource.FLOW_IMAGE,
})


def _key(scene_number: str) -> str:
    """Normalize scene numbers for manifest keys ('1' and '001' are the same scene)."""
    try:
        return f"{int(str(scene_number).strip()):03d}"
    except ValueError:
        return str(scene_number).strip()


class AssetManifest:
    """JSON-backed store: normalized scene number -> record dict. Saved after every
    write so a crash mid-run doesn't lose progress already made (resume support)."""

    def __init__(self, images_dir: Path):
        self.path = Path(images_dir) / MANIFEST_NAME
        self._data: Dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8"
        )

    def get(self, scene_number: str) -> Optional[dict]:
        return self._data.get(_key(scene_number))

    def set(self, scene_number: str, record: dict) -> None:
        key = _key(scene_number)
        if self._data.get(key) == record:
            return
        self._data[key] = record
        self.save()

    def all(self) -> Dict[str, dict]:
        return dict(self._data)


@dataclasses.dataclass
class ResolveSummary:
    results: Dict[str, AssetResult]
    warnings: List[str]

    @property
    def failed(self) -> List[AssetResult]:
        return [
            r for r in self.results.values()
            if not r.ok and r.status not in (SceneStatus.CANCELLED, SceneStatus.SKIPPED)
        ]

    @property
    def cancelled(self) -> List[AssetResult]:
        return [r for r in self.results.values() if r.status == SceneStatus.CANCELLED]

    @property
    def ok(self) -> bool:
        return not self.failed and not self.cancelled


class AssetManager:
    def __init__(
        self,
        images_dir: Path,
        stock_provider=None,
        flow_image_provider=None,
        flow_video_provider=None,
        youtube_provider=None,
        archive_provider=None,
        nasa_provider=None,
        research_provider=None,
        log: LogFn = print,
        resolved_style=None,
        coverage_by_scene: Optional[dict] = None,
        settings: Optional[dict] = None,
    ):
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.local_provider = LocalProvider()
        self.stock_provider = stock_provider
        self.flow_image_provider = flow_image_provider
        self.flow_video_provider = flow_video_provider
        self.youtube_provider = youtube_provider
        self.archive_provider = archive_provider
        self.nasa_provider = nasa_provider
        self.research_provider = research_provider
        self.resolved_style = resolved_style
        # Read by _run_visual_qa() so Visual QA can resolve the Gemini key and
        # run the vision tier. Previously nothing ever set this attribute, so
        # vision_semantic_score() returned None before reading the key and the
        # whole vision tier was unreachable regardless of configuration.
        self.settings = dict(settings or {})
        self.coverage_by_scene = dict(coverage_by_scene or {})
        # Property Video only: when a project has researched listings, stock
        # scenes get a candidate-side relevance floor so a clip that merely
        # came back from the search (but isn't about the query) is rejected
        # rather than accepted as "best available". Left at 0.0 (off) for
        # the normal YouTube workflow, whose ranking is unchanged.
        if research_provider is not None and stock_provider is not None:
            stock_provider.min_stock_relevance = PROPERTY_VIDEO_MIN_STOCK_RELEVANCE
        from style_engine.visual_selection import SelectionHistory

        self.selection_history = SelectionHistory()
        self.manifest = AssetManifest(self.images_dir)
        self.log = log
        self._manifest_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._cancelled_scenes: set[str] = set()
        self.recovery = SceneRecoveryTracker()
        for provider in (
            self.stock_provider,
            self.youtube_provider,
            self.archive_provider,
            self.nasa_provider,
            self.flow_image_provider,
            self.flow_video_provider,
            self.research_provider,
        ):
            if provider is not None:
                provider.should_stop_scene = self.is_scene_cancelled
                provider.resolved_style = resolved_style
                provider.selection_history = self.selection_history

    # ---------- cancellation ----------

    def request_cancel(self) -> None:
        """Cooperative cancellation: scenes not yet started are skipped (marked
        CANCELLED, not FAILED); a scene already resolved before this call keeps its
        result. Does not abort mid-flight network calls, but a Flow batch already in
        progress is told to stop via the engine's own STOP message (see
        providers/flow/provider.py), so it doesn't run for the full timeout."""
        self._cancel_event.set()

    def request_cancel_scene(self, scene_number: str) -> None:
        """Cancel one scene. Does not cancel the rest of the run."""
        self._cancelled_scenes.add(scene_key(scene_number))
        for provider in (
            self.youtube_provider,
            self.stock_provider,
            self.archive_provider,
            self.nasa_provider,
            self.flow_image_provider,
            self.flow_video_provider,
            self.research_provider,
        ):
            if provider is not None:
                provider.should_stop_scene = self.is_scene_cancelled

    def is_scene_cancelled(self, scene_number: str) -> bool:
        return scene_key(scene_number) in self._cancelled_scenes

    def reset_cancel(self) -> None:
        self._cancel_event.clear()
        self._cancelled_scenes.clear()

    def _run_cancelled(self) -> bool:
        """Run-level cancellation ONLY — did the user stop the whole run?

        This is what a Flow batch's `should_stop` must mean. It used to be
        `is_cancelled or any(scene cancelled in this batch)`, which made ONE
        cancelled/stopped scene look like a whole-run abort: the provider
        sends STOP for that scene, then re-checks should_stop() to decide why
        the batch ended (provider.py, "_resolve_batch_locked" result loop).
        With the batch-wide form that check always answered "the user
        cancelled", so every scene still in flight was written off as
        CANCELLED instead of the FAILED/"Interrupted ... Use Retry" the code
        already had for exactly this case — one bad prompt cancelling hundreds
        of unrelated scenes.

        Per-scene stopping is unaffected: FlowProvider._batch_should_stop()
        still ORs in its own per-scene `should_stop_scene` callback to decide
        when to STOP the engine, and _resolve_flow_batch() still marks the
        individually-cancelled scene CANCELLED on its own.
        """
        return self.is_cancelled

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ---------- routing / provider lookup ----------

    def _provider_for(self, source: AssetSource):
        return {
            AssetSource.LOCAL: self.local_provider,
            AssetSource.MANUAL: self.local_provider,
            AssetSource.STOCK: self.stock_provider,
            AssetSource.STOCK_IMAGE: self.stock_provider,
            AssetSource.STOCK_VIDEO: self.stock_provider,
            AssetSource.FLOW_IMAGE: self.flow_image_provider,
            AssetSource.FLOW_VIDEO: self.flow_video_provider,
            AssetSource.YOUTUBE_VIDEO: self.youtube_provider,
            AssetSource.ARCHIVE_VIDEO: self.archive_provider,
            AssetSource.NASA_VIDEO: self.nasa_provider,
            AssetSource.COMMONS_VIDEO: self.stock_provider,
            AssetSource.COMMONS_IMAGE: self.stock_provider,
            AssetSource.RESEARCH: self.research_provider,
        }[source]

    def classify(self, scene: SceneRow) -> AssetSource:
        source = SceneAssetRouter.classify(scene)
        if source is not None:
            # Manual CSV authority always wins — an explicit asset_type is
            # never second-guessed or overridden by research.
            return source
        if (
            self.research_provider is not None
            and self.research_provider.has_unused_candidates(scene.scene_number)
            and vg.find_image_for_scene(self.images_dir, scene.scene_number) is None
        ):
            # Only fills the gap when the CSV didn't request a specific
            # provider AND no manually-placed local file already covers
            # this scene (that intentional user action still wins).
            return AssetSource.RESEARCH
        return AssetSource.LOCAL

    def validate_rows(self, rows: List[SceneRow]) -> List[str]:
        return SceneAssetRouter.validate(rows, self.images_dir)

    # ---------- caching ----------

    def _result_from_complete_record(self, scene: SceneRow, record: dict) -> Optional[AssetResult]:
        raw_path = record.get("local_path")
        path = Path(raw_path) if raw_path else None
        if path is None or not path.is_file():
            # Manifest path can go stale after moves/mirrors; fall back to Images/.
            path = vg.find_image_for_scene(self.images_dir, scene.scene_number)
        if path is None or not path.is_file():
            return None
        try:
            recorded_source = AssetSource(str(record.get("source") or "local"))
        except ValueError:
            recorded_source = self.classify(scene)
        media_type = MediaType.VIDEO if vg.is_video_file(path) else MediaType.IMAGE
        return AssetResult(
            scene_number=scene.scene_number,
            path=path,
            media_type=media_type,
            source=recorded_source,
            status=SceneStatus.READY,
            metadata=record,
        )

    @staticmethod
    def _norm_text(value) -> str:
        return ("" if value is None else str(value)).strip()

    def _cache_hit(self, scene: SceneRow, source: AssetSource) -> Optional[AssetResult]:
        """LOCAL is never cache-shortcut (it's a free lookup and must never be treated
        as something we could delete/replace); STOCK/FLOW are cached against the
        prompt/query that produced them, and only count if the file is still there."""
        if source == AssetSource.LOCAL:
            return None
        record = self.manifest.get(scene.scene_number)
        if not record or record.get("status") != "complete":
            return None
        # Change Source (e.g. YouTube → Flow image) leaves a complete file whose
        # recorded source no longer matches the CSV. Reuse it for final render
        # unless the CSV text itself changed (stock → a new Flow prompt).
        if record.get("source") != source.value:
            new_text = self._norm_text(scene.prompt or scene.stock)
            old_prompt = self._norm_text(record.get("prompt"))
            old_stock = self._norm_text(record.get("stock_query"))
            if new_text and new_text not in (old_prompt, old_stock):
                return None
            return self._result_from_complete_record(scene, record)
        if (
            source in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO, AssetSource.YOUTUBE_VIDEO)
            and self._norm_text(record.get("prompt")) != self._norm_text(scene.prompt)
        ):
            return None
        if (
            source in (AssetSource.ARCHIVE_VIDEO, AssetSource.NASA_VIDEO)
            and self._norm_text(record.get("prompt")) != self._norm_text(scene.prompt)
        ):
            return None
        if (
            source in (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO)
            and self._norm_text(record.get("stock_query")) != self._norm_text(scene.stock)
        ):
            return None
        return self._result_from_complete_record(scene, record)

    def _record_from_result(self, scene: SceneRow, result: AssetResult) -> dict:
        record = {
            "source": result.source.value,
            "asset_type": scene.asset_type,
            "type": result.media_type.value if result.media_type else None,
            "prompt": scene.prompt,
            "script_segment": scene.script_segment,
            "stock_query": scene.stock,
            "local_path": str(result.path) if result.path else None,
            "status": "complete" if result.ok else "failed",
            "resolved_at": time.time(),
            "error": result.error,
        }
        # Provider-specific extras (provider_asset_id, author, source_url, ...)
        record.update(result.metadata or {})
        key = scene_key(scene.scene_number)
        cov = self.coverage_by_scene.get(key) or self.coverage_by_scene.get(str(scene.scene_number))
        if cov:
            record["coverage_plan"] = cov
        return record

    def _remove_stale_file(self, scene_number: str, keep: Path) -> None:
        """After a successful STOCK/FLOW download, delete any other pre-existing file
        for this scene (e.g. an old 001.jpg lingering next to a fresh 001.mp4) so the
        renderer's extension-priority lookup can't pick up the wrong one."""
        existing = vg.find_image_for_scene(self.images_dir, scene_number)
        if existing and existing.resolve() != keep.resolve() and existing.is_file():
            existing.unlink()

    def _annotate_actual_duration(self, result: AssetResult) -> None:
        """Measure the delivered file so the editor works from reality.

        Provider-agnostic on purpose: every provider's result passes through
        _finalize(), so Flow, stock, YouTube and archive clips are all covered
        by one mechanism rather than a Flow-specific side channel. Images are
        untouched. Purely additive — a failed probe never changes the result's
        status, and nothing here can trigger a regeneration.
        """
        if not result.ok or result.path is None:
            return
        if result.media_type != MediaType.VIDEO:
            return
        if result.metadata is None:
            result.metadata = {}
        requested = self._requested_video_duration()
        try:
            annotate_actual_duration(
                result.metadata,
                result.path,
                is_video=True,
                requested=requested,
            )
        except (OSError, ValueError):
            # Duration is advisory metadata; a probe failure must never fail a
            # scene. Deliberately narrow: a TypeError/AttributeError here would
            # be a real defect and should surface rather than vanish.
            pass

    def _requested_video_duration(self):
        """The operator's configured clip length — recorded, NOT assumed applied."""
        settings = getattr(self, "settings", None)
        if not isinstance(settings, dict):
            return None
        for key in ("flow_video_duration", "videoDuration", "video_duration"):
            if key in settings:
                return settings.get(key)
        return None

    def _finalize(self, scene: SceneRow, result: AssetResult) -> None:
        self._annotate_actual_duration(result)
        if result.ok and result.source != AssetSource.LOCAL:
            self._remove_stale_file(scene.scene_number, keep=result.path)
            meta = result.metadata or {}
            provider = str(meta.get("provider") or result.source.value or "")
            asset_id = str(meta.get("provider_asset_id") or meta.get("asset_id") or "")
            title = str(meta.get("title") or meta.get("alt") or "")
            desc = str(meta.get("description") or meta.get("tags") or "")
            self.selection_history.record(
                provider=provider,
                asset_id=asset_id,
                title=title,
                description=desc,
            )
        elif result.status == SceneStatus.SKIPPED:
            self.log(f"[ASSET] Scene {scene.scene_number} -> SKIPPED")
        elif result.status == SceneStatus.CANCELLED:
            self.log(f"[ASSET] Scene {scene.scene_number} -> CANCELLED")
        elif not result.ok:
            mark_needs_action(result)
            self.log(f"[ASSET] Scene {scene.scene_number} -> FAILED: {result.error}")
        record = self._record_from_result(scene, result)
        if result.ok and result.path is not None:
            self._run_visual_qa(scene, result, record)
        self._manifest_write(scene, record)
        self.recovery.status[scene_key(scene.scene_number)] = result.status.value

    def _run_visual_qa(self, scene: SceneRow, result: AssetResult, record: dict) -> None:
        try:
            from visual_qa import evaluate_scene_asset

            qa = evaluate_scene_asset(
                scene,
                result,
                images_dir=self.images_dir,
                coverage_plan=record.get("coverage_plan"),
                selection_history=self.selection_history,
                resolved=getattr(self, "resolved_style", None),
                settings=self.settings,
                enable_vision=True,
            )
            record["visual_qa"] = qa.to_dict()
            refined = (result.metadata or {}).get("_refined_coverage_plan")
            if refined:
                record["coverage_plan"] = refined
            if result.metadata is None:
                result.metadata = {}
            result.metadata.update({
                "visual_qa": record["visual_qa"],
                "coverage_plan": record.get("coverage_plan"),
            })
            if qa.status.value in ("WEAK", "FAIL"):
                self.log(
                    f"[VQA] Scene {scene.scene_number} -> {qa.status.value} "
                    f"(score {qa.overall_score:.2f}) — {qa.recommended_action.value}"
                )
        except Exception as exc:
            self.log(f"[VQA] Scene {scene.scene_number} QA skipped: {exc}")

    def _manifest_write(self, scene: SceneRow, record: dict) -> None:
        with self._manifest_lock:
            self.manifest.set(scene.scene_number, record)

    def _record_failed_approach(self, scene: SceneRow, source: AssetSource, result: AssetResult) -> None:
        if result.ok or result.status in (SceneStatus.CANCELLED, SceneStatus.SKIPPED):
            return
        key = scene_key(scene.scene_number)
        phase = (result.metadata or {}).get("youtube_phase")
        if source == AssetSource.YOUTUBE_VIDEO:
            from providers.youtube.base import unique_youtube_queries

            if phase == "search":
                for query in unique_youtube_queries(scene):
                    self.recovery.mark_query(key, query)
                self.recovery.mark_provider(key, "youtube")
            else:
                self.recovery.mark_query(key, scene.prompt)
                vid = (result.metadata or {}).get("video_id") or (result.metadata or {}).get("provider_asset_id")
                if vid:
                    self.recovery.mark_asset_id(key, str(vid))
        else:
            self.recovery.mark_provider(key, source.value)

    def _store_failure(self, scene: SceneRow, source: AssetSource, error: str) -> AssetResult:
        result = AssetResult(
            scene_number=scene.scene_number,
            path=None,
            media_type=None,
            source=source,
            status=SceneStatus.NEEDS_ACTION,
            error=error,
        )
        self._finalize(scene, result)
        return result

    def _apply_coverage_context(self, scene: SceneRow, provider) -> None:
        if provider is None:
            return
        key = scene_key(scene.scene_number)
        cov = self.coverage_by_scene.get(key) or self.coverage_by_scene.get(str(scene.scene_number))
        if not cov:
            provider.required_duration = None
            return
        dur = cov.get("narration_duration")
        try:
            provider.required_duration = float(dur) if dur else None
        except (TypeError, ValueError):
            provider.required_duration = None

    def _resolve_one(self, scene: SceneRow, source: AssetSource, *, try_declared_fallbacks: bool = True) -> AssetResult:
        if self.is_scene_cancelled(scene.scene_number):
            return self._cancelled_result(scene, source)
        provider = self._provider_for(source)
        if provider is None:
            return self._store_failure(
                scene, source, f"{source.value} provider is not configured for this run."
            )
        self._apply_coverage_context(scene, provider)
        for p in (
            self.youtube_provider,
            self.archive_provider,
            self.nasa_provider,
            self.stock_provider,
            self.flow_image_provider,
            self.flow_video_provider,
        ):
            if p is not None:
                p.should_stop_scene = self.is_scene_cancelled
        self.log(f"[ASSET] Scene {scene.scene_number} -> {source.value.upper()}")
        try:
            result = provider.resolve(scene, self.images_dir, log=self.log)
        except AssetError as exc:
            result = AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=source, status=SceneStatus.FAILED, error=exc.reason,
            )
        except Exception as exc:  # a provider bug must not abort the whole run
            result = AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=source, status=SceneStatus.FAILED, error=f"unexpected error: {exc}",
            )
        if self.is_scene_cancelled(scene.scene_number):
            if result.ok and result.path:
                result.path.unlink(missing_ok=True)
            return self._cancelled_result(scene, source)
        if (
            result.ok
            or not try_declared_fallbacks
            or source not in _FALLBACK_ELIGIBLE_SOURCES
            or not getattr(scene, "fallbacks", None)
        ):
            self._record_failed_approach(scene, source, result)
            self._finalize(scene, result)
            return result

        for name in scene.fallbacks:
            if self.is_scene_cancelled(scene.scene_number):
                return self._cancelled_result(scene, source)
            self.log(
                f"[ASSET] Scene {scene.scene_number} -> {source.value} failed; "
                f"trying declared fallback: {name}"
            )
            fallback_scene = scene.as_fallback(str(name))
            fallback_source = self.classify(fallback_scene)
            fallback_result = self._resolve_one(
                fallback_scene, fallback_source, try_declared_fallbacks=False
            )
            if fallback_result.ok:
                return fallback_result
        self._record_failed_approach(scene, source, result)
        self._finalize(scene, result)
        return result

    # ---------- public API ----------

    def resolve_scene(self, scene: SceneRow, force: bool = False) -> AssetResult:
        """Resolve a single scene. resolve_all() is preferred for a full project run
        (it batches FLOW scenes into one multi-account call); this is the direct,
        one-off path used by tests and anything that only needs one scene."""
        source = self.classify(scene)
        warning = scene.ignored_stock_warning
        if warning:
            self.log(f"[ASSET] WARNING: {warning}")
        if not force:
            cached = self._cache_hit(scene, source)
            if cached is not None:
                self.log(
                    f"[ASSET] Scene {scene.scene_number} -> {source.value.upper()} "
                    f"(cached, reusing {cached.path.name})"
                )
                return cached
        return self._resolve_one(scene, source)

    def _cancelled_result(self, scene: SceneRow, source: AssetSource) -> AssetResult:
        result = AssetResult(
            scene_number=scene.scene_number, path=None, media_type=None,
            source=source, status=SceneStatus.CANCELLED, error="Cancelled.",
        )
        self._manifest_write(scene, self._record_from_result(scene, result))
        return result

    def _resolve_flow_batch(
        self,
        source: AssetSource,
        provider,
        scenes: List[SceneRow],
        results: Dict[str, AssetResult],
        *,
        on_scene_start: Optional[SceneStartCallback] = None,
        on_scene_complete: Optional[SceneCompleteCallback] = None,
    ) -> None:
        """Shared by resolve_all() for both FLOW_IMAGE and FLOW_VIDEO — one batched
        GENERATE call per kind (never mixed), same cancel/error handling either way."""
        if not scenes:
            return
        if self.is_cancelled:
            for scene in scenes:
                result = self._cancelled_result(scene, source)
                results[scene.scene_number] = result
                if on_scene_complete:
                    on_scene_complete(scene, result)
            return
        if provider is None:
            kind = "image" if source == AssetSource.FLOW_IMAGE else "video"
            for scene in scenes:
                result = self._store_failure(
                    scene, source,
                    f"Flow {kind} provider is not configured (no Flow engine connection / no accounts logged in).",
                )
                results[scene.scene_number] = result
                if on_scene_complete:
                    on_scene_complete(scene, result)
            return

        self.log(f"[ASSET] {len(scenes)} scene(s) -> {source.value.upper()} (batched)")
        if on_scene_start:
            for scene in scenes:
                on_scene_start(scene, source)

        early_reported: Dict[str, AssetResult] = {}

        def _on_scene_ready(scene: SceneRow, result: AssetResult) -> None:
            """Flip the UI off PROCESSING as soon as a Flow file lands mid-batch."""
            if scene.scene_number in early_reported:
                return
            if self.is_scene_cancelled(scene.scene_number):
                if result.ok and result.path:
                    result.path.unlink(missing_ok=True)
                result = self._cancelled_result(scene, source)
            else:
                self._record_failed_approach(scene, source, result)
                self._finalize(scene, result)
            early_reported[scene.scene_number] = result
            results[scene.scene_number] = result
            if on_scene_complete:
                on_scene_complete(scene, result)

        try:
            batch_results = provider.resolve_batch(
                scenes,
                self.images_dir,
                log=self.log,
                should_stop=self._run_cancelled,
                on_scene_ready=_on_scene_ready,
            )
        except TypeError:
            # Older provider stubs in tests may not accept on_scene_ready.
            batch_results = provider.resolve_batch(
                scenes,
                self.images_dir,
                log=self.log,
                should_stop=self._run_cancelled,
            )
        except Exception as exc:
            batch_results = {}
            self.log(f"[FLOW] batch failed: {exc}")
        for scene in scenes:
            if scene.scene_number in early_reported:
                # Already finalized + UI-notified while the batch was still running.
                final = batch_results.get(scene.scene_number) or early_reported[scene.scene_number]
                results[scene.scene_number] = final
                continue
            result = batch_results.get(scene.scene_number) or AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=source, status=SceneStatus.FAILED,
                error="Flow engine returned no result for this scene.",
            )
            if self.is_scene_cancelled(scene.scene_number):
                if result.ok and result.path:
                    result.path.unlink(missing_ok=True)
                result = self._cancelled_result(scene, source)
            else:
                self._record_failed_approach(scene, source, result)
                self._finalize(scene, result)
            results[scene.scene_number] = result
            if on_scene_complete:
                on_scene_complete(scene, result)

        # Flow video rate/quota survivors → one automatic Flow image attempt.
        if source == AssetSource.FLOW_VIDEO and not self.is_cancelled:
            self._fallback_flow_video_to_image(
                scenes,
                results,
                on_scene_start=on_scene_start,
                on_scene_complete=on_scene_complete,
            )

        # Flow image failures → declared stock_image fallback. The batch path
        # never reaches _resolve_one(), so without this a Flow-image failure
        # dead-ends at NEEDS_ACTION even though the scene declares a fallback.
        # Guarded on FLOW_IMAGE so Flow VIDEO keeps its existing behaviour and
        # never falls back to stock here.
        if source == AssetSource.FLOW_IMAGE and not self.is_cancelled:
            self._fallback_flow_image_to_stock(
                scenes,
                results,
                on_scene_start=on_scene_start,
                on_scene_complete=on_scene_complete,
            )

    def _fallback_flow_image_to_stock(
        self,
        image_scenes: List[SceneRow],
        results: Dict[str, AssetResult],
        *,
        on_scene_start: Optional[SceneStartCallback] = None,
        on_scene_complete: Optional[SceneCompleteCallback] = None,
    ) -> None:
        """Flow image is preferred and free, but when it genuinely fails the
        scene falls back to stock_image rather than stopping at NEEDS_ACTION.

        Mirrors the declared-fallback behaviour `_resolve_one()` already gives
        the single-scene path, so both paths route Flow image -> stock image
        identically. Successful Flow images are never touched."""
        if self.stock_provider is None:
            return
        for scene in image_scenes:
            key = scene.scene_number
            result = results.get(key)
            if result is None or result.ok:
                continue
            if result.status in (SceneStatus.CANCELLED, SceneStatus.SKIPPED):
                continue
            if self.is_cancelled or self.is_scene_cancelled(key):
                continue
            fallback = scene.as_fallback("stock_image")
            fallback_source = self.classify(fallback)
            if fallback_source is None:
                continue
            self.log(
                f"[ASSET] Scene {key} -> flow_image failed; "
                f"trying declared fallback: stock_image"
            )
            if on_scene_start:
                on_scene_start(fallback, fallback_source)
            fallback_result = self._resolve_one(
                fallback, fallback_source, try_declared_fallbacks=False
            )
            if not fallback_result.ok:
                # Keep the original Flow failure as the reported error.
                continue
            results[key] = fallback_result
            if on_scene_complete:
                on_scene_complete(fallback, fallback_result)

    @staticmethod
    def _is_flow_rate_or_quota_error(result: AssetResult) -> bool:
        if result is None or result.ok:
            return False
        if result.status in (SceneStatus.CANCELLED, SceneStatus.SKIPPED):
            return False
        err = (result.error or "").lower()
        needles = (
            "rate limit",
            "rate_limited",
            "quota",
            "resource_exhausted",
            "all signed-in accounts",
            "account rotation",
            "persists on all",
            "persists — skipping",
            "persists - skipping",
        )
        return any(n in err for n in needles)

    def _fallback_flow_video_to_image(
        self,
        video_scenes: List[SceneRow],
        results: Dict[str, AssetResult],
        *,
        on_scene_start: Optional[SceneStartCallback] = None,
        on_scene_complete: Optional[SceneCompleteCallback] = None,
    ) -> None:
        """After Flow video fails on rate/quota (even after account rotation), try Flow image once."""
        if self.flow_image_provider is None:
            return
        by_number = {str(s.scene_number): s for s in video_scenes}
        to_retry: List[SceneRow] = []
        for number, result in list(results.items()):
            if not self._is_flow_rate_or_quota_error(result):
                continue
            if getattr(result, "source", None) not in (AssetSource.FLOW_VIDEO,):
                continue
            key = scene_key(number)
            used = self.recovery.failed_providers.get(key) or set()
            if "flow_image" in used or "image" in used:
                continue
            original = by_number.get(str(number))
            if original is None:
                continue
            prompt = (original.prompt or original.visual_description or "").strip()
            if not prompt:
                continue
            to_retry.append(
                SceneRow(
                    scene_number=original.scene_number,
                    script_segment=original.script_segment,
                    asset_type="image",
                    prompt=prompt,
                    visual_description=original.visual_description or prompt,
                    fallbacks=list(original.fallbacks or []),
                )
            )

        if not to_retry:
            return

        self.log(
            f"[FLOW] {len(to_retry)} video scene(s) still rate/quota-limited — "
            f"falling back to Flow image"
        )
        for scene in to_retry:
            self._cancelled_scenes.discard(scene_key(scene.scene_number))
            if on_scene_start:
                on_scene_start(scene, AssetSource.FLOW_IMAGE)

        early_reported: Dict[str, AssetResult] = {}

        def _on_ready(scene: SceneRow, result: AssetResult) -> None:
            if scene.scene_number in early_reported:
                return
            if self.is_scene_cancelled(scene.scene_number):
                if result.ok and result.path:
                    result.path.unlink(missing_ok=True)
                result = self._cancelled_result(scene, AssetSource.FLOW_IMAGE)
            else:
                self._record_failed_approach(scene, AssetSource.FLOW_IMAGE, result)
                self._finalize(scene, result)
            early_reported[scene.scene_number] = result
            results[scene.scene_number] = result
            if on_scene_complete:
                on_scene_complete(scene, result)

        try:
            batch_results = self.flow_image_provider.resolve_batch(
                to_retry,
                self.images_dir,
                log=self.log,
                should_stop=self._run_cancelled,
                on_scene_ready=_on_ready,
            )
        except TypeError:
            batch_results = self.flow_image_provider.resolve_batch(
                to_retry,
                self.images_dir,
                log=self.log,
                should_stop=self._run_cancelled,
            )
        except Exception as exc:
            batch_results = {}
            self.log(f"[FLOW] image fallback batch failed: {exc}")

        for scene in to_retry:
            if scene.scene_number in early_reported:
                continue
            result = batch_results.get(scene.scene_number) or AssetResult(
                scene_number=scene.scene_number,
                path=None,
                media_type=None,
                source=AssetSource.FLOW_IMAGE,
                status=SceneStatus.FAILED,
                error="Flow image fallback returned no result.",
            )
            if self.is_scene_cancelled(scene.scene_number):
                if result.ok and result.path:
                    result.path.unlink(missing_ok=True)
                result = self._cancelled_result(scene, AssetSource.FLOW_IMAGE)
            else:
                if result.ok:
                    self.log(
                        f"[FLOW] Scene {scene.scene_number} recovered via Flow image fallback"
                    )
                self._record_failed_approach(scene, AssetSource.FLOW_IMAGE, result)
                self._finalize(scene, result)
            results[scene.scene_number] = result
            if on_scene_complete:
                on_scene_complete(scene, result)

    def _resolve_sequential(
        self,
        scenes: List[SceneRow],
        source: AssetSource,
        results: Dict[str, AssetResult],
        *,
        on_scene_start: Optional[SceneStartCallback] = None,
        on_scene_complete: Optional[SceneCompleteCallback] = None,
    ) -> None:
        for scene in scenes:
            if self.is_cancelled or self.is_scene_cancelled(scene.scene_number):
                result = self._cancelled_result(scene, source)
            else:
                if on_scene_start:
                    on_scene_start(scene, source)
                result = self._resolve_one(scene, source)
            results[scene.scene_number] = result
            if on_scene_complete:
                on_scene_complete(scene, result)

    def _resolve_parallel(
        self,
        items: List[Tuple[AssetSource, SceneRow]],
        results: Dict[str, AssetResult],
        *,
        max_workers: int,
        on_scene_start: Optional[SceneStartCallback] = None,
        on_scene_complete: Optional[SceneCompleteCallback] = None,
    ) -> None:
        if not items:
            return
        workers = max(1, min(max_workers, len(items)))
        pending_items = list(items)
        queue_lock = threading.RLock()
        drained = threading.Event()

        def drain_cancelled() -> list[Tuple[AssetSource, SceneRow]]:
            with queue_lock:
                if drained.is_set():
                    return []
                rest = pending_items[:]
                pending_items.clear()
                drained.set()
            return rest

        def publish(source: AssetSource, scene: SceneRow, result: AssetResult) -> None:
            results[scene.scene_number] = result
            if on_scene_complete:
                on_scene_complete(scene, result)

        def work() -> None:
            while True:
                with queue_lock:
                    if not pending_items:
                        return
                    if self.is_cancelled:
                        for source, scene in drain_cancelled():
                            publish(source, scene, self._cancelled_result(scene, source))
                        return
                    source, scene = pending_items.pop(0)
                if self.is_scene_cancelled(scene.scene_number) or self.is_cancelled:
                    publish(source, scene, self._cancelled_result(scene, source))
                    continue
                if on_scene_start:
                    on_scene_start(scene, source)
                if self.is_cancelled:
                    publish(source, scene, self._cancelled_result(scene, source))
                    continue
                publish(source, scene, self._resolve_one(scene, source))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work) for _ in range(workers)]
            for fut in as_completed(futures):
                fut.result()
        if pending_items and self.is_cancelled:
            for source, scene in drain_cancelled():
                publish(source, scene, self._cancelled_result(scene, source))

    def resolve_all(
        self,
        rows: List[SceneRow],
        *,
        on_scene_start: Optional[SceneStartCallback] = None,
        on_scene_complete: Optional[SceneCompleteCallback] = None,
        max_parallel: Optional[int] = None,
    ) -> ResolveSummary:
        errors = self.validate_rows(rows)
        if errors:
            raise AssetError("validation", "; ".join(errors))
        self.reset_cancel()
        parallel_limit = max_parallel if max_parallel is not None else DEFAULT_PARALLEL_SCENES

        results: Dict[str, AssetResult] = {}
        warnings: List[str] = []
        pending: Dict[AssetSource, List[SceneRow]] = {
            AssetSource.LOCAL: [], AssetSource.MANUAL: [],
            AssetSource.STOCK: [], AssetSource.STOCK_IMAGE: [], AssetSource.STOCK_VIDEO: [],
            AssetSource.FLOW_IMAGE: [], AssetSource.FLOW_VIDEO: [],
            AssetSource.YOUTUBE_VIDEO: [],
            AssetSource.ARCHIVE_VIDEO: [], AssetSource.NASA_VIDEO: [],
            AssetSource.COMMONS_VIDEO: [], AssetSource.COMMONS_IMAGE: [],
            AssetSource.RESEARCH: [],
        }

        for scene in rows:
            source = self.classify(scene)
            warning = scene.ignored_stock_warning
            if warning:
                self.log(f"[ASSET] WARNING: {warning}")
                warnings.append(warning)

            cached = self._cache_hit(scene, source)
            if cached is not None:
                self.log(
                    f"[ASSET] Scene {scene.scene_number} -> {source.value.upper()} "
                    f"(cached, reusing {cached.path.name})"
                )
                results[scene.scene_number] = cached
                if on_scene_complete:
                    on_scene_complete(scene, cached)
                continue
            pending[source].append(scene)

        self._resolve_sequential(
            pending[AssetSource.LOCAL],
            AssetSource.LOCAL,
            results,
            on_scene_start=on_scene_start,
            on_scene_complete=on_scene_complete,
        )

        parallel_items: List[Tuple[AssetSource, SceneRow]] = []
        for stock_source in (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO):
            parallel_items.extend((stock_source, scene) for scene in pending[stock_source])
        parallel_items.extend(
            (AssetSource.YOUTUBE_VIDEO, scene) for scene in pending[AssetSource.YOUTUBE_VIDEO]
        )
        for clip_source in (
            AssetSource.ARCHIVE_VIDEO,
            AssetSource.NASA_VIDEO,
            AssetSource.COMMONS_VIDEO,
        ):
            parallel_items.extend((clip_source, scene) for scene in pending[clip_source])
        self._resolve_parallel(
            parallel_items,
            results,
            max_workers=parallel_limit,
            on_scene_start=on_scene_start,
            on_scene_complete=on_scene_complete,
        )

        self._resolve_sequential(
            pending[AssetSource.COMMONS_IMAGE],
            AssetSource.COMMONS_IMAGE,
            results,
            on_scene_start=on_scene_start,
            on_scene_complete=on_scene_complete,
        )

        # Sequential (not batched into parallel_items above): ResearchAssetProvider
        # mutates a shared MediaCandidate.used flag across scenes competing for
        # the same property's limited media pool — resolving in parallel would
        # race two scenes onto the same "unused" candidate.
        self._resolve_sequential(
            pending[AssetSource.RESEARCH],
            AssetSource.RESEARCH,
            results,
            on_scene_start=on_scene_start,
            on_scene_complete=on_scene_complete,
        )

        # Image and video generation are separate Flow API endpoints/workflows
        # (see providers/flow/provider.py) — batch them independently so a
        # project's image scenes and video scenes never get mixed into one
        # GENERATE call.
        for source, provider in (
            (AssetSource.FLOW_IMAGE, self.flow_image_provider),
            (AssetSource.FLOW_VIDEO, self.flow_video_provider),
        ):
            self._resolve_flow_batch(
                source,
                provider,
                pending[source],
                results,
                on_scene_start=on_scene_start,
                on_scene_complete=on_scene_complete,
            )

        ok_count = sum(1 for r in results.values() if r.ok)
        self.log(f"[ASSET] {ok_count}/{len(rows)} scenes ready.")
        return ResolveSummary(results=results, warnings=warnings)

    def regenerate_scene(self, scene: SceneRow) -> AssetResult:
        source = self.classify(scene)
        provider = self._provider_for(source)
        if provider is None:
            return self._store_failure(
                scene, source, f"{source.value} provider is not configured for this run."
            )
        prev = self.manifest.get(scene.scene_number) or {}
        exclude = (
            {"provider_asset_id": prev["provider_asset_id"]}
            if prev.get("provider_asset_id")
            else None
        )
        self.log(f"[ASSET] Scene {scene.scene_number} -> {source.value.upper()} (regenerate)")
        try:
            result = provider.regenerate(scene, self.images_dir, exclude=exclude, log=self.log)
        except AssetError as exc:
            result = AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=source, status=SceneStatus.FAILED, error=exc.reason,
            )
        except Exception as exc:
            result = AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=source, status=SceneStatus.FAILED, error=f"unexpected error: {exc}",
            )
        self._record_failed_approach(scene, source, result)
        self._finalize(scene, result)
        return result

    def retry_flow_batch(self, scenes: List[SceneRow]) -> Dict[str, AssetResult]:
        """One GENERATE for many Flow retries — avoids N parallel 'already running' races."""
        if not scenes:
            return {}
        by_source: Dict[AssetSource, List[SceneRow]] = {}
        for scene in scenes:
            self._cancelled_scenes.discard(scene_key(scene.scene_number))
            if self._was_skipped(scene):
                self._clear_skip(scene)
            source = self.classify(scene)
            if source not in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO):
                source = AssetSource.FLOW_IMAGE
            by_source.setdefault(source, []).append(scene)

        out: Dict[str, AssetResult] = {}
        for source, group in by_source.items():
            provider = self._provider_for(source)
            results: Dict[str, AssetResult] = {}
            self._resolve_flow_batch(source, provider, group, results)
            out.update(results)
        return out

    def _was_skipped(self, scene: SceneRow) -> bool:
        key = scene_key(scene.scene_number)
        if key in self.recovery.skipped:
            return True
        rec = self.manifest.get(scene.scene_number) or {}
        err = str(rec.get("error") or "").lower()
        return "placeholder only" in err or err.startswith("skipped")

    def _clear_skip(self, scene: SceneRow) -> None:
        self.recovery.skipped.discard(scene_key(scene.scene_number))

    def retry_scene(self, scene: SceneRow) -> AssetResult:
        """Repeat the same provider; skipped scenes become a Flow image instead."""
        key = scene_key(scene.scene_number)
        self._cancelled_scenes.discard(key)
        if self._was_skipped(scene):
            self._clear_skip(scene)
            self.log(f"[SCENE {scene.scene_number}] Replacing skip with Flow image")
            return self.change_source(scene, "flow_image")
        self.log(f"[SCENE {scene.scene_number}] Retry")
        return self.regenerate_scene(scene)

    def alternative_scene(self, scene: SceneRow) -> AssetResult:
        """Different query, candidate, or declared fallback — never the last failed query."""
        key = scene_key(scene.scene_number)
        self._cancelled_scenes.discard(key)
        self._clear_skip(scene)
        action = self.recovery.next_alternative(scene)
        if action["kind"] == "youtube_query":
            self.log(
                f"[SCENE {scene.scene_number}] Trying alternative query: \"{action['query']}\""
            )
            alt = dataclasses.replace(
                scene, prompt=action["query"], search_queries=list(action["queries"])
            )
            result = self._resolve_one(alt, AssetSource.YOUTUBE_VIDEO, try_declared_fallbacks=False)
            if not result.ok:
                self.recovery.mark_query(key, action["query"])
            return result
        if action["kind"] == "provider":
            name = action["provider"]
            self.log(f"[SCENE {scene.scene_number}] Trying alternative provider: {name.upper()}")
            fallback = scene.as_fallback(name)
            result = self._resolve_one(
                fallback, self.classify(fallback), try_declared_fallbacks=False
            )
            if not result.ok:
                self.recovery.mark_provider(key, name)
            return result
        if action["kind"] == "regenerate_exclude":
            self.log(f"[SCENE {scene.scene_number}] Trying alternative result from same provider")
            return self.regenerate_scene(scene)
        self.log(f"[SCENE {scene.scene_number}] No unused alternative remains")
        return self._store_failure(
            scene, self.classify(scene), "No unused alternative remains for this scene."
        )

    def change_source(self, scene: SceneRow, provider_name: str) -> AssetResult:
        key = scene_key(scene.scene_number)
        self._cancelled_scenes.discard(key)
        self._clear_skip(scene)
        self.log(f"[SCENE {scene.scene_number}] Change source -> {provider_name}")
        fallback = scene.as_fallback(provider_name)
        return self._resolve_one(fallback, self.classify(fallback), try_declared_fallbacks=False)

    def change_source_flow_batch(
        self, scenes: List[SceneRow], provider_name: str,
    ) -> Dict[str, AssetResult]:
        """Switch many scenes to Flow and resolve in one GENERATE (multi-account)."""
        if not scenes:
            return {}
        self.log(
            f"[ASSET] Change source -> {provider_name} for {len(scenes)} scene(s) "
            f"(batched Flow)"
        )
        updated: List[SceneRow] = []
        for scene in scenes:
            key = scene_key(scene.scene_number)
            self._cancelled_scenes.discard(key)
            self._clear_skip(scene)
            updated.append(scene.as_fallback(provider_name))

        by_source: Dict[AssetSource, List[SceneRow]] = {}
        for scene in updated:
            source = self.classify(scene)
            if source not in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO):
                continue
            by_source.setdefault(source, []).append(scene)

        out: Dict[str, AssetResult] = {}
        for source, group in by_source.items():
            provider = self._provider_for(source)
            results: Dict[str, AssetResult] = {}
            self._resolve_flow_batch(source, provider, group, results)
            out.update(results)
        return out

    def skip_scene(self, scene: SceneRow) -> AssetResult:
        """Keep narration; write a placeholder still so later scenes are untouched."""
        key = scene_key(scene.scene_number)
        n = int(str(scene.scene_number).strip())
        path = self.images_dir / f"{n:03d}.png"
        path.write_bytes(PLACEHOLDER_PNG)
        self.recovery.skipped.add(key)
        result = AssetResult(
            scene_number=scene.scene_number,
            path=path,
            media_type=MediaType.IMAGE,
            source=self.classify(scene),
            status=SceneStatus.SKIPPED,
            error="Skipped — no visual asset (placeholder only).",
        )
        self._finalize(scene, result)
        return result

    def attach_manual_clip(self, scene: SceneRow, source_path: Path) -> AssetResult:
        """Copy a user-picked local file into Images/ and mark the scene READY.

        Storage/state only — does not search YouTube, Pexels, or Flow.
        """
        from manual_clip import ManualClipError, install_manual_clip

        key = scene_key(scene.scene_number)
        self._cancelled_scenes.discard(key)
        self._clear_skip(scene)
        try:
            dest, info = install_manual_clip(self.images_dir, scene.scene_number, source_path)
        except ManualClipError as exc:
            return self._store_failure(scene, AssetSource.MANUAL, str(exc))
        except Exception as exc:
            return self._store_failure(scene, AssetSource.MANUAL, f"Could not add local clip: {exc}")
        meta = {
            "origin": "manual",
            "original_name": Path(source_path).name,
            "width": info.width,
            "height": info.height,
        }
        if info.duration is not None:
            meta["duration"] = info.duration
        result = AssetResult(
            scene_number=scene.scene_number,
            path=dest,
            media_type=info.media_type,
            source=AssetSource.MANUAL,
            status=SceneStatus.READY,
            metadata=meta,
        )
        self.log(f"[ASSET] Scene {scene.scene_number} -> MANUAL ({dest.name})")
        self._finalize(scene, result)
        return result
