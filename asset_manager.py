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
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import video_generator as vg
from providers.base import (
    AssetError,
    AssetResult,
    AssetSource,
    LogFn,
    MediaType,
    SceneRow,
    SceneStatus,
)
from providers.local_provider import LocalProvider
from providers.router import SceneAssetRouter

MANIFEST_NAME = ".asset_manifest.json"


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
        self._data[_key(scene_number)] = record
        self.save()

    def all(self) -> Dict[str, dict]:
        return dict(self._data)


@dataclasses.dataclass
class ResolveSummary:
    results: Dict[str, AssetResult]
    warnings: List[str]

    @property
    def failed(self) -> List[AssetResult]:
        return [r for r in self.results.values() if not r.ok and r.status != SceneStatus.CANCELLED]

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
        log: LogFn = print,
    ):
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.local_provider = LocalProvider()
        self.stock_provider = stock_provider
        self.flow_image_provider = flow_image_provider
        self.flow_video_provider = flow_video_provider
        self.manifest = AssetManifest(self.images_dir)
        self.log = log
        self._cancel_event = threading.Event()

    # ---------- cancellation ----------

    def request_cancel(self) -> None:
        """Cooperative cancellation: scenes not yet started are skipped (marked
        CANCELLED, not FAILED); a scene already resolved before this call keeps its
        result. Does not abort mid-flight network calls, but a Flow batch already in
        progress is told to stop via the engine's own STOP message (see
        providers/flow/provider.py), so it doesn't run for the full timeout."""
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ---------- routing / provider lookup ----------

    def _provider_for(self, source: AssetSource):
        return {
            AssetSource.LOCAL: self.local_provider,
            AssetSource.STOCK: self.stock_provider,
            AssetSource.STOCK_IMAGE: self.stock_provider,
            AssetSource.STOCK_VIDEO: self.stock_provider,
            AssetSource.FLOW_IMAGE: self.flow_image_provider,
            AssetSource.FLOW_VIDEO: self.flow_video_provider,
        }[source]

    def classify(self, scene: SceneRow) -> AssetSource:
        return SceneAssetRouter.classify(scene) or AssetSource.LOCAL

    def validate_rows(self, rows: List[SceneRow]) -> List[str]:
        return SceneAssetRouter.validate(rows, self.images_dir)

    # ---------- caching ----------

    def _cache_hit(self, scene: SceneRow, source: AssetSource) -> Optional[AssetResult]:
        """LOCAL is never cache-shortcut (it's a free lookup and must never be treated
        as something we could delete/replace); STOCK/FLOW are cached against the
        prompt/query that produced them, and only count if the file is still there."""
        if source == AssetSource.LOCAL:
            return None
        record = self.manifest.get(scene.scene_number)
        if not record or record.get("status") != "complete":
            return None
        if record.get("source") != source.value:
            return None
        if source in (AssetSource.FLOW_IMAGE, AssetSource.FLOW_VIDEO) and record.get("prompt") != scene.prompt:
            return None
        if (
            source in (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO)
            and record.get("stock_query") != scene.stock
        ):
            return None
        raw_path = record.get("local_path")
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.is_file():
            return None
        media_type = MediaType.VIDEO if vg.is_video_file(path) else MediaType.IMAGE
        return AssetResult(
            scene_number=scene.scene_number,
            path=path,
            media_type=media_type,
            source=source,
            status=SceneStatus.READY,
            metadata=record,
        )

    def _record_from_result(self, scene: SceneRow, result: AssetResult) -> dict:
        record = {
            "source": result.source.value,
            "type": result.media_type.value if result.media_type else None,
            "prompt": scene.prompt,
            "stock_query": scene.stock,
            "local_path": str(result.path) if result.path else None,
            "status": "complete" if result.ok else "failed",
            "resolved_at": time.time(),
            "error": result.error,
        }
        # Provider-specific extras (provider_asset_id, author, source_url, ...)
        record.update(result.metadata or {})
        return record

    def _remove_stale_file(self, scene_number: str, keep: Path) -> None:
        """After a successful STOCK/FLOW download, delete any other pre-existing file
        for this scene (e.g. an old 001.jpg lingering next to a fresh 001.mp4) so the
        renderer's extension-priority lookup can't pick up the wrong one."""
        existing = vg.find_image_for_scene(self.images_dir, scene_number)
        if existing and existing.resolve() != keep.resolve() and existing.is_file():
            existing.unlink()

    def _finalize(self, scene: SceneRow, result: AssetResult) -> None:
        if result.ok and result.source != AssetSource.LOCAL:
            self._remove_stale_file(scene.scene_number, keep=result.path)
        elif not result.ok:
            self.log(f"[ASSET] Scene {scene.scene_number} -> FAILED: {result.error}")
        self.manifest.set(scene.scene_number, self._record_from_result(scene, result))

    def _store_failure(self, scene: SceneRow, source: AssetSource, error: str) -> AssetResult:
        result = AssetResult(
            scene_number=scene.scene_number,
            path=None,
            media_type=None,
            source=source,
            status=SceneStatus.FAILED,
            error=error,
        )
        self._finalize(scene, result)
        return result

    def _resolve_one(self, scene: SceneRow, source: AssetSource) -> AssetResult:
        provider = self._provider_for(source)
        if provider is None:
            return self._store_failure(
                scene, source, f"{source.value} provider is not configured for this run."
            )
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
        self.manifest.set(scene.scene_number, self._record_from_result(scene, result))
        return result

    def _resolve_flow_batch(
        self, source: AssetSource, provider, scenes: List[SceneRow], results: Dict[str, AssetResult]
    ) -> None:
        """Shared by resolve_all() for both FLOW_IMAGE and FLOW_VIDEO — one batched
        GENERATE call per kind (never mixed), same cancel/error handling either way."""
        if not scenes:
            return
        if self.is_cancelled:
            for scene in scenes:
                results[scene.scene_number] = self._cancelled_result(scene, source)
            return
        if provider is None:
            kind = "image" if source == AssetSource.FLOW_IMAGE else "video"
            for scene in scenes:
                results[scene.scene_number] = self._store_failure(
                    scene, source,
                    f"Flow {kind} provider is not configured (no Flow engine connection / no accounts logged in).",
                )
            return

        self.log(f"[ASSET] {len(scenes)} scene(s) -> {source.value.upper()} (batched)")
        try:
            batch_results = provider.resolve_batch(
                scenes, self.images_dir, log=self.log, should_stop=lambda: self.is_cancelled
            )
        except Exception as exc:
            batch_results = {}
            self.log(f"[FLOW] batch failed: {exc}")
        for scene in scenes:
            result = batch_results.get(scene.scene_number) or AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=source, status=SceneStatus.FAILED,
                error="Flow engine returned no result for this scene.",
            )
            self._finalize(scene, result)
            results[scene.scene_number] = result

    def resolve_all(self, rows: List[SceneRow]) -> ResolveSummary:
        errors = self.validate_rows(rows)
        if errors:
            raise AssetError("validation", "; ".join(errors))
        self.reset_cancel()

        results: Dict[str, AssetResult] = {}
        warnings: List[str] = []
        pending: Dict[AssetSource, List[SceneRow]] = {
            AssetSource.LOCAL: [],
            AssetSource.STOCK: [], AssetSource.STOCK_IMAGE: [], AssetSource.STOCK_VIDEO: [],
            AssetSource.FLOW_IMAGE: [], AssetSource.FLOW_VIDEO: [],
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
                continue
            pending[source].append(scene)

        for scene in pending[AssetSource.LOCAL]:
            if self.is_cancelled:
                results[scene.scene_number] = self._cancelled_result(scene, AssetSource.LOCAL)
                continue
            results[scene.scene_number] = self._resolve_one(scene, AssetSource.LOCAL)

        for stock_source in (AssetSource.STOCK, AssetSource.STOCK_IMAGE, AssetSource.STOCK_VIDEO):
            for scene in pending[stock_source]:
                if self.is_cancelled:
                    results[scene.scene_number] = self._cancelled_result(scene, stock_source)
                    continue
                results[scene.scene_number] = self._resolve_one(scene, stock_source)

        # Image and video generation are separate Flow API endpoints/workflows
        # (see providers/flow/provider.py) — batch them independently so a
        # project's image scenes and video scenes never get mixed into one
        # GENERATE call.
        for source, provider in (
            (AssetSource.FLOW_IMAGE, self.flow_image_provider),
            (AssetSource.FLOW_VIDEO, self.flow_video_provider),
        ):
            self._resolve_flow_batch(source, provider, pending[source], results)

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
        self._finalize(scene, result)
        return result
