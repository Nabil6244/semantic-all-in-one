"""Deterministic cache for VO analysis + VO-aware plans."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from smart_editing import _audio_fingerprint

from .schema import VO_PLANNER_VERSION, AssetMixPreferences

CACHE_NAME = "vo_aware_plan.json"
VO_ANALYSIS_NAME = "vo_analysis.json"


def script_hash(script: str) -> str:
    raw = (script or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def settings_hash(mix: Optional[AssetMixPreferences], whisper_model: str = "") -> str:
    payload = {
        "v": VO_PLANNER_VERSION,
        "mix": (mix or AssetMixPreferences()).fingerprint(),
        "whisper": (whisper_model or "").strip().lower(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def plan_cache_key(
    script: str,
    audio_path: Path | str,
    *,
    mix: Optional[AssetMixPreferences] = None,
    whisper_model: str = "",
) -> str:
    parts = [
        script_hash(script),
        _audio_fingerprint(audio_path),
        settings_hash(mix, whisper_model),
        str(VO_PLANNER_VERSION),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def cache_path(state_dir: Path) -> Path:
    return Path(state_dir) / CACHE_NAME


def vo_analysis_path(state_dir: Path) -> Path:
    return Path(state_dir) / VO_ANALYSIS_NAME


def load_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_cached_plan(state_dir: Path, key: str) -> Optional[dict]:
    data = load_json(cache_path(state_dir))
    if not data or data.get("cache_key") != key:
        return None
    if int(data.get("planner_version") or 0) != VO_PLANNER_VERSION:
        return None
    return data.get("plan") if isinstance(data.get("plan"), dict) else None


def save_cached_plan(state_dir: Path, key: str, plan: dict) -> None:
    save_json(
        cache_path(state_dir),
        {
            "cache_key": key,
            "planner_version": VO_PLANNER_VERSION,
            "plan": plan,
        },
    )


def load_cached_vo_analysis(
    state_dir: Path,
    audio_path: Path | str,
    whisper_model: str = "",
) -> Optional[dict]:
    data = load_json(vo_analysis_path(state_dir))
    if not data:
        return None
    if data.get("audio_key") != _audio_fingerprint(audio_path):
        return None
    if (data.get("whisper_model") or "") != (whisper_model or ""):
        return None
    if int(data.get("planner_version") or 0) != VO_PLANNER_VERSION:
        return None
    analysis = data.get("analysis")
    return analysis if isinstance(analysis, dict) else None


def save_cached_vo_analysis(
    state_dir: Path,
    audio_path: Path | str,
    whisper_model: str,
    analysis: dict,
) -> None:
    save_json(
        vo_analysis_path(state_dir),
        {
            "audio_key": _audio_fingerprint(audio_path),
            "whisper_model": whisper_model or "",
            "planner_version": VO_PLANNER_VERSION,
            "analysis": analysis,
        },
    )


def store_whisper_words_in_smart_cache(
    state_dir: Path,
    audio_path: Path | str,
    words: list,
) -> None:
    """Reuse smart_editing whisper cache so render path can skip re-transcribe."""
    from smart_editing import _audio_fingerprint as af
    from smart_editing import load_cache, save_cache

    state_dir = Path(state_dir)
    existing = load_cache(state_dir)
    audio_key = af(audio_path)
    plan = dict(existing.get("plan") or {}) if isinstance(existing.get("plan"), dict) else {}
    plan["whisper_words"] = [[w, float(s), float(e)] for w, s, e in words]
    save_cache(
        state_dir,
        {
            **existing,
            "audio_key": audio_key,
            "plan": plan,
        },
    )
