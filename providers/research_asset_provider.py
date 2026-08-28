"""ResearchAssetProvider: bridges the research/ package's ResearchResult
(already-downloaded, property-scoped media) into the existing AssetProvider
contract, so AssetManager can treat research media exactly like Archive/NASA
output — this file, not research/, is where the CSV/scene pipeline
boundary lives.

Ranking stays owned by the existing Smart Visual Selection machinery
(smart_selection_score / SelectionHistory / scene_has_manual_authority) —
this provider only pre-filters to unused, on-disk candidates and adds a
small boost from property_match_score/script_relevance on top of the
existing score, never a second ranking system.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from providers.base import AssetProvider, AssetResult, AssetSource, LogFn, MediaType, SceneRow, SceneStatus
from research.models import MediaCandidate


class ResearchAssetProvider(AssetProvider):
    name = "research"
    source = AssetSource.RESEARCH

    def __init__(self, candidates: List[MediaCandidate]):
        self.candidates = list(candidates)
        self.should_stop_scene = None
        self.resolved_style = None
        self.selection_history = None

    def has_unused_candidates(self) -> bool:
        return any(self._is_available(c) for c in self.candidates)

    @staticmethod
    def _ensure_dimensions(candidate: MediaCandidate) -> None:
        """Smart Visual Selection's technical-quality gate rejects any
        candidate with no known width/height ("missing dimensions") unless
        the provider is on its hardcoded archival allowlist — which we
        deliberately don't touch (see module docstring: ranking stays
        owned by the existing scorer). The research engine normally already
        captures image dimensions at download time, but probe the file
        locally as a defensive fallback so a manifest gap never silently
        drops an otherwise-good photo."""
        if candidate.width and candidate.height:
            return
        if candidate.media_type != "image" or not candidate.local_path:
            return
        try:
            from PIL import Image

            with Image.open(candidate.local_path) as img:
                candidate.width, candidate.height = img.size
        except Exception:  # noqa: BLE001 - Pillow not installed, or not a real image
            pass

    @staticmethod
    def _is_available(candidate: MediaCandidate) -> bool:
        return bool(not candidate.used and candidate.local_path and Path(candidate.local_path).is_file())

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        available = [c for c in self.candidates if self._is_available(c)]
        if not available:
            return AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=self.source, status=SceneStatus.FAILED,
                error="No unused research media remaining for this property.",
            )

        from style_engine.visual_selection import (
            build_selection_context,
            scene_has_manual_authority,
            smart_selection_score,
        )

        manual = scene_has_manual_authority(scene)
        ctx = None if manual else build_selection_context(scene, self.resolved_style, self.selection_history)
        query = (scene.prompt or scene.stock or getattr(scene, "visual_description", "") or scene.script_segment or "").strip()
        used_ids = set(getattr(self.selection_history, "used_asset_ids", None) or set())
        provider_counts = getattr(self.selection_history, "provider_counts", None)

        scored = []
        for candidate in available:
            self._ensure_dimensions(candidate)
            asset_id = f"research:{candidate.source_id or ''}:{Path(candidate.local_path).name}"
            breakdown = smart_selection_score(
                query=query,
                script_segment=scene.script_segment or "",
                visual_description=getattr(scene, "visual_description", "") or "",
                title=candidate.title or "",
                description=candidate.role or "",
                extra_text=candidate.role or "",
                width=candidate.width or 0,
                height=candidate.height or 0,
                download_url=candidate.source_url,
                provider="research",
                media_type=candidate.media_type,
                used_asset_ids=used_ids,
                asset_id=asset_id,
                provider_use_counts=provider_counts,
                context=ctx,
            )
            if breakdown.reject_reason:
                continue
            # property_match_score/script_relevance are pre-filter/pre-sort
            # signals from the research engine, folded in as a small boost
            # on top of the existing scorer's total — not a replacement.
            boost = 0.15 * candidate.property_match_score + 0.10 * (candidate.script_relevance or 0.0)
            scored.append((breakdown.total + boost, candidate, asset_id))

        if not scored:
            return AssetResult(
                scene_number=scene.scene_number, path=None, media_type=None,
                source=self.source, status=SceneStatus.FAILED,
                error="All research media candidates were rejected by scoring for this scene.",
            )

        scored.sort(key=lambda t: t[0], reverse=True)
        _, chosen, asset_id = scored[0]

        n = int(str(scene.scene_number).strip())
        ext = Path(chosen.local_path).suffix or (".jpg" if chosen.media_type == "image" else ".mp4")
        target_path = Path(images_dir) / f"{n:03d}{ext}"
        shutil.copy2(chosen.local_path, target_path)
        chosen.used = True

        if self.selection_history is not None:
            self.selection_history.record(
                provider="research", asset_id=asset_id,
                title=chosen.title or "", description=chosen.role or "",
            )

        log(f"[ASSET] Scene {scene.scene_number} -> RESEARCH ({Path(chosen.local_path).name}, role={chosen.role})")
        media_type = MediaType.VIDEO if chosen.media_type == "video" else MediaType.IMAGE
        return AssetResult(
            scene_number=scene.scene_number, path=target_path, media_type=media_type,
            source=self.source, status=SceneStatus.READY,
            metadata={
                "provider": "research",
                "source_url": chosen.source_url,
                "role": chosen.role,
                "property_match_score": chosen.property_match_score,
                "script_relevance": chosen.script_relevance,
                "license_status": chosen.license_status,
                "license_evidence": chosen.license_evidence,
            },
        )
