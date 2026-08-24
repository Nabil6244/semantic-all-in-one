"""Audio probing for the SFX import/validate tools."""

from __future__ import annotations

import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from providers import hidden_subprocess

SUPPORTED_SUFFIXES = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    suffix: str


def is_supported_audio(path: Path | str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_SUFFIXES


def probe_audio(path: Path | str) -> AudioInfo:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported audio format: {suffix}")

    if suffix == ".wav":
        try:
            with wave.open(str(path), "rb") as wf:
                sr = int(wf.getframerate() or 0)
                frames = int(wf.getnframes() or 0)
                ch = int(wf.getnchannels() or 1)
            if sr <= 0 or frames <= 0:
                raise ValueError("WAV file contains no readable audio frames.")
            return AudioInfo(path, frames / float(sr), sr, ch, suffix)
        except wave.Error as exc:
            raise ValueError(f"Invalid WAV file: {path} ({exc})") from exc

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError(
            f"ffprobe is required to inspect {suffix} files. Install ffmpeg or provide WAV sources."
        )
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=sample_rate,channels",
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]
    try:
        proc = hidden_subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not probe audio file: {path}") from exc
    if proc.returncode != 0:
        raise ValueError(f"Unreadable audio file: {path}")

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
        raise ValueError(f"Audio file has no playable duration: {path}")
    return AudioInfo(path, duration, sr or 44100, max(1, ch), suffix)


def convert_to_wav(src: Path, dest: Path) -> Path:
    """Convert supported audio to mono 48kHz WAV for the production library."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".wav" and src.resolve() == dest.resolve():
        return dest
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        if src.suffix.lower() == ".wav":
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            return dest
        raise RuntimeError("ffmpeg is required to convert non-WAV sources to WAV.")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "48000",
        str(dest),
    ]
    proc = hidden_subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"ffmpeg failed converting {src} to WAV.")
    return dest
