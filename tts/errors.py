"""Human-readable TTS errors. Never leak raw process exit codes as the message."""

from __future__ import annotations

import sys


class TTSError(Exception):
    def __init__(self, message: str, code: str = "tts_error"):
        super().__init__(message)
        self.code = code
        self.message = message


PACKAGE_MISSING_DEV = (
    "Qwen3-TTS is not installed in the local TTS environment. "
    "Create an isolated env and install the official package:\n\n"
    "  conda create -p .venv-qwen python=3.12 -y\n"
    "  .venv-qwen/bin/python -m pip install -r requirements-qwen-tts.txt"
)

PACKAGE_MISSING_FROZEN = (
    "The Qwen3-TTS runtime is not installed.\n\n"
    "Re-run the Video Generator installer to download and install "
    "the required voice engine and model (~6GB)."
)

MODEL_MISSING_DEV = (
    "Qwen 1.7B Base model is not installed.\n\n"
    "Install the voice-cloning model to:\n"
    "  ~/.videogen/qwen3-tts/Qwen3-TTS-12Hz-1.7B-Base\n\n"
    "  huggingface-cli download Qwen/Qwen3-TTS-12Hz-1.7B-Base "
    "--local-dir ~/.videogen/qwen3-tts/Qwen3-TTS-12Hz-1.7B-Base"
)

MODEL_MISSING_FROZEN = (
    "The Qwen 1.7B Base voice-cloning model is not installed.\n\n"
    "Re-run the Video Generator installer to download the required model (~4.5GB)."
)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_missing_message() -> str:
    return PACKAGE_MISSING_FROZEN if _is_frozen() else PACKAGE_MISSING_DEV


def model_missing_message() -> str:
    return MODEL_MISSING_FROZEN if _is_frozen() else MODEL_MISSING_DEV


# Back-compat aliases (resolve at import for non-frozen / tests).
PACKAGE_MISSING = PACKAGE_MISSING_DEV
MODEL_MISSING = MODEL_MISSING_DEV

CLONE_MODEL_MISSING = MODEL_MISSING

REFERENCE_TEXT_REQUIRED = (
    "Reference transcript is required for high-quality voice cloning.\n\n"
    "Enter the exact words spoken in the reference recording."
)

VOICE_PROFILE_MISSING = (
    "Saved voice profile could not be loaded.\n\n"
    "Rebuild the voice or choose another saved voice from your library."
)

VOICE_PROFILE_NEEDS_REBUILD = (
    "This voice profile needs to be rebuilt.\n\n"
    "The saved clone prompt is missing or incompatible with the current Qwen model."
)

CLONE_MODEL_LOAD_FAILED = (
    "The Qwen 1.7B Base voice-cloning model could not be loaded.\n\n"
    "Check that the model is installed at "
    "~/.videogen/qwen3-tts/Qwen3-TTS-12Hz-1.7B-Base and that enough memory is available."
)

OOM_1_7B = (
    "Qwen3-TTS ran out of available memory while loading the model. "
    "Close other heavy apps and retry, or use a machine with more RAM."
)

MPS_UNAVAILABLE = (
    "Apple Metal (MPS) is not available to this PyTorch build. "
    "Generation will use CPU and may be much slower."
)


def map_exception(exc: BaseException) -> TTSError:
    if isinstance(exc, TTSError):
        return exc
    text = str(exc) or type(exc).__name__
    lowered = text.lower()
    name = type(exc).__name__

    if isinstance(exc, ImportError) or "qwen_tts" in lowered or "no module named 'qwen" in lowered:
        return TTSError(package_missing_message(), "package_missing")
    if "local_files_only" in lowered or "not found" in lowered and "qwen3-tts" in lowered:
        return TTSError(model_missing_message(), "model_missing")
    if "is not installed" in lowered and "model" in lowered:
        return TTSError(model_missing_message(), "model_missing")
    if name in ("OutOfMemoryError",) or "out of memory" in lowered or "mps backend out of memory" in lowered:
        return TTSError(OOM_1_7B, "TTS_OUT_OF_MEMORY")
    if "does not support generate_voice_clone" in lowered or "does not support create_voice_clone_prompt" in lowered:
        return TTSError(CLONE_MODEL_LOAD_FAILED, "VOICE_CLONE_GENERATION_FAILED")
    if "mps" in lowered and ("not available" in lowered or "unavailable" in lowered or "not built" in lowered):
        return TTSError(
            "Qwen3-TTS could not use Apple Metal (MPS) on this machine. "
            "CPU fallback was not possible: " + text,
            "unsupported_device",
        )
    if isinstance(exc, TimeoutError) or "timed out" in lowered:
        return TTSError(
            "Qwen3-TTS timed out while generating narration. "
            "The model may still be loading, or the script may be too long for this device.",
            "TTS_TIMEOUT",
        )
    if "invalid" in lowered and "text" in lowered:
        return TTSError(text, "invalid_text")
    return TTSError(f"Qwen3-TTS failed: {text}", "generation_failure")
