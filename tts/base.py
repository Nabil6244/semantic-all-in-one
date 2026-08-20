"""Small TTS provider contract. Voice cloning uses Qwen3-TTS-12Hz-1.7B-Base only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

CLONE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
# Backward-compatible alias — preset CustomVoice is no longer used for narration.
DEFAULT_MODEL_ID = CLONE_MODEL_ID
PROFILE_FORMAT_VERSION = 1

VOICE_MODE_CLONE = "clone"
VOICE_MODE_PRESET = "clone"  # legacy callers map to clone-only
VOICE_MODE_LABEL_CLONE = "Qwen 3 TTS — 1.7B Voice Clone"
VOICE_MODE_LABEL_PRESET = VOICE_MODE_LABEL_CLONE

PREVIEW_TEXT = "This is a preview of my saved voice profile."
DEFAULT_LANGUAGE = "English"

# Kept for import compatibility in tests/settings migration.
DEFAULT_VOICE = "clone"
DEFAULT_DOCUMENTARY_STYLE = ""
SUPPORTED_VOICES = ()


@dataclass
class TTSResult:
    path: Path
    duration_seconds: float
    sample_rate: int
    format: str
    provider: str
    voice: str
    generation_time_seconds: float
    load_time_seconds: float = 0.0
    device: str = ""
    model: str = ""
    local: bool = True
    extra: dict = field(default_factory=dict)


class TTSProvider(Protocol):
    def generate_clone(
        self,
        text: str,
        output_path: Path,
        *,
        ref_audio: Optional[Path | str] = None,
        ref_text: Optional[str] = None,
        voice_prompt_path: Optional[Path | str] = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> TTSResult: ...

    def build_voice_prompt(
        self,
        ref_audio: Path | str,
        ref_text: str,
        prompt_path: Path,
    ) -> None: ...

    def shutdown(self) -> None: ...
