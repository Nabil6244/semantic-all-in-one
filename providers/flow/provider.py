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
import sys
import threading
import time
import uuid
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

GENERATE_TIMEOUT_SECONDS = 20 * 60  # floor; large batches scale up (see _generate_timeout_seconds)
_SECONDS_PER_IMAGE = 25.0
_SECONDS_PER_VIDEO = 90.0
_ABORT_RETRY_MAX_ELAPSED = 90.0
_ABORT_RETRY_MIN_SCENES = 4
_BATCH_SETTLE_SECONDS = 0.35
_IDLE_POLL_SECONDS = 0.45
_SOFT_STOP_AFTER_SECONDS = 2.0
_FORCE_RESET_AFTER_SECONDS = 6.0
_IDLE_WAIT_TIMEOUT = 180.0
# One GENERATE at a time — Retry used to fire several Flow jobs and fail extras
# with "A Flow batch is already running".
_ENGINE_GENERATE_LOCK = threading.Lock()

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
        self.should_stop_scene = None

    def _scene_stopped(self, scene_number: str) -> bool:
        cb = getattr(self, "should_stop_scene", None)
        return bool(cb and cb(scene_number))

    def _batch_should_stop(self, should_stop: Optional[Callable[[], bool]], scenes: List[SceneRow]) -> bool:
        if should_stop is not None and should_stop():
            return True
        if not scenes:
            return False
        # Stop the engine as soon as any scene in this batch is cancelled so
        # per-scene Stop works during multi-prompt Flow runs.
        return any(self._scene_stopped(s.scene_number) for s in scenes)

    def resolve(self, scene: SceneRow, images_dir: Path, log: LogFn = print) -> AssetResult:
        return self.resolve_batch(
            [scene],
            images_dir,
            log=log,
            should_stop=lambda: self._scene_stopped(scene.scene_number),
        )[scene.scene_number]

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
        on_scene_ready: Optional[Callable[[SceneRow, AssetResult], None]] = None,
    ) -> Dict[str, AssetResult]:
        if not scenes:
            return {}
        try:
            client = self.engine_manager.ensure_running()
        except FlowEngineError as exc:
            return {s.scene_number: self._fail(s, str(exc)) for s in scenes}

        timeout_seconds = self._generate_timeout_seconds(len(scenes))
        lock_wait = max(_IDLE_WAIT_TIMEOUT + 30.0, timeout_seconds + 30.0)
        if not _ENGINE_GENERATE_LOCK.acquire(timeout=lock_wait):
            error = "Timed out waiting for another Flow job in this app — try Retry again."
            return {s.scene_number: self._fail(s, error) for s in scenes}
        try:
            return self._resolve_batch_locked(
                client,
                scenes,
                images_dir,
                log,
                should_stop,
                abort_retried=False,
                on_scene_ready=on_scene_ready,
            )
        finally:
            _ENGINE_GENERATE_LOCK.release()

    def _generate_timeout_seconds(self, n: int) -> float:
        """Keep a 20-minute floor in production; scale with batch size so 160 images
        are not cut off mid-download. Tests set GENERATE_TIMEOUT_SECONDS < 60."""
        n = max(1, int(n))
        video_mult = 3 if self.media_kind == "video" else 1
        base = GENERATE_TIMEOUT_SECONDS * video_mult
        if GENERATE_TIMEOUT_SECONDS < 60:
            return base
        per = _SECONDS_PER_VIDEO if self.media_kind == "video" else _SECONDS_PER_IMAGE
        return min(6 * 3600.0, max(base, n * per))

    def _wait_for_engine_idle(
        self,
        client,
        log: LogFn,
        should_stop: Optional[Callable[[], bool]],
    ) -> Optional[str]:
        """Return an error message, or None if the engine is idle and ready to GENERATE.

        A leftover Node sidecar (app relaunch without killing Flow) often stays
        `running: true` forever because STOP only sets stopAll. Soft-stop first,
        then FORCE_RESET so Retry can proceed instead of failing every scene.
        """
        t0 = time.monotonic()
        soft_stopped = False
        force_reset = False
        while True:
            try:
                busy = bool(client.get_state().get("running"))
            except Exception:
                busy = False
            if not busy:
                return None
            if should_stop is not None and should_stop():
                return "Cancelled."
            waited = time.monotonic() - t0
            if waited >= _SOFT_STOP_AFTER_SECONDS and not soft_stopped:
                log("[FLOW] Previous Flow batch still marked running — sending STOP...")
                try:
                    client.stop()
                except Exception:
                    pass
                soft_stopped = True
            if waited >= _FORCE_RESET_AFTER_SECONDS and not force_reset:
                log("[FLOW] Engine still busy after STOP — force-clearing stuck running flag...")
                try:
                    if hasattr(client, "force_stop"):
                        client.force_stop()
                    if hasattr(client, "reset_generate"):
                        client.reset_generate()
                except Exception:
                    pass
                force_reset = True
            if waited >= _IDLE_WAIT_TIMEOUT:
                # Last resort: one more reset, then proceed anyway — Node now queues
                # GENERATE, so a stale flag should not wipe the whole Retry batch.
                log("[FLOW] Engine idle wait timed out — resetting and continuing...")
                try:
                    if hasattr(client, "reset_generate"):
                        client.reset_generate()
                except Exception:
                    pass
                return None
            log("[FLOW] Waiting for the previous Flow batch to finish...")
            time.sleep(_IDLE_POLL_SECONDS)

    def _resolve_batch_locked(
        self,
        client,
        scenes: List[SceneRow],
        images_dir: Path,
        log: LogFn,
        should_stop: Optional[Callable[[], bool]],
        abort_retried: bool = False,
        on_scene_ready: Optional[Callable[[SceneRow, AssetResult], None]] = None,
    ) -> Dict[str, AssetResult]:
        idle_error = self._wait_for_engine_idle(client, log, should_stop)
        if idle_error:
            return {s.scene_number: self._fail(s, idle_error) for s in scenes}

        run_dir = self._new_run_dir(images_dir)
        batch_started_at = time.time()
        t_gen = time.monotonic()
        engine_root = client.get_info().get("downloadsRoot") or self._await_downloads_root(client)

        prompts = [s.prompt for s in scenes]
        kind_label = self.media_kind.upper()
        log(f"[FLOW] Sending {len(prompts)} {kind_label} prompt(s) to the Flow engine...")
        log(f"[FLOW] Run folder: {run_dir}")

        progress: Dict[int, dict] = {}
        early_placed: Dict[int, AssetResult] = {}
        done_event = threading.Event()
        terminal_error: List[str] = []

        def _try_place_early(idx: int, scene: SceneRow, progress_msg: dict) -> None:
            """Copy into assets/ as soon as Node finishes a scene — otherwise the
            folder stays empty until the whole 100+ prompt batch ends."""
            if idx in early_placed:
                return
            if not (
                progress_msg.get("status") == "done"
                or progress_msg.get("path")
                or progress_msg.get("file")
            ):
                return
            try:
                placed = self._resolve_one_result(
                    idx,
                    scene,
                    images_dir,
                    str(run_dir),
                    progress_msg,
                    log,
                    engine_root=engine_root,
                    batch_started_at=batch_started_at,
                )
                if placed.status == SceneStatus.READY:
                    early_placed[idx] = placed
                    if on_scene_ready is not None:
                        try:
                            on_scene_ready(scene, placed)
                        except Exception as exc:
                            log(f"[FLOW] Scene {scene.scene_number} ready callback failed: {exc}")
            except Exception as exc:
                log(f"[FLOW] Scene {scene.scene_number} early copy failed: {exc}")

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
                    body = (msg.get("message") or "")
                    if "ownload" in body:
                        log(f"[FLOW] {worker} -> Scene {scene.scene_number} downloading...")
                    else:
                        log(f"[FLOW] {worker} -> Scene {scene.scene_number} generating {self.media_kind}...")
                elif status in ("done", "failed"):
                    progress[idx] = msg
                    if status == "failed":
                        log(f"[FLOW] {worker} -> Scene {scene.scene_number} failed: {msg.get('message')}")
                    else:
                        log(f"[FLOW] {worker} -> Scene {scene.scene_number} generated")
                        _try_place_early(idx, scene, msg)
            elif mtype == "PROMPT_RESULT":
                idx = msg.get("index")
                if idx is not None and 0 <= idx < len(scenes):
                    prev = progress.get(idx) or {}
                    prev.update(msg)
                    # Normalize engine "error" into the message field the resolver reads.
                    if prev.get("status") == "failed" and not prev.get("message") and prev.get("error"):
                        prev["message"] = prev["error"]
                    progress[idx] = prev
                    _try_place_early(idx, scenes[idx], prev)
            elif mtype == "GENERATE_DONE":
                # Ignore a leftover batch's DONE (previous STOP/reset) so we
                # don't treat this run as finished before any prompt starts.
                reported = msg.get("outputDir") or msg.get("output_dir")
                if reported:
                    try:
                        if Path(str(reported)).resolve() != Path(run_dir).resolve():
                            return
                    except OSError:
                        pass
                done_event.set()
            elif mtype == "STATE" and msg.get("generateError") and not msg.get("running"):
                # orchestrator.js's generate() returns EARLY (no GENERATE_DONE broadcast
                # at all) for "no signed-in accounts" / "no prompts" — this STATE push is
                # the only terminal signal in that case, so we must race on it too or hang
                # for the full timeout. Confirmed against the real engine (see report).
                err = str(msg["generateError"])
                terminal_error.append(err)
                low = err.lower()
                if "no signed-in" in low or "paste at least" in low:
                    done_event.set()

        # Subscribe BEFORE sending GENERATE so a fast engine response can't arrive
        # before we're listening for it.
        unsubscribe = client.subscribe(on_message)
        cancelled = False
        try:
            settings = {
                "imageCount": 1,
                "mediaKind": self.media_kind,
                **self.flow_settings,
                # Absolute path — relative paths break once the Node sidecar's
                # cwd differs (common in the Windows packaged .exe layout).
                "outputDir": str(run_dir.resolve()),
            }
            client.generate(prompts, settings=settings, account_ids=self.account_ids)

            timeout_seconds = self._generate_timeout_seconds(len(scenes))
            deadline = time.monotonic() + timeout_seconds
            poll_seconds = 1.0
            timed_out = False
            while not done_event.is_set():
                if self._batch_should_stop(should_stop, scenes):
                    log("[FLOW] Cancelling — sending STOP to the engine...")
                    client.stop()
                    cancelled = True
                    done_event.wait(timeout=15)  # give it a moment to wind down gracefully
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    log(
                        "[FLOW] Timed out waiting for the Flow engine — "
                        "stopping it and keeping any scenes that already finished."
                    )
                    try:
                        client.stop()
                    except Exception:
                        pass
                    try:
                        if hasattr(client, "reset_generate"):
                            client.reset_generate()
                    except Exception:
                        pass
                    done_event.wait(timeout=5)
                    break
                done_event.wait(timeout=min(poll_seconds, remaining))

            # Late flush: Node may still be writing the last file after DONE.
            if not cancelled:
                time.sleep(_BATCH_SETTLE_SECONDS)

            elapsed = time.monotonic() - t_gen
            if (
                not cancelled
                and not timed_out
                and not abort_retried
                and self._abort_is_retryable(terminal_error)
                and self._looks_like_ghost_abort(scenes, progress, run_dir, elapsed)
            ):
                log(
                    "[FLOW] Engine finished instantly with no files "
                    "(leftover stop) — retrying this batch once..."
                )
                try:
                    client.stop()
                except Exception:
                    pass
                try:
                    if hasattr(client, "reset_generate"):
                        client.reset_generate()
                except Exception:
                    pass
                unsubscribe()
                unsubscribe = lambda: None
                return self._resolve_batch_locked(
                    client,
                    scenes,
                    images_dir,
                    log,
                    should_stop,
                    abort_retried=True,
                    on_scene_ready=on_scene_ready,
                )

            timeout_error = (
                "Timed out waiting for the Flow engine to finish generating. "
                "Finished scenes were kept — use Retry on the rest."
            )
            if timed_out or (not done_event.is_set() and not cancelled):
                fallback = timeout_error
            elif terminal_error and not progress and self._count_run_media(run_dir) == 0:
                return {s.scene_number: self._fail(s, terminal_error[0]) for s in scenes}
            else:
                fallback = None

            return self._collect_batch_results(
                scenes,
                images_dir,
                str(run_dir),
                progress,
                log,
                engine_root=engine_root,
                batch_started_at=batch_started_at,
                cancelled=cancelled,
                should_stop=should_stop,
                fallback_error=fallback,
                early_placed=early_placed,
            )
        finally:
            unsubscribe()

    def _await_downloads_root(self, client, timeout: float = 5.0) -> Optional[str]:
        try:
            msg = client.wait_for(lambda m: m.get("type") == "INFO", timeout=timeout)
            return msg.get("downloadsRoot")
        except FlowClientError:
            return None

    def _new_run_dir(self, images_dir: Path) -> Path:
        """Per-project, per-batch folder so leftover Flow_Images/001.png cannot leak in."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run_id = f"{self.media_kind}_{stamp}_{uuid.uuid4().hex[:8]}"
        images = Path(images_dir).resolve()
        # Normal layout: <project>/assets → <project>/flow/runs/<id>
        run_dir = images.parent / "flow" / "runs" / run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir
        except OSError:
            # Tests / odd paths (e.g. /tmp) — keep the run folder next to the assets.
            run_dir = images / ".flow_runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            return run_dir

    def _count_run_media(self, run_dir: Path) -> int:
        ext = _EXT_BY_KIND[self.media_kind]
        n = 0
        try:
            root = Path(run_dir)
            if not root.is_dir():
                return 0
            for p in root.rglob(f"*.{ext}"):
                if self._usable_media_file(p):
                    n += 1
        except OSError:
            pass
        return n

    @staticmethod
    def _abort_is_retryable(terminal_error: List[str]) -> bool:
        if not terminal_error:
            return True
        msg = (terminal_error[0] or "").lower()
        if "no signed-in" in msg or "paste at least" in msg:
            return False
        return "before any prompt" in msg

    def _looks_like_ghost_abort(
        self,
        scenes: List[SceneRow],
        progress: Dict[int, dict],
        run_dir: Path,
        elapsed: float,
    ) -> bool:
        if len(scenes) < _ABORT_RETRY_MIN_SCENES:
            return False
        if elapsed > _ABORT_RETRY_MAX_ELAPSED:
            return False
        for msg in progress.values():
            if msg.get("status") in ("done", "failed") or msg.get("path") or msg.get("file"):
                return False
        return self._count_run_media(run_dir) == 0

    def _collect_batch_results(
        self,
        scenes: List[SceneRow],
        images_dir: Path,
        run_dir: str,
        progress: Dict[int, dict],
        log: LogFn,
        *,
        engine_root: Optional[str],
        batch_started_at: Optional[float],
        cancelled: bool,
        should_stop: Optional[Callable[[], bool]],
        fallback_error: Optional[str],
        early_placed: Optional[Dict[int, AssetResult]] = None,
    ) -> Dict[str, AssetResult]:
        """Always try disk pickup first — files may exist even if BATCH_PROGRESS
        never arrived (or the wait loop timed out)."""
        results: Dict[str, AssetResult] = {}
        early = early_placed or {}
        for idx, scene in enumerate(scenes):
            if self._scene_stopped(scene.scene_number):
                results[scene.scene_number] = AssetResult(
                    scene.scene_number, None, None, self.source,
                    SceneStatus.CANCELLED, error="Cancelled.",
                )
                continue
            prior = early.get(idx)
            if prior is not None and prior.status == SceneStatus.READY and prior.path:
                results[scene.scene_number] = prior
                continue
            msg = progress.get(idx)
            resolved = self._resolve_one_result(
                idx,
                scene,
                images_dir,
                run_dir,
                msg,
                log,
                engine_root=engine_root,
                batch_started_at=batch_started_at,
            )
            if resolved.status == SceneStatus.READY:
                results[scene.scene_number] = resolved
                continue
            if msg and msg.get("status") == "failed":
                results[scene.scene_number] = self._fail(
                    scene,
                    msg.get("message") or msg.get("error") or "Flow generation failed.",
                )
                continue
            if idx not in progress and cancelled:
                # `cancelled` alone doesn't say WHY the batch stopped — that
                # could be this whole batch's own should_stop() (e.g. a
                # "Cancel All" run-level abort: every unstarted scene here
                # is genuinely cancelled, not just interrupted) or only a
                # sibling scene's should_stop_scene (this scene wasn't
                # itself told to stop, it just got caught in the STOP sent
                # for that sibling). Re-checking should_stop() here — cheap,
                # idempotent — disambiguates the two instead of always
                # reporting the sibling-interruption case.
                if should_stop is not None and should_stop():
                    results[scene.scene_number] = AssetResult(
                        scene.scene_number, None, None, self.source,
                        SceneStatus.CANCELLED, error="Cancelled.",
                    )
                else:
                    results[scene.scene_number] = AssetResult(
                        scene.scene_number, None, None, self.source,
                        SceneStatus.FAILED,
                        error="Interrupted when another scene in this batch was stopped. Use Retry.",
                    )
                continue
            if fallback_error:
                results[scene.scene_number] = self._fail(scene, fallback_error)
            else:
                results[scene.scene_number] = resolved
        return results

    def _resolve_one_result(
        self,
        idx: int,
        scene: SceneRow,
        images_dir: Path,
        downloads_root: str,
        progress_msg: Optional[dict],
        log: LogFn,
        *,
        engine_root: Optional[str] = None,
        batch_started_at: Optional[float] = None,
    ) -> AssetResult:
        found = self._find_generated_file(
            downloads_root,
            idx,
            progress_msg=progress_msg,
            engine_root=engine_root,
            batch_started_at=batch_started_at,
        )
        if found is None:
            if progress_msg and progress_msg.get("status") == "failed":
                error = (
                    progress_msg.get("message")
                    or progress_msg.get("error")
                    or "Flow generation failed."
                )
            else:
                error = (
                    "Flow generated this scene but the file was not downloaded "
                    "(not using leftover clips). Retry this scene."
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

    @staticmethod
    def _usable_media_file(path: Path) -> bool:
        try:
            return path.is_file() and path.stat().st_size > 64
        except OSError:
            return False

    @classmethod
    def _wait_usable_media_file(cls, path: Path, *, attempts: int = 1) -> bool:
        """Windows Defender / AV often locks a just-written file for a moment —
        Node already saved it, but Python's first is_file()/size check fails."""
        if attempts < 1:
            attempts = 1
        for i in range(attempts):
            if cls._usable_media_file(path):
                return True
            if i + 1 < attempts:
                time.sleep(0.35)
        return False

    @staticmethod
    def _file_is_from_this_batch(path: Path, batch_started_at: Optional[float]) -> bool:
        if batch_started_at is None:
            return True
        # Windows FAT/exFAT and some AV rewrite mtimes; keep a wide skew so a
        # real download from this run is not treated as a leftover.
        skew = 120.0 if sys.platform == "win32" else 5.0
        try:
            return path.stat().st_mtime >= (batch_started_at - skew)
        except OSError:
            return False

    @classmethod
    def _newest_named_under(
        cls,
        root: Path,
        name: str,
        batch_started_at: Optional[float],
        *,
        require_batch_mtime: bool = True,
    ) -> Optional[Path]:
        if not root.is_dir():
            return None
        matches = []
        for p in root.glob(f"*/{name}"):
            if not cls._usable_media_file(p):
                continue
            if require_batch_mtime and not cls._file_is_from_this_batch(p, batch_started_at):
                continue
            matches.append(p)
        if not matches:
            return None
        return max(matches, key=lambda p: p.stat().st_mtime)

    def _find_generated_file(
        self,
        downloads_root: str,
        global_index: int,
        *,
        progress_msg: Optional[dict] = None,
        engine_root: Optional[str] = None,
        batch_started_at: Optional[float] = None,
    ) -> Optional[Path]:
        """Prefer the exact path this batch just saved. Never accept a leftover
        `001.png` from a previous project's shared Flow_Images dump."""
        ext = _EXT_BY_KIND[self.media_kind]
        name = f"{global_index + 1:03d}.{ext}"
        # Per-batch run folders are unique — mtime gating is only needed when
        # falling back to the shared ~/Downloads/Flow_Images dump.
        win_retries = 6 if sys.platform == "win32" else 1

        raw = ""
        if progress_msg:
            raw = str(progress_msg.get("path") or progress_msg.get("file") or "").strip()
        if raw:
            # Node on Windows may emit mixed separators; Path handles both, but
            # normalize anyway so exists() checks are consistent.
            reported = Path(raw)
            if self._wait_usable_media_file(reported, attempts=win_retries):
                return reported
            try:
                alt = Path(downloads_root) / reported.name
                if self._wait_usable_media_file(alt, attempts=win_retries):
                    return alt
                # Account subfolder: <run>/<account-label>/001.png
                nested = self._newest_named_under(
                    Path(downloads_root), reported.name, batch_started_at,
                    require_batch_mtime=False,
                )
                if nested is not None:
                    return nested
            except OSError:
                pass

        run_hit = self._newest_named_under(
            Path(downloads_root), name, batch_started_at, require_batch_mtime=False,
        )
        if run_hit is not None:
            return run_hit

        # Wider search under this run folder only (safe — folder is unique).
        try:
            root = Path(downloads_root)
            if root.is_dir():
                for p in root.rglob(name):
                    if self._usable_media_file(p):
                        return p
        except OSError:
            pass

        # Older engines ignore outputDir and still write to ~/Downloads/Flow_Images.
        # That folder is shared across projects — keep a batch mtime gate there.
        if engine_root:
            engine_path = Path(engine_root)
            try:
                same_run = engine_path.resolve() == Path(downloads_root).resolve()
            except OSError:
                same_run = False
            if not same_run:
                return self._newest_named_under(
                    engine_path, name, batch_started_at, require_batch_mtime=True,
                )
        return None

    @staticmethod
    def _place_in_images_dir(src: Path, images_dir: Path, scene_number: str) -> Path:
        n = int(str(scene_number).strip())
        target = Path(images_dir) / f"{n:03d}{src.suffix.lower()}"
        try:
            if src.resolve() == target.resolve():
                return target
        except OSError:
            pass
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
