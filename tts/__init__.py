"""Local narration (Qwen3-TTS). Isolated from asset providers and the renderer."""

from tts.base import (
    CLONE_MODEL_ID,
    DEFAULT_DOCUMENTARY_STYLE,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL_ID,
    DEFAULT_VOICE,
    SUPPORTED_VOICES,
    TTSResult,
    VOICE_MODE_CLONE,
    VOICE_MODE_PRESET,
)
from tts.errors import TTSError
from tts.narration import collect_narration, narration_from_csv

__all__ = [
    "CLONE_MODEL_ID",
    "DEFAULT_DOCUMENTARY_STYLE",
    "DEFAULT_LANGUAGE",
    "DEFAULT_MODEL_ID",
    "DEFAULT_VOICE",
    "SUPPORTED_VOICES",
    "TTSError",
    "TTSResult",
    "VOICE_MODE_CLONE",
    "VOICE_MODE_PRESET",
    "collect_narration",
    "narration_from_csv",
]
