"""LocalProvider: thin wrapper around video_generator's existing filename-convention
lookup. This is the ONLY provider that touches pre-existing video_generator code —
it never writes/downloads anything, it just reports what's already on disk."""

from __future__ import annotations

from pathlib import Path

import video_generator as vg

from .base import AssetProvider, AssetResult, AssetSource, LogFn, MediaType, SceneRow, SceneStatus


class LocalProvider(AssetProvider):
    name = "local"
    source = AssetSource.LOCAL

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        path = vg.find_image_for_scene(images_dir, scene.scene_number)
        if path is None:
            return AssetResult(
                scene_number=scene.scene_number,
                path=None,
                media_type=None,
                source=AssetSource.LOCAL,
                status=SceneStatus.FAILED,
                error=(
                    f"No manual asset found for scene {scene.scene_number} in {images_dir} "
                    f"(and no prompt/stock keywords given for this scene)."
                ),
            )
        media_type = MediaType.VIDEO if vg.is_video_file(path) else MediaType.IMAGE
        log(f"[ASSET] Scene {scene.scene_number} -> LOCAL ({path.name})")
        return AssetResult(
            scene_number=scene.scene_number,
            path=path,
            media_type=media_type,
            source=AssetSource.LOCAL,
            status=SceneStatus.READY,
            metadata={},
        )
