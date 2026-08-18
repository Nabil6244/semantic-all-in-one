"""
FlowProvider: AssetProvider backed by the flow-engine Node sidecar. Video
Generator only ever calls resolve()/resolve_batch()/regenerate() here — it
never sees a prompt payload shape, a reCAPTCHA token, or a Playwright page.
All of that stays inside flow-engine/lib/flow-api.js, exactly as intended by
the provider boundary.

One class handles both image and video generation (the underlying engine call
— GENERATE with settings.mediaKind — and the Google Flow API endpoints behind
it are genuinely different per media_kind; see flow-engine/lib/flow-api.js's
generateOneImage vs generateOneVideo), distinguished by the `media_kind`
constructor argument. AssetManager holds one instance per kind
(FLOW_IMAGE / FLOW_VIDEO) so a project's image and video scenes are always
batched separately — they hit different Flow API endpoints and must not be
mixed into one GENERATE call.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

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
from .client import FlowClientError
from .engine_manager import FlowEngineError, FlowEngineManager

GENERATE_TIMEOUT_SECONDS = 20 * 60  # long multi-account batches with retries can take a while

_SOURCE_BY_KIND = {"image": AssetSource.FLOW_IMAGE, "video": AssetSource.FLOW_VIDEO}
_EXT_BY_KIND = {"image": "png", "video": "mp4"}
_MEDIA_TYPE_BY_KIND = {"image": MediaType.IMAGE, "video": MediaType.VIDEO}


class FlowProvider(AssetProvider):
    name = "flow"

    def __init__(
        self,
        engine_manager: FlowEngineManager,
        media_kind: str = "image",
        account_ids: Optional[List[str]] = None,
        flow_settings: Optional[dict] = None,
    ):
        if media_kind not in _SOURCE_BY_KIND:
            raise ValueError(f"media_kind must be 'image' or 'video', got {media_kind!r}")
        self.engine_manager = engine_manager
        self.media_kind = media_kind
        self.source = _SOURCE_BY_KIND[media_kind]
        self.account_ids = account_ids  # None = use all signed-in accounts
        # GUI-configured Flow Settings (model/aspectRatio for image;
        # videoModel/videoDuration for video) — see app.py's Flow Settings
        # section. Only the keys relevant to this instance's media_kind matter;
        # the engine ignores unrelated ones.
        self.flow_settings = flow_settings or {}

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        return self.resolve_batch([scene], images_dir, log=log)[scene.scene_number]

    def regenerate(
        self, scene: SceneRow, images_dir: Path, exclude: Optional[dict] = None, log: LogFn = print
    ) -> AssetResult:
        # Flow has no "asset id" to exclude like stock does — regenerating just
        # means resubmitting the same prompt for a fresh result.
        return self.resolve(scene, images_dir, log=log)

    def resolve_batch(
        self,
        scenes: List[SceneRow],
        images_dir: Path,
        log: LogFn = print,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, AssetResult]:
        if not scenes:
            return {}
        try:
            client = self.engine_manager.ensure_running()
        except FlowEngineError as exc:
            return {s.scene_number: self._fail(s, str(exc)) for s in scenes}

        if client.get_state().get("running"):
            error = "A Flow batch is already running in the engine — try again shortly."
            return {s.scene_number: self._fail(s, error) for s in scenes}

        downloads_root = client.get_info().get("downloadsRoot") or self._await_downloads_root(client)
        if not downloads_root:
            error = "Flow engine did not report a downloads folder — cannot locate generated files."
            return {s.scene_number: self._fail(s, error) for s in scenes}

        prompts = [s.prompt for s in scenes]
        kind_label = self.media_kind.upper()
        log(f"[FLOW] Sending {len(prompts)} {kind_label} prompt(s) to the Flow engine...")

        progress: Dict[int, dict] = {}
        done_event = threading.Event()
        terminal_error: List[str] = []

        def on_message(msg: dict) -> None:
            mtype = msg.get("type")
            if mtype == "BATCH_PROGRESS":
                idx = msg.get("index")
                status = msg.get("status")
                worker = msg.get("label") or msg.get("accountId") or "worker"
                if idx is None or idx >= len(scenes):
                    return
                scene = scenes[idx]
                if status == "running":
                    log(f"[FLOW] {worker} -> Scene {scene.scene_number} generating {self.media_kind}...")
                elif status in ("done", "failed"):
                    progress[idx] = msg
                    if status == "failed":
                        log(f"[FLOW] {worker} -> Scene {scene.scene_number} failed: {msg.get('message')}")
                    else:
                        log(f"[FLOW] {worker} -> Scene {scene.scene_number} generated")
            elif mtype == "GENERATE_DONE":
                done_event.set()
            elif mtype == "STATE" and msg.get("generateError") and not msg.get("running"):
                # orchestrator.js's generate() returns EARLY (no GENERATE_DONE broadcast
                # at all) for "no signed-in accounts" / "no prompts" — this STATE push is
                # the only terminal signal in that case, so we must race on it too or hang
                # for the full timeout. Confirmed against the real engine (see report).
                terminal_error.append(msg["generateError"])
                done_event.set()

        # Subscribe BEFORE sending GENERATE so a fast engine response can't arrive
        # before we're listening for it.
        unsubscribe = client.subscribe(on_message)
        cancelled = False
        try:
            settings = {"imageCount": 1, "mediaKind": self.media_kind, **self.flow_settings}
            client.generate(prompts, settings=settings, account_ids=self.account_ids)

            # Video generation genuinely takes much longer (Veo renders + polls to
            # completion, see flow-api.js's videoPollTimeoutMs) than image — give it
            # more room before declaring a timeout.
            timeout_seconds = GENERATE_TIMEOUT_SECONDS * (3 if self.media_kind == "video" else 1)
            deadline = time.monotonic() + timeout_seconds
            poll_seconds = 1.0
            while not done_event.is_set():
                if should_stop is not None and should_stop():
                    log("[FLOW] Cancelling — sending STOP to the engine...")
                    client.stop()
                    cancelled = True
                    done_event.wait(timeout=15)  # give it a moment to wind down gracefully
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    error = "Timed out waiting for the Flow engine to finish generating."
                    return {s.scene_number: self._fail(s, error) for s in scenes}
                done_event.wait(timeout=min(poll_seconds, remaining))

            if not done_event.is_set() and not cancelled:
                error = "Timed out waiting for the Flow engine to finish generating."
                return {s.scene_number: self._fail(s, error) for s in scenes}

            if terminal_error and not progress:
                # Batch never actually started (e.g. "No signed-in accounts").
                return {s.scene_number: self._fail(s, terminal_error[0]) for s in scenes}

            results: Dict[str, AssetResult] = {}
            for idx, scene in enumerate(scenes):
                if idx not in progress and cancelled:
                    results[scene.scene_number] = AssetResult(
                        scene.scene_number, None, None, self.source,
                        SceneStatus.CANCELLED, error="Cancelled.",
                    )
                    continue
                results[scene.scene_number] = self._resolve_one_result(
                    idx, scene, images_dir, downloads_root, progress.get(idx), log
                )
            return results
        finally:
            unsubscribe()

    def _await_downloads_root(self, client, timeout: float = 5.0) -> Optional[str]:
        try:
            msg = client.wait_for(lambda m: m.get("type") == "INFO", timeout=timeout)
            return msg.get("downloadsRoot")
        except FlowClientError:
            return None

    def _resolve_one_result(
        self, idx: int, scene: SceneRow, images_dir: Path, downloads_root: str, progress_msg: Optional[dict], log: LogFn
    ) -> AssetResult:
        found = self._find_generated_file(downloads_root, idx)
        if found is None:
            error = (
                progress_msg.get("message")
                if progress_msg and progress_msg.get("status") == "failed"
                else "No output file found after generation (check the Flow engine log)."
            )
            return self._fail(scene, error)

        # Hard content check — don't trust the filename's extension alone. If the
        # engine ever downloads the wrong media kind (e.g. a routing bug sends an
        # image job for a video scene), this must fail loudly, not silently accept
        # a picture as this scene's video.
        actual_kind = sniff_media_kind(found)
        if actual_kind is not None and actual_kind != self.media_kind:
            return self._fail(
                scene,
                f"Flow returned a {actual_kind} for a {self.media_kind} scene "
                f"(expected {self.media_kind.upper()}, got {actual_kind.upper()}) — not using it.",
            )

        target = self._place_in_images_dir(found, images_dir, scene.scene_number)
        log(f"[FLOW] Scene {scene.scene_number} -> saved {target.name}")
        return AssetResult(
            scene_number=scene.scene_number,
            path=target,
            media_type=_MEDIA_TYPE_BY_KIND[self.media_kind],
            source=self.source,
            status=SceneStatus.READY,
            metadata={"prompt": scene.prompt, "provider": "flow", "media_kind": self.media_kind},
        )

    def _find_generated_file(self, downloads_root: str, global_index: int) -> Optional[Path]:
        """batch-runner.js names files `{pad(abs+1)}.<ext>` (ext depends on
        mediaKind — see batch-runner.js) inside a per-account subfolder of
        downloadsRoot; the padded number is globally unique across the whole
        batch regardless of which account produced it (splitPrompts assigns
        contiguous, non-overlapping absolute indices), so we don't need to
        replicate the account-slicing algorithm to find the right file."""
        ext = _EXT_BY_KIND[self.media_kind]
        name = f"{global_index + 1:03d}.{ext}"
        root = Path(downloads_root)
        if not root.is_dir():
            return None
        matches = sorted(root.glob(f"*/{name}"), key=lambda p: p.stat().st_mtime, reverse=True)
        return matches[0] if matches else None

    @staticmethod
    def _place_in_images_dir(src: Path, images_dir: Path, scene_number: str) -> Path:
        n = int(str(scene_number).strip())
        target = Path(images_dir) / f"{n:03d}{src.suffix.lower()}"
        shutil.copy2(src, target)
        return target

    def _fail(self, scene: SceneRow, error: str) -> AssetResult:
        return AssetResult(
            scene_number=scene.scene_number,
            path=None,
            media_type=None,
            source=self.source,
            status=SceneStatus.FAILED,
            error=error,
        )
