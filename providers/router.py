"""
SceneAssetRouter: pure CSV-routing logic. Knows nothing about how any provider
works. Supports both CSV shapes SceneRow understands — the explicit
`asset_type` column (image/video/stock/local) and the legacy prompt/stock
inference — plus one backward-compatibility exception: both empty (or
asset_type=local) is allowed if a local file already covers the scene, so old
2-column CSVs with manually-placed Images/ keep working unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import video_generator as vg

from .base import AssetSource, SceneRow


class SceneAssetRouter:
    @staticmethod
    def classify(scene: SceneRow) -> Optional[AssetSource]:
        """CSV-only classification. Returns None for a scene that must fall back
        to an existing local file (asset_type=local, or — legacy format — both
        prompt and stock empty); this function deliberately doesn't touch the
        filesystem, so it stays a pure function of the CSV row."""
        if scene.wants_flow_video:
            return AssetSource.FLOW_VIDEO
        if scene.wants_flow_image:
            return AssetSource.FLOW_IMAGE
        if scene.wants_stock:
            return scene.stock_source
        if scene.wants_youtube:
            return AssetSource.YOUTUBE_VIDEO
        if scene.wants_archive:
            return AssetSource.ARCHIVE_VIDEO
        if scene.wants_nasa:
            return AssetSource.NASA_VIDEO
        if scene.wants_commons_video:
            return AssetSource.STOCK_VIDEO
        if scene.wants_commons_image:
            return AssetSource.STOCK_IMAGE
        return None

    @staticmethod
    def validate(rows: List[SceneRow], images_dir: Path) -> List[str]:
        """Fail-fast validation errors, one per scene that has neither a routable
        asset_type/prompt/stock value nor an existing local file. Mirrors
        video_generator's existing fail-before-Whisper philosophy."""
        errors: List[str] = []
        for scene in rows:
            if SceneAssetRouter.classify(scene) is not None:
                continue
            if vg.find_image_for_scene(images_dir, scene.scene_number) is not None:
                continue
            try:
                hint = f"{int(scene.scene_number):03d}"
            except ValueError:
                hint = scene.scene_number
            errors.append(
                f"Scene {scene.scene_number}: no prompt, no stock keywords, and no "
                f"local file found in {images_dir} (e.g. {hint}.png or {hint}.mp4). "
                f"Add a prompt, a stock query, or place a matching file there."
            )
        return errors
