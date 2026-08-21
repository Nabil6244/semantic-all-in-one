"""Ordered install pipeline: app → runtime → model, with aggregate progress."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import requests

from installer.download import (
    DownloadCancelled,
    DownloadError,
    download_file,
    head_content_length,
)
from installer.extract import ExtractError, extract_archive
from installer.manifest import (
    FileSpec,
    ManifestError,
    PlatformSpec,
    load_manifest,
    platform_spec,
    require_published,
    resolve_model_downloads,
)
from installer.paths import (
    WIN_EXE_NAME,
    app_install_dir,
    download_cache_dir,
    model_root,
    runtime_root,
    windows_start_menu_dir,
)
from installer.platform import UnsupportedPlatformError, detect_platform

StatusFn = Callable[[str], None]
ProgressFn = Callable[[float], None]  # 0.0 .. 1.0
ShouldStopFn = Callable[[], bool]


@dataclass
class InstallPlan:
    platform_id: str
    spec: PlatformSpec
    downloads: list[tuple[str, FileSpec]] = field(default_factory=list)  # phase, file
    sizes: list[int] = field(default_factory=list)  # known or estimated bytes per file


class InstallError(Exception):
    """Fatal install failure."""


def build_plan(manifest_path: Optional[Path] = None, platform_id: Optional[str] = None) -> InstallPlan:
    pid = platform_id or detect_platform()
    data = load_manifest(manifest_path)
    spec = platform_spec(data, pid)
    require_published(spec)

    downloads: list[tuple[str, FileSpec]] = []
    for f in spec.app:
        downloads.append(("app", f))
    for f in spec.runtime:
        downloads.append(("runtime", f))
    for f in resolve_model_downloads(spec):
        downloads.append(("model", f))

    sizes = [_known_size(f) for _, f in downloads]
    return InstallPlan(platform_id=pid, spec=spec, downloads=downloads, sizes=sizes)


def estimate_totals(plan: InstallPlan, session: Optional[requests.Session] = None) -> list[int]:
    """Fill unknown sizes via HEAD when possible."""
    sess = session or requests.Session()
    sizes = list(plan.sizes)
    for i, (_, f) in enumerate(plan.downloads):
        if sizes[i] > 0:
            continue
        if f.size > 0:
            sizes[i] = f.size
            continue
        cl = head_content_length(f.url, session=sess)
        if cl:
            sizes[i] = cl
    # If still unknown, use a placeholder so the bar still moves (equal weight later)
    if all(s <= 0 for s in sizes):
        sizes = [1] * len(sizes)
    else:
        avg = max(s for s in sizes if s > 0)
        sizes = [s if s > 0 else avg for s in sizes]
    plan.sizes = sizes
    return sizes


def _known_size(f: FileSpec) -> int:
    return int(f.size or 0)


def aggregate_progress(
    file_index: int,
    file_done: int,
    file_total: Optional[int],
    sizes: list[int],
) -> float:
    """
    Compute 0..1 across all files.
    sizes[i] is the planned weight for file i.
    Within the current file, use file_done/file_total when known, else file_done/sizes[i].
    """
    if not sizes:
        return 0.0
    total_weight = float(sum(max(1, s) for s in sizes))
    completed = float(sum(max(1, s) for s in sizes[:file_index]))
    weight = float(max(1, sizes[file_index]))
    if file_total and file_total > 0:
        frac = min(1.0, max(0.0, file_done / float(file_total)))
    else:
        frac = min(1.0, max(0.0, file_done / weight)) if weight else 0.0
    return min(1.0, (completed + frac * weight) / total_weight)


def run_install(
    plan: InstallPlan,
    *,
    status: Optional[StatusFn] = None,
    progress: Optional[ProgressFn] = None,
    should_stop: Optional[ShouldStopFn] = None,
) -> None:
    def _status(msg: str) -> None:
        if status:
            status(msg)

    def _progress(value: float) -> None:
        if progress:
            progress(max(0.0, min(1.0, value)))

    def _stop() -> bool:
        return bool(should_stop and should_stop())

    session = requests.Session()
    estimate_totals(plan, session=session)
    cache = download_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)

    app_archives: list[Path] = []
    runtime_archives: list[Path] = []
    model_files: list[tuple[FileSpec, Path]] = []

    for index, (phase, fspec) in enumerate(plan.downloads):
        if _stop():
            raise DownloadCancelled("install cancelled")

        label = {
            "app": "Downloading application",
            "runtime": "Downloading Qwen runtime",
            "model": "Downloading Qwen model",
        }.get(phase, "Downloading")
        _status(f"{label}: {fspec.filename or fspec.path}")

        dest_name = fspec.filename or Path(fspec.path).name
        dest = cache / f"{plan.platform_id}-{phase}-{dest_name}"

        def on_file_progress(done: int, total: Optional[int], idx=index) -> None:
            _progress(aggregate_progress(idx, done, total, plan.sizes))

        path = download_file(
            fspec.url,
            dest,
            expected_sha256=fspec.sha256,
            expected_size=fspec.size or plan.sizes[index],
            progress=on_file_progress,
            should_stop=_stop,
            session=session,
        )
        if phase == "app":
            app_archives.append(path)
        elif phase == "runtime":
            runtime_archives.append(path)
        else:
            model_files.append((fspec, path))

        _progress(aggregate_progress(index, plan.sizes[index], plan.sizes[index], plan.sizes))

    if _stop():
        raise DownloadCancelled("install cancelled")

    _status("Installing application…")
    app_dest = app_install_dir(plan.platform_id)
    for archive in app_archives:
        extract_archive(archive, app_dest, clear_dest=True)

    if plan.platform_id == "win-amd64":
        _create_windows_shortcut(app_dest)

    _status("Installing Qwen runtime…")
    rt_dest = runtime_root(plan.platform_id)
    for archive in runtime_archives:
        extract_archive(archive, rt_dest, clear_dest=True)

    _status("Installing Qwen model…")
    m_dest = model_root()
    m_dest.mkdir(parents=True, exist_ok=True)
    for fspec, path in model_files:
        rel = fspec.path or fspec.filename
        target = m_dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Model files are individual blobs — copy/replace into tree
        import shutil

        shutil.copy2(path, target)

    _status("Installation complete.")
    _progress(1.0)


def _create_windows_shortcut(app_dest: Path) -> None:
    if sys.platform != "win32":
        return
    exe = app_dest / WIN_EXE_NAME
    if not exe.is_file():
        # nested onedir
        candidates = list(app_dest.rglob(WIN_EXE_NAME))
        exe = candidates[0] if candidates else exe
    if not exe.is_file():
        return
    try:
        start_menu = windows_start_menu_dir()
        start_menu.mkdir(parents=True, exist_ok=True)
        link = start_menu / "Semantic All-In-One.lnk"
        # Minimal .lnk via PowerShell (no extra deps)
        ps = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{link}'); "
            f"$s.TargetPath = '{exe}'; "
            f"$s.WorkingDirectory = '{exe.parent}'; "
            f"$s.Save()"
        )
        os.system(f'powershell -NoProfile -Command "{ps}"')
    except Exception:
        pass


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, UnsupportedPlatformError):
        return str(exc)
    if isinstance(exc, ManifestError):
        return str(exc)
    if isinstance(exc, DownloadCancelled):
        return "Installation cancelled."
    if isinstance(exc, (DownloadError, ExtractError, InstallError)):
        return str(exc)
    return f"Installation failed: {exc}"
