"""Persistent local voice profiles for Qwen 1.7B Base voice cloning."""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from tts.base import CLONE_MODEL_ID, PROFILE_FORMAT_VERSION
from tts.errors import TTSError
from tts.reference import convert_reference_to_wav, validate_reference

VOICES_ROOT = Path.home() / ".videogen" / "voices"
PROFILE_NAME = "profile.json"
REFERENCE_NAME = "reference.wav"
PROMPT_NAME = "voice_prompt.pt"


def voices_root() -> Path:
    return VOICES_ROOT


def _slug(name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "").strip()).strip("-").lower()
    return base or "voice"


def _unique_id(name: str, existing: set[str]) -> str:
    slug = _slug(name)
    if slug not in existing:
        return slug
    n = 2
    while f"{slug}-{n}" in existing:
        n += 1
    return f"{slug}-{n}"


@dataclass
class VoiceProfile:
    id: str
    name: str
    model: str = CLONE_MODEL_ID
    profile_format_version: int = PROFILE_FORMAT_VERSION
    reference_audio: str = REFERENCE_NAME
    reference_text: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: str = "ready"  # ready | needs_rebuild | building
    is_default: bool = False
    prompt_file: str = PROMPT_NAME

    @property
    def dir(self) -> Path:
        return voices_root() / self.id

    @property
    def profile_path(self) -> Path:
        return self.dir / PROFILE_NAME

    @property
    def reference_path(self) -> Path:
        return self.dir / self.reference_audio

    @property
    def prompt_path(self) -> Path:
        return self.dir / self.prompt_file

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceProfile":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def _read_profile(path: Path) -> Optional[VoiceProfile]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return VoiceProfile.from_dict(data)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def list_voices() -> List[VoiceProfile]:
    root = voices_root()
    if not root.is_dir():
        return []
    profiles: list[VoiceProfile] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        profile = _read_profile(child / PROFILE_NAME)
        if profile is not None:
            profiles.append(refresh_profile_status(profile))
    profiles.sort(key=lambda p: (not p.is_default, p.name.lower()))
    return profiles


def get_voice(voice_id: str) -> Optional[VoiceProfile]:
    profile = _read_profile(voices_root() / voice_id / PROFILE_NAME)
    if profile is None:
        return None
    return refresh_profile_status(profile)


def get_default_voice() -> Optional[VoiceProfile]:
    voices = list_voices()
    for profile in voices:
        if profile.is_default:
            return profile
    return voices[0] if voices else None


def refresh_profile_status(profile: VoiceProfile) -> VoiceProfile:
    if profile.model != CLONE_MODEL_ID:
        profile.status = "needs_rebuild"
        return profile
    if profile.profile_format_version != PROFILE_FORMAT_VERSION:
        profile.status = "needs_rebuild"
        return profile
    if not profile.reference_path.is_file():
        profile.status = "needs_rebuild"
        return profile
    if not (profile.reference_text or "").strip():
        profile.status = "needs_rebuild"
        return profile
    if not profile.prompt_path.is_file():
        profile.status = "needs_rebuild"
        return profile
    if profile.status == "building":
        return profile
    profile.status = "ready"
    return profile


def _save_profile(profile: VoiceProfile) -> None:
    profile.updated_at = time.time()
    profile.dir.mkdir(parents=True, exist_ok=True)
    profile.profile_path.write_text(
        json.dumps(profile.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _clear_default_flag() -> None:
    for profile in list_voices():
        if profile.is_default:
            profile.is_default = False
            _save_profile(profile)


def set_default_voice(voice_id: str) -> VoiceProfile:
    profile = get_voice(voice_id)
    if profile is None:
        raise TTSError(f"Voice profile '{voice_id}' was not found.", "VOICE_PROFILE_MISSING")
    _clear_default_flag()
    profile.is_default = True
    _save_profile(profile)
    return profile


def create_voice_profile(
    name: str,
    ref_audio: Path | str,
    reference_text: str,
    *,
    make_default: bool = False,
) -> VoiceProfile:
    name = (name or "").strip()
    if not name:
        raise TTSError("Enter a name for this voice.", "invalid_voice_name")
    transcript = (reference_text or "").strip()
    if not transcript:
        raise TTSError(
            "Reference transcript is required.\n\n"
            "Enter the exact words spoken in the reference recording.",
            "REFERENCE_TEXT_REQUIRED",
        )
    info = validate_reference(ref_audio)
    existing_ids = {p.id for p in list_voices()}
    voice_id = _unique_id(name, existing_ids)
    profile = VoiceProfile(
        id=voice_id,
        name=name,
        reference_text=transcript,
        status="building",
        is_default=make_default or not existing_ids,
    )
    profile.dir.mkdir(parents=True, exist_ok=True)
    convert_reference_to_wav(info.path, profile.reference_path)
    if make_default or not existing_ids:
        _clear_default_flag()
        profile.is_default = True
    _save_profile(profile)
    return profile


def mark_voice_ready(voice_id: str) -> VoiceProfile:
    profile = get_voice(voice_id)
    if profile is None:
        raise TTSError(f"Voice profile '{voice_id}' was not found.", "VOICE_PROFILE_MISSING")
    profile.status = "ready"
    _save_profile(profile)
    return refresh_profile_status(profile)


def mark_voice_needs_rebuild(voice_id: str) -> VoiceProfile:
    profile = get_voice(voice_id)
    if profile is None:
        raise TTSError(f"Voice profile '{voice_id}' was not found.", "VOICE_PROFILE_MISSING")
    profile.status = "needs_rebuild"
    _save_profile(profile)
    return profile


def replace_voice_reference(
    voice_id: str,
    ref_audio: Path | str,
    reference_text: str,
) -> VoiceProfile:
    profile = get_voice(voice_id)
    if profile is None:
        raise TTSError(f"Voice profile '{voice_id}' was not found.", "VOICE_PROFILE_MISSING")
    transcript = (reference_text or "").strip()
    if not transcript:
        raise TTSError(
            "Reference transcript is required when replacing a voice.",
            "REFERENCE_TEXT_REQUIRED",
        )
    info = validate_reference(ref_audio)
    convert_reference_to_wav(info.path, profile.reference_path)
    profile.reference_text = transcript
    profile.status = "building"
    if profile.prompt_path.is_file():
        try:
            profile.prompt_path.unlink()
        except OSError:
            pass
    _save_profile(profile)
    return profile


def delete_voice(voice_id: str) -> None:
    profile = get_voice(voice_id)
    if profile is None:
        raise TTSError(f"Voice profile '{voice_id}' was not found.", "VOICE_PROFILE_MISSING")
    shutil.rmtree(profile.dir, ignore_errors=True)
    remaining = list_voices()
    if remaining and not any(p.is_default for p in remaining):
        remaining[0].is_default = True
        _save_profile(remaining[0])


def migrate_legacy_reference(path: str, name: str = "Imported Voice") -> Optional[VoiceProfile]:
    raw = (path or "").strip()
    if not raw or not Path(raw).is_file():
        return None
    if list_voices():
        return None
    try:
        profile = create_voice_profile(name, raw, "Reference transcript not recorded. Rebuild this voice with the exact spoken text.")
        profile.status = "needs_rebuild"
        _save_profile(profile)
        return profile
    except TTSError:
        return None
