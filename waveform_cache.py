"""Real audio waveform peaks, cached per project (Semantic YT Studio 2.0
CapCut-style editor).

Decodes actual audio via the already-bundled ffmpeg binary (no new
dependency — deliberately avoids numpy: raw PCM samples are read directly
with the stdlib ``array`` module) and downsamples into (min, max) peak
pairs per pixel-bucket, the same representation every waveform-drawing
timeline uses. Cached to disk keyed by file identity (path, size, mtime) —
same "material inputs -> hash -> miss on any uncertainty" philosophy as
render_cache.py — so scrubbing/zooming/redrawing the timeline never
re-decodes the same unchanged audio file twice.
"""

from __future__ import annotations

import array
import hashlib
import json
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from providers import hidden_subprocess

WAVEFORM_SCHEMA_VERSION = 1
WAVEFORM_DIRNAME = "waveforms"
DEFAULT_BUCKETS = 400
_DECODE_SAMPLE_RATE = 3000  # far below audio fidelity — plenty for a peak envelope


def _file_identity(path: Path) -> Optional[tuple]:
    try:
        st = path.stat()
        return (str(path.resolve()), st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _cache_key(identity: tuple, buckets: int) -> str:
    payload = {"schema": WAVEFORM_SCHEMA_VERSION, "identity": identity, "buckets": buckets}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _decode_peaks(audio_path: Path, buckets: int) -> Optional[List[Tuple[float, float]]]:
    """Real decode: ffmpeg -> raw mono s16le PCM -> stdlib array -> per-
    bucket (min, max) in [-1, 1]. Returns None (never raises) on any
    ffmpeg/IO failure — callers must treat that as "no waveform available"
    and simply not draw one, never fabricate bars."""
    try:
        proc = hidden_subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", str(audio_path),
                "-ac", "1", "-ar", str(_DECODE_SAMPLE_RATE), "-f", "s16le", "-",
            ],
            capture_output=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    raw = proc.stdout
    raw = raw[: len(raw) - (len(raw) % 2)]  # drop a trailing odd byte, if any
    samples = array.array("h")
    try:
        samples.frombytes(raw)
    except (ValueError, OSError):
        return None
    n = len(samples)
    if n == 0:
        return []
    bucket_size = max(1, n // max(1, buckets))
    peaks: List[Tuple[float, float]] = []
    for i in range(0, n, bucket_size):
        chunk = samples[i : i + bucket_size]
        if not chunk:
            continue
        lo = min(chunk) / 32768.0
        hi = max(chunk) / 32768.0
        peaks.append((round(lo, 4), round(hi, 4)))
        if len(peaks) >= buckets:
            break
    return peaks


def get_or_build_waveform(
    state_dir: Path,
    audio_path: Path,
    *,
    buckets: int = DEFAULT_BUCKETS,
) -> Optional[List[Tuple[float, float]]]:
    """Disk-cached (min, max) peak list for ``audio_path``, or None if it
    can't be decoded (missing file, unsupported format, ffmpeg failure) —
    never a fabricated/placeholder waveform."""
    audio_path = Path(audio_path)
    identity = _file_identity(audio_path)
    if identity is None:
        return None
    cache_dir = Path(state_dir) / WAVEFORM_DIRNAME
    key = _cache_key(identity, buckets)
    cache_file = cache_dir / f"{key}.json"
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [(float(p[0]), float(p[1])) for p in data]
        except (OSError, ValueError, json.JSONDecodeError, IndexError, TypeError):
            pass  # corrupt cache entry -> fall through and rebuild

    peaks = _decode_peaks(audio_path, buckets)
    if peaks is None:
        return None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(peaks), encoding="utf-8")
    except OSError:
        pass  # caching is best-effort; the computed peaks are still returned
    return peaks


def clear_waveform_cache(state_dir: Path) -> None:
    import shutil

    try:
        shutil.rmtree(Path(state_dir) / WAVEFORM_DIRNAME, ignore_errors=True)
    except OSError:
        pass
