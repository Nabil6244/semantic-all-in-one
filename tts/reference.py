"""Validate local reference recordings for Qwen voice clone. Never uploads audio."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tts.errors import TTSError

ALLOWED_REFERENCE_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}
# Official Base clone is a ~3s speaker sample. Recommend a short clean take.
REF_MIN_SECONDS = 2.0
REF_MAX_SECONDS = 60.0
REF_RECOMMENDED = (5.0, 20.0)

TOO_SHORT = (
    "Reference audio is too short.\n"
    "Please provide a clear voice recording of at least a few seconds.\n"
    f"Recommended: {REF_RECOMMENDED[0]:.0f}–{REF_RECOMMENDED[1]:.0f} seconds."
)
TOO_LONG = (
    "Reference audio is too long.\n"
    "Please use a short clean voice sample.\n"
    f"Recommended: {REF_RECOMMENDED[0]:.0f}–{REF_RECOMMENDED[1]:.0f} seconds "
    f"(maximum {REF_MAX_SECONDS:.0f}s)."
)


@dataclass(frozen=True)
class ReferenceInfo:
    path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    suffix: str


def _ffprobe_duration(path: Path) -> tuple[float, int, int]:
    probe = shutil.which("ffprobe") or shutil.which("ffmpeg")
    if not probe:
        raise TTSError(
            "Could not read the reference audio. ffmpeg/ffprobe is required "
            "to inspect MP3/M4A/FLAC files.",
            "REFERENCE_AUDIO_INVALID",
        )
    cmd = [
        "ffprobe" if "ffprobe" in probe or probe.endswith("ffprobe") else probe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=sample_rate,channels",
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]
    # Prefer real ffprobe when ffmpeg was found instead.
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        cmd[0] = ffprobe
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TTSError(
            "Could not read the reference audio file.",
            "REFERENCE_AUDIO_INVALID",
        ) from exc
    duration = 0.0
    sr = 0
    ch = 1
    for line in (proc.stdout or "").splitlines():
        if line.startswith("duration="):
            try:
                duration = float(line.split("=", 1)[1])
            except ValueError:
                duration = 0.0
        elif line.startswith("sample_rate="):
            try:
                sr = int(float(line.split("=", 1)[1]))
            except ValueError:
                sr = 0
        elif line.startswith("channels="):
            try:
                ch = int(float(line.split("=", 1)[1]))
            except ValueError:
                ch = 1
    if duration <= 0:
        raise TTSError(
            "Reference audio is invalid or contains no playable audio.",
            "REFERENCE_AUDIO_INVALID",
        )
    return duration, sr or 24000, max(1, ch)


def _wav_duration(path: Path) -> tuple[float, int, int]:
    import wave

    try:
        with wave.open(str(path), "rb") as wf:
            sr = int(wf.getframerate() or 0)
            frames = int(wf.getnframes() or 0)
            ch = int(wf.getnchannels() or 1)
        if sr <= 0 or frames <= 0:
            raise TTSError(
                "Reference audio is invalid or contains no playable audio.",
                "REFERENCE_AUDIO_INVALID",
            )
        return frames / float(sr), sr, ch
    except TTSError:
        raise
    except Exception as exc:
        raise TTSError(
            "Reference audio is invalid or contains no playable audio.",
            "REFERENCE_AUDIO_INVALID",
        ) from exc


def validate_reference(path: Path | str) -> ReferenceInfo:
    raw_text = str(path or "").strip()
    if not raw_text:
        raise TTSError(
            "No reference voice file was selected.",
            "REFERENCE_AUDIO_NOT_FOUND",
        )
    lowered = raw_text.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        raise TTSError(
            "Reference audio must be a local file. Audio stays on this computer.",
            "REFERENCE_AUDIO_INVALID",
        )
    raw = Path(raw_text)
    if not raw.is_file():
        raise TTSError(
            f"Reference audio was not found:\n{raw}",
            "REFERENCE_AUDIO_NOT_FOUND",
        )
    suffix = raw.suffix.lower()
    if suffix not in ALLOWED_REFERENCE_SUFFIXES:
        raise TTSError(
            "Unsupported reference format. Use WAV, MP3, M4A, or FLAC.",
            "REFERENCE_AUDIO_INVALID",
        )
    if suffix == ".wav":
        try:
            duration, sr, ch = _wav_duration(raw)
        except TTSError:
            duration, sr, ch = _ffprobe_duration(raw)
    else:
        duration, sr, ch = _ffprobe_duration(raw)
    if duration < REF_MIN_SECONDS:
        raise TTSError(TOO_SHORT, "REFERENCE_AUDIO_TOO_SHORT")
    if duration > REF_MAX_SECONDS:
        raise TTSError(TOO_LONG, "REFERENCE_AUDIO_TOO_LONG")
    return ReferenceInfo(
        path=raw.resolve(),
        duration_seconds=duration,
        sample_rate=sr,
        channels=ch,
        suffix=suffix,
    )


def convert_reference_to_wav(src: Path, dest: Path) -> Path:
    """Convert any supported reference to mono WAV for Qwen (local ffmpeg only)."""
    src = Path(src)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".wav":
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise TTSError(
            "ffmpeg is required to convert this reference audio to WAV.",
            "REFERENCE_AUDIO_INVALID",
        )
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-ac", "1", "-ar", "24000",
        str(dest),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TTSError(
            "Could not convert the reference audio.",
            "REFERENCE_AUDIO_INVALID",
        ) from exc
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 64:
        raise TTSError(
            "Could not convert the reference audio to WAV.",
            "REFERENCE_AUDIO_INVALID",
        )
    return dest
