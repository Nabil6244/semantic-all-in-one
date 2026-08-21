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
    return path.is_dir() and (path / "config.json").is_file()


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
    for path in candidate_model_dirs(repo_id):
        if _dir_looks_like_model(path):
            return path
    raise TTSError(model_missing_message(), code)


def model_is_installed(repo_id: str = CLONE_MODEL_ID) -> bool:
    try:
        find_local_model(repo_id)
        return True
    except TTSError:
        return False
