"""In-app provision of Qwen runtime + model (app installer payload ignored)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests

from installer.download import DownloadCancelled, DownloadError, download_file
from installer.extract import ExtractError, extract_archive
from installer.manifest import (
    FileSpec,
    ManifestError,
    PlatformSpec,
    load_manifest,
    platform_spec,
    resolve_model_downloads,
)
from installer.paths import download_cache_dir, model_root, provisioned_python, runtime_root, videogen_home
from installer.pipeline import aggregate_progress, estimate_totals
from installer.platform import UnsupportedPlatformError, detect_platform
from tts.base import CLONE_MODEL_ID
from tts.client import qwen_runtime_loadable, qwen_tts_importable
from tts.model_cache import model_download_progress_hint, model_files_match_manifest, model_is_installed

StatusFn = Callable[[str], None]
ProgressFn = Callable[[float], None]  # 0.0 .. 1.0
ShouldStopFn = Callable[[], bool]

READY_MARKER_NAME = "qwen-install-complete"


class ProvisionError(Exception):
    """Fatal Qwen provision failure."""


class ProvisionCancelled(ProvisionError):
    """User cancelled mid-provision."""


def qwen_ready_marker_path() -> Path:
    return videogen_home() / READY_MARKER_NAME


def mark_qwen_install_complete(platform_id: str) -> None:
    """Persist ready state only after a verified 100% install."""
    path = qwen_ready_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"platform={platform_id}\ncomplete=1\n",
        encoding="utf-8",
    )


def clear_qwen_install_complete() -> None:
    try:
        qwen_ready_marker_path().unlink(missing_ok=True)
    except OSError:
        pass


def is_qwen_locally_ready(platform_id: Optional[str] = None) -> bool:
    """
    True only when runtime + qwen_tts + model pass the same gate as Create Voice.
    Re-checked on every call (launch / Download UI).
    """
    try:
        pid = platform_id or detect_platform()
    except UnsupportedPlatformError:
        clear_qwen_install_complete()
        return False
    from tts.client import qwen_runtime_status

    ok, _ = qwen_runtime_status()
    if ok:
        try:
            mark_qwen_install_complete(pid)
        except OSError:
            pass
    else:
        clear_qwen_install_complete()
    return ok


def qwen_install_status_message(platform_id: Optional[str] = None) -> tuple[bool, str]:
    """(ready, short UI status). Uses the same checks as Create Voice."""
    try:
        pid = platform_id or detect_platform()
    except UnsupportedPlatformError as exc:
        return False, str(exc)

    from tts.client import qwen_runtime_status

    ok, _detail = qwen_runtime_status()
    if ok:
        return True, "Qwen voice engine ready."

    py = provisioned_python(pid)
    if py is None:
        return False, "Qwen not installed — click Download Qwen below."

    if not qwen_tts_importable(py):
        return False, "Qwen runtime broken or incomplete — click Download Qwen below."

    hint = model_download_progress_hint(model_root())
    if hint:
        return False, hint
    if not model_is_installed(CLONE_MODEL_ID):
        return False, "Qwen model not fully downloaded — click Download Qwen below."
    return False, "Qwen install incomplete — click Download Qwen below."


@dataclass
class ProvisionPlan:
    platform_id: str
    spec: PlatformSpec
    downloads: list[tuple[str, FileSpec]] = field(default_factory=list)  # phase, file
    sizes: list[int] = field(default_factory=list)


def runtime_and_model_ready(spec: PlatformSpec) -> bool:
    """True when runtime + model entries are downloadable (app URLs ignored)."""
    if not spec.runtime:
        return False
    if any(not f.url or not f.sha256 for f in spec.runtime):
        return False
    if not spec.model.files:
        return False
    if any(not (f.path or f.filename) or not f.sha256 for f in spec.model.files):
        return False
    return True


def require_runtime_and_model(spec: PlatformSpec) -> None:
    if not runtime_and_model_ready(spec):
        raise ManifestError(
            "Qwen download is not available yet.\n\n"
            "The install manifest is missing runtime or model download entries."
        )


def build_qwen_plan(
    manifest_path: Optional[Path] = None,
    platform_id: Optional[str] = None,
) -> ProvisionPlan:
    pid = platform_id or detect_platform()
    data = load_manifest(manifest_path)
    spec = platform_spec(data, pid)
    require_runtime_and_model(spec)

    downloads: list[tuple[str, FileSpec]] = []
    for f in spec.runtime:
        downloads.append(("runtime", f))
    for f in resolve_model_downloads(spec):
        downloads.append(("model", f))

    sizes = [int(f.size or 0) for _, f in downloads]
    return ProvisionPlan(platform_id=pid, spec=spec, downloads=downloads, sizes=sizes)


def provision_qwen(
    *,
    manifest_path: Optional[Path] = None,
    platform_id: Optional[str] = None,
    status: Optional[StatusFn] = None,
    progress: Optional[ProgressFn] = None,
    should_stop: Optional[ShouldStopFn] = None,
    force: bool = False,
) -> ProvisionPlan:
    """
    Download/verify/extract Qwen runtime and model files.

    Idempotent: if already installed and force is False, reports ready and returns.
    """
    plan = build_qwen_plan(manifest_path=manifest_path, platform_id=platform_id)

    def _status(msg: str) -> None:
        if status:
            status(msg)

    def _progress(value: float) -> None:
        if progress:
            progress(max(0.0, min(1.0, value)))

    def _stop() -> bool:
        return bool(should_stop and should_stop())

    if not force and is_qwen_locally_ready(plan.platform_id):
        _status("Qwen already installed.")
        _progress(1.0)
        return plan

    session = requests.Session()
    # Reuse installer size estimation (mutates plan.sizes via duck-typing).
    estimate_totals(plan, session=session)  # type: ignore[arg-type]

    cache = download_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)

    runtime_archives: list[Path] = []
    py = provisioned_python(plan.platform_id)
    need_runtime = force or py is None or not qwen_tts_importable(py)
    if py is not None and not need_runtime and not qwen_runtime_loadable(py):
        need_runtime = True
    need_model = force or not model_is_installed(CLONE_MODEL_ID)

    for index, (phase, fspec) in enumerate(plan.downloads):
        if _stop():
            raise ProvisionCancelled("Qwen download cancelled.")

        if phase == "runtime" and not need_runtime:
            _progress(aggregate_progress(index, plan.sizes[index], plan.sizes[index], plan.sizes))
            continue
        if phase == "model" and not need_model:
            _progress(aggregate_progress(index, plan.sizes[index], plan.sizes[index], plan.sizes))
            continue

        label = (
            "Downloading Qwen runtime"
            if phase == "runtime"
            else "Downloading Qwen model"
        )
        _status(f"{label}: {fspec.filename or fspec.path}")

        if phase == "runtime":
            dest_name = fspec.filename or Path(fspec.path).name
            dest = cache / f"{plan.platform_id}-runtime-{dest_name}"
        else:
            rel = fspec.path or fspec.filename
            dest = model_root() / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

        def on_file_progress(done: int, total: Optional[int], idx=index) -> None:
            _progress(aggregate_progress(idx, done, total, plan.sizes))

        try:
            path = download_file(
                fspec.url,
                dest,
                expected_sha256=fspec.sha256,
                expected_size=fspec.size or plan.sizes[index],
                progress=on_file_progress,
                should_stop=_stop,
                session=session,
            )
        except DownloadCancelled as exc:
            raise ProvisionCancelled(str(exc) or "Qwen download cancelled.") from exc
        except DownloadError as exc:
            raise ProvisionError(str(exc)) from exc

        if phase == "runtime":
            runtime_archives.append(path)

        _progress(aggregate_progress(index, plan.sizes[index], plan.sizes[index], plan.sizes))

    if _stop():
        raise ProvisionCancelled("Qwen download cancelled.")

    if need_runtime and runtime_archives:
        _status("Installing Qwen runtime…")
        rt_dest = runtime_root(plan.platform_id)
        try:
            for archive in runtime_archives:
                extract_archive(archive, rt_dest, clear_dest=True)
        except ExtractError as exc:
            raise ProvisionError(str(exc)) from exc
        from installer.runtime_fixup import repair_extracted_runtime

        repair_extracted_runtime(rt_dest)
        try:
            (rt_dest / ".videogen-runtime-ok").write_text("ok\n", encoding="utf-8")
        except OSError:
            pass
        py = provisioned_python(plan.platform_id)
        if py is None:
            raise ProvisionError(
                "Qwen runtime was downloaded but a working Python was not found after "
                "extraction.\n\n"
                "The Release runtime may be an old non-portable build (broken symlink). "
                "Rebuild via the Build Qwen Runtime workflow and re-upload the flat "
                "qwen-runtime-*.zip to the GitHub Release, then click Download again."
            )
        if not qwen_tts_importable(py):
            clear_qwen_install_complete()
            raise ProvisionError(
                "Qwen runtime was installed but the qwen_tts package could not be loaded.\n\n"
                "Try again with real-time antivirus scanning disabled for "
                f"{videogen_home()}, or delete the runtime folder and click Download again."
            )
        if not qwen_runtime_loadable(py):
            clear_qwen_install_complete()
            try:
                (rt_dest / ".videogen-runtime-ok").unlink(missing_ok=True)
            except OSError:
                pass
            raise ProvisionError(
                "Qwen runtime was installed but PyTorch/qwen_tts failed to load — "
                "the install is corrupted on disk.\n\n"
                "Add a Windows Security exclusion for "
                f"{videogen_home()}, delete the runtime folder, and click Reinstall."
            )

    if need_model and not model_files_match_manifest(model_root()):
        clear_qwen_install_complete()
        raise ProvisionError(
            f"Qwen model files are incomplete under {model_root()}.\n\n"
            "Click Download again to finish installing the ~3.8GB Base weights."
        )

    if not is_qwen_locally_ready(plan.platform_id):
        clear_qwen_install_complete()
        raise ProvisionError(
            "Qwen download finished but the voice engine is still not ready.\n\n"
            "Delete the runtime folder under ~/.videogen/runtime/qwen/ and click Download again."
        )

    mark_qwen_install_complete(plan.platform_id)
    _status("Qwen download complete.")
    _progress(1.0)
    return plan


def friendly_provision_error(exc: BaseException) -> str:
    if isinstance(exc, UnsupportedPlatformError):
        return str(exc)
    if isinstance(exc, ManifestError):
        return str(exc)
    if isinstance(exc, ProvisionCancelled):
        return "Qwen download cancelled."
    if isinstance(exc, (ProvisionError, DownloadError, ExtractError)):
        return str(exc)
    return f"Qwen download failed: {exc}"
