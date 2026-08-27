"""Project-scoped cleanup for pipeline-downloaded / generated media only.

Does not change acquisition or rendering. Never targets user voiceovers, SFX,
voice profiles, finals, scripts, CSVs, or project metadata.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from project_workspace import ProjectWorkspace, path_is_inside

# Manifest / AssetSource values written by the asset pipeline.
PIPELINE_SOURCES = frozenset(
    {
        "stock",
        "stock_image",
        "stock_video",
        "flow_image",
        "flow_video",
        "youtube_video",
        "archive_video",
        "nasa_video",
        "commons_video",
        "commons_image",
    }
)
PROTECTED_SOURCES = frozenset({"local", "manual"})

_SCENE_FILE = re.compile(r"^(\d{3})\.[^.]+$", re.IGNORECASE)
_MANUAL_ARCHIVE = re.compile(r"_\d*manual|_replaced", re.IGNORECASE)
_STOCK_USED = ".stock_used_assets.json"
_MANIFEST_NAME = ".asset_manifest.json"
_QA_NAME = ".scene_qa.json"


@dataclass
class DownloadedAssetsReport:
    """Inventory of deletable pipeline downloads for one project."""

    files: List[Path] = field(default_factory=list)
    total_bytes: int = 0
    project_root: Optional[Path] = None

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def is_empty(self) -> bool:
        return self.file_count == 0

    def format_size(self) -> str:
        return format_bytes(self.total_bytes)

    def button_label(self) -> str:
        if self.is_empty:
            return "Cleanup"
        return f"Cleanup · {self.file_count} · {self.format_size()}"

    def confirmation_message(self) -> str:
        root = self.project_root.name if self.project_root else "this project"
        return (
            f"Delete {self.file_count} downloaded asset file(s) "
            f"({self.format_size()}) from “{root}”?\n\n"
            "This removes Stock / YouTube / AI mirrors and temporary render files "
            "created by the asset pipeline.\n\n"
            "Kept: narration audio, scripts, CSVs, final videos, manual clips, "
            "and project settings."
        )


@dataclass
class DeleteDownloadedResult:
    deleted: List[Path] = field(default_factory=list)
    failed: List[Tuple[Path, str]] = field(default_factory=list)
    bytes_freed: int = 0
    confirmed: bool = False

    @property
    def ok(self) -> bool:
        return self.confirmed and not self.failed

    @property
    def partial(self) -> bool:
        return self.confirmed and bool(self.deleted) and bool(self.failed)


def format_bytes(n: int) -> str:
    value = float(max(0, int(n)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(n)} B"


def is_protected_asset_name(name: str) -> bool:
    """Manual archives / replacements must never be deleted by cleanup."""
    base = Path(name).name
    if base.startswith("."):
        return base not in (_STOCK_USED,)
    if _MANUAL_ARCHIVE.search(base):
        return True
    return False


def is_pipeline_manifest_source(source: Optional[str], status: Optional[str] = None) -> bool:
    key = (source or "").strip().lower()
    if key in PROTECTED_SOURCES:
        return False
    if key in PIPELINE_SOURCES:
        return True
    # Skip placeholders are pipeline-generated black frames.
    if (status or "").strip().lower() == "skipped" and key not in PROTECTED_SOURCES:
        return True
    return False


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    try:
        for path in root.rglob("*"):
            if path.is_file():
                yield path
    except OSError:
        return


def _load_manifest(assets_dir: Path) -> Dict[str, dict]:
    path = assets_dir / _MANIFEST_NAME
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_manifest(assets_dir: Path, data: Dict[str, dict]) -> None:
    path = assets_dir / _MANIFEST_NAME
    try:
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def scan_downloaded_assets(workspace: ProjectWorkspace) -> DownloadedAssetsReport:
    """List pipeline downloads/mirrors/tmp files eligible for cleanup."""
    ws = workspace
    ws.ensure_dirs()
    seen: Dict[Path, Path] = {}
    total = 0

    def add(path: Path) -> None:
        nonlocal total
        try:
            resolved = path.resolve()
        except OSError:
            return
        if not path_is_inside(resolved, ws.root.resolve()):
            return
        if not path.is_file():
            return
        if resolved in seen:
            return
        seen[resolved] = path
        total += _file_size(path)

    # Provider mirrors + ephemeral render work — always pipeline-owned.
    for folder in (ws.flow_dir, ws.youtube_dir, ws.stock_dir, ws.tmp_dir):
        for path in _iter_files(folder):
            add(path)

    manifest = _load_manifest(ws.assets_dir)
    if ws.assets_dir.is_dir():
        try:
            children = list(ws.assets_dir.iterdir())
        except OSError:
            children = []
        for path in children:
            if not path.is_file():
                continue
            name = path.name
            if name == _STOCK_USED:
                add(path)
                continue
            if is_protected_asset_name(name):
                continue
            match = _SCENE_FILE.match(name)
            if not match:
                continue
            key = match.group(1)
            record = manifest.get(key) or {}
            if is_pipeline_manifest_source(record.get("source"), record.get("status")):
                add(path)

    files = sorted(seen.values(), key=lambda p: str(p))
    return DownloadedAssetsReport(
        files=files,
        total_bytes=total,
        project_root=ws.root,
    )


def _prune_manifest_after_delete(
    workspace: ProjectWorkspace,
    deleted: Sequence[Path],
) -> None:
    """Drop pipeline scene records whose media files were removed."""
    deleted_names = {p.name for p in deleted}
    deleted_resolved = set()
    for p in deleted:
        try:
            deleted_resolved.add(p.resolve())
        except OSError:
            pass

    data = _load_manifest(workspace.assets_dir)
    if not data:
        workspace.sync_state_copies()
        return

    changed = False
    for key, record in list(data.items()):
        if not isinstance(record, dict):
            continue
        if not is_pipeline_manifest_source(record.get("source"), record.get("status")):
            continue
        file_name = str(record.get("file") or record.get("path") or "")
        bare = Path(file_name).name if file_name else ""
        scene_gone = False
        if bare and bare in deleted_names:
            scene_gone = True
        else:
            # Any deleted assets/NNN.* for this scene key.
            for name in deleted_names:
                m = _SCENE_FILE.match(name)
                if m and m.group(1) == key:
                    scene_gone = True
                    break
        if scene_gone:
            data.pop(key, None)
            changed = True

    if changed:
        _save_manifest(workspace.assets_dir, data)
    workspace.sync_state_copies()


def delete_downloaded_assets(
    workspace: ProjectWorkspace,
    *,
    confirm: bool = False,
    report: Optional[DownloadedAssetsReport] = None,
) -> DeleteDownloadedResult:
    """Delete scanned pipeline assets. No-op unless confirm=True."""
    if not confirm:
        return DeleteDownloadedResult(confirmed=False)

    inventory = report or scan_downloaded_assets(workspace)
    deleted: List[Path] = []
    failed: List[Tuple[Path, str]] = []
    freed = 0
    root = workspace.root.resolve()

    for path in inventory.files:
        try:
            resolved = path.resolve()
        except OSError as exc:
            failed.append((path, str(exc)))
            continue
        if not path_is_inside(resolved, root):
            failed.append((path, "Outside project root — skipped"))
            continue
        if is_protected_asset_name(path.name) and path.parent.resolve() == workspace.assets_dir.resolve():
            # Defense in depth if a protected name ever enters the inventory.
            failed.append((path, "Protected user asset — skipped"))
            continue
        size = _file_size(path)
        try:
            path.unlink()
        except OSError as exc:
            failed.append((path, str(exc)))
            continue
        deleted.append(path)
        freed += size

    _prune_manifest_after_delete(workspace, deleted)

    # Best-effort: remove empty mirror/tmp subfolders (never remove the dirs themselves).
    for folder in (workspace.flow_dir, workspace.youtube_dir, workspace.stock_dir, workspace.tmp_dir):
        if not folder.is_dir():
            continue
        try:
            for child in sorted(folder.rglob("*"), reverse=True):
                if child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
        except OSError:
            pass

    return DeleteDownloadedResult(
        deleted=deleted,
        failed=failed,
        bytes_freed=freed,
        confirmed=True,
    )


def protected_project_paths(workspace: ProjectWorkspace) -> List[Path]:
    """Paths that cleanup must never remove (for tests / audits)."""
    out = [
        workspace.root / "project.json",
        workspace.script_dir,
        workspace.csv_dir,
        workspace.audio_dir,
        workspace.final_dir,
        workspace.logs_dir,
        workspace.state_dir,
        workspace.assets_dir / _MANIFEST_NAME,
        workspace.assets_dir / _QA_NAME,
    ]
    return out
