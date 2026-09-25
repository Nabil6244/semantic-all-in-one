"""Project-scoped Cache & Storage operations for the Settings UI.

Pure thin wrapper over EXISTING cache/cleanup helpers — no second asset or
cache system:

    downloaded_assets.scan_downloaded_assets / delete_downloaded_assets
        -> "generated asset cache" (Flow/stock/YouTube mirrors + tmp
           scratch files; already project-scoped, already protects
           local/manual user assets)
    preview_engine.clear_proxy_cache
        -> "preview/proxy cache" (already project-scoped; never touches
           source media, CSVs, narration, or final renders)

Every project already lives in its own directory tree keyed by a stable
``project_id`` (see project_workspace.ProjectWorkspace), so per-project
isolation already exists on disk — this module only adds size accounting
and a "clear temp only" / "clear everywhere" layer on top of what's
already there. Deliberately excludes the shared, app-wide SFX library
(``~/.videogen/sfx``) and brand kits: those are user-managed resources the
user explicitly installs, not per-project cache, so "Clear All Cache"
never touches them.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import List, Optional, Tuple

import downloaded_assets
from preview_engine import PROXY_DIRNAME, clear_proxy_cache
from project_workspace import ProjectWorkspace, default_projects_root, list_projects, path_is_inside

format_bytes = downloaded_assets.format_bytes


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def proxy_cache_bytes(ws: ProjectWorkspace) -> int:
    return _dir_size(ws.state_dir / PROXY_DIRNAME)


def temp_cache_bytes(ws: ProjectWorkspace) -> int:
    return _dir_size(ws.tmp_dir)


def generated_asset_cache_bytes(ws: ProjectWorkspace) -> int:
    return downloaded_assets.scan_downloaded_assets(ws).total_bytes


def project_cache_bytes(ws: ProjectWorkspace) -> int:
    """Total clearable cache for one project: generated/downloaded assets
    (Flow/stock/YouTube mirrors + tmp scratch, via downloaded_assets) plus
    the preview/proxy render cache. Never includes source media, CSVs,
    narration, scripts, project metadata, or final renders — those are
    never scanned by either underlying helper."""
    return generated_asset_cache_bytes(ws) + proxy_cache_bytes(ws)


def clear_temp_cache(ws: ProjectWorkspace) -> int:
    """Delete only files under ws.tmp_dir — safe, incomplete/in-progress
    processing scratch files. Never touches assets/flow/youtube/stock/
    final/csv/audio/script/state. Returns bytes freed."""
    ws.ensure_dirs()
    tmp_root = ws.tmp_dir
    try:
        tmp_root_resolved = tmp_root.resolve()
    except OSError:
        return 0
    if not tmp_root.is_dir():
        return 0
    freed = 0
    for p in sorted(tmp_root.rglob("*"), reverse=True):
        try:
            resolved = p.resolve()
        except OSError:
            continue
        if not path_is_inside(resolved, tmp_root_resolved):
            continue
        if p.is_file():
            try:
                freed += p.stat().st_size
                p.unlink()
            except OSError:
                pass
        elif p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    return freed


def clear_preview_cache(ws: ProjectWorkspace) -> int:
    """Delete previews/proxies only — never source media, project files,
    narration, CSVs, or final renders (clear_proxy_cache only ever removes
    state_dir/preview_proxy, which holds nothing else)."""
    freed = proxy_cache_bytes(ws)
    clear_proxy_cache(ws.state_dir)
    return freed


def clear_generated_asset_cache(ws: ProjectWorkspace) -> downloaded_assets.DeleteDownloadedResult:
    """Remove cached generated/downloaded assets (and tmp scratch files)
    for the active project — future generation re-resolves them. Reuses
    the existing, already-tested downloaded_assets cleanup, which already
    protects local/manual user-supplied assets by name."""
    report = downloaded_assets.scan_downloaded_assets(ws)
    return downloaded_assets.delete_downloaded_assets(ws, confirm=True, report=report)


@dataclasses.dataclass
class ClearAllCacheResult:
    projects_scanned: int = 0
    bytes_freed: int = 0
    failures: List[Tuple[str, str]] = dataclasses.field(default_factory=list)


def clear_all_cache(projects_root: Optional[Path] = None) -> ClearAllCacheResult:
    """Clears temp + preview/proxy + generated-asset cache for EVERY
    project under ``projects_root`` — never touches source media, CSVs,
    narration, final renders, or project metadata (each per-project step
    reuses the same protections as the single-project clear functions
    above). Does not touch the shared, deliberately-global SFX library or
    brand kits — those are user-installed resources, not per-project
    cache."""
    root = Path(projects_root) if projects_root else default_projects_root()
    result = ClearAllCacheResult()
    for ws in list_projects(root):
        result.projects_scanned += 1
        try:
            result.bytes_freed += clear_temp_cache(ws)
            result.bytes_freed += clear_preview_cache(ws)
            result.bytes_freed += clear_generated_asset_cache(ws).bytes_freed
        except Exception as exc:  # best-effort across many projects
            result.failures.append((ws.project_id, str(exc)))
    return result
