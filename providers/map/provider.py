"""Map scene provider — asset_type=map.

Renders an animated satellite-map clip for the scene (map_scene / map-engine)
into Images/NNN.mp4, like any other video source. No Flow credits; a place
that can't be found fails the scene with a clear Needs-action message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from providers.base import AssetProvider, AssetResult, AssetSource, LogFn, MediaType, SceneRow, SceneStatus

DEFAULT_MAP_DURATION = 12.0


def _scene_file(images_dir: Path, scene_number: str) -> Path:
    try:
        stem = f"{int(str(scene_number).strip()):03d}"
    except ValueError:
        stem = str(scene_number).strip()
    return Path(images_dir) / f"{stem}.mp4"


class MapProvider(AssetProvider):
    name = "map"
    source = AssetSource.MAP

    def __init__(self, settings: Optional[dict] = None, duration: float = DEFAULT_MAP_DURATION, render=None):
        self.settings = dict(settings or {})
        self.duration = float(duration)
        self._render = render  # injectable for tests; default map_scene.render.render_map
        self.should_stop_scene = None
        self.should_stop_run: Optional[Callable[[], bool]] = None
        self._ai = None
        self._ai_ready = False

    def _ai_resolver(self):
        """Gemini fallback for places not in the bundled data — only when a
        Gemini key is configured; answers are cached on disk."""
        if not self._ai_ready:
            self._ai_ready = True
            try:
                from visual_director.llm import gemini_configured

                if gemini_configured(self.settings):
                    from map_scene.ai_places import gemini_place_resolver

                    self._ai = gemini_place_resolver(self.settings)
            except Exception:
                self._ai = None
        return self._ai

    def _stopped(self, scene: SceneRow) -> bool:
        scene_cb, run_cb = getattr(self, "should_stop_scene", None), getattr(self, "should_stop_run", None)
        return bool((callable(scene_cb) and scene_cb(str(scene.scene_number))) or (callable(run_cb) and run_cb()))

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        from map_scene.places import PlaceNotFound
        from map_scene.render import MapRenderCancelled, MapRenderError, render_map
        from map_scene.spec import MapPromptError

        sn = scene.scene_number
        prompt = (scene.prompt or "").strip()
        if not prompt:
            return AssetResult(sn, None, None, self.source, SceneStatus.FAILED,
                               error="No place given for this map scene (e.g. \"Florida > Florida Panhandle\").")
        if self._stopped(scene):
            return AssetResult(sn, None, None, self.source, SceneStatus.CANCELLED, error="Cancelled.")
        target = _scene_file(images_dir, sn)
        log(f"[MAP] Scene {sn} -> rendering map \"{prompt}\"")
        last_pct = [-1]

        def progress(frame: int, total: int) -> None:
            pct = int(frame * 100 / max(1, total)) // 25 * 25
            if pct > last_pct[0]:
                last_pct[0] = pct
                log(f"[MAP] Scene {sn} -> rendering map {pct}%")

        render = self._render or render_map
        try:
            result = render(prompt, target, duration=self.duration, ai=self._ai_resolver(),
                            progress=progress, cancel_check=lambda: self._stopped(scene))
        except MapRenderCancelled:
            return AssetResult(sn, None, None, self.source, SceneStatus.CANCELLED, error="Cancelled.")
        except (MapPromptError, PlaceNotFound) as exc:
            return AssetResult(sn, None, None, self.source, SceneStatus.FAILED, error=str(exc))
        except MapRenderError as exc:
            return AssetResult(sn, None, None, self.source, SceneStatus.FAILED, error=str(exc))
        except Exception as exc:  # never let one map take the whole run down
            return AssetResult(sn, None, None, self.source, SceneStatus.FAILED, error=f"Map render failed: {exc}")
        for note in getattr(result, "notes", None) or []:
            log(f"[MAP] Scene {sn} -> {note}")
        log(f"[MAP] Scene {sn} -> map ready ({Path(result.output).name})")
        return AssetResult(
            scene_number=sn, path=Path(result.output), media_type=MediaType.VIDEO, source=self.source,
            status=SceneStatus.READY,
            metadata={"provider": self.name, "prompt": prompt, "map_places": result.places,
                      "clip_duration": self.duration},
        )
