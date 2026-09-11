"""LocalProvider: thin wrapper around video_generator's existing filename-convention
lookup. This is the ONLY provider that touches pre-existing video_generator code —
it never writes/downloads anything for legacy ``local`` rows; for
``local_video`` / ``local_image`` it may copy a numbered library file into
Images/ via the existing manual-clip installer so the renderer stays unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import video_generator as vg

from .base import AssetProvider, AssetResult, AssetSource, LogFn, MediaType, SceneRow, SceneStatus
from .local_assets import (
    find_numbered_asset,
    is_local_numbered_type,
    media_kind_for_asset_type,
)


class LocalProvider(AssetProvider):
    name = "local"
    source = AssetSource.LOCAL

    def __init__(self, library_dir: Optional[Path] = None):
        # Optional folder of numbered assets (Local Assets mode). When unset,
        # numbered types still look inside images_dir with media-type checks.
        self.library_dir: Optional[Path] = Path(library_dir) if library_dir else None

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        if is_local_numbered_type(scene.asset_type):
            return self._resolve_numbered(scene, images_dir, log=log)
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

    def _resolve_numbered(
        self, scene: SceneRow, images_dir: Path, log: LogFn = print
    ) -> AssetResult:
        kind = media_kind_for_asset_type(scene.asset_type)
        assert kind is not None
        search_dir = self.library_dir if self.library_dir is not None else Path(images_dir)
        match, issue = find_numbered_asset(search_dir, scene.scene_number, kind)
        if issue is not None or match is None:
            err = issue.reason if issue is not None else "Local asset not found"
            return AssetResult(
                scene_number=scene.scene_number,
                path=None,
                media_type=None,
                source=AssetSource.LOCAL,
                status=SceneStatus.FAILED,
                error=err,
                metadata={
                    "origin": "local_numbered",
                    "expected_stem": issue.expected_stem if issue else None,
                    "media_kind": kind,
                    "library_dir": str(search_dir),
                },
            )

        dest = match.path
        meta = {
            "origin": "local_numbered",
            "library_path": str(match.path),
            "expected_stem": match.expected_stem,
            "media_kind": kind,
        }
        # Install into the project Images/ tree when the match lives outside it,
        # so Whisper/editorial/render keep using the existing 00N.ext convention.
        try:
            images_dir = Path(images_dir)
            if match.path.resolve().parent.resolve() != images_dir.resolve():
                from manual_clip import ManualClipError, install_manual_clip

                dest, info = install_manual_clip(images_dir, scene.scene_number, match.path)
                meta["width"] = info.width
                meta["height"] = info.height
                if info.duration is not None:
                    meta["duration"] = info.duration
            else:
                # Already in Images/ — still clear a conflicting opposite-type file
                # so find_image_for_scene cannot prefer the wrong media later.
                self._clear_conflicting_media(images_dir, scene.scene_number, dest)
        except Exception as exc:
            # Keep ManualClipError messages user-facing; never fall back to cloud.
            from manual_clip import ManualClipError

            reason = str(exc) if isinstance(exc, ManualClipError) else f"Could not install local asset: {exc}"
            return AssetResult(
                scene_number=scene.scene_number,
                path=None,
                media_type=None,
                source=AssetSource.LOCAL,
                status=SceneStatus.FAILED,
                error=reason,
                metadata=meta,
            )

        media_type = MediaType.VIDEO if kind == "video" else MediaType.IMAGE
        log(f"[ASSET] Scene {scene.scene_number} -> LOCAL {kind.upper()} ({Path(dest).name})")
        return AssetResult(
            scene_number=scene.scene_number,
            path=Path(dest),
            media_type=media_type,
            source=AssetSource.LOCAL,
            status=SceneStatus.READY,
            metadata=meta,
        )

    @staticmethod
    def _clear_conflicting_media(images_dir: Path, scene_number: str, keep: Path) -> None:
        keep_res = Path(keep).resolve()
        while True:
            existing = vg.find_image_for_scene(images_dir, scene_number)
            if existing is None or existing.resolve() == keep_res:
                break
            existing.unlink(missing_ok=True)
