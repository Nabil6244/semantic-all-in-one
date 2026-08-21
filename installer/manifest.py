"""Load and validate the install manifest bundled with the stub installer."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


RELEASE_NOT_PUBLISHED = (
    "This release is not published yet.\n\n"
    "The install manifest still has empty download URLs. "
    "Wait for a published Video Generator release, then run the installer again."
)


class ManifestError(Exception):
    """Invalid or unpublished install manifest."""


@dataclass
class FileSpec:
    url: str
    sha256: str
    filename: str
    size: int = 0
    path: str = ""  # relative path inside HF repo / extract tree


@dataclass
class ModelSpec:
    source: str
    repo_id: str
    revision: str
    files: list[FileSpec] = field(default_factory=list)


@dataclass
class PlatformSpec:
    platform_id: str
    app: list[FileSpec]
    runtime: list[FileSpec]
    model: ModelSpec


def _repo_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def default_manifest_path() -> Path:
    bundled = _repo_root() / "tts" / "install_manifest.json"
    if bundled.is_file():
        return bundled
    return Path(__file__).resolve().parent.parent / "tts" / "install_manifest.json"


def _parse_file(raw: dict[str, Any]) -> FileSpec:
    return FileSpec(
        url=str(raw.get("url") or "").strip(),
        sha256=str(raw.get("sha256") or "").strip().lower(),
        filename=str(raw.get("filename") or raw.get("path") or "").strip(),
        size=int(raw.get("size") or 0),
        path=str(raw.get("path") or "").strip(),
    )


def _parse_model(raw: dict[str, Any]) -> ModelSpec:
    files_raw = raw.get("files") or []
    files = [_parse_file(f) if isinstance(f, dict) else FileSpec("", "", str(f)) for f in files_raw]
    return ModelSpec(
        source=str(raw.get("source") or "huggingface").strip(),
        repo_id=str(raw.get("repo_id") or "").strip(),
        revision=str(raw.get("revision") or "main").strip(),
        files=files,
    )


def load_manifest(path: Optional[Path] = None) -> dict[str, Any]:
    manifest_path = Path(path) if path else default_manifest_path()
    if not manifest_path.is_file():
        raise ManifestError(f"Install manifest not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Install manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("Install manifest root must be an object.")
    return data


def platform_spec(data: dict[str, Any], platform_id: str) -> PlatformSpec:
    platforms = data.get("platforms") or {}
    raw = platforms.get(platform_id)
    if not isinstance(raw, dict):
        raise ManifestError(f"No install payload defined for platform '{platform_id}'.")
    app = [_parse_file(f) for f in (raw.get("app") or [])]
    runtime = [_parse_file(f) for f in (raw.get("runtime") or [])]
    model_raw = raw.get("model") or {}
    if not isinstance(model_raw, dict):
        raise ManifestError("Model section must be an object.")
    return PlatformSpec(
        platform_id=platform_id,
        app=app,
        runtime=runtime,
        model=_parse_model(model_raw),
    )


def is_published(spec: PlatformSpec) -> bool:
    """True when app/runtime URLs and model file list are filled in."""
    if not spec.app or not spec.runtime:
        return False
    if any(not f.url or not f.sha256 for f in spec.app):
        return False
    if any(not f.url or not f.sha256 for f in spec.runtime):
        return False
    if not spec.model.files:
        return False
    if any(not (f.path or f.filename) or not f.sha256 for f in spec.model.files):
        return False
    return True


def require_published(spec: PlatformSpec) -> None:
    if not is_published(spec):
        raise ManifestError(RELEASE_NOT_PUBLISHED)


def huggingface_file_url(repo_id: str, revision: str, rel_path: str) -> str:
    rel = rel_path.lstrip("/")
    return f"https://huggingface.co/{repo_id}/resolve/{revision}/{rel}"


def resolve_model_downloads(spec: PlatformSpec) -> list[FileSpec]:
    """Fill HF resolve URLs when url is empty but path/sha256 are set."""
    out: list[FileSpec] = []
    for f in spec.model.files:
        rel = f.path or f.filename
        url = f.url or huggingface_file_url(spec.model.repo_id, spec.model.revision, rel)
        out.append(
            FileSpec(
                url=url,
                sha256=f.sha256,
                filename=f.filename or Path(rel).name,
                size=f.size,
                path=rel,
            )
        )
    return out
