"""Discover a locally cached Qwen3-TTS model. Never download implicitly."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from tts.base import CLONE_MODEL_ID
from tts.errors import TTSError, model_missing_message

MODEL_DIR_NAME = "Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_MODEL_ID = CLONE_MODEL_ID


def _repo_dir_name(repo_id: str) -> str:
    return (repo_id or DEFAULT_MODEL_ID).rsplit("/", 1)[-1]


def _hf_hub_root() -> Path:
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _snapshot_from_hub(repo_id: str) -> Optional[Path]:
    folder = "models--" + repo_id.replace("/", "--")
    cache = _hf_hub_root() / folder
    refs_main = cache / "refs" / "main"
    if refs_main.is_file():
        rev = refs_main.read_text(encoding="utf-8").strip()
        snap = cache / "snapshots" / rev
        if (snap / "config.json").is_file():
            return snap
    snaps = cache / "snapshots"
    if snaps.is_dir():
        candidates = sorted(
            (p for p in snaps.iterdir() if (p / "config.json").is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]
    return None


def _dir_looks_like_model(path: Path) -> bool:
    """True only if Base clone weights look complete (not a tokenizer-only stub)."""
    if not path.is_dir():
        return False
    config = path / "config.json"
    weights = path / "model.safetensors"
    if not config.is_file() or not weights.is_file():
        return False
    # Real Base weights are ~3.8GB; speech tokenizer is ~650MB.
    try:
        if weights.stat().st_size < 2_000_000_000:
            return False
        head = config.read_text(encoding="utf-8")[:800]
    except OSError:
        return False
    if "qwen3_tts_tokenizer" in head:
        return False
    return model_files_match_manifest(path)


def model_files_match_manifest(model_dir: Path | None = None) -> bool:
    """
    Every manifest model file must exist with the expected byte size.
    Used so Download stays visible until the install is truly 100% complete.
    """
    root = Path(model_dir) if model_dir is not None else (Path.home() / ".videogen" / "qwen3-tts" / MODEL_DIR_NAME)
    if not root.is_dir():
        return False
    try:
        from installer.manifest import load_manifest, platform_spec, resolve_model_downloads
        from installer.platform import UnsupportedPlatformError, detect_platform

        pid = detect_platform()
        files = resolve_model_downloads(platform_spec(load_manifest(), pid))
    except Exception:
        # Fallback heuristics when manifest/platform unavailable
        return _dir_looks_like_model_basic(root)

    for fspec in files:
        rel = (fspec.path or fspec.filename or "").strip()
        if not rel:
            return False
        path = root / rel
        if not path.is_file():
            return False
        expected = int(fspec.size or 0)
        if expected > 0:
            try:
                if path.stat().st_size != expected:
                    return False
            except OSError:
                return False
    # Incomplete resume leftovers mean not ready
    if any(root.rglob("*.part")):
        return False
    return True


def _dir_looks_like_model_basic(path: Path) -> bool:
    config = path / "config.json"
    weights = path / "model.safetensors"
    if not config.is_file() or not weights.is_file():
        return False
    try:
        if weights.stat().st_size < 2_000_000_000:
            return False
        if "qwen3_tts_tokenizer" in config.read_text(encoding="utf-8")[:800]:
            return False
    except OSError:
        return False
    return True


def model_download_progress_hint(model_dir: Path | None = None) -> str | None:
    """Short UI hint when a partial .part download exists."""
    root = Path(model_dir) if model_dir is not None else (Path.home() / ".videogen" / "qwen3-tts" / MODEL_DIR_NAME)
    part = root / "model.safetensors.part"
    if not part.is_file():
        return None
    try:
        done = part.stat().st_size
    except OSError:
        return None
    expected = 3857413744
    try:
        from installer.manifest import load_manifest, platform_spec, resolve_model_downloads
        from installer.platform import detect_platform

        for fspec in resolve_model_downloads(platform_spec(load_manifest(), detect_platform())):
            if (fspec.path or "") == "model.safetensors" and fspec.size:
                expected = int(fspec.size)
                break
    except Exception:
        pass
    pct = max(0, min(99, int(100 * done / max(1, expected))))
    return f"Qwen model download incomplete ({pct}%). Click Download to resume."


def candidate_model_dirs(repo_id: str = CLONE_MODEL_ID) -> list[Path]:
    name = _repo_dir_name(repo_id)
    env = os.environ.get("QWEN_TTS_MODEL_DIR", "").strip()
    clone_env = os.environ.get("QWEN_TTS_CLONE_MODEL_DIR", "").strip()
    home = Path.home() / ".videogen" / "qwen3-tts" / name
    project = Path(__file__).resolve().parent.parent / "models" / name
    ordered: list[Path] = []
    if clone_env:
        ordered.append(Path(clone_env).expanduser())
    if env:
        ordered.append(Path(env).expanduser())
    ordered.extend([home, project])
    snap = _snapshot_from_hub(repo_id)
    if snap:
        ordered.append(snap)
    seen: set[str] = set()
    unique: list[Path] = []
    for p in ordered:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def find_local_model(repo_id: str = CLONE_MODEL_ID) -> Path:
    code = "VOICE_CLONE_MODEL_UNAVAILABLE"
    # Prefer the app install dir when it is 100% complete per manifest sizes.
    home = Path.home() / ".videogen" / "qwen3-tts" / _repo_dir_name(repo_id)
    if model_files_match_manifest(home):
        return home
    for path in candidate_model_dirs(repo_id):
        if path == home:
            continue
        if _dir_looks_like_model(path):
            return path
    raise TTSError(model_missing_message(), code)


def model_is_installed(repo_id: str = CLONE_MODEL_ID) -> bool:
    try:
        find_local_model(repo_id)
        return True
    except TTSError:
        return False
